import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/core/theme/app_theme.dart';
import 'package:aiei_wealth/data/models/closed_positions.dart';
import 'package:aiei_wealth/presentation/widgets/closed_positions_section.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';

/// TDS comes from the funds ledger, the only Console export that carries it,
/// and it arrives in two shapes that must never be summed: actually deducted
/// (a cost) and provisional (blocked, then normally reversed). On this account
/// that pair is ₹20,503 against ₹497.65 real, so conflating them would
/// overstate the tax 41-fold on screen.

Map<String, dynamic> _tdsJson({
  double deducted = 497.65,
  double blocked = 20503.03,
  double reversed = 20503.03,
  double outstanding = 0.0,
  List<List<String>> overlaps = const [],
}) => {
  'deducted': deducted,
  'provisional_blocked': blocked,
  'provisional_reversed': reversed,
  'provisional_outstanding': outstanding,
  'covers_from': '2026-08-07',
  'covers_to': '2026-09-09',
  'overlapping_periods': overlaps,
  'basis': 'Measured: Console funds ledger. Deducted is TDS actually withheld.',
  'entries': [
    {
      'particulars': 'TDS payable on Equity Intraday for 2026-08-07',
      'date': '2026-08-07',
      'debit': 497.65,
      'credit': 0.0,
      'kind': 'tds',
    },
    {
      'particulars': 'Provisional TDS amount blocked for 2026166',
      'date': '2026-09-02',
      'debit': 20503.03,
      'credit': 0.0,
      'kind': 'tds_provisional_blocked',
    },
    {
      'particulars': 'Provisional TDS amount reversed for 2026166',
      'date': '2026-09-03',
      'debit': 0.0,
      'credit': 20503.03,
      'kind': 'tds_provisional_reversed',
    },
  ],
};

Map<String, dynamic> _payload({Object? tds, Object? statement}) => {
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
      'lots': const [],
    },
  ],
  'totals': {
    'symbols_closed': 1,
    'trades': 1,
    'buy_value': 178350.20,
    'gross_pnl': 4564.84,
    'charges_estimated': 1254.01,
    'net_pnl_estimated': 3310.83,
    'wins': 1,
    'losses': 0,
    'win_rate_pct': 100.0,
    'unmatched_sell_qty': 0.0,
  },
  'tax_indicative': {'tax': 662.17, 'basis': 'Not a tax computation.'},
  'charges_basis': {'note': 'Estimated from the statutory rate card.'},
  'statement': statement,
  'tds': tds,
};

