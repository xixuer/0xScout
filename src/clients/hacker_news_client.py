import requests  # 导入requests库用于HTTP请求
import aiohttp   # 导入aiohttp库用于异步HTTP请求
import asyncio
import time
from bs4 import BeautifulSoup  # 导入BeautifulSoup库用于解析HTML内容
from datetime import datetime  # 导入datetime模块用于获取日期和时间
import os  # 导入os模块用于文件和目录操作
from typing import List, Dict, Any, Optional, Union
import traceback
import json

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

import httpx

# 运行时导入topic_analyzer，避免还没安装依赖时就出错
# from src.analyzers.topic_analyzer import HackerNewsTopicAnalyzer

try:
    from src.llm import LLM
    from src.config import Settings
except ImportError:
    LOG.warning("未能导入LLM或Settings模块，AI总结功能将不可用")

class HackerNewsClient:
    """
    HackerNews API客户端
    用于获取HackerNews上的热门文章、评论等信息
    """
    
    def __init__(self, use_cache=True, cache_ttl=3600):
        """
        初始化HackerNews客户端
        
        Args:
            use_cache: 是否使用缓存
            cache_ttl: 缓存有效期（秒）
        """
        self.base_url = "https://hacker-news.firebaseio.com/v0"
        
        # 初始化缓存管理器
        self.use_cache = use_cache and CacheManager is not None
        if self.use_cache:
            self.cache = CacheManager(cache_dir="cache/hackernews", default_ttl=cache_ttl)
            LOG.info("已启用HackerNews API缓存")
        else:
            self.cache = None
            LOG.info("未启用HackerNews API缓存")
    
    def get_top_stories(self, limit=30) -> List[int]:
        """
        获取热门文章ID列表
        
        Args:
            limit: 返回的文章数量上限
            
        Returns:
            文章ID列表
        """
        LOG.debug(f"获取HackerNews热门文章ID列表，限制为{limit}条")
        
        # 检查缓存
        cache_key = f"top_stories_{limit}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        url = f"{self.base_url}/topstories.json"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            story_ids = response.json()
            
            # 限制返回数量
            if limit and len(story_ids) > limit:
                story_ids = story_ids[:limit]
            
            # 缓存结果
            if self.use_cache:
                # 热门文章变化较快，使用较短的缓存时间
                self.cache.set(cache_key, story_ids, ttl=600)  # 10分钟
            
            return story_ids
        except Exception as e:
            LOG.error(f"获取HackerNews热门文章ID列表失败：{e}")
            return []
    
    async def async_get_top_stories(self, limit=30) -> List[int]:
        """
        异步获取热门文章ID列表
        
        Args:
            limit: 返回的文章数量上限
            
        Returns:
            文章ID列表
        """
        LOG.debug(f"异步获取HackerNews热门文章ID列表，限制为{limit}条")
        
        # 检查缓存
        cache_key = f"top_stories_{limit}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        url = f"{self.base_url}/topstories.json"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        story_ids = await response.json()
                        
                        # 限制返回数量
                        if limit and len(story_ids) > limit:
                            story_ids = story_ids[:limit]
                        
                        # 缓存结果
                        if self.use_cache:
                            # 热门文章变化较快，使用较短的缓存时间
                            self.cache.set(cache_key, story_ids, ttl=600)  # 10分钟
                        
                        return story_ids
                    else:
                        error_text = await response.text()
                        LOG.error(f"异步获取HackerNews热门文章ID列表失败，状态码: {response.status}, 响应: {error_text}")
                        return []
        except Exception as e:
            LOG.error(f"异步获取HackerNews热门文章ID列表时发生异常: {e}")
            return []
    
    def get_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        """
        获取指定ID的项目（文章、评论等）详情
        
        Args:
            item_id: 项目ID
            
        Returns:
            项目详情字典，如果获取失败则返回None
        """
        LOG.debug(f"获取HackerNews项目详情，ID: {item_id}")
        
        # 检查缓存
        cache_key = f"item_{item_id}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        url = f"{self.base_url}/item/{item_id}.json"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            item_data = response.json()
            
            # 缓存结果
            if self.use_cache:
                # 文章内容相对稳定，可以使用较长的缓存时间
                self.cache.set(cache_key, item_data)
            
            return item_data
        except Exception as e:
            LOG.error(f"获取HackerNews项目详情失败，ID: {item_id}, 错误: {e}")
            return None
    
    async def async_get_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        """
        异步获取指定ID的项目（文章、评论等）详情
        
        Args:
            item_id: 项目ID
            
        Returns:
            项目详情字典，如果获取失败则返回None
        """
        LOG.debug(f"异步获取HackerNews项目详情，ID: {item_id}")
        
        # 检查缓存
        cache_key = f"item_{item_id}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        url = f"{self.base_url}/item/{item_id}.json"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        item_data = await response.json()
                        
                        # 缓存结果
                        if self.use_cache:
                            # 文章内容相对稳定，可以使用较长的缓存时间
                            self.cache.set(cache_key, item_data)
                        
                        return item_data
                    else:
                        error_text = await response.text()
                        LOG.error(f"异步获取HackerNews项目详情失败，ID: {item_id}, 状态码: {response.status}, 响应: {error_text}")
                        return None
        except Exception as e:
            LOG.error(f"异步获取HackerNews项目详情时发生异常，ID: {item_id}, 错误: {e}")
            return None
    
    def get_top_stories_details(self, limit=30) -> List[Dict[str, Any]]:
        """
        获取热门文章详情列表
        
        Args:
            limit: 返回的文章数量上限
            
        Returns:
            热门文章详情列表
        """
        LOG.debug(f"获取HackerNews热门文章详情，限制为{limit}条")
        
        # 检查缓存
        cache_key = f"top_stories_details_{limit}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        # 获取热门文章ID列表
        story_ids = self.get_top_stories(limit)
        
        # 获取每篇文章的详情
        stories = []
        for story_id in story_ids:
            story = self.get_item(story_id)
            if story:
                stories.append(story)
        
        # 缓存结果
        if self.use_cache:
            # 文章详情变化较快，使用较短的缓存时间
            self.cache.set(cache_key, stories, ttl=600)  # 10分钟
        
        return stories
    
    def fetch_top_stories(self, limit=30) -> List[Dict[str, Any]]:
        """
        获取热门文章列表 (兼容性方法，内部调用 get_top_stories_details)
        
        Args:
            limit: 返回的文章数量上限
            
        Returns:
            热门文章详情列表
        """
        LOG.debug("准备获取Hacker News的热门新闻。")
        return self.get_top_stories_details(limit=limit)
    
    async def async_get_top_stories_details(self, limit=30) -> List[Dict[str, Any]]:
        """
        异步获取热门文章的详细信息
        
        Args:
            limit: 返回的文章数量上限
            
        Returns:
            文章详情列表
        """
        LOG.debug(f"异步获取HackerNews热门文章详情，限制为{limit}条")
        
        # 检查缓存
        cache_key = f"top_stories_details_{limit}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        # 获取热门文章ID列表
        story_ids = await self.async_get_top_stories(limit)
        
        # 异步获取每篇文章的详情
        tasks = []
        for story_id in story_ids:
            task = self.async_get_item(story_id)
            tasks.append(task)
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks)
        
        # 过滤掉失败的结果
        stories = [story for story in results if story]
        
        # 缓存结果
        if self.use_cache:
            # 文章详情变化较快，使用较短的缓存时间
            self.cache.set(cache_key, stories, ttl=600)  # 10分钟
        
        return stories
    
    def get_comments(self, story_id: int, limit=30) -> List[Dict[str, Any]]:
        """
        获取指定文章的评论
        
        Args:
            story_id: 文章ID
            limit: 返回的评论数量上限
            
        Returns:
            评论列表
        """
        LOG.debug(f"获取HackerNews文章评论，文章ID: {story_id}，限制为{limit}条")
        
        # 检查缓存
        cache_key = f"comments_{story_id}_{limit}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        # 获取文章详情
        story = self.get_item(story_id)
        if not story or 'kids' not in story:
            LOG.warning(f"文章不存在或没有评论，文章ID: {story_id}")
            return []
        
        # 获取评论ID列表
        comment_ids = story['kids']
        if limit and len(comment_ids) > limit:
            comment_ids = comment_ids[:limit]
        
        # 获取每条评论的详情
        comments = []
        for comment_id in comment_ids:
            comment = self.get_item(comment_id)
            if comment and not comment.get('deleted', False) and not comment.get('dead', False):
                comments.append(comment)
        
        # 缓存结果
        if self.use_cache:
            self.cache.set(cache_key, comments)
        
        return comments
    
    async def async_get_comments(self, story_id: int, limit=30) -> List[Dict[str, Any]]:
        """
        异步获取指定文章的评论
        
        Args:
            story_id: 文章ID
            limit: 返回的评论数量上限
            
        Returns:
            评论列表
        """
        LOG.debug(f"异步获取HackerNews文章评论，文章ID: {story_id}，限制为{limit}条")
        
        # 检查缓存
        cache_key = f"comments_{story_id}_{limit}"
        if self.use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        # 获取文章详情
        story = await self.async_get_item(story_id)
        if not story or 'kids' not in story:
            LOG.warning(f"文章不存在或没有评论，文章ID: {story_id}")
            return []
        
        # 获取评论ID列表
        comment_ids = story['kids']
        if limit and len(comment_ids) > limit:
            comment_ids = comment_ids[:limit]
        
        # 异步获取每条评论的详情
        tasks = []
        for comment_id in comment_ids:
            task = self.async_get_item(comment_id)
            tasks.append(task)
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks)
        
        # 过滤掉已删除或已死亡的评论
        comments = [comment for comment in results if comment and not comment.get('deleted', False) and not comment.get('dead', False)]
        
        # 缓存结果
        if self.use_cache:
            self.cache.set(cache_key, comments)
        
        return comments

    def export_top_stories(self, date=None, hour=None, enable_ai_summary=True):
        """
        导出当前 Hacker News 热门故事列表到 Markdown 文件
        
        Args:
            date: 日期字符串 (YYYY-MM-DD 格式)，如果未提供则使用当前日期
            hour: 小时字符串 (HH 格式)，如果未提供则使用当前小时
            enable_ai_summary: 是否启用AI摘要功能，默认为True
            
        Returns:
            生成的 Markdown 文件路径，如果发生错误则返回 None
        """
        LOG.debug("准备导出Hacker News的热门新闻。")
        
        try:
            # 获取新闻数据
            stories_details = self.get_top_stories_details(limit=30)  
            
            if not stories_details:
                LOG.warning("未找到任何Hacker News的新闻。")
                return None
            
            # 如果未提供 date 和 hour 参数，使用当前日期和时间
            if date is None:
                date = datetime.now().strftime('%Y-%m-%d')
            if hour is None:
                hour = datetime.now().strftime('%H')

            # 构建存储路径
            dir_path = os.path.join('hacker_news', date)
            os.makedirs(dir_path, exist_ok=True)  # 确保目录存在
            
            # 对故事进行分类
            categorized_stories = self._categorize_stories(stories_details)
            
            # 尝试为热门故事添加AI摘要
            if enable_ai_summary:
                LOG.info("AI摘要功能已启用，正在为热门文章生成摘要...")
                top_stories = sorted(stories_details, key=lambda x: x.get('score', 0), reverse=True)[:10]
                self._add_ai_summaries(top_stories)
            else:
                LOG.info("AI摘要功能已禁用，跳过摘要生成")
            
            # 保存原始列表
            stories_file_path = os.path.join(dir_path, f'{hour}.md')  # 定义文件路径
            with open(stories_file_path, 'w', encoding='utf-8') as file:
                file.write(f"# Hacker News 热门新闻 ({date} {hour}:00)\n\n")
                file.write("本报告收集了最近一小时内Hacker News平台上的热门讨论内容。\"分数\"代表用户的投票数量，反映了文章的热度与受欢迎程度。\n\n")
                
                # 首先显示最热门的故事
                file.write("## 🔥 最热门讨论\n\n")
                # 按分数排序，取前3个
                top_stories = sorted(stories_details, key=lambda x: x.get('score', 0), reverse=True)[:3]
                for idx, story in enumerate(top_stories, start=1):
                    self._write_story_entry(file, idx, story)
                
                # 添加展示类内容
                if categorized_stories['show_hn']:
                    file.write("\n## 👀 展示与分享\n\n")
                    file.write("用户分享的项目、产品和创造。\n\n")
                    for idx, story in enumerate(categorized_stories['show_hn'], start=1):
                        self._write_story_entry(file, idx, story)
                
                # 添加问答类内容
                if categorized_stories['ask_hn']:
                    file.write("\n## ❓ 问答与讨论\n\n")
                    file.write("社区成员提出的问题和讨论。\n\n")
                    for idx, story in enumerate(categorized_stories['ask_hn'], start=1):
                        self._write_story_entry(file, idx, story)
                
                # 添加技术类内容
                if categorized_stories['tech']:
                    file.write("\n## 💻 技术与工程\n\n")
                    file.write("编程、开发和技术相关的热门话题。\n\n")
                    for idx, story in enumerate(categorized_stories['tech'], start=1):
                        self._write_story_entry(file, idx, story)
                
                # 添加科学类内容
                if categorized_stories['science']:
                    file.write("\n## 🔬 科学研究\n\n")
                    file.write("科学发现、研究和相关讨论。\n\n")
                    for idx, story in enumerate(categorized_stories['science'], start=1):
                        self._write_story_entry(file, idx, story)
                
                # 添加商业类内容
                if categorized_stories['business']:
                    file.write("\n## 💼 商业与创业\n\n")
                    file.write("商业新闻、创业和行业动态。\n\n")
                    for idx, story in enumerate(categorized_stories['business'], start=1):
                        self._write_story_entry(file, idx, story)
                
                # 添加其他类内容
                if categorized_stories['others']:
                    file.write("\n## 📚 其他热门内容\n\n")
                    for idx, story in enumerate(categorized_stories['others'], start=1):
                        self._write_story_entry(file, idx, story)
            
            # 执行主题分析
            topics_file_path = self._analyze_topics(stories_details, date, hour)
            
            LOG.info(f"Hacker News热门新闻文件生成：{stories_file_path}")
            return stories_file_path
            
        except Exception as e:
            LOG.error(f"导出Hacker News热门新闻时发生错误: {e}")
            LOG.error(traceback.format_exc())
            return None
    
    def _categorize_stories(self, stories):
        """
        对Hacker News故事进行分类
        
        Args:
            stories: 故事列表
            
        Returns:
            分类后的故事字典
        """
        categories = {
            'show_hn': [],
            'ask_hn': [],
            'tech': [],
            'science': [],
            'business': [],
            'others': []
        }
        
        # 技术相关关键词
        tech_keywords = ['programming', 'code', 'software', 'developer', 'web', 'app', 
                         'python', 'javascript', 'rust', 'go', 'java', 'c++', 'typescript',
                         'database', 'api', 'framework', 'library', 'algorithm', 'github',
                         'git', 'docker', 'kubernetes', 'aws', 'cloud', 'devops', 'ai',
                         'ml', 'machine learning', 'deep learning', 'neural', 'llm']
        
        # 科学相关关键词
        science_keywords = ['science', 'research', 'study', 'physics', 'chemistry', 'biology',
                           'astronomy', 'space', 'mars', 'nasa', 'quantum', 'medicine',
                           'climate', 'energy', 'environment', 'genome', 'brain']
        
        # 商业相关关键词
        business_keywords = ['startup', 'business', 'company', 'founder', 'investor',
                            'venture', 'vc', 'funding', 'acquisition', 'market',
                            'finance', 'economy', 'stock', 'crypto', 'blockchain']
        
        for story in stories:
            title = story.get('title', '').lower()
            
            if story.get('type') == 'job' or 'hiring' in title or 'job' in title:
                categories['business'].append(story)
            elif 'show hn' in title or 'show hn:' in title:
                categories['show_hn'].append(story)
            elif 'ask hn' in title or 'ask hn:' in title:
                categories['ask_hn'].append(story)
            elif any(keyword in title for keyword in tech_keywords):
                categories['tech'].append(story)
            elif any(keyword in title for keyword in science_keywords):
                categories['science'].append(story)
            elif any(keyword in title for keyword in business_keywords):
                categories['business'].append(story)
            else:
                categories['others'].append(story)
        
        return categories
    
    def _write_story_entry(self, file, idx, story):
        """
        将故事条目写入文件
        
        Args:
            file: 文件对象
            idx: 索引
            story: 故事对象
        """
        if not story:
            return
            
        title = story.get('title', '无标题')
        story_type = story.get('type', 'unknown')
        
        # 根据不同类型添加不同的图标
        icon = "📰"
        if "show hn" in title.lower():
            icon = "🔍"
        elif "ask hn" in title.lower():
            icon = "❓"
        elif story_type == "job":
            icon = "💼"
        
        # 处理不同类型的故事
        if 'url' in story:
            # 普通的带外部链接的故事
            url = story['url']
            file.write(f"{icon} **[{title}]({url})**\n")
        else:
            # Ask HN, Show HN 或其他没有外部URL的故事类型
            hn_item_url = f"https://news.ycombinator.com/item?id={story.get('id', '')}"
            file.write(f"{icon} **[{title}]({hn_item_url})**\n")
        
        # 添加AI摘要（如果有）
        if 'ai_summary' in story and story['ai_summary']:
            file.write(f"  📝 {story['ai_summary']}\n")
        
        # 添加额外信息（分数、发布者、时间等）
        extra_info = []
        if 'score' in story:
            extra_info.append(f"👍 **{story['score']}** 分")
        if 'by' in story:
            extra_info.append(f"👤 作者: {story['by']}")
        if 'descendants' in story and story['descendants'] > 0:
            extra_info.append(f"💬 {story['descendants']} 条评论")
            
        if extra_info:
            file.write(f"  {' | '.join(extra_info)}\n\n")
        else:
            file.write("\n")
    
    def _analyze_topics(self, stories, date=None, hour=None):
        """
        分析故事主题并生成报告
        
        Args:
            stories: HN故事列表
            date: 日期字符串 (YYYY-MM-DD)
            hour: 小时字符串 (HH)
            
        Returns:
            生成的主题报告文件路径，如果发生错误则返回None
        """
        try:
            LOG.info("准备导入话题分析器...")
            # 确保NLTK数据已下载
            import nltk
            nltk_dirs = ["tokenizers/punkt", "corpora/stopwords", "corpora/wordnet"]
            for nltk_dir in nltk_dirs:
                try:
                    nltk.data.find(nltk_dir)
                except LookupError:
                    LOG.info(f"下载NLTK数据: {nltk_dir}...")
                    nltk.download(nltk_dir.split('/')[-1])
            
            # 延迟导入，确保即使没有安装分析器依赖也能运行基本功能
            from src.analyzers.topic_analyzer import HackerNewsTopicAnalyzer
            
            LOG.info("开始分析Hacker News主题...")
            analyzer = HackerNewsTopicAnalyzer()
            
            # 分析话题
            result = analyzer.analyze_topics(stories, date, hour)
            
            # 生成报告
            report = analyzer.generate_report(result)
            
            # 保存报告
            if date is None:
                date = datetime.now().strftime('%Y-%m-%d')
            if hour is None:
                hour = datetime.now().strftime('%H')
                
            dir_path = os.path.join('hacker_news', date)
            os.makedirs(dir_path, exist_ok=True)
            
            topics_file_path = os.path.join(dir_path, f'{hour}_topics.md')
            with open(topics_file_path, 'w', encoding='utf-8') as f:
                f.write(report)
                
            LOG.info(f"Hacker News主题分析报告已生成: {topics_file_path}")
            return topics_file_path
            
        except ImportError as e:
            LOG.warning(f"未能导入主题分析器，跳过主题分析 (请安装必要的依赖库): {e}")
            return None
        except Exception as e:
            LOG.error(f"分析Hacker News主题时发生错误: {e}")
            LOG.error(traceback.format_exc())
            return None
    
    def _add_ai_summaries(self, stories: List[Dict[str, Any]]) -> bool:
        """
        使用LLM为热门故事添加AI生成的摘要
        
        Args:
            stories: 需要添加摘要的故事列表
            
        Returns:
            是否成功添加摘要
        """
        try:
            # 检查是否可以导入LLM
            try:
                from src.llm import LLM
                from src.config import Settings
            except ImportError:
                LOG.warning("未能导入LLM或Settings模块，跳过AI总结")
                return False
                
            # 初始化LLM
            try:
                settings = Settings(config_file="config.json")
                llm = LLM(settings=settings)
            except Exception as e:
                LOG.warning(f"初始化LLM失败，跳过AI总结: {e}")
                return False
            
            LOG.info(f"开始为{len(stories)}个热门故事生成AI摘要...")
            
            # 为每个故事生成摘要
            for story in stories:
                # 如果已经有摘要，跳过
                if 'ai_summary' in story:
                    continue
                    
                title = story.get('title', '')
                url = story.get('url', '')
                
                # 构建提示
                prompt = f"""
                请为以下Hacker News文章生成一个简短的中文摘要（不超过30个字）。
                标题: {title}
                链接: {url if url else '无外部链接'}
                
                你的回答应该是纯文本格式，直接描述这篇文章大概讲了什么，不要包含"这篇文章讲述了"之类的引导语。
                """
                
                try:
                    # 使用LLM生成摘要 - 修复方法名称
                    summary_chunks = list(llm.generate_report(
                        system_prompt="你是一个简洁的文章摘要助手，你的任务是生成简短的中文摘要。",
                        user_content=prompt
                    ))
                    clean_summary = "".join(summary_chunks).strip()
                    
                    # 确保摘要不超过40个字
                    if len(clean_summary) > 40:
                        clean_summary = clean_summary[:37] + "..."
                    
                    # 保存摘要
                    story['ai_summary'] = clean_summary
                    LOG.debug(f"已为文章'{title}'生成摘要: {clean_summary}")
                    
                    # 避免过于频繁的API调用
                    time.sleep(0.5)
                    
                except Exception as e:
                    LOG.warning(f"为文章'{title}'生成摘要失败: {e}")
                    continue
            
            return True
            
        except Exception as e:
            LOG.error(f"添加AI摘要过程中发生错误: {e}")
            LOG.error(traceback.format_exc())
            return False
    
    async def async_export_top_stories(self, date=None, hour=None, enable_ai_summary=True):
        """
        异步导出当前 Hacker News 热门故事列表到 Markdown 文件
        
        Args:
            date: 日期字符串 (YYYY-MM-DD 格式)，如果未提供则使用当前日期
            hour: 小时字符串 (HH 格式)，如果未提供则使用当前小时
            enable_ai_summary: 是否启用AI摘要功能，默认为True
            
        Returns:
            生成的 Markdown 文件路径，如果发生错误则返回 None
        """
        LOG.debug("准备异步导出Hacker News的热门新闻。")
        
        try:
            # 获取新闻数据
            stories_details = await self.async_get_top_stories_details(limit=30)
            
            if not stories_details:
                LOG.warning("异步获取未找到任何Hacker News的新闻。")
                return None
            
            # 如果未提供 date 和 hour 参数，使用当前日期和时间
            if date is None:
                date = datetime.now().strftime('%Y-%m-%d')
            if hour is None:
                hour = datetime.now().strftime('%H')
            
            # 构建存储路径
            dir_path = os.path.join('hacker_news', date)
            os.makedirs(dir_path, exist_ok=True)
            
            # 对故事进行分类
            categorized_stories = self._categorize_stories(stories_details)
            
            # 尝试为热门故事添加AI摘要
            if enable_ai_summary:
                LOG.info("AI摘要功能已启用，正在为热门文章生成摘要...")
                top_stories = sorted(stories_details, key=lambda x: x.get('score', 0), reverse=True)[:10]
                self._add_ai_summaries(top_stories)
            else:
                LOG.info("AI摘要功能已禁用，跳过摘要生成")
            
            # 保存原始列表
            stories_file_path = os.path.join(dir_path, f'{hour}.md')
            with open(stories_file_path, 'w', encoding='utf-8') as file:
                file.write(f"# Hacker News 热门新闻 ({date} {hour}:00)\n\n")
                file.write("本报告收集了最近一小时内Hacker News平台上的热门讨论内容。\"分数\"代表用户的投票数量，反映了文章的热度与受欢迎程度。\n\n")
                
                # 首先显示最热门的故事
                file.write("## 🔥 最热门讨论\n\n")
                # 按分数排序，取前3个
                top_stories = sorted(stories_details, key=lambda x: x.get('score', 0), reverse=True)[:3]
                for idx, story in enumerate(top_stories, start=1):
                    self._write_story_entry(file, idx, story)
                
                # 添加展示类内容
                if categorized_stories['show_hn']:
                    file.write("\n## 👀 展示与分享\n\n")
                    file.write("用户分享的项目、产品和创造。\n\n")
                    for idx, story in enumerate(categorized_stories['show_hn'], start=1):
                        self._write_story_entry(file, idx, story)
                
                # 添加问答类内容
                if categorized_stories['ask_hn']:
                    file.write("\n## ❓ 问答与讨论\n\n")
                    file.write("社区成员提出的问题和讨论。\n\n")
                    for idx, story in enumerate(categorized_stories['ask_hn'], start=1):
                        self._write_story_entry(file, idx, story)
                
                # 添加技术类内容
                if categorized_stories['tech']:
                    file.write("\n## 💻 技术与工程\n\n")
                    file.write("编程、开发和技术相关的热门话题。\n\n")
                    for idx, story in enumerate(categorized_stories['tech'], start=1):
                        self._write_story_entry(file, idx, story)
                
                # 添加科学类内容
                if categorized_stories['science']:
                    file.write("\n## 🔬 科学研究\n\n")
                    file.write("科学发现、研究和相关讨论。\n\n")
                    for idx, story in enumerate(categorized_stories['science'], start=1):
                        self._write_story_entry(file, idx, story)
                
                # 添加商业类内容
                if categorized_stories['business']:
                    file.write("\n## 💼 商业与创业\n\n")
                    file.write("商业新闻、创业和行业动态。\n\n")
                    for idx, story in enumerate(categorized_stories['business'], start=1):
                        self._write_story_entry(file, idx, story)
                
                # 添加其他类内容
                if categorized_stories['others']:
                    file.write("\n## 📚 其他热门内容\n\n")
                    for idx, story in enumerate(categorized_stories['others'], start=1):
                        self._write_story_entry(file, idx, story)
            
            # 执行主题分析 (使用同步版本，因为分析器尚未异步化)
            topics_file_path = self._analyze_topics(stories_details, date, hour)
            
            LOG.info(f"Hacker News热门新闻文件异步生成：{stories_file_path}")
            return stories_file_path
            
        except Exception as e:
            LOG.error(f"异步导出Hacker News热门新闻时发生错误: {e}")
            LOG.error(traceback.format_exc())
            return None
    
    def clear_cache(self):
        """清除所有缓存"""
        if self.use_cache:
            count = self.cache.clear_all()
            LOG.info(f"已清除 {count} 个Hacker News缓存文件")
            return count
        return 0


if __name__ == "__main__":
    client = HackerNewsClient()
    client.export_top_stories()  # 默认情况下使用当前日期和时间
