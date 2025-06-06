import os
from logger import LOG  # 导入日志模块
from datetime import datetime, timezone, timedelta, date as datetime_date # Added for release date handling

class ReportGenerator:
    # 1. Modified __init__ signature and assignments
    def __init__(self, llm, settings, github_client): # Added settings and github_client
        self.llm = llm
        self.settings = settings # Store settings instance
        self.github_client = github_client # Store github_client instance

        # Fully enable __init__ with settings
        self.report_types = self.settings.get_report_types()
        self.prompts = {}  # 存储所有预加载的提示信息
        self._preload_prompts() # Call to preload prompts

    def _preload_prompts(self):
        """
        Preloads prompt files. It attempts to load prompts for all report types specified
        in the settings, plus essential types "github" and "github_digest", using a
        fallback mechanism for locating the prompt files.
        """
        LOG.debug("Preloading prompts...")

        configured_report_types = self.settings.get_report_types()
        essential_prompt_keys = {"github", "github_digest"}

        types_to_load_prompts_for = set(configured_report_types if configured_report_types else [])
        types_to_load_prompts_for.update(essential_prompt_keys)

        if not types_to_load_prompts_for:
            LOG.warning("No report types configured in settings and no essential types to load. No prompts will be loaded.")
            return

        LOG.info(f"Attempting to load prompts for report types: {list(types_to_load_prompts_for)}")

        for report_type in types_to_load_prompts_for:
            llm_specific_model_name = getattr(self.llm, 'model', None) or getattr(self.llm, 'model_name', None)
            llm_general_type = getattr(self.llm, 'model_type', None) # e.g., "openai", "ollama"

            prompt_loaded = False
            prompt_paths_tried = []

            # 1. Try with specific LLM model name: e.g., prompts/github_gpt-4o-mini_prompt.txt
            if llm_specific_model_name:
                specific_model_key = f"{report_type}_{llm_specific_model_name}"
                prompt_file_path = self.settings.get_prompt_file_path(specific_model_key)
                prompt_paths_tried.append(f"'{specific_model_key}' (Path: {prompt_file_path})")
                if prompt_file_path and os.path.exists(prompt_file_path):
                    try:
                        with open(prompt_file_path, "r", encoding='utf-8') as file:
                            self.prompts[report_type] = file.read()
                        LOG.debug(f"Successfully loaded prompt for '{report_type}' using specific model key '{specific_model_key}' from {prompt_file_path}")
                        prompt_loaded = True
                    except Exception as e:
                        LOG.error(f"Error loading prompt file {prompt_file_path} for key '{specific_model_key}': {e}")

            # 2. If not loaded, try with general LLM type: e.g., prompts/github_openai_prompt.txt
            if not prompt_loaded and llm_general_type:
                general_type_key = f"{report_type}_{llm_general_type}"
                prompt_file_path = self.settings.get_prompt_file_path(general_type_key)
                prompt_paths_tried.append(f"'{general_type_key}' (Path: {prompt_file_path})")
                if prompt_file_path and os.path.exists(prompt_file_path):
                    try:
                        with open(prompt_file_path, "r", encoding='utf-8') as file:
                            self.prompts[report_type] = file.read()
                        LOG.debug(f"Successfully loaded prompt for '{report_type}' using general LLM type key '{general_type_key}' from {prompt_file_path}")
                        prompt_loaded = True
                    except Exception as e:
                        LOG.error(f"Error loading prompt file {prompt_file_path} for key '{general_type_key}': {e}")

            # 3. If still not loaded, try with generic report_type key: e.g., prompts/github_prompt.txt
            if not prompt_loaded:
                generic_key = report_type
                prompt_file_path = self.settings.get_prompt_file_path(generic_key)
                prompt_paths_tried.append(f"'{generic_key}' (Path: {prompt_file_path})")
                if prompt_file_path and os.path.exists(prompt_file_path):
                    try:
                        with open(prompt_file_path, "r", encoding='utf-8') as file:
                            self.prompts[report_type] = file.read()
                        LOG.debug(f"Successfully loaded prompt for '{report_type}' using generic key '{generic_key}' from {prompt_file_path}")
                        prompt_loaded = True
                    except Exception as e:
                        LOG.error(f"Error loading prompt file {prompt_file_path} for key '{generic_key}': {e}")

            # 4. If no prompt file was loaded successfully after all attempts, assign a default generic prompt.
            if not prompt_loaded:
                LOG.warning(f"Prompt for report type '{report_type}' not found after trying paths: {', '.join(prompt_paths_tried)}. Assigning default prompt.")
                self.prompts[report_type] = "Please summarize the following content:"

            # Ensure error prompts are assigned if any load attempt failed but didn't set prompt_loaded
            if report_type not in self.prompts: # Should only happen if an error occurred in a successful load block before assignment
                 LOG.error(f"Critical error: Prompt for '{report_type}' was attempted but not assigned. Paths tried: {', '.join(prompt_paths_tried)}. Assigning error prompt.")
                 self.prompts[report_type] = "Error loading prompt. Please summarize the following content:"

        LOG.info(f"Prompts loaded for types: {list(self.prompts.keys())}")

    def _format_releases_markdown(self, releases: list) -> str:
        """
        Formats a list of release dictionaries into a Markdown string.
        """
        if not releases:
            return "### 🚀 近期 Releases:\n\n最近没有发现 Releases。\n"

        markdown_parts = ["### 🚀 近期 Releases:\n"]
        for release in releases:
            name = release.get("name", "N/A")
            tag_name = release.get("tag_name", "N/A")
            html_url = release.get("html_url", "#")
            author_login = release.get("author_login", "N/A")
            published_at_str = release.get("published_at", "N/A")
            body = release.get("body", "无 Release Notes。")

            try:
                # Format date like YYYY-MM-DD
                formatted_date = datetime.strptime(published_at_str, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")
            except ValueError:
                formatted_date = published_at_str # Keep original if parsing fails

            release_md = (
                f"*   **[{name}]({html_url})** (Tag: `{tag_name}`)\n"
                f"    *发布者: {author_login} 于 {formatted_date}*\n"
            )
            if body and body.strip(): # Only add details if body is not empty
                release_md += (
                    f"    <details>\n"
                    f"    <summary>查看 Release Notes</summary>\n\n"
                    f"    {body.strip()}\n\n"
                    f"    </details>\n"
                )
            release_md += "---\n" # Separator for readability
            markdown_parts.append(release_md)
        
        return "\n".join(markdown_parts)

    def _generate_github_project_basic_info_markdown(self, owner: str, repo_name: str, days: int) -> str:
        """
        Fetches and formats basic project info (issues, PRs, commits, releases) into Markdown.
        This is the content that might be passed to an LLM or used directly.
        """
        repo_full_name = f"{owner}/{repo_name}"

        # Calculate date range for the report title
        today = datetime.now(timezone.utc)
        # If days=1, it's "past 1 day" meaning today. start_date should be today.
        # If days=2, it's "past 2 days" meaning yesterday and today. start_date should be yesterday.
        # So, timedelta(days=days-1) is correct.
        start_date = today - timedelta(days=days-1)
        today_str = today.strftime('%Y-%m-%d')
        start_date_str = start_date.strftime('%Y-%m-%d')

        # Ensure 'since_date_iso' for GitHub API is from the beginning of the start_date
        # to capture all events on that day.
        # The GitHub API 'since' parameter is inclusive.
        # For commits, it's typically "since a certain point in time".
        # For issues/PRs, 'since' usually refers to update time.
        # Using the start_date at midnight (beginning of the day) is a safe bet.
        since_date_dt_for_api = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0, tzinfo=timezone.utc)
        since_date_iso = since_date_dt_for_api.isoformat()

        LOG.debug(f"Fetching updates for {repo_full_name} for the period {start_date_str} to {today_str} (API 'since': {since_date_iso})")

        # It's crucial that github_client methods return lists of dicts with expected keys
        commits = self.github_client.fetch_commits(repo_full_name, since=since_date_iso)
        issues = self.github_client.fetch_issues(repo_full_name, since=since_date_iso)
        pull_requests = self.github_client.fetch_pull_requests(repo_full_name, since=since_date_iso)
        recent_releases = self.github_client.get_recent_releases(owner, repo_name, days_limit=days) # days_limit here should align with 'days'

        content_parts = [f"## {repo_full_name} 项目更新 (过去 {days} 天: {start_date_str} 至 {today_str})\n"]

        content_parts.append("### 📝 Commits:\n")
        if commits:
            for commit in commits[:10]: # Display top 10 commits
                commit_sha = commit.get('sha', '')[:7]
                commit_msg = commit.get('commit', {}).get('message', 'No commit message').splitlines()[0]
                author_login = commit.get('author', {}).get('login', 'N/A')
                commit_url = commit.get('html_url', '#')
                content_parts.append(f"- [`{commit_sha}`]({commit_url}) {commit_msg} (by {author_login})")
        else:
            content_parts.append("最近 {days} 天内没有 Commits。\n")

        content_parts.append("\n### 🛠 Issues (Closed):\n")
        if issues:
            for issue in issues[:10]: # Display top 10 issues
                issue_number = issue.get('number')
                issue_title = issue.get('title', 'N/A')
                issue_url = issue.get('html_url', '#')
                closed_by = issue.get('user', {}).get('login', 'N/A') # User who closed or was assigned? API might vary.
                                                                    # For 'closed' issues, 'user' is often the creator.
                                                                    # If using events, actor would be clearer.
                                                                    # For now, assume 'user' is relevant.
                content_parts.append(f"- [#{issue_number}]({issue_url}) {issue_title} (User: {closed_by})")
        else:
            content_parts.append(f"最近 {days} 天内没有关闭的 Issues。\n")

        content_parts.append("\n### ⇄ Pull Requests (Closed/Merged):\n")
        if pull_requests:
            for pr in pull_requests[:10]: # Display top 10 PRs
                pr_number = pr.get('number')
                pr_title = pr.get('title', 'N/A')
                pr_url = pr.get('html_url', '#')
                pr_state = pr.get('state', 'N/A')
                pr_user = pr.get('user', {}).get('login', 'N/A')
                content_parts.append(f"- [#{pr_number}]({pr_url}) {pr_title} (State: {pr_state}, by {pr_user})")
        else:
            content_parts.append(f"最近 {days} 天内没有关闭或合并的 Pull Requests。\n")

        # Add formatted releases section
        content_parts.append("\n" + self._format_releases_markdown(recent_releases))

        return "\n".join(content_parts)

    def _aggregate_hourly_hn_data(self, target_date: str | datetime_date) -> str | None:
        if isinstance(target_date, datetime_date):
            target_date_str = target_date.strftime('%Y-%m-%d')
        else:
            target_date_str = target_date

        base_dir = "hacker_news" # Base directory for HN data
        date_dir = os.path.join(base_dir, target_date_str)

        LOG.info(f"Attempting to aggregate Hacker News data for date: {target_date_str} from directory: {date_dir}")

        if not os.path.isdir(date_dir):
            LOG.warning(f"Data directory {date_dir} not found for Hacker News aggregation.")
            return None

        hourly_files = sorted([f for f in os.listdir(date_dir) if f.endswith(".md") and os.path.isfile(os.path.join(date_dir, f))])

        if not hourly_files:
            LOG.warning(f"No .md files found in {date_dir} for Hacker News aggregation.")
            return None

        all_content_parts = [f"# Hacker News Aggregated Content for {target_date_str}\n\n"]

        for hour_file in hourly_files:
            file_path = os.path.join(date_dir, hour_file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    # Add a header for each hour's content for clarity
                    hour_str = hour_file.split('.')[0]
                    all_content_parts.append(f"## Content from {target_date_str} {hour_str}:00\n\n")
                    all_content_parts.append(f.read())
                    all_content_parts.append("\n\n---\n\n") # Separator
                LOG.debug(f"Successfully read and added content from {file_path}")
            except Exception as e:
                LOG.error(f"Error reading file {file_path}: {e}")
                # Decide if one bad file should stop all aggregation or just be skipped
                all_content_parts.append(f"[Error reading content from {hour_file}: {e}]\n\n---\n\n")

        if len(all_content_parts) <= 1: # Only the main header was added
            LOG.warning(f"No content was successfully aggregated from files in {date_dir}.")
            return None

        return "".join(all_content_parts)

    def generate_github_project_report(self, owner: str, repo_name: str, days: int = None) -> str:
        """
        Generates a report for a single GitHub project, including recent releases.
        It first compiles factual data, then optionally uses an LLM for a summary.
        """
        if days is None:
            # Assuming settings has a method to get this default value
            days = self.settings.get_github_progress_frequency_days()
        LOG.info(f"准备为 {owner}/{repo_name} 生成项目报告 (过去 {days} 天)...")

        # 1. Generate the factual Markdown content
        factual_markdown = self._generate_github_project_basic_info_markdown(owner, repo_name, days)

        # 2. (Optional) Pass to LLM for summarization/analysis
        # Check if a specific prompt for "github" type is loaded and LLM is available
        system_prompt = self.prompts.get("github") # Get preloaded prompt
        if system_prompt and self.llm and hasattr(self.llm, 'generate_report'):
            LOG.debug(f"使用 LLM 为 {owner}/{repo_name} 生成摘要报告。")
            try:
                report_content = self.llm.generate_report(system_prompt, factual_markdown)
                # One could choose to prepend/append factual_markdown to LLM summary here,
                # or let the prompt guide the LLM on how to use the factual data.
                # For now, the LLM output is considered the final report if successful.
            except Exception as e:
                LOG.error(f"LLM 生成报告 for {owner}/{repo_name} 失败: {e}")
                LOG.warning(f"LLM 生成失败，将返回原始数据报告 for {owner}/{repo_name}。")
                report_content = factual_markdown # Fallback to factual data
        else:
            LOG.info(f"LLM 提示或 LLM 实例未完全配置，返回原始数据报告 for {owner}/{repo_name}。")
            report_content = factual_markdown # Fallback to factual data

        # Note: Saving the report to a file is removed from this method.
        # The caller (e.g., Streamlit app or a batch process) should handle saving if needed.

        # If LLM is to be used for summarization
        if system_prompt and self.llm and hasattr(self.llm, 'generate_report'):
            LOG.debug(f"使用 LLM 为 {owner}/{repo_name} 生成摘要报告。")
            yield factual_markdown # Yield factual data first
            yield "\n\n---\n### 🤖 LLM 智能摘要 (AI Summary):\n\n" # Updated separator
            try:
                yield from self.llm.generate_report(system_prompt, factual_markdown)
            except Exception as e:
                error_message = f"LLM 生成报告 for {owner}/{repo_name} 失败: {e}"
                LOG.error(error_message)
                yield f"\n警告: {error_message}\n返回原始数据报告。" # Yield error as part of stream
        else: # Fallback to factual data if no LLM summarization
            LOG.info(f"LLM 提示或 LLM 实例未完全配置，返回原始数据报告 for {owner}/{repo_name}。")
            yield factual_markdown

    def generate_github_report(self, markdown_file_path): # This method is DEPRECATED
        """
        DEPRECATED/TO BE REFACTORED.
        This method is based on pre-generated markdown files and does not fit the new model
        of fetching data directly via GitHubClient and then formatting/summarizing.
        Consider removing or adapting if a use case for processing external markdown remains.
        生成 GitHub 项目的报告，并保存为 {original_filename}_report.md。
        """
        LOG.warning("DEPRECATED: generate_github_report(markdown_file_path) called. This method is outdated.")
        with open(markdown_file_path, 'r') as file:
            markdown_content = file.read()

        system_prompt = self.prompts.get("github", "Summarize the provided GitHub project information:") # Ensure default
        report = self.llm.generate_report(system_prompt, markdown_content)
        
        report_file_path = os.path.splitext(markdown_file_path)[0] + "_report.md"
        with open(report_file_path, 'w+') as report_file:
            report_file.write(report)

        LOG.info(f"GitHub 项目报告已保存到 {report_file_path} (using deprecated method)")
        return report, report_file_path

    def generate_github_subscription_report(self):
        """
        Yields an overall title, then yields individual GitHub project report generators
        for each subscribed repository.
        """
        LOG.info("准备为所有已订阅的 GitHub 仓库生成单独报告的迭代器...")
        yield f"# GitHub 订阅总报告 - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"

        subscriptions = self.settings.get_github_subscriptions()
        if not subscriptions:
            message = "没有配置 GitHub 仓库订阅，无法生成报告。"
            LOG.warning(message)
            yield message # Yield the message string directly
            return

        days = self.settings.get_github_progress_frequency_days()
        # The "github" prompt will be fetched by generate_github_project_report itself.

        processed_subs_count = 0
        for sub_idx, sub in enumerate(subscriptions):
            owner = None
            repo_name = None
            repo_identifier_for_log = str(sub)

            if isinstance(sub, dict):
                owner = sub.get("owner")
                repo_name = sub.get("repo_name") or sub.get("repo")
                if 'repo_url' in sub and sub['repo_url'] and not (owner and repo_name) :
                    try:
                        url_path = sub['repo_url'].replace("https://github.com/", "")
                        parts = url_path.split('/')
                        if len(parts) >= 2:
                            owner = parts[-2]
                            repo_name = parts[-1]
                            repo_identifier_for_log = f"{owner}/{repo_name}"
                        else:
                            LOG.warning(f"无法从 repo_url '{sub['repo_url']}' 解析 owner 和 repo_name。跳过订阅: {sub}")
                            continue
                    except Exception as e:
                        LOG.error(f"解析 repo_url '{sub['repo_url']}' 时出错: {e}。跳过订阅: {sub}", exc_info=True)
                        continue
            elif isinstance(sub, str) and '/' in sub:
                try:
                    parts = sub.split('/')
                    if len(parts) == 2:
                        owner = parts[0]
                        repo_name = parts[1]
                        repo_identifier_for_log = f"{owner}/{repo_name}"
                    else:
                        LOG.warning(f"字符串订阅格式 '{sub}' 不正确。跳过。")
                        continue
                except Exception as e:
                    LOG.error(f"解析字符串订阅 '{sub}' 时出错: {e}。跳过。", exc_info=True)
                    continue

            if not owner or not repo_name:
                LOG.warning(f"订阅条目格式无法识别或信息不完整，跳过: {sub}")
                continue

            LOG.info(f"为仓库 {owner}/{repo_name} (订阅 {sub_idx+1}/{len(subscriptions)}) 创建报告生成器...")
            # Yield the generator for the individual project report
            yield self.generate_github_project_report(owner=owner, repo_name=repo_name, days=days)
            processed_subs_count +=1
        
        if processed_subs_count == 0 and subscriptions: # Check if any subs were actually processed
             yield "所有订阅条目均未能成功解析为有效的仓库，未生成任何报告。"

        LOG.info("所有 GitHub 订阅的报告生成器已提供完毕。")


    def generate_hacker_news_hours_topic_report(self, content: str): # -> Generator[str, None, None]
        """
        Generates a report for Hacker News hourly topics using provided content (stream capable).
        """
        if not content or not content.strip(): # Check if content is None or empty
            message = "错误: 未提供Hacker News小时主题报告的内容或内容为空。"
            LOG.error(message)
            yield message
            return
        
        # Check if content itself is an error message from a previous step
        if content.startswith("错误:") or content.startswith("No data found") or content.startswith("No content found"):
            LOG.warning(f"generate_hacker_news_hours_topic_report received potentially erroneous content: {content}")
            yield content
            return

        system_prompt = self.prompts.get("hacker_news_hours_topic", "Summarize the top Hacker News topics from the last hour:")
        LOG.debug(f"使用提示生成 HN 小时主题报告: '{system_prompt[:50]}...'")
        try:
            yield from self.llm.generate_report(system_prompt, content)
            LOG.info("Hacker News 小时主题报告已流式生成。")
        except Exception as e:
            error_message = f"LLM 生成 HN 小时主题报告失败: {e}"
            LOG.error(error_message, exc_info=True)
            yield error_message
        

    def generate_hacker_news_daily_report(self, aggregated_content: str): # -> Generator[str, None, None]
        """
        Generates a daily summary report for Hacker News from aggregated hourly topics content (stream capable).
        """
        if not aggregated_content or not aggregated_content.strip():
            message = "错误: 未提供Hacker News每日摘要报告的内容或内容为空。"
            LOG.error(message)
            yield message
            return

        if aggregated_content.startswith("错误:") or aggregated_content.startswith("No aggregated data found"):
            LOG.warning(f"generate_hacker_news_daily_report received potentially erroneous content: {aggregated_content}")
            yield aggregated_content
            return

        system_prompt = self.prompts.get("hacker_news_daily_report", "Summarize the main Hacker News trends from the day:")
        LOG.debug(f"使用提示生成 HN 每日摘要报告: '{system_prompt[:50]}...'")
        try:
            yield from self.llm.generate_report(system_prompt, aggregated_content)
            LOG.info("Hacker News 每日摘要报告已流式生成。")
        except Exception as e:
            error_message = f"LLM 生成 HN 每日摘要报告失败: {e}"
            LOG.error(error_message, exc_info=True)
            yield error_message


    def get_hacker_news_hourly_report(self, target_date: str, target_hour: str): # -> Generator[str, None, None]
        """
        Retrieves and generates a report for a specific hour of Hacker News data (stream capable).

        Args:
            target_date: The target date in "YYYY-MM-DD" format.
            target_hour: The target hour in "HH" format (e.g., "00", "15").

        Yields:
            String chunks of the Hacker News hourly report, or an informative message
            if data is not found or an error occurs.
        """
        file_path = os.path.join("hacker_news", target_date, f"{target_hour}.md")
        LOG.debug(f"Attempting to read Hacker News data from: {file_path}")

        if not os.path.exists(file_path):
            message = f"No data found for Hacker News at {target_date} {target_hour}:00. File does not exist: {file_path}"
            LOG.warning(message)
            yield message
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if not content.strip():
                message = f"No content found in Hacker News data file: {file_path} for {target_date} {target_hour}:00."
                LOG.warning(message)
                yield message
                return

            LOG.info(f"Successfully read content from {file_path}. Generating hourly report.")
            yield from self.generate_hacker_news_hours_topic_report(content)
        except Exception as e:
            message = f"Error reading or processing Hacker News data file {file_path}: {e}"
            LOG.error(message, exc_info=True)
            yield message


    def get_hacker_news_daily_summary(self, target_date: str): # -> Generator[str, None, None]
        """
        Generates a daily summary report for Hacker News based on aggregated hourly data (stream capable).

        Args:
            target_date: The target date in "YYYY-MM-DD" format.

        Yields:
            String chunks of the Hacker News daily summary report, or an informative
            message if no data is available for aggregation.
        """
        LOG.debug(f"Attempting to generate Hacker News daily summary for date: {target_date}")

        aggregated_content = self._aggregate_hourly_hn_data(target_date)

        if not aggregated_content or not aggregated_content.strip():
            message = f"No aggregated data found for Hacker News on {target_date} to generate a daily summary."
            LOG.warning(message)
            yield message
            return

        LOG.info(f"Successfully aggregated Hacker News data for {target_date}. Generating daily summary report.")
        yield from self.generate_hacker_news_daily_report(aggregated_content)

    # _aggregate_topic_reports is removed as its functionality is moved to the caller.

if __name__ == '__main__':
    from config import Config  # 导入配置管理类
    from llm import LLM
    # Placeholder for GitHubClient if needed for main block testing
    # from github_client import GitHubClient

    LOG.info("ReportGenerator __main__ block for testing (partially active).")
    # Mock or simplified settings and clients for basic __init__ testing
    class MockSettings:
        def get_report_types(self):
            LOG.debug("[MockSettings] get_report_types called")
            return ["github", "hacker_news_hours_topic", "hacker_news_daily_report", "github_digest", "non_existent_prompt_type"]

        def get_prompt_file_path(self, key):
            LOG.debug(f"[MockSettings] get_prompt_file_path called with key: {key}")
            dummy_prompt_dir = "prompts"
            os.makedirs(dummy_prompt_dir, exist_ok=True)

            # Specific prompt for github_digest
            if key == "github_digest_mock_model":
                path = os.path.join(dummy_prompt_dir, "github_digest_mock_model_prompt.txt")
                if not os.path.exists(path):
                    with open(path, "w") as f: f.write("Summarize this collection of GitHub project updates.")
                return path

            # Generic prompt for github (single project)
            if key == "github_mock_model":
                path = os.path.join(dummy_prompt_dir, "github_mock_model_prompt.txt")
                if not os.path.exists(path):
                    with open(path, "w") as f: f.write("This is a mock GitHub prompt for testing.")
                return path

            # For HN, assume they might not have specific files and will use default from .get() in _preload_prompts
            if key.startswith("hacker_news"):
                 return os.path.join(dummy_prompt_dir, f"{key}_prompt.txt") # Path that might not exist

            return None

        def get_github_progress_frequency_days(self):
            LOG.debug("[MockSettings] get_github_progress_frequency_days called")
            return 7

        def get_github_subscriptions(self):
            LOG.debug("[MockSettings] get_github_subscriptions called")
            return [
                {"owner": "mockowner1", "repo": "mockrepo1"},
                {"owner": "mockowner2", "repo_name": "mockrepo2"} # Test with "repo_name" too
            ]

    class MockLLM:
        def __init__(self):
            self.model = "mock_model"
        def generate_report(self, system_prompt, user_content):
            LOG.debug(f"[MockLLM] generate_report called. System prompt starts with: '{system_prompt[:50]}...'")
            return f"LLM Summary: {user_content[:150]}..."

    class MockGitHubClient:
        def fetch_commits(self, repo_full_name, since): return [{"sha": "abc1234", "commit": {"message": f"Commit for {repo_full_name}"}, "author": {"login": "dev"}, "html_url": "#"}]
        def fetch_issues(self, repo_full_name, since): return [{"number": 1, "title": f"Issue for {repo_full_name}", "html_url": "#", "user": {"login": "reporter"}}]
        def fetch_pull_requests(self, repo_full_name, since): return [{"number": 2, "title": f"PR for {repo_full_name}", "html_url": "#", "state": "closed", "user": {"login": "merger"}}]
        def get_recent_releases(self, owner, repo_name, days_limit, count_limit=5):
            return [{"name": f"Release for {owner}/{repo_name}", "tag_name": "v1.0", "html_url": "#", "author_login": "releaser", "published_at": datetime.now(timezone.utc).isoformat(), "body": "Release notes."}]

    try:
        settings_mock = MockSettings()
        llm_mock = MockLLM()
        github_client_mock = MockGitHubClient()

        LOG.info("Initializing ReportGenerator with Mocks for full test...")
        report_generator = ReportGenerator(llm=llm_mock, settings=settings_mock, github_client=github_client_mock)
        LOG.info(f"ReportGenerator initialized successfully.")
        LOG.info(f"Loaded report types: {report_generator.report_types}")
        LOG.info(f"Loaded prompts: {report_generator.prompts.keys()}")
        # Check if the github prompt was loaded and others handled
        assert "github" in report_generator.prompts and report_generator.prompts["github"] != "Please summarize the following content:"
        assert "hacker_news_hours_topic" in report_generator.prompts and report_generator.prompts["hacker_news_hours_topic"] == "Please summarize the following content:"
        assert "non_existent_prompt_type" in report_generator.prompts # It will get a default prompt

        # Example of testing _format_releases_markdown (can be uncommented for local testing)
        # LOG.info("Testing _format_releases_markdown...")
        # sample_releases_data = [
        #     {"name": "Awesome Release v1.1", "tag_name": "v1.1", "html_url": "https://example.com/releases/v1.1",
        #      "author_login": "release-guru", "published_at": "2023-10-27T10:00:00Z", "body": "## New Features\n- Feature A\n- Feature B"},
        #     {"name": "Hotfix v1.1.1", "tag_name": "v1.1.1", "html_url": "https://example.com/releases/v1.1.1",
        #      "author_login": "fixer", "published_at": "2023-10-28T15:30:00Z", "body": "Fixed critical bug #123."}
        # ]
        # formatted_md = report_generator._format_releases_markdown(sample_releases_data)
        # LOG.debug("Sample Formatted Releases Markdown:\n" + formatted_md)
        # formatted_empty_md = report_generator._format_releases_markdown([])
        # LOG.debug("Sample Formatted Empty Releases Markdown:\n" + formatted_empty_md)

        # Test generate_github_project_report (requires MockGitHubClient methods to be implemented)
        # LOG.info("Testing generate_github_project_report...")
        # test_owner, test_repo = "testowner", "testrepo"
        # if hasattr(github_client_mock, 'fetch_commits'): # Check if mock methods are ready
        #     project_report_content = report_generator.generate_github_project_report(test_owner, test_repo)
        #     LOG.debug(f"Generated project report for {test_owner}/{test_repo}:\n{project_report_content[:300]}...")
        # else:
        #     LOG.warning("MockGitHubClient methods not fully implemented. Skipping generate_github_project_report test.")


    except Exception as e:
        LOG.error(f"Error in __main__ block during ReportGenerator testing: {e}", exc_info=True)

    LOG.info("ReportGenerator __main__ testing (for __init__ and _preload_prompts) finished.")