Future<void> _pump(
  WidgetTester tester,
  ClosedBook book, {
  double width = 1500,
}) async {
  tester.view.physicalSize = Size(width, 2400);
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
  group('ClosedTds parsing', () {
    test('keeps deducted, blocked and reversed as three separate figures', () {
      final t = ClosedBook.fromJson(_payload(tds: _tdsJson())).tds!;
      expect(t.deducted, 497.65);
      expect(t.provisionalBlocked, 20503.03);
      expect(t.provisionalReversed, 20503.03);
      expect(t.provisionalOutstanding, 0.0);
      expect(t.hasProvisional, isTrue);
      expect(t.hasOutstanding, isFalse);
      expect(t.entries, hasLength(3));
    });

    test('a block with no reversal is outstanding', () {
      final t = ClosedBook.fromJson(
        _payload(tds: _tdsJson(reversed: 0, outstanding: 20503.03)),
      ).tds!;
      expect(t.hasOutstanding, isTrue);
      expect(t.provisionalOutstanding, 20503.03);
    });

    test('a reversal entry is marked as one', () {
      final t = ClosedBook.fromJson(_payload(tds: _tdsJson())).tds!;
      final reversal = t.entries.firstWhere((e) => e.isReversal);
      expect(reversal.credit, 20503.03);
      expect(reversal.net, -20503.03); // money back
      expect(t.entries.first.isProvisional, isFalse);
    });

    test('charges plus TDS is available but never merged into charges', () {
      final b = ClosedBook.fromJson(_payload(tds: _tdsJson()));
      expect(b.charges, 1254.01); // unchanged by TDS
      expect(b.costWithTds, closeTo(1254.01 + 497.65, 0.001));
    });

    test('no ledger imported means no TDS block at all', () {
      final b = ClosedBook.fromJson(_payload());
      expect(b.tds, isNull);
      expect(b.costWithTds, 1254.01); // charges alone
    });
  });

  group('ClosedPositionsSection with TDS', () {
    testWidgets('shows the deducted figure, not the provisional one',
        (tester) async {
      await _pump(tester, ClosedBook.fromJson(_payload(tds: _tdsJson())));
      expect(tester.takeException(), isNull);
      expect(find.text('TDS DEDUCTED'), findsOneWidget);
      expect(find.text('Actually deducted'), findsOneWidget);
      expect(find.text('Provisional — blocked'), findsOneWidget);
      expect(find.text('Provisional — reversed'), findsOneWidget);
      // Netted to zero, so it is labelled as a net rather than as owed.
      expect(find.text('Provisional net (blocked − reversed)'), findsOneWidget);
      expect(find.text('Still blocked, not yet reversed'), findsNothing);
    });

    testWidgets('an outstanding block is called out as still blocked',
        (tester) async {
      await _pump(
        tester,
        ClosedBook.fromJson(
          _payload(tds: _tdsJson(reversed: 0, outstanding: 20503.03)),
        ),
      );
      expect(find.text('Still blocked, not yet reversed'), findsOneWidget);
      expect(find.textContaining('still blocked'), findsWidgets);
    });

    testWidgets('the panel renders from a ledger alone, with no P&L statement',
        (tester) async {
      await _pump(tester, ClosedBook.fromJson(_payload(tds: _tdsJson())));
      expect(find.text('BROKER STATEMENT'), findsOneWidget);
      // Twice by design: the panel's TDS block, and the per-position column
      // that only exists once a ledger has been imported.
      expect(find.text('TDS'), findsNWidgets(2));
      // No P&L statement, so no realised/charges reconciliation rows.
      expect(find.text('Realised — broker statement'), findsNothing);
      expect(find.text('WHAT THE CHARGES WERE'), findsNothing);
    });

    testWidgets('lists the individual TDS ledger lines', (tester) async {
      await _pump(tester, ClosedBook.fromJson(_payload(tds: _tdsJson())));
      expect(
        find.textContaining('TDS payable on Equity Intraday'),
        findsOneWidget,
      );
      expect(
        find.textContaining('Provisional TDS amount reversed'),
        findsOneWidget,
      );
    });

    testWidgets('overlapping ledgers warn that TDS doubles', (tester) async {
      await _pump(
        tester,
        ClosedBook.fromJson(
          _payload(
            tds: _tdsJson(
              overlaps: [
                ['2026-08-01..2026-08-31', '2026-08-15..2026-09-15'],
              ],
            ),
          ),
        ),
      );
      expect(find.textContaining('TDS is being counted twice'), findsOneWidget);
    });

    testWidgets('no ledger means no TDS anywhere on the card', (tester) async {
      await _pump(tester, ClosedBook.fromJson(_payload()));
      expect(find.text('TDS DEDUCTED'), findsNothing);
      expect(find.text('Actually deducted'), findsNothing);
    });

    for (final width in [375.0, 768.0, 1500.0]) {
      testWidgets('TDS block lays out at $width', (tester) async {
        await _pump(tester, ClosedBook.fromJson(_payload(tds: _tdsJson())),
            width: width);
        expect(tester.takeException(), isNull);
      });
    }
  });

  group('TDS column in BY POSITION', () {
    testWidgets('sits between CHARGES and NET, and only with a ledger',
        (tester) async {
      await _pump(tester, ClosedBook.fromJson(_payload(tds: _tdsJson())));
      // 'TDS' also labels the panel block lower down, so the comparison is
      // pinned to the header row: same vertical position as CHARGES and NET.
      final charges = tester.getRect(find.text('CHARGES').last);
      final net = tester.getRect(find.text('NET').last);
      final tdsInHeader = tester
          .widgetList<Text>(find.text('TDS'))
          .map((w) => tester.getRect(find.byWidget(w)))
          .where((r) => (r.top - charges.top).abs() < 4)
          .toList();
      expect(tdsInHeader, hasLength(1),
          reason: 'exactly one TDS label belongs to the column header row');
      expect(charges.left, lessThan(tdsInHeader.single.left));
      expect(tdsInHeader.single.left, lessThan(net.left));
    });

    testWidgets('no ledger means no TDS column at all', (tester) async {
      await _pump(tester, ClosedBook.fromJson(_payload()));
      // A column of dashes would read as "no tax was withheld"; absent reads
      // as "not imported", which is the truth.
      expect(find.text('TDS'), findsNothing);
    });

    testWidgets('a position with TDS shows it and nets it off', (tester) async {
      final book = ClosedBook.fromJson({
        ..._payload(tds: _tdsJson()),
        'symbols': [
          {
            'symbol': 'J&KBANK',
            'trades': 1,
            'qty_closed': 450.0,
            'buy_value': 81225.0,
            'sell_value': 81450.0,
            'gross_pnl': 225.0,
            'charges_estimated': 196.68,
            'net_pnl_estimated': 28.32,
            'net_pnl_pct_estimated': 0.03,
            'tds_attributed': 70.20,
            'tds_source': 'date_matched',
            'net_after_tds': -41.88,
            'net_after_tds_pct': -0.05,
            'lots': const [],
          },
        ],
      });
      final row = book.symbols.single;
      // The verdict flips once the withheld tax counts: +28.32 becomes -41.88.
      expect(row.netPnlEstimated, 28.32);
      expect(row.net, -41.88);
      expect(row.tdsAttributed, 70.20);

      await _pump(tester, book);
      expect(tester.takeException(), isNull);
      expect(find.text('-₹42'), findsWidgets);
    });

    testWidgets('a position with no TDS shows a dash, not a zero',
        (tester) async {
      await _pump(tester, ClosedBook.fromJson(_payload(tds: _tdsJson())));
      // The fixture's CUPID row carries no attributed TDS.
      expect(find.text('—'), findsWidgets);
    });
  });

  group('Dense table column gutter', () {
    testWidgets('a right-aligned header never touches the next left one',
        (tester) async {
      // The reported bug: 'DAY%' and 'SIGNAL' rendered as 'DAY%SIGNAL'.
      const cols = [
        DenseCol('INSTRUMENT', 3, numeric: false),
        DenseCol('DAY%', 2),
        DenseCol('SIGNAL', 2, numeric: false),
      ];
      tester.view.physicalSize = const Size(520, 300);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: Builder(
            builder: (context) => denseColumnHeader(context, cols),
          ),
        ),
      ));
      await tester.pump();
      expect(tester.takeException(), isNull);

      final day = tester.getRect(find.text('DAY%'));
      final signal = tester.getRect(find.text('SIGNAL'));
      expect(
        signal.left - day.right,
        greaterThan(2.0),
        reason: 'adjacent headers must be separated by the column gutter',
      );
    });

    testWidgets('a long header truncates instead of wrapping', (tester) async {
      const cols = [
        DenseCol('A VERY LONG COLUMN NAME INDEED', 1, numeric: false),
        DenseCol('X', 1),
      ];
      tester.view.physicalSize = const Size(200, 200);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: Builder(
            builder: (context) => denseColumnHeader(context, cols),
          ),
        ),
      ));
      await tester.pump();
      expect(tester.takeException(), isNull);
      final text = tester.widget<Text>(
        find.text('A VERY LONG COLUMN NAME INDEED'),
      );
      expect(text.maxLines, 1);
      expect(text.overflow, TextOverflow.ellipsis);
    });
  });
}
