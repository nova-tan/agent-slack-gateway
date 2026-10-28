"""Helpers for deriving stream names from GitHub issue URLs."""
from __future__ import annotations

import asyncio
import json
import re


def parse_issue_url(value: str) -> tuple[str, str, int] | None:
    match = re.fullmatch(r'https://github\.com/([\w.-]+)/([\w.-]+)/issues/([0-9]+)/?', value.strip())
    if not match:
        return None
    return match.group(1), match.group(2), int(match.group(3))


async def fetch_issue_title(owner: str, repo: str, number: int) -> str | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            'gh', 'issue', 'view', str(number), '--repo', f'{owner}/{repo}',
            '--json', 'title', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            output, _ = await asyncio.wait_for(proc.communicate(), 10)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return None
        return str(json.loads(output).get('title') or '') or None if proc.returncode == 0 else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None
