import sys
import os

# Get the absolute path of the current file's directory (src)
_current_dir = os.path.dirname(os.path.abspath(__file__))
# Get the absolute path of the project root directory (parent of src)
_project_root = os.path.dirname(_current_dir)

# Add the project root to sys.path if it's not already there
# This allows imports like 'from src.module import ...'
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Standard Library Imports
import json
# import os # Already imported above for sys.path
import re # Added import for normalize_repo_input
import traceback
from datetime import datetime # Added

# Third-Party Imports
import streamlit as st

# Project-Specific Imports
try:
    from src.report_generator import ReportGenerator
    from src.config import Settings
    from src.llm import LLM
    from src.github_client import GitHubClient
    from src.hacker_news_client import HackerNewsClient # Added
except ImportError as e:
    st.error(f"核心模块导入失败: {e}。应用无法启动。\n请检查项目结构和依赖项。")
    st.stop()

# --- Helper for Streaming and Capturing ---
def stream_and_capture(report_generator_call, content_list):
    """
    Wraps a generator to capture its yielded string content into a list
    while still allowing st.write_stream to consume it.
    """
    for chunk in report_generator_call:
        if isinstance(chunk, str):
            content_list.append(chunk)
        yield chunk

# --- Constants ---
CONFIG_PATH = "config.json"
SUBSCRIPTIONS_PATH = "subscriptions.json"
APP_VERSION = "0.1.1"
ALL_AVAILABLE_REPORT_TYPES = ["github", "hacker_news_hours_topic", "hacker_news_daily_report"]


