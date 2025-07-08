import openai,os
messages = [
    {"role": "user", "content": "今天阳光正正好，从书架上随机抽了一本书，读了三个小时"}
]
os.environ["OPENAI_API_KEY"] = "sk-EFhZxTqkXfedmKP_yxB8-XIisFkXQ7JGL6sunBI3XBfQfinP3oBgl5wzqDw"
# client = OpenAI(api_key=OPENAI_API_KEY)
response = openai.OpenAI(base_url="http://100.76.8.43:10086/v1").chat.completions.create(
        model="sf-deepseek-v3",
        # model="claude-3-sonnet-20240229",
        messages = messages,
        # timeout=30,
        # limit_tokens=200,
        # temperature=0.1,
        # logprobs=True,
        # top_logprobs=5,
    )
print(response)
print('\n')
# print(response.choices[0].message.content)


'''
# ChatCompletion 对象结构
ChatCompletion(
    # 唯一标识符
    id='0197af0a6d77e14a6523d3449ef49915',
    
    # 选择结果列表
    choices=[
        Choice(
                # 完成原因：stop 表示正常完成
            finish_reason='stop',
                # 选择索引
            index=0,
                # 日志概率（未启用）
            logprobs=None,
                # 消息内容
            message=ChatCompletionMessage(
                    # AI 回复的具体内容
                content='看来今天是个适合沉浸于文字的好日子呢！阳光、随机邂逅的书、三小时心无旁骛的阅读——这种偶然与专注交织的时刻，往往藏着意外的惊喜。\n\n你抽到的或许是一本早就想读却迟迟未翻开的书，又或者是一本被遗忘的旧书忽然焕发出新意义。无论是哪种，能在阳光里一口气读上三小时，大概是被书中的世界温柔地「捕獲」了吧？好奇是什么样的书让时间变得透明了呢…\n\n如果愿意分享，我很想听听：书中是否有某个片段突然照亮了你的思绪？或是这种不刻意规划的阅读，让你重新感受到了翻页时的雀跃？（连书架上的灰尘在阳光下飞舞的样子，可能都成了这段阅读记忆的注脚呢 ✨）',
                    # 拒绝内容（无）
                refusal=None,
                    # 角色：assistant 表示 AI 助手
                role='assistant',
                    # 函数调用（无）
                function_call=None,
                    # 工具调用（无）
                tool_calls=None
            )
        )
    ],
    
        # 创建时间戳
    created=1750988385,
        # 使用的模型名称
    model='deepseek-ai/DeepSeek-V3',
        # 对象类型
    object='chat.completion',
        # 服务层级（无）
    service_tier=None,
        # 系统指纹（无）
    system_fingerprint=None,
    
        # Token 使用情况
    usage=CompletionUsage(
            # 完成 token 数量
        completion_tokens=161,
            # 提示 token 数量
        prompt_tokens=19,
            # 总 token 数量
        total_tokens=180,
            # 提示 token 详细信息（空）
        prompt_tokens_details={},
            # 完成 token 详细信息
        completion_tokens_details={
            'reasoning_tokens': 0,
            'accepted_prediction_tokens': 0,
            'rejected_prediction_tokens': 0
        }
    )
)



'''

# """
# 通用 LLM API 调用工具函数
# 支持多种 LLM 服务的统一接口
# """

# import os
# import json
# import time
# import requests
# import openai
# from typing import Dict, List, Optional, Tuple, Any
# import logging

# # 配置日志
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # ==================== OpenAI 兼容 API ====================

# def call_openai_compatible_api(
#     messages: List[Dict[str, str]],
#     model: str = "gpt-3.5-turbo",
#     api_base: str = "https://api.openai.com/v1",
#     api_key: str = None,
#     temperature: float = 0.7,
#     limit_tokens: int = 1000,
#     timeout: int = 30,
#     **kwargs
# ) -> Tuple[str, int]:
#     """
#     调用 OpenAI 兼容的 API
    
