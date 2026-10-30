"""
Tests for Kite MCP session survival — the reason a user had to reconnect.

    python -m unittest test_kite_session -v

Nothing here touches the network or starts the session thread. Two things are
under test:

  1. The TRANSPORT PICKER. `streamablehttp_client` was renamed to
     `streamable_http_client` and then removed in mcp 2.x, while requirements
     allowed any `mcp>=1.27.0`. A clean install therefore picked up 2.x and
     every connect died on ImportError inside the retry loop — which the user
     sees as Kite never staying connected. Both SDK shapes are simulated with
     a fake module, because the installed SDK can only be one of them.
  2. The SESSION MEMORY. Authentication lives in the SERVER-side MCP session,
     so the session id is the only thing that can carry a login across a
     dropped stream or a backend restart. These assert it is kept when it
     should be and dropped the moment it must be.
"""

import asyncio
import json
import sys
import time
import types
import unittest
from unittest import mock

import kite_client
from kite_client import KiteMCPClient


def _client(tmp_file):
    """A client with no background thread and its own session file."""
    with mock.patch.object(KiteMCPClient, "_start_session"):
        c = KiteMCPClient()
    c._loop = None
    return c


class SessionFileTestCase(unittest.TestCase):
    def setUp(self):
        self.path = kite_client.DATA_DIR / "kite_session_unittest.json"
        self._real = kite_client.SESSION_FILE
        kite_client.SESSION_FILE = self.path
        self.path.unlink(missing_ok=True)
        self.c = _client(self.path)

    def tearDown(self):
        self.path.unlink(missing_ok=True)
        kite_client.SESSION_FILE = self._real

    # ── remembering ──

    def test_nothing_saved_means_nothing_to_resume(self):
        self.assertIsNone(self.c._load_saved_session_id())

    def test_a_fresh_id_round_trips(self):
        self.c._server_session_id = "abc123"
        self.c._remember_session()
        self.assertEqual(self.c._load_saved_session_id(), "abc123")

    def test_a_stale_id_is_not_offered(self):
        # Past its window the server will have dropped the session, so
        # offering the id only buys a refused round trip.
        self.path.write_text(json.dumps({
            "session_id": "old",
            "saved_at": time.time() - kite_client.SESSION_RESUME_MAX_AGE - 60,
        }), encoding="utf-8")
        self.assertIsNone(self.c._load_saved_session_id())

    def test_a_corrupt_file_is_not_fatal(self):
        self.path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(self.c._load_saved_session_id())

    def test_proving_the_login_persists_the_session(self):
        self.c._server_session_id = "live-id"
        self.c._adopt_profile({"user_id": "AB1234", "user_name": "T"})
        self.assertTrue(self.c.connected)
        self.assertEqual(self.c._load_saved_session_id(), "live-id")

    # ── forgetting ──

    def test_logout_forgets_the_session(self):
        # Otherwise the next reconnect silently resumes the login the user
        # just ended.
        self.c._server_session_id = "abc123"
        self.c._remember_session()
        self.c.logout()
        self.assertIsNone(self.c._load_saved_session_id())
        self.assertTrue(self.c._manual_disconnect)

    def test_a_proven_expiry_forgets_the_session(self):
        self.c._server_session_id = "abc123"
        self.c._adopt_profile({"user_id": "AB1234"})
        self.c._session = object()
        self.c._mcp_available = True
        with mock.patch.object(self.c, "call_tool",
                               return_value="Please login to continue"):
            self.assertFalse(self.c._check_profile())
        self.assertIsNone(self.c._load_saved_session_id())

    def test_an_unproven_failure_keeps_the_session_and_the_login(self):
        # A dropped poll is not a logout. Clearing here is what turned one
        # slow response into a login prompt.
        self.c._server_session_id = "abc123"
        self.c._adopt_profile({"user_id": "AB1234"})
        self.c._session = object()
        self.c._mcp_available = True
        with mock.patch.object(self.c, "call_tool",
                               side_effect=OSError("stream reset")):
            self.assertTrue(self.c._check_profile())
        self.assertTrue(self.c.connected)
        self.assertEqual(self.c._load_saved_session_id(), "abc123")

    def test_reconnect_rebuilds_the_stream_without_discarding_the_login(self):
        # "Reconnect" means try again, not log me out. Forgetting the id here
        # threw away the server-side session holding the Zerodha login, so the
        # rebuild could only come back unauthenticated — which is exactly the
        # "Kite keeps asking me to sign in" complaint. The id is dropped only
        # when a resume is actually refused, which the retry loop handles.
        self.c._server_session_id = "abc123"
        self.c._remember_session()
        self.c._manual_disconnect = True
        self.c.connected = True
        out = self.c.reconnect()
        self.assertTrue(out["reconnecting"])
        self.assertEqual(self.c._load_saved_session_id(), "abc123")
        self.assertEqual(self.c._server_session_id, "abc123")
        self.assertFalse(self.c._manual_disconnect)
        self.assertTrue(self.c._force_reconnect)
        self.assertEqual(self.c.connection_state, "reconnecting")

    def test_a_refused_resume_is_what_forgets_the_id(self):
        # The one piece of evidence that the session is really gone.
        self.c._server_session_id = "abc123"
        self.c._remember_session()
        self.c._forget_session()
        self.assertIsNone(self.c._load_saved_session_id())
        self.assertIsNone(self.c._server_session_id)

    def test_an_unauthenticated_start_does_not_delete_the_saved_session(self):
        """The bug that made a login unable to survive a restart.

        The app polls status every 15 seconds. On a fresh start the session is
        not authenticated yet, the server answers "please login", and the old
        code deleted the saved id on that answer — before the connect loop had
        even offered it back. The file was written on connect and gone fifteen
        seconds later, every time, so a resume never once happened.
        """
        self.c._server_session_id = "abc123"
        self.c._remember_session()
        self.c._user_id = None          # never authenticated in this run
        self.c._session = object()
        self.c._mcp_available = True
        with mock.patch.object(self.c, "call_tool",
                               return_value={"error": "Please login to Kite"}):
            self.assertFalse(self.c._check_profile())
        self.assertEqual(self.c._load_saved_session_id(), "abc123")

    def test_never_signed_in_reports_authentication_required(self):
        """Not "reconnecting" — retrying cannot produce a login.

        Kite answers `get_profile` with the literal string "Please log in first
        using the login tool" until you sign in. The state left behind was
        whatever the previous poll had set, usually "reconnecting", so the
        sidebar showed a retry spinner and never the Connect button. That is
        the loop people escape by closing the app.
        """
        self.c._user_id = None
        self.c._session = object()
        self.c._mcp_available = True
        self.c.connection_state = "reconnecting"
        with mock.patch.object(
                self.c, "call_tool",
                return_value="Please log in first using the login tool"):
            self.assertFalse(self.c._check_profile())
        self.assertEqual(self.c.connection_state, "authentication_required")
        self.assertFalse(self.c.connected)

    def test_an_unrecognised_refusal_still_asks_for_a_login(self):
        # Same conclusion without relying on Zerodha's wording: a live session
        # that names no user, and no identity to fall back on, means nobody has
        # signed in. Retrying cannot fix that, so it must not say "reconnecting".
        self.c._user_id = None
        self.c._session = object()
        self.c._mcp_available = True
        self.c.connection_state = "reconnecting"
        with mock.patch.object(self.c, "call_tool",
                               return_value="unrecognised refusal text"):
            self.assertFalse(self.c._check_profile())
        self.assertEqual(self.c.connection_state, "authentication_required")

    def test_an_established_login_still_gets_the_benefit_of_the_doubt(self):
        # The opposite case must not regress: a signed-in user whose profile
        # call hiccups keeps the session instead of being logged out.
        self.c._user_id = "AB1234"
        self.c.connected = True
        self.c._last_verified_at = __import__("time").monotonic()
        self.c._session = object()
        self.c._mcp_available = True
        with mock.patch.object(self.c, "call_tool",
                               return_value="service temporarily unavailable"):
            self.assertTrue(self.c._check_profile())
        self.assertTrue(self.c.connected)

    def test_losing_an_established_login_does_forget_it(self):
        # The other side: we WERE authenticated and the server now refuses, so
        # the saved id really is dead and keeping it would mislead the restart.
        self.c._server_session_id = "abc123"
        self.c._remember_session()
        self.c._user_id = "AB1234"      # we had an identity
        self.c._session = object()
        self.c._mcp_available = True
        with mock.patch.object(self.c, "call_tool",
                               return_value={"error": "session expired"}):
            self.assertFalse(self.c._check_profile())
        self.assertIsNone(self.c._load_saved_session_id())

    def test_logout_still_forgets_the_session(self):
        # Reconnect keeps the login; logout must not.
        self.c._server_session_id = "abc123"
        self.c._remember_session()
        self.c.logout()
        self.assertIsNone(self.c._load_saved_session_id())
        self.assertTrue(self.c._manual_disconnect)

    # ── capture ──

    def test_the_session_id_is_read_off_the_response(self):
        # mcp 2.x stopped handing back a session-id callback, so the header is
        # the one place both SDK generations agree on.
        response = types.SimpleNamespace(headers={"mcp-session-id": "from-wire"})
        asyncio.run(self.c._capture_session_id(response))
        self.assertEqual(self.c._server_session_id, "from-wire")

    def test_a_response_without_the_header_changes_nothing(self):
        self.c._server_session_id = "keep-me"
        asyncio.run(self.c._capture_session_id(
            types.SimpleNamespace(headers={})))
        self.assertEqual(self.c._server_session_id, "keep-me")

    # ── status ──

    def test_status_reports_whether_recovery_worked(self):
        self.c._session_resumed = True
        self.c._reconnects = 3
        status = self.c.get_status()
        self.assertTrue(status["session_resumed"])
        self.assertEqual(status["reconnects"], 3)


