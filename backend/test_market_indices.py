"""
Unit tests for the pure market-index tape layer.

    python -m unittest test_market_indices -v

No network, no yfinance — every series is hand-fed so the maths is pinned down.
"""

import unittest
from datetime import date, timedelta

import market_indices as mi


def _meta(symbol="^NSEI"):
    return dict(mi._META_BY_SYMBOL[symbol])


class TestUniverse(unittest.TestCase):
    def test_universe_symbols_are_unique(self):
        self.assertEqual(len(mi.UNIVERSE_SYMBOLS), len(set(mi.UNIVERSE_SYMBOLS)))

    def test_universe_covers_all_four_groups(self):
        groups = {m["group"] for m in mi.INDEX_UNIVERSE}
        self.assertEqual(groups, set(mi.GROUP_ORDER))

    def test_every_entry_has_symbol_label_group(self):
        for meta in mi.INDEX_UNIVERSE:
            self.assertTrue(meta["symbol"])
            self.assertTrue(meta["label"])
            self.assertIn(meta["group"], mi.GROUP_ORDER)

    def test_sensex_is_present(self):
        # Verified live during planning; guard against a silent removal.
        self.assertIn("^BSESN", mi.UNIVERSE_SYMBOLS)


class TestSectorMapping(unittest.TestCase):
    """Every benchmark must resolve inside the universe, or dip_map misses it."""

    def test_all_rule_targets_are_in_the_universe(self):
        for _, (symbol, _label) in mi._SECTOR_RULES:
            self.assertIn(symbol, mi.UNIVERSE_SYMBOLS)

    def test_indian_sector_names(self):
        self.assertEqual(mi.sector_index_for("Banking")[0], "^NSEBANK")
        self.assertEqual(mi.sector_index_for("IT")[0], "^CNXIT")
        self.assertEqual(mi.sector_index_for("Pharma")[0], "^CNXPHARMA")
        self.assertEqual(mi.sector_index_for("Auto")[0], "^CNXAUTO")
        self.assertEqual(mi.sector_index_for("FMCG")[0], "^CNXFMCG")
        self.assertEqual(mi.sector_index_for("Energy")[0], "^CNXENERGY")
        self.assertEqual(mi.sector_index_for("Metals")[0], "^CNXMETAL")

    def test_yfinance_sector_names(self):
        """_get_stock_info feeds us US-centric names — they must map too."""
        self.assertEqual(mi.sector_index_for("Financial Services")[0], "^NSEBANK")
        self.assertEqual(mi.sector_index_for("Technology")[0], "^CNXIT")
        self.assertEqual(mi.sector_index_for("Healthcare")[0], "^CNXPHARMA")
        self.assertEqual(mi.sector_index_for("Consumer Defensive")[0], "^CNXFMCG")
        self.assertEqual(mi.sector_index_for("Consumer Cyclical")[0], "^CNXAUTO")
        self.assertEqual(mi.sector_index_for("Basic Materials")[0], "^CNXMETAL")
        self.assertEqual(mi.sector_index_for("Utilities")[0], "^CNXENERGY")

    def test_unknown_and_empty_fall_back_to_nifty(self):
        for text in ("", None, "Widgets", "Aerospace & Defence"):
            self.assertEqual(mi.sector_index_for(text), mi.DEFAULT_BENCHMARK)

    def test_single_word_rules_match_tokens_not_substrings(self):
        """'it' must not fire on 'capital' or 'unit'."""
        self.assertEqual(mi.sector_index_for("Capital Goods"), mi.DEFAULT_BENCHMARK)

    def test_benchmark_for_stock_prefers_sector_over_size(self):
        self.assertEqual(
            mi.benchmark_for_stock("SUNPHARMA.NS", "Healthcare", "midcap")[0],
            "^CNXPHARMA")

    def test_benchmark_for_stock_uses_size_when_sector_unknown(self):
        self.assertEqual(mi.benchmark_for_stock("X.NS", "", "smallcap")[0],
                         "NIFTYSMLCAP250.NS")
        self.assertEqual(mi.benchmark_for_stock("X.NS", "", "midcap")[0],
                         "NIFTY_MIDCAP_100.NS")

    def test_benchmark_for_stock_defaults_to_nifty(self):
        self.assertEqual(mi.benchmark_for_stock("X.NS", "", ""), mi.DEFAULT_BENCHMARK)


