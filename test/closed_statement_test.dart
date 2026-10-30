import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/core/theme/app_theme.dart';
import 'package:aiei_wealth/data/models/closed_positions.dart';
import 'package:aiei_wealth/presentation/widgets/closed_positions_section.dart';

/// The imported Kite statement changes what the closed book *is*: measured
/// rather than reconstructed. These tests pin the distinction, because the
/// failure mode is a screen that shows an estimate labelled as a broker
/// figure — or the reverse, hiding real numbers behind "estimated".

Map<String, dynamic> _payload({
  Object? statement = _unset,
  Object? reconciliation = _unset,
}) => {
  'symbols': [
    {
      'symbol': 'CUPID',
      'trades': 1,
      'qty_closed': 660.0,
      'buy_value': 178350.20,
      'sell_value': 182915.04,
      'gross_pnl': 4564.84,
      'charges_estimated': 432.97,
      'net_pnl_estimated': 4131.87,
      'net_pnl_pct_estimated': 2.32,
      'realized_broker': 4564.84,
      'realized_source': 'broker_statement',
      'realized_agrees': true,
      'dp_charges_estimated': 15.34,
      'dp_charges_source': 'broker_statement',
      'last_sell': '2026-08-14',
      'lots': const [],
    },
  ],
  'totals': {
    'symbols_closed': 1,
    'trades': 1,
    'buy_value': 178350.20,
    'sell_value': 182915.04,
    'gross_pnl': 4564.84,
    'charges_estimated': 1254.01,
    'net_pnl_estimated': 3310.83,
    'net_pnl_pct_estimated': 1.86,
    'short_term_net': 3310.83,
    'long_term_net': 0.0,
    'wins': 1,
    'losses': 0,
    'win_rate_pct': 100.0,
    'unmatched_sell_qty': 0.0,
  },
  'tax_indicative': {'tax': 662.17, 'basis': 'Not a tax computation.'},
  'charges_basis': {'note': 'Estimated from the statutory rate card.'},
  'statement': statement == _unset
      ? {
          'periods': [
            {
              'period': '2025-10-01..2026-09-09',
              'from': '2025-10-01',
              'to': '2026-09-09',
              'realized_pnl': 5086.38,
              'charges_actual': 2234.72,
              'symbols_closed': 5,
            },
          ],
          'covers_from': '2025-10-01',
          'covers_to': '2026-09-09',
          'overlapping_periods': const [],
          'charges_by_head': [
            {'head': 'Brokerage', 'amount': 1308.0955},
            {'head': 'Securities Transaction Tax', 'amount': 586.0},
            {'head': 'Clearing Charges', 'amount': 0.0},
          ],
          'realized_pnl': 5086.38,
          'charges_actual': 2234.72,
          'other_credit_debit': -44.26,
          'period_net': 2807.40,
          'unrealized_pnl': -5974.10,
          'basis': 'Measured: Zerodha Console P&L statement.',
        }
      : statement,
  'reconciliation': reconciliation == _unset
      ? {
          'ledger_fifo_gross': 5086.38,
          'broker_realized': 5086.38,
          'gross_agrees': true,
          'charges_estimated': 1254.01,
          'charges_actual': 2234.72,
          'charges_estimate_error': -980.71,
          'note': 'FIFO against the broker.',
        }
      : reconciliation,
};

const _unset = Object();

Future<void> _pump(
  WidgetTester tester,
  ClosedBook book, {
  double width = 1500,
}) async {
  tester.view.physicalSize = Size(width, 2000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    theme: AppTheme.light(),
    home: Scaffold(
      body: SingleChildScrollView(
        child: SizedBox(
          width: width,
          child: ClosedPositionsSection(book: book),
        ),
      ),
    ),
  ));
  await tester.pump();
}

