"""
Kite MCP Integration Module for Ponfolio.

Uses Zerodha's Kite MCP (Model Context Protocol) server for:
- OAuth2 login flow with Zerodha (browser-based, no API keys needed)
- Real-time quotes, LTP, OHLC via MCP tools
- Portfolio holdings sync from live Zerodha account
- Positions, margins, orders, and GTT management
- Mutual fund holdings
- Instrument search

Architecture:
  A persistent MCP session runs in a background thread/event loop.
  This is CRITICAL because the Kite MCP login flow ties authentication
  to the session ID. If the session dies between the login URL generation
  and the user completing auth, the callback fails with
  "missing MCP session_id or Kite request_token".

  All tool calls are routed through this single persistent session via
  asyncio.run_coroutine_threadsafe().
"""

import json
import asyncio
import contextlib
import logging
import threading
import random
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any

logger = logging.getLogger("kite_client")

# ── Config ──
KITE_MCP_URL = "https://mcp.kite.trade/mcp"

# An idle streamable-HTTP stream gets closed by the server, and by any proxy
# in between. Ping inside that window rather than waiting to be disconnected:
# the authentication lives in the SERVER-side MCP session, so every dropped
# stream costs the user a fresh Zerodha login.
KEEPALIVE_SECONDS = 25
# One failed ping is a blip; three in a row means the stream is really gone and
# a deliberate reconnect beats waiting for the next tool call to discover it.
KEEPALIVE_FAILURES_BEFORE_RECONNECT = 3

# How long a verified login is still believed after a profile check fails for a
# reason that is NOT proof of logout. The status poll runs every 15s, so one
# slow or dropped get_profile used to blank "Kite Live" seconds after login
# even though the MCP session and its authentication were both still intact.
# Only the server answering without a user_id, or the transport actually
# reconnecting onto a new session id, ends the login before this expires.
PROFILE_GRACE_SECONDS = 150
# ...and a lone failure should not be announced at all: two in a row is the
# first point at which "reconnecting" is worth showing the user.
PROFILE_FAILURES_BEFORE_DEGRADED = 2
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# Where the server-side MCP session id is remembered between reconnects AND
# between runs of the backend. The Zerodha authentication is held by the
# SERVER against that id, so the id is the only thing that can carry a login
# across a dropped stream or an app restart. It is not a credential in its own
# right — it is useless without the server-side session still being alive — but
# it is session-bearing, so it lives beside the other local data files and
# never leaves the machine.
SESSION_FILE = DATA_DIR / "kite_session.json"
# Kite MCP sessions do not outlive the Zerodha trading day, and a stale id
# costs a wasted round trip plus a confusing "resume failed" in the log. Past
# this age, start clean instead of asking.
SESSION_RESUME_MAX_AGE = 12 * 3600
# HTTP timeouts for the transport. The read timeout has to be long: a
# streamable-HTTP GET stream is meant to sit open with nothing on it.
HTTP_TIMEOUT_SECONDS = 30.0
HTTP_READ_TIMEOUT_SECONDS = 300.0
# The header the MCP streamable-HTTP transport carries its session id in.
MCP_SESSION_HEADER = "mcp-session-id"


def _describe(exc: BaseException, depth: int = 0) -> str:
    """The real cause behind an anyio ExceptionGroup.

    Every transport failure was logged as `kind=ExceptionGroup`, which is the
    task group's wrapper and says nothing at all — a timeout, a refused
    resume, a TLS error and a cancelled task all look identical. Unwrapping it
    is the difference between a diagnosable failure and a guess.
    """
    inner = getattr(exc, "exceptions", None)
    if inner and depth < 3:
        return " | ".join(_describe(e, depth + 1) for e in inner[:3])
    text = " ".join(str(exc).split())
    return f"{type(exc).__name__}" + (f": {text[:90]}" if text else "")


# Kite MCP rate-limits per client. The SDK calls `raise_for_status()` on a
# tool POST inside the transport's task group, so a single 429 used to tear the
# WHOLE transport down, and the server never resumes a session after that
# (`session_resume_rejected` in the log, every time). That is the automatic
# logout: a burst of index-tape history calls, not an expired Zerodha token.
RATE_LIMIT_STATUSES = (429, 503)
RATE_LIMIT_RETRIES = 4
RATE_LIMIT_BASE_DELAY = 1.0
RATE_LIMIT_MAX_DELAY = 8.0
# The marker a synthesised rate-limit error carries, so callers (the
# keepalive in particular) can tell "slow down" apart from "stream is dead".
RATE_LIMITED_MESSAGE = "Kite rate limit reached (HTTP 429); request not sent"
# Client-side pacing of tool calls: at most this many in flight, and this much
# spacing between call starts. Kite's own REST limits are 3-10 req/s; staying
# under 3/s keeps the MCP proxy from answering 429 in the first place.
TOOL_CALL_CONCURRENCY = 2
TOOL_CALL_MIN_INTERVAL = 0.35


def _retry_after_seconds(response, attempt: int) -> float:
    """Server-suggested wait, else exponential backoff, capped."""
    try:
        value = float(response.headers.get("retry-after", ""))
        if value >= 0:
            return min(value, RATE_LIMIT_MAX_DELAY)
    except (TypeError, ValueError):
        pass
    return min(RATE_LIMIT_MAX_DELAY,
               RATE_LIMIT_BASE_DELAY * (2 ** attempt)) * random.uniform(0.8, 1.0)


def _jsonrpc_request_id(request) -> Any:
    """The JSON-RPC id of a POSTed request, or None for notifications/GETs."""
    if request.method != "POST":
        return None
    try:
        body = json.loads(bytes(request.content or b"").decode("utf-8"))
    except (ValueError, UnicodeDecodeError, TypeError):
        return None
    if isinstance(body, dict) and "method" in body:
        return body.get("id")
    return None


def _jsonrpc_error_response(request, request_id: Any, message: str):
    """A 200 carrying a JSON-RPC error for `request_id`: fails one call only."""
    import httpx
    return httpx.Response(
        200, request=request,
        headers={"content-type": "application/json"},
        json={"jsonrpc": "2.0", "id": request_id,
              "error": {"code": -32000, "message": message}})