class TestSummarizeIndex(unittest.TestCase):
    def test_basic_maths(self):
        # High 120, last 90 -> 25% off the high. Prev 100 -> -10% on the day.
        closes = [100.0] * 150 + [120.0, 100.0, 90.0]
        row = mi.summarize_index(_meta(), closes)
        self.assertEqual(row["status"], mi.STATUS_OK)
        self.assertEqual(row["last"], 90.0)
        self.assertEqual(row["prev_close"], 100.0)
        self.assertEqual(row["day_chg"], -10.0)
        self.assertEqual(row["day_chg_pct"], -10.0)
        self.assertEqual(row["high_52w"], 120.0)
        self.assertEqual(row["low_52w"], 90.0)
        self.assertEqual(row["off_high_pct"], 25.0)
        self.assertFalse(row["at_high"])
        self.assertFalse(row["short_window"])

    def test_off_high_is_a_positive_magnitude(self):
        """The engine consumes magnitudes; a sign here would be a bug factory."""
        row = mi.summarize_index(_meta(), [200.0] + [150.0] * 200)
        self.assertGreater(row["off_high_pct"], 0)
        self.assertEqual(row["off_high_pct"], 25.0)

    def test_at_high_flag_and_zero_off_high(self):
        row = mi.summarize_index(_meta(), [90.0] * 150 + [100.0])
        self.assertEqual(row["off_high_pct"], 0.0)
        self.assertTrue(row["at_high"])

    def test_at_high_tolerance(self):
        # 0.5% below the high still reads as "at the high".
        row = mi.summarize_index(_meta(), [100.0] * 150 + [99.5])
        self.assertEqual(row["off_high_pct"], 0.5)
        self.assertTrue(row["at_high"])

    def test_short_window_is_flagged(self):
        row = mi.summarize_index(_meta(), [100.0, 101.0, 102.0])
        self.assertEqual(row["status"], mi.STATUS_OK)
        self.assertTrue(row["short_window"])
        self.assertEqual(row["points"], 3)

    def test_single_point_has_no_day_change(self):
        row = mi.summarize_index(_meta(), [100.0])
        self.assertEqual(row["last"], 100.0)
        self.assertIsNone(row["prev_close"])
        self.assertIsNone(row["day_chg"])
        self.assertIsNone(row["day_chg_pct"])
        # A one-point series is its own high and low, so every distance from
        # that high is zero — and a zero drawdown is what the status ladder
        # reads as "at its high". Yahoo serves exactly one bar for several NSE
        # sector indices, so half the tape flew an OVERHEATED verdict inferred
        # from a single close. The range figures are withheld instead.
        self.assertIsNone(row["off_high_pct"])
        self.assertIsNone(row["above_low_pct"])
        self.assertIsNone(row["high_52w"])
        self.assertTrue(row["history_unavailable"])
        self.assertEqual(row["market_status"], mi.MARKET_UNKNOWN)

    def test_a_real_range_still_reports_its_drawdown(self):
        # The guard must not silence indices that do have history.
        row = mi.summarize_index(_meta(), [100.0, 120.0, 90.0, 110.0, 108.0])
        self.assertFalse(row["history_unavailable"])
        self.assertEqual(row["high_52w"], 120.0)
        self.assertEqual(row["off_high_pct"], 10.0)
        self.assertNotEqual(row["market_status"], mi.MARKET_UNKNOWN)

    def test_nan_and_junk_values_are_dropped(self):
        row = mi.summarize_index(
            _meta(), [float("nan"), 100.0, None, "junk", 0, -5, 110.0])
        self.assertEqual(row["points"], 2)
        self.assertEqual(row["last"], 110.0)
        self.assertEqual(row["prev_close"], 100.0)

    def test_empty_series_is_unavailable_not_zero(self):
        """The core discipline: a dead feed must never look like a flat market."""
        for series in ([], None, [float("nan")], ["junk"], [0, -1]):
            row = mi.summarize_index(_meta(), series)
            self.assertEqual(row["status"], mi.STATUS_UNAVAILABLE)
            self.assertIsNone(row["last"])
            self.assertIsNone(row["day_chg_pct"])
            self.assertIsNone(row["off_high_pct"])
            self.assertNotEqual(row["off_high_pct"], 0.0)

    def test_unavailable_row_keeps_identity_fields(self):
        row = mi.summarize_index(_meta("^CNXIT"), [])
        self.assertEqual(row["symbol"], "^CNXIT")
        self.assertEqual(row["label"], "IT")
        self.assertEqual(row["group"], mi.GROUP_SECTOR)

    def test_row_shape_is_identical_ok_vs_unavailable(self):
        ok = mi.summarize_index(_meta(), [100.0, 101.0])
        dead = mi.summarize_index(_meta(), [])
        self.assertEqual(set(ok), set(dead))


