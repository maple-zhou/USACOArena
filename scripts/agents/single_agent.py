"""
LLM Agent System for Programming Competition

This module implements various agent classes that can interact with different LLM providers
and participate in programming competitions. The agents handle conversation management,
API requests, response parsing, and action execution.

Main Components:
- GenericAPIAgent: Generic agent that can work with any LLM API
- StreamingGenericAPIAgent: Agent with streaming support for real-time responses

The agents support:
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
from typing import Dict, List, Optional, Any
import os
from datetime import datetime

from competemas.models.agent import Agent
from competemas.utils.logger_config import get_logger

logger = get_logger("llm_agents")


class GenericAPIAgent(Agent):
    """
    Generic agent that can communicate with any LLM API provider.
    
    This agent is designed to work with various LLM services by allowing
    customizable request and response formats. It supports:
    - Configurable API endpoints and authentication
    - Flexible request/response format templates
    - Token usage tracking and multipliers
    - Retry logic with exponential backoff
    - Conversation history management
    
    Common use cases:
    - OpenAI GPT models (gpt-4, gpt-3.5-turbo)
    - Anthropic Claude models
    - Google Gemini models
    - Custom or local LLM endpoints
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
        request_timeout: Optional[float] = 300
    ):
        """
        Initialize a generic API agent
        
        Args:
            name: Name of the agent
            model_id: Model ID to use
            api_base_url: Base URL of the API
            api_key: API key for authentication
            prompt_config_path: Path to prompt configuration file
            log_dir: Directory to store conversation logs
            session_id: Optional session identifier
            request_format: Request format configuration with the following fields:
                - url: API endpoint path
                - method: Request method (GET/POST)
                - headers: Request headers
                - body_template: Request body template with placeholders for {prompt}, etc.
            response_format: Response format configuration with the following fields:
                - response_path: Path to extract text from response (e.g., "choices[0].text")
                - error_path: Path to extract error message from response
        """
        super().__init__(name, prompt_config_path, log_dir, session_id)
        self.model_id = model_id
        self._api_base_url = api_base_url.rstrip('/')
        self._api_key = api_key
        self.request_timeout = request_timeout
        
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
        """Process the current state and return actions"""
        if not self.prompt_system or not self.action_parser:
            raise RuntimeError("PromptSystem and ActionParser must be initialized with prompt_config_path")
        # Generate prompt based on current state
        prompt = self.prompt_system.create_prompt(state)
        
        # Generate response from LLM
        response_text = await self.generate_response(state, prompt)
        
        
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
    
    async def generate_response(self, state: Dict, prompt: str) -> str:
        """Generate a response using the configured API"""
        response = None
        # Add user message to conversation history
        self.add_to_conversation("user", prompt)
        self.save_conversation()
        for _ in range(self.max_retries):
            try:
                
                competition_id = state.get('competitor_state', {}).get('competition_id')
                participant_id = state.get('competitor_state', {}).get('id')
                # Prepare request URL
                url = f"http://localhost:5000/api/agent/call/{competition_id}/{participant_id}"
                # print(f"GenericAPIAgent,url: {url}")
                # Prepare request headers
                headers = {
                    k: v.format(api_key=self.api_key)
                    for k, v in self.request_format['headers'].items()
                }
                
                # Prepare request body
                body = self.request_format['body_template'].copy()
                # Format the template values
                formatted_body = {}
                for key, value in body.items():
                    if isinstance(value, str):
                        # If the value is a template string, format it
                        formatted_body[key] = value.format(
                            messages=json.dumps(self.conversation_history),
                            model_id=self.model_id
                        )
                    else:
                        # If the value is not a string (e.g., temperature), keep it as is
                        formatted_body[key] = value
                
                # Parse the formatted messages back to JSON
                if "messages" in formatted_body:
                    formatted_body["messages"] = json.loads(formatted_body["messages"])
                
                has_json_block = False
                # Make the request
                json_retry_count = 0
                while not has_json_block and json_retry_count < 5:
                    response = await asyncio.to_thread(
                        requests.request,
                        method=self.request_format['method'],
                        url=url,
                        headers=headers,
                        json=formatted_body,
                        # timeout=self.request_timeout
                    )
                    response.raise_for_status()

                    # logger.error(f"LLM response: {response.json()}")

                    # print(f"LLMresponse: {response.json()}")
                    # Get the first element from the array response
                    result_array = response.json()
                    result = result_array[0]  # Extract the actual response object from the array

                    # print("\ngenerate_response result: ", result)
                    response_text = self._get_value_from_path(result, self.response_format["response_path"])
                    
                    logger.critical(f"\nNAME: {self.name}, response_text: {response_text}\n")
                    
                    # 检查response_text中是否包含```json标记或直接是JSON格式
                    def is_valid_json_or_has_markdown(text):
                        if not text:
                            return False
                        
                        # 检查是否包含```json标记
                        if re.search(r'```json', text, re.IGNORECASE):
                            return True
                        
                        # 检查是否直接是JSON格式
                        try:
                            json.loads(text.strip())
                            return True
                        except (json.JSONDecodeError, ValueError):
                            return False
                    
                    if response_text and not is_valid_json_or_has_markdown(response_text):
                        logger.error(f"NOT FOUND ```json markdown block or valid JSON in response for {self.name}")
                        json_retry_count += 1
                        time.sleep(self.retry_delay)
                    else:
                        has_json_block = True
                        if re.search(r'```json', response_text, re.IGNORECASE):
                            logger.info(f"Found ```json markdown block in response for {self.name}")
                        else:
                            logger.info(f"Found valid JSON format in response for {self.name}")
                    
                    # print(f"response_text: {response_text}")
                    # print("\n\n")
                    # prompt_tokens = result.get("usage", {}).get("prompt_tokens", 0)
                    # completion_tokens = result.get("usage", {}).get("completion_tokens", 0)
                    # reasoning_tokens = result.get("usage", {}).get("completion_tokens_details", {}).get("reasoning_tokens", 0)
                    # completion_tokens += reasoning_tokens

                    # Add assistant response to conversation history
                    self.add_to_conversation("assistant", response_text)
                    self.save_conversation()
                    self.conversation_history.pop()
                    # action = self.action_parser.parse_action(response_text)
                    

                return response_text
                
            except Exception as e:
                error_message = f"Error: {str(e)}"
                if response:
                    try:
                        error_message = f"Error: {response.json()}"
                    except json.JSONDecodeError:
                        error_message = f"Error: {response.text}"
                
                # Print detailed traceback information
                traceback_str = traceback.format_exc()
                print(f"\n=== DETAILED ERROR TRACEBACK for {self.name} (Try {_ + 1}) ===")
                print(f"Error Message: {error_message}")
                # print(f"Full Traceback:\n{traceback_str}")
                print("=" * 60)
                
                logger.error(f"Try {_ + 1} Error generating response with {self.name}: {error_message}")
                time.sleep(self.retry_delay)
        
        raise Exception(error_message)