class _RateLimitGuard:
    """httpx transport wrapper that absorbs 429/503 instead of crashing MCP.

    Retries with backoff first. If the server is still refusing, a JSON-RPC
    request is answered with a synthesised JSON-RPC *error* for its id, so the
    one tool call fails and the session — with the Zerodha login on it — stays.
    Anything that is not a request with an id gets the real response back.
    """

    def __init__(self, inner):
        self._inner = inner

    async def handle_async_request(self, request):
        import httpx
        response = None
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            try:
                response = await self._inner.handle_async_request(request)
            except httpx.TransportError as e:
                # A dropped connection on ONE tool POST is that call's
                # failure. Raised, it unwinds the transport task group and the
                # session (and login) with it. Not retried: the request may
                # already have reached the server (place_order is not
                # idempotent).
                request_id = _jsonrpc_request_id(request)
                if request_id is None:
                    raise
                logger.info("[Kite MCP] request_transport_error kind=%s — "
                            "failing the call, keeping the session",
                            type(e).__name__)
                return _jsonrpc_error_response(
                    request, request_id,
                    f"Kite request failed ({type(e).__name__}); please retry")
            if response.status_code not in RATE_LIMIT_STATUSES:
                return response
            if attempt == RATE_LIMIT_RETRIES:
                break
            delay = _retry_after_seconds(response, attempt)
            await response.aclose()
            logger.info("[Kite MCP] rate_limited status=%d retry_in=%.1fs attempt=%d",
                        response.status_code, delay, attempt + 1)
            await asyncio.sleep(delay)
        request_id = _jsonrpc_request_id(request)
        if request_id is None:
            return response
        status = response.status_code
        await response.aclose()
        logger.warning("[Kite MCP] rate_limited_giving_up status=%d — failing "
                       "the call, keeping the session", status)
        return _jsonrpc_error_response(request, request_id, RATE_LIMITED_MESSAGE)

    async def aclose(self):
        await self._inner.aclose()

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _guard_client(client):
    """Install the rate-limit guard on an httpx AsyncClient, if possible."""
    inner = getattr(client, "_transport", None)
    if inner is not None and not isinstance(inner, _RateLimitGuard):
        client._transport = _RateLimitGuard(inner)
    return client


def _new_http_client(headers: Dict[str, str]):
    """An httpx client carrying `headers` on every request.

    Built through the SDK's own factory when that is available: mcp 2.x vendors
    its own httpx, so a client constructed from the `httpx` this module can
    import may be the wrong class entirely.
    """
    import httpx
    timeout = httpx.Timeout(HTTP_TIMEOUT_SECONDS,
                            read=HTTP_READ_TIMEOUT_SECONDS)
    try:
        from mcp.shared._httpx_utils import create_mcp_http_client
        return _guard_client(
            create_mcp_http_client(headers=headers or None, timeout=timeout))
    except Exception:
        return _guard_client(httpx.AsyncClient(
            headers=headers or None, follow_redirects=True, timeout=timeout))


