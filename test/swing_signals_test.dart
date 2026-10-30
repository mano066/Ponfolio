import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/presentation/screens/swing_signals.dart';

/// A strong bullish breakout setup (entry above current price → WATCH).
Map<String, dynamic> _breakout() => {
      'symbol': 'RELIANCE.NS',
      'name': 'RELIANCE',
      'price': 2480.0,
      'score': 82,
      'setup': 'Volume Breakout',
      'rsi': 58.0,
      'stoch_rsi': 45.0,
      'macd_hist': 3.2,
      'macd_signal': 'Bullish',
      'atr': 30.0,
      'volume_ratio': 1.8,
      'volume_spike': true,
      'pattern': 'Bullish Engulfing',
      'bb_position': 'Upper',
      'ema20': 2450.0,
      'ema50': 2400.0,
      'adx': 28.0,
      'trend': 'Up',
      'supports': [2400.0, 2350.0],
      'resistances': [2520.0, 2560.0],
      'entry': 2485.0,
      'stop_loss': 2440.0,
      'target1': 2545.0,
      'target2': 2575.0,
      'risk_reward': '1:2.0',
      'risk_pct': 1.8,
      'reward_pct': 2.4,
      'data_source': 'Kite MCP',
    };

/// A weak downtrend setup that should be avoided.
Map<String, dynamic> _weak() => {
      'symbol': 'XYZ.NS',
      'name': 'XYZ',
      'price': 500.0,
      'score': 52,
      'setup': 'Trend Continuation',
      'rsi': 72.0,
      'stoch_rsi': 85.0,
      'macd_hist': -2.0,
      'macd_signal': 'Bearish',
      'atr': 12.0,
      'volume_ratio': 0.7,
      'volume_spike': false,
      'pattern': 'Bearish Engulfing',
      'bb_position': 'Middle',
      'ema20': 510.0,
      'ema50': 525.0,
      'adx': 14.0,
      'trend': 'Down',
      'supports': [],
      'resistances': [520.0, 540.0],
      'entry': null,
      'stop_loss': 485.0,
      'target1': 520.0,
      'target2': 535.0,
      'risk_reward': '1:0.8',
      'risk_pct': 3.0,
      'reward_pct': 4.0,
      'data_source': 'Kite MCP',
    };