class TestBuildTape(unittest.TestCase):
    def _full_tape(self, off_high=5.0):
        rows = []
        for meta in mi.INDEX_UNIVERSE:
            high = 100.0
            last = high * (1 - off_high / 100)
            rows.append(mi.summarize_index(dict(meta), [high] * 150 + [last]))
        return mi.build_tape(rows, as_of=date(2026, 9, 3))

    def test_returns_every_index_in_universe_order(self):
        tape = mi.build_tape([], as_of=date(2026, 9, 3))
        self.assertEqual([r["symbol"] for r in tape["indices"]],
                         list(mi.UNIVERSE_SYMBOLS))

    def test_missing_rows_are_filled_as_unavailable(self):
        one = mi.summarize_index(_meta(), [100.0] * 150 + [95.0])
        tape = mi.build_tape([one])
        self.assertEqual(len(tape["indices"]), len(mi.INDEX_UNIVERSE))
        statuses = {r["symbol"]: r["status"] for r in tape["indices"]}
        self.assertEqual(statuses["^NSEI"], mi.STATUS_OK)
        self.assertEqual(statuses["^CNXIT"], mi.STATUS_UNAVAILABLE)

    def test_order_is_stable_regardless_of_input_order(self):
        rows = [mi.summarize_index(dict(m), [100.0] * 150 + [99.0])
                for m in reversed(mi.INDEX_UNIVERSE)]
        tape = mi.build_tape(rows)
        self.assertEqual([r["symbol"] for r in tape["indices"]],
                         list(mi.UNIVERSE_SYMBOLS))

    def test_breadth_counts_only_available_rows(self):
        up = mi.summarize_index(_meta("^NSEI"), [100.0, 110.0])
        down = mi.summarize_index(_meta("^CNXIT"), [100.0, 90.0])
        tape = mi.build_tape([up, down])
        self.assertEqual(tape["breadth"]["up"], 1)
        self.assertEqual(tape["breadth"]["down"], 1)
        self.assertEqual(tape["breadth"]["available"], 2)
        self.assertEqual(tape["breadth"]["total"], len(mi.INDEX_UNIVERSE))

    def test_groups_are_emitted_in_order(self):
        tape = mi.build_tape([])
        self.assertEqual([g["key"] for g in tape["groups"]], list(mi.GROUP_ORDER))

    def test_group_symbol_lists_partition_the_universe(self):
        tape = mi.build_tape([])
        listed = [s for g in tape["groups"] for s in g["symbols"]]
        self.assertEqual(sorted(listed), sorted(mi.UNIVERSE_SYMBOLS))

    def test_as_of_is_echoed(self):
        tape = mi.build_tape([], as_of=date(2026, 9, 3))
        self.assertEqual(tape["as_of"], "2026-09-03")


class TestMoodAndSummary(unittest.TestCase):
    def _nifty_at(self, off_high_pct):
        last = 100.0 * (1 - off_high_pct / 100)
        return mi.build_tape(
            [mi.summarize_index(_meta("^NSEI"), [100.0] * 150 + [last])])

    def test_mood_bands(self):
        self.assertEqual(self._nifty_at(0.0)["market_mood"], "near-high")
        self.assertEqual(self._nifty_at(3.0)["market_mood"], "soft")
        self.assertEqual(self._nifty_at(8.0)["market_mood"], "falling")
        self.assertEqual(self._nifty_at(15.0)["market_mood"], "deep-fall")

    def test_mood_unknown_when_nifty_missing(self):
        self.assertEqual(mi.build_tape([])["market_mood"], "unknown")

    def test_mood_ignores_other_indices(self):
        """A crashing metal ETF must not colour the broad-market read."""
        nifty = mi.summarize_index(_meta("^NSEI"), [100.0] * 150 + [100.0])
        metal = mi.summarize_index(_meta("^CNXMETAL"), [100.0] * 150 + [50.0])
        self.assertEqual(mi.build_tape([nifty, metal])["market_mood"], "near-high")

    def test_summary_line_reads_plainly(self):
        self.assertIn("at its 1-year high", self._nifty_at(0.0)["summary"])
        self.assertIn("8.0% below", self._nifty_at(8.0)["summary"])
        self.assertIn("not available", mi.build_tape([])["summary"])


class TestDipMap(unittest.TestCase):
    def test_maps_symbol_to_off_high(self):
        row = mi.summarize_index(_meta("^CNXIT"), [100.0] * 150 + [80.0])
        dips = mi.dip_map(mi.build_tape([row]))
        self.assertEqual(dips["^CNXIT"], 20.0)

    def test_unavailable_maps_to_none_not_zero(self):
        """None means 'unknown' to the scorer; 0.0 would mean 'at its high'."""
        dips = mi.dip_map(mi.build_tape([]))
        self.assertIsNone(dips["^NSEI"])
        self.assertNotEqual(dips["^NSEI"], 0.0)

    def test_covers_every_universe_symbol(self):
        dips = mi.dip_map(mi.build_tape([]))
        self.assertEqual(set(dips), set(mi.UNIVERSE_SYMBOLS))

    def test_handles_empty_and_malformed_input(self):
        self.assertEqual(mi.dip_map({}), {})
        self.assertEqual(mi.dip_map({"indices": [None, "junk", {}]}), {})


