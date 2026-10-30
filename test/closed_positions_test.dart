import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/data/models/closed_positions.dart';

/// The realised book carries three kinds of number — measured, estimated and
/// indicative — and the parsing must not quietly turn a missing one into zero.

Map<String, dynamic> _lot({
  String symbol = 'GAEL',
  double qty = 10,
  String? buyDate = '2024-01-01',
  String? sellDate = '2024-06-01',
  double buyPrice = 100,
  double sellPrice = 150,
  int days = 152,
  String term = 'short',
}) => {
  'symbol': symbol,
  'qty': qty,
  'buy_date': buyDate,
  'buy_price': buyPrice,
  'buy_value': qty * buyPrice,
  'sell_date': sellDate,
  'sell_price': sellPrice,
  'sell_value': qty * sellPrice,
  'gross_pnl': qty * (sellPrice - buyPrice),
  'gross_pnl_pct': (sellPrice - buyPrice) / buyPrice * 100,
  'days_held': days,
  'term': term,
  'charges_estimated': 25.0,
  'net_pnl_estimated': qty * (sellPrice - buyPrice) - 25.0,
};

Map<String, dynamic> _payload({
  List<Map<String, dynamic>>? symbols,
  Map<String, dynamic>? totals,
}) => {
  'as_of': '2026-09-09T10:00:00+05:30',
  'symbols':
      symbols ??
      [
        {
          'symbol': 'GAEL',
          'trades': 2,
          'qty_closed': 20.0,
          'buy_value': 2000.0,
          'sell_value': 3000.0,
          'gross_pnl': 1000.0,
          'dp_charges_estimated': 15.93,
          'charges_estimated': 65.93,
          'net_pnl_estimated': 934.07,
          'net_pnl_pct_estimated': 46.7,
          'unmatched_sell_qty': 0.0,
          'still_open_qty': 5.0,
          'first_buy': '2024-01-01',
          'last_sell': '2024-06-01',
          'lots': [_lot(), _lot(sellDate: '2024-05-01')],
        },
      ],
  'totals':
      totals ??
      {
        'symbols_closed': 1,
        'trades': 2,
        'buy_value': 2000.0,
        'sell_value': 3000.0,
        'gross_pnl': 1000.0,
        'charges_estimated': 65.93,
        'net_pnl_estimated': 934.07,
        'net_pnl_pct_estimated': 46.7,
        'short_term_net': 934.07,
        'long_term_net': 0.0,
        'wins': 2,
        'losses': 0,
        'win_rate_pct': 100.0,
        'unmatched_sell_qty': 0.0,
      },
  'tax_indicative': {
    'short_term_gain': 934.07,
    'long_term_gain': 0.0,
    'ltcg_exemption_applied': 0.0,
    'tax': 186.81,
    'basis': 'Statutory rates on this ledger only. Not a tax computation.',
  },
  'charges_basis': {
    'note': 'Estimated from the statutory delivery rate card.',
    'dp_charge_per_sell_day': 15.93,
  },
};

void main() {
  group('ClosedBook parsing', () {
    test('reads the totals, the tax line and both bases', () {
      final b = ClosedBook.fromJson(_payload());
      expect(b.trades, 2);
      expect(b.netPnlEstimated, 934.07);
      expect(b.grossPnl, 1000.0);
      expect(b.chargesEstimated, 65.93);
      expect(b.taxIndicative, 186.81);
      expect(b.winRatePct, 100.0);
      expect(b.chargesNote, contains('Estimated'));
      expect(b.taxBasis, contains('Not a tax computation'));
      expect(b.isEmpty, isFalse);
    });

    test('a null payload is an empty book, not a crash', () {
      final b = ClosedBook.fromJson(null);
      expect(b.isEmpty, isTrue);
      expect(b.trades, 0);
      expect(b.netPnlEstimated, isNull);
      expect(b.symbols, isEmpty);
    });

    test('a missing figure stays null and is never read as zero', () {
      final b = ClosedBook.fromJson({
        'symbols': [],
        'totals': {'trades': 0, 'net_pnl_estimated': null},
      });
      expect(b.netPnlEstimated, isNull);
      expect(b.grossPnl, isNull);
      expect(b.winRatePct, isNull);
    });

    test('a non-finite or junk number is rejected rather than propagated', () {
      expect(closedNumber('not a number'), isNull);
      expect(closedNumber(double.infinity), isNull);
      expect(closedNumber(double.nan), isNull);
      expect(closedNumber('12.5'), 12.5);
      expect(closedNumber(7), 7.0);
    });

    test('empty and literal-null strings do not become text', () {
      expect(closedText(''), isNull);
      expect(closedText('null'), isNull);
      expect(closedText('  '), isNull);
      expect(closedText(' GAEL '), 'GAEL');
    });

    test('lots parse with their term and holding period', () {
      final b = ClosedBook.fromJson(_payload());
      final lots = b.symbols.single.lots;
      expect(lots, hasLength(2));
      expect(lots.first.daysHeld, 152);
      expect(lots.first.isLongTerm, isFalse);
      expect(lots.first.netPnlEstimated, 475.0);
    });

    test('a long-term lot is flagged as such', () {
      final b = ClosedBook.fromJson(
        _payload(
          symbols: [
            {
              'symbol': 'ITC',
              'trades': 1,
              'qty_closed': 10.0,
              'lots': [_lot(symbol: 'ITC', days: 500, term: 'long')],
            },
          ],
        ),
      );
      expect(b.symbols.single.lots.single.isLongTerm, isTrue);
    });
  });

  group('ClosedBook derived views', () {
    test('symbols rank worst-first, because a closed book is reviewed', () {
      final b = ClosedBook.fromJson(
        _payload(
          symbols: [
            {'symbol': 'WIN', 'trades': 1, 'net_pnl_estimated': 900.0, 'lots': []},
            {'symbol': 'LOSS', 'trades': 1, 'net_pnl_estimated': -400.0, 'lots': []},
            {'symbol': 'FLAT', 'trades': 1, 'net_pnl_estimated': 0.0, 'lots': []},
          ],
        ),
      );
      expect(b.ranked.map((s) => s.symbol), ['LOSS', 'FLAT', 'WIN']);
    });

    test('recent lots come back newest sale first', () {
      final b = ClosedBook.fromJson(_payload());
      expect(b.recentLots.first.sellDate, '2024-06-01');
      expect(b.recentLots.last.sellDate, '2024-05-01');
    });

    test('average prices divide value by the quantity actually closed', () {
      final s = ClosedSymbol.fromJson({
        'symbol': 'GAEL',
        'trades': 2,
        'qty_closed': 20.0,
        'buy_value': 2000.0,
        'sell_value': 3000.0,
        'lots': [],
      });
      expect(s.avgBuyPrice, 100.0);
      expect(s.avgSellPrice, 150.0);
    });

    test('average price is unknown when nothing was closed', () {
      final s = ClosedSymbol.fromJson({'symbol': 'X', 'qty_closed': 0.0});
      expect(s.avgBuyPrice, isNull);
      expect(s.avgSellPrice, isNull);
    });

    test('an unmatched sell is surfaced, not silently dropped', () {
      final b = ClosedBook.fromJson(
        _payload(totals: {'trades': 1, 'unmatched_sell_qty': 12.0}),
      );
      expect(b.unmatchedSellQty, 12.0);
    });
  });
}
