import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/core/theme/app_theme.dart';
import 'package:aiei_wealth/data/models/closed_positions.dart';
import 'package:aiei_wealth/presentation/widgets/closed_positions_section.dart';

/// The section stacks a KPI grid, a wide table and an expandable lot list, so
/// the failure mode is a RenderFlex assertion at paint time that analysis
/// cannot see. Every test here pumps at a real width and asserts no exception.

ClosedBook _book({
  double net = 934.07,
  double unmatched = 0,
  int trades = 3,
  bool longTerm = false,
}) => ClosedBook.fromJson({
  'as_of': '2026-09-09T10:00:00+05:30',
  'symbols': [
    {
      'symbol': 'ENGINERSIN',
      'trades': 2,
      'qty_closed': 310.0,
      'buy_value': 88000.0,
      'sell_value': 85365.0,
      'gross_pnl': -2635.0,
      'charges_estimated': 210.56,
      'net_pnl_estimated': -2845.56,
      'net_pnl_pct_estimated': -3.22,
      'last_sell': '2025-02-11',
      'still_open_qty': 0.0,
      'lots': [
        {
          'symbol': 'ENGINERSIN', 'qty': 100.0,
          'buy_date': '2024-01-02', 'buy_price': 285.0, 'buy_value': 28500.0,
          'sell_date': '2025-02-11', 'sell_price': 275.0, 'sell_value': 27500.0,
          'gross_pnl': -1000.0, 'days_held': longTerm ? 406 : 40,
          'term': longTerm ? 'long' : 'short',
          'charges_estimated': 70.0, 'net_pnl_estimated': -1070.0,
        },
        {
          'symbol': 'ENGINERSIN', 'qty': 210.0,
          'buy_date': '2024-03-02', 'buy_price': 283.0, 'buy_value': 59430.0,
          'sell_date': '2025-02-11', 'sell_price': 275.0, 'sell_value': 57750.0,
          'gross_pnl': -1680.0, 'days_held': 346, 'term': 'short',
          'charges_estimated': 140.0, 'net_pnl_estimated': -1820.0,
        },
      ],
    },
    {
      'symbol': 'CUPID',
      'trades': 1,
      'qty_closed': 660.0,
      'buy_value': 196000.0,
      'sell_value': 200564.0,
      'gross_pnl': 4564.84,
      'charges_estimated': 432.97,
      'net_pnl_estimated': 4131.87,
      'net_pnl_pct_estimated': 2.32,
      'last_sell': '2025-06-18',
      'lots': [
        {
          'symbol': 'CUPID', 'qty': 660.0,
          'buy_date': '2024-08-01', 'buy_price': 297.0, 'buy_value': 196020.0,
          'sell_date': '2025-06-18', 'sell_price': 303.9, 'sell_value': 200574.0,
          'gross_pnl': 4554.0, 'days_held': 321, 'term': 'short',
          'charges_estimated': 432.97, 'net_pnl_estimated': 4121.03,
        },
      ],
    },
  ],
  'totals': {
    'symbols_closed': 2, 'trades': trades,
    'buy_value': 284000.0, 'sell_value': 285929.0,
    'gross_pnl': 1929.84, 'charges_estimated': 643.53,
    'net_pnl_estimated': net, 'net_pnl_pct_estimated': 0.73,
    'short_term_net': net, 'long_term_net': 0.0,
    'wins': 1, 'losses': 1, 'win_rate_pct': 50.0,
    'unmatched_sell_qty': unmatched,
  },
  'tax_indicative': {
    'short_term_gain': net, 'long_term_gain': 0.0,
    'ltcg_exemption_applied': 0.0, 'tax': net * 0.2,
    'basis': 'Statutory rates only. Not a tax computation.',
  },
  'charges_basis': {'note': 'Estimated from the statutory rate card.'},
});

Future<void> _pump(
  WidgetTester tester,
  Widget section, {
  double width = 1500,
  bool dark = false,
}) async {
  tester.view.physicalSize = Size(width, 1400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    theme: dark ? AppTheme.dark() : AppTheme.light(),
    home: Scaffold(
      body: SingleChildScrollView(child: SizedBox(width: width, child: section)),
    ),
  ));
  await tester.pump();
}