class TestEmptyTape(unittest.TestCase):
    def test_shape_matches_populated_tape(self):
        row = mi.summarize_index(_meta(), [100.0] * 150 + [95.0])
        self.assertEqual(set(mi.empty_tape()), set(mi.build_tape([row])))

    def test_every_index_unavailable(self):
        tape = mi.empty_tape()
        self.assertTrue(all(r["status"] == mi.STATUS_UNAVAILABLE
                            for r in tape["indices"]))
        self.assertEqual(tape["breadth"]["available"], 0)




# ══════════════════════════════════════════════════════════════════════════
#  ENRICHED TAPE METRICS
# ══════════════════════════════════════════════════════════════════════════

def _rising(n=400, start=100.0):
    """Strictly rising closes — every statistic is hand-checkable."""
    return [start + i for i in range(n)]


def _dates_from(n, first=date(2024, 1, 1)):
    return [first + timedelta(days=i) for i in range(n)]


class TestFiftyTwoWeekWindowIsASlice(unittest.TestCase):
    """
    The regression this guards is the whole reason the window is a slice.

    summarize_index is fed a decade of closes by the backtest path.  If the
    52-week high were max(series), a ten-year high would be served as a
    52-week high and every drawdown the deploy engine scores against would be
    inflated — silently, and only for the indices with the longest history.
    """

    def test_52w_high_ignores_bars_older_than_the_window(self):
        # A spike far outside the 52-week window must not become the 52w high.
        series = [1000.0] + [100.0 + i for i in range(300)]
        row = mi.summarize_index(_meta(), series)
        self.assertEqual(row["high_52w"], 399.0)      # max of the last 252
        self.assertEqual(row["high_max"], 1000.0)     # the spike survives here

    def test_off_high_pct_is_measured_against_the_52w_high(self):
        series = [1000.0] + [100.0] * 300
        row = mi.summarize_index(_meta(), series)
        self.assertEqual(row["off_high_pct"], 0.0)       # flat inside the window
        self.assertEqual(row["off_max_high_pct"], 90.0)  # 90% below the spike

    def test_short_series_uses_everything_it_has(self):
        row = mi.summarize_index(_meta(), [100.0, 90.0])
        self.assertEqual(row["points_52w"], 2)
        self.assertTrue(row["short_window"])


class TestTrailingReturns(unittest.TestCase):
    def test_offsets_match_hand_computation(self):
        s = _rising()
        row = mi.summarize_index(_meta(), s)
        for key, off in (("chg_1w_pct", 5), ("chg_1m_pct", 21), ("chg_3m_pct", 63)):
            past = s[-1 - off]
            self.assertAlmostEqual(row[key], round((s[-1] - past) / past * 100, 2))

    def test_return_is_unknown_when_series_cannot_reach_back(self):
        # 10 closes cannot answer a 3-month question.
        row = mi.summarize_index(_meta(), _rising(10))
        self.assertIsNotNone(row["chg_1w_pct"])
        self.assertIsNone(row["chg_1m_pct"])
        self.assertIsNone(row["chg_3m_pct"])


class TestYearToDate(unittest.TestCase):
    def test_ytd_measures_from_last_close_of_previous_year(self):
        n = 400
        s, d = _rising(n), _dates_from(n)
        row = mi.summarize_index(_meta(), s, dates=d)
        base = s[d.index(date(2024, 12, 31))]
        self.assertAlmostEqual(row["chg_ytd_pct"],
                               round((s[-1] - base) / base * 100, 2))

    def test_no_dates_means_unknown_not_zero(self):
        self.assertIsNone(mi.summarize_index(_meta(), _rising())["chg_ytd_pct"])

    def test_ragged_dates_are_refused_rather_than_misaligned(self):
        # A short date list would silently put the year boundary in the wrong
        # place; unknown is the only honest answer.
        row = mi.summarize_index(_meta(), _rising(400), dates=_dates_from(10))
        self.assertIsNone(row["chg_ytd_pct"])

    def test_dates_stay_aligned_when_bad_closes_are_dropped(self):
        n = 400
        s, d = _rising(n), _dates_from(n)
        s[5] = float("nan")          # dropped by the cleaner
        row = mi.summarize_index(_meta(), s, dates=d)
        self.assertEqual(row["points"], n - 1)
        self.assertIsNotNone(row["chg_ytd_pct"])

    def test_series_entirely_within_one_year_has_no_ytd(self):
        row = mi.summarize_index(_meta(), _rising(30), dates=_dates_from(30))
        self.assertIsNone(row["chg_ytd_pct"])


