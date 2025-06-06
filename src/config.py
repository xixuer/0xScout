import json
import os
from logger import LOG # Added LOG import

class Settings: # Renamed from Config
    def __init__(self, config_file='config.json'): # Added config_file parameter
        self.config_file = config_file # Store config_file path
        self.load_config()
    
    def load_config(self):
        if not os.path.exists(self.config_file):
            # This basic error handling can be refined later if needed,
            # e.g., by logging or raising a more specific custom error.
            # For now, FileNotFoundError is clear.
            cwd = os.getcwd()
            print(f"Error: Configuration file '{self.config_file}' not found in CWD: {cwd}.")
            raise FileNotFoundError(f"Configuration file '{self.config_file}' not found. CWD: {cwd}")

        with open(self.config_file, 'r', encoding='utf-8') as f: # Use self.config_file, added encoding
            config = json.load(f)
            
            self.email = config.get('email', {})
            self.email['password'] = os.getenv('EMAIL_PASSWORD', self.email.get('password', ''))

            # 加载 GitHub 相关配置
            github_config = config.get('github', {})
            self.github_token = os.getenv('GITHUB_TOKEN', github_config.get('token'))
            self.subscriptions_file = github_config.get('subscriptions_file', 'subscriptions.json') # Added default
            self.freq_days = github_config.get('progress_frequency_days', 1)
            self.exec_time = github_config.get('progress_execution_time', "08:00")

            # 加载 LLM 相关配置
            llm_config = config.get('llm', {})
            self.llm_model_type = llm_config.get('model_type', 'openai')
            self.openai_model_name = llm_config.get('openai_model_name', 'gpt-4o-mini')
            # Load OpenAI API Key, prioritizing environment variable
            self.llm_openai_api_key = os.getenv('OPENAI_API_KEY', llm_config.get('openai_api_key'))
            # Load OpenAI Base URL, prioritizing environment variable
            openai_base_url_from_config = llm_config.get('openai_base_url')
            effective_config_url = openai_base_url_from_config if openai_base_url_from_config else 'https://api.openai.com/v1'
            self.llm_openai_base_url = os.getenv('OPENAI_BASE_URL', effective_config_url)
            if not self.llm_openai_base_url: # Ensure it's not empty string if env var was empty
                self.llm_openai_base_url = 'https://api.openai.com/v1'

            self.ollama_model_name = llm_config.get('ollama_model_name', 'llama3')
            self.ollama_api_url = llm_config.get('ollama_api_url', 'http://localhost:11434/api/chat')
            
            # 加载报告类型配置
            # Default report types updated to match Streamlit app's expectation if not in config
            self.report_types = config.get('report_types', ["github", "hacker_news_hours_topic", "hacker_news_daily_report"])
            
            # 加载 Slack 配置
            slack_config = config.get('slack', {})
            self.slack_webhook_url = slack_config.get('webhook_url')

    # --- Getter methods for various configurations ---

    def get_github_token(self) -> str | None:
        return self.github_token

    def get_subscriptions_file(self) -> str | None:
        # Ensure this returns a sensible default if not set, or handle in caller
        return self.subscriptions_file if hasattr(self, 'subscriptions_file') else "subscriptions.json"


    def get_github_progress_frequency_days(self) -> int:
        return self.freq_days if hasattr(self, 'freq_days') else 1

    def get_github_progress_execution_time(self) -> str:
        return self.exec_time if hasattr(self, 'exec_time') else "08:00"

    def get_email_config(self) -> dict:
        return self.email if hasattr(self, 'email') else {}

    def get_llm_model_type(self) -> str:
        return self.llm_model_type if hasattr(self, 'llm_model_type') else "openai"

    def get_openai_model_name(self) -> str:
        return self.openai_model_name if hasattr(self, 'openai_model_name') else "gpt-4o-mini"

    def get_ollama_model_name(self) -> str:
        return self.ollama_model_name if hasattr(self, 'ollama_model_name') else "llama3"

    def get_ollama_api_url(self) -> str:
        return self.ollama_api_url if hasattr(self, 'ollama_api_url') else "http://localhost:11434/api/chat"

    def get_openai_api_key(self) -> str | None:
        return getattr(self, 'llm_openai_api_key', None)

    def get_openai_base_url(self) -> str:
        return getattr(self, 'llm_openai_base_url', 'https://api.openai.com/v1')

    def get_report_types(self) -> list:
        return self.report_types if hasattr(self, 'report_types') else ["github", "hacker_news_hours_topic", "hacker_news_daily_report"]

    def get_slack_webhook_url(self) -> str | None:
        return self.slack_webhook_url if hasattr(self, 'slack_webhook_url') else None

    def get_prompt_file_path(self, prompt_key: str) -> str | None:
        """
        Constructs and returns the path to a prompt file.
        Assumes prompts are in a 'prompts' directory relative to project root.
        """
        # Correctly determine project_root assuming this file (config.py) is in 'src/'
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_file_dir)

        prompt_file = os.path.join(project_root, "prompts", f"{prompt_key}_prompt.txt")

        # Check if the specific prompt file exists
        if os.path.exists(prompt_file):
            return prompt_file

        # Fallback logic: if prompt_key includes a model (e.g., "github_gpt-4o-mini"),
        # try stripping the model part and looking for a generic prompt (e.g., "github_prompt.txt").
        parts = prompt_key.split('_')
        if len(parts) > 1: # Potential model suffix
            generic_key = parts[0] # e.g., "github" from "github_gpt-4o-mini"
            # Check if the first part itself is a known report type or a more generic key
            # This logic might need to be more sophisticated based on naming conventions.
            # For now, assume the first part is the generic type.

            # Try generic prompt (e.g., "github_prompt.txt")
            generic_prompt_file = os.path.join(project_root, "prompts", f"{generic_key}_prompt.txt")
            if os.path.exists(generic_prompt_file):
                # print(f"Specific prompt for '{prompt_key}' not found, using generic '{generic_key}'.") # For debugging
                return generic_prompt_file

        # If neither specific nor generic prompt file is found
        return None

    def get_github_subscriptions(self) -> list:
        """
        从指定的订阅文件中加载并返回 GitHub 订阅列表。
        如果文件不存在、为空或格式不正确，则返回空列表。
        """
        # Ensure LOG is available or import it if not already at file top
        # from logger import LOG # Assuming LOG is globally available or passed if not module level

        subscriptions_file_path = self.get_subscriptions_file() # Use getter to ensure default
        if not subscriptions_file_path: # Should always return a path due to default in getter
            LOG.warning("Settings.get_github_subscriptions: subscriptions_file 属性未配置。返回空列表。")
            return []

        # Path handling: Assume subscriptions_file is relative to config_file or CWD
        # If config_file has a path, make subscriptions_file relative to it
        # Otherwise, assume it's relative to CWD (which is project root for streamlit_app.py)
        if self.config_file and os.path.dirname(self.config_file):
            base_dir = os.path.dirname(self.config_file)
            actual_subscriptions_file_path = os.path.join(base_dir, subscriptions_file_path)
        else:
            actual_subscriptions_file_path = subscriptions_file_path

        if not os.path.exists(actual_subscriptions_file_path):
            LOG.warning(f"Settings.get_github_subscriptions: 订阅文件 '{actual_subscriptions_file_path}' 未找到。返回空列表。")
            # Consider creating a default empty file here if appropriate
            # For now, just returning empty list.
            # Example: save_json_file(actual_subscriptions_file_path, {"github_subscriptions": [], "hacker_news_subscriptions": []})
            return []

        try:
            with open(actual_subscriptions_file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content: # Empty file
                    LOG.warning(f"Settings.get_github_subscriptions: 订阅文件 '{actual_subscriptions_file_path}' 为空。返回空列表。")
                    return []

                data = json.loads(content)

                if not isinstance(data, dict):
                    LOG.warning(f"Settings.get_github_subscriptions: 订阅文件 '{actual_subscriptions_file_path}' 内容不是预期的字典格式。返回空列表。")
                    return []

                github_subs = data.get("github_subscriptions", [])
                if not isinstance(github_subs, list):
                    LOG.warning(f"Settings.get_github_subscriptions: 'github_subscriptions' 键在 '{actual_subscriptions_file_path}' 中不是列表。返回空列表。")
                    return []

                # Optional: Validate structure of items in github_subs if needed
                # e.g. ensure each item is a dict with 'owner' and 'repo'/'repo_name'
                valid_subs = []
                for sub in github_subs:
                    if isinstance(sub, dict):
                        if sub.get('repo_url'): # New format with repo_url
                            valid_subs.append(sub)
                        elif sub.get('owner') and (sub.get('repo') or sub.get('repo_name')): # Dict format with owner/repo
                            valid_subs.append(sub)
                        else: # Invalid or unrecognized dict format
                            LOG.warning(f"Skipping invalid or incomplete GitHub dictionary subscription item: {sub}")
                    elif isinstance(sub, str) and '/' in sub: # Basic check for "owner/repo" string
                        LOG.debug(f"Found legacy string subscription: {sub}. It will be processed by ReportGenerator.")
                        valid_subs.append(sub)
                    else: # Other invalid formats (e.g., non-dict, non-string, or malformed string)
                        LOG.warning(f"Skipping invalid GitHub subscription item (neither valid dict nor 'owner/repo' string): {sub}")
                return valid_subs

        except json.JSONDecodeError:
            LOG.error(f"Settings.get_github_subscriptions: 解析订阅文件 '{actual_subscriptions_file_path}' 失败。请检查其JSON格式。返回空列表。", exc_info=True)
            return []
        except Exception as e:
            LOG.error(f"Settings.get_github_subscriptions: 加载订阅文件 '{actual_subscriptions_file_path}' 时发生未知错误: {e}。返回空列表。", exc_info=True)
            return []
