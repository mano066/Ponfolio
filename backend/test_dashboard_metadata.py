import unittest
from datetime import datetime, timezone
from dashboard_metadata import freshness, monthly_buys, utc_now


class MetadataTests(unittest.TestCase):
    def test_missing_timestamp_is_stale(self):
        self.assertTrue(freshness([None])["stale"])
        self.assertTrue(freshness([])["stale"])

    def test_oldest_component_controls_freshness(self):
        self.assertTrue(freshness([utc_now(), "2020-01-01T00:00:00Z"])["stale"])
        self.assertFalse(freshness([utc_now()])["stale"])

    def test_month_purchases_exclude_sales_future_dates_and_other_months(self):
        rows = [
            {"date": "2026-09-01", "type": "BUY", "amount": 100},
            {"date": "2026-09-02", "type": "SELL", "amount": 200},
            {"date": "2026-09-08", "amount": 300},
            {"date": "2026-08-31", "amount": 400},
            {"date": "2026-09-03", "invested": 50},
        ]
        self.assertEqual(monthly_buys(rows, datetime(2026,9,7,tzinfo=timezone.utc)), 150)