class TestMovingAverages(unittest.TestCase):
    def test_dma_matches_mean_of_window(self):
        s = _rising()
        row = mi.summarize_index(_meta(), s)
        for win in mi.DMA_WINDOWS:
            self.assertAlmostEqual(row["dma_%d" % win],
                                   round(sum(s[-win:]) / win, 2))

    def test_dma_is_unknown_when_series_is_shorter_than_the_window(self):
        row = mi.summarize_index(_meta(), _rising(60))
        self.assertIsNotNone(row["dma_50"])
        self.assertIsNone(row["dma_100"])
        self.assertIsNone(row["dma_200"])
        self.assertIsNone(row["vs_dma_200_pct"])

    def test_vs_dma_sign_follows_price_position(self):
        up = mi.summarize_index(_meta(), _rising())
        self.assertGreater(up["vs_dma_50_pct"], 0)
        down = mi.summarize_index(_meta(), list(reversed(_rising())))
        self.assertLess(down["vs_dma_50_pct"], 0)


class TestRSI(unittest.TestCase):
    def test_monotonic_rise_pins_rsi_at_100(self):
        self.assertEqual(mi.summarize_index(_meta(), _rising())["rsi_14"], 100.0)

    def test_rsi_is_unknown_below_the_minimum_window(self):
        row = mi.summarize_index(_meta(), _rising(mi.MIN_POINTS_FOR_RSI - 1))
        self.assertIsNone(row["rsi_14"])

    def test_rsi_stays_in_range_on_a_choppy_series(self):
        s = [100.0 + (3 if i % 2 else -2) * (i % 7) for i in range(200)]
        rsi = mi.summarize_index(_meta(), s)["rsi_14"]
        self.assertIsNotNone(rsi)
        self.assertGreaterEqual(rsi, 0.0)
        self.assertLessEqual(rsi, 100.0)


class TestMarketStatus(unittest.TestCase):
    def _status_at_drawdown(self, dd_pct):
        return mi.summarize_index(
            _meta(), [100.0] * 250 + [100.0 * (1 - dd_pct / 100)])["market_status"]

    def test_ladder_cut_points(self):
        self.assertEqual(self._status_at_drawdown(0), mi.MARKET_OVERHEATED)
        self.assertEqual(self._status_at_drawdown(5), mi.MARKET_NORMAL)
        self.assertEqual(self._status_at_drawdown(12), mi.MARKET_DIP)
        self.assertEqual(self._status_at_drawdown(20), mi.MARKET_ATTRACTIVE)
        self.assertEqual(self._status_at_drawdown(35), mi.MARKET_HIGH_RISK)

    def test_red_marks_risk_not_a_good_dip(self):
        """
        The palette runs opposite to a P&L one on purpose. An index at its own
        high is the dangerous place to deploy a dip reserve, so that is the red
        rung; a genuine correction is green. An earlier ladder had this
        inverted and painted a deep dip red — alarming the user at exactly the
        moment this feature exists to catch.
        """
        red = mi.MARKET_STATUS_EMOJI[mi.MARKET_OVERHEATED]
        green = mi.MARKET_STATUS_EMOJI[mi.MARKET_ATTRACTIVE]
        self.assertEqual(red, "🔴")
        self.assertEqual(green, "🟢")
        # At the high -> red. In a correction -> green. Never the reverse.
        self.assertEqual(self._status_at_drawdown(0), mi.MARKET_OVERHEATED)
        self.assertEqual(self._status_at_drawdown(20), mi.MARKET_ATTRACTIVE)
        self.assertNotEqual(
            mi.MARKET_STATUS_EMOJI[self._status_at_drawdown(20)], red)

    def test_unavailable_index_is_unknown_not_extended(self):
        # "The feed is down" must never render as "sitting at its high".
        self.assertEqual(mi.classify_market_status(None), mi.MARKET_UNKNOWN)
        self.assertEqual(mi._unavailable_row(_meta())["market_status"],
                         mi.MARKET_UNKNOWN)

    def test_every_status_has_a_label_and_an_emoji(self):
        for key in (mi.MARKET_OVERHEATED, mi.MARKET_NORMAL, mi.MARKET_DIP,
                    mi.MARKET_ATTRACTIVE, mi.MARKET_HIGH_RISK,
                    mi.MARKET_UNKNOWN):
            self.assertIn(key, mi.MARKET_STATUS_LABELS)
            self.assertIn(key, mi.MARKET_STATUS_EMOJI)


