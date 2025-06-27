import json
import logging
import asyncio
import requests
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod
import os
import time


from prompts import PromptSystem, ActionParser
from conversation_logger import ConversationLogger

# # Configure logging
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
# )
logger = logging.getLogger("llm_agents")


class Agent(ABC):
    """Base class for Multi-Agent Systems"""
    def __init__(
        self,
        name: str,
        prompt_config_path: Optional[str] = None,
        log_dir: str = "logs",
        session_id: Optional[str] = None
    ):
        self.name = name
        self.conversation_history: List[Dict] = []
        self.prompt_system = PromptSystem(prompt_config_path)
        self.action_parser = ActionParser(prompt_config_path)
        self.logger = ConversationLogger(log_dir)
        self.session_id = session_id
        
        # 从配置文件加载 API 配置
        self.max_retries, self.retry_delay = self._load_api_config()
    
    def _load_api_config(self) -> tuple[int, int]:
        """从配置文件加载 API 配置"""
        try:
            with open('config/competition_config.json', 'r') as f:
                config = json.load(f)
                api_config = config.get('api_config', {})
                return (
                    api_config.get('max_retries', 20),
                    api_config.get('retry_delay', 10)
                )
        except Exception as e:
            logger.warning(f"无法加载配置文件，使用默认值: {e}")
            return 20, 10
    
    def truncate_conversation_history(self, max_turns: int = 10) -> None:
        """Truncate conversation history to keep only the latest turns and system prompt"""
        if len(self.conversation_history) <= max_turns * 2 + 1:  # +1 for system prompt
            return
            
        # Keep system prompt if it exists
        system_prompt = None
        if self.conversation_history and self.conversation_history[0]["role"] == "system":
            system_prompt = self.conversation_history[0]
            
        # Keep only the latest max_turns pairs of user/assistant messages
        self.conversation_history = self.conversation_history[-(max_turns * 2):]
        
        # Add back system prompt if it existed
        if system_prompt:
            self.conversation_history.insert(0, system_prompt)
    
    @abstractmethod
    async def generate_response(self, prompt: str) -> str:
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
        Process the competition state and action result, and return the next action.
        
        Args:
            state: Dictionary containing the current competition state
            action_result: Optional dictionary containing the result of the last action
        
        Returns:
            Dictionary containing the next action to take
        """
        # Create prompt using the prompt system
        prompt = self.prompt_system.create_prompt(state)
        
        # logger.info(f"Prompt: {prompt}")
        # If this is the first message, add system prompt
        if not self.conversation_history:
            self.add_to_conversation("system", self.prompt_system.config.get("system_prompt", ""))
        
        # Truncate conversation history before generating response
        self.truncate_conversation_history()
        
        # logger.info(f"Prompt: {prompt}")
        # Generate response
        response, tokens_used = await self.generate_response(state,prompt)
        
        # Parse action using the action parser
        action = self.action_parser.parse_action(response)
        action["tokens_used"] = tokens_used
        
        # # Save conversation after each interaction
        # self.save_conversation({
        #     "state": state,
        #     "action": action
        # })
        
        return action


class GenericAPIAgent(Agent):
    """Agent using any LLM service via API"""
    def __init__(
        self,
        name: str,
        model_id: str,
        api_base: str,
        api_key: str,
        prompt_config_path: Optional[str] = None,
        log_dir: str = "logs",
        session_id: Optional[str] = None,
        request_format: Dict = None,
        response_format: Dict = None,
        request_timeout: Optional[float] = 300
    ):
        """
        Initialize a generic API agent
        
        Args:
            name: Name of the agent
            model_id: Model ID to use
            api_base: Base URL of the API
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
        self.api_base = api_base.rstrip('/')
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
    
    async def generate_response(self, state: Dict, prompt: str) -> tuple[str, int]:
        """Generate a response using the configured API"""
        response = None
        # Add user message to conversation history
        self.add_to_conversation("user", prompt)
        self.save_conversation()
        for _ in range(self.max_retries):
            try:
                
                # Prepare request URL
                url = f"{self.api_base}{self.request_format['url']}"
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
                # logger.info(f"Formatted body: {formatted_body}")
                # Make the request
                response = await asyncio.to_thread(
                    requests.post,
                    url="http://localhost:5000/api/agent/request",
                    json={
                        "method": self.request_format['method'],
                        "url": url,
                        "headers": headers,
                        "json": formatted_body,
                        "timeout": self.request_timeout,
                        "response_format": self.response_format,
                        "competition_id": state.get("competition_id")
                    }
                )

                response.raise_for_status()

                # Directly unpack the list from the JSON response
                response_text, prompt_tokens, completion_tokens = response.json()

                # Add assistant response to conversation history
                self.add_to_conversation("assistant", response_text)
                self.save_conversation()
                self.conversation_history.pop()
                action = self.action_parser.parse_action(response_text)
                
                self.add_to_conversation("assistant", response_text)
                self.save_conversation()
                
                return response_text, (prompt_tokens, completion_tokens)
                
            except Exception as e:
                error_message = f"Error: {str(e)}"
                if response:
                    try:
                        error_message = f"Error: {response.json()}"
                    except json.JSONDecodeError:
                        error_message = f"Error: {response.text}"
                
                logger.error(f"Try {_ + 1} Error generating response with {self.name}: {error_message}")
                time.sleep(self.retry_delay)
        
        raise Exception(error_message)


