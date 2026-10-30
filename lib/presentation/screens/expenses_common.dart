import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/data/models/expense_config.dart';
import 'package:aiei_wealth/data/models/expense_schema.dart';
import 'package:aiei_wealth/data/models/expense_analytics.dart';
import 'package:aiei_wealth/providers/expense_provider.dart';
import 'package:aiei_wealth/presentation/widgets/editable_grid.dart';

/// Shared helpers for the Expense dashboard pages: per-section accent colors,
/// currency formatters and the editable-grid builders (so both the section
/// detail pages and the Raw Data page render the exact same tables).

// ── Section accents ──────────────────────────────────────────────
const kLocal = Color(0xFF5367FF);
const kAccountA = Color(0xFF00B386);
const kAccountB = Color(0xFFE0A82E);
const kInv = Color(0xFF8B5CF6);
const kStk = Color(0xFF00A8CC);

/// Currency filter for KPI/label emphasis.
enum CurrencyView { local, inr, mixed }

extension CurrencyViewX on CurrencyView {
  String get label => switch (this) {
        CurrencyView.local => ExpenseConfig.current.localCurrency,
        CurrencyView.inr => 'INR',
        CurrencyView.mixed => 'Mixed',
      };
}

// ── Money formatting ─────────────────────────────────────────────

/// A local-currency amount, formatted per the expense config.
String fmtLocal(double v) => ExpenseConfig.current.money(v);

String fmtLocalSigned(double v) => (v >= 0 ? '+' : '') + fmtLocal(v);

/// Short names used in captions and titles.
String get localLabel => ExpenseConfig.current.localLabel;
String get localCcy => ExpenseConfig.current.localCurrency;
String get accountALabel => ExpenseConfig.current.accountALabel;
String get accountBLabel => ExpenseConfig.current.accountBLabel;
String get accountAShort => ExpenseConfig.current.short('account_a');
String get accountBShort => ExpenseConfig.current.short('account_b');

// ── Editable-grid builders (one per section) ─────────────────────

List<Map<String, dynamic>> sectionMonths(Map<String, dynamic> d, String key) =>
    ExpenseAnalytics.section(d, key)['months'] is List
        ? (ExpenseAnalytics.section(d, key)['months'] as List)
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList()
        : <Map<String, dynamic>>[];

Widget localGrid(ExpenseStore notifier, int year, Map<String, dynamic> data) =>
    EditableGrid(
      icon: LucideIcons.wallet,
      accent: kLocal,
      title: '$localLabel Cashflow',
      subtitle: '$localCcy · salary vs living expenses',
      frozenLabel: 'MONTH',
      cols: ExpenseSchema.localCols(data),
      rows: ExpenseAnalytics.localRows(data),
      frozenText: (r, i) => ExpenseSchema.monthTitle('${r['month']}'),
      totalSkip: const {'opening', 'total_opening', 'balance'},
      onCommit: (i, k, v) => notifier.updateMonthCell(year, 'local', i, k, v),
    );

Widget accountAGrid(ExpenseStore notifier, int year, Map<String, dynamic> data) =>
    EditableGrid(
      icon: LucideIcons.landmark,
      accent: kAccountA,
      title: accountALabel,
      subtitle: 'INR · remittance in + outflows',
      frozenLabel: 'MONTH',
      cols: ExpenseSchema.accountA,
      rows: ExpenseAnalytics.accountARows(data),
      frozenText: (r, i) => ExpenseSchema.monthTitle('${r['month']}'),
      totalSkip: const {'opening', 'after', 'balance'},
      onCommit: (i, k, v) => notifier.updateMonthCell(year, 'account_a', i, k, v),
    );

Widget accountBGrid(ExpenseStore notifier, int year, Map<String, dynamic> data) =>
    EditableGrid(
      icon: LucideIcons.landmark,
      accent: kAccountB,
      title: accountBLabel,
      subtitle: 'INR · dividends/interest + outflows',
      frozenLabel: 'MONTH',
      cols: ExpenseSchema.accountB,
      rows: ExpenseAnalytics.accountBRows(data),
      frozenText: (r, i) => ExpenseSchema.monthTitle('${r['month']}'),
      totalSkip: const {'opening', 'after', 'balance'},
      onCommit: (i, k, v) => notifier.updateMonthCell(year, 'account_b', i, k, v),
    );

Widget investGrid(ExpenseStore notifier, int year, Map<String, dynamic> data) =>
    EditableGrid(
      icon: LucideIcons.piggyBank,
      accent: kInv,
      title: 'Investment Contributions',
      subtitle: 'INR · Mutual / Gold / Silver / Para / NASDAQ',
      frozenLabel: 'MONTH',
      cols: ExpenseSchema.investCols(data),
      rows: ExpenseAnalytics.investRows(data),
      frozenText: (r, i) => ExpenseSchema.monthTitle('${r['month']}'),
      totalSkip: const {'mutual'},
      onCommit: (i, k, v) =>
          notifier.updateMonthCell(year, 'investments', i, k, v),
    );

Widget stockGrid(ExpenseStore notifier, int year, Map<String, dynamic> data) =>
    EditableGrid(
      icon: LucideIcons.trendingUp,
      accent: kStk,
      title: 'Stock Trade Log',
      subtitle: 'INR · per-scrip buys with charges',
      frozenLabel: 'DATE',
      frozenWidth: 108,
      cols: ExpenseSchema.stockCols(),
      rows: ExpenseAnalytics.trades(data),
      frozenText: (r, i) => '${r['date'] ?? ''}',
      frozenEditable: true,
      onFrozenCommit: (i, v) => notifier.updateStockCell(year, i, 'date', v),
      totalSkip: const {'balance'},
      onCommit: (i, k, v) => notifier.updateStockCell(year, i, k, v),
      onAddRow: () => notifier.addStockRow(year),
      onDeleteRow: (i) => notifier.deleteStockRow(year, i),
    );

// ── Small read-only table primitive for analytic pages ───────────

/// A simple bordered row of label + value cells for compact stat tables.
class StatRow extends StatelessWidget {
  final String label;
  final String value;
  final Color? valueColor;
  final bool header;
  const StatRow(this.label, this.value,
      {super.key, this.valueColor, this.header = false});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: c.bd.withValues(alpha: 0.5))),
      ),
      child: Row(children: [
        Expanded(
          child: Text(label,
              style: header
                  ? Theme.of(context).textTheme.titleSmall
                  : Theme.of(context).textTheme.bodySmall),
        ),
        Text(value,
            style: TextStyle(
              fontFeatures: const [],
              fontWeight: header ? FontWeight.w700 : FontWeight.w600,
              color: valueColor ?? c.t1,
              fontSize: 12.5,
            )),
      ]),
    );
  }
}
