import os
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Generator, Union

try:
    from src.core.base_report_generator import BaseReportGenerator
    from src.clients.github_client import GitHubClient
    from src.logger import LOG
except ImportError:
    try:
        from core.base_report_generator import BaseReportGenerator
        from clients.github_client import GitHubClient
        from logger import LOG
    except ImportError:
        import logging
        LOG = logging.getLogger(__name__)
        from base_report_generator import BaseReportGenerator
        from github_client import GitHubClient

class GitHubReportGenerator(BaseReportGenerator):
    """
    GitHub报告生成器
    负责生成与GitHub相关的所有报告
    """
    
    def __init__(self, llm, settings):
        """
        初始化GitHub报告生成器
        
        Args:
            llm: 语言模型实例
            settings: 配置设置实例
        """
        self.llm = llm
        self.settings = settings
        self.prompts = {}
        self._preload_prompts()
        
        # 初始化GitHub客户端
        self.github_client = GitHubClient(
            token=settings.get("github_token"),
            use_cache=settings.get("use_cache", True),
            cache_ttl=settings.get("cache_ttl", 3600)
        )
        
        LOG.info("GitHub报告生成器已初始化")
    
    def _preload_prompts(self):
        """
        预加载提示模板
        """
        LOG.debug("预加载GitHub报告提示模板...")
        self.prompts["repo_summary"] = """
        请根据以下GitHub仓库的信息，生成一个简洁的摘要报告：
        
        仓库名称：{repo}
        
        提交信息：
        {commits}
        
        问题信息：
        {issues}
        
        拉取请求信息：
        {pull_requests}
        
        请包括以下内容：
        1. 最近的主要更新和变化
        2. 活跃的开发领域
        3. 值得关注的问题和PR
        4. 总体发展趋势
        
        请使用中文回答，保持简洁明了。
        """
        
        self.prompts["release_summary"] = """
        请根据以下GitHub仓库的发布信息，生成一个简洁的发布摘要报告：
        
        仓库名称：{repo}
        
        发布信息：
        {releases}
        
        请包括以下内容：
        1. 最新版本的主要特性和改进
        2. 重要的Bug修复
        3. 重大API变化或破坏性更新
        4. 升级建议
        
        请使用中文回答，保持简洁明了。
        """
        
        # 兼容旧代码
        self.prompts["github"] = """
        请根据以下GitHub仓库的信息，生成一个详细的项目进展报告：
        
        {content}
        
        请包括以下内容：
        1. 项目概述
        2. 主要更新和变化
        3. 活跃的开发领域
        4. 值得关注的问题和PR
        5. 总体发展趋势
        
        请使用中文回答，保持简洁明了。
        """
        
        self.prompts["github_digest"] = """
        请根据以下多个GitHub仓库的信息，生成一个综合的技术动态摘要：
        
        {content}
        
        请包括以下内容：
        1. 各项目的主要更新亮点
        2. 共同的技术趋势
        3. 值得关注的重要变化
        
        请使用中文回答，保持简洁明了。
        """
        
        LOG.debug("GitHub提示模板已加载")
    
    def _format_releases_markdown(self, releases: list) -> str:
        """
        将发布版本列表格式化为Markdown字符串
        
        Args:
            releases: 发布版本列表
            
        Returns:
            格式化后的Markdown字符串
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
                formatted_date = datetime.strptime(published_at_str, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")
            except ValueError:
                formatted_date = published_at_str
            
            release_md = (
                f"*   **[{name}]({html_url})** (Tag: `{tag_name}`)\n"
                f"    *发布者: {author_login} 于 {formatted_date}*\n"
            )
            if body and body.strip():
                release_md += (
                    f"    <details>\n"
                    f"    <summary>查看 Release Notes</summary>\n\n"
                    f"    {body.strip()}\n\n"
                    f"    </details>\n"
                )
            release_md += "---\n"
            markdown_parts.append(release_md)
        
        return "\n".join(markdown_parts)
    
    def _generate_github_project_basic_info_markdown(self, owner: str, repo_name: str, days: int) -> str:
        """
        获取并格式化GitHub项目基本信息为Markdown
        
        Args:
            owner: 仓库所有者
            repo_name: 仓库名称
            days: 天数范围
            
        Returns:
            格式化后的Markdown字符串
        """
        repo_full_name = f"{owner}/{repo_name}"
        
        # 计算日期范围
        today = datetime.now(timezone.utc)
        start_date = today - timedelta(days=days-1)
        today_str = today.strftime('%Y-%m-%d')
        start_date_str = start_date.strftime('%Y-%m-%d')
        
        # 确保API的since_date是从start_date的开始
        since_date_dt_for_api = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0, tzinfo=timezone.utc)
        since_date_iso = since_date_dt_for_api.isoformat()
        
        LOG.debug(f"获取{repo_full_name}在{start_date_str}到{today_str}期间的更新 (API 'since': {since_date_iso})")
        
        # 获取数据
        commits = self.github_client.fetch_commits(repo_full_name, since=since_date_iso)
        issues = self.github_client.fetch_issues(repo_full_name, since=since_date_iso)
        pull_requests = self.github_client.fetch_pull_requests(repo_full_name, since=since_date_iso)
        recent_releases = self.github_client.get_recent_releases(owner, repo_name, days_limit=days)
        
        content_parts = [f"## {repo_full_name} 项目更新 (过去 {days} 天: {start_date_str} 至 {today_str})\n"]
        
        # 添加Commits信息
        content_parts.append("### 📝 Commits:\n")
        if commits:
            for commit in commits[:10]:
                commit_sha = commit.get('sha', '')[:7]
                commit_msg = commit.get('commit', {}).get('message', 'No commit message').splitlines()[0]
                author_login = commit.get('author', {}).get('login', 'N/A')
                commit_url = commit.get('html_url', '#')
                content_parts.append(f"- [`{commit_sha}`]({commit_url}) {commit_msg} (by {author_login})")
        else:
            content_parts.append(f"最近 {days} 天内没有 Commits。\n")
        
        # 添加Issues信息
        content_parts.append("\n### 🛠 Issues (Closed):\n")
        if issues:
            for issue in issues[:10]:
                issue_number = issue.get('number')
                issue_title = issue.get('title', 'N/A')
                issue_url = issue.get('html_url', '#')
                closed_by = issue.get('user', {}).get('login', 'N/A')
                content_parts.append(f"- [#{issue_number}]({issue_url}) {issue_title} (User: {closed_by})")
        else:
            content_parts.append(f"最近 {days} 天内没有关闭的 Issues。\n")
        
        # 添加Pull Requests信息
        content_parts.append("\n### ⇄ Pull Requests (Closed/Merged):\n")
        if pull_requests:
            for pr in pull_requests[:10]:
                pr_number = pr.get('number')
                pr_title = pr.get('title', 'N/A')
                pr_url = pr.get('html_url', '#')
                pr_user = pr.get('user', {}).get('login', 'N/A')
                content_parts.append(f"- [#{pr_number}]({pr_url}) {pr_title} (by {pr_user})")
        else:
            content_parts.append(f"最近 {days} 天内没有合并的 Pull Requests。\n")
        
        # 添加Releases信息
        releases_markdown = self._format_releases_markdown(recent_releases)
        content_parts.append(f"\n{releases_markdown}")
        
        return "\n".join(content_parts)
    
    async def _async_generate_github_project_basic_info_markdown(self, owner: str, repo_name: str, days: int) -> str:
        """
        异步获取并格式化GitHub项目基本信息为Markdown
        
        Args:
            owner: 仓库所有者
            repo_name: 仓库名称
            days: 天数范围
            
        Returns:
            格式化后的Markdown字符串
        """
        repo_full_name = f"{owner}/{repo_name}"
        
        # 计算日期范围
        today = datetime.now(timezone.utc)
        start_date = today - timedelta(days=days-1)
        today_str = today.strftime('%Y-%m-%d')
        start_date_str = start_date.strftime('%Y-%m-%d')
        
        # 确保API的since_date是从start_date的开始
        since_date_dt_for_api = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0, tzinfo=timezone.utc)
        since_date_iso = since_date_dt_for_api.isoformat()
        
        LOG.debug(f"异步获取{repo_full_name}在{start_date_str}到{today_str}期间的更新 (API 'since': {since_date_iso})")
        
        # 并行获取数据
        updates_task = self.github_client.async_fetch_updates(repo_full_name, since=since_date_iso)
        releases_task = self.github_client.async_get_recent_releases(owner, repo_name, days_limit=days)
        
        updates, recent_releases = await asyncio.gather(updates_task, releases_task)
        
        commits = updates.get('commits', [])
        issues = updates.get('issues', [])
        pull_requests = updates.get('pull_requests', [])
        
        content_parts = [f"## {repo_full_name} 项目更新 (过去 {days} 天: {start_date_str} 至 {today_str})\n"]
        
        # 添加Commits信息
        content_parts.append("### 📝 Commits:\n")
        if commits:
            for commit in commits[:10]:
                commit_sha = commit.get('sha', '')[:7]
                commit_msg = commit.get('commit', {}).get('message', 'No commit message').splitlines()[0]
                author_login = commit.get('author', {}).get('login', 'N/A')
                commit_url = commit.get('html_url', '#')
                content_parts.append(f"- [`{commit_sha}`]({commit_url}) {commit_msg} (by {author_login})")
        else:
            content_parts.append(f"最近 {days} 天内没有 Commits。\n")
        
        # 添加Issues信息
        content_parts.append("\n### 🛠 Issues (Closed):\n")
        if issues:
            for issue in issues[:10]:
                issue_number = issue.get('number')
                issue_title = issue.get('title', 'N/A')
                issue_url = issue.get('html_url', '#')
                closed_by = issue.get('user', {}).get('login', 'N/A')
                content_parts.append(f"- [#{issue_number}]({issue_url}) {issue_title} (User: {closed_by})")
        else:
            content_parts.append(f"最近 {days} 天内没有关闭的 Issues。\n")
        
        # 添加Pull Requests信息
        content_parts.append("\n### ⇄ Pull Requests (Closed/Merged):\n")
        if pull_requests:
            for pr in pull_requests[:10]:
                pr_number = pr.get('number')
                pr_title = pr.get('title', 'N/A')
                pr_url = pr.get('html_url', '#')
                pr_user = pr.get('user', {}).get('login', 'N/A')
                content_parts.append(f"- [#{pr_number}]({pr_url}) {pr_title} (by {pr_user})")
        else:
            content_parts.append(f"最近 {days} 天内没有合并的 Pull Requests。\n")
        
        # 添加Releases信息
        releases_markdown = self._format_releases_markdown(recent_releases)
        content_parts.append(f"\n{releases_markdown}")
        
        return "\n".join(content_parts)
    
    def generate_report(self, *args, **kwargs) -> Union[str, Generator[str, None, None]]:
        """
        生成报告
        
        支持的参数组合:
        - repo, days: 生成仓库摘要报告
        - owner, repo, days_limit, count_limit: 生成发布摘要报告
        - repos, days: 批量生成多个仓库的摘要报告
        
        Returns:
            生成的报告内容
        """
        if 'repos' in kwargs:
            # 批量生成多个仓库的摘要报告
            repos = kwargs.get('repos')
            days = kwargs.get('days', 7)
            return self.generate_batch_repo_summaries(repos, days)
        elif 'owner' in kwargs and 'repo' in kwargs:
            # 生成发布摘要报告
            owner = kwargs.get('owner')
            repo = kwargs.get('repo')
            days_limit = kwargs.get('days_limit', 30)
            count_limit = kwargs.get('count_limit', 5)
            return self.generate_release_summary(owner, repo, days_limit, count_limit)
        elif 'repo' in kwargs:
            # 生成仓库摘要报告
            repo = kwargs.get('repo')
            days = kwargs.get('days', 7)
            return self.generate_repo_summary(repo, days)
        else:
            LOG.error("生成报告时缺少必要参数")
            raise ValueError("生成报告时缺少必要参数")
            
    def generate_repo_summary(self, repo: str, days: int = 7) -> str:
        """
        生成仓库摘要报告
        
        Args:
            repo: 仓库名称 (格式: owner/repo)
            days: 过去多少天的数据
            
        Returns:
            生成的报告内容
        """
        LOG.info(f"开始生成GitHub仓库 {repo} 的摘要报告 (过去 {days} 天)")
        
        try:
            # 解析仓库名称
            owner, repo_name = repo.split('/')
            
            # 获取项目基本信息
            project_info_markdown = self._generate_github_project_basic_info_markdown(owner, repo_name, days)
            
            # 使用LLM生成报告
            prompt = self.prompts["repo_summary"].format(
                repo=repo,
                commits=project_info_markdown,
                issues="",
                pull_requests=""
            )
            
            summary = self.llm.generate_text(prompt)
            
            LOG.info(f"GitHub仓库 {repo} 的摘要报告生成完成")
            return summary
        except Exception as e:
            LOG.error(f"生成GitHub仓库 {repo} 的摘要报告时发生错误: {e}")
            return f"生成报告时发生错误: {e}"
    
    async def async_generate_repo_summary(self, repo: str, days: int = 7) -> str:
        """
        异步生成仓库摘要报告
        
        Args:
            repo: 仓库名称 (格式: owner/repo)
            days: 过去多少天的数据
            
        Returns:
            生成的报告内容
        """
        LOG.info(f"开始异步生成GitHub仓库 {repo} 的摘要报告 (过去 {days} 天)")
        
        try:
            # 解析仓库名称
            owner, repo_name = repo.split('/')
            
            # 异步获取项目基本信息
            project_info_markdown = await self._async_generate_github_project_basic_info_markdown(owner, repo_name, days)
            
            # 使用LLM生成报告
            prompt = self.prompts["repo_summary"].format(
                repo=repo,
                commits=project_info_markdown,
                issues="",
                pull_requests=""
            )
            
            summary = await self.llm.async_generate_text(prompt)
            
            LOG.info(f"GitHub仓库 {repo} 的摘要报告异步生成完成")
            return summary
        except Exception as e:
            LOG.error(f"异步生成GitHub仓库 {repo} 的摘要报告时发生错误: {e}")
            return f"生成报告时发生错误: {e}"
    
    def generate_release_summary(self, owner: str, repo: str, days_limit: int = 30, count_limit: int = 5) -> str:
        """
        生成发布摘要报告
        
        Args:
            owner: 仓库所有者
            repo: 仓库名称
            days_limit: 过去多少天的数据
            count_limit: 最多包含多少个发布
            
        Returns:
            生成的报告内容
        """
        LOG.info(f"开始生成 {owner}/{repo} 的发布摘要报告")
        
        # 获取最近的发布
        releases = self.github_client.get_recent_releases(
            owner=owner,
            repo_name=repo,
            days_limit=days_limit,
            count_limit=count_limit
        )
        
        if not releases:
            LOG.warning(f"{owner}/{repo} 在过去 {days_limit} 天内没有发布")
            return f"{owner}/{repo} 在过去 {days_limit} 天内没有发布"
        
        # 格式化发布信息
        releases_text = ""
        for release in releases:
            releases_text += f"版本: {release['tag_name']}\n"
            releases_text += f"名称: {release['name']}\n"
            releases_text += f"发布时间: {release['published_at']}\n"
            releases_text += f"链接: {release['html_url']}\n"
            releases_text += f"内容: {release['body']}\n\n"
        
        # 使用LLM生成摘要
        prompt = self.prompts["release_summary"].format(
            repo=f"{owner}/{repo}",
            releases=releases_text
        )
        
        summary = self.llm.generate_text(prompt)
        
        LOG.info(f"{owner}/{repo} 的发布摘要报告生成完成")
        return summary
    
    async def async_generate_release_summary(self, owner: str, repo: str, days_limit: int = 30, count_limit: int = 5) -> str:
        """
        异步生成发布摘要报告
        
        Args:
            owner: 仓库所有者
            repo: 仓库名称
            days_limit: 过去多少天的数据
            count_limit: 最多包含多少个发布
            
        Returns:
            生成的报告内容
        """
        LOG.info(f"开始异步生成 {owner}/{repo} 的发布摘要报告")
        
        # 异步获取最近的发布
        releases = await self.github_client.async_get_recent_releases(
            owner=owner,
            repo_name=repo,
            days_limit=days_limit,
            count_limit=count_limit
        )
        
        if not releases:
            LOG.warning(f"{owner}/{repo} 在过去 {days_limit} 天内没有发布")
            return f"{owner}/{repo} 在过去 {days_limit} 天内没有发布"
        
        # 格式化发布信息
        releases_text = ""
        for release in releases:
            releases_text += f"版本: {release['tag_name']}\n"
            releases_text += f"名称: {release['name']}\n"
            releases_text += f"发布时间: {release['published_at']}\n"
            releases_text += f"链接: {release['html_url']}\n"
            releases_text += f"内容: {release['body']}\n\n"
        
        # 使用LLM生成摘要
        prompt = self.prompts["release_summary"].format(
            repo=f"{owner}/{repo}",
            releases=releases_text
        )
        
        summary = await self.llm.async_generate_text(prompt)
        
        LOG.info(f"{owner}/{repo} 的发布摘要报告异步生成完成")
        return summary
    
    def generate_batch_repo_summaries(self, repos: List[str], days: int = 7) -> Dict[str, str]:
        """
        批量生成多个仓库的摘要报告
        
        Args:
            repos: 仓库名称列表
            days: 过去多少天的数据
            
        Returns:
            字典，键为仓库名称，值为生成的报告内容
        """
        LOG.info(f"开始批量生成 {len(repos)} 个GitHub仓库的摘要报告")
        
        summaries = {}
        for repo in repos:
            try:
                summary = self.generate_repo_summary(repo, days)
                summaries[repo] = summary
            except Exception as e:
                LOG.error(f"生成 {repo} 的摘要报告时出错: {e}")
                summaries[repo] = f"生成报告时出错: {e}"
        
        LOG.info(f"批量生成 {len(repos)} 个GitHub仓库的摘要报告完成")
        return summaries
    
    async def async_generate_batch_repo_summaries(self, repos: List[str], days: int = 7) -> Dict[str, str]:
        """
        异步批量生成多个仓库的摘要报告
        
        Args:
            repos: 仓库名称列表
            days: 过去多少天的数据
            
        Returns:
            字典，键为仓库名称，值为生成的报告内容
        """
        LOG.info(f"开始异步批量生成 {len(repos)} 个GitHub仓库的摘要报告")
        
        tasks = []
        for repo in repos:
            task = self.async_generate_repo_summary(repo, days)
            tasks.append((repo, task))
        
        summaries = {}
        for repo, task in tasks:
            try:
                summary = await task
                summaries[repo] = summary
            except Exception as e:
                LOG.error(f"异步生成 {repo} 的摘要报告时出错: {e}")
                summaries[repo] = f"生成报告时出错: {e}"
        
        LOG.info(f"异步批量生成 {len(repos)} 个GitHub仓库的摘要报告完成")
        return summaries
    
    def get_consolidated_github_report(self, days: int = 1) -> Generator[str, None, None]:
        """
        获取合并的GitHub报告，包含所有订阅仓库的更新
        
        Args:
            days: 天数范围，默认为1天
            
        Returns:
            合并报告内容（生成器）
        """
        LOG.info(f"生成合并的GitHub报告，过去 {days} 天")
        
        # 获取订阅的仓库列表
        subscriptions = self.settings.get_github_subscriptions()
        if not subscriptions:
            yield "没有订阅的GitHub仓库。请先添加订阅。"
            return
        
        # 收集所有仓库的基本信息
        all_repos_info = []
        for sub in subscriptions:
            repo_url = sub.get('repo_url')
            if not repo_url:
                continue
            
            try:
                owner, repo_name = repo_url.split('/')
                repo_info = self._generate_github_project_basic_info_markdown(owner, repo_name, days)
                all_repos_info.append(repo_info)
            except Exception as e:
                LOG.error(f"获取仓库 {repo_url} 的信息时发生错误: {e}", exc_info=True)
                all_repos_info.append(f"## {repo_url}\n\n获取信息时发生错误: {e}\n")
        
        if not all_repos_info:
            yield "无法获取任何订阅仓库的信息。"
            return
        
        # 合并所有仓库信息
        combined_info = "\n\n".join(all_repos_info)
        
        # 使用LLM生成合并报告
        system_prompt = self.prompts.get("github_digest", "请总结以下多个GitHub项目的更新内容，并按项目分类整理:")
        
        # 返回生成的报告
        yield from self.llm.generate_report(system_prompt, combined_info)
    
    async def async_get_consolidated_github_report(self, days: int = 1) -> Generator[str, None, None]:
        """
        异步获取合并的GitHub报告，包含所有订阅仓库的更新
        
        Args:
            days: 天数范围，默认为1天
            
        Returns:
            合并报告内容（生成器）
        """
        LOG.info(f"异步生成合并的GitHub报告，过去 {days} 天")
        
        # 获取订阅的仓库列表
        subscriptions = self.settings.get_github_subscriptions()
        if not subscriptions:
            yield "没有订阅的GitHub仓库。请先添加订阅。"
            return
        
        # 准备仓库列表
        repos = []
        for sub in subscriptions:
            repo_url = sub.get('repo_url')
            if repo_url:
                repos.append(repo_url)
        
        if not repos:
            yield "没有有效的订阅仓库。"
            return
        
        # 批量获取仓库信息
        tasks = []
        for repo in repos:
            try:
                owner, repo_name = repo.split('/')
                task = self._async_generate_github_project_basic_info_markdown(owner, repo_name, days)
                tasks.append(task)
            except ValueError:
                LOG.error(f"无效的仓库格式: {repo}")
                tasks.append(asyncio.create_task(asyncio.sleep(0)))  # 添加一个空任务作为占位符
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 收集有效的仓库信息
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                LOG.error(f"获取仓库 {repos[i]} 的信息时发生错误: {result}")
                valid_results.append(f"## {repos[i]}\n\n获取信息时发生错误: {result}\n")
            elif isinstance(result, str):
                valid_results.append(result)
        
        if not valid_results:
            yield "无法获取任何订阅仓库的信息。"
            return
        
        # 合并所有仓库信息
        combined_info = "\n\n".join(valid_results)
        
        # 使用LLM生成合并报告
        system_prompt = self.prompts.get("github_digest", "请总结以下多个GitHub项目的更新内容，并按项目分类整理:")
        
        # 异步函数中不能使用yield from，需要手动迭代
        for chunk in self.llm.generate_report(system_prompt, combined_info):
            yield chunk 