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
import hashlib
from datetime import datetime # Added

# Third-Party Imports
import streamlit as st

# Project-Specific Imports
from dotenv import load_dotenv
from loguru import logger as LOG
from src.logger import LOG # ADD THIS LINE
try:
    from src.report_generator import ReportGenerator
    from src.config import Settings
    from src.llm import LLM
    from src.clients.github_client import GitHubClient
    from src.clients.hacker_news_client import HackerNewsClient
    from src.notifier import Notifier
except ImportError as e:
    st.error(f"核心模块导入失败: {e}。应用无法启动。\n请检查项目结构和依赖项。")
    st.stop()

# --- Constants ---
CONFIG_PATH = "config.json"
SUBSCRIPTIONS_PATH = "subscriptions.json"
APP_VERSION = "0.1.1" 
ALL_AVAILABLE_REPORT_TYPES = ["github", "hacker_news_hours_topic", "hacker_news_daily_report"]
SESSION_TIMEOUT = 3600  # 自动登出时间（秒）, 默认1小时


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

SMTP_PRESETS = {
    "腾讯企业邮": {"server": "smtp.exmail.qq.com", "port": 465},
    "QQ邮箱": {"server": "smtp.qq.com", "port": 465}, # Or port 587 for STARTTLS
    "163邮箱": {"server": "smtp.163.com", "port": 465}, # Or port 25/994. 465 is common for SSL.
    "Gmail": {"server": "smtp.gmail.com", "port": 587}, # Requires STARTTLS
    "自定义": {"server": "", "port": 465} # Default for custom
}

