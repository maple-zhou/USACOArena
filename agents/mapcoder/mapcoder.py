"""
MapCoder Agent System for Programming Competition

This module implements MapCoder agent that uses a multi-agent system approach to solve
programming problems. The agent uses retrieval, planning, coding, and verification agents
to generate high-quality code solutions.

Main Components:
- MapCoderAgent: Agent that implements multi-agent system pattern for problem solving

The agent supports:
- Retrieval of similar problems and algorithms
- Step-by-step planning generation
- Code generation with iterative improvement
- Functional correctness evaluation
- Multiple LLM providers (OpenAI, Anthropic, Google, etc.)
- Conversation history management and truncation
- Token usage tracking and multipliers
- Retry logic with exponential backoff
- Response parsing and action extraction
"""

import json
import asyncio
import requests
import traceback
import time
import re
import xml.etree.ElementTree as ET
import tempfile
import subprocess
import psutil
from typing import Dict, List, Optional, Any
import os
from datetime import datetime

from competemas.models.agent import Agent
from competemas.utils.logger_config import get_logger

logger = get_logger("mapcoder_agents")


def clear_process(process):
    """Clear process and its children"""
    try:
        parent = psutil.Process(process.pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
        time.sleep(0.1)
    except psutil.NoSuchProcess:
        pass


def func_exec(directory: str, timeout: int):
    """Execute code in temporary directory with timeout"""
    try:
        if os.name == 'nt':
            command = "cd {} && dir && python {}".format(directory, "main.py")
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            command = "cd {}; python3 {};".format(directory, "main.py")
            process = subprocess.Popen(command,
                                    shell=True,
                                    preexec_fn=os.setsid,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE
                                    )
        
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            return_code = process.returncode
        except subprocess.TimeoutExpired:
            clear_process(process)
            return False, f"Timeout: Process exceeded the timeout of {timeout} seconds"

        if return_code == 0:
            clear_process(process)
            return True, "pass"
        else:
            error_output = stderr.decode('utf-8') if stderr else ""
            clear_process(process)
            if error_output:
                return False, error_output
            else:
                return True, "pass"
    except Exception as ex:
        return False, f"Error: {ex}"


def evaluate_functional_correctness(test_cases: list, completion: str, timeout: int = 1, stop_early: bool = False):
    """Evaluate functional correctness of generated code"""
    test_log = ""
    passed = True
    for io in test_cases:
        try:
            code = ("from typing import *\n" if "from typing import *" not in completion else "") + \
                completion + "\n" + io + "\n"
            with tempfile.TemporaryDirectory() as temp_dir:
                code_path = os.path.join(temp_dir, "main.py")
                with open(code_path, "w") as f:
                    f.write(code)
                is_pass, _ = func_exec(temp_dir, timeout)
            
            if is_pass:
                test_log += f"passed in test case: {io}\n"
            else:
                if stop_early:
                    return False, f"failed in test case: {io}\n"
                passed = False
                test_log += f"failed in test case: {io}\n"
        except Exception as e:
            if stop_early:
                return False, f"failed in test case: {io}\n"
            passed = False
            test_log += f"failed in test case: {io}\n"
    
    return passed, test_log


class MapCoderAgent(Agent):
    """
    MapCoder agent that uses multi-agent system pattern for problem solving.
    
    This agent is designed to solve complex programming problems by:
    1. Retrieval: Finding similar problems and algorithms
    2. Planning: Creating step-by-step solution plans
    3. Coding: Generating code based on plans
    4. Verification: Testing and improving code iteratively
    
    The agent supports:
    - Configurable API endpoints and authentication
    - Flexible request/response format templates
    - Token usage tracking and multipliers
    - Retry logic with exponential backoff
    - Conversation history management
    - Multi-agent coordination
    - Functional correctness evaluation
    """
    
    def __init__(
        self,
        name: str,
        model_id: str,
        api_base_url: str,
        api_key: str,
        prompt_config_path: Optional[str] = None,
        log_dir: str = "logs",
        session_id: Optional[str] = None,
        request_format: Optional[Dict] = None,
        response_format: Optional[Dict] = None,
        request_timeout: Optional[float] = 300,
        k: int = 3,
        t: int = 3,
        language: str = "Python"
    ):
        """
        Initialize a MapCoder agent
        
        Args:
            name: Name of the agent
            model_id: Model ID to use
            api_base_url: Base URL of the API
            api_key: API key for authentication
            prompt_config_path: Path to prompt configuration file
            log_dir: Directory to store conversation logs
            session_id: Optional session identifier
            request_format: Request format configuration
            response_format: Response format configuration
            request_timeout: Request timeout in seconds
            k: Number of similar problems to retrieve
            t: Number of improvement iterations
            language: Programming language to use
        """
        super().__init__(name, prompt_config_path, log_dir, session_id)
        self.model_id = model_id
        self._api_base_url = api_base_url.rstrip('/')
        self._api_key = api_key
        self.request_timeout = request_timeout
        self.k = k
        self.t = t
        self.language = language
        
        self.mapping = {
            1: "one (01)",
            2: "two (02)",
            3: "three (03)",
            4: "four (04)",
            5: "five (05)",
            6: "six (06)",
            7: "seven (07)",
            8: "eight (08)",
            9: "nine (09)",
        }
        
        # Default request format
        self.request_format = request_format or {
            "url": "/v1/chat/completions",
            "method": "POST",
            "headers": {
                "Content-Type": "application/json",
                "Authorization": "Bearer {api_key}"
            },
            "body_template": {
                "messages": "{messages}",
                "model": "{model_id}",
                "temperature": 0.7
            }
        }
        
        # Default response format
        self.response_format = response_format or {
            "response_path": "choices[0].message.content",
            "error_path": "error.message"
        }
    
    @property
    def name(self) -> str:
        """Get the agent name"""
        return self._name
    
    @property
    def api_base_url(self) -> str:
        """Get the API base URL"""
        return self._api_base_url
    
    @property
    def api_key(self) -> str:
        """Get the API key"""
        return self._api_key
    
    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Process the current state using multi-agent system pattern and return actions"""
        if not self.prompt_system or not self.action_parser:
            raise RuntimeError("PromptSystem and ActionParser must be initialized with prompt_config_path")
        
        # Generate prompt based on current state
        prompt = self.prompt_system.create_prompt(state)
        
        # Use multi-agent system approach to generate response
        response_text = await self.generate_response_mapcoder(state, prompt)
        logger.critical(f"\nNAME: {self.name}, response_text: {response_text}\n")
        
        # Parse action from response
        action = self.action_parser.parse_action(response_text)
        
        return action
    
    def _get_value_from_path(self, data: Dict, path: str) -> Any:
        """Extract value from nested dictionary using dot notation path"""
        if not path:
            return data
        
        parts = path.split('.')
        current = data
        
        for part in parts:
            if '[' in part:
                key, index = part.split('[')
                index = int(index.rstrip(']'))
                current = current[key][index]
            else:
                current = current[part]
        
        return current
    
    async def generate_response_mapcoder(self, state: Dict, prompt: str) -> str:
        """Generate response using multi-agent system pattern"""
        # Extract query from prompt
        query = prompt
        
        # Get sample I/O for testing
        sample_io = self.get_humaneval_sample_io(query)
        
        # Retrieval Agent: find k similar problems
        input_kb_exemplars = [
            {
                "role": "user",
                "content": self.create_retrieval_prompt(query),
            },
        ]
        
        response = await self._make_api_request(state, input_kb_exemplars[0]["content"])
        
        # Post processing
        response = self.trim_text(
            response, "# Identify the algorithm (Brute-force, Dynamic Programming, Divide-and-conquer, Greedy, Backtracking, Recursive, Binary search, and so on) that needs to be used to solve the original problem.")
        response = self.trim_text(
            response, "# Write a useful tutorial about the above mentioned algorithms. Provide a high level generic tutorial for solving this types of problem. Do not generate code.")
        response = self.trim_text(
            response, "# Planning to solve this problem:")
        response = self.trim_text(
            response, f"# Let's think step by step to solve this problem in {self.language} programming language.")
        response = self.replace_tag(response, 'algorithm')
        response = self.replace_tag(response, 'description')
        response = self.replace_tag(response, 'code')
        response = self.replace_tag(response, 'planning')

        response = self.parse_xml(response)

        algorithm_prompt = self.create_algorithm_prompt(response['algorithm'])
        sample_io_prompt = self.create_sample_io_prompt(sample_io)

        # Planning Agent: create step-by-step plans
        plannings = []
        for example_no, example in enumerate(response["problem"], start=1):
            example_problem = example["description"]
            example_planning = example["planning"]

            input_for_problem_planning = self.create_planning_prompt(
                example_problem, example_planning, algorithm_prompt, query, sample_io_prompt
            )
            
            planning = await self._make_api_request(state, input_for_problem_planning)
            
            input_for_planning_verification = self.create_verification_prompt(
                self.language, query, planning
            )
            
            verification_res = await self._make_api_request(state, input_for_planning_verification)

            verification_res = self.replace_tag(verification_res, 'explanation')
            verification_res = self.replace_tag(verification_res, 'confidence')

            verification_res = self.parse_xml(verification_res)

            verification_res['confidence'] = int(str(verification_res['confidence']).strip())

            plannings.append((
                planning,
                verification_res['confidence'],
                example
            ))

        plannings.sort(key=lambda x: x[1], reverse=True)
        std_input_prompt = ""   # HumanEval
        
        for planning_with_ex in plannings:
            planning, confidence, example = planning_with_ex

            input_for_final_code_generation = self.create_code_generation_prompt(
                self.language, algorithm_prompt, query, planning, sample_io_prompt, std_input_prompt
            )

            # Coding Agent: generate code
            code = await self._make_api_request(state, input_for_final_code_generation)
            code = self.parse_code(code)

            response_text = f"## Planning: {planning}\n## Code:\n```\n{code}\n```"
            passed = False

            for i in range(1, self.t + 1):
                passed, test_log = evaluate_functional_correctness(sample_io, code)

                if passed:
                    break

                # Debugging Agent: improve code
                input_for_improving_code = self.create_improvement_prompt(
                    self.language, algorithm_prompt, query, response_text, test_log, std_input_prompt
                )

                response = await self._make_api_request(state, input_for_improving_code)
                code = self.parse_code(response)

            if passed:
                break

        return code
    
    def create_retrieval_prompt(self, query: str) -> str:
        """Create retrieval prompt"""
        return f"""
        Find {self.mapping[self.k]} similar programming problems to the following problem.
        
        Problem:
        {query}
        
        For each similar problem, provide:
        1. A brief description of the problem
        2. The algorithm used to solve it
        3. A step-by-step planning approach
        
        Return the results in XML format:
        <root>
            <algorithm>Algorithm name</algorithm>
            <problem>
                <description>Problem description</description>
                <planning>Step-by-step planning</planning>
            </problem>
            <!-- Repeat for k problems -->
        </root>
        """
    
    def create_algorithm_prompt(self, algorithm: str) -> str:
        """Create algorithm explanation prompt"""
        return f"""
        Algorithm: {algorithm}
        
        This algorithm is typically used for problems that require:
        - [Key characteristics of the algorithm]
        - [When to use this approach]
        - [Common patterns and techniques]
        """
    
    def create_sample_io_prompt(self, sample_io: list) -> str:
        """Create sample I/O prompt"""
        if len(sample_io) > 0:
            if isinstance(sample_io[0], str):
                return "\n".join(sample_io)
            if isinstance(sample_io[0], dict):
                return "\n".join([f"Input:\n{io['input']}\nExpected output:\n{io['output'][0]}" for io in sample_io])
        return str(sample_io)
    
    def create_planning_prompt(self, example_problem: str, example_planning: str, 
                             algorithm_prompt: str, query: str, sample_io_prompt: str) -> str:
        """Create planning prompt"""
        return f"""
        Based on the following example, create a step-by-step plan to solve the given problem.
        
        Example Problem: {example_problem}
        Example Planning: {example_planning}
        
        {algorithm_prompt}
        
        Problem to solve: {query}
        
        Sample I/O:
        {sample_io_prompt}
        
        Create a detailed step-by-step plan to solve this problem.
        """
    
    def create_verification_prompt(self, language: str, query: str, planning: str) -> str:
        """Create verification prompt"""
        return f"""
        Verify if the following planning is appropriate for solving the problem.
        
        Problem: {query}
        Planning: {planning}
        Language: {language}
        
        Return in XML format:
        <root>
            <explanation>Your explanation</explanation>
            <confidence>Confidence score (1-10)</confidence>
        </root>
        """
    
    def create_code_generation_prompt(self, language: str, algorithm_prompt: str, 
                                    query: str, planning: str, sample_io_prompt: str, 
                                    std_input_prompt: str) -> str:
        """Create code generation prompt"""
        return f"""
        Generate code to solve the following problem.
        
        {algorithm_prompt}
        
        Problem: {query}
        Planning: {planning}
        
        Sample I/O:
        {sample_io_prompt}
        
        {std_input_prompt}
        
        Generate the complete solution in {language}.
        """
    
    def create_improvement_prompt(self, language: str, algorithm_prompt: str, 
                                query: str, response: str, test_log: str, 
                                std_input_prompt: str) -> str:
        """Create code improvement prompt"""
        return f"""
        Improve the following code based on the test results.
        
        {algorithm_prompt}
        
        Problem: {query}
        Current solution: {response}
        
        Test results: {test_log}
        
        {std_input_prompt}
        
        Generate an improved version of the code in {language}.
        """
    
    async def _make_api_request(self, state: Dict, prompt: str) -> str:
        """Make API request with retry logic"""
        response = None
        for _ in range(self.max_retries):
            try:
                competition_id = state.get('competitor_state', {}).get('competition_id')
                participant_id = state.get('competitor_state', {}).get('id')
                
                # Prepare request URL
                url = f"http://localhost:5000/api/agent/call/{competition_id}/{participant_id}"
                
                # Prepare request headers
                headers = {
                    k: v.format(api_key=self.api_key)
                    for k, v in self.request_format['headers'].items()
                }
                
                # Prepare request body
                body = self.request_format['body_template'].copy()
                formatted_body = {}
                for key, value in body.items():
                    if isinstance(value, str):
                        formatted_body[key] = value.format(
                            messages=json.dumps([{"role": "user", "content": prompt}]),
                            model_id=self.model_id
                        )
                    else:
                        formatted_body[key] = value
                
                # Parse the formatted messages back to JSON
                if "messages" in formatted_body:
                    formatted_body["messages"] = json.loads(formatted_body["messages"])

                # Make the request
                response = await asyncio.to_thread(
                    requests.request,
                    method=self.request_format['method'],
                    url=url,
                    headers=headers,
                    json=formatted_body,
                )
                response.raise_for_status()

                # Get the first element from the array response
                result_array = response.json()
                result = result_array[0]  # Extract the actual response object from the array

                response_text = self._get_value_from_path(result, self.response_format["response_path"])
                
                # Check if response contains valid JSON or markdown
                def is_valid_json_or_has_markdown(text):
                    if not text:
                        return False
                    
                    # Check if contains ```json markdown
                    if re.search(r'```json', text, re.IGNORECASE):
                        return True
                    
                    # Check if directly is JSON format
                    try:
                        json.loads(text.strip())
                        return True
                    except (json.JSONDecodeError, ValueError):
                        return False
                
                if response_text and not is_valid_json_or_has_markdown(response_text):
                    logger.error(f"NOT FOUND ```json markdown block or valid JSON in response for {self.name}")
                    time.sleep(self.retry_delay)
                    continue
                
                return response_text
                
            except Exception as e:
                error_message = f"Error: {str(e)}"
                if response:
                    try:
                        error_message = f"Error: {response.json()}"
                    except json.JSONDecodeError:
                        error_message = f"Error: {response.text}"
                
                logger.error(f"Try {_ + 1} Error generating response with {self.name}: {error_message}")
                time.sleep(self.retry_delay)
        
        raise Exception(f"Failed to generate response after {self.max_retries} attempts")
    
    def parse_code(self, response: str) -> str:
        """Parse code from response"""
        if "```" not in response:
            return response

        code_pattern = r'```((.|\n)*?)```'
        if "```Python" in response:
            code_pattern = r'```Python((.|\n)*?)```'
        if "```Python3" in response:
            code_pattern = r'```Python3((.|\n)*?)```'
        if "```python" in response:
            code_pattern = r'```python((.|\n)*?)```'
        if "```python3" in response:
            code_pattern = r'```python3((.|\n)*?)```'
        if "```C" in response:
            code_pattern = r'```C((.|\n)*?)```'
        if "```c" in response:
            code_pattern = r'```c((.|\n)*?)```'
        if "```C++" in response:
            code_pattern = r'```C\+\+((.|\n)*?)```'
        if "```c++" in response:
            code_pattern = r'```c\+\+((.|\n)*?)```'
        if "```Java" in response:
            code_pattern = r'```Java((.|\n)*?)```'
        if "```java" in response:
            code_pattern = r'```java((.|\n)*?)```'
        if "```Node" in response:
            code_pattern = r'```Node((.|\n)*?)```'
        if "```node" in response:
            code_pattern = r'```node((.|\n)*?)```'
        if "```Rust" in response:
            code_pattern = r'```Rust((.|\n)*?)```'
        if "```rust" in response:
            code_pattern = r'```rust((.|\n)*?)```'
        if "```PHP" in response:
            code_pattern = r'```PHP((.|\n)*?)```'
        if "```php" in response:
            code_pattern = r'```php((.|\n)*?)```'
        if "```Go" in response:
            code_pattern = r'```Go((.|\n)*?)```'
        if "```go" in response:
            code_pattern = r'```go((.|\n)*?)```'
        if "```Ruby" in response:
            code_pattern = r'```Ruby((.|\n)*?)```'
        if "```ruby" in response:
            code_pattern = r'```ruby((.|\n)*?)```'
        if "```C#" in response:
            code_pattern = r'```C#((.|\n)*?)```'
        if "```c#" in response:
            code_pattern = r'```c#((.|\n)*?)```'
        if "```csharp" in response:
            code_pattern = r'```csharp((.|\n)*?)```'

        code_blocks = re.findall(code_pattern, response, re.DOTALL)

        if isinstance(code_blocks[-1], (tuple, list)):
            code_str = "\n".join(code_blocks[-1])
        elif isinstance(code_blocks[-1], str):
            code_str = code_blocks[-1]
        else:
            code_str = response

        return code_str

    @staticmethod
    def trim_text(text: str, trimmed_text: str) -> str:
        """Trim text by removing specified substring"""
        return text.replace(trimmed_text, '').strip()
    
    @staticmethod
    def replace_tag(text: str, tag: str) -> str:
        """Replace XML tags with CDATA sections"""
        if f'<{tag}><![CDATA[' in text and f']]></{tag}>' in text:
            return text 
        else:
            return text.replace(f'<{tag}>', f'<{tag}><![CDATA[').replace(f'</{tag}>', f']]></{tag}>').strip()
    
    @staticmethod
    def get_humaneval_sample_io(query: str) -> list:
        """Extract sample I/O from HumanEval format query"""
        pattern = r'>>> (.*?)\n\s*([^\n>]*)'
        matches = re.findall(pattern, query)
        
        assertions = []
        
        for match in matches:
            function_call = match[0].strip()
            expected_output = match[1].strip()
            
            if expected_output and not expected_output.startswith('>>>'):
                assertions.append(f"assert {function_call} == {expected_output}")
            elif not expected_output:
                assertions.append(f"assert {function_call} is None")
        
        return assertions

    def xml_to_dict(self, element) -> dict:
        """Convert XML element to dictionary"""
        result = {}
        for child in element:
            if child:
                child_data = self.xml_to_dict(child)
                if child.tag in result:
                    if isinstance(result[child.tag], list):
                        result[child.tag].append(child_data)
                    else:
                        result[child.tag] = [result[child.tag], child_data]
                else:
                    result[child.tag] = child_data
            else:
                result[child.tag] = child.text
        return result

    def parse_xml(self, response: str) -> dict:
        """Parse XML response to dictionary"""
        if '```xml' in response:
            response = response.replace('```xml', '')
        if '```' in response:
            response = response.replace('```', '')

        try:
            root = ET.fromstring(response)
        except:
            try:
                root = ET.fromstring('<root>\n' + response + '\n</root>')
            except:
                root = ET.fromstring('<root>\n' + response)
        return self.xml_to_dict(root) 