class StreamingGenericAPIAgent(Agent):
    """Agent using any LLM service via API with streaming support"""
    def __init__(
        self,
        name: str,
        model_id: str,
        api_base: str,
        api_key: str,
        prompt_config_path: Optional[str] = None,
        log_dir: str = "logs",
        session_id: Optional[str] = None,
        request_format: Dict = None,
        response_format: Dict = None,
        request_timeout: Optional[float] = 300
    ):
        """
        Initialize a streaming generic API agent
        
        Args:
            name: Name of the agent
            model_id: Model ID to use
            api_base: Base URL of the API
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
        self.api_base = api_base.rstrip('/')
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
    
    async def generate_response(self, state: Dict, prompt: str) -> tuple[str, int]:
        """Generate a response using the configured API with streaming support"""
        response = None
        # Add user message to conversation history
        self.add_to_conversation("user", prompt)
        self.save_conversation()
        for _ in range(self.max_retries):
            try:
                
                # Prepare request URL
                url = f"{self.api_base}{self.request_format['url']}"
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
                    url="http://localhost:5000/api/agent/request",
                    json={
                        "method": self.request_format['method'],
                        "url": url,
                        "headers": headers,
                        "json": formatted_body,
                        "stream": True,
                        "timeout": self.request_timeout,
                        "response_format": self.response_format,
                        "competition_id": state.get("competition_id")
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

                reasoning_content, content, usage_info, prompt_tokens, completion_tokens = response.json()

                # Add assistant response to conversation history
                self.add_to_conversation("assistant", "<thinking>" + reasoning_content + "</thinking>\n\n" + content)
                self.save_conversation()
                self.conversation_history.pop()

                # if not content:
                #     # try to parse content from reasoning_content
                #     idx = reasoning_content.find("```json")
                action = self.action_parser.parse_action(content)
                
                # # Calculate tokens
                # prompt_tokens = usage_info.get("prompt_tokens", 0) if usage_info else 0
                # completion_tokens = usage_info.get("completion_tokens", 0) if usage_info else 0
                # reasoning_tokens = usage_info.get("completion_tokens_details", {}).get("reasoning_tokens", 0) if usage_info else 0
                # completion_tokens += reasoning_tokens

                return content, (prompt_tokens, completion_tokens)
            
            except Exception as e:
                if response:
                    error_message = f"Error: {response.json()}"
                    if response.status_code == 429:
                        logger.error(f"Rate limit exceeded.")
                        time.sleep(self.retry_delay*2)
                else:
                    error_message = f"Error: {str(e)}"
                logger.error(f"Try {_ + 1} Error generating response with {self.name}: {error_message}")
                time.sleep(self.retry_delay)
        
        raise Exception(error_message)