# --- App Configuration ---
st.set_page_config(
    page_title="0xScout Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Helper Functions ---

def show_message(message_type: str, text: str):
    """Displays a message using Streamlit's alert components with icons."""
    if message_type == "success":
        st.success(f"✅ {text}")
    elif message_type == "error":
        st.error(f"❌ {text}")
    elif message_type == "warning":
        st.warning(f"⚠️ {text}")
    elif message_type == "info":
        st.info(f"ℹ️ {text}")
    else:
        st.write(text)

def load_json_file(file_path: str) -> dict | None:
    """Loads a JSON file with error handling."""
    try:
        if not os.path.exists(file_path):
            if file_path == CONFIG_PATH:
                show_message("error", f"关键配置文件 {file_path} 未找到。应用无法运行。")
                st.stop()
            show_message("warning", f"文件 {file_path} 未找到。将使用默认/空数据结构。")
            return None
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        if file_path == CONFIG_PATH:
            show_message("error", f"关键配置文件 {file_path} 未找到。应用无法运行。")
            st.stop()
        show_message("error", f"文件 {file_path} 未找到。")
        return None
    except json.JSONDecodeError:
        show_message("error", f"解析文件 {file_path} 失败。请检查JSON格式。")
        return None
    except Exception as e:
        show_message("error", f"加载文件 {file_path} 时发生未知错误: {e}")
        if file_path == CONFIG_PATH:
            st.stop()
        return None


def save_json_file(file_path: str, data: dict) -> bool:
    """Saves data to a JSON file with error handling."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except IOError as e:
        show_message("error", f"无法写入到文件 {file_path}。详情: {e}")
        return False
    except Exception as e:
        show_message("error", f"保存文件 {file_path} 时发生未知错误: {e}")
        return False


def normalize_repo_input(repo_input: str) -> str | None:
    """
    Normalizes GitHub repository input (URL or 'owner/repo') to 'owner/repo' format.
    Returns None if input is invalid.
    """
    repo_input = repo_input.strip()
    match = re.match(r"^(?:https?:\/\/)?(?:www\.)?github\.com\/([a-zA-Z0-9_-]+)\/([a-zA-Z0-9_-]+)(?:\.git)?\/?$", repo_input)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    match_simple = re.match(r"^([a-zA-Z0-9_-]+)\/([a-zA-Z0-9_-]+)$", repo_input)
    if match_simple:
        return f"{match_simple.group(1)}/{match_simple.group(2)}"
    return None

def build_github_url(owner_repo_str: str) -> str:
    """Constructs a full GitHub URL from an 'owner/repo' string."""
    return f"https://github.com/{owner_repo_str}"


# --- Subscription Management ---

def get_subscriptions() -> dict:
    """Retrieves and prepares subscription data."""
    data = load_json_file(SUBSCRIPTIONS_PATH)
    if not isinstance(data, dict):
        if data is not None:
            show_message("info", f"文件 {SUBSCRIPTIONS_PATH} 内容不是预期的字典格式或为空，将使用默认订阅结构。")
        return {"github_subscriptions": [], "hacker_news_subscriptions": []}

    data.setdefault("github_subscriptions", [])
    data.setdefault("hacker_news_subscriptions", [])

    migrated_subs = []
    needs_save = False
    for sub in data.get("github_subscriptions", []):
        if isinstance(sub, str):
            migrated_subs.append({"repo_url": sub, "last_processed_timestamp": None, "custom_branch": None})
            needs_save = True
        elif isinstance(sub, dict) and "repo_url" in sub:
            sub.setdefault("last_processed_timestamp", None)
            sub.setdefault("custom_branch", None)
            migrated_subs.append(sub)

    if needs_save:
        data["github_subscriptions"] = migrated_subs
        if save_json_file(SUBSCRIPTIONS_PATH, data):
            show_message("info", "旧版订阅格式已自动更新为新版。")
        else:
            show_message("error", "自动迁移旧版订阅格式失败。更改未保存。")
    else:
        data["github_subscriptions"] = migrated_subs
    return data


def display_subscription_management():
    """UI for managing GitHub repository subscriptions."""
    st.header("🔧 GitHub 仓库订阅管理")
    if "repo_to_remove" not in st.session_state:
        st.session_state.repo_to_remove = None

    subscriptions_data = get_subscriptions()
    github_subs_list = subscriptions_data.get("github_subscriptions", [])

    st.subheader("➕ 添加新订阅")
    new_repo_input = st.text_input(
        "输入 GitHub 仓库 (例如 'owner/repo' 或完整 URL):",
        key="new_repo_text_input_sub_mgmt",
        help="输入仓库的 owner/repo 格式或完整的 GitHub URL。"
    )

    if st.button("添加订阅", key="add_sub_button", help="点击以添加此仓库到订阅列表。"):
        if new_repo_input:
            normalized_repo_url = normalize_repo_input(new_repo_input)
            if not normalized_repo_url:
                 show_message("error", "输入格式不正确。请使用 'owner/repo' 或完整的 GitHub URL。")
            elif any(sub.get("repo_url") == normalized_repo_url for sub in github_subs_list):
                show_message("warning", f"仓库 {normalized_repo_url} 已经订阅过了。")
            else:
                new_sub_entry = {"repo_url": normalized_repo_url, "last_processed_timestamp": None, "custom_branch": None}
                github_subs_list.append(new_sub_entry)
                if save_json_file(SUBSCRIPTIONS_PATH, subscriptions_data):
                    show_message("success", f"成功添加订阅: {normalized_repo_url}")
                    st.rerun()
                else:
                    github_subs_list.pop()
        else:
            show_message("warning", "请输入仓库信息。")

    st.markdown("---")
    st.subheader("📜 当前已订阅的仓库")
    if not github_subs_list:
        show_message("info", "目前没有订阅任何 GitHub 仓库。")
    else:
        for idx, repo_entry in enumerate(github_subs_list):
            repo_url_normalized = repo_entry.get("repo_url")
            if not repo_url_normalized: continue
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"- [{repo_url_normalized}]({build_github_url(repo_url_normalized)})")
            with col2:
                button_key = f"remove_sub_{repo_url_normalized.replace('/', '_')}_{idx}"
                if st.button("➖ 移除", key=button_key, help=f"移除 {repo_url_normalized} 订阅"):
                    st.session_state.repo_to_remove = repo_url_normalized

        if st.session_state.repo_to_remove:
            repo_to_remove_url = st.session_state.repo_to_remove
            current_subs = get_subscriptions()
            updated_github_subs = [sub for sub in current_subs.get("github_subscriptions", []) if sub.get("repo_url") != repo_to_remove_url]
            if len(updated_github_subs) < len(current_subs.get("github_subscriptions", [])):
                current_subs["github_subscriptions"] = updated_github_subs
                if save_json_file(SUBSCRIPTIONS_PATH, current_subs):
                    show_message("success", f"成功移除仓库: {repo_to_remove_url}")
                else:
                    show_message("error", f"移除仓库 {repo_to_remove_url} 失败。更改未保存。")
            st.session_state.repo_to_remove = None
            st.rerun()

# --- App Settings UI ---
def display_app_settings_ui():
    """UI for managing application settings."""
    st.header("⚙️ 应用设置")

    config_data = load_json_file(CONFIG_PATH)
    if not config_data: # Should be stopped by load_json_file if critical, but good practice
        show_message("error", "无法加载配置文件。设置页面不可用。")
        return

    # LLM Settings
    st.subheader("LLM 配置")
    llm_config = config_data.get("llm", {})
    model_type_options = ["openai", "ollama"]
    current_model_type = llm_config.get("model_type", model_type_options[0])
    model_type_index = model_type_options.index(current_model_type) if current_model_type in model_type_options else 0

    model_type_selection = st.selectbox(
        "LLM 模型类型:",
        options=model_type_options,
        index=model_type_index,
        key="llm_model_type_select" # This key is used by session_state to get the current selection
    )

    # Conditional display based on model_type_selection (st.session_state.llm_model_type_select)
    # Ensure session_state has the value from the selectbox if it has been interacted with.
    # The selectbox itself returns the current value, which can be used directly for conditional logic below.

    if model_type_selection == "openai":
        st.text_input(
            "OpenAI 模型名称:",
            value=llm_config.get("openai_model_name", "gpt-4o-mini"),
            key="settings_llm_openai_model_name", # Standardized key
            help="例如: gpt-4, gpt-3.5-turbo, gpt-4o-mini"
        )
        st.text_input(
            "OpenAI API Base URL (可选):",
            value=llm_config.get('openai_base_url', 'https://api.openai.com/v1'),
            key="settings_llm_openai_base_url",
            help="例如：https://api.openai.com/v1 或其他兼容OpenAI API的接口地址。如果留空，则使用官方默认地址。"
        )
    elif model_type_selection == "ollama":
        st.text_input(
            "Ollama 模型名称:",
            value=llm_config.get("ollama_model_name", "llama3"),
            key="settings_llm_ollama_model_name", # Standardized key
            help="例如: llama3, codellama, mistral"
        )
        st.text_input(
            "Ollama API URL:",
            value=llm_config.get("ollama_api_url", "http://localhost:11434/api/chat"),
            key="settings_llm_ollama_api_url", # Standardized key
        )
    st.markdown("---")

    # Email Settings
    st.subheader("✉️ 邮箱配置")
    email_config = config_data.get("email", {})
    email_provider_options = ["自定义", "腾讯企业邮", "QQ邮箱", "163邮箱", "Gmail"]
    # Note: 'email_provider' is a new custom key, not from original config structure.
    # We'll need to handle its saving and potential logic for pre-filling SMTP details later.
    current_email_provider = email_config.get("provider", email_provider_options[0])
    try:
        email_provider_index = email_provider_options.index(current_email_provider)
    except ValueError:
        email_provider_index = 0 # Default to "自定义"

    st.selectbox(
        "选择邮箱服务商:",
        options=email_provider_options,
        index=email_provider_index,
        key="settings_email_provider",
        help="选择常用的邮箱服务商预设，或选择“自定义”手动填写SMTP信息。"
    )
    st.text_input(
        "SMTP 服务器地址:",
        value=email_config.get("smtp_server", ""),
        key="settings_email_smtp_server"
    )
    st.number_input(
        "SMTP 端口:",
        min_value=1,
        max_value=65535,
        value=email_config.get("smtp_port", 465), # Default to 465 for SSL
        step=1,
        key="settings_email_smtp_port"
    )
    st.text_input(
        "发件人邮箱地址:",
        value=email_config.get("from", ""),
        key="settings_email_from_address"
    )
    st.text_input(
        "发件人邮箱密码/授权码:",
        type="password",
        value=email_config.get("password", ""),
        key="settings_email_password"
    )
    # Current config stores 'to' as a list. For UI, join to string, and split back when saving.
    to_addresses_list = email_config.get("to", [])
    to_addresses_str = ", ".join(to_addresses_list) if isinstance(to_addresses_list, list) else ""
    st.text_input(
        "收件人邮箱地址 (多个请用英文逗号分隔):",
        value=to_addresses_str,
        key="settings_email_to_addresses"
    )
    st.markdown("---")

    # GitHub Report Settings
    st.subheader("GitHub 报告配置")
    github_config = config_data.get("github", {})
    progress_frequency_days = st.number_input(
        "报告频率 (天):",
        min_value=1,
        max_value=30,
        value=github_config.get("progress_frequency_days", 1),
        key="progress_freq_days_input",
        help="生成 GitHub 进度报告的时间周期（天数）。"
    )
    progress_execution_time = st.text_input(
        "报告生成时间 (HH:MM):",
        value=github_config.get("progress_execution_time", "08:00"),
        key="progress_exec_time_input",
        help="每日生成后台报告的时间点 (24小时制，例如 08:00 或 23:30)。"
    )
    st.markdown("---")

    # Enabled Report Types
    st.subheader("启用的报告类型")
    current_report_types = config_data.get("report_types", ALL_AVAILABLE_REPORT_TYPES[:1]) # Default to first if not set

    selected_report_types = st.multiselect(
        "选择要启用的报告类型:",
        options=ALL_AVAILABLE_REPORT_TYPES,
        default=current_report_types,
        key="enabled_report_types_multiselect",
        help="选择应用将生成和处理的报告种类。"
    )
    st.markdown("---")

    # API Token Configuration (specifically GitHub token for now)
    st.subheader("🔑 API Token 配置")
    # github_config is already fetched above for GitHub Report Settings
    github_token_value = github_config.get("token", "")

    # Session state for checkbox
    if "settings_show_github_token" not in st.session_state: # This is the state variable
        st.session_state.settings_show_github_token = False

    # Checkbox widget updates st.session_state.settings_show_github_token directly due to its key
    st.checkbox(
        "显示/隐藏 GitHub Token",
        key="settings_show_github_token" # Key directly maps to session state variable
    )

    # Add risk warning if user chooses to show token
    if st.session_state.settings_show_github_token: # Use the session state variable
        st.warning("注意：显示Token会将其明文展示在屏幕上，请确保环境安全，并在使用完毕后及时隐藏。")

    if st.session_state.settings_show_github_token: # Use the session state variable
        st.text_input(
            "GitHub Token:",
            value=github_token_value,
            key="settings_github_token",
            type="default", # Show as plain text
            help="您的GitHub个人访问令牌 (Personal Access Token)。"
            )
    else:
        st.text_input(
            "GitHub Token:",
            value=github_token_value,
            key="settings_github_token",
            type="password", # Hide with bullets
            help="您的GitHub个人访问令牌 (Personal Access Token)。"
            )
    # token_display_area = st.empty() # This was an alternative display idea, not used.

    # OpenAI API Key
    # Initialize session state for the OpenAI API Key checkbox state variable
    if "settings_show_openai_api_key" not in st.session_state:
        st.session_state.settings_show_openai_api_key = False

    # Checkbox widget updates st.session_state.settings_show_openai_api_key directly
    st.checkbox(
        "显示/隐藏 OpenAI API Key",
        key="settings_show_openai_api_key" # Key directly maps to session state variable
    )

    if st.session_state.settings_show_openai_api_key: # Use the session state variable
        st.warning("注意：显示OpenAI API Key会将其明文展示在屏幕上，请确保环境安全，并在使用完毕后及时隐藏。")
        openai_api_key_type = "default"
    else:
        openai_api_key_type = "password"

    st.text_input(
        "OpenAI API Key:",
        value=llm_config.get("openai_api_key", ""),
        key="settings_openai_api_key",
        type=openai_api_key_type, # Dynamically set type
        help="输入您的OpenAI API密钥。"
    )
    st.markdown("---")


    if st.button("保存设置", key="save_app_settings_button"):
        current_config = load_json_file(CONFIG_PATH)
        if current_config is None:
            show_message("error", "无法加载现有配置。保存操作已中止。")
            return

        # Update LLM settings
        # This block was duplicated by mistake in previous step, consolidating here.
        # The dynamic save logic for LLM settings and OpenAI API key is handled below.
        # llm_settings = current_config.setdefault('llm', {})
        # llm_settings['model_type'] = st.session_state.llm_model_type_select
        # llm_settings['openai_model_name'] = st.session_state.openai_model_name_input
        # llm_settings['ollama_model_name'] = st.session_state.ollama_model_name_input
        # llm_settings['ollama_api_url'] = st.session_state.ollama_api_url_input

        # Update GitHub report settings
        github_settings = current_config.setdefault('github', {})
        github_settings['progress_frequency_days'] = st.session_state.progress_freq_days_input
        github_settings['progress_execution_time'] = st.session_state.progress_exec_time_input

        # Update enabled report types
        current_config['report_types'] = st.session_state.enabled_report_types_multiselect

        # --- Update LLM Settings (Dynamic & Standardized Keys) ---
        llm_settings = current_config.setdefault('llm', {})
        selected_llm_type = st.session_state.llm_model_type_select # This key is correct for the selectbox
        llm_settings['model_type'] = selected_llm_type

        if selected_llm_type == "openai":
            # Use standardized keys for session_state access
            llm_settings['openai_model_name'] = st.session_state.settings_llm_openai_model_name
            llm_settings['openai_base_url'] = st.session_state.settings_llm_openai_base_url
            llm_settings.pop('ollama_model_name', None)
            llm_settings.pop('ollama_api_url', None)
        elif selected_llm_type == "ollama":
            # Use standardized keys for session_state access
            llm_settings['ollama_model_name'] = st.session_state.settings_llm_ollama_model_name
            llm_settings['ollama_api_url'] = st.session_state.settings_llm_ollama_api_url
            llm_settings.pop('openai_model_name', None)
            llm_settings.pop('openai_base_url', None) # Also remove base_url if switching to ollama

        # OpenAI API Key (part of LLM settings but handled separately due to sensitivity)
        # Key for text input is 'settings_openai_api_key'
        if st.session_state.settings_openai_api_key:
            llm_settings['openai_api_key'] = st.session_state.settings_openai_api_key
        elif 'openai_api_key' not in llm_settings:
            llm_settings['openai_api_key'] = ""
        # Else: preserve original value if field untouched.

        # --- Update Email Settings ---
        email_settings = current_config.setdefault('email', {})
        email_settings['provider'] = st.session_state.settings_email_provider
        email_settings['smtp_server'] = st.session_state.settings_email_smtp_server
        email_settings['smtp_port'] = st.session_state.settings_email_smtp_port
        email_settings['from'] = st.session_state.settings_email_from_address

        # Process 'to' addresses string back to list
        to_addresses_str = st.session_state.settings_email_to_addresses
        email_settings['to'] = [addr.strip() for addr in to_addresses_str.split(',') if addr.strip()]

        # Handle email password: only update if a new password is provided
        if st.session_state.settings_email_password:
            email_settings['password'] = st.session_state.settings_email_password
        elif 'password' not in email_settings: # If no password was set before and user didn't input
            email_settings['password'] = ""
        # Else: if password exists and user didn't change it, keep the existing one (already in email_settings)

        # --- Update GitHub Token ---
        # github_settings was already obtained or created for progress_frequency_days etc.
        # Ensure 'token' is handled carefully
        if st.session_state.settings_github_token: # If user entered something in the token field
            github_settings['token'] = st.session_state.settings_github_token
        elif 'token' not in github_settings: # If no token was set before and user didn't input
            github_settings['token'] = ""
        # Else: if token exists and user didn't change it (e.g. field was displayed as password but not re-typed), keep existing.
        # Note: Since st.text_input with type="password" still holds its original value in session_state if not changed,
        # this logic correctly preserves the token if the user doesn't type a new one.
        # If the field was visible and then cleared, it would save an empty string.
        # If it was password, not changed, original value from config (github_token_value) is in st.session_state.settings_github_token.

        # Save the updated configuration
        if save_json_file(CONFIG_PATH, current_config):
            show_message("success", "设置已成功保存！页面将刷新以应用部分更改。")
            # Some changes might require a full app restart if they affect initial setup.
            # For now, a simple rerun might reload config for some parts.
            st.rerun()
        else:
            # save_json_file already shows an error message
            pass


# --- Report Generation UI ---
def display_report_generation_ui():
    """UI for generating various types of reports."""
    st.header("📊 生成报告")
    # st.session_state.generated_report_content is no longer used for primary display with st.write_stream
    # If "Clear report display" button is removed, this might not be needed at all.
    # For now, keep it to avoid breaking other logic if it exists, but it won't be set by new streaming.

    config_data = load_json_file(CONFIG_PATH)
    if not config_data: return

    # Pre-fill session state for temporary LLM settings
    llm_global_config = config_data.get("llm", {})
    st.session_state.current_openai_model_name_from_config = llm_global_config.get("openai_model_name", "gpt-4o-mini")
    st.session_state.current_openai_base_url_from_config = llm_global_config.get("openai_base_url", "https://api.openai.com/v1")
    st.session_state.current_ollama_model_name_from_config = llm_global_config.get("ollama_model_name", "llama3")
    st.session_state.current_ollama_api_url_from_config = llm_global_config.get("ollama_api_url", "http://localhost:11434/api/chat")
    # Note: OpenAI API Key is not pre-filled in temporary settings for security/simplicity.

    available_report_types = config_data.get("report_types", [])
    if not available_report_types:
        show_message("warning", "配置文件中未定义任何报告类型 (`report_types`)。")
        return

    report_type = st.selectbox(
        "选择报告类型:", available_report_types, key="report_type_select",
        help="选择您希望生成的报告种类。"
    )

    with st.expander("⚙️ 临时 LLM 设置 (高级)", expanded=False):
        temp_llm_provider_options = ["使用应用设置中的模型", "openai", "ollama"]
        # Initialize session state for the selectbox itself if not present
        if "temp_llm_provider" not in st.session_state:
            st.session_state.temp_llm_provider = temp_llm_provider_options[0]

        st.selectbox(
            "LLM 提供商 (本次报告):",
            options=temp_llm_provider_options,
            index=temp_llm_provider_options.index(st.session_state.temp_llm_provider), # Use current session state value
            key="temp_llm_provider", # This key directly updates st.session_state.temp_llm_provider
            help="选择本次报告使用的LLM提供商。此设置不会保存到全局配置。"
        )

        if st.session_state.temp_llm_provider == "openai":
            # Initialize session state for inputs if not present, using pre-filled values
            if "temp_openai_model_name_input" not in st.session_state:
                st.session_state.temp_openai_model_name_input = st.session_state.current_openai_model_name_from_config
            if "temp_openai_base_url_input" not in st.session_state:
                st.session_state.temp_openai_base_url_input = st.session_state.current_openai_base_url_from_config

            st.text_input(
                "OpenAI 模型名称 (本次报告):",
                value=st.session_state.temp_openai_model_name_input, # Use session state value
                key="temp_openai_model_name_input", # Key updates session state
                help="例如: gpt-4o-mini, gpt-4o, gpt-3.5-turbo. 此设置仅用于本次报告。"
            )
            st.text_input(
                "OpenAI API Base URL (可选, 本次报告):",
                value=st.session_state.temp_openai_base_url_input, # Use session state value
                key="temp_openai_base_url_input", # Key updates session state
                help="留空则使用官方默认地址。此设置仅用于本次报告。"
            )
        elif st.session_state.temp_llm_provider == "ollama":
            # Initialize session state for inputs if not present, using pre-filled values
            if "temp_ollama_model_name_input" not in st.session_state:
                st.session_state.temp_ollama_model_name_input = st.session_state.current_ollama_model_name_from_config
            if "temp_ollama_api_url_input" not in st.session_state:
                st.session_state.temp_ollama_api_url_input = st.session_state.current_ollama_api_url_from_config

            st.text_input(
                "Ollama 模型名称 (本次报告):",
                value=st.session_state.temp_ollama_model_name_input, # Use session state value
                key="temp_ollama_model_name_input", # Key updates session state
                help="例如: llama3, gemma2:2b. 此设置仅用于本次报告。"
            )
            st.text_input(
                "Ollama API URL (本次报告):",
                value=st.session_state.temp_ollama_api_url_input, # Use session state value
                key="temp_ollama_api_url_input", # Key updates session state
                help="此设置仅用于本次报告。"
            )

    generate_report_button = False
    target_repo_input = None
    github_report_scope = "all"

    if report_type == "github":
        github_report_scope_options = ["所有已订阅仓库", "指定单个仓库"]
        github_report_scope_selection = st.radio(
            "选择GitHub报告范围:", github_report_scope_options, key="gh_scope_radio",
            help="选择是为所有已订阅的仓库生成报告，还是为单个特定仓库生成。"
        )
        if github_report_scope_selection == "指定单个仓库":
            github_report_scope = "single"
            target_repo_input = None # Initialize target_repo_input

            input_method = st.radio(
                "选择仓库指定方式:",
                options=["从已订阅列表选择", "手动输入仓库名"],
                key="gh_single_repo_input_method_radio",
                horizontal=True
            )

            if input_method == "从已订阅列表选择":
                current_subscriptions = get_subscriptions()
                subscribed_repo_urls = [
                    sub.get("repo_url") for sub in current_subscriptions.get("github_subscriptions", [])
                    if isinstance(sub, dict) and sub.get("repo_url")
                ]
                # Add empty option for no selection or placeholder
                repo_options = [""] + sorted(list(set(subscribed_repo_urls)))
                target_repo_select = st.selectbox(
                    "从已订阅仓库中选择:",
                    repo_options,
                    index=0, # Default to no selection or first item
                    key="gh_single_repo_select_conditional",
                    help="从已订阅仓库列表中选择。"
                )
                if target_repo_select: # Check if a valid repo is selected (not empty string)
                    target_repo_input = target_repo_select
                # If target_repo_select is "" (empty string), target_repo_input remains None or its previous state.
                # Explicitly setting to None if empty helps clarify state.
                else:
                    target_repo_input = None

            elif input_method == "手动输入仓库名":
                target_repo_manual_input = st.text_input(
                    "手动输入 owner/repo 或 GitHub URL:", # Updated help text to be more inclusive
                    key="gh_single_repo_manual_conditional",
                    help="输入仓库的 owner/repo 格式或完整的 GitHub URL。"
                )
                if target_repo_manual_input:
                    normalized_manual_input = normalize_repo_input(target_repo_manual_input)
                    if normalized_manual_input:
                        target_repo_input = normalized_manual_input
                    else:
                        # Display error directly under the input field for better UX
                        st.error("手动输入的仓库格式不正确。请使用 'owner/repo' 或 GitHub URL。")
                        target_repo_input = None # Ensure it's None if normalization fails
                else:
                    target_repo_input = None # Ensure it's None if input is empty

            # Button display logic based on target_repo_input being successfully set
            if target_repo_input:
                generate_report_button = st.button(f"为 {target_repo_input} 生成GitHub报告", key="generate_single_gh_report_btn")
            else:
                # Provide clearer guidance based on the selected input method or if no input yet.
                if input_method == "从已订阅列表选择":
                    show_message("info", "请从列表中选择一个已订阅的仓库。")
                elif input_method == "手动输入仓库名":
                    show_message("info", "请输入有效的仓库名称或URL。")
                # else case for initial state before any interaction might not be strictly needed if radio defaults.
        else: # This is for "所有已订阅仓库"
            github_report_scope = "all"
            generate_report_button = st.button("为所有已订阅仓库生成GitHub报告", key="generate_all_gh_report_btn")
    elif report_type == "hacker_news_hours_topic":
        generate_report_button = st.button("生成Hacker News小时热门话题报告", key="generate_hn_hours_topic_btn")
    elif report_type == "hacker_news_daily_report":
        generate_report_button = st.button("生成Hacker News每日摘要报告", key="generate_hn_daily_report_btn")
    else:
        show_message("warning", f"暂不支持 '{report_type}' 类型的报告生成UI。")

    if generate_report_button:
        full_report_content = [] # Initialize accumulator for the report
        report_type_prefix = report_type # Default prefix

        try:
            report_settings_override = {}
            if st.session_state.temp_llm_provider == "openai":
                report_settings_override['llm'] = {
                    "model_type": "openai",
                    "openai_model_name": st.session_state.temp_openai_model_name_input,
                    "openai_base_url": st.session_state.temp_openai_base_url_input if st.session_state.temp_openai_base_url_input else st.session_state.current_openai_base_url_from_config, # Default to global config's value if temp is empty
                    "openai_api_key": config_data.get("llm", {}).get("openai_api_key", "") # Load from global
                }
            elif st.session_state.temp_llm_provider == "ollama":
                report_settings_override['llm'] = {
                    "model_type": "ollama",
                    "ollama_model_name": st.session_state.temp_ollama_model_name_input,
                    "ollama_api_url": st.session_state.temp_ollama_api_url_input
                }
            # Else: "使用应用设置中的模型", report_settings_override remains empty, Settings loads from file.

            settings = Settings(config_file=CONFIG_PATH, overrides=report_settings_override if report_settings_override else None)
            llm_instance = LLM(settings=settings)
            github_token = config_data.get("github", {}).get("token")
            if not github_token and report_type == "github":
                show_message("error", "GitHub token 未在配置中找到，无法生成GitHub相关报告。")
                st.session_state.generated_report_content = "错误: GitHub token 未配置。"
                return
            github_client_instance = GitHubClient(token=github_token if github_token else "dummy_token_if_not_github_report")
            report_generator = ReportGenerator(llm=llm_instance, settings=settings, github_client=github_client_instance)
        except Exception as e:
            show_message("error", f"初始化报告所需组件失败: {e}")
            st.code(traceback.format_exc())
            # st.session_state.generated_report_content = f"初始化报告生成器失败: {e}" # Old way
            st.error(f"初始化报告生成器失败: {e}") # Direct error display
            return

        # Logic for st.write_stream
        if report_type == "github" and github_report_scope == "all":
            report_type_prefix = "github_subscriptions_report"
            with st.spinner("⏳ 正在为所有已订阅仓库生成GitHub报告..."):
                main_report_iter = iter(report_generator.generate_github_subscription_report())
                overall_title = next(main_report_iter, None)

                if overall_title and isinstance(overall_title, str):
                    if overall_title.startswith("没有配置 GitHub 仓库订阅") or \
                       overall_title.startswith("所有订阅条目均未能成功解析为有效的仓库"):
                        st.info(overall_title)
                        full_report_content.append(overall_title + "\n")
                    else:
                        st.markdown(overall_title)
                        full_report_content.append(overall_title + "\n")
                        for single_project_generator in main_report_iter:
                            project_specific_iter = iter(single_project_generator)
                            left_col, right_col = st.columns(2)
                            factual_data_chunk, separator_chunk = None, None
                            try:
                                factual_data_chunk = next(project_specific_iter, None)
                                if factual_data_chunk:
                                    with left_col:
                                        st.markdown("---")
                                        st.markdown(factual_data_chunk)
                                    full_report_content.append("\n---\n" + factual_data_chunk + "\n")
                                else:
                                    with left_col: st.warning("未能获取项目的原始数据部分。")

                                separator_chunk = next(project_specific_iter, None)
                                if separator_chunk:
                                    with right_col:
                                        st.markdown("---")
                                        st.markdown(separator_chunk)
                                    full_report_content.append("\n---\n" + separator_chunk + "\n")
                                    if "LLM 智能摘要" in separator_chunk or "AI Summary" in separator_chunk:
                                        st.write_stream(stream_and_capture(project_specific_iter, full_report_content))
                                else:
                                    with right_col: st.info("LLM摘要部分未生成或无内容。")
                                    full_report_content.append("LLM摘要部分未生成或无内容。\n")
                            except StopIteration:
                                if factual_data_chunk and not separator_chunk: # LLM part fully skipped
                                    with right_col: st.info("LLM摘要部分未生成或无内容。")
                                    full_report_content.append("LLM摘要部分未生成或无内容。\n")
                                elif not factual_data_chunk:
                                     st.warning("一个项目报告生成器未产生预期的数据。")
                            except Exception as e_proj_stream:
                                st.error(f"处理单个项目报告流时出错: {e_proj_stream}")
                            st.divider()
                            full_report_content.append("\n---\n") # Visual separator in Markdown
                elif overall_title is None:
                     st.warning("报告生成器未能初始化或未产生任何内容。")
            show_message("success", "GitHub 订阅报告流程处理完毕。")

        elif report_type == "github" and github_report_scope == "single" and target_repo_input:
            report_type_prefix = f"github_report_{target_repo_input.replace('/', '_')}"
            try:
                owner, repo_name = target_repo_input.split('/')
                with st.spinner(f"⏳ 正在为 {target_repo_input} 生成GitHub报告..."):
                    left_column, right_column = st.columns(2)
                    report_stream_gen = report_generator.generate_github_project_report(owner=owner, repo_name=repo_name)
                    factual_data_chunk, separator_chunk = None, None
                    try:
                        factual_data_chunk = next(report_stream_gen)
                        with left_column:
                            st.markdown("---")
                            st.markdown("### 📝 原始数据 (Factual Data)")
                            st.markdown(factual_data_chunk)
                        full_report_content.append("---\n### 📝 原始数据 (Factual Data)\n" + factual_data_chunk + "\n")

                        separator_chunk = next(report_stream_gen)
                        with right_column:
                            st.markdown(separator_chunk)
                        full_report_content.append(separator_chunk + "\n")
                        st.write_stream(stream_and_capture(report_stream_gen, full_report_content))
                    except StopIteration:
                        with left_column:
                            if factual_data_chunk is not None and separator_chunk is None:
                                with right_column: st.info("LLM摘要未生成（可能由于配置或无适用内容）。")
                                full_report_content.append("LLM摘要未生成（可能由于配置或无适用内容）。\n")
                            elif factual_data_chunk is None:
                                st.warning("报告生成器未产生任何内容。")
                    except Exception as e_stream_consume:
                        st.error(f"处理报告流时发生错误: {e_stream_consume}")
                show_message("success", f"GitHub 项目 {target_repo_input} 报告流程处理完毕。")
            except ValueError:
                st.error(f"仓库格式不正确: {target_repo_input}。请使用 'owner/repo' 格式。")
            except Exception as e_gh_single:
                st.error(f"为 {target_repo_input} 生成GitHub报告时出错: {e_gh_single}")

        elif report_type == "hacker_news_hours_topic":
            report_type_prefix = "hn_hourly_report"
            with st.spinner("⏳ 正在生成Hacker News小时热门话题报告..."):
                try:
                    hn_client = HackerNewsClient() # Should this be initialized earlier?
                    markdown_file_path = hn_client.export_top_stories() # This seems to be a file path, not the report content itself.
                    if markdown_file_path is None:
                        st.error("错误: 未能获取Hacker News数据文件路径。")
                        full_report_content.append("错误: 未能获取Hacker News数据文件路径。\n")
                    else:
                        fn = os.path.basename(markdown_file_path)
                        hour_str = os.path.splitext(fn)[0]
                        date_str = os.path.basename(os.path.dirname(markdown_file_path))
                        if not (hour_str.isdigit() and len(date_str.split('-')) == 3):
                            st.error(f"错误: 无法从路径 {markdown_file_path} 解析日期/小时。")
                            full_report_content.append(f"错误: 无法从路径 {markdown_file_path} 解析日期/小时。\n")
                        else:
                            report_type_prefix = f"hn_hourly_{date_str}_{hour_str}"
                            st.write_stream(stream_and_capture(report_generator.get_hacker_news_hourly_report(date_str, hour_str), full_report_content))
                            show_message("success", "Hacker News 小时热门话题报告流程处理完毕。")
                except Exception as e_hn_hourly:
                    st.error(f"生成Hacker News小时报告时出错: {e_hn_hourly}")
                    full_report_content.append(f"生成Hacker News小时报告时出错: {e_hn_hourly}\n")

        elif report_type == "hacker_news_daily_report":
            report_type_prefix = "hn_daily_summary"
            with st.spinner("⏳ 正在生成Hacker News每日摘要报告..."):
                try:
                    current_date_str = datetime.now().strftime('%Y-%m-%d')
                    report_type_prefix = f"hn_daily_summary_{current_date_str}"
                    st.write_stream(stream_and_capture(report_generator.get_hacker_news_daily_summary(current_date_str), full_report_content))
                    show_message("success", "Hacker News 每日摘要报告流程处理完毕。")
                except Exception as e_hn_daily:
                    st.error(f"生成Hacker News每日报告时出错: {e_hn_daily}")
                    full_report_content.append(f"生成Hacker News每日报告时出错: {e_hn_daily}\n")
        else:
            if report_type == "github" and github_report_scope == "single" and not target_repo_input:
                show_message("info", "请为 '指定单个仓库' 提供一个仓库（手动输入或从列表选择）。")

        # Add download button if content was generated
        final_markdown_report = "".join(full_report_content)
        if final_markdown_report.strip():
            st.download_button(
                label="📥 Download Report (Markdown)",
                data=final_markdown_report.encode('utf-8'),
                file_name=f"{report_type_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown"
            )

    # Remove or comment out the old display logic
    # st.markdown("---")
    # if st.session_state.generated_report_content:
    #     st.subheader("📄 生成的报告:")
    #     st.markdown(st.session_state.generated_report_content, unsafe_allow_html=True)
    #     if st.button("清除报告显示", key="clear_report_display_btn", help="点击以清除当前显示的报告内容。"):
    #         st.session_state.generated_report_content = None
    #         st.rerun()


# --- Config Overview UI ---
def _display_config_detail_item(label: str, value, is_sensitive: bool = False):
    """Internal helper to display a single config item."""
    display_value = "••••••••" if is_sensitive and value else str(value)
    st.markdown(f"**{label}:** `{display_value}`")

def display_config_overview():
    """UI for displaying application configuration overview."""
    st.header("⚙️ 应用配置概览")
    config_data = load_json_file(CONFIG_PATH)
    if not config_data:
        show_message("error", "无法加载配置数据，配置概览不可用。")
        return

    with st.expander("GitHub 配置", expanded=True):
        github_cfg = config_data.get("github", {})
        if github_cfg:
            _display_config_detail_item("Token", github_cfg.get("token"), is_sensitive=True)
            _display_config_detail_item("订阅文件路径", github_cfg.get("subscriptions_file", SUBSCRIPTIONS_PATH))
            _display_config_detail_item("进度报告频率 (天)", github_cfg.get("progress_frequency_days", "N/A"))
            _display_config_detail_item("进度报告生成时间", github_cfg.get("progress_execution_time", "N/A"))
        else:
            show_message("info", "未配置 GitHub 相关信息。")

    with st.expander("邮件配置"):
        email_cfg = config_data.get("email", {})
        if email_cfg:
            _display_config_detail_item("SMTP 服务器", email_cfg.get("smtp_server", "N/A"))
            _display_config_detail_item("SMTP 端口", email_cfg.get("smtp_port", "N/A"))
            _display_config_detail_item("发件人", email_cfg.get("from", "N/A"))
            _display_config_detail_item("密码", email_cfg.get("password"), is_sensitive=True)
            to_emails = email_cfg.get('to', [])
            _display_config_detail_item("收件人", ", ".join(to_emails) if isinstance(to_emails, list) else str(to_emails))
        else:
            show_message("info", "未配置邮件相关信息。")

    with st.expander("LLM 配置"):
        llm_cfg = config_data.get("llm", {})
        if llm_cfg:
            _display_config_detail_item("模型类型", llm_cfg.get("model_type", "N/A"))
            _display_config_detail_item("OpenAI 模型名称", llm_cfg.get("openai_model_name", "N/A"))
            _display_config_detail_item("Ollama 模型名称", llm_cfg.get("ollama_model_name", "N/A"))
            _display_config_detail_item("Ollama API URL", llm_cfg.get("ollama_api_url", "N/A"))
        else:
            show_message("info", "未配置 LLM 相关信息。")

    with st.expander("报告类型"):
        report_types = config_data.get("report_types", [])
        if report_types:
            st.markdown("- " + "\n- ".join(report_types))
        else:
            show_message("info", "未配置报告类型。")

    with st.expander("Slack 配置"):
        slack_cfg = config_data.get("slack", {})
        if slack_cfg:
            _display_config_detail_item("Webhook URL", slack_cfg.get("webhook_url"), is_sensitive=True)
        else:
            show_message("info", "未配置 Slack 相关信息。")

    st.markdown("---")
    st.caption(f"提示: 配置文件 `{CONFIG_PATH}` 控制这些设置。敏感信息（如Token/密码）在此处部分隐藏。")
    st.markdown("""
    <details>
    <summary>点击查看自定义样式说明</summary>
    <p>您可以通过在项目根目录下创建 <code>.streamlit/config.toml</code> 文件来自定义应用主题和样式。</p>
    <p>例如，要设置暗色主题并更改主颜色，您的 <code>.streamlit/config.toml</code> 可能如下所示:</p>
    <pre><code>
[theme]
base="dark"
primaryColor="#1E88E5"
    </code></pre>
    <p>更多信息请查阅 <a href="https://docs.streamlit.io/library/advanced-features/theming" target="_blank">Streamlit 主题文档</a>。</p>
    </details>
    """, unsafe_allow_html=True)


def display_subscriptions_overview():
    """UI for displaying a summary of current subscriptions."""
    st.subheader("📚 当前订阅概览")
    subscriptions_data = get_subscriptions()
    if subscriptions_data:
        github_subs_count = len(subscriptions_data.get("github_subscriptions", []))
        st.metric(label="GitHub 仓库订阅数量", value=github_subs_count)
    else:
        show_message("warning", "无法加载订阅信息以显示概览。")

# --- Main Application ---
def main():
    """Main function to run the Streamlit application."""
    st.title("智能信息助手 - 0xScout Dashboard")
    st.caption(f"欢迎使用 0xScout！ ({APP_VERSION}) 选择左侧导航栏的功能开始探索。")

    st.sidebar.title("🧭 导航与控制")
    # Updated nav_options and nav_icons
    nav_options = ["配置概览", "订阅管理", "报告生成", "应用设置"]
    nav_icons = {"配置概览": "⚙️", "订阅管理": "🔧", "报告生成": "📊", "应用设置": "🛠️"}

    nav_display_options = []
    for opt in nav_options:
        nav_display_options.append(f"{nav_icons.get(opt, '📄')} {opt}")

    nav_mapping = {display_opt: original_opt for display_opt, original_opt in zip(nav_display_options, nav_options)}

    displayed_selection = st.sidebar.radio(
        "选择功能:", nav_display_options, key="nav_main_radio_selector", label_visibility="collapsed"
    )
    nav_selection = nav_mapping[displayed_selection]

    st.sidebar.markdown("---")
    st.sidebar.info(f"**0xScout**\n\n版本: {APP_VERSION}")

    if nav_selection == "配置概览":
        display_config_overview()
        st.markdown("---")
        display_subscriptions_overview()
    elif nav_selection == "订阅管理":
        display_subscription_management()
    elif nav_selection == "报告生成":
        display_report_generation_ui()
    elif nav_selection == "应用设置": # New branch for App Settings
        display_app_settings_ui()
    else:
        show_message("error", "无效的导航选项。")

if __name__ == "__main__":
    main()
