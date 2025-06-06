import unittest
from unittest.mock import Mock, patch, MagicMock, call
import sys
import os
import argparse

# Add src directory to Python path to allow direct import of modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from command_handler import CommandHandler
from github_client import GitHubClient
from subscription_manager import SubscriptionManager
from report_generator import ReportGenerator
from hacker_news_client import HackerNewsClient
from llm import LLM # Needed for ReportGenerator instantiation if not deeply mocked
from config import Config # Needed for ReportGenerator instantiation if not deeply mocked

class TestHackerNewsCommands(unittest.TestCase):

    def setUp(self):
        # Create mock objects for all dependencies of CommandHandler
        self.mock_github_client = Mock(spec=GitHubClient)
        self.mock_subscription_manager = Mock(spec=SubscriptionManager)

        # Mock ReportGenerator and its methods that will be called
        self.mock_report_generator = Mock(spec=ReportGenerator)
        self.mock_report_generator.get_hacker_news_hourly_report = Mock(return_value="Hourly Report Content")
        self.mock_report_generator.get_hacker_news_daily_summary = Mock(return_value="Daily Summary Content")

        self.mock_hacker_news_client = Mock(spec=HackerNewsClient)

        # Instantiate CommandHandler with the mocked dependencies
        self.handler = CommandHandler(
            github_client=self.mock_github_client,
            subscription_manager=self.mock_subscription_manager,
            report_generator=self.mock_report_generator,
            hacker_news_client=self.mock_hacker_news_client
        )

    @patch('builtins.print')
    def test_hn_fetch_command(self, mock_print):
        # Test successful fetch
        self.mock_hacker_news_client.export_top_stories.return_value = "/path/to/hn_stories.md"
        # Simulate calling through argparser by directly calling the method
        # In a real scenario, parser.parse_args(['hn-fetch']).func(args) would be called
        # For simplicity, we directly call the method as args is not used by hn_fetch
        self.handler.hn_fetch(None)
        self.mock_hacker_news_client.export_top_stories.assert_called_once()
        mock_print.assert_any_call("Fetching latest Hacker News stories...")
        mock_print.assert_any_call("Hacker News stories saved to: /path/to/hn_stories.md")

        # Reset mock for next scenario
        self.mock_hacker_news_client.export_top_stories.reset_mock()
        mock_print.reset_mock()

        # Test failed fetch
        self.mock_hacker_news_client.export_top_stories.return_value = None
        self.handler.hn_fetch(None)
        self.mock_hacker_news_client.export_top_stories.assert_called_once()
        mock_print.assert_any_call("Fetching latest Hacker News stories...")
        mock_print.assert_any_call("Failed to fetch Hacker News stories.")

    @patch('builtins.print')
    def test_hn_hourly_report_command(self, mock_print):
        # Create mock args for the command
        mock_args = argparse.Namespace(date='2023-01-01', hour='12')

        self.handler.hn_hourly_report(mock_args)

        self.mock_report_generator.get_hacker_news_hourly_report.assert_called_once_with('2023-01-01', '12')
        mock_print.assert_any_call("Generating Hacker News hourly report for 2023-01-01 12:00...")
        mock_print.assert_any_call("Hourly Report Content")

    @patch('builtins.print')
    def test_hn_daily_report_command(self, mock_print):
        # Create mock args for the command
        mock_args = argparse.Namespace(date='2023-01-01')

        self.handler.hn_daily_report(mock_args)

        self.mock_report_generator.get_hacker_news_daily_summary.assert_called_once_with('2023-01-01')
        mock_print.assert_any_call("Generating Hacker News daily summary for 2023-01-01...")
        mock_print.assert_any_call("Daily Summary Content")

if __name__ == '__main__':
    unittest.main()
