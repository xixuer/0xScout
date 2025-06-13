#!/usr/bin/env python3
"""
0xScout 主入口文件
"""
import os
import sys
import argparse
import asyncio
import json
from datetime import datetime

# 将项目根目录添加到系统路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from src.generators.report_generator_factory import ReportGeneratorFactory
    from src.logger import LOG
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    LOG = logging.getLogger(__name__)
    LOG.error("导入模块失败，请确保项目结构正确")
    sys.exit(1)

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
    config_path = os.path.join(project_root, 'config.json')
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

async def generate_github_report(args):
    """生成GitHub报告"""
    config = load_config()
    llm = MockLLM()
    
    github_generator = ReportGeneratorFactory.create_generator("github", llm, config)
    
    if args.batch:
        # 批量生成报告
        repos = args.repos.split(',')
        LOG.info(f"批量生成 {len(repos)} 个仓库的报告")
        
        reports = await github_generator.async_generate_batch_repo_summaries(repos, days=args.days)
        
        for repo, report in reports.items():
            print(f"\n=== {repo} 报告 ===\n")
            print(report)
    else:
        # 生成单个仓库报告
        repo = args.repo
        LOG.info(f"生成仓库 {repo} 的报告")
        
        if args.async_mode:
            report = await github_generator.async_generate_repo_summary(repo, days=args.days)
        else:
            report = github_generator.generate_repo_summary(repo, days=args.days)
        
        print(report)

async def generate_hackernews_report(args):
    """生成HackerNews报告"""
    config = load_config()
    llm = MockLLM()
    
    hn_generator = ReportGeneratorFactory.create_generator("hacker_news", llm, config)
    
    if args.story_id:
        # 生成文章评论报告
        LOG.info(f"生成文章 {args.story_id} 的评论报告")
        
        if args.async_mode:
            report = await hn_generator.async_generate_story_comments_summary(args.story_id, limit=args.limit)
        else:
            report = hn_generator.generate_story_comments_summary(args.story_id, limit=args.limit)
    else:
        # 生成热门文章报告
        LOG.info(f"生成热门文章报告 (前 {args.limit} 条)")
        
        if args.async_mode:
            report = await hn_generator.async_generate_top_stories_summary(limit=args.limit)
        else:
            report = hn_generator.generate_top_stories_summary(limit=args.limit)
    
    print(report)

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='0xScout - 技术情报收集与分析工具')
    subparsers = parser.add_subparsers(dest='command', help='子命令')
    
    # GitHub命令
    github_parser = subparsers.add_parser('github', help='生成GitHub报告')
    github_parser.add_argument('--repo', type=str, help='仓库名称 (格式: owner/repo)')
    github_parser.add_argument('--days', type=int, default=7, help='过去多少天的数据 (默认: 7)')
    github_parser.add_argument('--async', dest='async_mode', action='store_true', help='使用异步模式')
    github_parser.add_argument('--batch', action='store_true', help='批量处理多个仓库')
    github_parser.add_argument('--repos', type=str, help='仓库列表，用逗号分隔 (格式: owner1/repo1,owner2/repo2)')
    
    # HackerNews命令
    hn_parser = subparsers.add_parser('hackernews', help='生成HackerNews报告')
    hn_parser.add_argument('--story-id', type=int, help='文章ID')
    hn_parser.add_argument('--limit', type=int, default=30, help='获取的文章或评论数量 (默认: 30)')
    hn_parser.add_argument('--async', dest='async_mode', action='store_true', help='使用异步模式')
    
    # 示例命令
    example_parser = subparsers.add_parser('example', help='运行示例代码')
    
    return parser.parse_args()

async def run_example():
    """运行示例代码"""
    LOG.info("运行示例代码...")
    
    # 导入示例模块
    try:
        from src.examples.example import run_sync_example, run_async_example, run_batch_example
        
        # 运行同步示例
        run_sync_example()
        
        # 运行异步示例
        await run_async_example()
        
        # 运行批量处理示例
        await run_batch_example()
    except ImportError as e:
        LOG.error(f"导入示例模块失败: {e}")
        print("示例模块导入失败，请确保项目结构正确")

async def main():
    """主函数"""
    args = parse_args()
    
    if args.command == 'github':
        if args.batch and not args.repos:
            print("错误: 批量处理模式需要提供 --repos 参数")
            return
        if not args.batch and not args.repo:
            print("错误: 需要提供 --repo 参数")
            return
        
        await generate_github_report(args)
    elif args.command == 'hackernews':
        await generate_hackernews_report(args)
    elif args.command == 'example':
        await run_example()
    else:
        print("请指定子命令: github, hackernews 或 example")
        print("使用 -h 或 --help 查看帮助")

if __name__ == "__main__":
    asyncio.run(main())
