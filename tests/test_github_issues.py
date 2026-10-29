import unittest
from unittest import mock

from copilot_gateway.github_issues import fetch_issue_title, parse_issue_url


class IssueUrlTests(unittest.TestCase):
    def test_issue_url_in_slack_text(self) -> None:
        self.assertEqual(
            parse_issue_url("<https://github.com/acme/widget/issues/42|issue>"),
            ("acme", "widget", 42),
        )

    def test_other_urls_are_not_issues(self) -> None:
        for url in ("https://github.com/acme/widget/pull/42", "https://github.com.example/acme/widget/issues/42"):
            with self.subTest(url=url):
                self.assertIsNone(parse_issue_url(url))


class IssueTitleTests(unittest.IsolatedAsyncioTestCase):
    @mock.patch("copilot_gateway.github_issues.asyncio.create_subprocess_exec")
    async def test_title_and_failure(self, create_process) -> None:
        process = mock.Mock(returncode=0)
        process.communicate = mock.AsyncMock(return_value=(b"Fix the bug\n", b""))
        create_process.return_value = process
        self.assertEqual(await fetch_issue_title("acme", "widget", 42), "Fix the bug")
        self.assertEqual(create_process.await_args.args[:6], ("gh", "issue", "view", "42", "--repo", "acme/widget"))

        process.returncode = 1
        process.communicate.return_value = (b"", b"not found")
        with self.assertRaisesRegex(RuntimeError, "not found"):
            await fetch_issue_title("acme", "widget", 42)


if __name__ == "__main__":
    unittest.main()