class TestValuationIsHonestlyUnavailable(unittest.TestCase):
    """
    Valuation is specified by the dashboard but no feed in use carries a
    historical index P/E or P/B.  It must read as unavailable, never as a
    number, and never as zero.
    """

    def test_valuation_fields_are_none_with_a_stated_reason(self):
        row = mi.summarize_index(_meta(), _rising())
        for key in ("pe", "pb", "pe_avg_5y", "pb_avg_5y"):
            self.assertIsNone(row[key])
        self.assertEqual(row["valuation_status"], mi.VALUATION_UNAVAILABLE)
        self.assertTrue(row["valuation_note"])


class TestRowShapeInvariant(unittest.TestCase):
    def test_ok_and_unavailable_rows_still_match_after_enrichment(self):
        ok = mi.summarize_index(_meta(), _rising())
        self.assertEqual(set(ok), set(mi._unavailable_row(_meta())))

    def test_every_metric_key_is_declared_in_the_template(self):
        ok = mi.summarize_index(_meta(), _rising())
        identity = {"symbol", "label", "group", "status"}
        self.assertEqual(set(ok) - identity, set(mi._EMPTY_METRICS))


class TestCorporateActionTrimming(unittest.TestCase):
    """
    The threshold here separates two real populations measured on this
    universe, and both bounds matter — see CORPORATE_ACTION_1D_MOVE_PCT.
    """

    def test_unit_split_is_detected_and_earlier_bars_dropped(self):
        closes = [0.34] * 300 + [34.0] * 700          # GOLDBEES-shaped step
        out, _dates, info = mi.trim_corporate_actions(closes)
        self.assertTrue(info["trimmed"])
        self.assertEqual(info["dropped"], 300)
        self.assertEqual(len(out), 700)

    def test_genuine_thirty_percent_index_day_is_kept(self):
        """
        ^CNXPSUBANK rose 30% on 2017-10-25 on the bank recapitalisation
        announcement. A 25% cut discarded 280 bars of real history for it.
        """
        closes = [100.0] * 300 + [130.0] * 300
        _out, _dates, info = mi.trim_corporate_actions(closes)
        self.assertFalse(info["trimmed"])

    def test_two_for_one_split_is_still_caught(self):
        # The smallest step a split can produce, at exactly -50%.
        closes = [100.0] * 300 + [50.0] * 300
        _out, _dates, info = mi.trim_corporate_actions(closes)
        self.assertTrue(info["trimmed"])

    def test_dates_stay_aligned_with_the_trimmed_closes(self):
        closes = [1.0] * 100 + [100.0] * 100
        dates = _dates_from(200)
        out, out_dates, info = mi.trim_corporate_actions(closes, dates)
        self.assertEqual(len(out), len(out_dates))
        self.assertEqual(out_dates[0], dates[info["dropped"]])

    def test_only_the_last_event_sets_the_cut(self):
        closes = [1.0] * 100 + [100.0] * 100 + [10000.0] * 100
        _out, _dates, info = mi.trim_corporate_actions(closes)
        self.assertEqual(len(info["events"]), 2)
        self.assertEqual(info["dropped"], 200)

    def test_clean_series_is_returned_untouched(self):
        closes = [100.0 + i for i in range(300)]
        out, _dates, info = mi.trim_corporate_actions(closes)
        self.assertFalse(info["trimmed"])
        self.assertEqual(out, closes)

    def test_too_short_to_judge_is_not_trimmed(self):
        out, _dates, info = mi.trim_corporate_actions([100.0])
        self.assertFalse(info["trimmed"])
        self.assertEqual(out, [100.0])