def display_app_settings_ui():
    """UI for managing application settings."""
    st.header("⚙️ 应用设置")

    config_data = load_json_file(CONFIG_PATH)
    if not config_data: # Should be stopped by load_json_file if critical, but good practice
        show_message("error", "无法加载配置文件。设置页面不可用。")
        return
        
    # 应用密码设置
    st.subheader("🔒 应用访问密码")
    
    # 确保app_access部分存在
    if "app_access" not in config_data:
        config_data["app_access"] = {}
    
    with st.form("password_change_form"):
        st.write("更改应用访问密码")
        current_password = st.text_input("当前密码", type="password")
        new_password = st.text_input("新密码", type="password")
        confirm_password = st.text_input("确认新密码", type="password")
        
        password_submit = st.form_submit_button("更改密码")
        
        if password_submit:
            # 获取当前存储的密码哈希
            current_hash = config_data["app_access"].get("password_hash", "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918")  # Default "admin"
            
            # 验证当前密码
            input_current_hash = hashlib.sha256(current_password.encode()).hexdigest()
            
            if input_current_hash != current_hash:
                st.error("当前密码不正确")
            elif new_password != confirm_password:
                st.error("新密码与确认密码不匹配")
            elif not new_password:
                st.error("新密码不能为空")
            else:
                # 更新密码哈希
                new_hash = hashlib.sha256(new_password.encode()).hexdigest()
                config_data["app_access"]["password_hash"] = new_hash
                
                # 保存配置
                if save_json_file(CONFIG_PATH, config_data):
                    st.success("密码已更改成功！")
                else:
                    st.error("保存新密码失败")
    
    # 会话超时设置
    st.write("会话超时设置")
    st.caption("设置多长时间无活动后自动登出（单位：分钟）")
    
    # 获取当前超时设置（默认60分钟）
    current_timeout = config_data.get("app_access", {}).get("session_timeout_minutes", 60)
    
    # 创建一个滑块来设置超时时间
    timeout_options = [5, 10, 15, 30, 60, 120, 240, 480]
    timeout_index = timeout_options.index(60) if current_timeout not in timeout_options else timeout_options.index(current_timeout)
    
    new_timeout = st.select_slider(
        "会话超时时间（分钟）",
        options=timeout_options,
        value=timeout_options[timeout_index]
    )
    
    # 如果超时设置发生变化，更新配置
    if new_timeout != current_timeout:
        config_data.setdefault("app_access", {})["session_timeout_minutes"] = new_timeout
        if save_json_file(CONFIG_PATH, config_data):
            st.success(f"会话超时时间已更新为 {new_timeout} 分钟")
            # 更新全局变量
            global SESSION_TIMEOUT
            SESSION_TIMEOUT = new_timeout * 60  # 转换为秒
        else:
            st.error("保存超时设置失败")
    
    st.markdown("---")
    
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
    email_provider_options = list(SMTP_PRESETS.keys()) # Use keys from SMTP_PRESETS
    current_email_provider_from_config = email_config.get("provider", email_provider_options[0]) # Default to first option

    # Initialize session state for provider, server, and port if they don't exist
    if "current_provider" not in st.session_state:
        st.session_state.current_provider = current_email_provider_from_config
        # Ensure the provider from config is valid, otherwise default to "自定义"
        if current_email_provider_from_config not in SMTP_PRESETS:
            st.session_state.current_provider = "自定义"

        st.session_state.current_smtp_server = email_config.get(
            "smtp_server",
            SMTP_PRESETS[st.session_state.current_provider]["server"]
        )
        st.session_state.current_smtp_port = email_config.get(
            "smtp_port",
            SMTP_PRESETS[st.session_state.current_provider]["port"]
        )

    # Provider selection
    selected_provider = st.selectbox(
        "选择邮箱服务商预设",
        options=email_provider_options,
        index=email_provider_options.index(st.session_state.current_provider),
        key="settings_email_provider_selector",
        help="选择常用的邮箱服务商预设，或选择'自定义'手动填写SMTP信息。"
    )

    if selected_provider != st.session_state.current_provider:
        st.session_state.current_provider = selected_provider
        if selected_provider in SMTP_PRESETS:
            st.session_state.current_smtp_server = SMTP_PRESETS[selected_provider]["server"]
            st.session_state.current_smtp_port = SMTP_PRESETS[selected_provider]["port"]
        else: # Fallback, though options should restrict to SMTP_PRESETS keys
            st.session_state.current_smtp_server = ""
            st.session_state.current_smtp_port = 465
        st.rerun()

    # SMTP Server input field
    smtp_server_input = st.text_input(
        "SMTP 服务器地址:",
        value=st.session_state.current_smtp_server,
        key="settings_email_smtp_server"
    )
    if smtp_server_input != st.session_state.current_smtp_server and selected_provider == st.session_state.current_provider:
        st.session_state.current_smtp_server = smtp_server_input

    # SMTP Port input field
    smtp_port_input = st.number_input(
        "SMTP 端口:",
        min_value=1,
        max_value=65535,
        value=st.session_state.current_smtp_port,
        step=1,
        key="settings_email_smtp_port"
    )
    if smtp_port_input != st.session_state.current_smtp_port and selected_provider == st.session_state.current_provider:
        st.session_state.current_smtp_port = smtp_port_input

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
        # Use the new selector key for provider, and the direct keys for server/port
        email_settings['provider'] = st.session_state.settings_email_provider_selector
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

    available_report_types = config_data.get("report_types", [])
    if not available_report_types:
        show_message("warning", "配置文件中未定义任何报告类型 (`report_types`)。")
        return

    report_type = st.selectbox(
        "选择报告类型:", available_report_types, key="report_type_select",
        help="选择您希望生成的报告种类。"
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
            current_subscriptions = get_subscriptions()
            subscribed_repo_urls = [
                sub.get("repo_url") for sub in current_subscriptions.get("github_subscriptions", [])
                if isinstance(sub, dict) and sub.get("repo_url")
            ]
            repo_options = [""] + sorted(list(set(subscribed_repo_urls)))
            col_manual, col_select = st.columns(2)
            with col_manual:
                target_repo_manual_input = st.text_input(
                    "手动输入 owner/repo:", key="gh_single_repo_manual_text",
                    help="如果仓库未订阅或想手动指定。"
                )
            with col_select:
                target_repo_select = st.selectbox(
                    "或从已订阅仓库中选择:", repo_options, index=0,
                    key="gh_single_repo_select_box",
                    help="从已订阅仓库列表中选择。"
                )
            if target_repo_manual_input:
                normalized_manual_input = normalize_repo_input(target_repo_manual_input)
                if normalized_manual_input:
                    target_repo_input = normalized_manual_input
                else:
                    show_message("error", "手动输入的仓库格式不正确。请使用 'owner/repo'。")
            elif target_repo_select:
                target_repo_input = target_repo_select
            if target_repo_input:
                generate_report_button = st.button(f"为 {target_repo_input} 生成GitHub报告", key="generate_single_gh_report_btn")
            else:
                show_message("info", "请为 '指定单个仓库' 提供一个仓库（手动输入或从列表选择）。")
        else:
            github_report_scope = "all"
            generate_report_button = st.button("为所有已订阅仓库生成GitHub报告", key="generate_all_gh_report_btn")
    elif report_type == "hacker_news_hours_topic":
        generate_report_button = st.button("生成Hacker News小时热门话题报告", key="generate_hn_hours_topic_btn")
        
        # 添加显示选项
        if "show_hn_topic_analysis" not in st.session_state:
            st.session_state.show_hn_topic_analysis = True
        
        if "enable_ai_summary" not in st.session_state:
            st.session_state.enable_ai_summary = True
            
        col1, col2 = st.columns(2)
        with col1:
            st.checkbox("启用话题智能分析", value=st.session_state.show_hn_topic_analysis, 
                       key="hn_topic_analysis_checkbox", help="启用后将生成话题聚类分析报告")
        with col2:
            st.checkbox("启用AI文章摘要", value=st.session_state.enable_ai_summary,
                       key="hn_ai_summary_checkbox", help="启用后将为热门文章生成简短的AI摘要描述")
        
        # 每次复选框变更时更新状态
        st.session_state.show_hn_topic_analysis = st.session_state.hn_topic_analysis_checkbox
        st.session_state.enable_ai_summary = st.session_state.hn_ai_summary_checkbox
    elif report_type == "hacker_news_daily_report":
        generate_report_button = st.button("生成Hacker News每日摘要报告", key="generate_hn_daily_report_btn")
    else:
        show_message("warning", f"暂不支持 '{report_type}' 类型的报告生成UI。")

    if generate_report_button:
        try:
            settings = Settings(config_file=CONFIG_PATH)
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
            with st.spinner("⏳ 正在为所有已订阅仓库生成GitHub报告..."):
                main_report_iter = iter(report_generator.generate_github_subscription_report())

                overall_title = next(main_report_iter, None)
                if overall_title and isinstance(overall_title, str):
                    # Check if it's an info/error message first
                    if overall_title.startswith("没有配置 GitHub 仓库订阅") or \
                       overall_title.startswith("所有订阅条目均未能成功解析为有效的仓库"):
                        st.info(overall_title)
                        # No further processing needed if it's just an info message
                    else:
                        st.markdown(overall_title) # Display the main title
                        # Now iterate through the project-specific generators
                        for single_project_generator in main_report_iter:
                            project_specific_iter = iter(single_project_generator)
                            left_col, right_col = st.columns(2)
                            factual_data_chunk = None # Initialize for current project
                            separator_chunk = None  # Initialize for current project
                            try:
                                factual_data_chunk = next(project_specific_iter, None)
                                if factual_data_chunk:
                                    with left_col:
                                        st.markdown("---")
                                        # Factual data already contains its own "## owner/repo ..." title from _generate_github_project_basic_info_markdown
                                        st.markdown(factual_data_chunk)
                                else:
                                    with left_col: st.warning("未能获取项目的原始数据部分。")

                                separator_chunk = next(project_specific_iter, None)
                                if separator_chunk:
                                    with right_col:
                                        st.markdown("---") # Added for visual consistency
                                        st.markdown(separator_chunk)
                                        # Check if it's the actual LLM summary header or a skip notice
                                        if "LLM 智能摘要" in separator_chunk or "AI Summary" in separator_chunk:
                                            st.write_stream(project_specific_iter)
                                        # If it's a skip notice like "LLM摘要已跳过", it's already displayed by the markdown above.
                                else: # No separator/notice, means LLM part was skipped or something unexpected.
                                     with right_col: st.info("LLM摘要部分未生成或无内容。")

                            except StopIteration:
                                # This means the single_project_generator ended.
                                # This can happen if only factual data was yielded (LLM skipped with no notice chunk)
                                if factual_data_chunk and not separator_chunk:
                                     with right_col: st.info("LLM摘要部分未生成或无内容。")
                                elif not factual_data_chunk: # Should be caught by earlier check but as a safeguard
                                     st.warning("一个项目报告生成器未产生预期的数据。")
                            except Exception as e_proj_stream:
                                st.error(f"处理单个项目报告流时出错: {e_proj_stream}")
                                st.code(traceback.format_exc())
                            st.divider() # Visual separator between project reports
                elif overall_title is None: # Should not happen if generator is well-behaved
                     st.warning("报告生成器未能初始化或未产生任何内容。")

            show_message("success", "GitHub 订阅报告流程处理完毕。")

        elif report_type == "github" and github_report_scope == "single" and target_repo_input:
            try:
                owner, repo_name = target_repo_input.split('/')
                with st.spinner(f"⏳ 正在为 {target_repo_input} 生成GitHub报告..."):
                    left_column, right_column = st.columns(2)
                    report_stream = report_generator.generate_github_project_report(owner=owner, repo_name=repo_name)
                    factual_data_chunk = None
                    separator_chunk = None
                    try:
                        factual_data_chunk = next(report_stream)
                        with left_column:
                            st.markdown("---") # Added for visual consistency
                            st.markdown("### 📝 原始数据 (Factual Data)")
                            st.markdown(factual_data_chunk)

                        separator_chunk = next(report_stream)
                        with right_column:
                            st.markdown(separator_chunk) # Display the rich separator
                            st.write_stream(report_stream) # Stream remaining LLM parts

                    except StopIteration:
                        with left_column: # Ensure message appears in a column
                            if factual_data_chunk is not None and separator_chunk is None:
                                # Factual data yielded, LLM part skipped.
                                # Factual data is already in left_column.
                                with right_column: # Display message in right column
                                    st.info("LLM摘要未生成（可能由于配置或无适用内容）。")
                            elif factual_data_chunk is None:
                                st.warning("报告生成器未产生任何内容。")
                    except Exception as e_stream_consume:
                        st.error(f"处理报告流时发生错误: {e_stream_consume}")
                        st.code(traceback.format_exc())
                show_message("success", f"GitHub 项目 {target_repo_input} 报告流程处理完毕。")
            except ValueError:
                st.error(f"仓库格式不正确: {target_repo_input}。请使用 'owner/repo' 格式。")
            except Exception as e_gh_single:
                st.error(f"为 {target_repo_input} 生成GitHub报告时出错: {e_gh_single}")
                st.code(traceback.format_exc())

        elif report_type == "hacker_news_hours_topic":
            with st.spinner("⏳ 正在生成Hacker News小时热门话题报告..."):
                try:
                    hn_client = HackerNewsClient()
                    
                    # 根据用户选择是否进行话题分析
                    enable_topic_analysis = st.session_state.get("show_hn_topic_analysis", True)
                    
                    # 根据用户选择是否启用AI摘要
                    enable_ai_summary = st.session_state.get("enable_ai_summary", True)
                    
                    # 导出热门文章
                    markdown_file_path = hn_client.export_top_stories(enable_ai_summary=enable_ai_summary)
                    
                    if markdown_file_path is None:
                        st.error("错误: 未能获取Hacker News数据文件路径。")
                    else:
                        fn = os.path.basename(markdown_file_path)
                        hour_str = os.path.splitext(fn)[0]
                        date_str = os.path.basename(os.path.dirname(markdown_file_path))
                        
                        if not (hour_str.isdigit() and len(date_str.split('-')) == 3):
                            st.error(f"错误: 无法从路径 {markdown_file_path} 解析日期/小时。")
                        else:
                            # 读取基本列表报告
                            with open(markdown_file_path, 'r', encoding='utf-8') as f:
                                stories_content = f.read()
                                
                            # 尝试读取话题分析报告
                            topics_file_path = os.path.join(os.path.dirname(markdown_file_path), f"{hour_str}_topics.md")
                            topics_content = None
                            
                            if os.path.exists(topics_file_path):
                                with open(topics_file_path, 'r', encoding='utf-8') as f:
                                    topics_content = f.read()
                            
                            # 显示报告
                            if enable_topic_analysis and topics_content:
                                # 如果启用了话题分析并且有分析结果，则以标签页形式展示
                                tab1, tab2 = st.tabs(["📊 话题分析", "📝 原始列表"])
                                
                                with tab1:
                                    st.markdown(topics_content)
                                    
                                with tab2:
                                    st.markdown(stories_content)
                            else:
                                # 只显示原始列表
                                st.markdown(stories_content)
                                
                                if enable_topic_analysis and not topics_content:
                                    st.info("未找到话题分析结果。这可能是因为分析器尚未安装、分析过程中出错，或者数据量不足以进行有意义的聚类。")
                            
                            show_message("success", "Hacker News 小时热门话题报告生成完毕。")
                except Exception as e_hn_hourly:
                    st.error(f"生成Hacker News小时报告时出错: {e_hn_hourly}")
                    st.code(traceback.format_exc())

        elif report_type == "hacker_news_daily_report":
            with st.spinner("⏳ 正在生成Hacker News每日摘要报告..."):
                try:
                    current_date_str = datetime.now().strftime('%Y-%m-%d')
                    st.write_stream(report_generator.get_hacker_news_daily_summary(current_date_str))
                    show_message("success", "Hacker News 每日摘要报告流程处理完毕。")
                except Exception as e_hn_daily:
                    st.error(f"生成Hacker News每日报告时出错: {e_hn_daily}")
                    st.code(traceback.format_exc())
        else:
            if report_type == "github" and github_report_scope == "single" and not target_repo_input:
                show_message("info", "请为 '指定单个仓库' 提供一个仓库（手动输入或从列表选择）。")
            # else: # Other unhandled cases, though UI should prevent most.
                # show_message("warning", "选择的报告类型或范围无法处理。")

    # Remove or comment out the old display logic
    # st.markdown("---")
    # if st.session_state.generated_report_content:
    #     st.subheader("📄 生成的报告:")
    #     st.markdown(st.session_state.generated_report_content, unsafe_allow_html=True)
    #     if st.button("清除报告显示", key="clear_report_display_btn", help="点击以清除当前显示的报告内容。"):
    #         st.session_state.generated_report_content = None
    #         st.rerun()

    st.markdown("---")
    st.subheader("📧 测试邮件发送")
    if st.button("立即发送测试摘要邮件", key="send_test_email_now_button"):
        with st.spinner("⏳ 正在准备并发送测试邮件..."):
            try:
                current_settings = Settings(config_file=CONFIG_PATH)
                if not current_settings.get_email_config().get('to'):
                    show_message("error", "邮件发送失败：未配置收件人地址。请在应用设置中配置。")
                elif not current_settings.get_email_config().get('from') or \
                     not current_settings.get_email_config().get('smtp_server') or \
                     not current_settings.get_email_config().get('smtp_port'):
                    show_message("error", "邮件发送失败：发件人邮箱或SMTP服务器信息不完整。请在应用设置中配置。")
                else:
                    llm_instance = LLM(settings=current_settings)
                    github_token = current_settings.get_github_token()
                    github_client_instance = GitHubClient(token=github_token if github_token else "dummy_token_for_test_email")

                    notifier_instance = Notifier(email_settings=current_settings.get_email_config())
                    report_generator_instance = ReportGenerator(llm=llm_instance, settings=current_settings, github_client=github_client_instance)

                    # --- Generate Hacker News Daily Summary ---
                    hn_summary_str = ""
                    try:
                        LOG.info("Test Email: Generating Hacker News Daily Summary...")
                        current_date_str_hn = datetime.now().strftime('%Y-%m-%d')
                        hn_report_stream = report_generator_instance.get_hacker_news_daily_summary(current_date_str_hn)

                        hn_report_chunks = []
                        for chunk in hn_report_stream:
                            hn_report_chunks.append(str(chunk)) # Ensure chunk is string
                        hn_summary_str = "".join(hn_report_chunks)
                        if not hn_summary_str.strip():
                            hn_summary_str = "\n_Hacker News Daily Summary: No content generated or an error occurred._\n"
                            LOG.warning("Test Email: Hacker News Daily Summary content was empty.")
                        else:
                            LOG.info("Test Email: Hacker News Daily Summary generated.")
                    except Exception as e_hn:
                        LOG.error(f"Test Email: Error generating Hacker News Daily Summary: {e_hn}", exc_info=True)
                        hn_summary_str = f"\n_Error generating Hacker News Daily Summary: {e_hn}_\n"

                    # --- Generate Consolidated GitHub Report ---
                    github_summary_str = ""
                    try:
                        LOG.info("Test Email: Generating Consolidated GitHub Report (days=1)...")
                        github_summary_str = report_generator_instance.get_consolidated_github_report_for_email(days=1)
                        if not github_summary_str.strip():
                            github_summary_str = "\n_GitHub Subscriptions Update: No content generated or an error occurred unexpectedly._\n"
                            LOG.warning("Test Email: Consolidated GitHub Report content was unexpectedly empty (method should return specific messages).")
                        else:
                            LOG.info("Test Email: Consolidated GitHub Report generated.")
                    except Exception as e_gh:
                        LOG.error(f"Test Email: Error generating Consolidated GitHub Report: {e_gh}", exc_info=True)
                        github_summary_str = f"\n_Error generating GitHub Subscriptions Update: {e_gh}_\n"

                    # --- Combine Reports ---
                    combined_report_markdown = (
                        f"## 智能信息助手 - 测试邮件\n\n"
                        f"以下是为您生成的测试报告内容：\n\n"
                        f"---\n"
                        f"### 1. Hacker News 每日摘要\n\n{hn_summary_str}\n\n"
                        f"---\n"
                        f"### 2. GitHub 仓库订阅更新\n\n{github_summary_str}"
                    )

                    email_subject = f"[测试邮件] 每日摘要: HN资讯 & GitHub仓库动态 ({datetime.now().strftime('%Y-%m-%d')})"

                    if combined_report_markdown.strip():
                        LOG.info("Test Email: Sending combined report...")
                        notifier_instance.send_email(email_subject, combined_report_markdown)

                        recipients = current_settings.get_email_config().get('to', [])
                        recipients_str = ", ".join(recipients) if isinstance(recipients, list) else str(recipients)
                        show_message("success", f"合并的测试邮件已尝试发送至: {recipients_str}。请检查收件箱。")
                    else:
                        show_message("warning", "未能生成任何测试邮件内容。邮件未发送。")
                        LOG.warning("Test Email: Combined report content was empty. Email not sent.")
            except FileNotFoundError as e:
                show_message("error", f"初始化组件失败：配置文件缺失 - {e}")
                st.code(traceback.format_exc())
            except Exception as e:
                show_message("error", f"发送测试邮件时发生错误: {e}")
                st.code(traceback.format_exc())

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
        
    # 应用访问信息
    st.subheader("🔒 应用访问信息")
    app_access = config_data.get("app_access", {})
    if app_access:
        st.markdown("**密码保护:** 已启用")
    else:
        st.markdown("**密码保护:** 使用默认密码 (admin)")
    
    # 显示会话超时设置
    timeout_minutes = config_data.get("app_access", {}).get("session_timeout_minutes", 60)
    st.markdown(f"**会话超时:** {timeout_minutes} 分钟")
    
    st.caption("请在应用设置中更改默认密码以增强安全性")
    
    st.markdown("---")

    # Add a new section for Time Information
    st.subheader("🕰️ 时间与计划任务信息")

    # Display Current System Time
    try:
        system_now = datetime.now()
        st.markdown(f"**当前服务器系统时间:** `{system_now.strftime('%Y-%m-%d %H:%M:%S %Z')}`")
    except Exception as e:
        st.markdown(f"**当前服务器系统时间:** `获取失败: {e}`")

    # Display Scheduled GitHub Report Time
    if config_data: # Check if config_data was loaded successfully (already checked above but good for clarity)
        github_cfg = config_data.get("github", {})
        scheduled_time_str = github_cfg.get("progress_execution_time", "未配置")
        frequency_days = github_cfg.get("progress_frequency_days", "未配置")

        st.markdown(f"**GitHub 报告计划发送时间 (来自 config.json):** `{scheduled_time_str}` (每 `{frequency_days}` 天)")

        st.caption("请注意：计划任务的执行依赖于服务器的本地时间设置。如果服务器时间或时区不正确，计划任务可能不会在预期的（例如北京）时间运行。")
    else: # Should not be reached if initial check passes, but as a safeguard
        st.markdown("**GitHub 报告计划发送时间:** `配置加载失败`")

    st.markdown("---")

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

def check_session_timeout():
    """检查会话是否超时"""
    if "last_activity" in st.session_state:
        # 计算自上次活动以来的时间（秒）
        elapsed = (datetime.now() - st.session_state["last_activity"]).total_seconds()
        if elapsed > SESSION_TIMEOUT:
            # 会话超时，清除会话状态
            if "password_correct" in st.session_state:
                del st.session_state["password_correct"]
            if "last_activity" in st.session_state:
                del st.session_state["last_activity"]
            return True
    
    # 更新最后活动时间
    st.session_state["last_activity"] = datetime.now()
    return False

def check_password():
    """验证密码"""
    # 检查会话是否超时
    if check_session_timeout():
        st.sidebar.warning("会话已超时，请重新登录")
        
    # 如果已经通过验证，则直接返回True
    if "password_correct" in st.session_state and st.session_state["password_correct"]:
        return True
    
    # 加载配置文件以获取密码散列值
    config_data = load_json_file(CONFIG_PATH)
    
    # 如果配置文件中没有密码散列值，则设置默认密码为 "admin"
    stored_password_hash = config_data.get("app_access", {}).get("password_hash", "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918")  # "admin"的SHA-256散列值
    
    # 检查是否使用默认密码
    is_default_password = not config_data.get("app_access", {}).get("password_hash")
    
    # 创建一个侧边栏表单进行密码输入
    with st.sidebar.form("登录表单"):
        st.markdown("### 🔒 登录")
        
        if is_default_password:
            st.warning("⚠️ 当前使用默认密码: admin")
            st.caption("请成功登录后在'应用设置'中修改默认密码")
            
        password = st.text_input("请输入密码", type="password")
        submit = st.form_submit_button("登录")
    
    # 如果用户点击了提交按钮
    if submit:
        # 计算输入密码的SHA-256散列值
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        # 验证密码
        if password_hash == stored_password_hash:
            st.session_state["password_correct"] = True
            return True
        else:
            st.sidebar.error("❌ 密码错误")
            return False
            
    # 如果用户没有提交表单，返回False
    return False

# --- Main Application ---
def main():
    """Main function to run the Streamlit application."""
    # 从配置文件加载会话超时设置
    try:
        config_data = load_json_file(CONFIG_PATH)
        if config_data:
            timeout_minutes = config_data.get("app_access", {}).get("session_timeout_minutes", 60)
            global SESSION_TIMEOUT
            SESSION_TIMEOUT = timeout_minutes * 60  # 转换为秒
    except Exception as e:
        LOG.error(f"加载会话超时设置失败: {e}")
    
    st.title("智能信息助手 - 0xScout Dashboard")
    st.caption(f"欢迎使用 0xScout！ ({APP_VERSION}) 选择左侧导航栏的功能开始探索。")
    
    # 密码验证
    if not check_password():
        st.warning("⚠️ 应用已启用密码保护")
        st.info("请在左侧边栏输入密码以访问应用内容和功能")
        
        # 显示有关API密钥安全性的信息
        with st.expander("📌 关于密码保护"):
            st.markdown("""
            **为什么需要密码保护？**
            
            密码保护可以防止未授权用户访问您的应用，这对保护您的API密钥(如OpenAI、GitHub等)安全非常重要。
            未经授权的访问可能导致：
            - API密钥被盗用
            - 产生意外的API使用费用
            - 隐私数据泄露
            
            **首次使用**
            - 默认密码为: `admin`
            - 登录后请立即在"应用设置"中修改默认密码
            """)
        return
        
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
    
    # 添加登出按钮
    st.sidebar.markdown("---")
    if st.sidebar.button("🔒 登出"):
        if "password_correct" in st.session_state:
            del st.session_state["password_correct"]
        if "last_activity" in st.session_state:
            del st.session_state["last_activity"]
        st.rerun()

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
