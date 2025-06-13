import asyncio
import sys
import os
import traceback # Import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


from config import Settings
from llm import LLM
from github_client import GitHubClient
from report_generator import ReportGenerator
from logger import LOG as SCRIPT_LOGGER

async def main():
    SCRIPT_LOGGER.info("Starting subscription report generation test...")
    try:
        config_file_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        SCRIPT_LOGGER.info(f"Attempting to load settings from: {config_file_path}")
        settings = Settings(config_file=config_file_path)

        SCRIPT_LOGGER.info(f"LLM settings: type={settings.get_llm_model_type()}, key={settings.get_openai_api_key()[:5]}...")

        llm_instance = LLM(settings=settings)

        class MockGitHubClient:
            def fetch_commits(self, *args, **kwargs): SCRIPT_LOGGER.debug(f"MockGitHubClient.fetch_commits called with {args}"); return []
            def fetch_issues(self, *args, **kwargs): SCRIPT_LOGGER.debug(f"MockGitHubClient.fetch_issues called with {args}"); return []
            def fetch_pull_requests(self, *args, **kwargs): SCRIPT_LOGGER.debug(f"MockGitHubClient.fetch_pull_requests called with {args}"); return []
            def get_recent_releases(self, *args, **kwargs): SCRIPT_LOGGER.debug(f"MockGitHubClient.get_recent_releases called with {args}"); return []

        github_client_mock = MockGitHubClient()

        report_gen = ReportGenerator(llm=llm_instance, settings=settings, github_client=github_client_mock)

        original_method = report_gen._generate_github_project_basic_info_markdown
        calls = []
        def patched_method(owner, repo_name, days):
            SCRIPT_LOGGER.info(f"Patched _generate_github_project_basic_info_markdown CALLED FOR {owner}/{repo_name}")
            calls.append((owner, repo_name))
            return f"Mocked basic info for {owner}/{repo_name}"
        report_gen._generate_github_project_basic_info_markdown = patched_method

        SCRIPT_LOGGER.info("Generating GitHub subscription report...")
        report_content = report_gen.generate_github_subscription_report()

        SCRIPT_LOGGER.info(f"Report content (first 100 chars): {report_content[:100]}...")
        SCRIPT_LOGGER.info(f"_generate_github_project_basic_info_markdown WAS CALLED FOR: {calls}")

        expected_calls = [
            ('testowner1', 'testrepo1'),
            ('testowner2', 'testrepo2'),
            ('testowner3', 'testrepo3'),
            ('testowner4', 'testrepo4')
        ]

        if set(calls) == set(expected_calls):
            SCRIPT_LOGGER.info("SUCCESS: _generate_github_project_basic_info_markdown called for all expected valid subscriptions.")
        else:
            # This SCRIPT_LOGGER.error is a potential source of the NameError if it's an error path.
            # However, the error 'e' is NameError for LOG, not SCRIPT_LOGGER.
            SCRIPT_LOGGER.error(f"FAILURE: Call mismatch. Expected: {expected_calls}, Got: {calls}")

        report_gen._generate_github_project_basic_info_markdown = original_method

    except Exception as e:
        from logger import LOG as FALLBACK_LOGGER # Keep this import local to except block
        tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__)) # Corrected call
        FALLBACK_LOGGER.error(f"Test script failed (using fallback logger): {e}\nTRACEBACK:\n{tb_str}")

        try:
            if SCRIPT_LOGGER:
                SCRIPT_LOGGER.info("SCRIPT_LOGGER still exists in except block.")
            else:
                FALLBACK_LOGGER.warning("SCRIPT_LOGGER is None or False in except block.")
        except NameError:
            FALLBACK_LOGGER.warning("SCRIPT_LOGGER is NOT DEFINED in except block.")
        except Exception as e_diag:
            FALLBACK_LOGGER.error(f"Error during SCRIPT_LOGGER diagnostic: {e_diag}")

if __name__ == "__main__":
    asyncio.run(main())