class KiteMCPClient:
    """Wrapper around Kite MCP server with a persistent session.

    The session is maintained in a background asyncio event loop running
    on a daemon thread.  Every public method submits work to that loop
    via run_coroutine_threadsafe, so callers can use normal sync code.
    """

    def __init__(self):
        self.connected = False
        self.profile = None
        self.last_error = None
        self._user_name = None
        self._user_id = None
        self._email = None
        self._mcp_available = False
        self.connection_state = "connecting"
        self.last_success_at = None
        self.last_keepalive_at = None
        self._manual_disconnect = False
        self._profile_check_lock = threading.Lock()
        self._last_profile_check = 0.0
        self._last_verified_at = 0.0
        self._profile_failures = 0

        # The server-side MCP session id currently in play, and whether the
        # login on it was inherited from a previous stream or process rather
        # than typed in again. Surfaced in status so "did it really recover?"
        # is answerable without reading the log.
        self._server_session_id = None
        self._session_resumed = False
        self._reconnects = 0
        self._session_id_getter = None
        self._force_reconnect = False
        # Created on the session thread: an asyncio.Event built before its loop
        # exists binds to the wrong one on older Pythons.
        self._wake: Optional[asyncio.Event] = None

        # Persistent session state
        self._session = None
        self._loop: asyncio.AbstractEventLoop = None
        self._thread: threading.Thread = None
        self._ready = threading.Event()
        self._shutdown = False

        # Start the persistent session
        self._start_session()

    # ──────────────────────────────────────
    # Persistent Session Management
    # ──────────────────────────────────────

    def _start_session(self):
        """Spin up a background thread that holds the MCP session open."""
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="kite-mcp")
        self._thread.start()
        # Wait up to 15s for the session to initialize
        if self._ready.wait(timeout=15):
            logger.info("[Kite MCP] Persistent session established")
        else:
            logger.warning("[Kite MCP] Session init timed out")

    def _run_loop(self):
        """Entry point for the background thread."""
        asyncio.set_event_loop(self._loop)
        self._wake = asyncio.Event()
        self._loop.run_until_complete(self._maintain_session())

    # ── remembering the server-side session ──

    def _load_saved_session_id(self) -> Optional[str]:
        """The session id from a previous run, if it is young enough to try."""
        try:
            saved = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        session_id = saved.get("session_id")
        age = time.time() - float(saved.get("saved_at") or 0)
        if not session_id or age > SESSION_RESUME_MAX_AGE:
            return None
        logger.info("[Kite MCP] saved_session_found age_seconds=%.0f", age)
        return str(session_id)

    def _remember_session(self) -> None:
        """Persist the current session id so a restart can pick the login up.

        The id is taken from the response header when the hook saw one, and
        from the SDK's own getter when it did not. Relying on the header alone
        left nothing on disk whenever the hook missed — and with nothing on
        disk every restart of the app comes back unauthenticated, which is the
        "I have to log in to Kite again" report.
        """
        if not self._server_session_id and callable(self._session_id_getter):
            try:
                self._server_session_id = self._session_id_getter()
            except Exception:
                pass
        if not self._server_session_id:
            # Loud, because the consequence is silent and expensive: the login
            # simply will not survive a restart.
            logger.warning("[Kite MCP] session_not_persisted — no session id "
                           "captured; the login will not survive a restart")
            return
        try:
            SESSION_FILE.write_text(json.dumps({
                "session_id": self._server_session_id,
                "saved_at": time.time(),
                "user_id": self._user_id,
            }), encoding="utf-8")
        except OSError as e:
            logger.info("[Kite MCP] session_save_failed kind=%s", type(e).__name__)

    def _forget_session(self) -> None:
        """Drop the remembered id once it is proven not to resume."""
        self._server_session_id = None
        self._session_resumed = False
        try:
            SESSION_FILE.unlink()
        except OSError:
            pass

    @contextlib.asynccontextmanager
    async def _transport(self, resume_id: Optional[str]):
        """Open a streamable-HTTP transport and yield `(read, write)`.

        Three SDK facts forced this to be a helper rather than one inline call:

          * `streamablehttp_client` — the name this module used to call — was
            renamed to `streamable_http_client` and then REMOVED in mcp 2.x.
            Requirements only said `mcp>=1.27.0`, so a clean install picked up
            2.x and every connection attempt died on ImportError inside the
            retry loop below. To the user that is Kite never connecting at all,
            with a Connect button that never sticks.
          * 1.x yields `(read, write, get_session_id)`, 2.x yields
            `(read, write)`. Unpacking a fixed arity breaks against one of
            them, so the session id is learnt from the response headers and the
            callback is only used as a fallback.
          * `terminate_on_close` defaults to True, which sends a DELETE on the
            way out and destroys the SERVER-side session — the one holding the
            Zerodha login. Dropping a stream has to cost the stream, not the
            authentication.

        `resume_id` is offered as a request header rather than set on the
        transport, because the transport object is not reachable through either
        wrapper, and it only adds a session-id header of its own once it has
        learnt one. So ours is what travels on the initialize request, which is
        exactly the request that has to carry it for the server to hand the
        existing session back.
        """
        headers = {MCP_SESSION_HEADER: resume_id} if resume_id else {}
        self._session_id_getter = None
        try:
            from mcp.client.streamable_http import streamable_http_client
        except ImportError:  # mcp < 1.27, before the rename
            from mcp.client.streamable_http import streamablehttp_client
            async with streamablehttp_client(
                    KITE_MCP_URL, headers=headers,
                    timeout=HTTP_TIMEOUT_SECONDS,
                    sse_read_timeout=HTTP_READ_TIMEOUT_SECONDS,
                    terminate_on_close=False) as streams:
                if len(streams) > 2 and callable(streams[2]):
                    self._session_id_getter = streams[2]
                yield streams[0], streams[1]
            return

        client = _new_http_client(headers)
        hooks = dict(getattr(client, "event_hooks", None) or {})
        hooks["response"] = list(hooks.get("response") or []) \
            + [self._capture_session_id]
        client.event_hooks = hooks
        # The SDK only closes an http client it created itself, so this one is
        # ours to close — otherwise every reconnect leaks a connection pool.
        async with client:
            async with streamable_http_client(
                    KITE_MCP_URL, http_client=client,
                    terminate_on_close=False) as streams:
                if len(streams) > 2 and callable(streams[2]):
                    self._session_id_getter = streams[2]
                yield streams[0], streams[1]

    async def _capture_session_id(self, response) -> None:
        """httpx response hook: learn the session id the server assigned.

        Read off the wire rather than from the SDK because mcp 2.x stopped
        handing back a session-id callback, and this is the one place both
        generations agree on.
        """
        try:
            session_id = response.headers.get(MCP_SESSION_HEADER)
        except Exception:
            return
        if session_id and session_id != self._server_session_id:
            self._server_session_id = session_id

    async def _verify_login_on(self, session) -> bool:
        """Ask the server, from inside the session's own loop, who we are.

        Deliberately not `check_connection`: that hops onto this event loop via
        run_coroutine_threadsafe, and calling it from the loop it targets would
        deadlock the connection thread on itself.
        """
        try:
            result = await asyncio.wait_for(
                session.call_tool("get_profile", arguments={}), timeout=20)
        except Exception as e:
            logger.info("[Kite MCP] resume_probe_failed kind=%s", type(e).__name__)
            return False
        parsed = self._parse_tool_result(result)
        if isinstance(parsed, dict) and parsed.get("user_id"):
            self._adopt_profile(parsed)
            return True
        return False

    async def _maintain_session(self):
        """Keep MCP session alive. Reconnects automatically on failure.

        On every reconnect the OLD server session id is offered back to the
        server. If it still holds that session the Zerodha login comes back
        with it and the user is never asked to log in again; if it does not,
        the id is dropped and a clean session is negotiated. That difference —
        offering the id instead of always starting fresh — is the whole reason
        a dropped stream used to cost a login.
        """
        attempts = 0
        resume_id = self._load_saved_session_id()
        while not self._shutdown:
            established_at = None
            attempting_resume = bool(resume_id)
            try:
                from mcp import ClientSession

                logger.info("[Kite MCP] Connecting to %s ... resume=%s",
                            KITE_MCP_URL, "yes" if attempting_resume else "no")
                self._server_session_id = None
                async with self._transport(resume_id) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        logger.info("[Kite MCP] Session ready — %d tools available", len(tools.tools))

                        self._session = session
                        established_at = time.monotonic()
                        self._mcp_available = True
                        self.last_error = None
                        if not self._server_session_id and self._session_id_getter:
                            self._server_session_id = self._session_id_getter()

                        # Did the server keep the session we asked for? A new
                        # id means it did not, and the login went with it.
                        kept = bool(resume_id) and self._server_session_id in (
                            None, resume_id)
                        if kept and await self._verify_login_on(session):
                            self._server_session_id = resume_id
                            self._session_resumed = True
                            logger.info("[Kite MCP] session_resumed user=%s",
                                        self._user_id)
                        else:
                            if attempting_resume:
                                # WARNING, not info: this is the exact moment a
                                # login is lost, and it was invisible at the
                                # default log level.
                                logger.warning(
                                    "[Kite MCP] session_resume_rejected "
                                    "offered=%s server_gave=%s",
                                    (resume_id or "")[-12:],
                                    (self._server_session_id or "")[-12:])
                            self._session_resumed = False
                            self._clear_auth_state(
                                "Sign in to Zerodha to connect Kite.")
                            self.connection_state = "authentication_required"
                        resume_id = None
                        self._remember_session()
                        self._ready.set()

                        # Keep the session alive with a real MCP ping. Holding
                        # the context open while sleeping is not a keep-alive:
                        # nothing travels on the stream, the far end closes it
                        # as idle, and the reconnect below lands on a NEW
                        # session id — which is where the authentication was.
                        # That is the automatic Kite disconnect: not an expired
                        # Zerodha token, an abandoned HTTP stream.
                        failures = 0
                        while not self._shutdown:
                            # Interruptible so a user-requested reconnect does
                            # not wait out the ping interval before anything
                            # visibly happens.
                            with contextlib.suppress(asyncio.TimeoutError):
                                await asyncio.wait_for(self._wake.wait(),
                                                       timeout=KEEPALIVE_SECONDS)
                            self._wake.clear()
                            if self._force_reconnect:
                                self._force_reconnect = False
                                raise ConnectionError("reconnect requested")
                            if self._session is None:
                                break
                            try:
                                await asyncio.wait_for(session.send_ping(), timeout=10)
                                failures = 0
                                self.last_keepalive_at = datetime.now() \
                                    .astimezone().isoformat(timespec="seconds")
                            except asyncio.CancelledError:
                                raise
                            except Exception as ping_error:
                                if RATE_LIMITED_MESSAGE in str(ping_error):
                                    # Throttled, not disconnected: the server
                                    # answered. Reconnecting would cost the login.
                                    continue
                                failures += 1
                                logger.info(
                                    "[Kite MCP] keepalive_failed kind=%s streak=%d",
                                    type(ping_error).__name__, failures)
                                if failures >= KEEPALIVE_FAILURES_BEFORE_RECONNECT:
                                    raise

            except asyncio.CancelledError:
                break
            except Exception as e:
                delay = min(60.0, 2.0 ** min(attempts + 1, 6)) * random.uniform(0.8, 1.0)
                attempts += 1
                if established_at is not None and time.monotonic() - established_at >= 60:
                    attempts = 0
                self._session = None
                self._mcp_available = False
                self._reconnects += 1
                # Carry the id into the next attempt. The authentication lives
                # with the SERVER-side session, so offering the same id back is
                # what turns a dropped stream into a reconnect instead of into
                # another Zerodha login. The identity is deliberately NOT
                # cleared here: it is re-proven against the resumed session (or
                # given up) at the top of the loop, and blanking it now is what
                # made a single network blip present as "please reconnect".
                resume_id = self._server_session_id or resume_id
                if attempting_resume and established_at is None:
                    # The id we offered is what the server refused. Stop
                    # offering it, and do not wait a full backoff to find out
                    # that a clean session works.
                    logger.info("[Kite MCP] resume_attempt_failed kind=%s",
                                type(e).__name__)
                    self._forget_session()
                    resume_id = None
                    delay = min(delay, 2.0)
                    attempts = max(0, attempts - 1)
                logger.warning("[Kite MCP] transport_failure cause=%s "
                               "retry_seconds=%.1f resume=%s",
                               _describe(e), delay,
                               "yes" if resume_id else "no")
                self.connection_state = "reconnecting"
                self.last_error = ("Kite connection interrupted. "
                                   "Restoring the session automatically.")
                self._ready.set()
                await asyncio.sleep(delay)

    def _ensure_session(self) -> bool:
        """Check that the persistent session is alive."""
        return self._session is not None and self._mcp_available

    def _run_on_session(self, coro, timeout=30):
        """Submit a coroutine to the persistent session's event loop and wait."""
        if not self._ensure_session():
            raise ConnectionError("Kite MCP session not available")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()
            raise

    # ──────────────────────────────────────
    # Tool Calling
    # ──────────────────────────────────────

    def _pace(self) -> None:
        """Space tool-call starts so a burst never reaches the server at once.

        The index tape alone asks for 15 histories plus a 28-instrument OHLC
        the moment Kite connects; unpaced, that is what drew the 429s.
        """
        lock = self.__dict__.setdefault("_pace_lock", threading.Lock())
        with lock:
            now = time.monotonic()
            start = max(now, getattr(self, "_next_call_at", 0.0))
            self._next_call_at = start + TOOL_CALL_MIN_INTERVAL
        wait = start - now
        if wait > 0:
            time.sleep(wait)

    def call_tool(self, tool_name: str, arguments: dict = None) -> Any:
        """Call an MCP tool on the persistent session (sync)."""
        if not self._ensure_session():
            raise ConnectionError("Kite MCP session unavailable")
        gate = self.__dict__.setdefault(
            "_call_gate", threading.BoundedSemaphore(TOOL_CALL_CONCURRENCY))
        with gate:
            self._pace()
            if not self._ensure_session():
                raise ConnectionError("Kite MCP session unavailable")
            return self._run_on_session(
                self._session.call_tool(tool_name, arguments=arguments or {})
            )

    def list_tools(self) -> Optional[list]:
        """What the MCP server says it can do, as [{name, description}].

        Needed because the account-scoped calls were returning empty while the
        session reported connected, and there was no way to tell whether a tool
        was failing, missing, or named something else entirely. Guessing tool
        names from the client side is how you end up debugging a call that was
        never going to exist.
        """
        if not self._ensure_session():
            return None
        try:
            listed = self._run_on_session(self._session.list_tools())
            out = []
            for t in (getattr(listed, "tools", None) or []):
                out.append({
                    "name": getattr(t, "name", str(t)),
                    "description": (getattr(t, "description", "") or "")[:200],
                })
            return out
        except Exception as e:
            logger.error("[Kite MCP] list_tools failed: %s", e)
            return None

    def call_tool_raw(self, tool_name: str, arguments: dict = None) -> dict:
        """Call a tool and report what came back WITHOUT interpreting it.

        The normal accessors swallow the shape: get_holdings returns None
        whenever the payload is not a list, which is indistinguishable from an
        empty portfolio. This keeps the raw text so a plain-language error from
        the server is visible instead of being flattened into "no data".
        """
        try:
            result = self.call_tool(tool_name, arguments)
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        parsed = self._parse_tool_result(result)
        return {
            "ok": True,
            "parsed_type": type(parsed).__name__,
            "is_error_text": isinstance(parsed, str),
            "count": len(parsed) if isinstance(parsed, (list, dict)) else None,
            # Truncated: a full tradebook would swamp the response, and the
            # first rows are enough to see the shape and the field names.
            "sample": (parsed[:3] if isinstance(parsed, list)
                       else (parsed if isinstance(parsed, dict)
                             else str(parsed)[:800])),
        }

    def _parse_tool_result(self, result) -> Any:
        """Parse MCP tool result content into Python objects."""
        if result is None:
            return None
        if hasattr(result, 'content') and result.content:
            texts = []
            for item in result.content:
                if hasattr(item, 'text'):
                    texts.append(item.text)
            combined = "\n".join(texts)
            try:
                return json.loads(combined)
            except (json.JSONDecodeError, ValueError):
                return combined
        return result

    # ──────────────────────────────────────
    # Auth Flow
    # ──────────────────────────────────────

    def _clear_auth_state(self, error: str = None) -> None:
        """Clear identity whenever the current MCP session cannot prove it."""
        self.connected = False
        self.profile = None
        self._user_name = None
        self._user_id = None
        self._email = None
        self.last_error = error
        # Surrender the grace window too, or the next poll would resurrect a
        # login this call just established was gone.
        self._last_verified_at = 0.0
        self._profile_failures = 0
        self.connection_state = "authentication_required" if error else "disconnected"

    def get_login_url(self) -> Optional[str]:
        """Get Zerodha login URL via MCP login tool.

        The returned URL contains the MCP session_id.  Because we use
        a persistent session, the same session will still be alive when
        the user finishes authentication on Zerodha and gets redirected
        back to the Kite MCP callback.

        Returns None if already logged in or if MCP is unavailable.
        """
        if not self._ensure_session():
            return None
        try:
            result = self.call_tool("login")
            parsed = self._parse_tool_result(result)

            if isinstance(parsed, dict):
                url = parsed.get("login_url") or parsed.get("url")
                if url and url.startswith("http"):
                    return url

            if isinstance(parsed, str):
                import re
                # Check if already logged in
                if "already logged in" in parsed.lower():
                    logger.info("[Kite MCP] Already logged in")
                    self.check_connection()
                    return None

                # Extract URL from Markdown link syntax [text](url)
                md_urls = re.findall(r'\]\((https?://[^)]+)\)', parsed)
                if md_urls:
                    return md_urls[0]

                # Fallback: extract any URL, strip trailing punctuation
                urls = re.findall(r'https?://[^\s<>"\']+', parsed)
                if urls:
                    url = urls[0].rstrip(')')
                    return url
                # No URL found - don't return raw text as URL
                logger.warning("[Kite MCP] Login tool returned no URL")
                return None

            return None
        except Exception as e:
            logger.error("[Kite MCP] Login error: %s", e)
            self.last_error = str(e)
            return None

    def check_connection(self) -> bool:
        """Check if we're authenticated by trying to get profile."""
        if getattr(self, "_manual_disconnect", False):
            return False
        lock = getattr(self, "_profile_check_lock", None)
        if lock is not None and not lock.acquire(blocking=False):
            return self.connected
        try:
            if time.monotonic() - getattr(self, "_last_profile_check", 0) < 10:
                return self.connected
            self._last_profile_check = time.monotonic()
            return self._check_profile()
        finally:
            if lock is not None:
                lock.release()

    def _hold_login(self, reason: str) -> bool:
        """Report an unproven check failure without cancelling a live login.

        A dropped poll is not a logout. While a recent verification is still
        inside the grace window the login is reported as it was last PROVEN to
        be, so the sidebar keeps saying "Kite Live" instead of flipping to
        "Kite retrying" on the first slow response. Past the window the claim
        is too old to stand behind and the session is surrendered.
        """
        self._profile_failures = getattr(self, "_profile_failures", 0) + 1
        age = time.monotonic() - getattr(self, "_last_verified_at", 0.0)
        if self.connected and age < PROFILE_GRACE_SECONDS:
            if self._profile_failures >= PROFILE_FAILURES_BEFORE_DEGRADED:
                self.last_error = "Kite is slow to answer. The session is still open."
                self.connection_state = "degraded"
            return True
        self.connected = False
        self.connection_state = "reconnecting"
        self.last_error = reason
        return False

    def _adopt_profile(self, parsed: Dict[str, Any]) -> None:
        """Record a proven login, and remember the session that proved it.

        Persisting the id here rather than only at connect time is what lets a
        restart of the backend inherit the login: the id is written the moment
        it is known to be authenticated.
        """
        self.connected = True
        self.profile = parsed
        self._user_name = parsed.get("user_name")
        self._user_id = parsed.get("user_id")
        self._email = parsed.get("email")
        self.last_error = None
        self.connection_state = "connected"
        self._profile_failures = 0
        self._last_verified_at = time.monotonic()
        self.last_success_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self._remember_session()
        logger.info("[Kite MCP] authentication_verified")

    def _check_profile(self) -> bool:
        if not self._ensure_session():
            # No transport at all: still inside the grace window this is the
            # reconnect loop doing its job, not the user being logged out.
            return self._hold_login("Kite MCP session not available")
        try:
            result = self.call_tool("get_profile")
            parsed = self._parse_tool_result(result)
            if parsed and isinstance(parsed, dict) and parsed.get("user_id"):
                self._adopt_profile(parsed)
                return True
            # A service error or malformed response is not proof of logout.
            error_text = (parsed if isinstance(parsed, str) else
                          str(parsed.get("error", "")) + " " + str(parsed.get("message", ""))
                          if isinstance(parsed, dict) else "").lower()
            expired = any(marker in error_text for marker in (
                "please log in", "please login", "not authenticated",
                "token expired", "session expired", "invalid token"))
            if expired:
                # "Please log in" means THIS session is not authenticated. It
                # is only evidence about the SAVED one if we were logged in a
                # moment ago and are not now.
                #
                # Forgetting unconditionally is what made the login unable to
                # survive a restart: the app polls status every 15 seconds, so
                # on a fresh start — before the user has signed in, and before
                # the connect loop has had a chance to offer the saved id back
                # — the first poll answered "please login" and deleted the very
                # file the resume depends on. Written on connect, gone fifteen
                # seconds later, never once used.
                if self._user_id:
                    self._forget_session()
                self._clear_auth_state("Kite authentication expired. Please reconnect.")
                # Say WHICH kind of not-connected this is. `_clear_auth_state`
                # leaves `connection_state` alone, so a session that has simply
                # never been signed into kept whatever the last poll set —
                # usually "reconnecting" — and the sidebar offered a retry
                # spinner forever instead of the Connect button that would
                # actually fix it. Retrying cannot produce a login.
                self.connection_state = "authentication_required"
                return False
            if not self._user_id:
                # A live MCP session that will not name a user, and no identity
                # to fall back on, means nobody has signed in yet. Holding the
                # login here is holding nothing: `_hold_login` drops to
                # "reconnecting", and the sidebar then offers a retry spinner
                # for a condition retrying cannot fix. Deciding this on the
                # ABSENCE of a user rather than on Zerodha's English error text
                # keeps it working when that wording changes.
                self._clear_auth_state("Sign in to Zerodha to connect Kite.")
                self.connection_state = "authentication_required"
                return False
            return self._hold_login("Profile check unavailable. Retrying the existing session.")
        except (TimeoutError, OSError) as e:
            # A temporary network failure is not proof of token expiry.
            logger.info("[Kite MCP] profile_transport_failure kind=%s", type(e).__name__)
            return self._hold_login("Connection interrupted. Retrying the existing session.")
        except Exception as e:
            # Anything else is also unproven. This used to clear the identity,
            # which turned one bad frame on the stream — an MCP protocol error,
            # a half-read response, a cancelled task — into "please reconnect
            # to Kite", with the login prompt to match. Only the server
            # answering WITHOUT a user_id (handled above) is evidence that the
            # session is no longer authenticated.
            logger.info("[Kite MCP] profile_unexpected_failure kind=%s", type(e).__name__)
            return self._hold_login("Connection interrupted. Retrying the existing session.")

    def logout(self):
        """Clear local connection state."""
        # Forget the id too, or the next reconnect would quietly resume the
        # very login the user just asked to end.
        self._forget_session()
        self._clear_auth_state()
        self._manual_disconnect = True
        logger.info("[Kite MCP] Logged out (local state cleared)")

    def reconnect(self) -> dict:
        """Drop the current stream and rebuild it, keeping the login if it holds.

        The transport is not torn down from here — its context belongs to the
        maintenance task, and exiting it from another task trips anyio's
        cancel-scope check. Instead the keepalive is woken and asked to fail,
        so the existing retry path does the rebuilding.

        The remembered session id is deliberately NOT discarded. This used to
        call `_forget_session()` first, which made "reconnect" the most
        expensive button in the app: it threw away the server-side session that
        held the Zerodha login, so the rebuild could only ever come back
        unauthenticated and the user had to sign in again. The retry path
        already forgets the id the moment a resume is actually refused
        (`resume_attempt_failed`), which is the only evidence that the session
        is gone. Asking to reconnect means "try again", not "log me out".
        """
        self._manual_disconnect = False
        self._last_profile_check = 0.0
        self.connection_state = "reconnecting"
        self._mcp_available = False
        self._force_reconnect = True
        wake = self._wake
        if wake is not None and self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(wake.set)
        return {"reconnecting": True}

    # ──────────────────────────────────────
    # Status
    # ──────────────────────────────────────

    def get_status(self) -> dict:
        """Get current connection status."""
        return {
            "connected": self.connected,
            "connection_state": getattr(self, "connection_state", "disconnected"),
            "last_success_at": getattr(self, "last_success_at", None),
            # Proof the stream is being held open, not just that a
            # login once succeeded — the two failed together before.
            "last_keepalive_at": getattr(self, "last_keepalive_at", None),
            # Whether this login was inherited from a previous stream or run
            # rather than typed in again, and how many times the transport has
            # been rebuilt under it. Together they answer "is the automatic
            # recovery actually working?" without reading the log.
            "session_resumed": bool(getattr(self, "_session_resumed", False)),
            "reconnects": int(getattr(self, "_reconnects", 0)),
            "configured": self._mcp_available,
            "mcp_available": self._mcp_available,
            "mcp_url": KITE_MCP_URL,
            "user_name": self._user_name,
            "user_id": self._user_id,
            "email": self._email,
            "broker": "Zerodha" if self.connected else None,
            "last_error": self.last_error,
            "mode": "MCP (Free)",
        }

    # ──────────────────────────────────────
    # Portfolio Data
    # ──────────────────────────────────────

    def resolve_instrument_token(self, instrument: str) -> Optional[int]:
        """The numeric token for an `exchange:tradingsymbol`, or None.

        `get_historical_data` wants a token, not a symbol, and only
        `search_instruments` can turn one into the other. Tokens are stable, so
        the caller is expected to cache what it gets back rather than look the
        same index up every fifteen seconds.
        """
        if not instrument or not self._ensure_session():
            return None
        exchange, _, tradingsymbol = str(instrument).partition(":")
        try:
            result = self.call_tool("search_instruments",
                                    {"query": tradingsymbol, "limit": 20})
            parsed = self._parse_tool_result(result)
            rows = parsed if isinstance(parsed, list) else (
                parsed.get("instruments") or parsed.get("data") or []
                if isinstance(parsed, dict) else [])
            for row in rows:
                if not isinstance(row, dict):
                    continue
                # Match BOTH halves. A bare tradingsymbol match would happily
                # return the NSE equity when the index was wanted, and the two
                # have wildly different price series.
                if (str(row.get("tradingsymbol", "")).upper()
                        == tradingsymbol.upper()
                        and str(row.get("exchange", "")).upper()
                        == exchange.upper()):
                    token = row.get("instrument_token")
                    return int(token) if token is not None else None
            return None
        except Exception as e:
            logger.info("[Kite MCP] token_lookup_failed kind=%s",
                        type(e).__name__)
            return None

    def get_index_history(self, instrument_token: int, from_date: str,
                          to_date: str, interval: str = "day"
                          ) -> Optional[List[Dict]]:
        """Daily candles for one instrument, oldest first.

        This is the only route to a 52-week range for the NSE sector indices:
        Yahoo serves a single bar for them and NSE's own endpoint answers a
        block page. Returns None on any refusal so the caller keeps whatever
        series it already had rather than replacing it with nothing.
        """
        if not instrument_token or not self._ensure_session():
            return None
        try:
            result = self.call_tool("get_historical_data", {
                "instrument_token": int(instrument_token),
                "from_date": from_date, "to_date": to_date,
                "interval": interval})
            parsed = self._parse_tool_result(result)
            rows = parsed if isinstance(parsed, list) else (
                parsed.get("candles") or parsed.get("data") or []
                if isinstance(parsed, dict) else [])
            clean = [r for r in rows if isinstance(r, (dict, list)) and r]
            if clean:
                logger.info("[Kite MCP] history %s candles for token %s",
                            len(clean), instrument_token)
                return clean
            if isinstance(parsed, str):
                logger.info("[Kite MCP] history_refused: %s", parsed[:80])
            return None
        except Exception as e:
            logger.info("[Kite MCP] history_failed kind=%s", type(e).__name__)
            return None

    def get_index_quotes(self, instruments: List[str]) -> Optional[Dict]:
        """Live OHLC for a list of `exchange:tradingsymbol` instruments.

        Used for the market tape. Kite's OHLC response carries the PREVIOUS
        session's close alongside the live price, which is the entire day-change
        figure — and it is available for the NSE sector indices that Yahoo
        serves no history for at all. Those cards had a live level and nothing
        to compare it against.

        Returns None rather than {} when the session cannot answer, so the
        caller can leave the existing figures alone instead of overwriting good
        data with blanks.
        """
        if not instruments or not self._ensure_session():
            return None
        try:
            result = self.call_tool("get_ohlc",
                                    {"instruments": list(instruments)})
            parsed = self._parse_tool_result(result)
            if isinstance(parsed, dict):
                # Some builds nest the map under "data"; accept both.
                inner = parsed.get("data")
                quotes = inner if isinstance(inner, dict) else parsed
                if any(isinstance(v, dict) for v in quotes.values()):
                    logger.info("[Kite MCP] index quotes for %d instruments",
                                len(quotes))
                    return quotes
            if isinstance(parsed, str):
                logger.info("[Kite MCP] index_quotes_refused: %s", parsed[:80])
            return None
        except Exception as e:
            logger.info("[Kite MCP] index_quotes_failed kind=%s",
                        type(e).__name__)
            return None

    def get_holdings(self) -> Optional[List[Dict]]:
        """Fetch portfolio holdings from Zerodha via MCP."""
        if not self._ensure_session():
            return None
        try:
            result = self.call_tool("get_holdings")
            parsed = self._parse_tool_result(result)
            if isinstance(parsed, list):
                logger.info("[Kite MCP] Fetched %d holdings", len(parsed))
                return parsed
            if isinstance(parsed, dict) and "holdings" in parsed:
                return parsed["holdings"]
            if isinstance(parsed, str):
                # Do not flatten an authentication failure into an empty
                # portfolio while leaving the stale connected badge alive.
                self._clear_auth_state(parsed[:200])
                logger.warning("[Kite MCP] Holdings unavailable: %s", parsed[:200])
            return parsed if isinstance(parsed, list) else None
        except Exception as e:
            logger.error("[Kite MCP] Holdings error: %s", e)
            return None

    def get_positions(self) -> Optional[Dict]:
        """Fetch current day positions via MCP."""
        if not self._ensure_session():
            return None
        try:
            result = self.call_tool("get_positions")
            return self._parse_tool_result(result)
        except Exception as e:
            logger.error("[Kite MCP] Positions error: %s", e)
            return None

    def get_margins(self) -> Optional[Dict]:
        """Fetch account margins via MCP."""
        if not self._ensure_session():
            return None
        try:
            result = self.call_tool("get_margins")
            return self._parse_tool_result(result)
        except Exception as e:
            logger.error("[Kite MCP] Margins error: %s", e)
            return None

    # ──────────────────────────────────────
    # Market Data
    # ──────────────────────────────────────

    def get_ltp(self, symbols: List[str]) -> Optional[Dict]:
        """Get last traded price for instruments.

        Args:
            symbols: List like ["NSE:RELIANCE", "NSE:INFY"]
        """
        if not self._ensure_session():
            return None
        try:
            result = self.call_tool("get_ltp", {"instruments": symbols})
            return self._parse_tool_result(result)
        except Exception as e:
            logger.error("[Kite MCP] LTP error: %s", e)
            return None

    def get_quotes(self, symbols: List[str]) -> Optional[Dict]:
        """Get full quotes for instruments."""
        if not self._ensure_session():
            return None
        try:
            result = self.call_tool("get_quotes", {"instruments": symbols})
            return self._parse_tool_result(result)
        except Exception as e:
            logger.error("[Kite MCP] Quotes error: %s", e)
            return None

    def get_ohlc(self, symbols: List[str]) -> Optional[Dict]:
        """Get OHLC data for instruments."""
        if not self._ensure_session():
            return None
        try:
            result = self.call_tool("get_ohlc", {"instruments": symbols})
            return self._parse_tool_result(result)
        except Exception as e:
            logger.error("[Kite MCP] OHLC error: %s", e)
            return None

    def get_historical_data(self, instrument_token: int, from_date: str, to_date: str,
                            interval: str = "day") -> Optional[List]:
        """Get historical candle data via MCP."""
        if not self._ensure_session():
            return None
        try:
            result = self.call_tool("get_historical_data", {
                "instrument_token": instrument_token,
                "from_date": from_date,
                "to_date": to_date,
                "interval": interval,
            })
            return self._parse_tool_result(result)
        except Exception as e:
            logger.error("[Kite MCP] Historical data error: %s", e)
            return None

    def search_instruments(self, query: str, exchange: str = None) -> Optional[List]:
        """Search for trading instruments via MCP."""
        if not self._ensure_session():
            return None
        try:
            args = {"query": query}
            if exchange:
                args["exchange"] = exchange
            result = self.call_tool("search_instruments", args)
            return self._parse_tool_result(result)
        except Exception as e:
            logger.error("[Kite MCP] Search instruments error: %s", e)
            return None

    # ──────────────────────────────────────
    # Orders
    # ──────────────────────────────────────

    def get_orders(self) -> Optional[List]:
        """Get today's orders via MCP."""
        if not self._ensure_session():
            return None
        try:
            result = self.call_tool("get_orders")
            return self._parse_tool_result(result)
        except Exception as e:
            logger.error("[Kite MCP] Orders error: %s", e)
            return None

    def place_order(self, tradingsymbol: str, exchange: str = "NSE",
                    transaction_type: str = "BUY", quantity: int = 1,
                    order_type: str = "MARKET", product: str = "CNC",
                    price: float = None, trigger_price: float = None) -> Optional[str]:
        """Place a new order via MCP."""
        if not self._ensure_session():
            return None
        try:
            params = {
                "tradingsymbol": tradingsymbol,
                "exchange": exchange,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "order_type": order_type,
                "product": product,
            }
            if price is not None:
                params["price"] = price
            if trigger_price is not None:
                params["trigger_price"] = trigger_price

            result = self.call_tool("place_order", params)
            parsed = self._parse_tool_result(result)
            if isinstance(parsed, dict):
                order_id = parsed.get("order_id")
                if order_id:
                    logger.info("[Kite MCP] Order placed: %s", order_id)
                    return str(order_id)
            return str(parsed) if parsed else None
        except Exception as e:
            logger.error("[Kite MCP] Place order error: %s", e)
            return None

    def modify_order(self, order_id: str, **kwargs) -> Optional[str]:
        """Modify an existing order via MCP."""
        if not self._ensure_session():
            return None
        try:
            params = {"order_id": order_id, **kwargs}
            result = self.call_tool("modify_order", params)
            return self._parse_tool_result(result)
        except Exception as e:
            logger.error("[Kite MCP] Modify order error: %s", e)
            return None

    def cancel_order(self, order_id: str) -> Optional[str]:
        """Cancel an order via MCP."""
        if not self._ensure_session():
            return None
        try:
            result = self.call_tool("cancel_order", {"order_id": order_id})
            return self._parse_tool_result(result)
        except Exception as e:
            logger.error("[Kite MCP] Cancel order error: %s", e)
            return None

    def get_trades(self, offset: int = 0, limit: int = 0) -> Optional[List]:
        """Get trading history via MCP (one page).

        The MCP ``get_trades`` tool takes ``from``/``limit`` pagination args.
        Both are optional — with neither, the server returns its default page.
        """
        if not self._ensure_session():
            return None
        args = {}
        if offset:
            args["from"] = offset
        if limit:
            args["limit"] = limit
        try:
            result = self.call_tool("get_trades", args or None)
            parsed = self._parse_tool_result(result)
            return self._as_trade_list(parsed)
        except Exception as e:
            logger.error("[Kite MCP] Trades error: %s", e)
            return None

    @staticmethod
    def _as_trade_list(parsed) -> Optional[List]:
        """Unwrap whatever shape get_trades came back as into a plain list."""
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in ("trades", "data", "results", "items"):
                if isinstance(parsed.get(key), list):
                    return parsed[key]
        return None

    def fetch_all_trades(self, page_size: int = 200, max_pages: int = 50) -> Optional[List]:
        """Page through the whole tradebook the MCP server is willing to serve.

        Zerodha's underlying tradebook is day-scoped on the classic Connect API,
        so this may well come back as just today's fills. We page anyway and let
        the caller decide what the coverage means — the trade store accumulates
        across days, so a day-only feed still builds real history over time.

        Stops on an empty page, a short page, or a page that adds no new
        trade_ids (a server that ignores ``from`` would otherwise loop forever).
        """
        if not self._ensure_session():
            return None
        collected: List[Dict] = []
        seen_ids = set()
        offset = 0
        for _ in range(max_pages):
            page = self.get_trades(offset=offset, limit=page_size)
            if page is None:
                # Hard failure on the first page means "no data"; mid-run it
                # means "stop here and keep what we have".
                return None if not collected else collected
            if not page:
                break
            fresh = 0
            for t in page:
                if not isinstance(t, dict):
                    continue
                tid = str(t.get("trade_id") or t.get("order_id") or "")
                key = tid or json.dumps(t, sort_keys=True, default=str)
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                collected.append(t)
                fresh += 1
            if fresh == 0 or len(page) < page_size:
                break
            offset += len(page)
        logger.info("[Kite MCP] Tradebook: %d trade(s) across %d page(s)",
                    len(collected), (offset // page_size) + 1)
        return collected

    # ──────────────────────────────────────
    # GTT Orders
    # ──────────────────────────────────────

    def get_gtt_orders(self) -> Optional[List]:
        """Get all GTT orders via MCP."""
        if not self._ensure_session():
            return None
        try:
            result = self.call_tool("get_gtts")
            return self._parse_tool_result(result)
        except Exception as e:
            logger.error("[Kite MCP] GTT error: %s", e)
            return None

    def place_gtt_order(self, tradingsymbol: str, exchange: str, trigger_type: str,
                        last_price: float, trigger_values: list, orders: list) -> Optional[int]:
        """Place a GTT order via MCP."""
        if not self._ensure_session():
            return None
        try:
            result = self.call_tool("place_gtt_order", {
                "tradingsymbol": tradingsymbol,
                "exchange": exchange,
                "trigger_type": trigger_type,
                "last_price": last_price,
                "trigger_values": trigger_values,
                "orders": orders,
            })
            parsed = self._parse_tool_result(result)
            if isinstance(parsed, dict):
                return parsed.get("trigger_id")
            return parsed
        except Exception as e:
            logger.error("[Kite MCP] Place GTT error: %s", e)
            return None

    def modify_gtt_order(self, trigger_id: int, **kwargs) -> Optional[Any]:
        """Modify an existing GTT order via MCP."""
        if not self._ensure_session():
            return None
        try:
            params = {"trigger_id": trigger_id, **kwargs}
            result = self.call_tool("modify_gtt_order", params)
            return self._parse_tool_result(result)
        except Exception as e:
            logger.error("[Kite MCP] Modify GTT error: %s", e)
            return None

    def delete_gtt_order(self, trigger_id: int) -> Optional[Any]:
        """Delete a GTT order via MCP."""
        if not self._ensure_session():
            return None
        try:
            result = self.call_tool("delete_gtt_order", {"trigger_id": trigger_id})
            return self._parse_tool_result(result)
        except Exception as e:
            logger.error("[Kite MCP] Delete GTT error: %s", e)
            return None

    # ──────────────────────────────────────
    # Mutual Funds
    # ──────────────────────────────────────

    def get_mf_holdings(self) -> Optional[List]:
        """Get mutual fund holdings via MCP."""
        if not self._ensure_session():
            return None
        try:
            result = self.call_tool("get_mf_holdings")
            return self._parse_tool_result(result)
        except Exception as e:
            logger.error("[Kite MCP] MF holdings error: %s", e)
            return None

    # ──────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────

    def symbol_to_kite_format(self, yf_symbol: str) -> str:
        """Convert Yahoo Finance symbol to Kite format.

        'RELIANCE.NS' → 'NSE:RELIANCE'
        'RELIANCE.BO' → 'BSE:RELIANCE'
        """
        if yf_symbol.endswith(".NS"):
            return f"NSE:{yf_symbol[:-3]}"
        elif yf_symbol.endswith(".BO"):
            return f"BSE:{yf_symbol[:-3]}"
        return f"NSE:{yf_symbol}"

    def kite_to_yf_symbol(self, kite_symbol: str, exchange: str = "NSE") -> str:
        """Convert Kite symbol to Yahoo Finance format.

        'RELIANCE' (exchange=NSE) → 'RELIANCE.NS'
        """
        suffix = ".NS" if exchange == "NSE" else ".BO"
        return f"{kite_symbol}{suffix}"

    def transform_holdings_to_portfolio(self, holdings: List[Dict]) -> List[Dict]:
        """Transform Kite holdings format to our portfolio format.

        Kite holding format:
        {
            "tradingsymbol": "RELIANCE",
            "exchange": "NSE",
            "quantity": 10,
            "average_price": 2500.0,
            "last_price": 2650.0,
            "pnl": 1500.0,
            ...
        }

        Our portfolio format:
        {
            "symbol": "RELIANCE.NS",
            "name": "RELIANCE",
            "shares": 10,
            "avg_cost": 2500.0,
            "kite_last_price": 2650.0,   # price snapshot from the holdings payload
            "kite_close_price": 2600.0,  # previous close, for day-change
            "kite_exchange": "NSE",      # true exchange, don't re-derive from the suffix
        }

        The kite_* fields are a *fallback* price source only. Kite already hands us a
        live price with every holding, so we keep it instead of throwing it away and
        forcing a second round-trip through get_ohlc/yfinance that can fail silently.
        Callers must treat them as potentially stale — see price_source in the API.
        """
        portfolio = []
        for h in holdings:
            qty = h.get("quantity", 0)
            if qty <= 0:
                continue  # Skip zero-quantity holdings

            exchange = h.get("exchange", "NSE")
            symbol = self.kite_to_yf_symbol(h["tradingsymbol"], exchange)

            def _num(key):
                """Kite sends these as float, but be defensive about None/str."""
                try:
                    v = float(h.get(key) or 0)
                except (TypeError, ValueError):
                    return 0.0
                return v if v > 0 else 0.0

            portfolio.append({
                "symbol": symbol,
                "name": h.get("tradingsymbol", symbol.replace(".NS", "")),
                "shares": qty,
                "avg_cost": round(h.get("average_price", 0), 2),
                "kite_last_price": round(_num("last_price"), 2),
                "kite_close_price": round(_num("close_price"), 2),
                "kite_exchange": exchange,
            })
        return portfolio


# ── Singleton instance ──
kite = KiteMCPClient()