class StreamingGenericAPIAgent(Agent):
    """
    Generic agent with streaming support for real-time LLM responses.
    
    This agent extends GenericAPIAgent to support streaming responses, which provides:
    - Real-time response generation as tokens are produced
    - Lower perceived latency for users
    - Ability to process reasoning content separately from final output
    - Support for models with thinking/reasoning capabilities
    
    Streaming is particularly useful for:
    - Interactive applications requiring immediate feedback
    - Long-form responses where partial content is valuable
    - Models that expose internal reasoning (like Claude with thinking)
    - Reducing time-to-first-token in user interfaces
    
    The agent handles the complexity of streaming protocols and provides
    the same interface as the non-streaming version.
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
        request_timeout: Optional[float] = 300
    ):
        """
        Initialize a streaming generic API agent
        
        Args:
            name: Name of the agent
            model_id: Model ID to use
            api_base_url: Base URL of the API
            api_key: API key for authentication
            prompt_config_path: Path to prompt configuration file
            log_dir: Directory to store conversation logs
            session_id: Optional session identifier
            request_format: Request format configuration with the following fields:
                - url: API endpoint path
                - method: Request method (GET/POST)
                - headers: Request headers
                - body_template: Request body template with placeholders for {prompt}, etc.
            response_format: Response format configuration with the following fields:
                - response_path: Path to extract text from response (e.g., "choices[0].text")
                - error_path: Path to extract error message from response
        """
        super().__init__(name, prompt_config_path, log_dir, session_id)
        self.model_id = model_id
        self._api_base_url = api_base_url.rstrip('/')
        self._api_key = api_key
        self.request_timeout = request_timeout
        
        # Default request format with streaming enabled
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
                "temperature": 0.7,
                "stream": True,
                "stream_options": {
                    "include_usage": True
                },
                "enable_thinking": True
            }
        }
        
        # Default response format for streaming
        self.response_format = response_format or {
            "response_path": "choices[0].message.content",
            "error_path": "error.message",
            "reasoning_path": "choices[0].message.reasoning",
            "usage_path": "usage"
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
        """Process the current state and return actions"""
        if not self.prompt_system or not self.action_parser:
            raise RuntimeError("PromptSystem and ActionParser must be initialized with prompt_config_path")
        # Generate prompt based on current state
        prompt = self.prompt_system.create_prompt(state)
        # Generate response from LLM (returns content, (prompt_tokens, completion_tokens))
        content, _ = await self.generate_response(state, prompt)
        # Parse action from response content
        action = self.action_parser.parse_action(content)
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
    
    async def generate_response(self, state: Dict, prompt: str) -> tuple[str, tuple[int, int]]:
        """Generate a streaming response using the configured API"""
        # Add user message to conversation history
        self.add_to_conversation("user", prompt)
        self.save_conversation()
        
        for _ in range(self.max_retries):
            try:
                competition_id = state.get('competitor_state', {}).get('competition_id')
                participant_id = state.get('competitor_state', {}).get('id')
                
                # Prepare request URL for streaming
                url = f"http://localhost:5000/api/stream_agent/call/{competition_id}/{participant_id}"
                
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
                            messages=json.dumps(self.conversation_history),
                            model_id=self.model_id
                        )
                    else:
                        formatted_body[key] = value
                
                # Parse the formatted messages back to JSON
                if "messages" in formatted_body:
                    formatted_body["messages"] = json.loads(formatted_body["messages"])

                # Make the streaming request
                response = await asyncio.to_thread(
                    requests.request,
                    method=self.request_format['method'],
                    url=url,
                    headers=headers,
                    json=formatted_body,
                    timeout=self.request_timeout
                )
                response.raise_for_status()

                # Parse streaming response
                result_array = response.json()
                
                # Extract components from the array response
                reasoning_content = result_array[0] if len(result_array) > 0 else ""
                content = result_array[1] if len(result_array) > 1 else ""
                usage_info = result_array[2] if len(result_array) > 2 else {}
                prompt_tokens = result_array[3] if len(result_array) > 3 else 0
                completion_tokens = result_array[4] if len(result_array) > 4 else 0

                # Add assistant response to conversation history
                self.add_to_conversation("assistant", content)
                self.save_conversation()
                self.conversation_history.pop()
                
                return content, (prompt_tokens, completion_tokens)
                
            except Exception as e:
                error_message = f"Error: {str(e)}"
                logger.error(f"Try {_ + 1} Error generating streaming response with {self.name}: {error_message}")
                time.sleep(self.retry_delay)
        
        raise Exception(f"Failed to generate streaming response after {self.max_retries} attempts")