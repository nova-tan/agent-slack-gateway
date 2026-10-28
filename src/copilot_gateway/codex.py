"""Codex app-server adapter implementing the gateway session interface."""
from __future__ import annotations

import asyncio
import time
from typing import Any

from .acp import ACPSession, PromptContent, SessionDeadError


class CodexSession(ACPSession):
    def __init__(self, *, approval_mode: str, **kwargs: Any) -> None:
        super().__init__(args=('app-server', '--stdio'), **kwargs)
        self.approval_mode = approval_mode
        self._turn_id: str | None = None
        self._turn_done: asyncio.Future[dict[str, Any]] | None = None

    async def start(self) -> None:
        if self.alive:
            return
        self._stopping = False
        try:
            self._proc = await asyncio.create_subprocess_exec(
                self.command, *self.args, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd, limit=16 * 1024 * 1024,
            )
        except FileNotFoundError as exc:
            raise SessionDeadError(f'Codex binary not found: {self.command!r}') from exc
        self.pid = self._proc.pid
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._stderr_loop())
        try:
            await self._request('initialize', {'clientInfo': {
                'name': 'slack_gateway', 'title': 'Slack Gateway', 'version': '0.1.0'}})
            await self._notify('initialized', {})
            result = await self._request('thread/start', {
                'cwd': self.cwd, 'model': self.model,
                'approvalPolicy': 'never' if self.approval_mode == 'auto' else 'on-request',
                'sandbox': 'danger-full-access' if self.approval_mode == 'auto' else 'workspace-write',
            })
            self.session_id = result['thread']['id']
            self.created_at = time.time()
        except BaseException:
            await self.close()
            raise

    async def prompt(self, content: PromptContent) -> dict[str, Any]:
        async with self._prompt_lock:
            if not self.alive:
                raise SessionDeadError('Codex session is not alive.')
            self._cancel_requested = False
            blocks = [{'type': 'text', 'text': content}] if isinstance(content, str) else content
            inputs = []
            for block in blocks:
                if block['type'] == 'text':
                    inputs.append({'type': 'text', 'text': block['text']})
                elif block['type'] == 'image':
                    inputs.append({'type': 'image', 'url': f"data:{block['mimeType']};base64,{block['data']}"})
                else:
                    raise ValueError(f"Unsupported prompt content: {block['type']}")
            self._turn_done = asyncio.get_running_loop().create_future()
            try:
                result = await self._request('turn/start', {'threadId': self.session_id, 'input': inputs}, timeout=self.prompt_timeout)
                self._turn_id = result['turn']['id']
                if self._cancel_requested:
                    await self._interrupt()
                turn = await asyncio.wait_for(self._turn_done, self.prompt_timeout)
                status = turn.get('status')
                if status == 'failed':
                    raise RuntimeError(str(turn.get('error') or 'Codex turn failed'))
                return {'stopReason': 'cancelled' if status == 'interrupted' else 'end_turn'}
            except asyncio.TimeoutError:
                await self.close()
                raise
            finally:
                self._turn_id = None
                self._turn_done = None
                self._active_tools.clear()

    async def _interrupt(self) -> None:
        if self._turn_id:
            await self._request('turn/interrupt', {'threadId': self.session_id, 'turnId': self._turn_id})

    async def cancel(self) -> None:
        if self.alive and self.busy():
            self._cancel_requested = True
            await self._interrupt()

    def _on_process_exit(self) -> None:
        if self._turn_done and not self._turn_done.done():
            self._turn_done.set_exception(SessionDeadError('Codex process exited'))
        if self._stopping:
            return
        self.session_id = None
        self._active_tools.clear()
        for future in self._pending.values():
            if not future.done():
                future.set_exception(SessionDeadError('Codex process exited'))
        self._pending.clear()
        asyncio.create_task(self.on_event('error', {'message': 'Codex process exited; the next message will start a fresh session.'}))

    async def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if params.get('threadId') not in (None, self.session_id):
            return
        if method == 'turn/completed':
            if self._turn_done and not self._turn_done.done():
                self._turn_done.set_result(params.get('turn') or {})
        elif method == 'item/agentMessage/delta':
            await self.on_event('text', {'text': params.get('delta', '')})
        elif method in ('item/reasoning/summaryTextDelta', 'item/reasoning/textDelta'):
            await self.on_event('thought', {'text': params.get('delta', '')})
        elif method in ('item/started', 'item/completed'):
            item = params.get('item') or {}
            kind = item.get('type', '')
            if kind in ('agentMessage', 'userMessage', 'reasoning'):
                return
            item_id = item.get('id')
            status = 'completed' if method == 'item/completed' else 'in_progress'
            task = {'title': str(item.get('command') or kind), 'kind': str(kind), 'status': status}
            if item_id:
                if status == 'completed':
                    self._active_tools.pop(item_id, None)
                else:
                    self._active_tools[item_id] = task
            await self.on_event('tool', task)

    async def _handle_server_request(self, msg: dict[str, Any]) -> None:
        method, params = msg['method'], msg.get('params') or {}
        if method in ('item/commandExecution/requestApproval', 'item/fileChange/requestApproval'):
            try:
                choice = await self.permission_handler({
                    'toolCall': {'title': params.get('reason') or params.get('command') or method,
                                 'kind': method, 'rawInput': params},
                    'options': [{'optionId': 'accept', 'name': 'Approve', 'kind': 'allow_once'}],
                })
                decision = 'accept' if choice == 'accept' else 'decline'
            except Exception:
                decision = 'decline'
            await self._write({'id': msg['id'], 'result': {'decision': decision}})
        else:
            await self._write({'id': msg['id'], 'error': {'code': -32601, 'message': 'Unsupported request'}})
