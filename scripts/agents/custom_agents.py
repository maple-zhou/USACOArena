"""
LLM Agent System for Programming Competition

This module implements various agent classes that can interact with different LLM providers
and participate in programming competitions. The agents handle conversation management,
API requests, response parsing, and action execution.

Main Components:
- Agent: Abstract base class defining the agent interface
- GenericAPIAgent: Generic agent that can work with any LLM API
- StreamingGenericAPIAgent: Agent with streaming support for real-time responses

The agents support:
- Multiple LLM providers (OpenAI, Anthropic, Google, etc.)
- Conversation history management and truncation
- Token usage tracking and multipliers
- Retry logic with exponential backoff
- Response parsing and action extraction
"""

from cgitb import reset
import json
import asyncio
import requests
import traceback
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod
import os
import time

from scripts.prompts.custom_prompts import PromptSystem, ActionParser
from competemas.utils.conversation_logger import ConversationLogger
from competemas.engine.agent_interface import AgentInterface
from competemas.utils.logger_config import get_logger

logger = get_logger("llm_agents")


class Agent(AgentInterface, ABC):
    """
    Abstract base class for LLM agents in programming competitions.
    
    This class provides the foundation for all agent implementations, handling:
    - Conversation history management
    - Prompt generation and response parsing
    - Logging and session management
    - API configuration loading
    
    Subclasses must implement the generate_response method to handle
    communication with specific LLM providers.
    """
    
    def __init__(
        self,
        name: str,
        prompt_config_path: Optional[str] = None,
        log_dir: str = "logs",
        session_id: Optional[str] = None
    ):
        """
        Initialize the agent with basic configuration.
        
        Args:
            name: Unique identifier for this agent
            prompt_config_path: Path to JSON file containing prompt templates
            log_dir: Directory for storing conversation logs
            session_id: Optional session identifier for tracking conversations
        """
        self._name = name
        self.conversation_history: List[Dict] = []  # Stores conversation messages
        self.prompt_system = PromptSystem(prompt_config_path)  # Handles prompt generation
        self.action_parser = ActionParser(prompt_config_path)  # Parses LLM responses into actions
        self.logger = ConversationLogger(log_dir)  # Manages conversation logging
        self.session_id = session_id  # Session tracking for conversation continuity
        self._api_base_url = ""
        self._api_key = ""
        
        # Load API configuration from configuration file
        self.max_retries, self.retry_delay = self._load_api_config()
    
    @property
    def name(self) -> str:
        """Get the agent name"""
        return self._name
    
    @name.setter 
    def name(self, value: str) -> None:
        """Set the agent name"""
        self._name = value
    
    @property
    def api_base_url(self) -> str:
        """Get the agent's API base URL"""
        return self._api_base_url
    
    @api_base_url.setter
    def api_base_url(self, value: str) -> None:
        """Set the agent's API base URL"""
        self._api_base_url = value
    
    @property
    def api_key(self) -> str:
        """Get the agent's API key"""
        return self._api_key
    
    @api_key.setter
    def api_key(self, value: str) -> None:
        """Set the agent's API key"""
        self._api_key = value
    
    def _load_api_config(self) -> tuple[int, int]:
        """Load API configuration from configuration file"""
        try:
            with open('config/competition_config.json', 'r') as f:
                config = json.load(f)
                api_config = config.get('api_config', {})
                return (
                    api_config.get('max_retries', 20),
                    api_config.get('retry_delay', 10)
                )
        except Exception as e:
            logger.warning(f"Unable to load configuration file, using default values: {e}")
            return 20, 10
    
    def truncate_conversation_history(self, max_turns: int = 10) -> None:
        """
        Truncate conversation history to prevent context length overflow.
        
        Keeps the system prompt (if exists) and the most recent conversation turns
        to stay within token limits while maintaining conversation context.
        
        Args:
            max_turns: Maximum number of user/assistant conversation pairs to keep
        """
        # If history is already short enough, no truncation needed
        if len(self.conversation_history) <= max_turns * 2 + 1:  # +1 for system prompt
            return
            
        # Preserve the system prompt if it exists at the beginning
        system_prompt = None
        if self.conversation_history and self.conversation_history[0]["role"] == "system":
            system_prompt = self.conversation_history[0]
            
        # Keep only the latest max_turns pairs of user/assistant messages
        # This ensures we don't exceed the context window while maintaining recent context
        self.conversation_history = self.conversation_history[-(max_turns * 2):]
        
        # Restore the system prompt at the beginning if it existed
        if system_prompt:
            self.conversation_history.insert(0, system_prompt)
    
    @abstractmethod
    async def generate_response(self, state: Dict, prompt: str) -> str:
        """Generate a response from the MAS"""
        pass
    
    def add_to_conversation(self, role: str, content: str) -> None:
        """Add a message to the conversation history"""
        self.conversation_history.append({"role": role, "content": content})
    
    def get_conversation_history(self) -> List[Dict]:
        """Get the conversation history"""
        return self.conversation_history
    
    def save_conversation(self, metadata: Optional[Dict] = None) -> str:
        """Save the current conversation history"""
        return self.logger.save_conversation(
            self.name,
            self.conversation_history,
            self.session_id,
            metadata
        )
    
    async def process(self, state: Dict) -> Dict:
        """
        Process the current competition state and generate the next action.
        
        This is the main method that orchestrates the agent's decision-making process:
        1. Create a prompt based on the current competition state
        2. Initialize system prompt if this is the first interaction
        3. Manage conversation history to stay within context limits
        4. Generate a response from the LLM
        5. Parse the response into a structured action
        6. Track token usage for billing and limits
        
        Args:
            state: Dictionary containing the current competition state, including:
                   - competition details
                   - available problems
                   - participant status
                   - rankings
                   - last action result
        
        Returns:
            Dictionary containing the next action to take, with fields:
            - action: The action type (e.g., "VIEW_PROBLEM", "submission_SOLUTION")
            - parameters: Action-specific parameters
            - tokens_used: Tuple of (prompt_tokens, completion_tokens)
        """
        # Create contextual prompt using the current competition state
        prompt = self.prompt_system.create_prompt(state)
        # logger.error(f"prompt: {prompt}")
        
        # Initialize system prompt on first interaction to establish agent behavior
        if not self.conversation_history:
            system_prompt = self.prompt_system.config.get("system_prompt", "")
            self.add_to_conversation("system", system_prompt)
        
        # Truncate conversation history to prevent context length overflow
        # This maintains recent context while staying within token limits
        self.truncate_conversation_history()
        
        
        # Generate response from the LLM using the current state and prompt
        response = await self.generate_response(state, prompt)
        # logger.error(f"0000000response: {response}")
        # Parse the LLM response into a structured action that the competition system can execute
        action = self.action_parser.parse_action(response)
        # print(f"action: {action}")
        # action: {'action': 'VIEW_PROBLEM', 'parameters': {'problem_id': '1323_bronze_feb'}}
    
        # action["tokens_used"] = tokens_used  # Track token usage for billing and limits
        
        # Optional: Save conversation for debugging and analysis
        # Uncomment the following lines to enable conversation logging
        # self.save_conversation({
        #     "state": state,
        #     "action": action
        # })
        
        return action


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
        self.api_base_url = api_base_url.rstrip('/')
        self.api_key = api_key
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

    async def _make_request(self, *, state: Dict, model: str, messages: List[Dict], **kwargs) -> requests.Response:
        """
        Makes a request to the local server with an OpenAI-like signature.
        It constructs the OpenAI-style request body from its arguments.
        """
        # 1. Construct the OpenAI-style request body from the function arguments.
        openai_input = {
            "model": model,
            "messages": messages,
            **kwargs
        }

        # 2. Wrap the OpenAI-style body in the payload for our local server.
        # This info points to the real LLM endpoint.
        target_url = f"{self.api_base_url}{self.request_format['url']}"
        target_headers = {
            k: v.format(api_key=self.api_key)
            for k, v in self.request_format['headers'].items()
        }

        # Get competition/participant IDs for the local server's URL.
        competition_id = state.get('competitor_state', {}).get('competition_id')
        participant_id = state.get('competitor_state', {}).get('id')
        
        # This is the final payload for our local proxy server.
        server_payload = {
            "method": self.request_format['method'],
            "url": target_url,
            "headers": target_headers,
            "json": openai_input,  # The OpenAI-style body is nested here.
            "timeout": self.request_timeout,
            "response_format": self.response_format,
        }
        
        # The URL for our local proxy server.
        server_url = f"http://localhost:5000/api/agent/call/{competition_id}/{participant_id}"
        
        # 3. Make the async request to the local proxy server.
        response = await asyncio.to_thread(
            requests.post,
            url=server_url,
            json=server_payload
        )
        
        response.raise_for_status()
        return response

    async def generate_response(self, state: Dict, prompt: str) -> str:
        """Generate a response using the configured API."""
        response = None
        # Add user message to conversation history.
        self.add_to_conversation("user", prompt)
        self.save_conversation()
        for _ in range(self.max_retries):
            try:
                # 1. Get any extra OpenAI parameters from the template (e.g., temperature).
                extra_params = self.request_format['body_template'].copy()
                extra_params.pop("model", None)
                extra_params.pop("messages", None)

                # 2. Call _make_request with an OpenAI-like signature.
                response = await self._make_request(
                    state=state,
                    model=self.model_id,
                    messages=self.conversation_history,
                    **extra_params  # Pass other params like temperature.
                )

                # 3. Process the response from the server.
                result_array = response.json()
                result = result_array[0]  # The server wraps the real response in an array.
                response_text = self._get_value_from_path(result, self.response_format["response_path"])
                
                # Add assistant response to conversation history and then remove it 
                # to keep the history clean for the next turn.
                self.add_to_conversation("assistant", response_text)
                self.save_conversation()
                self.conversation_history.pop()
                
                return response_text
                
            except Exception as e:
                error_message = f"Error: {str(e)}"
                if response:
                    try:
                        error_message = f"Error: {response.json()}"
                    except json.JSONDecodeError:
                        error_message = f"Error: {response.text}"
                
                # Print detailed traceback information.
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
        self.api_base_url = api_base_url.rstrip('/')
        self.api_key = api_key
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
        
        # Default response format
        self.response_format = response_format or {
            "response_path": "choices[0].message.content",
            "error_path": "error.message"
        }
    
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
        """Generate a response using the configured API with streaming support"""
        response = None
        # Add user message to conversation history
        self.add_to_conversation("user", prompt)
        self.save_conversation()
        for _ in range(self.max_retries):
            try:
                
                # Prepare request URL
                url = f"{self.api_base_url}{self.request_format['url']}"
                # print(f"StreamingGenericAPIAgent,url: {url}")
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
                
                # # Make the streaming request
                # response = await asyncio.to_thread(
                #     requests.post,
                #     url=url,
                #     headers=headers,
                #     json=formatted_body,
                #     stream=True,
                #     timeout=self.request_timeout
                # )

                response = await asyncio.to_thread(
                    requests.post,
                    url=f"http://localhost:5000/api/agent/{state.get('competition_id')}/{state.get('participant_id')}/request",
                    json={
                        "method": self.request_format['method'],
                        "url": url,
                        "headers": headers,
                        "json": formatted_body,
                        "stream": True,
                        "timeout": self.request_timeout,
                        "response_format": self.response_format,
                    }
                )

                response.raise_for_status()
                
                # # Process streaming response
                # reasoning_content = ""
                # content = ""
                # usage_info = None
                
                # for line in response.iter_lines():
                #     if line:
                #         # Skip "data: " prefix
                #         if line.startswith(b"data: "):
                #             line = line[6:]
                        
                #         # Skip heartbeat message
                #         if line == b"[DONE]":
                #             break
                        
                #         try:
                #             # Parse JSON data
                #             chunk = json.loads(line.decode('utf-8'))
                            
                #             # Check for usage information
                #             if "usage" in chunk:
                #                 usage_info = chunk["usage"]
                            
                #             # Extract reasoning_content and content
                #             if "choices" in chunk and len(chunk["choices"]) > 0:
                #                 delta = chunk["choices"][0].get("delta", {})
                #                 if "reasoning_content" in delta and delta["reasoning_content"]:
                #                     reasoning_content += delta["reasoning_content"]
                #                 elif "content" in delta and delta["content"] is not None:
                #                     content += delta["content"]
                #         except json.JSONDecodeError:
                #             continue

                # Parse response similar to GenericAPIAgent  
                result_array = response.json()
                result = result_array[0]  # Extract the actual response object from the array
                
                # Extract response text using configured path
                response_text = self._get_value_from_path(result, self.response_format["response_path"])
                
                # Extract token usage information
                prompt_tokens = result.get("usage", {}).get("prompt_tokens", 0)
                completion_tokens = result.get("usage", {}).get("completion_tokens", 0)
                reasoning_tokens = result.get("usage", {}).get("completion_tokens_details", {}).get("reasoning_tokens", 0)
                completion_tokens += reasoning_tokens

                # Add assistant response to conversation history
                self.add_to_conversation("assistant", response_text)
                self.save_conversation()
                self.conversation_history.pop()

                action = self.action_parser.parse_action(response_text)
                
                return response_text, (prompt_tokens, completion_tokens)
            
            except ValueError as e:
                if response:
                    error_message = f"Error: {response.json()}"
                    if response.status_code == 429:
                        logger.error(f"Rate limit exceeded.")
                        time.sleep(self.retry_delay*2)
                else:
                    error_message = f"Error: {str(e)}"
                
                # Print detailed traceback information
                # traceback_str = traceback.format_exc()
                # print(f"\n=== DETAILED ERROR TRACEBACK for {self.name} (Try {_ + 1}) ===")
                # print(f"Error Message: {error_message}")
                # print(f"Full Traceback:\n{traceback_str}")
                # print("=" * 60)
                
                logger.error(f"Try {_ + 1} Error generating response with {self.name}: {error_message}")
                time.sleep(self.retry_delay)
        
        raise Exception(error_message)