import schedule # 导入 schedule 实现定时任务执行器
import time  # 导入time库，用于控制时间间隔
import os   # 导入os模块用于文件和目录操作
import signal  # 导入signal库，用于信号处理
import sys  # 导入sys库，用于执行系统相关的操作
from datetime import datetime  # 导入 datetime 模块用于获取当前日期

from config import Config  # 导入配置管理类
from github_client import GitHubClient  # 导入GitHub客户端类，处理GitHub API请求
from hacker_news_client import HackerNewsClient
from notifier import Notifier  # 导入通知器类，用于发送通知
from report_generator import ReportGenerator  # 导入报告生成器类
from llm import LLM  # 导入语言模型类，可能用于生成报告内容
from subscription_manager import SubscriptionManager  # 导入订阅管理器类，管理GitHub仓库订阅
from logger import LOG  # 导入日志记录器


def graceful_shutdown(signum, frame):
    # 优雅关闭程序的函数，处理信号时调用
    LOG.info("[优雅退出]守护进程接收到终止信号")
    sys.exit(0)  # 安全退出程序

def github_job(subscription_manager, github_client, report_generator, notifier, days):
    LOG.info("[开始执行定时任务]GitHub Repo 项目进展报告")
    subscriptions = subscription_manager.list_subscriptions()  # 获取当前所有订阅
    LOG.info(f"订阅列表：{subscriptions}")
    for repo_full_name in subscriptions: # Changed 'repo' to 'repo_full_name' for clarity
        # 遍历每个订阅的仓库，执行以下操作
        try:
            parts = repo_full_name.split('/')
            if len(parts) == 2 and parts[0] and parts[1]:
                owner, repo_name_only = parts[0], parts[1] # Renamed repo_name to repo_name_only to avoid conflict
                LOG.info(f"为仓库 {owner}/{repo_name_only} 生成报告...")

                report_stream = report_generator.generate_github_project_report(owner=owner, repo_name=repo_name_only, days=days)

                report_chunks = []
                for chunk in report_stream:
                    report_chunks.append(chunk)
                email_report_string = "".join(report_chunks)

                # Ensure email_report_string is not empty before notifying,
                # though generators should yield error strings if issues occur.
                if email_report_string.strip():
                    notifier.notify_github_report(repo_full_name, email_report_string)
                    LOG.info(f"已为仓库 {repo_full_name} 发送通知。")
                else:
                    LOG.warning(f"为仓库 {repo_full_name} 生成的报告内容为空，未发送通知。")
            else:
                LOG.error(f"订阅中的仓库名称格式不正确: '{repo_full_name}'。应为 'owner/repo' 格式。跳过此仓库的邮件通知。")
        except Exception as e:
            LOG.error(f"处理仓库 {repo_full_name} 的报告生成或通知时发生错误: {e}", exc_info=True)
            # Optionally, notify about the error itself if critical
            # notifier.notify_error(f"Error processing {repo_full_name}: {e}")

    LOG.info(f"[定时任务执行完毕] GitHub Repo 项目进展报告")


def hn_topic_job(hacker_news_client, report_generator):
    LOG.info("[开始执行定时任务]Hacker News 热点话题跟踪")
    markdown_file_path = hacker_news_client.export_top_stories()

    if markdown_file_path is None:
        LOG.error("未能获取 Hacker News 的热门报道，无法生成小时报告。")
        LOG.info(f"[定时任务执行完毕] Hacker News 热点话题跟踪 - 无数据")
        return

    try:
        # 从路径 hacker_news/YYYY-MM-DD/HH.md 解析日期和小时
        # basename = HH.md, dirname = hacker_news/YYYY-MM-DD
        base_name_with_ext = os.path.basename(markdown_file_path) # HH.md
        target_hour = os.path.splitext(base_name_with_ext)[0] # HH

        date_dir_full_path = os.path.dirname(markdown_file_path) # hacker_news/YYYY-MM-DD
        target_date = os.path.basename(date_dir_full_path) # YYYY-MM-DD

        # Basic validation for parsed components
        # Check if target_date looks like YYYY-MM-DD and target_hour is a number
        if not (len(target_date.split('-')) == 3 and target_hour.isdigit()):
            LOG.error(f"无法从路径 {markdown_file_path} 解析有效的日期和小时。日期部分: '{target_date}', 小时部分: '{target_hour}'")
            LOG.info(f"[定时任务执行完毕] Hacker News 热点话题跟踪 - 解析路径失败")
            return

        LOG.debug(f"从路径 {markdown_file_path} 解析得到日期: {target_date}, 小时: {target_hour}")
        report = report_generator.get_hacker_news_hourly_report(target_date, target_hour)
        LOG.debug(f"Generated HN hourly report (daemon): {report}")
    except Exception as e:
        LOG.error(f"处理 Hacker News 小时报告时发生错误 (路径: {markdown_file_path}): {e}", exc_info=True)

    LOG.info(f"[定时任务执行完毕] Hacker News 热点话题跟踪")


def hn_daily_job(hacker_news_client, report_generator, notifier):
    LOG.info("[开始执行定时任务]Hacker News 今日前沿技术趋势")
    # 获取当前日期，并格式化为 'YYYY-MM-DD' 格式
    date = datetime.now().strftime('%Y-%m-%d')

    report_stream = report_generator.get_hacker_news_daily_summary(date)

    report_chunks = []
    for chunk in report_stream:
        report_chunks.append(chunk)
    email_report_string = "".join(report_chunks)

    # notifier.notify_hn_report 会处理报告内容，即使是"无数据"的消息也应发送
    if email_report_string.strip(): # Check if there's actual content to send
        notifier.notify_hn_report(date, email_report_string)
        LOG.info(f"已为日期 {date} 发送 Hacker News 每日摘要通知。")
    else:
        LOG.warning(f"为日期 {date} 生成的 Hacker News 每日摘要内容为空，未发送通知。")

    LOG.info(f"[定时任务执行完毕] Hacker News 今日前沿技术趋势")


def main():
    # 设置信号处理器
    signal.signal(signal.SIGTERM, graceful_shutdown)

    config = Config()  # 创建配置实例
    github_client = GitHubClient(config.github_token)  # 创建GitHub客户端实例
    hacker_news_client = HackerNewsClient() # 创建 Hacker News 客户端实例
    notifier = Notifier(config.email)  # 创建通知器实例
    llm = LLM(config)  # 创建语言模型实例
    report_generator = ReportGenerator(llm, config, github_client)  # 创建报告生成器实例
    subscription_manager = SubscriptionManager(config.subscriptions_file)  # 创建订阅管理器实例

    # 启动时立即执行（如不需要可注释）
    # github_job(subscription_manager, github_client, report_generator, notifier, config.freq_days)
    hn_daily_job(hacker_news_client, report_generator, notifier)

    # 安排 GitHub 的定时任务
    schedule.every(config.freq_days).days.at(
        config.exec_time
    ).do(github_job, subscription_manager, github_client, report_generator, notifier, config.freq_days)
    
    # 安排 hn_topic_job 每4小时执行一次，从0点开始
    schedule.every(4).hours.at(":00").do(hn_topic_job, hacker_news_client, report_generator)

    # 安排 hn_daily_job 每天早上10点执行一次
    schedule.every().day.at("10:00").do(hn_daily_job, hacker_news_client, report_generator, notifier)

    try:
        # 在守护进程中持续运行
        while True:
            schedule.run_pending()
            time.sleep(1)  # 短暂休眠以减少 CPU 使用
    except Exception as e:
        LOG.error(f"主进程发生异常: {str(e)}")
        sys.exit(1)



if __name__ == '__main__':
    main()
