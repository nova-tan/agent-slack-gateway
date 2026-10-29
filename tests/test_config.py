import unittest
from unittest import mock

from copilot_gateway.config import Config


class WorkspaceConfigTests(unittest.TestCase):
    @mock.patch("copilot_gateway.config.load_local_env")
    def test_workspace_url_is_required(self, _load_env) -> None:
        for value in ("", "  ", "/"):
            with self.subTest(value=value), mock.patch.dict(
                "os.environ",
                {"SLACK_BOT_TOKEN": "bot", "SLACK_APP_TOKEN": "app", "SLACK_WORKSPACE_URL": value},
                clear=True,
            ):
                with self.assertRaisesRegex(SystemExit, "SLACK_WORKSPACE_URL is required"):
                    Config.from_env()

    @mock.patch("copilot_gateway.config.load_mcp_servers", return_value=[])
    @mock.patch("copilot_gateway.config.load_local_env")
    def test_workspace_url_uses_configured_value(self, _load_env, _load_mcp) -> None:
        with mock.patch.dict(
            "os.environ",
            {"SLACK_BOT_TOKEN": "bot", "SLACK_APP_TOKEN": "app",
             "SLACK_WORKSPACE_URL": " https://example.slack.com/ "},
            clear=True,
        ):
            self.assertEqual(Config.from_env().slack_workspace_url, "https://example.slack.com")


if __name__ == "__main__":
    unittest.main()