#     Args:
#         messages: 对话消息列表
#         model: 模型名称
#         api_base: API 基础 URL
#         api_key: API 密钥
#         temperature: 温度参数
#         limit_tokens: 最大 token 数
#         timeout: 超时时间（秒）
#         **kwargs: 其他参数
    
#     Returns:
#         Tuple[str, int]: (响应内容, 使用的 token 数)
#     """
#     try:
#         # 设置 API 密钥
#         if api_key:
#             os.environ["OPENAI_API_KEY"] = api_key
        
#         # 创建客户端
#         client = openai.OpenAI(
#             base_url=api_base,
#             api_key=api_key or os.getenv("OPENAI_API_KEY")
#         )
        
#         # 调用 API
#         response = client.chat.completions.create(
#             model=model,
#             messages=messages,
#             temperature=temperature,
#             limit_tokens=limit_tokens,
#             timeout=timeout,
#             **kwargs
#         )
        
#         # 解析响应
#         content = response.choices[0].message.content
#         usage = response.usage
        
#         # 计算 token 使用量
#         total_tokens = usage.total_tokens if usage else 0
        
#         logger.info(f"OpenAI API 调用成功: {model}, tokens: {total_tokens}")
#         return content, total_tokens
        
#     except Exception as e:
#         logger.error(f"OpenAI API 调用失败: {e}")
#         raise

# # ==================== 旧版 OpenAI API ====================

# def call_openai_legacy_api(
#     messages: List[Dict[str, str]],
#     model: str = "gpt-3.5-turbo",
#     api_base: str = "https://api.openai.com/v1",
#     api_key: str = None,
#     temperature: float = 0.7,
#     limit_tokens: int = 1000,
#     **kwargs
# ) -> Tuple[str, int]:
#     """
#     调用旧版 OpenAI API（openai < 1.0）
    
#     Args:
#         messages: 对话消息列表
#         model: 模型名称
#         api_base: API 基础 URL
#         api_key: API 密钥
#         temperature: 温度参数
#         limit_tokens: 最大 token 数
#         **kwargs: 其他参数
    
#     Returns:
#         Tuple[str, int]: (响应内容, 使用的 token 数)
#     """
#     try:
#         # 设置 API 密钥
#         if api_key:
#             os.environ["OPENAI_API_KEY"] = api_key
        
#         # 调用旧版 API
#         response = openai.ChatCompletion.create(
#             model=model,
#             messages=messages,
#             temperature=temperature,
#             limit_tokens=limit_tokens,
#             api_base=api_base,
#             **kwargs
#         )
        
#         # 解析响应
#         content = response.choices[0].message.content
#         usage = response.usage
        
#         # 计算 token 使用量
#         total_tokens = usage.total_tokens if usage else 0
        
#         logger.info(f"OpenAI Legacy API 调用成功: {model}, tokens: {total_tokens}")
#         return content, total_tokens
        
#     except Exception as e:
#         logger.error(f"OpenAI Legacy API 调用失败: {e}")
#         raise

# # ==================== 自定义 HTTP API ====================

# def call_custom_http_api(
#     messages: List[Dict[str, str]],
#     api_url: str,
#     headers: Dict[str, str] = None,
#     model: str = None,
#     temperature: float = 0.7,
#     limit_tokens: int = 1000,
#     timeout: int = 30,
#     **kwargs
# ) -> Tuple[str, int]:
#     """
#     调用自定义 HTTP API
    
#     Args:
#         messages: 对话消息列表
#         api_url: API 端点 URL
#         headers: HTTP 请求头
#         model: 模型名称
#         temperature: 温度参数
#         limit_tokens: 最大 token 数
#         timeout: 超时时间（秒）
#         **kwargs: 其他参数
    
#     Returns:
#         Tuple[str, int]: (响应内容, 使用的 token 数)
#     """
#     try:
#         # 构建请求数据
#         payload = {
#             "messages": messages,
#             "temperature": temperature,
#             "limit_tokens": limit_tokens,
#             **kwargs
#         }
        
