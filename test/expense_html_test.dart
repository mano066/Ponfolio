import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/data/models/expense_config.dart';
import 'package:aiei_wealth/data/models/expense_schema.dart';
import 'package:aiei_wealth/services/expense_import_service.dart';

/// Verifies the header-name-based parser against synthetic Google Sheets HTML
/// exports in test/fixtures (made-up numbers, the same table layout as a real
/// export: one sheet stacking the local ledger, Account A, Account B, the
/// investment tracker and the stock log).
void main() {
  final svc = ExpenseImportService();

  Map<String, dynamic> parse(String name, int year) => svc.parseContent(
      File('test/fixtures/$name').readAsStringSync(),
      isHtml: true,
      fallbackYear: year);

  int rows(Map d, String sec, [String key = 'months']) {
    final s = d[sec];
    return s is Map && s[key] is List ? (s[key] as List).length : 0;
  }

  double sum(Map d, String sec, String field) {
    final s = d[sec];
    if (s is! Map || s['months'] is! List) return 0;
    return (s['months'] as List).fold(0.0,
        (a, m) => a + ((m as Map)[field] as num? ?? 0).toDouble());
  }

  Map month(Map d, String sec, String m) =>
      (d[sec]['months'] as List).firstWhere((r) => (r as Map)['month'] == m) as Map;

  tearDown(() => ExpenseConfig.current = const ExpenseConfig());

  test('ledger-only sheet: no interest column, Jul-Dec', () {
    final d = parse('expense_sample_2024.html', 2024);
    expect(d['year'], 2024);
    expect(rows(d, 'local'), 6); // Jul..Dec
    expect(rows(d, 'account_a'), 0);
    expect(rows(d, 'stocks', 'trades'), 0);
    expect(sum(d, 'local', 'salary'), 240000);
    // interest column absent → all zero, must not throw
    expect(sum(d, 'local', 'interest'), 0);
    final jul = (d['local']['months'] as List).first as Map;
    expect(jul['month'], 'jul');
    expect(jul['opening'], 8000);
    // 6 × (40,000 − 15,000) on top of the opening
    expect(month(d, 'local', 'dec')['balance'], 158000);
  });

  test('all five sections are found and recomputed', () {
    ExpenseConfig.current = const ExpenseConfig(scrips: ['AAA', 'BBB', 'CCC']);
    final d = parse('expense_sample_2026.html', 2026);
    expect(d['year'], 2026, reason: 'detected from the trade dates');
    expect(rows(d, 'local'), 12);
    expect(rows(d, 'account_a'), 12);
    expect(rows(d, 'account_b'), 12);
    expect(rows(d, 'investments'), 7, reason: 'carry row + Jan..Jun');
    expect(rows(d, 'stocks', 'trades'), 3, reason: 'the undated totals row is skipped');

    // Local ledger chains its opening from the previous month's balance.
    expect(month(d, 'local', 'jan')['opening'], 10000);
    expect(month(d, 'local', 'mar')['opening'], 47200);
    expect(month(d, 'local', 'mar')['actual_expense'], 30800, reason: 'transfer excluded');
    expect(month(d, 'local', 'dec')['balance'], 197820);

    // Account A: after = opening + INR received + interest − GST.
    final aMar = month(d, 'account_a', 'mar');
    expect(aMar['local_amount'], 30000);
    expect(aMar['inr_received'], 81000);
    expect((aMar['after'] as num).toDouble(), closeTo(248850, 0.01));
    expect((aMar['balance'] as num).toDouble(), closeTo(232800, 0.01));
    expect(month(d, 'account_a', 'apr')['transfer_b'], 20000);

    // Account B: blank Jan/Feb, explicit opening in Mar, last balance 11,000.
    expect(month(d, 'account_b', 'mar')['opening'], 5000);
    expect(month(d, 'account_b', 'apr')['stock'], 15000);
    expect(month(d, 'account_b', 'dec')['balance'], 11000);

    // Stocks: per-scrip totals rebuilt by recompute.
    final bs = d['stocks']['by_stock'] as Map;
    expect(bs, {'AAA': 11000.0, 'BBB': 7000.0, 'CCC': 5000.0});
    final deployed = bs.values.fold<double>(0, (a, v) => a + (v as num).toDouble());
    expect(deployed, 23000);
    expect((d['stocks']['trades'] as List).first['charges'], 20);
  });

  test('without configured scrips the stock log still parses, with no per-scrip split', () {
    final d = parse('expense_sample_2026.html', 2026);
    expect(ExpenseSchema.scrips, isEmpty);
    expect(rows(d, 'stocks', 'trades'), 3);
    expect(d['stocks']['by_stock'], isEmpty);
  });

  test('configured header aliases map a workbook\'s own column names', () {
    final grid = [
      ['Month', 'Transfer date', 'Remit', 'INR Received', 'Open balance', 'Sis', 'Total Balance'],
      ['Jan', '', '1,000', '2,500', '100', '400', ''],
    ];
    final plain = svc.parseRows(grid, fallbackYear: 2026);
    final a0 = (plain['account_a']['months'] as List).first as Map;
    expect(a0['local_amount'], 0, reason: 'unknown header without config');
    expect(a0['family'], 0);

    ExpenseConfig.current = ExpenseConfig.fromJson({
      'header_aliases': {
        'account_a': {
          'local_amount': ['remit'],
          'family': ['sis'],
        },
      },
    });
    final d = svc.parseRows(grid, fallbackYear: 2026);
    final a = (d['account_a']['months'] as List).first as Map;
    expect(a['local_amount'], 1000);
    expect(a['family'], 400);
    expect(a['balance'], 100 + 2500 - 400);
  });
}