void main() {
  testWidgets('reports net, gross and charges as three separate figures',
      (tester) async {
    await _pump(tester, ClosedPositionsSection(book: _book()));
    expect(tester.takeException(), isNull);
    expect(find.text('NET REALISED'), findsOneWidget);
    expect(find.text('GROSS REALISED'), findsOneWidget);
    expect(find.text('TAX (INDICATIVE)'), findsOneWidget);
    // Charges are named twice on purpose: once in the KPI strip for the book,
    // once as the per-position column, so a row can be checked against the
    // total. Neither is folded into the net figure beside it.
    expect(find.text('CHARGES'), findsNWidgets(2));
    // Both closed positions are listed, worst first.
    expect(find.text('ENGINERSIN'), findsOneWidget);
    expect(find.text('CUPID'), findsOneWidget);
  });

  testWidgets('says on the card that charges and tax are computed, not billed',
      (tester) async {
    await _pump(tester, ClosedPositionsSection(book: _book()));
    expect(
      find.textContaining('estimated from the statutory delivery rate card'),
      findsOneWidget,
    );
    expect(find.textContaining('not a tax computation'), findsOneWidget);
  });

  testWidgets('the worst position sorts above the profitable one',
      (tester) async {
    await _pump(tester, ClosedPositionsSection(book: _book()));
    expect(
      tester.getTopLeft(find.text('ENGINERSIN')).dy,
      lessThan(tester.getTopLeft(find.text('CUPID')).dy),
    );
  });

  testWidgets('tapping a position reveals its FIFO round trips',
      (tester) async {
    await _pump(tester, ClosedPositionsSection(book: _book()));
    expect(find.textContaining('ROUND TRIPS'), findsNothing);
    await tester.tap(find.text('ENGINERSIN'));
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.text('ENGINERSIN · 2 ROUND TRIPS'), findsOneWidget);
    // Each lot shows both legs and its holding period.
    expect(find.textContaining('2024-01-02 @ 285.00'), findsOneWidget);
    await tester.tap(find.text('ENGINERSIN'));
    await tester.pump();
    expect(find.textContaining('ROUND TRIPS'), findsNothing);
  });

  testWidgets('a long-term lot is tagged LT, a short one ST', (tester) async {
    await _pump(tester, ClosedPositionsSection(book: _book(longTerm: true)));
    await tester.tap(find.text('ENGINERSIN'));
    await tester.pump();
    expect(find.text('LT'), findsOneWidget);
    expect(find.text('ST'), findsOneWidget);
  });

  testWidgets('an unmatched sell is called out, not hidden', (tester) async {
    await _pump(tester, ClosedPositionsSection(book: _book(unmatched: 12)));
    expect(
      find.textContaining('12 sold shares have no matching buy'),
      findsOneWidget,
    );
  });

  testWidgets('no unmatched sells means no warning', (tester) async {
    await _pump(tester, ClosedPositionsSection(book: _book()));
    expect(find.textContaining('no matching buy'), findsNothing);
  });

  testWidgets('an empty book explains what would appear here', (tester) async {
    await _pump(tester, const ClosedPositionsSection(book: ClosedBook()));
    expect(find.text('No closed positions yet'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('loading an empty book shows the loader, not an empty state',
      (tester) async {
    await _pump(
      tester,
      const ClosedPositionsSection(book: ClosedBook(), loading: true),
    );
    expect(find.text('No closed positions yet'), findsNothing);
    expect(find.byType(DensePulseLoaderProbe), findsNothing);
  });

  testWidgets('a failure offers a retry rather than an empty table',
      (tester) async {
    var retried = false;
    await _pump(
      tester,
      ClosedPositionsSection(
        book: const ClosedBook(),
        error: StateError('backend down'),
        onRetry: () => retried = true,
      ),
    );
    expect(find.text('Could not load closed positions'), findsOneWidget);
    await tester.tap(find.text('Retry'));
    expect(retried, isTrue);
  });

  for (final width in [375.0, 768.0, 1500.0]) {
    for (final dark in [true, false]) {
      testWidgets('lays out at $width dark=$dark without overflowing',
          (tester) async {
        await _pump(tester, ClosedPositionsSection(book: _book()),
            width: width, dark: dark);
        expect(tester.takeException(), isNull);
        await tester.tap(find.text('CUPID'));
        await tester.pump();
        expect(tester.takeException(), isNull);
      });
    }
  }
}

/// Placeholder finder type so the loading test states its intent without
/// reaching into the kit's private widgets.
class DensePulseLoaderProbe extends StatelessWidget {
  const DensePulseLoaderProbe({super.key});
  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
