import sys # Moved to top if not already
import os # Moved to top if not already

# Get the absolute path of the 'src' directory (where this daemon_process.py file is)
# __file__ is the path to the current script.
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
# Get the absolute path of the project root (which is the parent directory of 'src')
PROJECT_ROOT = os.path.dirname(SRC_DIR)

# Add PROJECT_ROOT to the beginning of sys.path if it's not already there
# This allows Python to find modules in the project root, like 'config.py'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Now, the rest of the original imports can follow
import schedule
import time
import signal # Already imported sys and os
from datetime import datetime, timedelta # Ensure timedelta is available
import pytz

from config import Settings as Config # This import should now work reliably
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

# Renamed from github_job, new logic implemented
def send_daily_reports_job(subscription_manager, github_client, report_generator, notifier, days_frequency):
    LOG.info(f"定时任务 send_daily_reports_job 启动。执行频率: 每 {days_frequency} 天。")
    LOG.info("[开始执行每日合并报告任务]")

    github_report_string = "_GitHub仓库更新: 未能生成或无内容。_"
    hn_summary_string = "_Hacker News每日摘要: 未能生成或无内容。_"

    beijing_time_now = datetime.now(pytz.timezone('Asia/Shanghai'))
    current_date_str_for_reports = beijing_time_now.strftime('%Y-%m-%d')

    # --- Generate Consolidated GitHub Report ---
    LOG.info(f"Generating consolidated GitHub report for last {days_frequency} days...")
    try:
        temp_github_report = report_generator.get_consolidated_github_report_for_email(days=days_frequency)
        if temp_github_report and temp_github_report.strip() and \
           not temp_github_report.startswith("错误：") and \
           not temp_github_report.startswith("注意："):
            github_report_string = temp_github_report
        elif temp_github_report and temp_github_report.strip():
            github_report_string = temp_github_report
        LOG.info("Consolidated GitHub report generation attempt complete.")
    except Exception as e_gh:
        LOG.error(f"Error generating consolidated GitHub report: {e_gh}", exc_info=True)
        github_report_string = f"_GitHub仓库更新: 生成时发生错误 - {e_gh}_"

    # --- Generate Hacker News Daily Summary ---
    LOG.info(f"Generating Hacker News daily summary for {current_date_str_for_reports}...")
    try:
        hn_summary_stream = report_generator.get_hacker_news_daily_summary(current_date_str_for_reports)
        hn_report_chunks = []
        for chunk in hn_summary_stream:
            hn_report_chunks.append(str(chunk))
        temp_hn_summary = "".join(hn_report_chunks)

        if temp_hn_summary and temp_hn_summary.strip() and \
           not temp_hn_summary.startswith("错误：") and \
           not temp_hn_summary.startswith("未能获取") and \
           not temp_hn_summary.startswith("注意："):
            hn_summary_string = temp_hn_summary
        elif temp_hn_summary and temp_hn_summary.strip():
             hn_summary_string = temp_hn_summary
        LOG.info("Hacker News daily summary generation attempt complete.")
    except Exception as e_hn:
        LOG.error(f"Error generating Hacker News daily summary: {e_hn}", exc_info=True)
        hn_summary_string = f"_Hacker News每日摘要: 生成时发生错误 - {e_hn}_"

    # --- Combine Reports & Send Email ---
    email_subject = f"每日资讯摘要 ({current_date_str_for_reports}): GitHub仓库 & Hacker News"

    combined_report_markdown = (
        f"# 每日资讯摘要 ({current_date_str_for_reports})\n\n"
        f"## 1. GitHub 仓库订阅更新\n\n{github_report_string}\n\n"
        f"---\n"
        f"## 2. Hacker News 每日热点\n\n{hn_summary_string}"
    )

    try:
        LOG.info(f"Attempting to send combined daily email. Subject: {email_subject}")
        notifier.send_email(email_subject, combined_report_markdown)
        LOG.info("Combined daily email sent successfully.")
    except Exception as e_email:
        LOG.error(f"Failed to send combined daily email: {e_email}", exc_info=True)

    LOG.info("[每日合并报告任务执行完毕]")

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


# Old hn_daily_job is removed.

