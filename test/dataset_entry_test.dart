import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/data/models/expense_config.dart';
import 'package:aiei_wealth/data/models/expense_schema.dart';
import 'package:aiei_wealth/data/models/expense_analytics.dart';
import 'package:aiei_wealth/data/models/expense_history.dart';

/// Verifies the Raw Dataset Entry logic that is pure (no Hive/Drive):
/// dynamic income/transfer fields feed the right totals, soft-delete excludes
/// stock trades, and the validation engine classifies errors vs warnings.
void main() {
  Map<String, dynamic> yearWith(Map<String, dynamic> janOverrides,
      {List<Map<String, dynamic>>? extraDefs}) {
    final d = ExpenseSchema.blankYear(2027);
    final ledger = d['local'] as Map;
    if (extraDefs != null) ledger['extra_categories'] = extraDefs;
    final months = (ledger['months'] as List).cast<Map>();
    final jan = months.firstWhere((m) => m['month'] == 'jan');
    janOverrides.forEach((k, v) => jan[k] = v);
    ExpenseSchema.recompute(d);
    return d;
  }

  group('dynamic fields', () {
    test('extra INCOME field adds to Total Income', () {
      final d = yearWith(
        {'salary': 50000, 'rent': 8000, 'i_rental': 12000},
        extraDefs: [
          {'key': 'i_rental', 'label': 'Rental Income', 'kind': 'income'},
        ],
      );
      final r = ExpenseAnalytics.monthlyReport(d, 2027, 'jan');
      expect(r.totalIncome, 62000); // salary 50000 + rental 12000
      expect(r.totalExpense, 8000); // rent only
      // income field is NOT listed as a spend category
      expect(r.categories.any((c) => c.key == 'i_rental'), false);
    });

    test('extra TRANSFER field counts in expense but not actual expense', () {
      final d = yearWith(
        {'salary': 50000, 'rent': 8000, 'x_wire': 5000},
        extraDefs: [
          {'key': 'x_wire', 'label': 'Wire to Family', 'kind': 'transfer'},
        ],
      );
      final r = ExpenseAnalytics.monthlyReport(d, 2027, 'jan');
      expect(r.totalExpense, 13000); // rent 8000 + wire 5000
      expect(r.actualExpense, 8000); // wire excluded from actual (it's transfer)
      expect(r.transfer, 5000); // transfer_total picks up the extra transfer
    });

    test('extra EXPENSE category adds to Total Expense and actual', () {
      final d = yearWith(
        {'salary': 50000, 'rent': 8000, 'x_insurance': 3000},
        extraDefs: [
          {'key': 'x_insurance', 'label': 'Insurance', 'kind': 'expense'},
        ],
      );
      final r = ExpenseAnalytics.monthlyReport(d, 2027, 'jan');
      expect(r.totalExpense, 11000);
      expect(r.actualExpense, 11000);
      expect(r.categories.firstWhere((c) => c.key == 'x_insurance').amount, 3000);
    });
  });

  test('soft-deleted stock trade is excluded from deployed total', () {
    ExpenseConfig.current = const ExpenseConfig(scrips: ['AAA', 'BBB']);
    addTearDown(() => ExpenseConfig.current = const ExpenseConfig());
    final d = ExpenseSchema.blankYear(2027);
    final stocks = d['stocks'] as Map;
    stocks['trades'] = [
      {'date': '1/1', 'invested': 10000.0, 'charges': 0.0, 'scrips': {'AAA': 10000.0}},
      {'date': '2/1', 'invested': 5000.0, 'charges': 0.0, 'scrips': {'BBB': 5000.0}, '_deleted': true},
    ];
    ExpenseSchema.recompute(d);
    expect(ExpenseAnalytics.stockDeployed(d), 10000); // deleted 5000 excluded
    final byScrip = ExpenseAnalytics.byScrip(d);
    expect(byScrip.containsKey('BBB'), false); // deleted trade's scrip dropped
    expect(byScrip['AAA'], 10000);
  });

  group('validation', () {
    test('duplicate month is a blocking error', () {
      final d = ExpenseSchema.blankYear(2027);
      final months = (d['local'] as Map)['months'] as List;
      months.add({'month': 'jan', 'label': 'Jan (dup)', 'salary': 1000});
      ExpenseSchema.recompute(d);
      final issues = ExpenseValidation.validate(d, 2027);
      expect(ExpenseValidation.hasBlockingErrors(issues), true);
      expect(issues.any((i) => i.isError && i.message.contains('Duplicate')), true);
    });

    test('transfer > income and expense > income are warnings (not blocking)', () {
      final d = yearWith({'salary': 10000, 'rent': 25000, 'transfer': 15000});
      final issues = ExpenseValidation.validate(d, 2027);
      expect(ExpenseValidation.hasBlockingErrors(issues), false);
      expect(issues.any((i) => i.message.contains('transfer')), true);
      expect(issues.any((i) => i.message.contains('actual expense')), true);
      expect(issues.any((i) => i.message.contains('negative')), true);
    });

    test('clean data yields no blocking errors', () {
      final d = yearWith({'salary': 50000, 'rent': 8000, 'food': 4000});
      final issues = ExpenseValidation.validate(d, 2027);
      expect(ExpenseValidation.hasBlockingErrors(issues), false);
    });
  });

  group('opening-balance cascade', () {
    // recompute() replaces the section's month list, so always re-read from [d].
    List<Map> mrows(Map<String, dynamic> d, String sec) =>
        (((d[sec] as Map)['months']) as List).cast<Map>();
    void setCell(Map<String, dynamic> d, String sec, String mk, String k, num v) =>
        mrows(d, sec).firstWhere((m) => m['month'] == mk)[k] = v;
    num cell(Map<String, dynamic> d, String sec, String mk, String k) =>
        (mrows(d, sec).firstWhere((m) => m['month'] == mk)[k] as num?) ?? 0;

    test('editing an early month re-chains all later closing balances', () {
      final d = ExpenseSchema.blankYear(2027);
      setCell(d, 'local', 'jan', 'opening', 1000);
      setCell(d, 'local', 'jan', 'salary', 5000); // Jan balance = 6000
      ExpenseSchema.recompute(d); // first pass writes openings for all months
      expect(cell(d, 'local', 'dec', 'balance'), 6000);

      // Now EDIT July (the frozen-chain bug: this used to not cascade).
      setCell(d, 'local', 'jul', 'food', 2000);
      ExpenseSchema.recompute(d);
      expect(cell(d, 'local', 'jul', 'balance'), 4000);
      expect(cell(d, 'local', 'dec', 'balance'), 4000);

      // And raising Jan salary must ripple all the way to December.
      setCell(d, 'local', 'jan', 'salary', 9000);
      ExpenseSchema.recompute(d);
      expect(cell(d, 'local', 'dec', 'balance'), 8000); // +4000
    });

    test('explicit opening after a leading blank gap is preserved (Account B case)', () {
      final d = ExpenseSchema.blankYear(2027);
      // Jan/Feb blank, Mar has an explicit opening + a dividend.
      setCell(d, 'account_b', 'mar', 'opening', 5000);
      setCell(d, 'account_b', 'mar', 'dividend', 1000);
      ExpenseSchema.recompute(d);
      expect(cell(d, 'account_b', 'mar', 'opening'), 5000);
      expect(cell(d, 'account_b', 'mar', 'balance'), 6000);
      expect(cell(d, 'account_b', 'apr', 'opening'), 6000);
    });
  });

  test('ExpenseChange round-trips through JSON', () {
    const c = ExpenseChange(
      changeId: 'CHG-20260704-001',
      timestamp: '2026-07-04 20:30',
      action: 'edit',
      sourceSheet: '2026',
      sourceSection: 'Local Monthly Expense',
      year: 2026,
      month: 'Jul 2026',
      sourceRow: 10,
      sourceColumn: 'Food',
      sourceCellAddress: 'J10',
      oldValue: 0,
      newValue: 12500,
      currency: 'LCY',
      note: 'Updated July food expense',
      saveStatus: 'saved',
      driveUploadStatus: 'success',
    );
    final back = ExpenseChange.fromJson(c.toJson());
    expect(back.changeId, 'CHG-20260704-001');
    expect(back.sourceCellAddress, 'J10');
    expect(back.newValue, 12500);
    expect(back.driveUploadStatus, 'success');
  });
}
