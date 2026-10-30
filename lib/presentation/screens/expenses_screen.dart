import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/expense_analytics.dart';
import 'package:aiei_wealth/providers/expense_provider.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/presentation/screens/expenses_common.dart';
import 'package:aiei_wealth/presentation/screens/expenses_pages.dart';
import 'package:aiei_wealth/presentation/screens/expenses_monthly.dart';
import 'package:aiei_wealth/presentation/screens/expenses_entry.dart';

/// ─── Personal Finance Dashboard ───
/// A multi-page analytics dashboard over the yearly expense workbook. Every
/// section (local-currency salary ledger, Account A/B, investments, stock log)
/// is imported without loss; this shell adds KPI cards, charts, category/income
/// analysis, transfer/exchange views and a data-audit page on top of the
/// existing editable spreadsheet grids. Filters: Year (+ All Years) and
/// Currency (local / INR / Mixed).

enum ExpensePage {
  overview('Overview', LucideIcons.layoutDashboard),
  monthly('Monthly Overview', LucideIcons.calendarRange),
  income('Income', LucideIcons.trendingUp),
  categories('Categories', LucideIcons.pieChart),
  transfer('Transfers & Accounts', LucideIcons.landmark),
  investments('Investments', LucideIcons.piggyBank),
  audit('Data Audit', LucideIcons.shieldCheck),
  entry('Data Entry', LucideIcons.filePlus2);

  final String label;
  final IconData icon;
  const ExpensePage(this.label, this.icon);
}

class ExpensesScreen extends ConsumerStatefulWidget {
  const ExpensesScreen({super.key});
  @override
  ConsumerState<ExpensesScreen> createState() => _ExpensesScreenState();
}

class _ExpensesScreenState extends ConsumerState<ExpensesScreen> {
  ExpensePage _page = ExpensePage.overview;
  CurrencyView _currency = CurrencyView.mixed;
  bool _allYears = false;

  @override
  Widget build(BuildContext context) {
    final st = ref.watch(expenseStoreProvider);
    final version = st.version;
    final notifier = ref.read(expenseStoreProvider.notifier);
    final year = ref.watch(selectedExpenseYearProvider);
    final data = notifier.viewFor(year);
    final hasData = notifier.hasData(year);

    // Concrete years with data (for All-Years aggregation/comparison).
    final concrete = notifier.years.where(notifier.hasData).toList();
    final overviewYears = _allYears && concrete.isNotEmpty ? concrete : [year];
    final dataByYear = {for (final y in overviewYears) y: notifier.viewFor(y)};

    final imported =
        ExpenseAnalytics.coverage(data).values.fold<int>(0, (a, b) => a + b);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _Toolbar(
            years: notifier.years,
            selected: year,
            allYears: _allYears,
            currency: _currency,
            importedRows: imported,
            onSelectYear: (y) {
              setState(() => _allYears = false);
              ref.read(selectedExpenseYearProvider.notifier).set(y);
            },
            onAllYears: () => setState(() => _allYears = true),
            onCurrency: (v) => setState(() => _currency = v),
            onAddYear: () {
              setState(() => _allYears = false);
              notifier.addFutureYear();
            },
            onDelete: hasData ? () => _confirmDelete(context, year) : null,
          ),
          const SizedBox(height: 10),
          _PageTabs(page: _page, onSelect: (p) => setState(() => _page = p)),
          const SizedBox(height: 12),
          Expanded(
            child: _body(
                context, notifier, year, data, overviewYears, dataByYear, version),
          ),
      ],
    );
  }

  Widget _body(
    BuildContext context,
    ExpenseStore notifier,
    int year,
    Map<String, dynamic> data,
    List<int> overviewYears,
    Map<int, Map<String, dynamic>> dataByYear,
    int version,
  ) {
    switch (_page) {
      case ExpensePage.overview:
        return OverviewPage(
          key: ValueKey('ov-$overviewYears-$_currency-$version'),
          years: overviewYears,
          dataByYear: dataByYear,
          currency: _currency,
        );
      case ExpensePage.entry:
        return const RawDatasetEntryPage(key: ValueKey('entry'));
      case ExpensePage.monthly:
        return MonthlyOverviewPage(
            key: ValueKey('mo-$year-$version'), data: data, year: year);
      case ExpensePage.income:
        return IncomePage(key: ValueKey('in-$year-$version'), data: data, year: year);
      case ExpensePage.categories:
        return CategoriesPage(key: ValueKey('cat-$year-$version'), data: data);
      case ExpensePage.transfer:
        return TransferPage(
            key: ValueKey('tr-$year-$version'),
            data: data,
            year: year,
            notifier: notifier);
      case ExpensePage.investments:
        return InvestmentsPage(
            key: ValueKey('inv-$year-$version'),
            data: data,
            year: year,
            notifier: notifier);
      case ExpensePage.audit:
        return AuditPage(key: ValueKey('au-$year-$version'), data: data, year: year);
    }
  }

  Future<void> _confirmDelete(BuildContext context, int year) async {
    final c = context.colors;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: c.bg2,
        title: Text('Clear $year data?', style: AppTextStyles.heading3(c.t1)),
        content: Text(
            'This removes all saved values for $year. Seeded years reload on next launch.',
            style: AppTextStyles.bodySmall(c.t2)),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: Text('Clear', style: TextStyle(color: c.dn))),
        ],
      ),
    );
    if (ok == true) {
      await ref.read(expenseStoreProvider.notifier).deleteYear(year);
    }
  }
}