class VerifyLoginTestCase(unittest.TestCase):
    """`_verify_login_on` runs INSIDE the session loop, so it must not hop."""

    def setUp(self):
        self.c = _client(None)

    def test_a_profile_with_a_user_id_adopts_the_login(self):
        session = mock.Mock()
        session.call_tool = mock.AsyncMock(return_value=_text_result(
            json.dumps({"user_id": "AB1234", "user_name": "T"})))
        with mock.patch.object(self.c, "_remember_session"):
            self.assertTrue(asyncio.run(self.c._verify_login_on(session)))
        self.assertEqual(self.c._user_id, "AB1234")

    def test_a_please_login_answer_is_not_a_login(self):
        session = mock.Mock()
        session.call_tool = mock.AsyncMock(
            return_value=_text_result("Please login to continue."))
        self.assertFalse(asyncio.run(self.c._verify_login_on(session)))
        self.assertFalse(self.c.connected)

    def test_a_raising_probe_is_not_a_login(self):
        session = mock.Mock()
        session.call_tool = mock.AsyncMock(side_effect=RuntimeError("no route"))
        self.assertFalse(asyncio.run(self.c._verify_login_on(session)))


class TransportPickerTestCase(unittest.TestCase):
    """The regression that broke connecting outright.

    The installed SDK exposes only one of the two entry points, so both are
    simulated. What matters in each case is that a transport opens at all, and
    that `terminate_on_close=False` reaches it — the SDK default sends a DELETE
    on the way out, which destroys the server-side session holding the login.
    """

    def setUp(self):
        self.c = _client(None)
        self.calls = {}
        self._saved = sys.modules.get("mcp.client.streamable_http")

    def tearDown(self):
        if self._saved is not None:
            sys.modules["mcp.client.streamable_http"] = self._saved
        else:
            sys.modules.pop("mcp.client.streamable_http", None)
        sys.modules.pop("mcp.shared._httpx_utils", None)

    def _install(self, modern: bool, arity: int):
        """Fake the SDK surface: 2.x has only the underscored name."""
        calls = self.calls
        streams = tuple([mock.Mock(), mock.Mock()][:2]
                        + ([lambda: "from-callback"] if arity == 3 else []))

        class _Ctx:
            async def __aenter__(self_inner):
                return streams

            async def __aexit__(self_inner, *a):
                return False

        module = types.ModuleType("mcp.client.streamable_http")

        if modern:
            def streamable_http_client(url, *, http_client=None,
                                       terminate_on_close=True):
                calls.update(name="streamable_http_client", url=url,
                            http_client=http_client,
                            terminate_on_close=terminate_on_close)
                return _Ctx()
            module.streamable_http_client = streamable_http_client
        else:
            def streamablehttp_client(url, headers=None, timeout=None,
                                      sse_read_timeout=None,
                                      terminate_on_close=True):
                calls.update(name="streamablehttp_client", url=url,
                            headers=headers,
                            terminate_on_close=terminate_on_close)
                return _Ctx()
            module.streamablehttp_client = streamablehttp_client

        sys.modules["mcp.client.streamable_http"] = module

    def _open(self, resume_id=None):
        async def run():
            async with self.c._transport(resume_id) as (read, write):
                return read, write
        return asyncio.run(run())

    def test_it_uses_the_modern_name_when_that_is_all_there_is(self):
        # This is the mcp 2.x shape. The old code imported the removed name
        # and never got a transport at all.
        self._install(modern=True, arity=2)
        with mock.patch.object(kite_client, "_new_http_client",
                               return_value=_FakeHttpClient()):
            read, write = self._open()
        self.assertEqual(self.calls["name"], "streamable_http_client")
        self.assertIsNotNone(read)
        self.assertIsNotNone(write)

    def test_it_falls_back_to_the_legacy_name(self):
        self._install(modern=False, arity=3)
        self._open()
        self.assertEqual(self.calls["name"], "streamablehttp_client")

    def test_the_session_is_never_terminated_on_close(self):
        # The SDK default DELETEs the server-side session on the way out,
        # taking the Zerodha login with it. Closing a stream must cost the
        # stream only.
        for modern in (True, False):
            with self.subTest(modern=modern):
                self._install(modern=modern, arity=2 if modern else 3)
                with mock.patch.object(kite_client, "_new_http_client",
                                       return_value=_FakeHttpClient()):
                    self._open()
                self.assertFalse(self.calls["terminate_on_close"])

    def test_a_resume_id_travels_on_the_request(self):
        # It has to be on the INITIALIZE request: that is the one the server
        # reads to decide whether to hand an existing session back.
        self._install(modern=True, arity=2)
        fake = _FakeHttpClient()
        with mock.patch.object(kite_client, "_new_http_client",
                               return_value=fake) as factory:
            self._open(resume_id="resume-me")
        self.assertEqual(factory.call_args[0][0],
                         {kite_client.MCP_SESSION_HEADER: "resume-me"})

    def test_no_resume_id_means_no_session_header(self):
        self._install(modern=True, arity=2)
        with mock.patch.object(kite_client, "_new_http_client",
                               return_value=_FakeHttpClient()) as factory:
            self._open()
        self.assertEqual(factory.call_args[0][0], {})

    def test_the_capture_hook_is_attached(self):
        self._install(modern=True, arity=2)
        fake = _FakeHttpClient()
        with mock.patch.object(kite_client, "_new_http_client",
                               return_value=fake):
            self._open()
        self.assertIn(self.c._capture_session_id, fake.event_hooks["response"])

    def test_the_three_tuple_callback_is_kept_as_a_fallback(self):
        self._install(modern=False, arity=3)
        self._open()
        self.assertTrue(callable(self.c._session_id_getter))
        self.assertEqual(self.c._session_id_getter(), "from-callback")

    def test_our_http_client_is_closed(self):
        # The SDK only closes a client it created itself, so an unclosed one
        # leaks a connection pool per reconnect.
        self._install(modern=True, arity=2)
        fake = _FakeHttpClient()
        with mock.patch.object(kite_client, "_new_http_client",
                               return_value=fake):
            self._open()
        self.assertTrue(fake.closed)


