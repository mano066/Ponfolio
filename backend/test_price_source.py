"""
Tests for price-source attribution.

    python -m unittest test_price_source -v

The bug these pin: the dashboard read "Live from Zerodha" while every single
price had fallen back to Yahoo. Kite's session reported connected — get_profile
genuinely succeeds and returns the real user id — but get_ohlc and get_ltp were
both failing, so the badge described the CONNECTION rather than the DATA.
"""

import unittest

import main


class TestDeriveDataSource(unittest.TestCase):
    def test_only_kite_priced_reads_as_kite(self):
        self.assertEqual(main._derive_data_source(19, 0), "kite")

    def test_only_fallback_priced_reads_as_yfinance(self):
        # The live case: a connected Kite session that priced nothing.
        self.assertEqual(main._derive_data_source(0, 19), "yfinance")

    def test_a_partial_kite_book_is_mixed_not_kite(self):
        """
        The over-claim this exists to prevent. Kite prices the NSE names while
        the BSE-only ones fall back to Yahoo, which is normal — but calling
        that "kite" tells the user every number is live when most are not.
        """
        self.assertEqual(main._derive_data_source(11, 8), "mixed")

    def test_one_stray_kite_price_does_not_promote_the_whole_book(self):
        self.assertEqual(main._derive_data_source(1, 18), "mixed")

    def test_nothing_priced_is_none_not_yfinance(self):
        # "No price arrived" and "Yahoo priced it" are different facts.
        self.assertEqual(main._derive_data_source(0, 0), "none")

    def test_the_connection_never_enters_into_it(self):
        # Deliberately no kite_connected argument: a session existing is not
        # evidence that a price came from it, and that conflation was the bug.
        import inspect
        params = list(inspect.signature(main._derive_data_source).parameters)
        self.assertEqual(params, ["from_kite", "from_yf"])


class TestProviderConstants(unittest.TestCase):
    def test_the_four_providers_are_distinct(self):
        srcs = {
            main.PRICE_SRC_KITE,
            main.PRICE_SRC_YF,
            main.PRICE_SRC_KITE_SNAPSHOT,
            main.PRICE_SRC_NONE,
        }
        self.assertEqual(len(srcs), 4)

    def test_a_snapshot_price_is_not_counted_as_live_kite(self):
        """
        kite_holdings is the price Kite sent at sync time, not a live quote.
        Counting it as live Kite data would resurrect the same over-claim in a
        subtler form: the number really did come from Zerodha, but hours ago.
        """
        self.assertNotEqual(main.PRICE_SRC_KITE_SNAPSHOT, main.PRICE_SRC_KITE)
        # And it must not feed the kite counter — derive only sees the two.
        self.assertEqual(main._derive_data_source(0, 0), "none")


class TestFetchPriceContract(unittest.TestCase):
    def test_two_value_wrapper_still_exists_for_old_callers(self):
        # Several call sites only want numbers; the wrapper keeps them working
        # rather than forcing a signature change across the file.
        import inspect
        self.assertIn("yf_sym",
                      inspect.signature(main._fetch_price).parameters)
        self.assertIn("yf_sym",
                      inspect.signature(main._fetch_price_with_source).parameters)


class TestKiteAuthenticationState(unittest.TestCase):
    def _client(self, parsed=None, error=None):
        client = type(main.kite_client).__new__(type(main.kite_client))
        client.connected = True
        client.profile = {"user_id": "OLD"}
        client._user_name = "Old User"
        client._user_id = "OLD"
        client._email = "old@example.com"
        client.last_error = None
        client._ensure_session = lambda: True
        if error is not None:
            def fail(*_args, **_kwargs):
                raise error
            client.call_tool = fail
        else:
            client.call_tool = lambda *_args, **_kwargs: parsed
        client._parse_tool_result = lambda value: value
        return client

    def test_failed_profile_does_not_discard_a_proven_identity(self):
        # A service error is not a logout. Clearing the identity here is what
        # turned one bad frame on the stream into a fresh Zerodha login, so the
        # user is kept on record and the session is retried instead.
        client = self._client("Failed to execute get_profile")
        self.assertFalse(client.check_connection())
        self.assertFalse(client.connected)
        self.assertEqual(client._user_id, "OLD")
        self.assertEqual(client.connection_state, "reconnecting")
        self.assertNotIn("Failed", client.last_error)

    def test_profile_exception_does_not_discard_a_proven_identity(self):
        client = self._client(error=RuntimeError("session gone"))
        self.assertFalse(client.check_connection())
        self.assertFalse(client.connected)
        self.assertEqual(client.profile, {"user_id": "OLD"})
        self.assertEqual(client.connection_state, "reconnecting")
        # The raw exception text must not reach the user-facing field.
        self.assertNotIn("session gone", client.last_error)

    def test_a_proven_expiry_does_clear_the_identity(self):
        client = self._client("Please log in first using the login tool")
        self.assertFalse(client.check_connection())
        self.assertIsNone(client._user_id)
        self.assertIsNone(client.profile)
        self.assertEqual(client.connection_state, "authentication_required")

    def test_valid_profile_reestablishes_identity(self):
        client = self._client({
            "user_id": "AB1234",
            "user_name": "Test User",
            "email": "user@example.com",
        })
        self.assertTrue(client.check_connection())
        self.assertTrue(client.connected)
        self.assertEqual(client._user_id, "AB1234")

    def test_holdings_auth_error_clears_stale_connected_identity(self):
        client = self._client("Please log in first using the login tool")
        self.assertIsNone(client.get_holdings())
        self.assertFalse(client.connected)
        self.assertIsNone(client._user_name)


if __name__ == "__main__":
    unittest.main()