#         if model:
#             payload["model"] = model
        
#         # 设置默认请求头
#         default_headers = {
#             "Content-Type": "application/json"
#         }
#         if headers:
#             default_headers.update(headers)
        
#         # 发送请求
#         response = requests.post(
#             api_url,
#             json=payload,
#             headers=default_headers,
#             timeout=timeout
#         )
#         response.raise_for_status()
        
#         # 解析响应
#         result = response.json()
        
#         # 提取内容（支持多种响应格式）
#         content = None
#         if "choices" in result and len(result["choices"]) > 0:
#             choice = result["choices"][0]
#             if "message" in choice:
#                 content = choice["message"].get("content", "")
#             elif "text" in choice:
#                 content = choice["text"]
#         elif "response" in result:
#             content = result["response"]
#         elif "content" in result:
#             content = result["content"]
#         else:
#             content = str(result)
        
#         # 计算 token 使用量
#         total_tokens = 0
#         if "usage" in result:
#             usage = result["usage"]
#             total_tokens = usage.get("total_tokens", 0)
        
#         logger.info(f"Custom HTTP API 调用成功: {api_url}, tokens: {total_tokens}")
#         return content, total_tokens
        
#     except Exception as e:
#         logger.error(f"Custom HTTP API 调用失败: {e}")
#         raise

# # ==================== 流式 API ====================

# def call_streaming_api(
#     messages: List[Dict[str, str]],
#     api_type: str = "openai",
#     **kwargs
# ) -> Tuple[str, int]:
#     """
#     调用流式 API
    
#     Args:
#         messages: 对话消息列表
#         api_type: API 类型 ("openai", "custom")
#         **kwargs: 其他参数
    
#     Returns:
#         Tuple[str, int]: (完整响应内容, 使用的 token 数)
#     """
#     try:
#         if api_type == "openai":
#             return _stream_openai_api(messages, **kwargs)
#         elif api_type == "custom":
#             return _stream_custom_api(messages, **kwargs)
#         else:
#             raise ValueError(f"不支持的流式 API 类型: {api_type}")
            
#     except Exception as e:
#         logger.error(f"流式 API 调用失败: {e}")
#         raise

# def _stream_openai_api(
#     messages: List[Dict[str, str]],
#     model: str = "gpt-3.5-turbo",
#     api_base: str = "https://api.openai.com/v1",
#     api_key: str = None,
#     **kwargs
# ) -> Tuple[str, int]:
#     """OpenAI 流式 API"""
#     try:
#         client = openai.OpenAI(
#             base_url=api_base,
#             api_key=api_key or os.getenv("OPENAI_API_KEY")
#         )
        
#         stream = client.chat.completions.create(
#             model=model,
#             messages=messages,
#             stream=True,
#             **kwargs
#         )
        
#         content = ""
#         total_tokens = 0
        
#         for chunk in stream:
#             if chunk.choices[0].delta.content:
#                 content += chunk.choices[0].delta.content
#                 print(chunk.choices[0].delta.content, end="", flush=True)
        
#         print()  # 换行
        
#         # 获取 token 使用量（流式 API 可能不提供）
#         if hasattr(stream, 'usage') and stream.usage:
#             total_tokens = stream.usage.total_tokens
        
#         return content, total_tokens
        
#     except Exception as e:
#         logger.error(f"OpenAI 流式 API 调用失败: {e}")
#         raise

# def _stream_custom_api(
#     messages: List[Dict[str, str]],
#     api_url: str,
#     **kwargs
# ) -> Tuple[str, int]:
#     """自定义流式 API"""
#     try:
#         payload = {
#             "messages": messages,
#             "stream": True,
#             **kwargs
#         }
        
#         response = requests.post(
#             api_url,
#             json=payload,
#             stream=True,
#             headers={"Content-Type": "application/json"}
#         )
        
#         content = ""
#         total_tokens = 0
        
