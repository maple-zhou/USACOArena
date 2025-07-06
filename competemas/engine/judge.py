import json
import subprocess
import requests
from typing import Dict, List, Optional, Any
from ..models.models import Submission, Problem, Case, TestResult, SubmissionStatus, Competition
from ..utils.logger_config import get_logger

logger = get_logger("judge")

class Judge:
    """
    Judge class to handle code evaluation using the local OJ system based on online-judge-rust.
    """
    def __init__(self, oj_endpoint: str = "http://localhost:9000/2015-03-31/functions/function/invocations"):
        self.oj_endpoint = oj_endpoint
        logger.info(f"Initialized Judge with OJ service at {oj_endpoint}")
    
    def evaluate_submission(self, submission: Submission, problem: Problem, competition: Optional[Competition] = None, first_one: bool = False) -> Submission:
        """
        Evaluate a submission against all test cases of a problem.
        Updates the submission with test results, final status, and score.
        """
        logger.info(f"Evaluating submission {submission.id} for problem {problem.id}")
        
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
                    logger.info(f"Submission failed on test case {test_case.id} with status {test_result.status}")
                    break
            else:
                submission.status = SubmissionStatus.ACCEPTED
                logger.info("Submission passed all test cases")
            
            # Calculate pass_score
            # Calculate score (proportion of test cases passed * max score)
            passed_tests = sum(1 for result in submission.test_results if result.status == SubmissionStatus.ACCEPTED)
            base_score = problem.get_problem_base_score(competition) if competition else 0
            submission.pass_score = int((passed_tests / total_tests) * base_score) if total_tests > 0 else 0
            # Calculate first AC bonus  
            first_ac_bonus = problem.get_problem_firstAC_bonus(competition) if competition else 0
            if submission.status == SubmissionStatus.ACCEPTED and first_ac_bonus > 0 and first_one:
                submission.pass_score += first_ac_bonus
                logger.info(f"Added first AC bonus of {first_ac_bonus} points")


            # Calculate submission tokens
            submission.submission_tokens = submission.calculate_submission_tokens(competition)
            
            # Calculate penalty
            submission.penalty = submission.calculate_penalty(competition)
            
            logger.info(f"Final submission score: {submission.pass_score}, Penalty: {submission.penalty}")
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
                "version": "2.0",
                "rawPath": "/compile-and-execute",
                "requestContext": {
                    "http": {
                        "method": "POST",
                        "path": "/compile-and-execute"
                    }
                },
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps({
                    "compile": {
                        "source_code": code,
                        "compiler_options": self._get_compiler_options(language),
                        "language": self._get_language_code(language)
                    },
                    "execute": {
                        "stdin": input_data,
                        "timeout_ms": time_limit_ms
                    }
                }),
                "isBase64Encoded": False
            }
            
            # Send request to OJ
            response = requests.post(
                self.oj_endpoint,
                json=payload,
                # headers={"Content-Type": "application/json"}
            )
            
            # Parse the response - handle multi-level JSON structure
            response_json = response.json()
            # The actual result is inside 'body' as a string
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
            if execute_result.get("exit_code", 0) != 0:
                stderr = execute_result.get("stderr", "")
                
                # Check for different types of runtime issues
                verdict = execute_result.get("verdict", "").lower()
                if verdict == "time limit exceeded" or "time limit" in stderr.lower():
                    status = SubmissionStatus.TIME_LIMIT_EXCEEDED
                elif verdict == "memory limit exceeded" or "memory limit" in stderr.lower():
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
                "version": "2.0",
                "rawPath": "/compile-and-execute",
                "requestContext": {
                    "http": {
                        "method": "POST",
                        "path": "/compile-and-execute"
                    }
                },
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps({
                    "compile": {
                        "source_code": test_code,
                        "compiler_options": "-O2 -std=c++17",
                        "language": "cpp"
                    },
                    "execute": {
                        "stdin": "5 7",
                        "timeout_ms": 5000
                    }
                }),
                "isBase64Encoded": False
            }
            
            response = requests.post(
                self.oj_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            # Parse the response - handle multi-level JSON structure
            response_json = response.json()
            # The actual result is inside 'body' as a string
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