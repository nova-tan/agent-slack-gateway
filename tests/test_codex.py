import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from copilot_gateway.codex import CodexSession
from copilot_gateway.config import Config
from copilot_gateway.sessions import SessionRegistry


class CodexTests(unittest.IsolatedAsyncioTestCase):
    def session(self):
        return CodexSession(command='codex', cwd='/tmp', model=None,
                            on_event=AsyncMock(), permission_handler=AsyncMock(return_value='accept'),
                            approval_mode='buttons')

    async def test_notifications_stream_and_track_tasks(self):
        session = self.session()
        session.session_id = 'thread'
        await session._handle_notification('item/agentMessage/delta', {'threadId': 'thread', 'delta': 'hello'})
        session.on_event.assert_awaited_with('text', {'text': 'hello'})
        item = {'id': 'x', 'type': 'commandExecution', 'command': 'ls'}
        await session._handle_notification('item/started', {'threadId': 'thread', 'item': item})
        self.assertEqual(session.active_tasks()[0]['title'], 'ls')
        await session._handle_notification('item/completed', {'threadId': 'thread', 'item': item})
        self.assertEqual(session.active_tasks(), [])

    async def test_approval_and_denial(self):
        session = self.session()
        session._write = AsyncMock()
        request = {'id': 1, 'method': 'item/commandExecution/requestApproval', 'params': {'command': 'ls'}}
        await session._handle_server_request(request)
        session._write.assert_awaited_with({'id': 1, 'result': {'decision': 'accept'}})
        session.permission_handler.return_value = None
        await session._handle_server_request(request)
        session._write.assert_awaited_with({'id': 1, 'result': {'decision': 'decline'}})

    async def test_turn_and_image_and_interrupt(self):
        session = self.session()
        session.session_id = 'thread'
        session._proc = unittest.mock.Mock(returncode=None)
        async def request(method, params, **kwargs):
            if method == 'turn/start':
                self.assertEqual(params['input'][1]['url'], 'data:image/png;base64,YQ==')
                asyncio.get_running_loop().call_soon(session._turn_done.set_result, {'status': 'interrupted'})
                return {'turn': {'id': 'turn'}}
        session._request = AsyncMock(side_effect=request)
        result = await session.prompt([{'type': 'text', 'text': 'hi'}, {'type': 'image', 'mimeType': 'image/png', 'data': 'YQ=='}])
        self.assertEqual(result['stopReason'], 'cancelled')

    async def test_registry_selects_codex(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = SessionRegistry(Config(slack_bot_token='x', slack_app_token='y', provider='codex', cwd=directory, state_dir=Path(directory)))
            conv, _ = await registry.get_or_create('x', channel='x', thread_ts=None,
                on_event_factory=lambda c: AsyncMock(), permission_handler_factory=lambda c: AsyncMock())
            self.assertIsInstance(conv.session, CodexSession)
            await registry.close_all()
