import base64
import gzip
import json
import lzma
import requests
from typing import List, Optional
from ..models.models import Submission, Problem, Case, TestResult, SubmissionStatus, Competition
from ..utils.logger_config import get_logger

logger = get_logger("judge")

class Judge:
    """
    Judge class to handle code evaluation using the local OJ system based on online-judge-rust.
    """
    def __init__(self, oj_endpoint: str = "http://localhost:8000/usacoarena/oj/compile-and-execute"):
        self.oj_endpoint = oj_endpoint
        # Large test cases exceed AWS Lambda's payload limit; compress inputs above this size (bytes)
        self._stdin_compress_threshold = 700_000
        # AWS Lambda synchronous invoke hard limit is 6 MB (6,291,456 bytes);
        # keep a small safety margin but allow large xz-encoded payloads.
        self._stdin_base64_limit = 6_100_000
        logger.debug(f"Initialized Judge with OJ service at {oj_endpoint}")
    
    def evaluate_submission(self, submission: Submission, problem: Problem, competition: Optional[Competition] = None, first_one: bool = False) -> Submission:
        """
        Evaluate a submission against all test cases of a problem.
        Updates the submission with test results, final status, and score.
        """
        logger.debug(f"Evaluating submission {submission.id} for problem {problem.id}")
        
        from ..utils.problem_loader import USACOProblemLoader
        problem_loader = USACOProblemLoader()
        test_cases = problem_loader.load_test_cases(problem.id)
        total_tests = len(test_cases)
        logger.debug(f"Loaded {total_tests} test cases")

        # Set initial values
        try:
            # Run the code against each test case
            for test_case in test_cases:
                logger.debug(f"Running test case {test_case.id}")
                test_result = self._run_test(
                    submission.code,
                    submission.language,
                    test_case.input_data,
                    test_case.expected_output,
                    problem.time_limit_ms,
                    problem.memory_limit_mb * 1024  # Convert MB to KB
                )
                submission.test_results.append(test_result)
                logger.debug(f"Test case {test_case.id} result: {test_result.status}")
                
                if test_result.status != SubmissionStatus.ACCEPTED:
                    submission.status = test_result.status
                    logger.critical(f"Submission failed on test case {test_case.id} with status {test_result.status}")
                    break
            else:
                submission.status = SubmissionStatus.ACCEPTED
                logger.debug("Submission passed all test cases")
            
            # Calculate pass_score
            # OLD: Calculate score (proportion of test cases passed * max score)
            # passed_tests = sum(1 for result in submission.test_results if result.status == SubmissionStatus.ACCEPTED)
            # base_score = problem.get_problem_base_score(competition) if competition else 0
            # submission.pass_score = int((passed_tests / total_tests) * base_score) if total_tests > 0 else 0

            # NEW: Only give score when submission is fully accepted (AC)
            base_score = problem.get_problem_base_score(competition) if competition else 0
            if submission.status == SubmissionStatus.ACCEPTED:
                submission.pass_score = base_score
            else:
                submission.pass_score = 0

            # Calculate first AC bonus
            first_ac_bonus = problem.get_problem_firstAC_bonus(competition) if competition else 0
            if submission.status == SubmissionStatus.ACCEPTED and first_ac_bonus > 0 and first_one:
                submission.pass_score += first_ac_bonus
                logger.debug(f"Added first AC bonus of {first_ac_bonus} points")


            # Calculate submission tokens
            submission.submission_tokens = submission.calculate_submission_tokens(competition)
            
            # Calculate penalty
            submission.penalty = submission.calculate_penalty(competition)
            
            logger.info(f"Submission pass score: {submission.pass_score}, Penalty: {submission.penalty}")
            return submission
        
        except Exception as e:
            # Handle any exceptions during evaluation
            logger.error(f"Error evaluating submission: {str(e)}", exc_info=True)
            submission.status = SubmissionStatus.COMPILATION_ERROR
            submission.test_results = [
                TestResult(
                    test_case_id="error",
                    status=SubmissionStatus.COMPILATION_ERROR,
                    error_message=str(e)
                )
            ]
            submission.pass_score = 0
            submission.penalty = submission.calculate_penalty(competition)
            return submission
    
    def _run_test(
        self,
        code: str,
        language: str,
        input_data: str,
        expected_output: str,
        time_limit_ms: int,
        memory_limit_kb: int
    ) -> TestResult:
        """
        Run a single test case against the OJ system.
        Returns a TestResult with the outcome.
        """
        try:
            # Prepare the request payload for the OJ
            payload = {
                "compile": {
                    "source_code": code,
                    "compiler_options": self._get_compiler_options(language),
                    "language": self._get_language_code(language)
                },
                "execute": self._build_execute_payload(
                    input_data,
                    time_limit_ms,
                    memory_limit_kb
                ),
            }

            response = requests.post(
                self.oj_endpoint,
                json=payload,
            )
            
            # Parse the response - handle multi-level JSON structure
            response_json = response.json()
            if 'body' in response_json and isinstance(response_json['body'], str):
                result = json.loads(response_json['body'])
            else:
                result = response_json
            
            # Extract relevant information
            compile_result = result.get("compile", {})
            execute_result = result.get("execute", {})
            
            # Check for compilation errors
            if compile_result.get("exit_code", 0) != 0:
                return TestResult(
                    test_case_id="compilation",
                    status=SubmissionStatus.COMPILATION_ERROR,
                    error_message=compile_result.get("stderr", "Compilation failed")
                )
            
            # Check for runtime errors
            exit_code = execute_result.get("exit_code", 0)
            if exit_code != 0:
                stderr = execute_result.get("stderr", "")

                # Check for different types of runtime issues
                verdict = execute_result.get("verdict", "").lower()
                stderr_lower = stderr.lower()
                if (
                    verdict == "time limit exceeded"
                    or "time limit" in stderr_lower
                    or exit_code in (124, 31744)
                    or "status 124" in stderr_lower
                ):
                    status = SubmissionStatus.TIME_LIMIT_EXCEEDED
                elif verdict == "memory limit exceeded" or "memory limit" in stderr_lower:
                    status = SubmissionStatus.MEMORY_LIMIT_EXCEEDED
                else:
                    status = SubmissionStatus.RUNTIME_ERROR

                return TestResult(
                    test_case_id="execution",
                    status=status,
                    runtime_ms=self._parse_time(execute_result.get("wall_time", "0")),
                    memory_kb=self._parse_memory(execute_result.get("memory_usage", "0")),
                    output=execute_result.get("stdout", ""),
                    error_message=stderr
                )
            
            # Get actual output and compare with expected
            actual_output = execute_result.get("stdout", "").strip()
            expected_output = expected_output.strip()
            
            # Check memory usage before determining final status
            memory_used = self._parse_memory(execute_result.get("memory_usage", "0"))
            if memory_used > memory_limit_kb:
                return TestResult(
                    test_case_id="execution",
                    status=SubmissionStatus.MEMORY_LIMIT_EXCEEDED,
                    runtime_ms=self._parse_time(execute_result.get("wall_time", "0")),
                    memory_kb=memory_used,
                    output=actual_output
                )
            
            # Determine status based on output comparison
            status = SubmissionStatus.ACCEPTED if self._compare_outputs(actual_output, expected_output) else SubmissionStatus.WRONG_ANSWER
            
            return TestResult(
                test_case_id="execution",
                status=status,
                runtime_ms=self._parse_time(execute_result.get("wall_time", "0")),
                memory_kb=memory_used,
                output=actual_output
            )
            
        except Exception as e:
            # Handle any exceptions during the OJ communication
            return TestResult(
                test_case_id="error",
                status=SubmissionStatus.RUNTIME_ERROR,
                error_message=str(e)
            )

    def _build_execute_payload(
        self,
        input_data: str,
        time_limit_ms: int,
        memory_limit_kb: int
    ) -> dict:
        execute_payload = {
            "timeout_ms": time_limit_ms,
            "memory_limit_kb": memory_limit_kb,
        }

        input_bytes = input_data.encode("utf-8")

        if len(input_bytes) <= self._stdin_compress_threshold:
            execute_payload["stdin"] = input_data
            return execute_payload

        gzip_compressed = gzip.compress(input_bytes)
        gzip_encoded = base64.b64encode(gzip_compressed).decode("ascii")

        if len(gzip_encoded) <= self._stdin_base64_limit:
            logger.debug(
                "Compressing stdin with gzip: original=%d bytes, compressed=%d bytes, encoded=%d bytes",
                len(input_bytes),
                len(gzip_compressed),
                len(gzip_encoded),
            )
            execute_payload["stdin_gzip_base64"] = gzip_encoded
            return execute_payload

        xz_compressed = lzma.compress(input_bytes, format=lzma.FORMAT_XZ, preset=6)
        xz_encoded = base64.b64encode(xz_compressed).decode("ascii")

        if len(xz_encoded) <= self._stdin_base64_limit:
            logger.debug(
                "Compressing stdin with xz: original=%d bytes, compressed=%d bytes, encoded=%d bytes",
                len(input_bytes),
                len(xz_compressed),
                len(xz_encoded),
            )
            execute_payload["stdin_xz_base64"] = xz_encoded
            return execute_payload

        raise ValueError(
            "Input test case remains too large after compression; consider splitting or using stdin_id"
        )

    def _get_compiler_options(self, language: str) -> str:
        """Get appropriate compiler options based on language"""
        language = language.lower()
        if language in ["c++", "cpp"]:
            return "-O2 -std=c++17"
        elif language == "java":
            return ""
        elif language in ["python", "python3"]:
            return ""
        else:
            return ""
    
    def _get_language_code(self, language: str) -> str:
        """Convert user-friendly language name to OJ language code"""
        language = language.lower()
        if language in ["c++", "cpp"]:
            return "cpp"
        elif language == "java":
            return "java21"
        elif language in ["python", "python3"]:
            return "py12"
        else:
            return language
    
    def _compare_outputs(self, actual: str, expected: str) -> bool:
        """
        Compare actual and expected outputs.
        Handles common formatting differences.
        """
        # Normalize line endings
        actual = actual.replace("\r\n", "\n").strip()
        expected = expected.replace("\r\n", "\n").strip()
        
        # Simple exact match
        if actual == expected:
            return True
        
        # Normalize whitespace
        actual_normalized = " ".join(actual.split())
        expected_normalized = " ".join(expected.split())
        
        if actual_normalized == expected_normalized:
            return True
        
        # Check if they're both numbers and numerically equivalent
        try:
            actual_float = float(actual)
            expected_float = float(expected)
            # Allow small floating-point difference
            return abs(actual_float - expected_float) < 1e-6
        except (ValueError, TypeError):
            pass
        
        # More advanced comparisons could be added here
        
        return False
    
    def test_oj_connection(self) -> bool:
        """Test the connection to the OJ system with a simple problem"""
        test_code = """
#include <iostream>
using namespace std;

int main() {
  int a, b;
  cin >> a >> b;
  cout << a + b << endl;
  return 0;
}
"""
        try:
            payload = {
                "compile": {
                    "source_code": test_code,
                    "compiler_options": "-O2 -std=c++17",
                    "language": "cpp"
                },
                "execute": self._build_execute_payload("5 7", 5000, 256 * 1024)
            }

            response = requests.post(
                self.oj_endpoint,
                json=payload,
            )

            response_json = response.json()
            if 'body' in response_json and isinstance(response_json['body'], str):
                result = json.loads(response_json['body'])
            else:
                result = response_json
            
            # Extract relevant information
            execute_result = result.get("execute", {})
            
            
            # Check if we got the expected output "12"
            return execute_result.get("stdout", "").strip() == "12"
        
        except Exception:
            return False

    def _parse_time(self, time_str: str) -> int:
        """Parse time string to milliseconds"""
        try:
            # Convert seconds to milliseconds
            return int(float(time_str) * 1000)
        except (ValueError, TypeError):
            return 0

    def _parse_memory(self, memory_str: str) -> int:
        """Parse memory string to KB"""
        try:
            return int(memory_str)
        except (ValueError, TypeError):
            return 0

    def test_code_with_custom_cases(
        self,
        code: str,
        language: str,
        test_cases: List[Case],
        time_limit_ms: int = 5000,
        memory_limit_mb: int = 256
    ) -> List[TestResult]:
        """
        Test code against user-provided custom test cases.
        This method does not affect competition scoring and is used for code verification only.

        Args:
            code: Source code to test
            language: Programming language
            test_cases: List of test cases with input and expected output
            time_limit_ms: Time limit in milliseconds
            memory_limit_mb: Memory limit in MB

        Returns:
            List of TestResult objects containing execution results
        """
        logger.debug(f"Testing code with {len(test_cases)} custom test cases")

        test_results = []
        memory_limit_kb = memory_limit_mb * 1024  # Convert MB to KB

        try:
            # Run the code against each custom test case
            for i, test_case in enumerate(test_cases):
                logger.debug(f"Running custom test case {i+1}")
                test_result = self._run_test(
                    code,
                    language,
                    test_case.input_data,
                    test_case.expected_output,
                    time_limit_ms,
                    memory_limit_kb
                )
                test_result.test_case_id = f"custom_case_{i+1}"
                test_results.append(test_result)
                logger.debug(f"Custom test case {i+1} result: {test_result.status}")

        except Exception as e:
            # Handle any exceptions during testing
            logger.error(f"Error testing code with custom cases: {str(e)}", exc_info=True)
            test_results = [
                TestResult(
                    test_case_id="error",
                    status=SubmissionStatus.RUNTIME_ERROR,
                    error_message=str(e)
                )
            ]

        logger.info(f"Completed testing with {len(test_results)} custom test case results")
        return test_results
