import os
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional, Generator, Union
import glob

try:
    from src.core.base_report_generator import BaseReportGenerator
    from src.clients.hacker_news_client import HackerNewsClient
    from src.logger import LOG
except ImportError:
    try:
        from core.base_report_generator import BaseReportGenerator
        from clients.hacker_news_client import HackerNewsClient
        from logger import LOG
    except ImportError:
        import logging
        LOG = logging.getLogger(__name__)
        from base_report_generator import BaseReportGenerator
        from hacker_news_client import HackerNewsClient

class HackerNewsReportGenerator(BaseReportGenerator):
    """
    Hacker News报告生成器
    负责生成与Hacker News相关的所有报告
    """
    
    def __init__(self, llm, settings):
        """
        初始化Hacker News报告生成器
        
        Args:
            llm: 语言模型实例
            settings: 配置设置实例
        """
        self.llm = llm
        self.settings = settings
        self.prompts = {}
        self._preload_prompts()
        
        # 初始化HackerNews客户端
        self.hacker_news_client = HackerNewsClient(
            use_cache=settings.get("use_cache", True),
            cache_ttl=settings.get("cache_ttl", 3600)
        )
        
        LOG.info("HackerNews报告生成器已初始化")
    
    def _preload_prompts(self):
        """
        预加载提示模板
        """
        LOG.debug("预加载HackerNews提示模板...")
        self.prompts["top_stories_summary"] = """
        请根据以下HackerNews热门文章信息，生成一个简洁的摘要报告：
        
        热门文章：
        {stories}
        
        请包括以下内容：
        1. 当前热门技术话题和趋势
        2. 值得关注的文章亮点
        3. 技术社区关注的焦点
        
        请使用中文回答，保持简洁明了。
        """
        
        self.prompts["story_comments_summary"] = """
        请根据以下HackerNews文章及其评论信息，生成一个简洁的摘要报告：
        
        文章标题：{title}
        文章链接：{url}
        
        评论：
        {comments}
        
        请包括以下内容：
        1. 评论中提到的主要观点
        2. 有价值的见解和建议
        3. 存在的争议点
        
        请使用中文回答，保持简洁明了。
        """
        
        # 兼容旧代码
        self.prompts["hacker_news_hours_topic"] = """
        请分析以下Hacker News热门新闻，总结主要话题和趋势:
        
        {content}
        
        请包括以下内容：
        1. 当前热门技术话题
        2. 值得关注的文章亮点
        3. 技术社区关注的焦点
        
        请使用中文回答，保持简洁明了。
        """
        
        self.prompts["hacker_news_daily_report"] = """
        请分析以下一天内的Hacker News热门新闻，总结主要话题和趋势，并按重要性排序:
        
        {content}
        
        请包括以下内容：
        1. 当天的热门技术话题
        2. 重要的技术动态和新闻
        3. 值得关注的讨论和见解
        4. 技术社区的整体关注点
        
        请使用中文回答，保持简洁明了。
        """
        
        LOG.debug("HackerNews提示模板已加载")
    
    def _aggregate_hourly_hn_data(self, date_str: str) -> str:
        """
        聚合指定日期的Hacker News每小时数据
        
        Args:
            date_str: 日期字符串，格式为YYYY-MM-DD
            
        Returns:
            聚合后的Markdown字符串
        """
        LOG.debug(f"聚合{date_str}的Hacker News每小时数据")
        
        # 构建数据目录路径
        data_dir = os.path.join("hacker_news", date_str)
        if not os.path.exists(data_dir):
            LOG.warning(f"Hacker News数据目录{data_dir}不存在")
            return f"# Hacker News {date_str}数据\n\n未找到该日期的数据。"
        
        # 获取所有小时文件
        hour_files = glob.glob(os.path.join(data_dir, "*.md"))
        if not hour_files:
            LOG.warning(f"在{data_dir}中未找到任何小时数据文件")
            return f"# Hacker News {date_str}数据\n\n该日期下没有小时数据文件。"
        
        # 按小时排序
        hour_files.sort()
        
        # 读取并聚合所有小时数据
        all_hours_content = []
        for hour_file in hour_files:
            try:
                hour = os.path.basename(hour_file).replace(".md", "")
                with open(hour_file, "r", encoding="utf-8") as f:
                    content = f.read()
                all_hours_content.append(f"## {hour}:00\n\n{content}\n")
            except Exception as e:
                LOG.error(f"读取{hour_file}时发生错误: {e}", exc_info=True)
        
        # 合并所有小时数据
        return f"# Hacker News {date_str}全天数据\n\n" + "\n".join(all_hours_content)
    
    def generate_hourly_report(self, content: str) -> Generator[str, None, None]:
        """
        生成Hacker News小时报告
        
        Args:
            content: Hacker News小时数据内容
            
        Returns:
            生成的报告内容（生成器）
        """
        LOG.info("生成Hacker News小时报告")
        
        try:
            # 使用LLM生成报告
            system_prompt = self.prompts.get("hacker_news_hours_topic", "请分析以下Hacker News热门新闻，总结主要话题和趋势:")
            
            # 返回生成的报告
            yield from self.llm.generate_report(system_prompt, content)
        except Exception as e:
            LOG.error(f"生成Hacker News小时报告时发生错误: {e}", exc_info=True)
            yield f"生成报告时发生错误: {e}"
    
    async def async_generate_hourly_report(self, content: str) -> Generator[str, None, None]:
        """
        异步生成Hacker News小时报告
        
        Args:
            content: Hacker News小时数据内容
            
        Returns:
            生成的报告内容（生成器）
        """
        LOG.info("异步生成Hacker News小时报告")
        
        try:
            # 使用LLM生成报告
            system_prompt = self.prompts.get("hacker_news_hours_topic", "请分析以下Hacker News热门新闻，总结主要话题和趋势:")
            
            # 异步函数中不能使用yield from，需要手动迭代
            for chunk in self.llm.generate_report(system_prompt, content):
                yield chunk
        except Exception as e:
            LOG.error(f"异步生成Hacker News小时报告时发生错误: {e}", exc_info=True)
            yield f"生成报告时发生错误: {e}"
    
    def get_hourly_report(self, target_date: str, target_hour: str) -> Generator[str, None, None]:
        """
        获取指定日期和小时的Hacker News报告
        
        Args:
            target_date: 目标日期，格式为YYYY-MM-DD
            target_hour: 目标小时，格式为HH
            
        Returns:
            生成的报告内容（生成器）
        """
        LOG.info(f"获取{target_date} {target_hour}:00的Hacker News报告")
        
        # 构建文件路径
        file_path = os.path.join("hacker_news", target_date, f"{target_hour}.md")
        if not os.path.exists(file_path):
            LOG.warning(f"Hacker News数据文件{file_path}不存在")
            yield f"未找到{target_date} {target_hour}:00的Hacker News数据。"
            return
        
        try:
            # 读取文件内容
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 生成报告
            yield from self.generate_hourly_report(content)
        except Exception as e:
            LOG.error(f"获取{target_date} {target_hour}:00的Hacker News报告时发生错误: {e}", exc_info=True)
            yield f"获取报告时发生错误: {e}"
    
    async def async_get_hourly_report(self, target_date: str, target_hour: str) -> Generator[str, None, None]:
        """
        异步获取指定日期和小时的Hacker News报告
        
        Args:
            target_date: 目标日期，格式为YYYY-MM-DD
            target_hour: 目标小时，格式为HH
            
        Returns:
            生成的报告内容（生成器）
        """
        LOG.info(f"异步获取{target_date} {target_hour}:00的Hacker News报告")
        
        # 构建文件路径
        file_path = os.path.join("hacker_news", target_date, f"{target_hour}.md")
        if not os.path.exists(file_path):
            LOG.warning(f"Hacker News数据文件{file_path}不存在")
            yield f"未找到{target_date} {target_hour}:00的Hacker News数据。"
            return
        
        try:
            # 读取文件内容
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 异步生成报告
            async for chunk in self.async_generate_hourly_report(content):
                yield chunk
        except Exception as e:
            LOG.error(f"异步获取{target_date} {target_hour}:00的Hacker News报告时发生错误: {e}", exc_info=True)
            yield f"获取报告时发生错误: {e}"
    
    def generate_daily_report(self, date_str: str) -> Generator[str, None, None]:
        """
        生成指定日期的Hacker News每日报告
        
        Args:
            date_str: 日期字符串，格式为YYYY-MM-DD
            
        Returns:
            生成的报告内容（生成器）
        """
        LOG.info(f"生成{date_str}的Hacker News每日报告")
        
        try:
            # 聚合该日期的所有小时数据
            aggregated_content = self._aggregate_hourly_hn_data(date_str)
            
            # 使用LLM生成报告
            system_prompt = self.prompts.get("hacker_news_daily_report", "请分析以下一天内的Hacker News热门新闻，总结主要话题和趋势，并按重要性排序:")
            
            # 返回生成的报告
            yield from self.llm.generate_report(system_prompt, aggregated_content)
        except Exception as e:
            LOG.error(f"生成{date_str}的Hacker News每日报告时发生错误: {e}", exc_info=True)
            yield f"生成报告时发生错误: {e}"
    
    async def async_generate_daily_report(self, date_str: str) -> Generator[str, None, None]:
        """
        异步生成指定日期的Hacker News每日报告
        
        Args:
            date_str: 日期字符串，格式为YYYY-MM-DD
            
        Returns:
            生成的报告内容（生成器）
        """
        LOG.info(f"异步生成{date_str}的Hacker News每日报告")
        
        try:
            # 聚合该日期的所有小时数据
            aggregated_content = self._aggregate_hourly_hn_data(date_str)
            
            # 使用LLM生成报告
            system_prompt = self.prompts.get("hacker_news_daily_report", "请分析以下一天内的Hacker News热门新闻，总结主要话题和趋势，并按重要性排序:")
            
            # 异步函数中不能使用yield from，需要手动迭代
            for chunk in self.llm.generate_report(system_prompt, aggregated_content):
                yield chunk
        except Exception as e:
            LOG.error(f"异步生成{date_str}的Hacker News每日报告时发生错误: {e}", exc_info=True)
            yield f"生成报告时发生错误: {e}"
    
    def generate_report(self, *args, **kwargs) -> Union[str, Generator[str, None, None]]:
        """
        生成报告
        
        支持的参数组合:
        - limit: 生成热门文章摘要报告
        - story_id, limit: 生成文章评论摘要报告
        
        Returns:
            生成的报告内容
        """
        if 'story_id' in kwargs:
            # 生成文章评论摘要报告
            story_id = kwargs.get('story_id')
            limit = kwargs.get('limit', 30)
            return self.generate_story_comments_summary(story_id, limit)
        else:
            # 生成热门文章摘要报告
            limit = kwargs.get('limit', 30)
            return self.generate_top_stories_summary(limit)
    
    def generate_top_stories_summary(self, limit: int = 30) -> str:
        """
        生成热门文章摘要报告
        
        Args:
            limit: 获取的文章数量
            
        Returns:
            生成的报告内容
        """
        LOG.info(f"开始生成HackerNews热门文章摘要报告 (前 {limit} 条)")
        
        # 获取热门文章详情
        stories = self.hacker_news_client.get_top_stories_details(limit)
        
        if not stories:
            LOG.warning("未获取到HackerNews热门文章")
            return "未获取到HackerNews热门文章"
        
        # 格式化文章信息
        stories_text = ""
        for idx, story in enumerate(stories, start=1):
            stories_text += f"{idx}. 标题: {story.get('title', 'N/A')}\n"
            stories_text += f"   链接: {story.get('url', 'N/A')}\n"
            stories_text += f"   分数: {story.get('score', 0)}\n"
            stories_text += f"   评论数: {len(story.get('kids', []))}\n\n"
        
        # 使用LLM生成摘要
        prompt = self.prompts["top_stories_summary"].format(
            stories=stories_text
        )
        
        summary = self.llm.generate_text(prompt)
        
        LOG.info("HackerNews热门文章摘要报告生成完成")
        return summary
    
    async def async_generate_top_stories_summary(self, limit: int = 30) -> str:
        """
        异步生成热门文章摘要报告
        
        Args:
            limit: 获取的文章数量
            
        Returns:
            生成的报告内容
        """
        LOG.info(f"开始异步生成HackerNews热门文章摘要报告 (前 {limit} 条)")
        
        # 异步获取热门文章详情
        stories = await self.hacker_news_client.async_get_top_stories_details(limit)
        
        if not stories:
            LOG.warning("未获取到HackerNews热门文章")
            return "未获取到HackerNews热门文章"
        
        # 格式化文章信息
        stories_text = ""
        for idx, story in enumerate(stories, start=1):
            stories_text += f"{idx}. 标题: {story.get('title', 'N/A')}\n"
            stories_text += f"   链接: {story.get('url', 'N/A')}\n"
            stories_text += f"   分数: {story.get('score', 0)}\n"
            stories_text += f"   评论数: {len(story.get('kids', []))}\n\n"
        
        # 使用LLM生成摘要
        prompt = self.prompts["top_stories_summary"].format(
            stories=stories_text
        )
        
        summary = await self.llm.async_generate_text(prompt)
        
        LOG.info("HackerNews热门文章摘要报告异步生成完成")
        return summary
    
    def generate_story_comments_summary(self, story_id: int, limit: int = 30) -> str:
        """
        生成文章评论摘要报告
        
        Args:
            story_id: 文章ID
            limit: 获取的评论数量
            
        Returns:
            生成的报告内容
        """
        LOG.info(f"开始生成HackerNews文章评论摘要报告，文章ID: {story_id}")
        
        # 获取文章详情
        story = self.hacker_news_client.get_item(story_id)
        if not story:
            LOG.warning(f"未找到ID为 {story_id} 的文章")
            return f"未找到ID为 {story_id} 的文章"
        
        # 获取文章评论
        comments = self.hacker_news_client.get_comments(story_id, limit)
        
        if not comments:
            LOG.warning(f"文章 {story_id} 没有评论")
            return f"文章 '{story.get('title', 'N/A')}' 没有评论"
        
        # 格式化评论信息
        comments_text = ""
        for idx, comment in enumerate(comments, start=1):
            text = comment.get('text', 'N/A').replace('<p>', '\n').replace('</p>', '')
            comments_text += f"{idx}. {text}\n\n"
        
        # 使用LLM生成摘要
        prompt = self.prompts["story_comments_summary"].format(
            title=story.get('title', 'N/A'),
            url=story.get('url', 'N/A'),
            comments=comments_text
        )
        
        summary = self.llm.generate_text(prompt)
        
        LOG.info(f"HackerNews文章 {story_id} 评论摘要报告生成完成")
        return summary
    
    async def async_generate_story_comments_summary(self, story_id: int, limit: int = 30) -> str:
        """
        异步生成文章评论摘要报告
        
        Args:
            story_id: 文章ID
            limit: 获取的评论数量
            
        Returns:
            生成的报告内容
        """
        LOG.info(f"开始异步生成HackerNews文章评论摘要报告，文章ID: {story_id}")
        
        # 异步获取文章详情
        story = await self.hacker_news_client.async_get_item(story_id)
        if not story:
            LOG.warning(f"未找到ID为 {story_id} 的文章")
            return f"未找到ID为 {story_id} 的文章"
        
        # 异步获取文章评论
        comments = await self.hacker_news_client.async_get_comments(story_id, limit)
        
        if not comments:
            LOG.warning(f"文章 {story_id} 没有评论")
            return f"文章 '{story.get('title', 'N/A')}' 没有评论"
        
        # 格式化评论信息
        comments_text = ""
        for idx, comment in enumerate(comments, start=1):
            text = comment.get('text', 'N/A').replace('<p>', '\n').replace('</p>', '')
            comments_text += f"{idx}. {text}\n\n"
        
        # 使用LLM生成摘要
        prompt = self.prompts["story_comments_summary"].format(
            title=story.get('title', 'N/A'),
            url=story.get('url', 'N/A'),
            comments=comments_text
        )
        
        summary = await self.llm.async_generate_text(prompt)
        
        LOG.info(f"HackerNews文章 {story_id} 评论摘要报告异步生成完成")
        return summary 