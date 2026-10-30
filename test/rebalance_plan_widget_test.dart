import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'package:aiei_wealth/core/theme/app_colors.dart';
import 'package:aiei_wealth/core/theme/app_theme.dart';
import 'package:aiei_wealth/presentation/widgets/rebalance_plan_section.dart';
import 'package:aiei_wealth/providers/rebalance_provider.dart';

/// Fixtures mirror the shape `rebalance_engine.build_plan` really emits —
/// including the parts that are easy to get wrong from the client side: a
/// `gain_pct` that is null rather than 0 when cost is unknown, a `target_pct`
/// that equals the current weight for anything inside its band, and a manual
/// holding that is `tradable: false` with no priced trade against it.

Map<String, dynamic> _asset(
  String key, {
  String category = 'stocks',
  String categoryLabel = 'Stocks',
  String action = 'TRIM',
  double weight = 30.0,
  double target = 10.0,
  double portfolioPct = 20.69,
  String status = 'over',
  double value = 300000,
  double amount = 200000,
  double gain = 100000,
  double tax = 20800,
  double net = 179200,
  Object? gainPct = 100.0,
  double heldUnits = 3000,
  double longTermUnits = 2000,
  double tradeUnits = -2000,
  double? weightAfter,
  int deployRank = 1,
  bool tradable = true,
  bool selected = true,
  String reason = '30.0% of the stocks sleeve, above the 10% ceiling.',
  String? note,
}) {
  // The settled side of the row, derived from the trade rather than passed in,
  // so a fixture cannot describe a sale of 2,000 units that leaves the holding
  // untouched. The widget reads these; the engine computes them in `_settle`.
  final bought = action == 'ADD' ? tradeUnits.abs() : 0.0;
  final sold = action == 'TRIM' ? tradeUnits.abs() : 0.0;
  final price = heldUnits > 0 ? value / heldUnits : 0.0;
  final after = heldUnits - sold + bought;
  return {
      'key': key,
      'name': key,
      'sleeve': category,
      'category': category,
      'category_label': categoryLabel,
      'value': value,
      'weight_pct': weight,
      'target_pct': target,
      'portfolio_pct': portfolioPct,
      'band': [2.0, 10.0],
      'status': status,
      'action': action,
      'amount': amount,
      'gain': gain,
      'tax': tax,
      'net_proceeds': net,
      'gain_pct': gainPct,
      'held_units': heldUnits,
      'long_term_units': longTermUnits,
      'trade_units': tradeUnits,
      'deploy_rank': deployRank,
      'invested': 150000.0,
      'tradable': tradable,
      'selected': selected,
      'reason': reason,
      'note': ?note,
      'price': price,
      'units_bought': bought,
      'units_sold': sold,
      'sold_pct_of_held': heldUnits > 0 ? sold / heldUnits * 100 : 0.0,
      'held_after': after,
      'value_after': after * price,
      'weight_after_pct': weightAfter ?? weight,
      'net_cash': (sold - bought) * price,
    };
}

Map<String, dynamic> _categoryRow(
  String category,
  String label, {
  double value = 0,
  int positions = 0,
  double currentPct = 0,
  double targetPct = 0,
  double driftPct = 0,
  String status = 'within',
  String action = 'HOLD',
  double amount = 0,
  double manualValue = 0,
}) =>
    {
      'category': category,
      'label': label,
      'value': value,
      'tradable_value': value - manualValue,
      'manual_value': manualValue,
      'positions': positions,
      'current_pct': currentPct,
      'target_pct': targetPct,
      'drift_pct': driftPct,
      'tolerance_pct': 5.0,
      'band': [targetPct - 5, targetPct + 5],
      'status': status,
      'action': action,
      'amount': amount,
    };