class TestKiteCandles(unittest.TestCase):
    """Kite is the only source that will give the sector indices a series."""

    def test_both_response_shapes_parse(self):
        # Kite has returned dicts in some builds and bare arrays in others.
        dicts = [{"date": "2026-09-15T00:00:00+0530", "close": 27000.0},
                 {"date": "2026-09-16T00:00:00+0530", "close": 27100.0}]
        arrays = [["2026-09-15T00:00:00+0530", 1, 2, 1, 27000.0, 0],
                  ["2026-09-16T00:00:00+0530", 1, 2, 1, 27100.0, 0]]
        self.assertEqual(mi.parse_candles(dicts), mi.parse_candles(arrays))
        self.assertEqual(mi.parse_candles(dicts)[1], [27000.0, 27100.0])

    def test_two_bars_on_one_day_count_as_one_session(self):
        # Keeping the time would make an intraday refresh look like extra
        # history to everything downstream that counts points.
        days, closes = mi.parse_candles([
            {"date": "2026-09-17T00:00:00+0530", "close": 27215.0},
            {"date": "2026-09-17T15:30:00+0530", "close": 27220.0}])
        self.assertEqual(len(days), 1)
        self.assertEqual(closes, [27220.0])

    def test_oldest_first(self):
        days, _ = mi.parse_candles([
            {"date": "2026-09-17", "close": 3.0},
            {"date": "2026-09-15", "close": 1.0},
            {"date": "2026-09-16", "close": 2.0}])
        self.assertEqual([d.isoformat() for d in days],
                         ["2026-09-15", "2026-09-16", "2026-09-17"])

    def test_junk_rows_are_dropped_not_guessed(self):
        days, closes = mi.parse_candles([
            {"date": "not a date", "close": 1.0},
            {"date": "2026-09-16", "close": 0},
            {"date": "2026-09-16", "close": None},
            {"close": 5.0},
            [], None, "nonsense",
            {"date": "2026-09-17", "close": 27215.0}])
        self.assertEqual(len(days), 1)
        self.assertEqual(closes, [27215.0])

    def test_an_empty_response_yields_an_empty_series(self):
        self.assertEqual(mi.parse_candles([]), ([], []))
        self.assertEqual(mi.parse_candles(None), ([], []))

    def test_a_parsed_series_is_long_enough_to_produce_a_range(self):
        # The point of the whole exercise: enough closes that summarize_index
        # stops withholding the 52-week figures.
        candles = [{"date": f"2026-0{m}-15", "close": 100.0 + m}
                   for m in range(1, 8)]
        days, closes = mi.parse_candles(candles)
        self.assertGreaterEqual(len(closes), mi.MIN_POINTS_FOR_RANGE)
        row = mi.summarize_index(_meta(), closes, dates=days)
        self.assertFalse(row["history_unavailable"])
        self.assertIsNotNone(row["off_high_pct"])


class TestKiteLiveOverlay(unittest.TestCase):
    """Kite supplies the live level and the previous close; Yahoo the range.

    The sector cards that read "no history" always had a live level — what was
    missing was a prior close to measure it against. Kite ships both in one
    OHLC response, which fixes the day change without touching the 52-week
    figures that genuinely need a series.
    """

    def row(self, symbol="^CNXAUTO", **kw):
        base = {"symbol": symbol, "label": "AUTO", "last": 27215.0,
                "prev_close": None, "day_chg": None, "day_chg_pct": None,
                "day_chg_span_days": None, "stale_history": False,
                "off_high_pct": None, "high_52w": None,
                "history_unavailable": True}
        base.update(kw)
        return base

    def test_a_quote_supplies_the_missing_day_change(self):
        rows = [self.row()]
        n = mi.apply_live_quotes(rows, {
            "NSE:NIFTY AUTO": {"last_price": 27215.0,
                               "ohlc": {"open": 27000.0, "high": 27300.0,
                                        "low": 26950.0, "close": 27000.0}}})
        self.assertEqual(n, 1)
        self.assertEqual(rows[0]["prev_close"], 27000.0)
        self.assertEqual(rows[0]["day_chg"], 215.0)
        self.assertAlmostEqual(rows[0]["day_chg_pct"], 0.8, places=1)
        self.assertEqual(rows[0]["live_source"], "kite")

    def test_the_52_week_figures_are_left_alone(self):
        # A day change is not a range. Filling the 52-week fields from an OHLC
        # response would be inventing history the feed does not have.
        rows = [self.row()]
        mi.apply_live_quotes(rows, {
            "NSE:NIFTY AUTO": {"last_price": 27215.0,
                               "ohlc": {"close": 27000.0}}})
        self.assertIsNone(rows[0]["off_high_pct"])
        self.assertIsNone(rows[0]["high_52w"])
        self.assertTrue(rows[0]["history_unavailable"])

    def test_an_index_with_real_history_keeps_its_range(self):
        rows = [self.row(off_high_pct=11.4, high_52w=26328.55,
                         history_unavailable=False)]
        mi.apply_live_quotes(rows, {
            "NSE:NIFTY AUTO": {"last_price": 27215.0,
                               "ohlc": {"close": 27000.0}}})
        self.assertEqual(rows[0]["high_52w"], 26328.55)
        self.assertEqual(rows[0]["off_high_pct"], 11.4)

    def test_a_quote_without_a_previous_close_updates_only_the_level(self):
        rows = [self.row()]
        mi.apply_live_quotes(rows, {
            "NSE:NIFTY AUTO": {"last_price": 27300.0, "ohlc": {}}})
        self.assertEqual(rows[0]["last"], 27300.0)
        self.assertIsNone(rows[0]["day_chg"])

    def test_junk_and_zero_quotes_are_ignored(self):
        # A zero close would read as a 100% crash on everything derived from it.
        rows = [self.row()]
        before = dict(rows[0])
        n = mi.apply_live_quotes(rows, {
            "NSE:NIFTY AUTO": {"last_price": 0, "ohlc": {"close": 27000.0}},
            "NSE:NIFTY FMCG": {"last_price": "junk"},
            "NSE:NOT A REAL INDEX": {"last_price": 100.0}})
        self.assertEqual(n, 0)
        self.assertEqual(rows[0], before)

    def test_every_mapped_instrument_round_trips(self):
        for sym, instrument in mi.KITE_INDEX.items():
            with self.subTest(sym):
                self.assertEqual(mi.KITE_TO_YAHOO[instrument], sym)

    def test_only_indices_with_no_nse_instrument_are_unmapped(self):
        # SENSEX is a BSE index; the other two are American. Everything else
        # must be mapped, or a sector card silently keeps its blank.
        unmapped = {m["symbol"] for m in mi.INDEX_UNIVERSE
                    if m["symbol"] not in mi.KITE_INDEX}
        self.assertEqual(unmapped, {"^BSESN", "^GSPC", "^IXIC"})


