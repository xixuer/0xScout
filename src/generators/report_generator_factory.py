from typing import Dict, Any, Optional

try:
    from src.core.base_report_generator import BaseReportGenerator
    from src.generators.github_report_generator import GitHubReportGenerator
    from src.generators.hacker_news_report_generator import HackerNewsReportGenerator
    from src.logger import LOG
except ImportError:
    try:
        from core.base_report_generator import BaseReportGenerator
        from generators.github_report_generator import GitHubReportGenerator
        from generators.hacker_news_report_generator import HackerNewsReportGenerator
        from logger import LOG
    except ImportError:
        import logging
        LOG = logging.getLogger(__name__)
        from base_report_generator import BaseReportGenerator
        from github_report_generator import GitHubReportGenerator
        from hacker_news_report_generator import HackerNewsReportGenerator

class ReportGeneratorFactory:
    """
    报告生成器工厂类
    用于创建不同类型的报告生成器
    """
    
    @staticmethod
    def create_generator(generator_type: str, llm: Any, settings: Dict[str, Any]) -> Optional[BaseReportGenerator]:
        """
        创建报告生成器
        
        Args:
            generator_type: 生成器类型，可选值为"github"或"hacker_news"
            llm: 语言模型实例
            settings: 配置设置
            
        Returns:
            报告生成器实例，如果类型不支持则返回None
        """
        LOG.info(f"创建 {generator_type} 报告生成器")
        
        if generator_type.lower() == "github":
            return GitHubReportGenerator(llm, settings)
        elif generator_type.lower() in ["hacker_news", "hackernews", "hn"]:
            return HackerNewsReportGenerator(llm, settings)
        else:
            LOG.error(f"不支持的报告生成器类型: {generator_type}")
            return None 