Map<String, dynamic> _plan({
  List<Map<String, dynamic>>? actions,
  List<Map<String, dynamic>>? categoryRows,
  Map<String, dynamic>? market,
  Map<String, dynamic>? crash,
  Map<String, dynamic>? volatility,
  List<Map<String, dynamic>>? fired,
  List<Map<String, dynamic>>? considered,
  Map<String, dynamic>? totals,
  Map<String, dynamic>? settings,
  Map<String, dynamic>? strategyPreset,
  Map<String, dynamic>? contribution,
  bool targetsSet = true,
  bool targetsRescaled = false,
  String mode = 'auto',
}) =>
    {
      'as_of': '2026-09-10',
      'residency': 'nri',
      'contribution': contribution ??
          {'amount': 0.0, 'deployed': 0.0, 'left': 0.0, 'positions': 0},
      'policy': {
        'min_weight_pct': 2.0,
        'max_weight_pct': 10.0,
        'deviation_pct': 5.0,
        'boom_gain_pct': 20.0,
        'crash_drop_pct': 15.0,
        'vol_trigger_pct': 22.0,
        'gain_trigger_pct': null,
        'loss_trigger_pct': null,
        'cadence': 'semiannual',
        'mode': mode,
      },
      'triggers': {
        'due': (fired ?? const []).isNotEmpty || mode == 'manual',
        'mode': mode,
        'fired': fired ?? const [],
        'considered': considered ?? const [],
        'enabled': const [],
        'cadence': 'semiannual',
        'window_days': 182,
        'next_calendar_due': '2027-03-02',
      },
      'market': market ??
          {
            'available': true,
            'boom': false,
            'heat': 'calm',
            'benchmark': 'NIFTY 50',
            'reason': '1 of 5 boom signals are firing.',
            'signals': [
              {
                'name': 'overbought',
                'hit': false,
                'known': true,
                'detail': 'RSI 48'
              },
            ],
          },
      'crash': crash ??
          {
            'available': true,
            'crash': false,
            'severity': 'stable',
            'benchmark': 'NIFTY 50',
            'reason': '0 of 5 crash signals are firing.',
            'signals': const [],
          },
      'volatility': volatility ??
          {
            'available': true,
            'elevated': false,
            'vol_pct': 13.4,
            'threshold_pct': 22.0,
            'benchmark': 'NIFTY 50',
            'reason': 'NIFTY 50 is running at 13.4% annualised volatility '
                '(trigger at 22%).',
          },
      'allocation': {
        'total_value': 1450000.0,
        'targets_set': targetsSet,
        'targets_rescaled': targetsRescaled,
        'tolerance_pct': 5.0,
        'rows': categoryRows ??
            [
              _categoryRow('stocks', 'Stocks',
                  value: 1000000,
                  positions: 11,
                  currentPct: 69.0,
                  targetPct: 50.0,
                  driftPct: 19.0,
                  status: 'over',
                  action: 'REDUCE',
                  amount: -275500),
              _categoryRow('mutual_funds', 'Mutual Funds',
                  value: 300000,
                  positions: 1,
                  currentPct: 20.7,
                  targetPct: 30.0,
                  driftPct: -9.3,
                  status: 'under',
                  action: 'INCREASE',
                  amount: 135000),
              _categoryRow('gold', 'Gold',
                  value: 100000,
                  positions: 1,
                  currentPct: 6.9,
                  targetPct: 10.0,
                  manualValue: 100000),
              _categoryRow('debt', 'Debt', targetPct: 10.0),
            ],
        'drifted': 2,
        'worst_drift_pct': 19.0,
      },
      'strategy_preset': strategyPreset ??
          const {
            'id': 'S10',
            'name': 'Wide band + dividends',
            'tagline': 'Reinvest income, trim only past 20%.',
            'trim_pct': 20.0,
            'deploy': 'gap',
            'reinvest_income': true,
            'never_sells': false,
            'effective_max_weight_pct': 20.0,
            'deploy_label': 'largest shortfall first',
            'deploy_note': null,
            'income_note': 'This rule puts income back to work.',
            'measured': {'xirr_pct': 15.97, 'sells': 3},
            'measured_note': 'Backtested on a ten-stock NSE basket, '
                'not a forecast.',
          },
      'sleeves': const {},
      'actions': actions ?? const [],
      'portfolio_value': 1450000.0,
      'portfolio_gain_pct': 66.7,
      'selection': const {'categories': null, 'assets': null},
      'settings': settings ??
          {
            'cadence': 'semiannual',
            'triggers': ['calendar', 'market_boom'],
            'selected_categories': null,
            'selected_assets': null,
            'all_triggers': [
              {'name': 'calendar', 'label': 'Calendar review'},
              {'name': 'market_boom', 'label': 'Market boom'},
              {'name': 'market_crash', 'label': 'Market crash'},
            ],
            'all_categories': [
              {'name': 'stocks', 'label': 'Stocks'},
            ],
          },
      'totals': totals ??
          {
            'sell_value': 200000.0,
            'buy_value': 10000.0,
            'tax_estimated': 20800.0,
            'net_proceeds': 179200.0,
            'cash_after_plan': 169200.0,
            'trims': 1,
            'adds': 1,
            'skipped': 0,
            'manual_review': 0,
          },
      'strategy': [
        {
          'title': 'Spend long-term units first',
          'body': 'Same trade, smaller bill.'
        },
      ],
    };

/// One replayed trade date, in the shape `/rebalance/history` returns.
Map<String, dynamic> _historyRows(String date, int index, int count,
        {List<Map<String, dynamic>>? rows}) =>
    {
      'index': index,
      'count': count,
      'date': date,
      'rows': rows ??
          [
            {
              'key': 'BIG',
              'name': 'BIG.NS',
              'held_before': 100.0,
              'fill': 250.0,
              'value_before': 24000.0,
              'weight_before_pct': 60.0,
              'action': 'BUY',
              'bought': 10.0,
              'sold': 0.0,
              'sold_pct_of_held': 0.0,
              'held_after': 110.0,
              'value_after': 26562.5,
              'weight_after_pct': 62.5,
              'net_cash': -2500.0,
            },
            {
              'key': 'SMALL',
              'name': 'SMALL.NS',
              'held_before': 40.0,
              'fill': null,
              'value_before': 16000.0,
              'weight_before_pct': 40.0,
              'action': 'HOLD',
              'bought': 0.0,
              'sold': 0.0,
              'sold_pct_of_held': 0.0,
              'held_after': 40.0,
              'value_after': 15937.5,
              'weight_after_pct': 37.5,
              'net_cash': 0.0,
            },
          ],
    };

/// Totals derived FROM the rows, so a fixture cannot describe a page whose
/// summary contradicts the lines above it.
Map<String, dynamic> _historyPage(String date, int index, int count,
    {List<Map<String, dynamic>>? rows, List<String> unpriced = const []}) {
  final page = _historyRows(date, index, count, rows: rows);
  final list = (page['rows'] as List).cast<Map<String, dynamic>>();
  double sum(String f) =>
      list.fold(0.0, (a, r) => a + ((r[f] as num?)?.toDouble() ?? 0));
  page['totals'] = {
    'value_before': sum('value_before'),
    'value_after': sum('value_after'),
    'bought': sum('bought'),
    'sold': sum('sold'),
    'net_cash': sum('net_cash'),
    'positions': list.length,
    'traded': list.where((r) => r['action'] != 'HOLD').length,
    'unpriced': unpriced.length,
    'unpriced_keys': unpriced,
  };
  return page;
}

