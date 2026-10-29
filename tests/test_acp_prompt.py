import unittest
from unittest import mock

from copilot_gateway.acp import ACPSession


class PromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_and_image_blocks_are_forwarded(self) -> None:
        session = ACPSession(
            command="copilot", args=(), cwd="/", model=None,
            on_event=mock.AsyncMock(), permission_handler=mock.AsyncMock(),
        )
        session._proc = mock.Mock(returncode=None)
        session.session_id = "session"
        session._request = mock.AsyncMock(return_value={})

        blocks = [{"type": "image", "data": "encoded", "mimeType": "image/png"}]
        for content, expected in (("hello", [{"type": "text", "text": "hello"}]), (blocks, blocks)):
            with self.subTest(content=content):
                await session.prompt(content)
                self.assertEqual(session._request.await_args.args[1]["prompt"], expected)


if __name__ == "__main__":
    unittest.main()
