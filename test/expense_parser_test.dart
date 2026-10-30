import 'dart:io';
import 'package:csv/csv.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/data/models/expense_config.dart';
import 'package:aiei_wealth/services/expense_import_service.dart';

/// Verifies the multi-table expense CSV parser against a synthetic CSV export
/// (test/fixtures/expense_sample_2026.csv, made-up numbers).
void main() {
  tearDown(() => ExpenseConfig.current = const ExpenseConfig());

  test('parses a five-section CSV sheet correctly', () {
    ExpenseConfig.current = const ExpenseConfig(scrips: ['AAA', 'BBB', 'CCC']);
    final content = File('test/fixtures/expense_sample_2026.csv').readAsStringSync();
    final rows = csv.decode(content);
    final svc = ExpenseImportService();
    final d = svc.parseRows(rows, fallbackYear: 2026);

    expect(d['year'], 2026);

    // ── Local ledger — totals summed from months after recompute ──
    final local = d['local'] as Map;
    final tMonths = local['months'] as List;
    expect(tMonths.length, 12, reason: 'Jan..Dec');
    double sumField(List ms, String k) =>
        ms.fold(0.0, (a, m) => a + (((m as Map)[k] as num?)?.toDouble() ?? 0));
    expect(sumField(tMonths, 'salary'), 600000);
    expect(sumField(tMonths, 'total_income'), 621620);
    expect(sumField(tMonths, 'actual_expense'), 378800);
    expect(sumField(tMonths, 'transfer'), 55000);
    final jan = tMonths.first as Map;
    expect(jan['month'], 'jan');
    expect(jan['salary'], 50000);
    expect(jan['rent'], 12000);
    // The sheet's TOTAL row is kept as the section totals.
    expect((local['totals'] as Map)['salary'], 600000);

    // ── Account A (INR) ──
    final accountA = d['account_a'] as Map;
    final accountAMonths = accountA['months'] as List;
    expect(accountAMonths.length, 12);
    final aJan = accountAMonths.first as Map;
    expect(aJan['opening'], 200000);
    expect(aJan['family'], 2000);
    expect(aJan['mutual'], 10000);
    // last month with a real balance
    expect(_last(accountAMonths, 'balance'), 132000);

    // ── Account B (INR) ──
    final accountB = d['account_b'] as Map;
    final accountBMonths = accountB['months'] as List;
    final april = accountBMonths.firstWhere((m) => (m as Map)['month'] == 'apr') as Map;
    expect(april['inr_received'], 20000);
    expect(april['stock'], 15000);
    final june = accountBMonths.firstWhere((m) => (m as Map)['month'] == 'jun') as Map;
    expect(june['food'], 500);

    // ── Investments ──
    final inv = d['investments'] as Map;
    final invMonths = inv['months'] as List;
    final invTotalMutual = invMonths.fold<double>(
        0, (a, m) => a + ((m as Map)['mutual'] as num).toDouble());
    // previous-year carry (3,000) + Jan..Jun 10,000 each
    expect(invTotalMutual, 63000);
    final invJan = invMonths.firstWhere((m) => (m as Map)['month'] == 'jan') as Map;
    expect(invJan['total'], 10000, reason: 'allocation sum, Mutual not double-counted');
    expect(invJan['bank_balance'], 500);

    // ── Stocks ──
    final stocks = d['stocks'] as Map;
    final trades = stocks['trades'] as List;
    expect(trades.length, 3);
    final byStock = stocks['by_stock'] as Map;
    // AAA bought twice: 6,000 + 5,000
    expect((byStock['AAA'] as num).toDouble(), closeTo(11000, 0.01));
    expect(byStock.containsKey('CCC'), true);
  });
}

double _last(List months, String key) {
  for (var i = months.length - 1; i >= 0; i--) {
    final v = ((months[i] as Map)[key] as num?)?.toDouble() ?? 0;
    if (v != 0) return v;
  }
  return 0;
}
