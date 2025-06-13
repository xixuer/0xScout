# src/clients/github_client.py

import requests  # 导入requests库用于HTTP请求
import aiohttp   # 导入aiohttp库用于异步HTTP请求
import asyncio   # 导入asyncio库用于异步编程
from datetime import datetime, date, timedelta, timezone  # 导入日期处理模块, 添加timezone
import os  # 导入os模块用于文件和目录操作
import json # Added for json.JSONDecodeError handling in get_recent_releases
from typing import Dict, List, Any, Optional, Union

# 导入缓存管理器和日志
try:
    from src.utils.cache_manager import CacheManager
    from src.logger import LOG
except ImportError:
    try:
        from utils.cache_manager import CacheManager
        from logger import LOG
    except ImportError:
        import logging
        LOG = logging.getLogger(__name__)
        LOG.error("无法导入CacheManager，将不使用缓存功能")
        CacheManager = None

class GitHubClient:
    def __init__(self, token, use_cache=True, cache_ttl=3600):
        self.token = token  # GitHub API令牌
        self.headers = {'Authorization': f'token {self.token}'}  # 设置HTTP头部认证信息
        
        # 初始化缓存管理器
        self.use_cache = use_cache and CacheManager is not None
        if self.use_cache:
            self.cache = CacheManager(cache_dir="cache/github", default_ttl=cache_ttl)
            LOG.info("已启用GitHub API缓存")
        else:
            self.cache = None
            LOG.info("未启用GitHub API缓存")

    def fetch_updates(self, repo, since=None, until=None):
        # 获取指定仓库的更新，可以指定开始和结束日期
        updates = {
            'commits': self.fetch_commits(repo, since, until),  # 获取提交记录
            'issues': self.fetch_issues(repo, since, until),  # 获取问题
            'pull_requests': self.fetch_pull_requests(repo, since, until)  # 获取拉取请求
        }
        return updates
    
    async def async_fetch_updates(self, repo, since=None, until=None):
        """
        异步获取指定仓库的更新
        
        Args:
            repo: 仓库名称 (格式: owner/repo)
            since: 开始日期
            until: 结束日期
            
        Returns:
            包含commits, issues, pull_requests的字典
        """
        # 使用asyncio.gather并行执行多个异步任务
        commits_task = self.async_fetch_commits(repo, since, until)
        issues_task = self.async_fetch_issues(repo, since, until)
        prs_task = self.async_fetch_pull_requests(repo, since, until)
        
        # 等待所有任务完成
        commits, issues, prs = await asyncio.gather(
            commits_task, issues_task, prs_task
        )
        
        return {
            'commits': commits,
            'issues': issues,
            'pull_requests': prs
        }

    def fetch_commits(self, repo, since=None, until=None):
        LOG.debug(f"准备获取 {repo} 的 Commits")
        
        # 检查缓存
        cache_key = f"commits_{repo}_{since}_{until}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        url = f'https://api.github.com/repos/{repo}/commits'  # 构建获取提交的API URL
        params = {}
        if since:
            params['since'] = since  # 如果指定了开始日期，添加到参数中
        if until:
            params['until'] = until  # 如果指定了结束日期，添加到参数中

        response = None # Initialize response to None for broader scope in except block
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()  # 检查请求是否成功
            result = response.json()
            
            # 缓存结果
            if self.use_cache:
                self.cache.set(cache_key, result)
                
            return result  # 返回JSON格式的数据
        except Exception as e:
            LOG.error(f"从 {repo} 获取 Commits 失败：{str(e)}")
            if response is not None:
                 LOG.error(f"响应详情：{response.text}")
            else:
                 LOG.error("无响应数据可用")
            return []  # Handle failure case
    
    async def async_fetch_commits(self, repo, since=None, until=None):
        """异步获取提交记录"""
        LOG.debug(f"准备异步获取 {repo} 的 Commits")
        
        # 检查缓存
        cache_key = f"commits_{repo}_{since}_{until}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        url = f'https://api.github.com/repos/{repo}/commits'
        params = {}
        if since:
            params['since'] = since
        if until:
            params['until'] = until
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params, timeout=10) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # 缓存结果
                        if self.use_cache:
                            self.cache.set(cache_key, result)
                            
                        return result
                    else:
                        error_text = await response.text()
                        LOG.error(f"从 {repo} 异步获取 Commits 失败，状态码: {response.status}, 响应: {error_text}")
                        return []
        except Exception as e:
            LOG.error(f"从 {repo} 异步获取 Commits 时发生异常: {str(e)}")
            return []

    def fetch_issues(self, repo, since=None, until=None):
        LOG.debug(f"准备获取 {repo} 的 Issues。")
        
        # 检查缓存
        cache_key = f"issues_{repo}_{since}_{until}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        url = f'https://api.github.com/repos/{repo}/issues'  # 构建获取问题的API URL
        params = {'state': 'closed', 'since': since, 'until': until} # Consider making 'state' a parameter
        response = None
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            # 缓存结果
            if self.use_cache:
                self.cache.set(cache_key, result)
                
            return result
        except Exception as e:
            LOG.error(f"从 {repo} 获取 Issues 失败：{str(e)}")
            if response is not None:
                 LOG.error(f"响应详情：{response.text}")
            else:
                 LOG.error("无响应数据可用")
            return []
    
    async def async_fetch_issues(self, repo, since=None, until=None):
        """异步获取问题"""
        LOG.debug(f"准备异步获取 {repo} 的 Issues")
        
        # 检查缓存
        cache_key = f"issues_{repo}_{since}_{until}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        url = f'https://api.github.com/repos/{repo}/issues'
        params = {'state': 'closed', 'since': since, 'until': until}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params, timeout=10) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # 缓存结果
                        if self.use_cache:
                            self.cache.set(cache_key, result)
                            
                        return result
                    else:
                        error_text = await response.text()
                        LOG.error(f"从 {repo} 异步获取 Issues 失败，状态码: {response.status}, 响应: {error_text}")
                        return []
        except Exception as e:
            LOG.error(f"从 {repo} 异步获取 Issues 时发生异常: {str(e)}")
            return []

    def fetch_pull_requests(self, repo, since=None, until=None):
        LOG.debug(f"准备获取 {repo} 的 Pull Requests。")
        
        # 检查缓存
        cache_key = f"prs_{repo}_{since}_{until}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        url = f'https://api.github.com/repos/{repo}/pulls'  # 构建获取拉取请求的API URL
        params = {'state': 'closed', 'since': since, 'until': until} # Consider making 'state' a parameter
        response = None
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()  # 确保成功响应
            result = response.json()
            
            # 缓存结果
            if self.use_cache:
                self.cache.set(cache_key, result)
                
            return result
        except Exception as e:
            LOG.error(f"从 {repo} 获取 Pull Requests 失败：{str(e)}")
            if response is not None:
                 LOG.error(f"响应详情：{response.text}")
            else:
                 LOG.error("无响应数据可用")
            return []
    
    async def async_fetch_pull_requests(self, repo, since=None, until=None):
        """异步获取拉取请求"""
        LOG.debug(f"准备异步获取 {repo} 的 Pull Requests")
        
        # 检查缓存
        cache_key = f"prs_{repo}_{since}_{until}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        url = f'https://api.github.com/repos/{repo}/pulls'
        params = {'state': 'closed', 'since': since, 'until': until}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params, timeout=10) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # 缓存结果
                        if self.use_cache:
                            self.cache.set(cache_key, result)
                            
                        return result
                    else:
                        error_text = await response.text()
                        LOG.error(f"从 {repo} 异步获取 Pull Requests 失败，状态码: {response.status}, 响应: {error_text}")
                        return []
        except Exception as e:
            LOG.error(f"从 {repo} 异步获取 Pull Requests 时发生异常: {str(e)}")
            return []

    def get_recent_releases(self, owner: str, repo_name: str, days_limit: int = 7, count_limit: int = 5):
        """
        Fetches recent releases for a given repository.

        Args:
            owner: The owner of the repository.
            repo_name: The name of the repository.
            days_limit: How many days back to look for releases.
            count_limit: Maximum number of releases to return.

        Returns:
            A list of dictionaries, where each dictionary contains details of a release.
            Returns an empty list if an error occurs or no releases are found.
        """
        repo_full_name = f"{owner}/{repo_name}"
        LOG.debug(f"准备获取 {repo_full_name} 的最新 Releases (最近 {days_limit} 天, 最多 {count_limit} 条)")
        
        # 检查缓存
        cache_key = f"releases_{owner}_{repo_name}_{days_limit}_{count_limit}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        url = f"https://api.github.com/repos/{owner}/{repo_name}/releases"

        response = None
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()  # Check for HTTP errors
            releases_data = response.json()
        except requests.exceptions.RequestException as e:
            LOG.error(f"从 {repo_full_name} 获取 Releases API 请求失败: {e}")
            if response is not None and hasattr(response, 'text'):
                 LOG.error(f"响应详情：{response.text}")
            else:
                 LOG.error("无响应数据可用")
            return []
        except json.JSONDecodeError as e: # Ensure json is imported for this
            LOG.error(f"从 {repo_full_name} 获取 Releases API 响应 JSON 解析失败: {e}")
            if response is not None and hasattr(response, 'text'):
                 LOG.error(f"响应内容: {response.text}")
            else:
                 LOG.error("无响应数据可用")
            return []


        if not releases_data:
            LOG.info(f"{repo_full_name} 没有找到任何 Releases。")
            return []

        recent_releases = []
        limit_date = datetime.now(timezone.utc) - timedelta(days=days_limit)

        for release in releases_data:
            try:
                published_at_str = release.get("published_at")
                if not published_at_str:
                    LOG.warning(f"Release '{release.get('name', 'N/A')}' for {repo_full_name} has no 'published_at' date. Skipping.")
                    continue

                release_date = datetime.strptime(published_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

                if release_date >= limit_date:
                    recent_releases.append({
                        "name": release.get("name"),
                        "tag_name": release.get("tag_name"),
                        "published_at": published_at_str,
                        "html_url": release.get("html_url"),
                        "body": release.get("body"),
                        "author_login": release.get("author", {}).get("login")
                    })
            except Exception as e:
                LOG.error(f"解析 Release '{release.get('name', 'N/A')}' for {repo_full_name} 时出错: {e}")
                continue

        recent_releases.sort(key=lambda r: r["published_at"], reverse=True)

        if len(recent_releases) > count_limit:
            LOG.debug(f"对 {repo_full_name} 的 Releases 应用数量限制，从 {len(recent_releases)} 条到 {count_limit} 条。")
            recent_releases = recent_releases[:count_limit]

        if not recent_releases:
            LOG.info(f"{repo_full_name} 在过去 {days_limit} 天内没有符合条件的 Releases。")
        
        # 缓存结果
        if self.use_cache:
            self.cache.set(cache_key, recent_releases)
        
        return recent_releases
    
    async def async_get_recent_releases(self, owner: str, repo_name: str, days_limit: int = 7, count_limit: int = 5):
        """异步获取最近的发布版本"""
        repo_full_name = f"{owner}/{repo_name}"
        LOG.debug(f"准备异步获取 {repo_full_name} 的最新 Releases (最近 {days_limit} 天, 最多 {count_limit} 条)")
        
        # 检查缓存
        cache_key = f"releases_{owner}_{repo_name}_{days_limit}_{count_limit}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        url = f"https://api.github.com/repos/{owner}/{repo_name}/releases"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=10) as response:
                    if response.status == 200:
                        releases_data = await response.json()
                    else:
                        error_text = await response.text()
                        LOG.error(f"从 {repo_full_name} 异步获取 Releases 失败，状态码: {response.status}, 响应: {error_text}")
                        return []
        except Exception as e:
            LOG.error(f"从 {repo_full_name} 异步获取 Releases 时发生异常: {str(e)}")
            return []
        
        if not releases_data:
            LOG.info(f"{repo_full_name} 没有找到任何 Releases。")
            return []
        
        recent_releases = []
        limit_date = datetime.now(timezone.utc) - timedelta(days=days_limit)
        
        for release in releases_data:
            try:
                published_at_str = release.get("published_at")
                if not published_at_str:
                    LOG.warning(f"Release '{release.get('name', 'N/A')}' for {repo_full_name} has no 'published_at' date. Skipping.")
                    continue
                
                release_date = datetime.strptime(published_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                
                if release_date >= limit_date:
                    recent_releases.append({
                        "name": release.get("name"),
                        "tag_name": release.get("tag_name"),
                        "published_at": published_at_str,
                        "html_url": release.get("html_url"),
                        "body": release.get("body"),
                        "author_login": release.get("author", {}).get("login")
                    })
            except Exception as e:
                LOG.error(f"解析 Release '{release.get('name', 'N/A')}' for {repo_full_name} 时出错: {e}")
                continue
        
        recent_releases.sort(key=lambda r: r["published_at"], reverse=True)
        
        if len(recent_releases) > count_limit:
            LOG.debug(f"对 {repo_full_name} 的 Releases 应用数量限制，从 {len(recent_releases)} 条到 {count_limit} 条。")
            recent_releases = recent_releases[:count_limit]
        
        if not recent_releases:
            LOG.info(f"{repo_full_name} 在过去 {days_limit} 天内没有符合条件的 Releases。")
        
        # 缓存结果
        if self.use_cache:
            self.cache.set(cache_key, recent_releases)
        
        return recent_releases

    def export_daily_progress(self, repo):
        LOG.debug(f"[准备导出项目进度]：{repo}")
        today_iso = datetime.now(timezone.utc).date().isoformat() # Use UTC for consistency
        # To align with 'since' which is typically a full timestamp for precision,
        # let's use beginning of today UTC for 'since'.
        # However, GitHub API 'since' for commits can be just a date.
        # Let's keep it simple as date string, assuming API handles it inclusively.
        # If more precision is needed, use: (datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)).isoformat()

        updates = self.fetch_updates(repo, since=today_iso)
        
        repo_dir = os.path.join('daily_progress', repo.replace("/", "_"))
        os.makedirs(repo_dir, exist_ok=True)
        
        file_path = os.path.join(repo_dir, f'{today_iso}.md')
        with open(file_path, 'w', encoding='utf-8') as file: # Specify encoding
            file.write(f"# Daily Progress for {repo} ({today_iso})\n\n")
            file.write("\n## Issues Closed Today\n")
            if updates.get('issues'):
                for issue in updates['issues']:
                    file.write(f"- [{issue.get('title', 'N/A')} #{issue.get('number', 'N/A')}]({issue.get('html_url', '#')})\n")
            else:
                file.write("No issues closed today.\n")
        
        LOG.info(f"[{repo}]项目每日进展文件生成： {file_path}")
        return file_path

    def export_progress_by_date_range(self, repo, days):
        today = datetime.now(timezone.utc).date()
        since_date = today - timedelta(days=days)
        
        today_iso = today.isoformat()
        since_date_iso = since_date.isoformat()

        updates = self.fetch_updates(repo, since=since_date_iso, until=today_iso)
        
        repo_dir = os.path.join('daily_progress', repo.replace("/", "_"))
        os.makedirs(repo_dir, exist_ok=True)
        
        date_str = f"{since_date_iso}_to_{today_iso}"
        file_path = os.path.join(repo_dir, f'{date_str}.md')
        
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(f"# Progress for {repo} ({date_str})\n\n")
            
            file.write("\n## Commits\n")
            if updates.get('commits'):
                for commit in updates['commits']:
                    sha = commit.get('sha', 'N/A')[:7]
                    message = commit.get('commit', {}).get('message', 'N/A').splitlines()[0]
                    file.write(f"- [{sha}]({commit.get('html_url', '#')}) {message}\n")
            else:
                file.write("No commits in this period.\n")
            
            file.write("\n## Issues Closed\n")
            if updates.get('issues'):
                for issue in updates['issues']:
                    file.write(f"- [{issue.get('title', 'N/A')} #{issue.get('number', 'N/A')}]({issue.get('html_url', '#')})\n")
            else:
                file.write("No issues closed in this period.\n")
            
            file.write("\n## Pull Requests Merged\n")
            if updates.get('pull_requests'):
                for pr in updates['pull_requests']:
                    file.write(f"- [{pr.get('title', 'N/A')} #{pr.get('number', 'N/A')}]({pr.get('html_url', '#')})\n")
            else:
                file.write("No pull requests merged in this period.\n")
        
        LOG.info(f"[{repo}]项目进展文件生成： {file_path}")
        return file_path
    
    async def async_export_progress_by_date_range(self, repo, days):
        """异步导出指定日期范围的项目进展"""
        today = datetime.now(timezone.utc).date()
        since_date = today - timedelta(days=days)
        
        today_iso = today.isoformat()
        since_date_iso = since_date.isoformat()
        
        updates = await self.async_fetch_updates(repo, since=since_date_iso, until=today_iso)
        
        repo_dir = os.path.join('daily_progress', repo.replace("/", "_"))
        os.makedirs(repo_dir, exist_ok=True)
        
        date_str = f"{since_date_iso}_to_{today_iso}"
        file_path = os.path.join(repo_dir, f'{date_str}.md')
        
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(f"# Progress for {repo} ({date_str})\n\n")
            
            file.write("\n## Commits\n")
            if updates.get('commits'):
                for commit in updates['commits']:
                    sha = commit.get('sha', 'N/A')[:7]
                    message = commit.get('commit', {}).get('message', 'N/A').splitlines()[0]
                    file.write(f"- [{sha}]({commit.get('html_url', '#')}) {message}\n")
            else:
                file.write("No commits in this period.\n")
            
            file.write("\n## Issues Closed\n")
            if updates.get('issues'):
                for issue in updates['issues']:
                    file.write(f"- [{issue.get('title', 'N/A')} #{issue.get('number', 'N/A')}]({issue.get('html_url', '#')})\n")
            else:
                file.write("No issues closed in this period.\n")
            
            file.write("\n## Pull Requests Merged\n")
            if updates.get('pull_requests'):
                for pr in updates['pull_requests']:
                    file.write(f"- [{pr.get('title', 'N/A')} #{pr.get('number', 'N/A')}]({pr.get('html_url', '#')})\n")
            else:
                file.write("No pull requests merged in this period.\n")
        
        LOG.info(f"[{repo}]项目进展文件异步生成： {file_path}")
        return file_path
    
    async def async_batch_fetch_updates(self, repos, since=None, until=None):
        """
        批量异步获取多个仓库的更新
        
        Args:
            repos: 仓库名称列表 (格式: ["owner1/repo1", "owner2/repo2", ...])
            since: 开始日期
            until: 结束日期
            
        Returns:
            字典，键为仓库名称，值为包含commits, issues, pull_requests的字典
        """
        LOG.info(f"批量异步获取 {len(repos)} 个仓库的更新")
        
        tasks = []
        for repo in repos:
            task = self.async_fetch_updates(repo, since, until)
            tasks.append(task)
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        updates_by_repo = {}
        for i, result in enumerate(results):
            repo = repos[i]
            if isinstance(result, Exception):
                LOG.error(f"获取仓库 {repo} 的更新时发生错误: {result}")
                updates_by_repo[repo] = {
                    'commits': [],
                    'issues': [],
                    'pull_requests': []
                }
            else:
                updates_by_repo[repo] = result
        
        return updates_by_repo
