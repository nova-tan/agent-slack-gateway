"""GitHub issue references used for stream channels."""

import asyncio
import re

_ISSUE_URL = re.compile(
    r"(?<![\w./-])https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


def parse_issue_url(text: str) -> tuple[str, str, int] | None:
    match = _ISSUE_URL.search(text)
    if match is None:
        return None
    return match.group(1), match.group(2), int(match.group(3))


async def fetch_issue_title(owner: str, repo: str, number: int) -> str:
    process = await asyncio.create_subprocess_exec(
        "gh", "issue", "view", str(number), "--repo", f"{owner}/{repo}", "--json", "title", "--jq", ".title",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 10)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError(f"Timed out fetching title for GitHub issue {owner}/{repo}#{number}.")
    if process.returncode:
        raise RuntimeError(f"Unable to fetch GitHub issue title: {stderr.decode(errors='replace').strip()}")
    title = stdout.decode(errors="replace").strip()
    if not title:
        raise RuntimeError(f"GitHub issue {owner}/{repo}#{number} has no title.")
    return title
