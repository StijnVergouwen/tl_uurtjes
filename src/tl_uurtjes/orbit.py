"""Minimal client for the official Teamleader Orbit MCP server (OAuth + tool calls)."""

import asyncio
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.shared.auth import (
    AuthorizationCodeResult,
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)

from .core import CONFIG_DIR

MCP_URL = "https://api.orbit.teamleader.eu/mcp"
CALLBACK_PORT = 8765
REDIRECT_URI = f"http://127.0.0.1:{CALLBACK_PORT}/callback"


class FileTokenStorage(TokenStorage):
    """Keeps the OAuth client registration and tokens in a private JSON file."""

    def __init__(self, path: Path = CONFIG_DIR / "oauth.json"):
        self.path = path

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.touch(mode=0o600)
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.path)

    async def get_tokens(self) -> OAuthToken | None:
        raw = self._load().get("tokens")
        return OAuthToken.model_validate(raw) if raw else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = self._load()
        data["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
        self._save(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        raw = self._load().get("client")
        return OAuthClientInformationFull.model_validate(raw) if raw else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        data = self._load()
        data["client"] = client_info.model_dump(mode="json", exclude_none=True)
        self._save(data)


def is_logged_in() -> bool:
    return bool(FileTokenStorage()._load().get("tokens"))


async def _open_browser(url: str) -> None:
    print(f"Opening Orbit login in your browser:\n{url}", flush=True)
    webbrowser.open(url)


async def _wait_for_callback() -> AuthorizationCodeResult:
    """Serves the OAuth redirect on 127.0.0.1 and returns the authorization code."""
    loop = asyncio.get_running_loop()
    result: asyncio.Future[dict[str, list[str]]] = loop.create_future()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            if url.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            params = parse_qs(url.query)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>Ingelogd bij Orbit. Je kunt dit venster sluiten.</h2>".encode())
            loop.call_soon_threadsafe(lambda: result.done() or result.set_result(params))

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", CALLBACK_PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        params = await asyncio.wait_for(result, timeout=300)
    finally:
        server.shutdown()
    if "error" in params:
        raise RuntimeError(f"Orbit login failed: {params['error'][0]}")
    return AuthorizationCodeResult(
        code=params["code"][0],
        state=params.get("state", [None])[0],
        iss=params.get("iss", [None])[0],
    )


def _auth() -> OAuthClientProvider:
    return OAuthClientProvider(
        server_url=MCP_URL,
        client_metadata=OAuthClientMetadata(
            client_name="tl-uurtjes",
            redirect_uris=[REDIRECT_URI],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
        ),
        storage=FileTokenStorage(),
        redirect_handler=_open_browser,
        callback_handler=_wait_for_callback,
    )


class ToolError(RuntimeError):
    pass


async def _with_session(fn):
    async with create_mcp_http_client(auth=_auth()) as http:
        async with streamable_http_client(MCP_URL, http_client=http) as (read, write, *_):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await fn(session)


def _result_text(result) -> str:
    text = "\n".join(c.text for c in result.content if getattr(c, "type", None) == "text")
    if result.is_error:
        raise ToolError(text or "Orbit returned an error")
    return text


def call(name: str, arguments: dict[str, Any] | None = None) -> str:
    """Calls one Orbit tool and returns its text output."""

    async def run(session: ClientSession):
        return _result_text(await session.call_tool(name, arguments or {}))

    return asyncio.run(_with_session(run))


def call_many(calls: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """Calls several Orbit tools over one session, in order."""

    async def run(session: ClientSession):
        return [_result_text(await session.call_tool(n, a)) for n, a in calls]

    return asyncio.run(_with_session(run))


def list_tools() -> list:
    async def run(session: ClientSession):
        return (await session.list_tools()).tools

    return asyncio.run(_with_session(run))