# Placeholder for where other components are initialized in main()
# This function will be called from main() and when rescheduling.
def setup_schedules(current_config, schedule_lib, beijing_timezone, local_timezone,
                    job_send_daily_reports, job_hn_topic, # Pass job functions
                    components): # Pass dict of components like notifier, report_generator etc.

    LOG.info("Setting up scheduled jobs...")
    schedule_lib.clear() # Clear any existing schedules before setting new ones

    # --- Schedule Daily Combined Report Job ---
    # Note: current_config.get_github_progress_frequency_days() is used for freq,
    # this corresponds to the old github_job's frequency.
    daily_report_exec_time_str_bj = current_config.get_github_progress_execution_time()
    daily_report_freq_days = current_config.get_github_progress_frequency_days()

    try:
        parsed_time_bj = datetime.strptime(daily_report_exec_time_str_bj, "%H:%M").time()

        now_for_date_bj = datetime.now(beijing_timezone)
        target_dt_bj = now_for_date_bj.replace(hour=parsed_time_bj.hour, minute=parsed_time_bj.minute, second=0, microsecond=0)

        local_target_dt = target_dt_bj.astimezone(local_timezone)
        local_daily_report_time_str = local_target_dt.strftime("%H:%M")

        LOG.info(f"Daily Combined Report job: Configured for Beijing Time {daily_report_exec_time_str_bj} (every {daily_report_freq_days} days).")
        LOG.info(f"Calculated server local time for scheduling Daily Combined Report job: {local_daily_report_time_str} (Timezone: {local_timezone}).")

        schedule_lib.every(daily_report_freq_days).days.at(local_daily_report_time_str).do(
            job_send_daily_reports, # This is the renamed github_job
            components['subscription_manager'],
            components['github_client'],
            components['report_generator'],
            components['notifier'],
            daily_report_freq_days
        )
        LOG.info(f"Daily Combined Report job successfully scheduled at {local_daily_report_time_str} server local time.")

    except ValueError:
        LOG.error(f"Invalid format for 'progress_execution_time' ('{daily_report_exec_time_str_bj}'). Daily Combined Report job NOT scheduled.")
    except Exception as e_sched_daily:
        LOG.error(f"Error during Daily Combined Report job scheduling: {e_sched_daily}", exc_info=True)

    # --- Schedule HN Topic Job (Beijing Time based) ---
    BJ_HOURS_FOR_HN_TOPIC = ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"]
    LOG.info(f"Hacker News Topic job: Will be scheduled for these Beijing Times: {BJ_HOURS_FOR_HN_TOPIC}.")

    for bj_hour_str in BJ_HOURS_FOR_HN_TOPIC:
        local_hn_topic_time_str = "ERROR" # Default in case of error before assignment
        try:
            parsed_hn_time_bj = datetime.strptime(bj_hour_str, "%H:%M").time()

            now_for_date_bj_hn = datetime.now(beijing_timezone)
            target_dt_bj_hn = now_for_date_bj_hn.replace(
                hour=parsed_hn_time_bj.hour, minute=parsed_hn_time_bj.minute, second=0, microsecond=0
            )

            local_target_dt_hn = target_dt_bj_hn.astimezone(local_timezone)
            local_hn_topic_time_str = local_target_dt_hn.strftime("%H:%M")

            LOG.info(f"  Scheduling HN Topic job for Beijing Time {bj_hour_str} at server local time {local_hn_topic_time_str} (Timezone: {local_timezone}).")
            schedule_lib.every().day.at(local_hn_topic_time_str).do(
                job_hn_topic,
                components['hacker_news_client'],
                components['report_generator']
            )
        except Exception as e_sched_hn_topic:
            LOG.error(f"Error scheduling HN Topic job for Beijing Time {bj_hour_str} (calculated local: {local_hn_topic_time_str}): {e_sched_hn_topic}", exc_info=True)

    LOG.info("All job scheduling setup completed.")


