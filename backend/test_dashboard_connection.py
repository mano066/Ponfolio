import unittest
from unittest.mock import patch
from kite_client import KiteMCPClient


class ConnectionTests(unittest.TestCase):
    def client(self):
        with patch.object(KiteMCPClient, "_start_session"):
            client = KiteMCPClient()
        client._ensure_session = lambda: True
        client._parse_tool_result = lambda v: v
        return client

    def test_success_and_duplicate_checks(self):
        client = self.client()
        with patch.object(client, "call_tool", return_value={"user_id": "test"}) as call:
            self.assertTrue(client.check_connection())
            self.assertTrue(client.check_connection())
            self.assertEqual(call.call_count, 1)
        self.assertEqual(client.connection_state, "connected")

    def test_temporary_timeout_preserves_session_identity_and_recovers(self):
        client = self.client()
        client.profile = {"user_id": "test"}
        with patch.object(client, "call_tool", side_effect=TimeoutError("secret must not leak")):
            self.assertFalse(client.check_connection())
        self.assertEqual(client.connection_state, "reconnecting")
        self.assertIsNotNone(client.profile)
        self.assertNotIn("secret", client.last_error)
        client._last_profile_check = 0
        with patch.object(client, "call_tool", return_value={"user_id": "test"}):
            self.assertTrue(client.check_connection())

    def test_expiry_requires_authentication(self):
        client = self.client()
        with patch.object(client, "call_tool", return_value="Please log in"):
            self.assertFalse(client.check_connection())
        self.assertEqual(client.connection_state, "authentication_required")
        self.assertIsNone(client.profile)

    def test_manual_disconnect_not_undone_by_status_poll(self):
        client = self.client()
        client.logout()
        with patch.object(client, "call_tool") as call:
            self.assertFalse(client.check_connection())
            call.assert_not_called()
        client._manual_disconnect = False
        with patch.object(client, "call_tool", return_value={"user_id": "test"}):
            self.assertTrue(client.check_connection())


class ProfileFailureTests(ConnectionTests):
    # Both of these describe an ESTABLISHED login. A session with no user at
    # all is "sign in", not "reconnecting" — see test_kite_session's
    # test_never_signed_in_reports_authentication_required.
    def test_service_error_is_not_logout(self):
        client = self.client()
        client.profile = {"user_id": "test"}
        client._user_id = "test"
        with patch.object(client, "call_tool", return_value={"error": "Service unavailable"}):
            self.assertFalse(client.check_connection())
        self.assertEqual(client.connection_state, "reconnecting")
        self.assertEqual(client.profile, {"user_id": "test"})
        client._last_profile_check = 0
        with patch.object(client, "call_tool", return_value={"user_id": "test"}):
            self.assertTrue(client.check_connection())

    def test_empty_response_is_not_logout(self):
        client = self.client()
        client._user_id = "test"
        with patch.object(client, "call_tool", return_value=None):
            self.assertFalse(client.check_connection())
        self.assertEqual(client.connection_state, "reconnecting")


class VerifiedLoginGraceTests(ConnectionTests):
    """A proven login survives failures that do not prove it ended.

    The status poll runs every 15s, so before this a single slow get_profile
    replaced "Kite Live" with "Kite retrying" seconds after a successful login.
    """

    def connected_client(self):
        client = self.client()
        with patch.object(client, "call_tool", return_value={"user_id": "test"}):
            self.assertTrue(client.check_connection())
        return client

    def test_one_dropped_poll_keeps_the_user_connected(self):
        client = self.connected_client()
        client._last_profile_check = 0
        with patch.object(client, "call_tool", side_effect=TimeoutError("boom")):
            self.assertTrue(client.check_connection())
        self.assertTrue(client.connected)
        self.assertEqual(client.connection_state, "connected")
        self.assertEqual(client._user_id, "test")

    def test_a_streak_reports_degraded_without_dropping_the_login(self):
        client = self.connected_client()
        with patch.object(client, "call_tool", side_effect=TimeoutError("boom")):
            for _ in range(4):
                client._last_profile_check = 0
                self.assertTrue(client.check_connection())
        self.assertTrue(client.connected)
        self.assertEqual(client.connection_state, "degraded")

    def test_the_grace_window_expires_into_reconnecting(self):
        client = self.connected_client()
        client._last_verified_at -= 10_000
        client._last_profile_check = 0
        with patch.object(client, "call_tool", side_effect=TimeoutError("boom")):
            self.assertFalse(client.check_connection())
        self.assertEqual(client.connection_state, "reconnecting")

    def test_a_real_logout_is_not_held_open_by_the_grace_window(self):
        client = self.connected_client()
        client._last_profile_check = 0
        with patch.object(client, "call_tool", return_value="Please log in"):
            self.assertFalse(client.check_connection())
        self.assertEqual(client.connection_state, "authentication_required")
        # The next unproven failure must not resurrect the cleared login.
        client._last_profile_check = 0
        with patch.object(client, "call_tool", side_effect=TimeoutError("boom")):
            self.assertFalse(client.check_connection())
        self.assertFalse(client.connected)