class LiveOverlayTestCase(unittest.TestCase):
    """The tape moves between rebuilds from one quotes call."""

    def _row(self, **kw):
        row = {"symbol": "^NSEI", "status": mi.STATUS_OK, "group": "broad",
               "last": 100.0, "high_52w": 120.0, "low_52w": 80.0,
               "off_high_pct": 16.67, "above_low_pct": 25.0}
        row.update(kw)
        return row

    def _nifty(self, last, prev=99.0):
        return {mi.KITE_INDEX["^NSEI"]: {"last_price": last,
                                         "ohlc": {"close": prev}}}

    def test_live_level_and_distances_follow_the_quote(self):
        rows, touched = mi.refresh_live_rows([self._row()], self._nifty(108.0))
        self.assertEqual(touched, 1)
        self.assertEqual(rows[0]["last"], 108.0)
        self.assertEqual(rows[0]["day_chg_pct"], round(9 / 99 * 100, 2))
        self.assertEqual(rows[0]["off_high_pct"], 10.0)
        self.assertEqual(rows[0]["above_low_pct"], 35.0)

    def test_a_print_beyond_the_high_moves_the_high(self):
        rows, _ = mi.refresh_live_rows([self._row()], self._nifty(130.0))
        self.assertEqual(rows[0]["high_52w"], 130.0)
        self.assertEqual(rows[0]["off_high_pct"], 0.0)

    def test_the_cached_rows_are_not_mutated(self):
        original = [self._row()]
        mi.refresh_live_rows(original, self._nifty(108.0))
        self.assertEqual(original[0]["last"], 100.0)

    def test_no_range_means_no_invented_distance(self):
        rows, _ = mi.refresh_live_rows(
            [self._row(high_52w=None, low_52w=None, off_high_pct=None,
                       above_low_pct=None)], self._nifty(108.0))
        self.assertIsNone(rows[0]["off_high_pct"])

    def test_no_quotes_changes_nothing(self):
        rows, touched = mi.refresh_live_rows([self._row()], {})
        self.assertEqual(touched, 0)
        self.assertEqual(rows[0]["last"], 100.0)


class MarketHoursTestCase(unittest.TestCase):
    def _at(self, y, m, d, hh, mm):
        from datetime import datetime
        return datetime(y, m, d, hh, mm, tzinfo=mi.IST)

    def test_session_bounds(self):
        # 2026-09-29 is a Tuesday.
        self.assertFalse(mi.is_market_open(self._at(2026, 9, 29, 9, 14)))
        self.assertTrue(mi.is_market_open(self._at(2026, 9, 29, 9, 15)))
        self.assertTrue(mi.is_market_open(self._at(2026, 9, 29, 15, 29)))
        self.assertFalse(mi.is_market_open(self._at(2026, 9, 29, 15, 30)))

    def test_weekends_are_closed(self):
        self.assertFalse(mi.is_market_open(self._at(2026, 10, 3, 11, 0)))

    def test_other_timezones_are_converted(self):
        from datetime import datetime, timezone
        # 04:00 UTC is 09:30 IST.
        self.assertTrue(mi.is_market_open(
            datetime(2026, 9, 29, 4, 0, tzinfo=timezone.utc)))


if __name__ == "__main__":
    unittest.main()