#         for line in response.iter_lines():
#             if line:
#                 line = line.decode('utf-8')
#                 if line.startswith('data: '):
#                     data = line[6:]  # 移除 'data: ' 前缀
#                     if data == '[DONE]':
#                         break
#                     try:
#                         chunk = json.loads(data)
#                         if 'choices' in chunk and len(chunk['choices']) > 0:
#                             delta = chunk['choices'][0].get('delta', {})
#                             if 'content' in delta:
#                                 content += delta['content']
#                                 print(delta['content'], end="", flush=True)
#                     except json.JSONDecodeError:
#                         continue
        
#         print()  # 换行
#         return content, total_tokens
        
#     except Exception as e:
#         logger.error(f"自定义流式 API 调用失败: {e}")
#         raise

# # ==================== 重试机制 ====================

# def call_llm_with_retry(
#     messages: List[Dict[str, str]],
#     api_type: str = "openai",
#     max_retries: int = 3,
#     retry_delay: float = 1.0,
#     **kwargs
# ) -> Tuple[str, int]:
#     """
#     带重试机制的 LLM API 调用
    
#     Args:
#         messages: 对话消息列表
#         api_type: API 类型
#         max_retries: 最大重试次数
#         retry_delay: 重试延迟（秒）
#         **kwargs: 其他参数
    
#     Returns:
#         Tuple[str, int]: (响应内容, 使用的 token 数)
#     """
#     for attempt in range(max_retries):
#         try:
#             if api_type == "openai":
#                 return call_openai_compatible_api(messages, **kwargs)
#             elif api_type == "openai_legacy":
#                 return call_openai_legacy_api(messages, **kwargs)
#             elif api_type == "custom":
#                 return call_custom_http_api(messages, **kwargs)
#             elif api_type == "streaming":
#                 return call_streaming_api(messages, **kwargs)
#             else:
#                 raise ValueError(f"不支持的 API 类型: {api_type}")
                
#         except Exception as e:
#             logger.warning(f"第 {attempt + 1} 次调用失败: {e}")
#             if attempt < max_retries - 1:
#                 time.sleep(retry_delay * (2 ** attempt))  # 指数退避
#             else:
#                 logger.error(f"所有重试都失败了")
#                 raise

# # ==================== 使用示例 ====================

# def example_usage():
#     """使用示例"""
#     messages = [
#         {"role": "user", "content": "请解释什么是人工智能"}
#     ]
    
#     # 示例1: OpenAI 兼容 API
#     try:
#         content, tokens = call_openai_compatible_api(
#             messages=messages,
#             model="gpt-3.5-turbo",
#             api_base="http://100.76.8.43:10086/v1",
#             api_key="your-api-key"
#         )
#         print(f"OpenAI API 响应: {content}")
#         print(f"使用 token 数: {tokens}")
#     except Exception as e:
#         print(f"OpenAI API 调用失败: {e}")
    
#     # # 示例2: 自定义 HTTP API
#     # try:
#     #     content, tokens = call_custom_http_api(
#     #         messages=messages,
#     #         api_url="http://your-api-endpoint/chat",
#     #         headers={"Authorization": "Bearer your-token"}
#     #     )
#     #     print(f"自定义 API 响应: {content}")
#     #     print(f"使用 token 数: {tokens}")
#     # except Exception as e:
#     #     print(f"自定义 API 调用失败: {e}")
    
#     # # 示例3: 带重试的调用
#     # try:
#     #     content, tokens = call_llm_with_retry(
#     #         messages=messages,
#     #         api_type="openai",
#     #         max_retries=3,
#     #         model="gpt-3.5-turbo",
#     #         api_base="http://100.76.8.43:10086/v1"
#     #     )
#     #     print(f"重试机制响应: {content}")
#     #     print(f"使用 token 数: {tokens}")
#     # except Exception as e:
#     #     print(f"重试机制调用失败: {e}")

# if __name__ == "__main__":
#     example_usage() 