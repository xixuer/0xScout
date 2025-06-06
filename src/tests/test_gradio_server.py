import unittest
from unittest.mock import patch, Mock, MagicMock
import sys
import os

# Add src directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Need to import the specific functions or classes we are testing from gradio_server
# However, gradio_server itself executes code on import (like creating clients, config).
# This can be problematic. For robust unit testing, these should ideally be refactored
# to be passed into functions or classes.
# For now, we'll try to patch the global objects it uses.

# Attempt to import the function to be tested
# If gradio_server.py has top-level code that causes side effects (e.g. API calls, file reads),
# this import itself could be an issue. Assume it's manageable for now.
from gradio_server import generate_hn_hour_topic, config as gradio_config
# We also need to patch objects used by generate_hn_hour_topic,
# such as hacker_news_client, ReportGenerator, LLM, LOG

class TestGradioHnFunctions(unittest.TestCase):

    # Patch global objects used within gradio_server.py's functions
    # These patches will apply to all tests in this class.
    # Note: Patching 'src.gradio_server.config' might be tricky if it's just a module import.
    # It's better to patch specific attributes or objects if possible.
    # For 'config', since it's used to instantiate LLM and ReportGenerator inside the function,
    # we might need to patch those classes directly.

    @patch('src.gradio_server.hacker_news_client') # Mock the global hacker_news_client instance
    @patch('src.gradio_server.ReportGenerator') # Mock the ReportGenerator class
    @patch('src.gradio_server.LLM') # Mock the LLM class
    @patch('src.gradio_server.LOG') # Mock the LOG object
    def test_generate_hn_hour_topic_success(self, mock_log, mock_llm_class, mock_report_generator_class, mock_hn_client):
        # Configure mocks
        mock_hn_client.export_top_stories.return_value = "hacker_news/2023-10-27/15.md"

        mock_report_generator_instance = Mock()
        mock_report_generator_instance.get_hacker_news_hourly_report.return_value = "Test Hourly Report"
        mock_report_generator_class.return_value = mock_report_generator_instance

        # Mock LLM instance if ReportGenerator instantiation depends on it, though it's part of ReportGenerator mock here
        mock_llm_instance = Mock()
        mock_llm_class.return_value = mock_llm_instance

        # Call the function
        # The global 'config' object from gradio_server will be used. We assume its default state is fine,
        # or we would need a more complex way to manipulate it for the test.
        result_report, result_file = generate_hn_hour_topic("ollama", "llama3")

        # Assertions
        self.assertEqual(result_report, "Test Hourly Report")
        self.assertIsNone(result_file)
        mock_hn_client.export_top_stories.assert_called_once()
        mock_report_generator_class.assert_called_once_with(mock_llm_instance, gradio_config, gradio_config.github_client) # check instantiation
        mock_report_generator_instance.get_hacker_news_hourly_report.assert_called_once_with("2023-10-27", "15")
        mock_log.error.assert_not_called()


    @patch('src.gradio_server.hacker_news_client')
    @patch('src.gradio_server.ReportGenerator') # Still need to mock this as it's instantiated
    @patch('src.gradio_server.LLM')
    @patch('src.gradio_server.LOG')
    def test_generate_hn_hour_topic_export_fails(self, mock_log, mock_llm_class, mock_report_generator_class, mock_hn_client):
        mock_hn_client.export_top_stories.return_value = None

        # Ensure ReportGenerator is not called if export fails early
        mock_report_generator_instance = Mock()
        mock_report_generator_class.return_value = mock_report_generator_instance

        result_report, result_file = generate_hn_hour_topic("ollama", "llama3")

        self.assertIn("Error: Could not fetch Hacker News data", result_report)
        self.assertIsNone(result_file)
        mock_hn_client.export_top_stories.assert_called_once()
        mock_report_generator_instance.get_hacker_news_hourly_report.assert_not_called()
        mock_log.error.assert_called_with("Gradio: Could not fetch Hacker News data. File path is None.")


    @patch('src.gradio_server.hacker_news_client')
    @patch('src.gradio_server.ReportGenerator') # Mocked to prevent actual instantiation or calls
    @patch('src.gradio_server.LLM')
    @patch('src.gradio_server.LOG')
    def test_generate_hn_hour_topic_path_parse_error(self, mock_log, mock_llm_class, mock_report_generator_class, mock_hn_client):
        mock_hn_client.export_top_stories.return_value = "invalid/path.md" # Invalid path for parsing

        mock_report_generator_instance = Mock()
        mock_report_generator_class.return_value = mock_report_generator_instance

        result_report, result_file = generate_hn_hour_topic("ollama", "llama3")

        self.assertIn("Error: Could not parse date/hour from file path", result_report)
        self.assertIsNone(result_file)
        mock_hn_client.export_top_stories.assert_called_once()
        # Ensure the actual report generation method wasn't called due to parsing error
        mock_report_generator_instance.get_hacker_news_hourly_report.assert_not_called()
        mock_log.error.assert_any_call(f"Gradio: Could not parse date/hour from file path: invalid/path.md")


    @patch('src.gradio_server.github_client') # Mock the global github_client instance
    @patch('src.gradio_server.ReportGenerator') # Mock the ReportGenerator class
    @patch('src.gradio_server.LLM') # Mock the LLM class
    @patch('src.gradio_server.LOG') # Mock the LOG object
    def test_generate_github_report_instantiation(self, mock_log, mock_llm_class, mock_report_generator_class, mock_gh_client):
        # This test specifically checks the ReportGenerator instantiation in generate_github_report
        # It's not a full test of generate_github_report, just the part that was changed.

        mock_gh_client.export_progress_by_date_range.return_value = "mock/path/to/progress.md"

        mock_report_generator_instance = Mock()
        mock_report_generator_instance.generate_github_report.return_value = ("GH Report", "gh_report.md")
        mock_report_generator_class.return_value = mock_report_generator_instance

        mock_llm_instance = Mock()
        mock_llm_class.return_value = mock_llm_instance

        from gradio_server import generate_github_report # Import here to use fresh mocks

        generate_github_report("ollama", "llama3", "owner/repo", 3)

        # Assert that ReportGenerator was instantiated correctly
        # The key here is that 'gradio_config.github_client' would resolve to the mocked 'mock_gh_client'
        # IF 'gradio_config' was also patched or if 'github_client' was directly patched at 'src.gradio_server.github_client'
        # The current setup for generate_hn_hour_topic patches src.gradio_server.hacker_news_client, so this should work similarly.
        mock_report_generator_class.assert_called_once_with(mock_llm_instance, gradio_config, mock_gh_client)


if __name__ == '__main__':
    unittest.main()