def main():
    # 设置信号处理器
    signal.signal(signal.SIGTERM, graceful_shutdown)

    config = Config()
    github_client = GitHubClient(config.get_github_token()) # Use getter
    hacker_news_client = HackerNewsClient()
    notifier = Notifier(config.get_email_config()) # Use getter
    llm = LLM(settings=config)
    report_generator = ReportGenerator(llm=llm, settings=config, github_client=github_client)
    subscription_manager = SubscriptionManager(config.get_subscriptions_file()) # Use positional argument

    beijing_tz = pytz.timezone('Asia/Shanghai')
    try:
        # Attempt to get local timezone robustly
        # Using tzlocal library is a more robust way if available, but sticking to pytz for now.
        local_tz_name_from_system = time.tzname[0] if time.daylight == 0 else time.tzname[1]
        # Check if tzname is specific enough, pytz might not recognize all system names directly
        # For common ones like 'CST', 'EST', it might be okay, but can be ambiguous.
        # A more direct way with pytz if system is well-configured for Python:
        local_tz = datetime.now().astimezone().tzinfo
        if local_tz is None or local_tz.tzname(None) is None or local_tz.tzname(None) in ['LMT', 'zzz']: # Check for minimal/ambiguous tzinfo
             LOG.warning(f"System local timezone name '{local_tz_name_from_system}' or resolved tzinfo '{local_tz}' is ambiguous or not specific. Falling back to offset-based local time. Scheduling might be less robust to DST changes if server's zone info is not fully recognized by pytz without tzlocal.")
             local_tz = datetime.now(pytz.utc).astimezone().tzinfo # This gets an offset-aware tz
        # else:
            # Attempt to make it a pytz timezone object if it's just a simple name from datetime.now().astimezone().tzinfo
            # This can be tricky. If local_tz is already a pytz object, this is fine.
            # If it's a simple string from tzinfo.tzname(), we might need to look it up.
            # For now, the above .astimezone().tzinfo should provide a usable tzinfo object.
            # If it's a string, it would need pytz.timezone(str(local_tz))
            # but tzinfo objects from datetime.now().astimezone().tzinfo are usually sufficient for astimezone() calls.

    except Exception as e_tz:
        LOG.error(f"Error determining local system timezone: {e_tz}. Defaulting to UTC for safety, this may not match server's actual local time behavior if server is not UTC.", exc_info=True)
        local_tz = pytz.utc

    LOG.info("守护进程已启动。")
    LOG.info(f"Configured server's determined local timezone for scheduling: {local_tz}")

    # Store components in a dictionary to pass to setup_schedules
    job_components = {
        'subscription_manager': subscription_manager,
        'github_client': github_client,
        'report_generator': report_generator,
        'notifier': notifier,
        'hacker_news_client': hacker_news_client
    }

    # Initial scheduling
    # Note: github_job is passed as job_send_daily_reports.
    # hn_daily_job is removed from direct scheduling here.
    # All previous schedule.every(...) lines are removed and handled by setup_schedules.
    current_config_for_scheduling = config
    setup_schedules(current_config_for_scheduling, schedule, beijing_tz, local_tz,
                    send_daily_reports_job, hn_topic_job,
                    job_components)
    last_scheduled_daily_exec_time_bj = current_config_for_scheduling.get_github_progress_execution_time()

    LOG.info(f"Initial daily report execution time (Beijing Time): {last_scheduled_daily_exec_time_bj}")
    LOG.info(f"计划任务设置完毕。进入主循环...")

    loop_counter = 0
    check_config_interval_seconds = 60
    loops_per_config_check = check_config_interval_seconds // 1

    try:
        while True:
            now_utc = datetime.now(pytz.utc)
            now_beijing = now_utc.astimezone(beijing_tz)
            now_local_server = now_utc.astimezone(local_tz)

            # --- Configuration Reload Check ---
            if loop_counter % loops_per_config_check == 0:
                LOG.debug(f"Loop iteration {loop_counter}. Checking for configuration changes...")
                try:
                    latest_config = Config() # Re-load config
                    new_daily_exec_time_bj = latest_config.get_github_progress_execution_time()

                    if new_daily_exec_time_bj != last_scheduled_daily_exec_time_bj:
                        LOG.info(f"Detected change in 'github.progress_execution_time' from '{last_scheduled_daily_exec_time_bj}' to '{new_daily_exec_time_bj}'. Rescheduling all jobs.")

                        setup_schedules(latest_config, schedule, beijing_tz, local_tz,
                                        send_daily_reports_job, hn_topic_job,
                                        job_components)

                        last_scheduled_daily_exec_time_bj = new_daily_exec_time_bj
                        current_config_for_scheduling = latest_config
                        LOG.info(f"Jobs rescheduled for new daily execution time (Beijing Time): {new_daily_exec_time_bj}")
                    else:
                        LOG.debug("No change detected in 'github.progress_execution_time'.")
                except Exception as e_conf_reload:
                    LOG.error(f"Error during configuration reload and check: {e_conf_reload}", exc_info=True)

            # --- Heartbeat Logging ---
            if loop_counter % 300 == 0:
                LOG.debug(f"Daemon heartbeat. Current loop count: {loop_counter}")
                LOG.debug(f"Current time: UTC: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}, Beijing: {now_beijing.strftime('%Y-%m-%d %H:%M:%S %Z')}, ServerLocal ({local_tz}): {now_local_server.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                if schedule.jobs:
                    job_details = []
                    for job in schedule.jobs:
                        job_details.append(f"  - Job: {job!r}, Next Run (local server time): {job.next_run}")
                    LOG.debug(f"Current scheduled jobs ({len(schedule.jobs)}):\n" + "\n".join(job_details))
                else:
                    LOG.debug("No jobs currently scheduled.")

            schedule.run_pending()

            loop_counter += 1
            if loop_counter >= 86400 * max(1, loops_per_config_check // 300 if loops_per_config_check > 0 and 300 % loops_per_config_check == 0 else 1) : # Reset loop_counter to avoid excessive growth
                loop_counter = 0

            time.sleep(1)
    except Exception as e:
        LOG.error(f"主进程发生异常: {str(e)}", exc_info=True)
        sys.exit(1)



if __name__ == '__main__':
    main()