void main() {
  group('ClosedStatement parsing', () {
    test('reads the period, the charge heads and the derived period net', () {
      final b = ClosedBook.fromJson(_payload());
      expect(b.isMeasured, isTrue);
      expect(b.statement!.coversFrom, '2025-10-01');
      expect(b.statement!.coversTo, '2026-09-09');
      expect(b.statement!.realizedPnl, 5086.38);
      expect(b.statement!.chargesActual, 2234.72);
      expect(b.statement!.periodNet, 2807.40);
      expect(b.statement!.otherCreditDebit, -44.26);
      expect(b.statement!.periods.single.label, '2025-10-01 → 2026-09-09');
    });

    test('the headline figures switch to the measured ones', () {
      final b = ClosedBook.fromJson(_payload());
      expect(b.realized, 5086.38); // broker, not the FIFO net
      expect(b.charges, 2234.72); // billed, not the 1254.01 estimate
      expect(b.chargesAreMeasured, isTrue);
    });

    test('without a statement the estimates remain the headline', () {
      final b = ClosedBook.fromJson(
        _payload(statement: null, reconciliation: null),
      );
      expect(b.isMeasured, isFalse);
      expect(b.chargesAreMeasured, isFalse);
      expect(b.realized, 4564.84); // falls back to FIFO gross
      expect(b.charges, 1254.01); // falls back to the estimate
      expect(b.statement, isNull);
    });

    test('zero-value charge heads are dropped from the ranked list', () {
      final ranked = ClosedBook.fromJson(_payload()).statement!.chargesRanked;
      expect(ranked.map((h) => h.head), ['Brokerage',
        'Securities Transaction Tax']);
      expect(ranked.first.amount, 1308.0955);
    });

    test('an overlap between imported periods is exposed', () {
      final b = ClosedBook.fromJson(
        _payload(
          statement: {
            'periods': const [],
            'overlapping_periods': [
              ['2025-10-01..2026-09-09', '2026-08-01..2026-08-31'],
            ],
          },
        ),
      );
      expect(b.statement!.hasOverlap, isTrue);
      expect(b.statement!.overlappingPeriods.single, hasLength(2));
    });

    test('reconciliation carries both sides and the estimate error', () {
      final rec = ClosedBook.fromJson(_payload()).reconciliation!;
      expect(rec.ledgerFifoGross, 5086.38);
      expect(rec.brokerRealized, 5086.38);
      expect(rec.grossAgrees, isTrue);
      expect(rec.chargesEstimateError, -980.71);
    });

    test('a per-symbol row prefers the broker figure but keeps FIFO', () {
      final s = ClosedBook.fromJson(_payload()).symbols.single;
      expect(s.isMeasured, isTrue);
      expect(s.realized, 4564.84);
      expect(s.grossPnl, 4564.84);
      expect(s.realizedAgrees, isTrue);
      expect(s.dpChargesSource, 'broker_statement');
    });
  });

  group('ClosedPositionsSection with a statement', () {
    testWidgets('headlines the broker figure and the billed charges',
        (tester) async {
      await _pump(tester, ClosedBook.fromJson(_payload()));
      expect(tester.takeException(), isNull);
      expect(find.text('REALISED (BROKER)'), findsOneWidget);
      expect(find.text('PERIOD NET'), findsOneWidget);
      expect(find.text('actually billed'), findsOneWidget);
      expect(find.text('estimated, not billed'), findsNothing);
    });

    testWidgets('shows the reconciliation and marks it reconciled',
        (tester) async {
      await _pump(tester, ClosedBook.fromJson(_payload()));
      expect(find.text('BROKER STATEMENT'), findsOneWidget);
      expect(find.text('RECONCILED'), findsOneWidget);
      expect(find.text('Realised — your ledger, FIFO'), findsOneWidget);
      expect(find.text('Realised — broker statement'), findsOneWidget);
      expect(find.text('Charges — actually billed'), findsOneWidget);
      expect(find.text('Estimate was off by'), findsOneWidget);
    });

    testWidgets('lists what the charges actually were', (tester) async {
      await _pump(tester, ClosedBook.fromJson(_payload()));
      expect(find.text('WHAT THE CHARGES WERE'), findsOneWidget);
      expect(find.text('Brokerage'), findsOneWidget);
      expect(find.text('Securities Transaction Tax'), findsOneWidget);
      // A zero head is real but not worth a row.
      expect(find.text('Clearing Charges'), findsNothing);
    });

    testWidgets('says period net is not profit on the closed lots',
        (tester) async {
      await _pump(tester, ClosedBook.fromJson(_payload()));
      expect(
        find.textContaining('period net is not the same as profit on these'),
        findsOneWidget,
      );
      expect(find.textContaining('Realised P&L and charges are measured'),
          findsOneWidget);
    });

    testWidgets('a mismatch is flagged, not reconciled away', (tester) async {
      await _pump(
        tester,
        ClosedBook.fromJson(
          _payload(
            reconciliation: {
              'ledger_fifo_gross': 4000.0,
              'broker_realized': 5086.38,
              'gross_agrees': false,
              'charges_estimated': 1254.01,
              'charges_actual': 2234.72,
            },
          ),
        ),
      );
      expect(find.text('MISMATCH'), findsOneWidget);
      expect(find.text('RECONCILED'), findsNothing);
    });

    testWidgets('an overlapping import warns that totals double',
        (tester) async {
      await _pump(
        tester,
        ClosedBook.fromJson(
          _payload(
            statement: {
              'periods': const [],
              'covers_from': '2025-10-01',
              'covers_to': '2026-09-09',
              'realized_pnl': 5086.38,
              'charges_actual': 2234.72,
              'overlapping_periods': [
                ['2025-10-01..2026-09-09', '2026-08-01..2026-08-31'],
              ],
            },
          ),
        ),
      );
      expect(
        find.textContaining('being added twice'),
        findsOneWidget,
      );
    });

    testWidgets('without a statement the estimate wording returns',
        (tester) async {
      await _pump(
        tester,
        ClosedBook.fromJson(_payload(statement: null, reconciliation: null)),
      );
      expect(find.text('BROKER STATEMENT'), findsNothing);
      expect(find.text('NET REALISED'), findsOneWidget);
      expect(find.text('estimated, not billed'), findsOneWidget);
      expect(
        find.textContaining('import the Kite P&L statement for the real'),
        findsOneWidget,
      );
    });

    for (final width in [375.0, 768.0, 1500.0]) {
      testWidgets('statement panel lays out at $width', (tester) async {
        await _pump(tester, ClosedBook.fromJson(_payload()), width: width);
        expect(tester.takeException(), isNull);
      });
    }
  });
}