class RateLimitGuardTestCase(unittest.TestCase):
    """A 429 must cost one call, never the transport (and the login on it).

    This is the automatic logout the installed app's log shows: a burst of
    index-tape calls drew `429 Too Many Requests`, the SDK raised it inside
    the transport task group, and the reconnect landed on a new session.
    """

    def setUp(self):
        import httpx
        self.httpx = httpx
        self._delays = mock.patch.object(kite_client, "RATE_LIMIT_BASE_DELAY", 0)
        self._delays.start()

    def tearDown(self):
        self._delays.stop()

    def _send(self, statuses, body=None, method="POST"):
        httpx = self.httpx
        seen = []

        def handler(request):
            seen.append(request)
            status = statuses[min(len(seen) - 1, len(statuses) - 1)]
            if isinstance(status, Exception):
                raise status
            return httpx.Response(status, json={"ok": True},
                                  headers={"retry-after": "0"} if status == 429 else {})

        guard = kite_client._RateLimitGuard(httpx.MockTransport(handler))
        payload = body if body is not None else {
            "jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {}}
        request = httpx.Request(method, "https://mcp.kite.trade/mcp",
                                json=payload if method == "POST" else None)
        response = asyncio.run(guard.handle_async_request(request))
        return response, seen

    def test_a_passing_response_is_untouched(self):
        response, seen = self._send([200])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(seen), 1)

    def test_a_429_is_retried_until_it_clears(self):
        response, seen = self._send([429, 429, 200])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(seen), 3)

    def test_a_persistent_429_fails_the_call_not_the_transport(self):
        response, seen = self._send([429])
        self.assertEqual(len(seen), kite_client.RATE_LIMIT_RETRIES + 1)
        self.assertEqual(response.status_code, 200)
        response.read()
        body = json.loads(response.content)
        self.assertEqual(body["id"], 7)
        self.assertIn(kite_client.RATE_LIMITED_MESSAGE, body["error"]["message"])

    def test_a_notification_gets_the_real_status_back(self):
        # No id means no JSON-RPC reply is expected; nothing to fail softly.
        response, _ = self._send(
            [429], body={"jsonrpc": "2.0", "method": "notifications/x"})
        self.assertEqual(response.status_code, 429)

    def test_a_dropped_connection_on_a_call_is_not_retried_or_raised(self):
        response, seen = self._send([self.httpx.ReadError("gone")])
        self.assertEqual(len(seen), 1)  # place_order must never be resent
        response.read()
        self.assertIn("error", json.loads(response.content))

    def test_a_dropped_get_stream_still_raises(self):
        with self.assertRaises(self.httpx.ReadError):
            self._send([self.httpx.ReadError("gone")], method="GET")

    def test_the_guard_is_installed_on_new_clients(self):
        client = kite_client._new_http_client({})
        self.assertIsInstance(client._transport, kite_client._RateLimitGuard)
        asyncio.run(client.aclose())


class PacingTestCase(unittest.TestCase):
    def test_bursts_are_spaced(self):
        c = _client(None)
        with mock.patch.object(kite_client, "TOOL_CALL_MIN_INTERVAL", 0.05):
            t0 = time.monotonic()
            for _ in range(4):
                c._pace()
            self.assertGreaterEqual(time.monotonic() - t0, 0.14)


class _FakeHttpClient:
    def __init__(self):
        self.event_hooks = {}
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        self.closed = True
        return False


def _text_result(text):
    return types.SimpleNamespace(
        content=[types.SimpleNamespace(text=text)])


if __name__ == "__main__":
    unittest.main()
