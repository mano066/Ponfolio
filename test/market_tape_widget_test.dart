import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:aiei_wealth/core/theme/app_theme.dart';
import 'package:aiei_wealth/data/models/deploy_models.dart';
import 'package:aiei_wealth/presentation/widgets/deploy/market_tape_card.dart';
import 'package:aiei_wealth/providers/deploy_provider.dart';

Map<String, dynamic> _row(
  String sym,
  String label,
  String group, {
  double? last = 23903.5,
  double? dayChg = -12.4,
  double? pct = -0.05,
  double? low = 21281.0,
  double? high = 26277.0,
  String status = 'ok',
}) =>
    {
      'symbol': sym,
      'label': label,
      'group': group,
      'status': status,
      'last': last,
      'day_chg': dayChg,
      'day_chg_pct': pct,
      'low_52w': low,
      'high_52w': high,
      'off_high_pct': 9.2,
      'at_high': false,
      'short_window': false,
    };

void main() {
  testWidgets('tape chip shows day points, 52w low and 52w high',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 1600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final tape = MarketTape.fromJson({
      'as_of': '2026-09-03',
      'indices': [
        _row('^NSEI', 'NIFTY 50', 'broad'),
        _row('NIFTYSMLCAP250.NS', 'SMALLCAP 250', 'size',
            last: 17750.25,
            dayChg: 91.4,
            pct: 0.52,
            low: 14002.0,
            high: 19511.0),
        // Band unusable: low == high. Must not pin the marker to the low.
        _row('^CNXIT', 'IT', 'sector',
            last: 30835.0,
            dayChg: -4.25,
            pct: -0.01,
            low: 30835.0,
            high: 30835.0),
        // Feed down: every figure null.
        _row('^GSPC', 'S&P 500', 'global',
            last: null,
            dayChg: null,
            pct: null,
            low: null,
            high: null,
            status: 'unavailable'),
      ],
    });

    await tester.pumpWidget(ProviderScope(
      overrides: [
        marketTapeProvider.overrideWith((ref) => Stream.value(tape)),
      ],
      child: MaterialApp(
        theme: AppTheme.light(),
        home: const Scaffold(
          body: SingleChildScrollView(
            child: Padding(padding: EdgeInsets.all(20), child: MarketTapeCard()),
          ),
        ),
      ),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));

    expect(tester.takeException(), isNull);

    // Day change in points, both signs.
    expect(find.text('−12.4 pts'), findsOneWidget);
    expect(find.text('+91.4 pts'), findsOneWidget);

    // 52-week endpoints.
    expect(find.text('L 21,281'), findsOneWidget);
    expect(find.text('H 26,277'), findsOneWidget);

    // Unavailable row keeps the placeholders, never a zero.
    expect(find.text('L —'), findsOneWidget);
    expect(find.text('H —'), findsOneWidget);

    // Range position: real band resolves, degenerate and dead bands do not.
    final quotes = tape.indices;
    expect(quotes[0].rangePct, closeTo(52.5, 0.5));
    expect(quotes[2].rangePct, isNull); // low == high
    expect(quotes[3].rangePct, isNull); // feed down
  });
}