// ══════════════════════════════════════════════════════════════════
//  TOOLBAR (title + filters)
// ══════════════════════════════════════════════════════════════════

class _Toolbar extends StatelessWidget {
  final List<int> years;
  final int selected;
  final bool allYears;
  final CurrencyView currency;
  final int importedRows;
  final ValueChanged<int> onSelectYear;
  final VoidCallback onAllYears;
  final ValueChanged<CurrencyView> onCurrency;
  final VoidCallback onAddYear;
  final VoidCallback? onDelete;
  const _Toolbar({
    required this.years,
    required this.selected,
    required this.allYears,
    required this.currency,
    required this.importedRows,
    required this.onSelectYear,
    required this.onAllYears,
    required this.onCurrency,
    required this.onAddYear,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return DenseCard(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      child: Wrap(
        crossAxisAlignment: WrapCrossAlignment.center,
        runSpacing: 8,
        spacing: 6,
        children: [
          Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(LucideIcons.receipt, size: 16, color: c.blue),
            const SizedBox(width: 8),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('Personal Finance Dashboard',
                    style: AppTextStyles.heading3(c.t1)),
                Text('Salary, spending and transfers',
                    style: AppTextStyles.captionXs(c.t3)),
              ],
            ),
          ]),
          const SizedBox(width: 12),
          ...years.map((y) => _Pill(
                text: '$y',
                active: !allYears && y == selected,
                color: c.blue,
                onTap: () => onSelectYear(y),
              )),
          _Pill(
            text: 'All Years',
            active: allYears,
            color: c.accent,
            onTap: onAllYears,
          ),
          const SizedBox(width: 8),
          _CurrencyToggle(currency: currency, onChanged: onCurrency),
          _CompletenessBadge(rows: importedRows),
          if (onDelete != null)
            HeaderButton(
              icon: Icon(LucideIcons.trash2, size: 14, color: c.dn),
              text: 'Clear',
              onTap: onDelete,
            ),
          HeaderButton(
            icon: const Icon(LucideIcons.calendarPlus,
                size: 14, color: Colors.white),
            text: 'Add Year',
            primary: true,
            onTap: onAddYear,
          ),
        ],
      ),
    );
  }
}

class _CompletenessBadge extends StatelessWidget {
  final int rows;
  const _CompletenessBadge({required this.rows});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final ok = rows > 0;
    final color = ok ? c.up : c.gold;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(ok ? LucideIcons.checkCircle2 : LucideIcons.alertCircle,
            size: 12, color: color),
        const SizedBox(width: 5),
        Text('$rows rows imported', style: AppTextStyles.captionXs(color)),
      ]),
    );
  }
}

class _CurrencyToggle extends StatelessWidget {
  final CurrencyView currency;
  final ValueChanged<CurrencyView> onChanged;
  const _CurrencyToggle({required this.currency, required this.onChanged});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      padding: const EdgeInsets.all(2),
      decoration: BoxDecoration(
        color: c.bg3,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: c.bd),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        for (final v in CurrencyView.values)
          GestureDetector(
            onTap: () => onChanged(v),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 140),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: currency == v ? c.blue.withValues(alpha: 0.15) : null,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(v.label,
                  style:
                      AppTextStyles.captionXs(currency == v ? c.blue : c.t3)),
            ),
          ),
      ]),
    );
  }
}

class _Pill extends StatelessWidget {
  final String text;
  final bool active;
  final Color color;
  final VoidCallback onTap;
  const _Pill({
    required this.text,
    required this.active,
    required this.color,
    required this.onTap,
  });
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: active ? color.withValues(alpha: 0.12) : c.bg3,
            borderRadius: BorderRadius.circular(8),
            border:
                Border.all(color: active ? color.withValues(alpha: 0.4) : c.bd),
          ),
          child: Text(text,
              style: AppTextStyles.monoBold(active ? color : c.t2)
                  .copyWith(fontSize: 12)),
        ),
      ),
    );
  }
}

// ══════════════════════════════════════════════════════════════════
//  PAGE TABS
// ══════════════════════════════════════════════════════════════════

class _PageTabs extends StatelessWidget {
  final ExpensePage page;
  final ValueChanged<ExpensePage> onSelect;
  const _PageTabs({required this.page, required this.onSelect});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 36,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.zero,
        children: [
          for (final p in ExpensePage.values) ...[
            _Tab(page: p, active: p == page, onTap: () => onSelect(p)),
            const SizedBox(width: 6),
          ],
        ],
      ),
    );
  }
}

class _Tab extends StatelessWidget {
  final ExpensePage page;
  final bool active;
  final VoidCallback onTap;
  const _Tab({required this.page, required this.active, required this.onTap});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: active ? c.blue.withValues(alpha: 0.12) : c.bg2,
            borderRadius: BorderRadius.circular(9),
            border:
                Border.all(color: active ? c.blue.withValues(alpha: 0.4) : c.bd),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(page.icon, size: 14, color: active ? c.blue : c.t3),
            const SizedBox(width: 6),
            Text(page.label,
                style: active
                    ? AppTextStyles.bodySmall(c.blue)
                        .copyWith(fontWeight: FontWeight.w700)
                    : AppTextStyles.bodySmall(c.t2)),
          ]),
        ),
      ),
    );
  }
}
