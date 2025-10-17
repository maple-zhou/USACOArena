import json
import requests
from typing import List, Optional
from ..models.models import Submission, Problem, Case, TestResult, SubmissionStatus, Competition
from ..utils.logger_config import get_logger

logger = get_logger("judge")

class Judge:
    """
    Judge class to handle code evaluation using the local OJ system based on online-judge-rust.
    """
    def __init__(self, oj_endpoint: str = "http://localhost:10086/compile-and-execute"):
        self.oj_endpoint = oj_endpoint
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
            first_failure_status: Optional[SubmissionStatus] = None
            first_failure_case_id: Optional[str] = None

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

                if test_result.status != SubmissionStatus.ACCEPTED and first_failure_status is None:
                    first_failure_status = test_result.status
                    first_failure_case_id = test_case.id
                    logger.critical(
                        f"Submission encountered first failing test case {test_case.id} with status {test_result.status}"
                    )

            if first_failure_status is None:
                submission.status = SubmissionStatus.ACCEPTED
                logger.debug("Submission passed all test cases")
            else:
                submission.status = first_failure_status
                logger.critical(
                    f"Submission marked as {first_failure_status} based on failing test case {first_failure_case_id}; remaining tests executed"
                )
            
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
            compile_section = {
                "source_code": code,
                "language": self._get_language_code(language),
            }

            compiler_options = self._get_compiler_options(language)
            if compiler_options:
                compile_section["compiler_options"] = compiler_options

            payload = {
                "compile": compile_section,
                "execute": self._build_execute_payload(
                    input_data,
                    time_limit_ms,
                ),
                "test_case": self._build_test_case_payload(expected_output),
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

            stdout = execute_result.get("stdout", "")
            stderr = execute_result.get("stderr", "")
            verdict = execute_result.get("verdict")
            runtime_ms = self._parse_time(execute_result.get("wall_time", "0"))
            memory_used = self._parse_memory(execute_result.get("memory_usage", "0"))

            status = self._map_verdict(verdict)

            if status is None:
                exit_code = execute_result.get("exit_code", 0)
                if exit_code != 0:
                    stderr_lower = stderr.lower()
                    if (
                        "time limit" in stderr_lower
                        or exit_code in (124, 31744)
                        or "status 124" in stderr_lower
                    ):
                        status = SubmissionStatus.TIME_LIMIT_EXCEEDED
                    elif "memory limit" in stderr_lower:
                        status = SubmissionStatus.MEMORY_LIMIT_EXCEEDED
                    else:
                        status = SubmissionStatus.RUNTIME_ERROR
                else:
                    actual_output = stdout.strip()
                    expected = expected_output.strip()
                    status = (
                        SubmissionStatus.ACCEPTED
                        if self._compare_outputs(actual_output, expected)
                        else SubmissionStatus.WRONG_ANSWER
                    )
            actual_output = stdout.strip()

            if status == SubmissionStatus.ACCEPTED and memory_used > memory_limit_kb:
                status = SubmissionStatus.MEMORY_LIMIT_EXCEEDED

            error_message = stderr if status != SubmissionStatus.ACCEPTED and stderr else None

            return TestResult(
                test_case_id="execution",
                status=status,
                runtime_ms=runtime_ms,
                memory_kb=memory_used,
                output=actual_output,
                error_message=error_message,
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
    ) -> dict:
        return {
            "stdin": input_data,
            "timeout_ms": time_limit_ms,
        }

    def _build_test_case_payload(self, expected_output: str) -> dict:
        return {
            "checker_type": "strict_diff",
            "expected_output": expected_output,
        }

    def _map_verdict(self, verdict: Optional[str]) -> Optional[SubmissionStatus]:
        if not verdict:
            return None

        normalized = verdict.strip().lower()
        mapping = {
            "accepted": SubmissionStatus.ACCEPTED,
            "wrong_answer": SubmissionStatus.WRONG_ANSWER,
            "presentation_error": SubmissionStatus.WRONG_ANSWER,
            "time_limit_exceeded": SubmissionStatus.TIME_LIMIT_EXCEEDED,
            "output_limit_exceeded": SubmissionStatus.RUNTIME_ERROR,
            "runtime_error": SubmissionStatus.RUNTIME_ERROR,
            "memory_limit_exceeded": SubmissionStatus.MEMORY_LIMIT_EXCEEDED,
        }

        return mapping.get(normalized)

    def _get_compiler_options(self, language: str) -> List[str]:
        """Get appropriate compiler options based on language"""
        language = language.lower()
        if language in ["c++", "cpp"]:
            return ["-O2", "-std=c++17"]
        elif language == "java":
            return []
        elif language in ["python", "python3"]:
            return []
        else:
            return []
    
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
            compile_section = {
                "source_code": test_code,
                "language": "cpp",
            }
            options = self._get_compiler_options("cpp")
            if options:
                compile_section["compiler_options"] = options

            payload = {
                "compile": compile_section,
                "execute": self._build_execute_payload("5 7", 5000),
                "test_case": self._build_test_case_payload("12\n"),
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