void main() {
  group('parseRR', () {
    test('parses "1:2.0" strings', () {
      expect(SwingSignals.parseRR('1:2.0'), 2.0);
      expect(SwingSignals.parseRR('1:3.5'), 3.5);
    });
    test('accepts numbers and rejects junk', () {
      expect(SwingSignals.parseRR(2.5), 2.5);
      expect(SwingSignals.parseRR(null), isNull);
      expect(SwingSignals.parseRR('n/a'), isNull);
    });
  });

  group('score buckets', () {
    test('bucket + confidence bands', () {
      expect(SwingSignals.bucketFor(85), 'Strong Setup');
      expect(SwingSignals.bucketFor(70), 'Good Setup');
      expect(SwingSignals.bucketFor(55), 'Watchlist');
      expect(SwingSignals.bucketFor(30), 'Avoid');
      expect(SwingSignals.confidenceFor(90), 'High');
      expect(SwingSignals.confidenceFor(66), 'Medium');
      expect(SwingSignals.confidenceFor(40), 'Low');
    });
  });

  group('breakout setup', () {
    final sig = SwingSignals.of(_breakout());

    test('is a WATCH (price still below the break trigger)', () {
      expect(sig.plan.action, SwingAction.watch);
      expect(sig.score, 82);
      expect(sig.scoreBucket, 'Strong Setup');
      expect(sig.confidence, 'High');
    });

    test('buy zone starts at the trigger and reason says "buy above"', () {
      expect(sig.plan.buyLow, 2485.0);
      expect(sig.plan.buyHigh! > sig.plan.buyLow!, true);
      expect(sig.plan.reason.toLowerCase(), contains('buy'));
      expect(sig.plan.reason, contains('2485'));
    });

    test('risk/reward per share and position sizing on 1% capital', () {
      expect(sig.plan.riskPerShare, 45.0); // 2485 - 2440
      expect(sig.plan.rewardPerShare, 60.0); // 2545 - 2485
      // 1% of 10L = 10,000 / 45 = 222 shares (floored)
      expect(sig.plan.positionQty, 222);
      expect(sig.plan.invalidIf, contains('2440'));
    });

    test('component scores reward trend/volume/pattern', () {
      final byLabel = {for (final c in sig.components) c.label: c.score};
      expect(byLabel['Trend']! >= 80, true);
      expect(byLabel['Volume']! >= 80, true);
      expect(byLabel['Pattern']! >= 80, true);
      expect(byLabel['Risk:Reward'], 80);
    });

    test('continuation signals fire', () {
      expect(sig.fired(SignalKind.continuation) >= 3, true);
      final exit = sig.tagsByKind[SignalKind.exit];
      // exit rules are surfaced through the plan, not the tag map
      expect(exit, anyOf(isNull, isEmpty));
      expect(sig.plan.exitRules, isNotEmpty);
    });

    test('confidence override wins when provided', () {
      final s2 = SwingSignals.of(_breakout(), confidenceOverride: 'Low');
      expect(s2.confidence, 'Low');
    });
  });

  group('weak downtrend setup', () {
    final sig = SwingSignals.of(_weak());
    test('is AVOID with an explanatory reason', () {
      expect(sig.plan.action, SwingAction.avoid);
      expect(sig.plan.reason.toLowerCase(), contains('avoid'));
    });
    test('avoid conditions fire and buy zone is suppressed', () {
      expect(sig.fired(SignalKind.avoid) >= 3, true);
    });
    test('null entry falls back to LTP and is flagged derived', () {
      expect(sig.plan.entryDerived, true);
      expect(sig.plan.entry, 500.0);
    });
  });

  // ── 14-Day Swing Desk (AI-selected, user-executed) ──
  // Fixed dates: 2026-07-08 is a Wednesday.
  final today = DateTime(2026, 7, 8);

  /// A tracked desk record (backend swing_desk.json shape), selected yesterday.
  Map<String, dynamic> rec_({Map<String, dynamic> over = const {}}) => {
        'symbol': 'GOOD.NS',
        'name': 'GOOD',
        'selected_date': '2026-07-07', // Tuesday → 1 trading day
        'scan_date': '2026-07-07',
        'day_batch_label': '2026-07-07 Picks',
        'original_price': 99.0,
        'original_score': 78,
        'original_grade': 'A',
        'original_setup_type': 'Breakout',
        'original_entry': 100.0,
        'original_stop_loss': 96.0,
        'original_target1': 108.0,
        'original_target2': 112.0,
        'buy_zone_low': 99.0,
        'buy_zone_high': 101.0,
        'tracking_status': 'WAIT',
        'entered': false,
        'trigger_hit': false,
        'auto_selected': true,
        ...over,
      };

  /// Today's re-analysis snapshot for that stock.
  Map<String, dynamic> snap_({Map<String, dynamic> over = const {}}) => {
        'symbol': 'GOOD.NS',
        'price': 98.5, // below the 99–101 buy zone → still waiting
        'current_price': 98.5,
        'selection_score': 77,
        'grade': 'A',
        'setup_type': 'Breakout',
        'trend': 'Up',
        'ema20': 96.5,
        'ema50': 93.0,
        'volume_ratio': 1.4,
        'risk_reward_ratio': 2.2,
        'data_quality_score': 82,
        ...over,
      };

  group('desk — trading days', () {
    test('same day 0, Friday→Monday 1, one week 5', () {
      expect(
          SwingDeskLogic.tradingDaysBetween(
              DateTime(2026, 7, 8), DateTime(2026, 7, 8)),
          0);
      expect(
          SwingDeskLogic.tradingDaysBetween(
              DateTime(2026, 7, 3), DateTime(2026, 7, 6)),
          1);
      expect(
          SwingDeskLogic.tradingDaysBetween(
              DateTime(2026, 7, 1), DateTime(2026, 7, 8)),
          5);
    });

    test('days remaining counts down from 14', () {
      expect(SwingDeskLogic.daysRemaining('2026-07-07', today), 13);
      expect(SwingDeskLogic.daysRemaining('2026-06-18', today), 0);
    });
  });

  group('desk — classification / lifecycle', () {
    test('selected stock remains WAIT the next day (not removed)', () {
      expect(SwingDeskLogic.classifyTracked(rec_(), snap_(), today),
          DeskAction.wait);
      expect(SwingDeskLogic.daysRemaining('2026-07-07', today), 13);
    });

    test('BUY only when trigger conditions are met', () {
      // Below the buy zone → WAIT.
      expect(SwingDeskLogic.classifyTracked(rec_(), snap_(), today),
          DeskAction.wait);
      // Inside the buy zone with trend + volume + rr → BUY.
      expect(
          SwingDeskLogic.classifyTracked(rec_(),
              snap_(over: {'price': 100.2, 'current_price': 100.2}), today),
          DeskAction.buy);
      // In zone but volume fails the confirmation → back to WAIT.
      expect(
          SwingDeskLogic.classifyTracked(
              rec_(),
              snap_(over: {
                'price': 100.2,
                'current_price': 100.2,
                'volume_ratio': 0.6
              }),
              today),
          DeskAction.wait);
    });

    test('selected stock stays on the desk even when invalidated', () {
      // Day 9, still valid, below zone → WAIT (kept).
      expect(
          SwingDeskLogic.classifyTracked(
              rec_(over: {'selected_date': '2026-06-25'}), snap_(), today),
          DeskAction.wait);
      // Setup turns invalid (stop broken) → AVOID (kept on desk).
      expect(
          SwingDeskLogic.classifyTracked(rec_(),
              snap_(over: {'price': 95.0, 'current_price': 95.0}), today),
          DeskAction.avoid);
    });

    test('expired stock leaves the active desk after 14 trading days', () {
      // 2026-06-18 (Thu) → 2026-07-08 (Wed) = 14 trading days.
      expect(
          SwingDeskLogic.classifyTracked(
              rec_(over: {'selected_date': '2026-06-18'}), snap_(), today),
          DeskAction.expired);
    });

    test('entered trade HOLDs, then EXITs on stop', () {
      expect(
          SwingDeskLogic.classifyTracked(rec_(over: {'entered': true}),
              snap_(over: {'price': 104.0, 'current_price': 104.0}), today),
          DeskAction.hold);
      expect(
          SwingDeskLogic.classifyTracked(rec_(over: {'entered': true}),
              snap_(over: {'price': 95.5, 'current_price': 95.5}), today),
          DeskAction.exit);
    });

    test('entered trade EXITs when the thesis collapses (no stop hit yet)',
        () {
      // Price still well above the stop and above the EMAs, but the score
      // has cratered since selection — should EXIT rather than HOLD.
      expect(
          SwingDeskLogic.classifyTracked(
              rec_(over: {'entered': true, 'original_score': 78}),
              snap_(over: {
                'price': 104.0,
                'current_price': 104.0,
                'selection_score': 50, // 78 -> 50, drop of 28 >= scoreDropRemove (20)
              }),
              today),
          DeskAction.exit);
      // Same price/trend, but grade flips to Avoid — should also EXIT.
      expect(
          SwingDeskLogic.classifyTracked(
              rec_(over: {'entered': true}),
              snap_(over: {
                'price': 104.0,
                'current_price': 104.0,
                'grade': 'Avoid',
              }),
              today),
          DeskAction.exit);
      // Small score dip, healthy grade → still HOLD.
      expect(
          SwingDeskLogic.classifyTracked(
              rec_(over: {'entered': true, 'original_score': 78}),
              snap_(over: {
                'price': 104.0,
                'current_price': 104.0,
                'selection_score': 70, // drop of 8, below the 20-pt threshold
              }),
              today),
          DeskAction.hold);
    });

    test('late window (day 11+) needs strong confirmation for BUY', () {
      final late = rec_(over: {'selected_date': '2026-06-23'});
      expect(
          SwingDeskLogic.daysInTracking('2026-06-23', today) >= 11, true);
      // In zone but only baseline confirmation → WAIT.
      expect(
          SwingDeskLogic.classifyTracked(
              late,
              snap_(over: {
                'price': 100.2,
                'current_price': 100.2,
                'volume_ratio': 1.0,
                'risk_reward_ratio': 1.5
              }),
              today),
          DeskAction.wait);
      // Strong confirmation → BUY.
      expect(
          SwingDeskLogic.classifyTracked(
              late,
              snap_(over: {
                'price': 100.2,
                'current_price': 100.2,
                'volume_ratio': 1.3,
                'risk_reward_ratio': 2.2,
                'grade': 'A'
              }),
              today),
          DeskAction.buy);
    });

    test('setup status follows score drift', () {
      expect(
          SwingDeskLogic.setupStatusFor(originalScore: 78, currentScore: 85),
          SetupStatus.improved);
      expect(
          SwingDeskLogic.setupStatusFor(originalScore: 78, currentScore: 68),
          SetupStatus.weakened);
      expect(
          SwingDeskLogic.setupStatusFor(originalScore: 78, currentScore: 77),
          SetupStatus.same);
      expect(
          SwingDeskLogic.setupStatusFor(
              originalScore: 78, currentScore: 77, invalid: true),
          SetupStatus.invalid);
    });

    test('readyConditionsMet caps "triggered" at max_entry_price — a gap far '
        'past the entry must not count as a valid trigger forever', () {
      final gapped = rec_(over: {'max_entry_price': 104.0});
      // Price gapped from entry 100 all the way to 200 — must NOT be ready.
      expect(
          SwingDeskLogic.readyConditionsMet(
              gapped, snap_(over: {'price': 200.0, 'current_price': 200.0}), 1),
          false);
      // A price genuinely back inside the buy zone still triggers normally.
      expect(
          SwingDeskLogic.readyConditionsMet(
              gapped, snap_(over: {'price': 100.0, 'current_price': 100.0}), 1),
          true);
    });
  });

  group('desk — grouping by selected date', () {
    test('stocks group by batch, newest date first', () {
      final grouped = SwingDeskLogic.groupBySelectedDate([
        rec_(over: {
          'symbol': 'A.NS',
          'selected_date': '2026-07-08',
          'day_batch_label': '2026-07-08 Picks'
        }),
        rec_(over: {
          'symbol': 'B.NS',
          'selected_date': '2026-07-08',
          'day_batch_label': '2026-07-08 Picks'
        }),
        rec_(over: {
          'symbol': 'C.NS',
          'selected_date': '2026-07-07',
          'day_batch_label': '2026-07-07 Picks'
        }),
      ]);
      expect(grouped.map((g) => g['batch_label']).toList(),
          ['2026-07-08 Picks', '2026-07-07 Picks']);
      expect((grouped.first['stocks'] as List).length, 2);
    });
  });

  group('desk — top focus shortlist', () {
    Map<String, dynamic> pick_(String sym, String status, int score,
            {String setup = 'same',
            bool entered = false,
            String rr = '1:1.3',
            int daysLeft = 10}) =>
        {
          'symbol': sym,
          'tracking_status': status,
          'setup_status': setup,
          'entered': entered,
          'current_score': score,
          'original_score': score,
          'risk_reward': rr,
          'days_remaining': daysLeft,
        };

    test('keeps only fresh-entry candidates (BUY/WAIT, valid, not entered)',
        () {
      final top = SwingDeskLogic.topFocus([
        pick_('BUY1.NS', 'BUY', 80),
        pick_('WAIT1.NS', 'WAIT', 95),
        pick_('AVOID1.NS', 'AVOID', 99),
        pick_('EXPIRED1.NS', 'EXPIRED', 99),
        pick_('INVALID1.NS', 'WAIT', 99, setup: 'invalid'),
        pick_('HELD1.NS', 'HOLD', 99, entered: true),
        pick_('ENTERED1.NS', 'BUY', 99, entered: true),
      ]);
      expect(top.map((s) => s['symbol']).toList(), ['BUY1.NS', 'WAIT1.NS']);
    });

    test('BUY outranks higher-scored WAIT; then score; capped at 5', () {
      final top = SwingDeskLogic.topFocus([
        pick_('W99.NS', 'WAIT', 99),
        pick_('B70.NS', 'BUY', 70),
        pick_('W97.NS', 'WAIT', 97),
        pick_('W96.NS', 'WAIT', 96),
        pick_('W95.NS', 'WAIT', 95),
        pick_('W94.NS', 'WAIT', 94),
        pick_('W93.NS', 'WAIT', 93),
      ]);
      expect(top.length, 5);
      expect(top.first['symbol'], 'B70.NS');
      expect(top.map((s) => s['symbol']).toList(),
          ['B70.NS', 'W99.NS', 'W97.NS', 'W96.NS', 'W95.NS']);
    });

    test('score ties break on setup drift, then R:R', () {
      final top = SwingDeskLogic.topFocus([
        pick_('SAME.NS', 'WAIT', 90, setup: 'same'),
        pick_('IMP.NS', 'WAIT', 90, setup: 'improved'),
        pick_('WEAK.NS', 'WAIT', 90, setup: 'weakened'),
        pick_('SAMEHIRR.NS', 'WAIT', 90, setup: 'same', rr: '1:2.5'),
      ]);
      expect(top.map((s) => s['symbol']).toList(),
          ['IMP.NS', 'SAMEHIRR.NS', 'SAME.NS', 'WEAK.NS']);
    });

    test('duplicate symbols keep the first (newest-batch) instance', () {
      final top = SwingDeskLogic.topFocus([
        pick_('DUP.NS', 'WAIT', 88, daysLeft: 13),
        pick_('DUP.NS', 'WAIT', 91, daysLeft: 5),
      ]);
      expect(top.length, 1);
      expect(top.first['days_remaining'], 13);
    });
  });

  group('desk — Focus Dashboard (sorted by actual profit)', () {
    Map<String, dynamic> tracked_(String sym, String status,
            {double? priceChangePct, int daysLeft = 10}) =>
        {
          'symbol': sym,
          'tracking_status': status,
          'price_change_pct': priceChangePct,
          'days_remaining': daysLeft,
        };

    test('sorts every active status by actual profit %, highest first', () {
      final dash = SwingDeskLogic.focusDashboard([
        tracked_('WAIT1.NS', 'WAIT', priceChangePct: 1.0),
        tracked_('HOLD1.NS', 'HOLD', priceChangePct: 9.0),
        tracked_('AVOID1.NS', 'AVOID', priceChangePct: -4.0),
        tracked_('EXIT1.NS', 'EXIT', priceChangePct: -1.0),
        tracked_('BUY1.NS', 'BUY', priceChangePct: 5.0),
      ]);
      expect(dash.map((s) => s['symbol']).toList(),
          ['HOLD1.NS', 'BUY1.NS', 'WAIT1.NS', 'EXIT1.NS', 'AVOID1.NS']);
    });

    test('expired stocks are excluded (retired to history server-side)', () {
      final dash = SwingDeskLogic.focusDashboard([
        tracked_('LIVE.NS', 'WAIT', priceChangePct: 2.0),
        tracked_('GONE.NS', 'EXPIRED', priceChangePct: 50.0),
      ]);
      expect(dash.map((s) => s['symbol']).toList(), ['LIVE.NS']);
    });

    test('stocks with no price yet sort last, not as zero', () {
      final dash = SwingDeskLogic.focusDashboard([
        tracked_('NOPRICE.NS', 'WAIT', priceChangePct: null),
        tracked_('LOSER.NS', 'WAIT', priceChangePct: -8.0),
      ]);
      expect(dash.map((s) => s['symbol']).toList(),
          ['LOSER.NS', 'NOPRICE.NS']);
    });

    test('duplicate symbols keep the first (newest-batch) instance', () {
      final dash = SwingDeskLogic.focusDashboard([
        tracked_('DUP.NS', 'WAIT', priceChangePct: 3.0, daysLeft: 13),
        tracked_('DUP.NS', 'WAIT', priceChangePct: 3.0, daysLeft: 5),
      ]);
      expect(dash.length, 1);
      expect(dash.first['days_remaining'], 13);
    });

    test('focusDashboardWithHistory merges active + completed, sorted together',
        () {
      final merged = SwingDeskLogic.focusDashboardWithHistory(
        [
          tracked_('ACTIVE_WIN.NS', 'HOLD', priceChangePct: 4.0),
          tracked_('ACTIVE_LOSS.NS', 'WAIT', priceChangePct: -2.0),
        ],
        [
          {
            'symbol': 'DONE_WIN.NS',
            'final_price': 112.0,
            'actual_profit_pct': 12.0,
          },
          {
            'symbol': 'DONE_LOSS.NS',
            'final_price': 90.0,
            'actual_profit_pct': -10.0,
          },
          // No actual_profit_pct (e.g. a bare manual-removal stub) — skipped.
          {'symbol': 'STUB_ONLY.NS', 'removal_reason': 'Archived by user'},
        ],
      );
      expect(merged.map((s) => s['symbol']).toList(), [
        'DONE_WIN.NS',
        'ACTIVE_WIN.NS',
        'ACTIVE_LOSS.NS',
        'DONE_LOSS.NS',
      ]);
      final done = merged.firstWhere((s) => s['symbol'] == 'DONE_WIN.NS');
      expect(done['completed'], true);
      expect(done['tracking_status'], 'EXPIRED');
      expect(done['tracking_day'], 14);
      final active = merged.firstWhere((s) => s['symbol'] == 'ACTIVE_WIN.NS');
      expect(active['completed'], false);
    });
  });

  group('desk — wire parsing', () {
    test('action enum round-trips the wire format', () {
      for (final a in DeskAction.values) {
        expect(deskActionFrom(a.wire), a);
      }
      expect(deskActionFrom('garbage'), DeskAction.wait);
      expect(deskActionFrom(null), DeskAction.wait);
    });

    test('setup status parses with a safe default', () {
      expect(setupStatusFrom('improved'), SetupStatus.improved);
      expect(setupStatusFrom('weakened'), SetupStatus.weakened);
      expect(setupStatusFrom('invalid'), SetupStatus.invalid);
      expect(setupStatusFrom(null), SetupStatus.same);
    });
  });

  // ── Signal freshness — actionable_status (wire: backend validate_recommendation) ──
  group('actionable status — wire parsing', () {
    test('every wire value round-trips to its enum', () {
      const wire = {
        'READY_TO_BUY': ActionableStatus.readyToBuy,
        'WAIT_FOR_ENTRY': ActionableStatus.waitForEntry,
        'NEAR_BUY_ZONE': ActionableStatus.nearBuyZone,
        'MISSED_ENTRY': ActionableStatus.missedEntry,
        'TARGET_ALREADY_REACHED': ActionableStatus.targetAlreadyReached,
        'INVALID': ActionableStatus.invalid,
        'PENDING_ENTRY': ActionableStatus.pendingEntry,
        'DATA_STALE': ActionableStatus.dataStale,
      };
      wire.forEach((w, expected) {
        expect(actionableStatusFrom(w), expected, reason: w);
      });
    });

    test('unknown/null defaults to WAIT_FOR_ENTRY rather than looking actionable', () {
      expect(actionableStatusFrom('garbage'), ActionableStatus.waitForEntry);
      expect(actionableStatusFrom(null), ActionableStatus.waitForEntry);
    });

    test('only READY_TO_BUY and NEAR_BUY_ZONE are fresh buy opportunities', () {
      for (final s in ActionableStatus.values) {
        final expected =
            s == ActionableStatus.readyToBuy || s == ActionableStatus.nearBuyZone;
        expect(isFreshBuyOpportunity(s), expected, reason: s.name);
        expect(s.isActionableBuy, expected, reason: s.name);
      }
    });

    test('labels never say "BUY" once price is past the entry limit', () {
      expect(ActionableStatus.missedEntry.label, isNot(contains('BUY')));
      expect(ActionableStatus.missedEntry.label.toLowerCase(), contains('missed'));
      expect(ActionableStatus.waitForEntry.label.toLowerCase(), contains('wait'));
      expect(ActionableStatus.readyToBuy.label.toLowerCase(), contains('ready'));
      expect(ActionableStatus.targetAlreadyReached.label.toLowerCase(),
          contains('already reached'));
      expect(ActionableStatus.pendingEntry.label.toLowerCase(), contains('pending'));
    });
  });

  group('fill label formatting', () {
    test('formats "Filled at ₹X on DATE TIME" from the backend timestamp shape', () {
      expect(formatFillLabel(101.5, '2026-07-23 10:32'),
          'Filled at ₹101.50 on 2026-07-23 10:32');
    });

    test('falls back to just the price when no fill timestamp is available', () {
      expect(formatFillLabel(101.5, null), 'Filled at ₹101.50');
      expect(formatFillLabel(101.5, ''), 'Filled at ₹101.50');
    });
  });
}
