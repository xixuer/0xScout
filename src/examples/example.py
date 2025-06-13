import asyncio
import os
import json
from datetime import datetime

try:
    from src.generators.report_generator_factory import ReportGeneratorFactory
    from src.logger import LOG
except ImportError:
    try:
        from generators.report_generator_factory import ReportGeneratorFactory
        from logger import LOG
    except ImportError:
        import logging
        logging.basicConfig(level=logging.INFO)
        LOG = logging.getLogger(__name__)
        from report_generator_factory import ReportGeneratorFactory

# 模拟LLM接口
class MockLLM:
    def generate_text(self, prompt):
        LOG.info("生成文本...")
        return f"这是根据提示生成的文本: {prompt[:50]}..."
    
    async def async_generate_text(self, prompt):
        LOG.info("异步生成文本...")
        return f"这是异步生成的文本: {prompt[:50]}..."

# 加载配置
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '../../config.json')
    if not os.path.exists(config_path):
        LOG.warning(f"配置文件不存在: {config_path}，使用默认配置")
        return {
            "github_token": os.environ.get("GITHUB_TOKEN", ""),
            "use_cache": True,
            "cache_ttl": 3600
        }
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except Exception as e:
        LOG.error(f"加载配置文件失败: {e}")
        return {
            "github_token": os.environ.get("GITHUB_TOKEN", ""),
            "use_cache": True,
            "cache_ttl": 3600
        }

# 同步示例
def run_sync_example():
    LOG.info("运行同步示例...")
    
    # 加载配置
    config = load_config()
    
    # 创建LLM实例
    llm = MockLLM()
    
    # 创建GitHub报告生成器
    github_generator = ReportGeneratorFactory.create_generator("github", llm, config)
    
    # 生成GitHub仓库报告
    repo = "microsoft/vscode"
    report = github_generator.generate_report(repo=repo, days=7)
    LOG.info(f"GitHub报告: {report[:100]}...")
    
    # 创建HackerNews报告生成器
    hn_generator = ReportGeneratorFactory.create_generator("hacker_news", llm, config)
    
    # 生成HackerNews热门文章报告
    hn_report = hn_generator.generate_report(limit=10)
    LOG.info(f"HackerNews报告: {hn_report[:100]}...")

# 异步示例
async def run_async_example():
    LOG.info("运行异步示例...")
    
    # 加载配置
    config = load_config()
    
    # 创建LLM实例
    llm = MockLLM()
    
    # 创建GitHub报告生成器
    github_generator = ReportGeneratorFactory.create_generator("github", llm, config)
    
    # 异步生成GitHub仓库报告
    repo = "microsoft/vscode"
    report_task = github_generator.async_generate_repo_summary(repo, days=7)
    
    # 创建HackerNews报告生成器
    hn_generator = ReportGeneratorFactory.create_generator("hacker_news", llm, config)
    
    # 异步生成HackerNews热门文章报告
    hn_report_task = hn_generator.async_generate_top_stories_summary(limit=10)
    
    # 等待所有任务完成
    report, hn_report = await asyncio.gather(report_task, hn_report_task)
    
    LOG.info(f"异步GitHub报告: {report[:100]}...")
    LOG.info(f"异步HackerNews报告: {hn_report[:100]}...")

# 批量处理示例
async def run_batch_example():
    LOG.info("运行批量处理示例...")
    
    # 加载配置
    config = load_config()
    
    # 创建LLM实例
    llm = MockLLM()
    
    # 创建GitHub报告生成器
    github_generator = ReportGeneratorFactory.create_generator("github", llm, config)
    
    # 批量处理多个仓库
    repos = ["microsoft/vscode", "facebook/react", "tensorflow/tensorflow"]
    
    # 异步批量生成报告
    reports = await github_generator.async_generate_batch_repo_summaries(repos, days=7)
    
    for repo, report in reports.items():
        LOG.info(f"{repo} 报告: {report[:50]}...")

if __name__ == "__main__":
    # 运行同步示例
    run_sync_example()
    
    # 运行异步示例
    asyncio.run(run_async_example())
    
    # 运行批量处理示例
    asyncio.run(run_batch_example()) 