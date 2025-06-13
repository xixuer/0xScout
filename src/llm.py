import json
import requests
import httpx # Added import
from openai import OpenAI  # 导入OpenAI库用于访问GPT模型
from logger import LOG  # 导入日志模块
import time

class LLM:
    def __init__(self, settings): # Renamed parameter from config to settings
        """
        初始化 LLM 类，根据配置选择使用的模型（OpenAI 或 Ollama）。

        :param settings: Settings 对象，包含所有的模型配置参数。
        """
        LOG.info("LLM.__init__ called.")
        self.settings = settings

        # Initialize attributes to ensure they exist
        self.model_type = "openai" # Default, will be overwritten
        self.openai_api_key = None
        self.openai_base_url = None
        self.openai_model_name = None
        self.ollama_model_name = None
        self.ollama_api_url = None
        self.client = None # OpenAI client

        try:
            raw_model_type_from_settings = self.settings.get_llm_model_type()
            LOG.debug(f"LLM.__init__: Raw model_type from settings: '{raw_model_type_from_settings}'")

            if raw_model_type_from_settings and isinstance(raw_model_type_from_settings, str):
                self.model_type = raw_model_type_from_settings.lower()
            else:
                LOG.warning(f"LLM.__init__: model_type from settings was None or not a string ('{raw_model_type_from_settings}'). Defaulting to 'openai'.")
                self.model_type = "openai" # Ensure a default string value

            LOG.info(f"LLM.__init__: Effective model_type set to: '{self.model_type}'")

        except Exception as e:
            LOG.error(f"LLM.__init__: Error while getting model_type from settings: {e}", exc_info=True)
            self.model_type = "openai" # Fallback to a default in case of unexpected error
            LOG.warning(f"LLM.__init__: Falling back to model_type='openai' due to an error during settings access.")

        LOG.debug(f"LLM.__init__: About to check effective model_type ('{self.model_type}') for client setup.")
        if self.model_type == "openai":
            LOG.info("LLM.__init__: model_type is 'openai'. Proceeding with OpenAI client setup.")
            self.openai_api_key = self.settings.get_openai_api_key()
            self.openai_base_url = self.settings.get_openai_base_url()
            self.openai_model_name = self.settings.get_openai_model_name()

            if not self.openai_api_key:
                LOG.error("OpenAI API Key 未在配置中提供 (环境变量 OPENAI_API_KEY 或配置文件 llm.openai_api_key)。")

            client_params = {"api_key": self.openai_api_key}
            # The OpenAI library typically handles the default base URL if 'base_url' is None.
            # Pass it only if it's explicitly set and non-default, or always pass if lib handles it.
            # Current OpenAI lib versions (>=1.0) accept base_url=None or a valid URL.
            if self.openai_base_url:
                client_params["base_url"] = self.openai_base_url

            # --- BEGINNING OF NEW/MODIFIED CODE for custom httpx.Client ---
            try:
                LOG.debug("尝试创建自定义 httpx.Client (trust_env=False, proxies=None)...")
                custom_http_client = httpx.Client(
                    trust_env=False,
                    timeout=httpx.Timeout(60.0, connect=20.0),  # 总超时60秒，连接超时20秒
                    limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
                    follow_redirects=True  # 跟随重定向
                )
                client_params["http_client"] = custom_http_client
                LOG.debug("自定义 httpx.Client 创建成功并已添加到 client_params。")
            except Exception as http_client_exc:
                LOG.error(f"创建自定义 httpx.Client 时发生错误: {http_client_exc}", exc_info=True)
                # Proceed without custom http_client, OpenAI init might still work or fail with more info
                pass
            # --- END OF NEW/MODIFIED CODE ---

            LOG.debug(f"准备初始化 OpenAI 客户端，参数 (可能包含自定义http_client): { {k: (type(v).__name__ if k == 'http_client' else v) for k, v in client_params.items()} }")
            # 脱敏显示API Key以供日志确认，但避免完整暴露
            key_to_log = self.openai_api_key
            if key_to_log and len(key_to_log) > 7: # e.g., sk-xxxx...xxxx
                key_display = f"{key_to_log[:5]}...{key_to_log[-4:]}"
            elif key_to_log:
                key_display = "**** (Key too short for partial display)"
            else:
                key_display = "Not Set"
            LOG.debug(f"OpenAI API Key (for client init): {key_display}")
            LOG.debug(f"OpenAI Base URL (for client init): {self.openai_base_url}")

            returned_client_object = None # Initialize variable
            try:
                LOG.debug(f"尝试调用 OpenAI(**client_params)...") # Log before call, concise
                returned_client_object = OpenAI(**client_params)
                self.client = returned_client_object # Assign only on success

                LOG.info(f"OpenAI() 调用成功返回。返回对象类型: {type(returned_client_object)}。")
                if self.client is not None:
                    LOG.info(f"self.client 已被设置为 OpenAI 客户端实例。类型: {type(self.client)}")
                else: # Should not happen if OpenAI() constructor behaves as expected (raises error or returns client)
                    LOG.warning("OpenAI() 调用返回了 None，但没有抛出异常。self.client 因此被设置为 None。")
            except Exception as e:
                exception_type = type(e).__name__
                exception_msg = str(e)
                LOG.error(
                    f"OpenAI 客户端初始化时捕获到异常。类型: {exception_type}, 消息: {exception_msg}. " +
                    "参数详情已记录到日志上下文。",
                    client_params_on_error={k: (type(v).__name__ if k == 'http_client' else v) for k, v in client_params.items()},
                    exc_info=True
                )
                # This error will prevent OpenAI calls.
                # Raising here would stop LLM init; an alternative is to let generate_report fail.
                self.client = None # Ensure client is None if init fails

        elif self.model_type == "ollama":
            self.ollama_model_name = self.settings.get_ollama_model_name()
            self.ollama_api_url = self.settings.get_ollama_api_url()
            # ... (any other ollama specific setup)
        else:
            # This log should ideally include the problematic value of self.model_type
            LOG.error(f"LLM.__init__: 不支持的模型类型在最终判断时为: '{self.model_type}'")
            # raise ValueError(f"不支持的模型类型: {self.model_type}") # Temporarily comment out raise for full log flow

    def generate_report(self, system_prompt, user_content):
        """
        生成报告，根据配置选择不同的模型来处理请求。

        :param system_prompt: 系统提示信息，包含上下文和规则。
        :param user_content: 用户提供的内容，通常是Markdown格式的文本。
        :return: 生成的报告内容。
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        # 根据选择的模型调用相应的生成报告方法
        if self.model_type == "openai":
            yield from self._generate_report_openai(messages)
        elif self.model_type == "ollama":
            yield from self._generate_report_ollama(messages)
        else:
            # This case should have been caught in __init__
            LOG.error(f"generate_report called with unsupported model type: {self.model_type}")
            yield f"错误: 不支持的模型类型 '{self.model_type}'。" # Yield error as a chunk

    def _generate_report_openai(self, messages):
        """
        使用 OpenAI GPT 模型生成报告 (流式)。

        :param messages: 包含系统提示和用户内容的消息列表。
        :yield: 生成的报告内容块。
        """
        if not self.client:
            LOG.error("OpenAI 客户端未初始化。请检查 API Key 和 Base URL 配置。")
            # Yield error as a chunk or raise, for now, yield as error string
            yield "错误: OpenAI 客户端未初始化。可能是由于 API Key 或 Base URL 配置不正确。"
            return # Stop generation

        LOG.info(f"使用 OpenAI {self.openai_model_name or '默认模型'} 模型流式生成报告 (Base URL: {self.openai_base_url or '默认'})。")
        
        # 增加重试逻辑
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # 添加超时设置
                stream = self.client.chat.completions.create(
                    model=self.openai_model_name, # Use the stored model name
                    messages=messages,
                    stream=True,
                    timeout=120  # 设置120秒超时
                )
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                # 成功完成，退出循环
                break
            except Exception as e:
                retry_count += 1
                LOG.error(f"生成 OpenAI 报告时发生错误 (尝试 {retry_count}/{max_retries})：{e}")
                if retry_count >= max_retries:
                    # 所有重试都失败
                    yield f"错误: 调用 OpenAI API 失败 - {e}"
                else:
                    # 稍等然后重试
                    wait_seconds = 2 ** retry_count  # 指数退避: 2, 4, 8...
                    LOG.info(f"等待 {wait_seconds} 秒后重试...")
                    time.sleep(wait_seconds)
                    # 对于流式API，可能需要告知用户正在重试
                    yield f"\n[系统: 请求遇到问题，正在重试 ({retry_count}/{max_retries})...]\n"

    def _generate_report_ollama(self, messages):
        """
        使用 Ollama LLaMA 模型生成报告 (流式)。

        :param messages: 包含系统提示和用户内容的消息列表。
        :yield: 生成的报告内容块。
        """
        LOG.info(f"使用 Ollama {self.ollama_model_name or '默认模型'} 模型流式生成报告 (API URL: {self.ollama_api_url or '未配置'})。")
        if not self.ollama_api_url or not self.ollama_model_name:
            LOG.error("Ollama API URL 或模型名称未配置。")
            yield "错误: Ollama API URL 或模型名称未配置。" # Yield error as a chunk
            return # Stop generation
        try:
            payload = {
                "model": self.ollama_model_name, # Use the stored model name
                "messages": messages,
                # max_tokens and temperature might not be standard for all Ollama models' stream APIs in this exact payload.
                # Ollama's /api/chat often takes them directly.
                # For streaming, these might be less relevant or handled differently.
                "stream": True # Enable streaming
            }

            response = requests.post(self.ollama_api_url, json=payload, stream=True) # Corrected self.api_url to self.ollama_api_url
            response.raise_for_status()  # Raise an exception for HTTP error codes

            for line in response.iter_lines():
                if line:
                    try:
                        json_line = json.loads(line.decode('utf-8'))
                        # Ollama streaming typically sends message content in 'message': {'content': '...'} for /api/chat
                        # or 'response': '...' for /api/generate. Assuming /api/chat structure from payload.
                        # The exact structure might vary based on Ollama version and endpoint.
                        # Common streaming structure: each JSON object has a 'response' field for /api/generate
                        # and 'message': {'content': ...} for /api/chat.
                        # Also, a 'done': false/true field.

                        # Adjusting based on typical Ollama /api/chat streaming format:
                        if 'message' in json_line and 'content' in json_line['message']:
                            content_piece = json_line['message']['content']
                            if content_piece: # Ensure there's actual content
                                yield content_piece
                        elif 'response' in json_line : # Fallback for /api/generate like format
                             content_piece = json_line.get('response')
                             if content_piece:
                                yield content_piece

                        # Stop if 'done' is true and it's part of the JSON line (common pattern)
                        if json_line.get('done'):
                            break
                    except json.JSONDecodeError:
                        LOG.warning(f"无法解码来自 Ollama 的 JSON 行: {line.decode('utf-8')}")
                        continue # Skip malformed lines
        except requests.exceptions.RequestException as e:
            LOG.error(f"调用 Ollama API 时发生请求错误：{e}")
            yield f"错误: 调用 Ollama API 失败 - {e}"
        except Exception as e:
            LOG.error(f"生成 Ollama 报告时发生错误：{e}")
            yield f"错误: 处理 Ollama 响应时发生未知错误 - {e}"
            raise

if __name__ == '__main__':
    from config import Settings  # Updated import from Config to Settings

    # Example of how to initialize Settings - assuming config.json is in the parent directory of src, or CWD
    # Adjust path as necessary if running llm.py directly for testing.
    # For this example, assume config.json is discoverable by Settings default.
    try:
        settings_obj = Settings() # Use updated class name
        llm = LLM(settings=settings_obj) # Pass settings object with the new parameter name

        markdown_content="""
# Progress for langchain-ai/langchain (2024-08-20 to 2024-08-21)

## Issues Closed in the Last 1 Days
- partners/chroma: release 0.1.3 #25599
- docs: few-shot conceptual guide #25596
- docs: update examples in api ref #25589
"""

    # 示例：生成 GitHub 报告
        system_prompt = "Your specific system prompt for GitHub report generation"
        github_report = llm.generate_report(system_prompt, markdown_content)
        LOG.debug(github_report)
    except FileNotFoundError as e:
        LOG.error(f"__main__ block in llm.py failed to load Settings: {e}. Ensure config.json is accessible.")
    except Exception as e:
        LOG.error(f"__main__ block in llm.py encountered an error: {e}")
