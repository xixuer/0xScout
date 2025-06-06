# src/command_handler.py

import argparse  # 导入argparse库，用于处理命令行参数解析

class CommandHandler:
    def __init__(self, github_client, subscription_manager, report_generator, hacker_news_client): # Added hacker_news_client
        # 初始化CommandHandler，接收GitHub客户端、订阅管理器和报告生成器
        self.github_client = github_client
        self.subscription_manager = subscription_manager
        self.report_generator = report_generator
        self.hacker_news_client = hacker_news_client # Added
        self.parser = self.create_parser()  # 创建命令行解析器

    def create_parser(self):
        # 创建并配置命令行解析器
        parser = argparse.ArgumentParser(
            description='0xScout Command Line Interface',
            formatter_class=argparse.RawTextHelpFormatter
        )
        subparsers = parser.add_subparsers(title='Commands', dest='command')

        # 添加订阅命令
        parser_add = subparsers.add_parser('add', help='Add a subscription')
        parser_add.add_argument('repo', type=str, help='The repository to subscribe to (e.g., owner/repo)')
        parser_add.set_defaults(func=self.add_subscription)

        # 删除订阅命令
        parser_remove = subparsers.add_parser('remove', help='Remove a subscription')
        parser_remove.add_argument('repo', type=str, help='The repository to unsubscribe from (e.g., owner/repo)')
        parser_remove.set_defaults(func=self.remove_subscription)

        # 列出所有订阅命令
        parser_list = subparsers.add_parser('list', help='List all subscriptions')
        parser_list.set_defaults(func=self.list_subscriptions)

        # 导出每日进展命令
        parser_export = subparsers.add_parser('export', help='Export daily progress')
        parser_export.add_argument('repo', type=str, help='The repository to export progress from (e.g., owner/repo)')
        parser_export.set_defaults(func=self.export_daily_progress)

        # 导出特定日期范围进展命令
        parser_export_range = subparsers.add_parser('export-range', help='Export progress over a range of dates')
        parser_export_range.add_argument('repo', type=str, help='The repository to export progress from (e.g., owner/repo)')
        parser_export_range.add_argument('days', type=int, help='The number of days to export progress for')
        parser_export_range.set_defaults(func=self.export_progress_by_date_range)

        # 生成日报命令
        parser_generate = subparsers.add_parser('generate', help='Generate daily report from markdown file')
        parser_generate.add_argument('file', type=str, help='The markdown file to generate report from')
        parser_generate.set_defaults(func=self.generate_daily_report)

        # 帮助命令
        parser_help = subparsers.add_parser('help', help='Show help message')
        parser_help.set_defaults(func=self.print_help)

        # Hacker News fetch command
        parser_hn_fetch = subparsers.add_parser('hn-fetch', help='Fetch latest Hacker News stories and save to file')
        parser_hn_fetch.set_defaults(func=self.hn_fetch)

        # Hacker News hourly report command
        parser_hn_hourly = subparsers.add_parser('hn-hourly-report', help='Generate Hacker News hourly report for a specific date and hour')
        parser_hn_hourly.add_argument('date', type=str, help='Date in YYYY-MM-DD format')
        parser_hn_hourly.add_argument('hour', type=str, help='Hour in HH format (e.g., 09, 15)')
        parser_hn_hourly.set_defaults(func=self.hn_hourly_report)

        # Hacker News daily report command
        parser_hn_daily = subparsers.add_parser('hn-daily-report', help='Generate Hacker News daily summary for a specific date')
        parser_hn_daily.add_argument('date', type=str, help='Date in YYYY-MM-DD format')
        parser_hn_daily.set_defaults(func=self.hn_daily_report)

        return parser  # 返回配置好的解析器

    # 下面是各种命令对应的方法实现，每个方法都使用了相应的管理器来执行实际操作，并输出结果信息
    def add_subscription(self, args):
        self.subscription_manager.add_subscription(args.repo)
        print(f"Added subscription for repository: {args.repo}")

    def remove_subscription(self, args):
        self.subscription_manager.remove_subscription(args.repo)
        print(f"Removed subscription for repository: {args.repo}")

    def list_subscriptions(self, args):
        subscriptions = self.subscription_manager.list_subscriptions()
        print("Current subscriptions:")
        for sub in subscriptions:
            print(f"  - {sub}")

    def export_daily_progress(self, args):
        self.github_client.export_daily_progress(args.repo)
        print(f"Exported daily progress for repository: {args.repo}")

    def export_progress_by_date_range(self, args):
        self.github_client.export_progress_by_date_range(args.repo, days=args.days)
        print(f"Exported progress for the last {args.days} days for repository: {args.repo}")

    def generate_daily_report(self, args):
        self.report_generator.generate_github_report(args.file)
        print(f"Generated daily report from file: {args.file}")

    def hn_fetch(self, args):
        print("Fetching latest Hacker News stories...")
        file_path = self.hacker_news_client.export_top_stories()
        if file_path:
            print(f"Hacker News stories saved to: {file_path}")
        else:
            print("Failed to fetch Hacker News stories.")

    def hn_hourly_report(self, args):
        print(f"Generating Hacker News hourly report for {args.date} {args.hour}:00...")
        report = self.report_generator.get_hacker_news_hourly_report(args.date, args.hour)
        print(report)

    def hn_daily_report(self, args):
        print(f"Generating Hacker News daily summary for {args.date}...")
        report = self.report_generator.get_hacker_news_daily_summary(args.date)
        print(report)

    def print_help(self, args=None):
        self.parser.print_help()  # 输出帮助信息