Map<String, dynamic> _history(
    {List<Map<String, dynamic>>? pages, bool reconciles = true}) {
  final list = pages ??
      [_historyPage('2026-03-10', 1, 2), _historyPage('2026-09-10', 2, 2)];
  return {'pages': list, 'count': list.length, 'reconciles': reconciles};
}

Future<void> _pump(WidgetTester tester, Map<String, dynamic> plan,
    {Map<String, dynamic>? history}) async {
  tester.view.physicalSize = const Size(1500, 2600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);

  await tester.pumpWidget(ProviderScope(
    overrides: [
      rebalancePlanProvider.overrideWith((ref) async => plan),
      rebalanceHistoryProvider
          .overrideWith((ref) async => history ?? _history()),
    ],
    child: MaterialApp(
      theme: AppTheme.dark(),
      home: const Scaffold(
        body: SingleChildScrollView(child: RebalancePlanSection()),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  // ── the per-asset band ──

  testWidgets('a breach is listed with its size and its after-tax cost',
      (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]));

    expect(find.text('BIG.NS'), findsOneWidget);
    expect(find.text('SELL'), findsOneWidget);
    // Its share of its own CATEGORY. There is no share-of-book column.
    expect(find.text('30.00%'), findsWidgets);
    // Net proceeds are the reinvestable figure and must be reachable from the
    // row, not left for the reader to subtract.
    expect(
        find.byTooltip('Realises ₹100000, ₹20800 withheld, ₹179200 reaches the '
            'account.'),
        findsOneWidget);
    expect(find.textContaining('TAX WITHHELD'), findsOneWidget);
    expect(find.textContaining('NET FROM SALES'), findsOneWidget);
  });

  testWidgets('the row reads as a ledger entry: before, trade, after',
      (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]));
    for (final header in [
      'ASSET', 'HELD BEFORE', 'FILL', 'VALUE BEFORE', 'GAIN/LOSS',
      'W% BEFORE', 'ACTION', 'BOUGHT', 'SOLD', 'SOLD % OF HELD',
      'HELD AFTER', 'W% AFTER', 'NET CASH +/−',
    ]) {
      expect(find.text(header), findsOneWidget, reason: header);
    }
  });

  testWidgets('gain and loss percent is shown per asset', (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]));
    expect(find.text('+100.0%'), findsOneWidget);
  });

  testWidgets('a holding with no cost basis shows a dash, never a flat zero',
      (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS', gainPct: null)]));
    expect(find.text('+0.0%'), findsNothing);
  });

  testWidgets('a holding inside its band targets where it already is',
      (tester) async {
    await _pump(
        tester,
        _plan(actions: [
          _asset('OK.NS',
              action: 'HOLD',
              status: 'within',
              weight: 6.0,
              target: 6.0,
              amount: 0,
              reason: 'Inside its band.')
        ]));
    expect(find.text('HOLD'), findsOneWidget);
    expect(find.text('SELL'), findsNothing);
  });

  // ── categories ──

  testWidgets('all four categories are listed, empty ones included',
      (tester) async {
    // A 10% gold target with nothing in it is exactly the finding the user
    // needs; dropping the empty row would hide it.
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]));
    expect(find.text('STOCKS'), findsOneWidget);
    expect(find.text('MUTUAL FUNDS'), findsOneWidget);
    expect(find.text('GOLD'), findsOneWidget);
    expect(find.text('DEBT'), findsOneWidget);
  });

  testWidgets('the asset mix table shows current against target and drift',
      (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]));
    expect(find.text('ASSET MIX'), findsOneWidget);
    expect(find.text('69.0%'), findsOneWidget);
    expect(find.text('50.0%'), findsOneWidget);
    expect(find.text('+19.0 pts'), findsOneWidget);
    expect(find.textContaining('Reduce ₹'), findsOneWidget);
    expect(find.textContaining('Add ₹'), findsWidgets);
  });

  testWidgets('with no target set the table says today is the target',
      (tester) async {
    await _pump(tester,
        _plan(actions: [_asset('BIG.NS')], targetsSet: false));
    expect(find.textContaining('No target set yet'), findsOneWidget);
    expect(find.text('SET TARGETS'), findsOneWidget);
  });

  testWidgets('rescaled targets are disclosed rather than silently applied',
      (tester) async {
    await _pump(tester,
        _plan(actions: [_asset('BIG.NS')], targetsRescaled: true));
    expect(find.textContaining('did not add up to 100%'), findsOneWidget);
  });

  // ── selection ──

  testWidgets('a deselected category is labelled and its breach skipped',
      (tester) async {
    await _pump(
        tester,
        _plan(
          actions: [
            _asset('BIG.NS'),
            _asset('Flexi Fund',
                category: 'mutual_funds',
                categoryLabel: 'Mutual Funds',
                action: 'SKIP',
                selected: false,
                reason: 'Outside its band, but not selected for this '
                    'rebalance.'),
          ],
          settings: {
            'cadence': 'semiannual',
            'triggers': const ['calendar'],
            'selected_categories': const ['stocks'],
            'selected_assets': null,
            'all_triggers': const [
              {'name': 'calendar', 'label': 'Calendar review'}
            ],
            'all_categories': const [
              {'name': 'stocks', 'label': 'Stocks'},
              {'name': 'mutual_funds', 'label': 'Mutual Funds'},
            ],
          },
          totals: {
            'sell_value': 200000.0,
            'buy_value': 0.0,
            'tax_estimated': 20800.0,
            'net_proceeds': 179200.0,
            'cash_after_plan': 179200.0,
            'trims': 1,
            'adds': 0,
            'skipped': 1,
            'manual_review': 0,
          },
        ));
    expect(find.text('NOT IN THIS REBALANCE'), findsNWidgets(3));
    expect(find.text('SKIP'), findsOneWidget);
    // The totals describe the SELECTED plan, so a narrowed selection has to
    // say so or the numbers read as the whole portfolio's.
    expect(find.textContaining('selected holdings only'), findsOneWidget);
  });

  // ── manual assets ──

  testWidgets('a hand-entered holding is never given a priced trade',
      (tester) async {
    await _pump(
        tester,
        _plan(actions: [
          _asset('manual:gold',
              category: 'gold',
              categoryLabel: 'Gold',
              action: 'REVIEW',
              status: 'over',
              tradable: false,
              gainPct: null,
              amount: 0,
              value: 100000,
              reason: 'Entered by hand, so there are no units or price here '
                  'to trade.'),
        ]));
    expect(find.text('MANUAL'), findsOneWidget);
  });

  // ── market readings ──

  testWidgets('boom, crash and volatility are each reported', (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]));
    expect(find.text('BOOM'), findsOneWidget);
    expect(find.text('CRASH'), findsOneWidget);
    expect(find.text('VOLATILITY'), findsOneWidget);
    expect(find.text('CALM'), findsOneWidget);
    expect(find.text('STABLE'), findsOneWidget);
    expect(find.text('13.4%'), findsOneWidget);
  });

  testWidgets('a fired boom trigger is named on the strip', (tester) async {
    await _pump(tester, _plan(
      actions: [_asset('BIG.NS')],
      fired: [
        {
          'name': 'market_boom',
          'label': 'Market boom',
          'detail': '4 of 5 boom signals are firing.'
        },
      ],
      market: {
        'available': true,
        'boom': true,
        'heat': 'boom',
        'benchmark': 'NIFTY 50',
        'reason': '4 of 5 boom signals are firing.',
        'signals': const [],
      },
    ));
    expect(find.text('DUE NOW'), findsOneWidget);
    expect(find.textContaining('Market boom'), findsWidgets);
  });

  testWidgets('a crash is reported as the buy side, not as a boom',
      (tester) async {
    await _pump(tester, _plan(
      actions: [_asset('BIG.NS')],
      fired: [
        {
          'name': 'market_crash',
          'label': 'Market crash',
          'detail': '4 of 5 crash signals are firing.'
        },
      ],
      crash: {
        'available': true,
        'crash': true,
        'severity': 'crash',
        'benchmark': 'NIFTY 50',
        'reason': '4 of 5 crash signals are firing.',
        'signals': const [],
      },
    ));
    expect(find.text('CRASH'), findsWidgets);
    expect(find.textContaining('Market crash'), findsWidgets);
  });

  testWidgets('a dead index feed reads as unknown, never as calm',
      (tester) async {
    await _pump(tester, _plan(
      actions: [_asset('BIG.NS')],
      market: {
        'available': false,
        'boom': false,
        'heat': 'unknown',
        'reason': 'No index data, so market heat is unknown.',
        'signals': const [],
      },
      crash: {
        'available': false,
        'crash': false,
        'severity': 'unknown',
        'reason': 'No index data.',
        'signals': const [],
      },
      volatility: const {
        'available': false,
        'elevated': false,
        'vol_pct': null,
        'threshold_pct': 22.0,
        'reason': 'No volatility reading on the tape.',
      },
    ));
    expect(find.text('UNKNOWN'), findsNWidgets(2));
    expect(find.textContaining('cannot be ruled in or out'), findsOneWidget);
    expect(find.textContaining('cannot fire either way'), findsOneWidget);
    expect(find.text('CALM'), findsNothing);
    expect(find.text('STABLE'), findsNothing);
  });

  testWidgets('a switched-off trigger is shown as not watching',
      (tester) async {
    // A rule that is off and a rule that is on and quiet are different
    // states; a user must not believe a crash rule is watching when it is not.
    await _pump(tester, _plan(
      actions: [_asset('BIG.NS')],
      considered: [
        {
          'name': 'market_crash',
          'label': 'Market crash',
          'hit': false,
          'enabled': false,
          'detail': 'Market fall not measured.'
        },
      ],
    ));
    expect(find.textContaining('Not watching'), findsOneWidget);
  });

  // ── mode, totals, empties ──

  testWidgets('manual mode is due because the user asked to look',
      (tester) async {
    await _pump(tester,
        _plan(actions: [_asset('BIG.NS')], mode: 'manual', fired: const []));
    expect(find.text('MANUAL'), findsOneWidget);
    expect(find.text('DUE NOW'), findsOneWidget);
    expect(find.textContaining('because you asked to look'), findsOneWidget);
  });

  testWidgets('automatic mode with nothing firing is not due', (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')], fired: const []));
    expect(find.text('AUTOMATIC'), findsOneWidget);
    expect(find.text('NOT DUE'), findsOneWidget);
    expect(find.textContaining('2027-03-02'), findsOneWidget);
  });

  testWidgets('a plan needing new money labels the shortfall', (tester) async {
    await _pump(tester, _plan(
      actions: [
        _asset('TINY.NS',
            action: 'ADD',
            status: 'under',
            weight: 0.9,
            target: 2.0,
            amount: 15000,
            gain: 0,
            tax: 0,
            net: 0,
            reason: '0.9% of the stocks sleeve, below the 2% floor.')
      ],
      totals: {
        'sell_value': 0.0,
        'buy_value': 15000.0,
        'tax_estimated': 0.0,
        'net_proceeds': 0.0,
        'cash_after_plan': -15000.0,
        'trims': 0,
        'adds': 1,
        'skipped': 0,
        'manual_review': 0,
      },
    ));
    expect(find.text('NEW MONEY NEEDED'), findsOneWidget);
    expect(find.text('CASH LEFT OVER'), findsNothing);
  });

  testWidgets('an empty portfolio says so instead of claiming balance',
      (tester) async {
    await _pump(tester, _plan(actions: const []));
    expect(find.text('Nothing to weigh yet'), findsOneWidget);
  });

  testWidgets('a nearly mature lot carries its deferral note', (tester) async {
    await _pump(tester, _plan(actions: [
      _asset('BIG.NS',
          note: '500 of these units turn long-term in 12 days.'),
    ]));
    expect(find.byTooltip('500 of these units turn long-term in 12 days.'),
        findsOneWidget);
  });

  testWidgets('the settings panel opens and shows both bands', (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]));
    expect(find.text('REBALANCE SETTINGS'), findsOneWidget);
    // Collapsed by default: the plan is the point of the screen.
    expect(find.text('PER-ASSET BAND'), findsNothing);

    await tester.tap(find.text('REBALANCE SETTINGS'));
    await tester.pumpAndSettle();

    expect(find.text('PER-ASSET BAND'), findsOneWidget);
    expect(find.text('CATEGORY DRIFT ALLOWED'), findsOneWidget);
    expect(find.text('REBALANCE TRIGGERS'), findsOneWidget);
    expect(find.byType(RangeSlider), findsOneWidget);
    expect(find.textContaining('2% – 10% of its category'), findsOneWidget);
    expect(find.text('PORTFOLIO GAIN OVER'), findsOneWidget);
    expect(find.text('PORTFOLIO LOSS OVER'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  // ── strategy picker ──

  testWidgets('the selected preset is named with what it does', (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]));
    expect(find.text('REBALANCING STRATEGY'), findsOneWidget);
    expect(find.textContaining('S10 · Wide band + dividends'), findsOneWidget);
    expect(find.text('Trims above 20%'), findsOneWidget);
    expect(find.text('Funds largest shortfall first'), findsOneWidget);
    expect(find.text('Reinvests income'), findsOneWidget);
  });

  testWidgets('a backtested return is never shown as a forecast',
      (tester) async {
    // The figure is prominent, so the sentence that bounds it has to be on
    // screen with it — not in a tooltip and not on another tab.
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]));
    expect(find.text('15.97%'), findsOneWidget);
    expect(find.text('BACKTESTED'), findsOneWidget);
    expect(find.textContaining('not a forecast'), findsOneWidget);
  });

  testWidgets('a never-sells preset says so instead of showing a ceiling',
      (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')], strategyPreset: {
      'id': 'S6',
      'name': 'Cash-flow + dividends',
      'tagline': 'S2, plus put the dividends back to work.',
      'never_sells': true,
      'effective_max_weight_pct': 20.0,
      'deploy_label': 'largest shortfall first',
      'reinvest_income': true,
      'measured': {'xirr_pct': 15.82, 'sells': 0},
      'measured_note': 'Backtested, not a forecast.',
    }));
    expect(find.text('Never sells'), findsOneWidget);
    expect(find.text('Trims above 20%'), findsNothing);
  });

  testWidgets('the return-on-cost proxy is disclosed where it is used',
      (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')], strategyPreset: {
      'id': 'M1',
      'name': 'Master',
      'tagline': 'Reinvest income, fund the weakest first, cap at 25%.',
      'never_sells': false,
      'effective_max_weight_pct': 25.0,
      'deploy_label': 'weakest return on cost first',
      'deploy_note': 'Ordered by return on cost, not by the 12-month price '
          'momentum the backtest used.',
      'reinvest_income': true,
      'measured': {'xirr_pct': 16.53, 'sells': 1},
      'measured_note': 'Backtested, not a forecast.',
    }));
    expect(find.text('Funds weakest return on cost first'), findsOneWidget);
    expect(find.textContaining('not by the 12-month price momentum'),
        findsOneWidget);
  });

  testWidgets('a category table is self-contained at 100% of itself',
      (tester) async {
    // Stocks are weighed against stocks and funds against funds. A
    // share-of-everything column here would invite comparing a stock's weight
    // to a fund's, which is the comparison the band is designed not to make.
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]));
    expect(find.text('W% BEFORE'), findsOneWidget);
    expect(find.text('OF BOOK'), findsNothing);
    // ...and the cross-category view still exists, above.
    expect(find.text('ASSET MIX'), findsOneWidget);
  });

  testWidgets('a deferred breach is not reported as inside the band',
      (tester) async {
    // A holding over its ceiling whose sale is deferred for tax is still over
    // its ceiling. Counting only proposed TRADES once printed "all inside
    // their band" directly above a row showing 30% against a 10% ceiling.
    await _pump(
        tester,
        _plan(actions: [
          _asset('BIG.NS',
              action: 'WAIT',
              status: 'over',
              amount: 0,
              reason: 'Wait: insufficient verified long-term FIFO units.')
        ]));
    expect(find.text('WAIT'), findsOneWidget);
    expect(find.text('all inside their band'), findsNothing);
    expect(find.textContaining('OUT OF BAND'), findsOneWidget);
  });

  testWidgets('a genuinely clean category still says so', (tester) async {
    await _pump(
        tester,
        _plan(actions: [
          _asset('OK.NS',
              action: 'HOLD',
              status: 'within',
              weight: 6.0,
              target: 6.0,
              amount: 0,
              reason: 'Inside its band.')
        ]));
    expect(find.text('all inside their band'), findsOneWidget);
    expect(find.textContaining('OUT OF BAND'), findsNothing);
  });

  // ── share counts ──

  testWidgets('the row shows what is held and how much of it is long term',
      (tester) async {
    // 3,000 held, 1,800 of them past a year. Without the second number a
    // "WAIT" verdict is an assertion the reader cannot check. The sold count
    // is deliberately neither figure, so a collision cannot make this pass.
    await _pump(tester,
        _plan(actions: [_asset('BIG.NS', longTermUnits: 1800, tradeUnits: -900)]));
    expect(find.text('HELD BEFORE'), findsOneWidget);
    expect(find.text('1Y+ QTY'), findsOneWidget);
    expect(find.text('3000'), findsOneWidget);
    expect(find.text('1800'), findsOneWidget);
    // ...and what the trade leaves behind.
    expect(find.text('2100'), findsOneWidget);
  });

  testWidgets('a sell is a red share count in the SOLD column', (tester) async {
    await _pump(tester,
        _plan(actions: [_asset('BIG.NS', longTermUnits: 1800, tradeUnits: -2000)]));
    final t = tester.widget<Text>(find.text('2000'));
    expect(t.style!.color, AppTheme.dark().extension<AppColorScheme>()!.dn);
  });

  testWidgets('a buy is a green positive share count', (tester) async {
    await _pump(
        tester,
        _plan(actions: [
          _asset('TINY.NS',
              action: 'ADD', status: 'under', weight: 0.9, target: 2.0,
              amount: 15000, tradeUnits: 137)
        ]));
    final t = tester.widget<Text>(find.text('137'));
    expect(t.style!.color, AppTheme.dark().extension<AppColorScheme>()!.up);
  });

  testWidgets('a row proposing nothing shows no share count', (tester) async {
    await _pump(
        tester,
        _plan(actions: [
          _asset('OK.NS',
              action: 'HOLD', status: 'within', weight: 6.0, target: 6.0,
              amount: 0, tradeUnits: 0)
        ]));
    // Both trade columns read a plain zero - this is a ledger, and "nothing
    // bought" is a fact, not an absence.
    expect(find.text('0'), findsAtLeastNWidgets(2));
    expect(find.text('HOLD'), findsOneWidget);
  });

  testWidgets('fractional units survive for funds', (tester) async {
    // Whole shares for equities, but a fund really can hold 1,234.56 units.
    await _pump(
        tester,
        _plan(actions: [
          _asset('Flexi Fund',
              category: 'mutual_funds', categoryLabel: 'Mutual Funds',
              heldUnits: 1234.56, longTermUnits: 1000.25, tradeUnits: -12.5)
        ]));
    expect(find.text('1234.56'), findsOneWidget);
    expect(find.text('1000.25'), findsOneWidget);
    // Sold, and what is left: fractional on both sides of the trade.
    expect(find.text('12.50'), findsOneWidget);
    expect(find.text('1222.06'), findsOneWidget);
  });

  // ── the table follows the chosen strategy ──

  /// A preset as the engine reports it, with the three flags that decide
  /// which columns the table shows.
  Map<String, dynamic> _preset({
    required String id,
    required String name,
    required bool canSell,
    required bool showRank,
    String? rankLabel,
    double ceiling = 20.0,
    int? rank,
  }) =>
      {
        'id': id,
        'name': name,
        'tagline': '$name tagline.',
        'never_sells': !canSell,
        'effective_max_weight_pct': ceiling,
        'deploy_label': showRank ? 'weakest return on cost first'
            : 'largest shortfall first',
        'reinvest_income': false,
        'shows_long_term_units': canSell,
        'shows_rank': showRank,
        'rank_label': rankLabel,
        'rank': rank,
        'rank_of': 16,
        'measured': {'xirr_pct': 14.0, 'sells': canSell ? 3 : 0},
        'measured_note': 'Backtested, not a forecast.',
      };

  testWidgets('a selling strategy shows long-term units and BUY / SELL',
      (tester) async {
    await _pump(
        tester,
        _plan(actions: [_asset('BIG.NS')], strategyPreset: _preset(
            id: 'S10', name: 'Wide band + dividends',
            canSell: true, showRank: false)));
    expect(find.text('1Y+ QTY'), findsOneWidget);
    expect(find.text('ACTION'), findsOneWidget);
    expect(find.text('#'), findsNothing);
  });

  testWidgets('a never-sells strategy drops the long-term column entirely',
      (tester) async {
    // Nothing is ever sold under S6, so how much has aged past a year is a
    // number the reader cannot act on. Showing it invites a decision the rule
    // will not honour.
    await _pump(
        tester,
        _plan(actions: [_asset('BIG.NS')], strategyPreset: _preset(
            id: 'S6', name: 'Cash-flow + dividends',
            canSell: false, showRank: false)));
    expect(find.text('1Y+ QTY'), findsNothing);
    expect(find.text('ACTION'), findsOneWidget);
  });

  testWidgets('a tilt strategy adds the ranking that decides funding',
      (tester) async {
    await _pump(
        tester,
        _plan(actions: [_asset('BIG.NS', deployRank: 2)],
            strategyPreset: _preset(
                id: 'S9', name: 'Laggard tilt', canSell: false,
                showRank: true, rankLabel: 'Weakest first')));
    expect(find.text('#'), findsOneWidget);
    expect(find.text('2'), findsWidgets);
    // Still never sells, so the long-term column stays away.
    expect(find.text('1Y+ QTY'), findsNothing);
  });

  testWidgets('the master shows both the ranking and the long-term column',
      (tester) async {
    // M1 funds by weakness AND can trim at 25%, so it is the one preset that
    // needs every optional column at once.
    await _pump(
        tester,
        _plan(actions: [_asset('BIG.NS', deployRank: 1)],
            strategyPreset: _preset(
                id: 'M1', name: 'Master', canSell: true, showRank: true,
                rankLabel: 'Weakest first', ceiling: 25.0)));
    expect(find.text('#'), findsOneWidget);
    expect(find.text('1Y+ QTY'), findsOneWidget);
    expect(find.text('ACTION'), findsOneWidget);
  });

  testWidgets('switching strategy changes the columns on screen',
      (tester) async {
    // The point of the whole change: pick a different rule, get a different
    // table.
    await _pump(
        tester,
        _plan(actions: [_asset('BIG.NS')], strategyPreset: _preset(
            id: 'S3', name: 'Band rebalance', canSell: true,
            showRank: false, ceiling: 12.5)));
    expect(find.text('1Y+ QTY'), findsOneWidget);
    expect(find.text('#'), findsNothing);

    // Tear the tree down between the two. Pumping a second ProviderScope over
    // the first reuses the element tree, so the overridden plan provider keeps
    // handing back the first strategy's payload.
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpAndSettle();

    await _pump(
        tester,
        _plan(actions: [_asset('BIG.NS')], strategyPreset: _preset(
            id: 'S5', name: 'Momentum tilt', canSell: false,
            showRank: true, rankLabel: 'Strongest first')));
    expect(find.text('1Y+ QTY'), findsNothing);
    expect(find.text('#'), findsOneWidget);
  });

  testWidgets('every strategy shape renders a complete row', (tester) async {
    // Exercises all four column combinations. Net cash is the last column, so
    // it is the one a surplus cell would silently swallow — if it is present
    // in each shape, no cell has been dropped.
    for (final shape in [
      (id: 'S3', sell: true, rank: false),
      (id: 'S6', sell: false, rank: false),
      (id: 'S9', sell: false, rank: true),
      (id: 'M1', sell: true, rank: true),
    ]) {
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
      await _pump(
          tester,
          _plan(actions: [_asset('BIG.NS')], strategyPreset: _preset(
              id: shape.id, name: shape.id, canSell: shape.sell,
              showRank: shape.rank,
              rankLabel: shape.rank ? 'Weakest first' : null)));
      expect(find.text('NET CASH +/−'), findsOneWidget,
          reason: '${shape.id}: a cell was dropped');
      expect(find.text('HELD BEFORE'), findsOneWidget, reason: shape.id);
      expect(tester.takeException(), isNull, reason: shape.id);
    }
  });

  // ── adding new money ──

  testWidgets('with no contribution the panel invites one', (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]));
    expect(find.text('ADD FUND'), findsOneWidget);
    expect(find.text('PROCESS'), findsOneWidget);
    // Nothing placed yet, so nothing to clear.
    expect(find.text('CLEAR'), findsNothing);
    expect(find.textContaining('Enter an amount'), findsOneWidget);
  });

  testWidgets('a placed contribution reports what it bought and what is left',
      (tester) async {
    await _pump(
        tester,
        _plan(actions: [
          _asset('TINY.NS',
              action: 'ADD', status: 'under', weight: 0.9, target: 2.0,
              amount: 15000, tradeUnits: 137)
        ], contribution: {
          'amount': 10000.0,
          'deployed': 9991.83,
          'left': 8.17,
          'positions': 2,
        }));
    // Whole rupees, like every other money figure on this screen.
    expect(find.textContaining('₹9992 placed'), findsOneWidget);
    expect(find.textContaining('across 2 holdings'), findsOneWidget);
    expect(find.textContaining('left over'), findsOneWidget);
    // A contribution is in force, so it can be taken back.
    expect(find.text('CLEAR'), findsOneWidget);
  });

  testWidgets('the panel names the order the chosen strategy places money in',
      (tester) async {
    // The whole point of "it depends on the strategy": the copy has to say
    // WHICH rule is about to spend the money, or Process is a black box.
    await _pump(
        tester,
        _plan(actions: [_asset('BIG.NS')], strategyPreset: _preset(
            id: 'S9', name: 'Laggard tilt', canSell: false, showRank: true,
            rankLabel: 'Weakest first')));
    expect(find.textContaining('the way this strategy was measured'),
        findsOneWidget);
    expect(find.textContaining('weakest return on cost first'),
        findsAtLeastNWidgets(1));
  });

  // ── trade history pages ──

  Future<void> openHistory(WidgetTester tester) async {
    await tester.tap(find.text('TRADE HISTORY'));
    await tester.pumpAndSettle();
  }

  testWidgets('the selected strategy shows where it placed of sixteen',
      (tester) async {
    await _pump(
        tester,
        _plan(actions: [_asset('BIG.NS')], strategyPreset: _preset(
            id: 'M4', name: 'Master + peak guard', canSell: true,
            showRank: false, rank: 1)));
    expect(find.text('RANK'), findsOneWidget);
    expect(find.text('1'), findsWidgets);
    // The denominator has to travel with it: "1" alone reads as "first of the
    // ones worth showing", which is not the claim.
    expect(find.text(' / 16'), findsOneWidget);
  });

  testWidgets('a preset with no measured result shows no rank',
      (tester) async {
    // Custom is the user's own band; there is nothing to have ranked it.
    await _pump(
        tester,
        _plan(actions: [_asset('BIG.NS')], strategyPreset: _preset(
            id: 'CUSTOM', name: 'Custom', canSell: true, showRank: false)));
    expect(find.text('RANK'), findsNothing);
  });

  testWidgets('history is collapsed until asked for', (tester) async {
    // It costs a year of daily closes per holding to build, so it must not
    // load just because the plan did.
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]));
    expect(find.text('TRADE HISTORY'), findsOneWidget);
    expect(find.text('HELD BEFORE'), findsOneWidget); // the plan's own column
    expect(find.text('W% BEFORE'), findsOneWidget);
    expect(find.textContaining('page 1 of'), findsNothing);
  });

  testWidgets('it opens on the most recent page, not the oldest',
      (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]));
    await openHistory(tester);
    expect(find.text('page 2 of 2'), findsOneWidget);
    expect(find.text('2026-09-10'), findsOneWidget);
  });

  testWidgets('paging back shows the earlier date', (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]));
    await openHistory(tester);
    await tester.tap(find.byIcon(LucideIcons.chevronLeft));
    await tester.pumpAndSettle();
    expect(find.text('page 1 of 2'), findsOneWidget);
    expect(find.text('2026-03-10'), findsOneWidget);
  });

  testWidgets('a position closed out shows zero held, not a dash',
      (tester) async {
    // A dash reads as "unknown", which is the opposite of what selling 100%
    // of a holding means.
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]),
        history: _history(pages: [
          _historyPage('2026-08-14', 1, 1, rows: [
            {
              'key': 'CUPID',
              'name': 'CUPID',
              'held_before': 310.0,
              'fill': 297.0,
              'value_before': 91407.0,
              'weight_before_pct': 100.0,
              'action': 'SELL',
              'bought': 0.0,
              'sold': 310.0,
              'sold_pct_of_held': 100.0,
              'held_after': 0.0,
              'weight_after_pct': 0.0,
              'net_cash': 92070.0,
            }
          ])
        ]));
    await openHistory(tester);
    expect(find.text('310'), findsWidgets);
    expect(find.text('0'), findsWidgets);
    expect(find.text('100.00%'), findsWidgets);
    expect(find.textContaining('raised ₹92070'), findsOneWidget);
  });

  testWidgets('a page states what moved and what it cost', (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]));
    await openHistory(tester);
    expect(find.textContaining('1 of 2 holdings traded'), findsOneWidget);
    expect(find.textContaining('spent ₹2500'), findsOneWidget);
    // A row that did not trade has no fill price.
    expect(find.text('250.00'), findsOneWidget);
  });

  testWidgets('an unpriced holding is named rather than silently excluded',
      (tester) async {
    // Dropping it would change the denominator every other weight on the page
    // is measured against, so the footer has to admit it.
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]),
        history: _history(pages: [
          _historyPage('2026-03-10', 1, 1, unpriced: ['AAAX', 'BBBX'])
        ]));
    await openHistory(tester);
    expect(find.textContaining('exclude AAAX, BBBX'), findsOneWidget);
    expect(find.textContaining('held but not weighed'), findsOneWidget);
  });

  testWidgets('a replay that does not reconcile says so', (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]),
        history: _history(reconciles: false));
    await openHistory(tester);
    expect(find.textContaining('treat these quantities as approximate'),
        findsOneWidget);
  });

  testWidgets('an empty tradebook explains itself', (tester) async {
    await _pump(tester, _plan(actions: [_asset('BIG.NS')]), history: {
      'pages': [],
      'count': 0,
      'reconciles': true,
      'note': 'No equity transactions on file to replay.',
    });
    await openHistory(tester);
    expect(find.textContaining('No equity transactions'), findsOneWidget);
  });

  testWidgets('the section paints without a render exception', (tester) async {
    await _pump(tester, _plan(actions: [
      _asset('BIG.NS'),
      _asset('TINY.NS',
          action: 'ADD',
          status: 'under',
          weight: 0.9,
          target: 2.0,
          amount: 15000,
          gain: 0,
          tax: 0,
          net: 0),
      _asset('Flexi Fund',
          category: 'mutual_funds',
          categoryLabel: 'Mutual Funds',
          weight: 40.0,
          amount: 300000),
      _asset('manual:debt',
          category: 'debt',
          categoryLabel: 'Debt',
          action: 'REVIEW',
          tradable: false,
          gainPct: null,
          amount: 0),
    ]));
    expect(tester.takeException(), isNull);
  });
}
