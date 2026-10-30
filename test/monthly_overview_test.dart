import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/services/expense_import_service.dart';
import 'package:aiei_wealth/data/models/expense_analytics.dart';
import 'package:aiei_wealth/data/models/expense_schema.dart';

/// Verifies the Monthly Expense Overview analytics + source references against
/// a synthetic sheet (test/fixtures/expense_sample_2026.html, made-up numbers),
/// and the extra-category auto-detection against a sheet with a new category
/// column.
void main() {
  group('Monthly Overview (synthetic 2026 sheet)', () {
    late Map<String, dynamic> d;

    setUp(() {
      final content = File('test/fixtures/expense_sample_2026.html').readAsStringSync();
      d = ExpenseImportService()
          .parseContent(content, isHtml: true, fallbackYear: 2026);
    });

    test('Jan KPIs match the raw sheet', () {
      final r = ExpenseAnalytics.monthlyReport(d, 2026, 'jan');
      expect(r.openingBalance, 10000);
      expect(r.salary, 50000);
      expect(r.bonus, 0);
      expect(r.totalIncome, 50000);
      expect(r.totalOpening, 60000); // opening + income
      expect(r.totalExpense, 30800);
      expect(r.actualExpense, 30800); // transfer is 0 in Jan
      expect(r.transfer, 0);
      expect(r.closingBalance, 29200);
      expect(r.netSavings, 50000 - 30800);
      expect(r.filled, true);
      expect(r.future, false);
    });

    test('a transfer month separates actual expense from money moved', () {
      final r = ExpenseAnalytics.monthlyReport(d, 2026, 'mar');
      expect(r.openingBalance, 47200, reason: 'chained from Feb');
      expect(r.totalIncome, 70000, reason: 'salary + bonus');
      expect(r.transfer, 30000);
      expect(r.totalExpense, 60800);
      expect(r.actualExpense, 30800);
      expect(r.closingBalance, 56400);
    });

    test('category breakdown carries amount, shares and status', () {
      final r = ExpenseAnalytics.monthlyReport(d, 2026, 'jan');
      final food = r.categories.firstWhere((c) => c.label == 'Food');
      expect(food.amount, 6000);
      expect(food.pctOfTotal, closeTo(6000 / 30800 * 100, 0.01));
      expect(food.pctOfActual, closeTo(6000 / 30800 * 100, 0.01));
      expect(['Normal', 'High', 'Low', 'Not Available'].contains(food.status),
          true);
      // Rent (12,000) is the biggest Jan category → sorted first.
      expect(r.categories.first.label, 'Rent');
      expect(r.categories.firstWhere((c) => c.label == 'Credit Card').amount, 7000);
    });

    test('source reference resolves to the real cell', () {
      final ref = ExpenseAnalytics.localRef(d, 2026, 'jan', 'salary');
      expect(ref.isDerived, false);
      expect(ref.sheet, '2026');
      expect(ref.section, 'Local Monthly Expense');
      expect(ref.column.toLowerCase(), 'salary');
      expect(ref.originalValue, '50,000', reason: 'raw cell text is kept');
      expect(ref.normalizedValue, 0);
      expect(ref.accountType, 'Local Expense');
      expect(ref.currency, 'LCY');
      // Header is sheet row 1, Jan is row 2.
      expect(ref.row, 2);
      expect(ref.cellAddress, 'C2'); // col C = Salary (0=Month,1=Opening,2=Salary)
    });

    test('insights are generated', () {
      final r = ExpenseAnalytics.monthlyReport(d, 2026, 'jan');
      expect(r.insights, isNotEmpty);
      expect(r.insights.any((s) => s.contains('Highest spending')), true);
    });
  });

  test('Overview money-flow formulas match the spec acceptance values', () {
    // A synthetic year with round numbers, so every ratio is checkable by hand.
    final d = ExpenseSchema.blankYear(2025);
    final months = ((d['local'] as Map)['months'] as List).cast<Map>();
    months.firstWhere((m) => m['month'] == 'jan')
      ..['opening'] = 20000
      ..['salary'] = 300000
      ..['bonus'] = 50000
      ..['reimburse'] = 40000
      ..['interest'] = 10000
      // actual living expense 120,000 split across a couple of categories
      ..['rent'] = 80000
      ..['food'] = 40000
      ..['transfer'] = 60000;
    ExpenseSchema.recompute(d);

    final k = ExpenseAnalytics.localKpis(d);
    final opening = k.opening;
    final income = k.income;
    final actual = k.actualExpense;
    final transfer = k.transfer;
    final totalIncl = actual + transfer;
    final savings = income - actual;
    final availBefore = opening + income - actual;
    final closing = opening + income - totalIncl;
    final growth = closing - opening;

    expect(opening, 20000);
    expect(k.salary, 300000);
    expect(k.bonus, 50000);
    expect(k.reimburse, 40000);
    expect(k.interest, 10000);
    expect(income, 400000);
    expect(actual, 120000);
    expect(transfer, 60000);
    expect(totalIncl, 180000);
    expect(savings, 280000);
    expect(availBefore, 300000);
    expect(closing, 240000);
    expect(growth, 220000);
    expect((savings / income * 100), closeTo(70.0, 0.05));
    expect((actual / income * 100), closeTo(30.0, 0.05));
    expect((transfer / income * 100), closeTo(15.0, 0.05));
    expect((totalIncl / income * 100), closeTo(45.0, 0.05));
  });

  test('extra category column is auto-detected and summed', () {
    // A ledger sheet with a brand-new "Insurance" category the code never
    // hard-coded. It must flow into Total Expense and the category list.
    final grid = [
      ['Month', 'Opening Balance', 'Salary', 'Rent', 'Food', 'Insurance'],
      ['Jan', '1000', '5000', '800', '400', '300'],
    ];
    final d = ExpenseImportService().parseRows(grid, fallbackYear: 2027);
    final r = ExpenseAnalytics.monthlyReport(d, 2027, 'jan');
    // total expense = rent 800 + food 400 + insurance 300 = 1500
    expect(r.totalExpense, 1500);
    final ins = r.categories.firstWhere((c) => c.label == 'Insurance');
    expect(ins.amount, 300);
    // and it carries a source reference to its own cell
    expect(ins.ref!.isDerived, false);
    expect(ins.ref!.originalValue, '300');
    // extra key is recorded on the section
    expect(ExpenseSchema.extraCategoryKeys(d['local'] as Map), contains('x_insurance'));
  });
}
