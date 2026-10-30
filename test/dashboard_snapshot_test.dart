import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/data/models/dashboard_snapshot.dart';
import 'package:aiei_wealth/data/models/expense_schema.dart';

void main() {
  test('incoming-only month carries its closing balance forward', () {
    final data = ExpenseSchema.blankYear(2026);
    final months = (data['local'] as Map)['months'] as List;
    months[0]['incoming_transfer'] = 1500.0;
    months[1]['opening'] = 9000.0;
    ExpenseSchema.recompute(data);
    final result = (data['local'] as Map)['months'] as List;
    expect(result[0]['balance'], 1500);
    expect(result[1]['opening'], 1500);
    expect(result[0]['total_income'], 0);
    expect(result[0]['actual_expense'], 0);
  });
  test('missing price prevents a fabricated total and loss', () {
    final m = DashboardSnapshot(equity: {'holdings': [
      {'invested': 1000, 'total_value': null}
    ]}, funds: {'funds': []});
    expect(m.value, isNull);
    expect(m.pnl, isNull);
    expect(m.invested, 1000);
  });
  test('totals sum holdings and other assets without inventing a cost', () {
    final m = DashboardSnapshot(equity: {'holdings': [
      {'invested': 1000, 'total_value': 1200, 'day_change_value': -20}
    ]}, funds: {'funds': [{'invested': 500, 'current_value': 600}]},
      other: {'Cash': 100});
    expect(m.value, 1900);
    expect(m.invested, 1500);
    expect(m.pnl, 300);
    expect(m.absoluteReturn, 20);
    expect(m.equityDayChange, -20);
    expect(m.categoryValues['Unclassified'], 1800);
  });
  test('classification never assumes all stocks or index funds are large cap', () {
    expect(dashboardCategory('Nasdaq 100 Index'), 'International');
    expect(dashboardCategory('Small Cap Index'), 'Small Cap');
    expect(dashboardCategory('Large & Mid Cap'), 'Mixed equity');
    expect(dashboardCategory('Silver'), 'Silver');
    expect(dashboardCategory('Unknown'), 'Unclassified');
  });
  test('invalid target sum suppresses drift recommendation', () {
    final m = DashboardSnapshot(targets: {'Large Cap': 80, 'Gold': 80});
    expect(m.validTargets, isFalse);
    expect(m.drift('Gold'), isNull);
  });
  test('missing, future and offline timestamps are not fresh', () {
    final now = DateTime.utc(2026, 9, 7, 12);
    expect(dashboardFresh({'last_updated': '2026-09-07T11:58:00Z'}, now), isTrue);
    expect(dashboardFresh({'last_updated': '2026-09-07T11:58:00Z', 'offline': true}, now), isFalse);
    expect(dashboardFresh({'last_updated': '2026-09-07T13:00:00Z'}, now), isFalse);
    expect(dashboardFresh({}, now), isFalse);
  });
  test('transfers excluded from income, expenses, savings and top spending', () {
    final data = ExpenseSchema.blankYear(2026);
    final sec = data['local'] as Map;
    final row = (sec['months'] as List).first as Map;
    row.addAll(<String, dynamic>{'opening': 1000, 'salary': 10000, 'food': 2000,
      'transfer': 4000, 'incoming_transfer': 1500});
    final m = DashboardExpense.fromYear(data, DateTime(2026, 1, 20));
    expect(m.report!.totalIncome, 10000);
    expect(m.report!.actualExpense, 2000);
    expect(m.report!.netSavings, 8000);
    expect(m.report!.closingBalance, 6500);
    expect(m.topCategories.map((c) => c.key), ['food']);
    expect(row['balance'], isNot(6500)); // dashboard did not mutate source.
  });
  test('blank month is not presented as recorded zero spending', () {
    final m = DashboardExpense.fromYear(ExpenseSchema.blankYear(2026), DateTime(2026, 9, 7));
    expect(m.report!.filled, isFalse);
  });
}
