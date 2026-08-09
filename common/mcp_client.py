"""
Shared MCP client helper. Every agent that needs to call an MCP server
(ado_mcp, ppt_mcp, archive) uses this instead of writing its own connection
boilerplate — we wrote near-identical versions of this three times in the
first pass of this project; this is the one copy, shared.
"""
import json
import re
from contextlib import asynccontextmanager
from typing import Any, Optional

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# Some MCP servers (the official ADO one, notably) wrap tool results in an
# untrusted-content delimiter banner as their own prompt-injection defense —
# e.g. "<<hash>> [UNTRUSTED ... CONTENT] <<hash>>\n{json}\n<</hash>>". An LLM
# consuming this directly (as Claude does inside the Agent SDK's tool-use
# loop) is expected to understand and work around it. Plain Python code
# calling a tool directly (not through an agent loop) is not — so we strip
# it here before attempting to parse the real payload underneath.
_UNTRUSTED_WRAPPER_RE = re.compile(r"^<<[0-9a-f]+>>.*?<<[0-9a-f]+>>\s*\n(.*)\n<</[0-9a-f]+>>\s*$", re.DOTALL)


@asynccontextmanager
async def open_mcp_client(command: str, args: list[str], env: Optional[dict[str, str]] = None):
    """
    Async context manager: spawns an MCP server, connects, yields a client
    wrapper with a `call(tool_name, arguments)` coroutine, and cleans up
    automatically on exit.

    Usage:
        async with open_mcp_client("node", ["../mcp_servers/ado_mcp/..."]) as client:
            result = await client.call("wit_query", {...})
    """
    server_params = StdioServerParameters(command=command, args=args, env=env)
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield _McpClient(session)


class _McpClient:
    def __init__(self, session: ClientSession):
        self._session = session

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        result = await self._session.call_tool(tool_name, arguments)
        text_block = next((b for b in result.content if hasattr(b, "text")), None)
        if text_block is None:
            return None
        text = text_block.text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try stripping an untrusted-content delimiter wrapper, if present.
        match = _UNTRUSTED_WRAPPER_RE.match(text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return text  # genuinely not JSON — some tools legitimately return plain text

    async def list_tools(self) -> list[str]:
        tools = await self._session.list_tools()
        return [t.name for t in tools.tools]
