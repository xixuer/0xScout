import gradio as gr  # 导入gradio库用于创建GUI
import os # Added

from config import Config  # 导入配置管理模块
from github_client import GitHubClient  # 导入用于GitHub API操作的客户端
from hacker_news_client import HackerNewsClient
from report_generator import ReportGenerator  # 导入报告生成器模块
from llm import LLM  # 导入可能用于处理语言模型的LLM类
from subscription_manager import SubscriptionManager  # 导入订阅管理器
from logger import LOG  # 导入日志记录器

# 创建各个组件的实例
config = Config()
github_client = GitHubClient(config.github_token)
hacker_news_client = HackerNewsClient() # 创建 Hacker News 客户端实例
subscription_manager = SubscriptionManager(config.subscriptions_file)

def generate_github_report(model_type, model_name, repo, days):
    config.llm_model_type = model_type

    if model_type == "openai":
        config.openai_model_name = model_name
    else:
        config.ollama_model_name = model_name

    llm = LLM(config)  # 创建语言模型实例
    report_generator = ReportGenerator(llm, config, github_client)  # Updated: 创建报告生成器实例

    if not repo or '/' not in repo:
        LOG.error(f"Gradio: Invalid repository format for '{repo}'. Expected 'owner/repo'.")
        yield "Error: Invalid repository format. Please use 'owner/repo'.", None
        return

    try:
        owner, repo_name = repo.split('/', 1)
    except ValueError:
        LOG.error(f"Gradio: Could not parse owner/repo from '{repo}'.")
        yield "Error: Invalid repository format. Could not parse owner/repo.", None
        return

    if not owner or not repo_name:
        LOG.error(f"Gradio: Owner or repo_name is empty from parsed '{repo}'.")
        yield "Error: Owner or repository name cannot be empty.", None
        return

    LOG.info(f"Gradio: Generating GitHub project report for {owner}/{repo_name}, days={days}")
    # report_generator.generate_github_project_report now returns a generator
    report_stream = report_generator.generate_github_project_report(owner, repo_name, days)
    for chunk in report_stream:
        yield chunk, None # Yield content for markdown, None for file

def generate_hn_hour_topic(model_type, model_name):
    config.llm_model_type = model_type

    if model_type == "openai":
        config.openai_model_name = model_name
    else:
        config.ollama_model_name = model_name

    llm = LLM(config)  # 创建语言模型实例
    report_generator = ReportGenerator(llm, config, github_client)  # Updated: 创建报告生成器实例

    markdown_file_path = hacker_news_client.export_top_stories()

    if markdown_file_path is None:
        LOG.error("Gradio: Could not fetch Hacker News data. File path is None.")
        yield "Error: Could not fetch Hacker News data. File path is None.", None
        return

    try:
        fn = os.path.basename(markdown_file_path)
        hour_str = os.path.splitext(fn)[0]
        date_str = os.path.basename(os.path.dirname(markdown_file_path))
        # Basic validation
        if not (hour_str.isdigit() and len(date_str.split('-')) == 3):
            error_msg = f"Error: Could not parse date/hour from file path: {markdown_file_path}"
            LOG.error(f"Gradio: {error_msg}")
            yield error_msg, None
            return
    except Exception as e:
        error_msg = f"Error parsing date/hour from file path: {markdown_file_path}. Details: {e}"
        LOG.error(f"Gradio: {error_msg}", exc_info=True)
        yield error_msg, None
        return

    LOG.info(f"Gradio: Generating HN hourly report for {date_str} {hour_str}:00")
    # report_generator.get_hacker_news_hourly_report now returns a generator
    report_stream = report_generator.get_hacker_news_hourly_report(date_str, hour_str)
    for chunk in report_stream:
        yield chunk, None # Yield content for markdown, None for file


# 定义一个回调函数，用于根据 Radio 组件的选择返回不同的 Dropdown 选项
def update_model_list(model_type):
    if model_type == "openai":
        return gr.Dropdown(choices=["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"], label="选择模型")
    elif model_type == "ollama":
        return gr.Dropdown(choices=["llama3.1", "gemma2:2b", "qwen2:7b"], label="选择模型")


# 创建 Gradio 界面
with gr.Blocks(title="0xScout") as demo:
    # 创建 GitHub 项目进展 Tab
    with gr.Tab("GitHub 项目进展"):
        gr.Markdown("## GitHub 项目进展")  # 添加小标题

        # 创建 Radio 组件
        model_type = gr.Radio(["openai", "ollama"], label="模型类型", info="使用 OpenAI GPT API 或 Ollama 私有化模型服务")

        # 创建 Dropdown 组件
        model_name = gr.Dropdown(choices=["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"], label="选择模型")

        # 创建订阅列表的 Dropdown 组件
        subscription_list = gr.Dropdown(subscription_manager.list_subscriptions(), label="订阅列表", info="已订阅GitHub项目")

        # 创建 Slider 组件
        days = gr.Slider(value=2, minimum=1, maximum=7, step=1, label="报告周期", info="生成项目过去一段时间进展，单位：天")

        # 使用 radio 组件的值来更新 dropdown 组件的选项
        model_type.change(fn=update_model_list, inputs=model_type, outputs=model_name)

        # 创建按钮来生成报告
        button = gr.Button("生成报告")

        # 设置输出组件
        markdown_output = gr.Markdown()
        file_output = gr.File(label="下载报告")

        # 将按钮点击事件与导出函数绑定
        button.click(generate_github_report, inputs=[model_type, model_name, subscription_list, days], outputs=[markdown_output, file_output])

    # 创建 Hacker News 热点话题 Tab
    with gr.Tab("Hacker News 热点话题"):
        gr.Markdown("## Hacker News 热点话题")  # 添加小标题

        # 创建 Radio 组件
        model_type = gr.Radio(["openai", "ollama"], label="模型类型", info="使用 OpenAI GPT API 或 Ollama 私有化模型服务")

        # 创建 Dropdown 组件
        model_name = gr.Dropdown(choices=["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"], label="选择模型")

        # 使用 radio 组件的值来更新 dropdown 组件的选项
        model_type.change(fn=update_model_list, inputs=model_type, outputs=model_name)

        # 创建按钮来生成报告
        button = gr.Button("生成最新热点话题")

        # 设置输出组件
        markdown_output = gr.Markdown()
        file_output = gr.File(label="下载报告")

        # 将按钮点击事件与导出函数绑定
        button.click(generate_hn_hour_topic, inputs=[model_type, model_name,], outputs=[markdown_output, file_output])



if __name__ == "__main__":
    demo.launch(share=True, server_name="0.0.0.0")  # 启动界面并设置为公共可访问
    # 可选带有用户认证的启动方式
    # demo.launch(share=True, server_name="0.0.0.0", auth=("django", "1234"))