import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/expense_schema.dart';
import 'package:aiei_wealth/data/models/expense_analytics.dart';
import 'package:aiei_wealth/providers/expense_provider.dart';
import 'package:aiei_wealth/presentation/charts/expense_charts.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/presentation/screens/expenses_common.dart';
import 'package:aiei_wealth/presentation/screens/expenses_pages.dart' show ChartGrid;

/// ─── Monthly Expense Overview ───
/// A single-month deep dive over the local salary ledger: 15 KPI cards, a
/// category breakdown with per-category metrics & status, six charts (donut,
/// income-vs-expense, actual-vs-transfer, opening-vs-closing, month-over-month
/// and a cash-flow waterfall), auto-generated insights, the raw Excel row plus
/// a normalized view, and a source-reference table so every value traces back
/// to its origin cell. All values come from [ExpenseAnalytics.monthlyReport] —
/// nothing is hard-coded, so future months/categories flow through unchanged.

List<Color> _palette(BuildContext c) {
  final s = c.colors;
  return [
    s.blue, s.up, s.dn, s.gold, s.accent, s.cyan,
    s.blue.withValues(alpha: 0.6), s.up.withValues(alpha: 0.6),
    s.dn.withValues(alpha: 0.6), s.gold.withValues(alpha: 0.6),
    s.accent.withValues(alpha: 0.6), s.cyan.withValues(alpha: 0.6),
  ];
}

class MonthlyOverviewPage extends ConsumerWidget {
  final Map<String, dynamic> data;
  final int year;
  const MonthlyOverviewPage(
      {super.key, required this.data, required this.year});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final monthKey = ref.watch(selectedExpenseMonthProvider);
    final report = ExpenseAnalytics.monthlyReport(data, year, monthKey);
    final points = ExpenseAnalytics.localPoints(data, year);

    return ListView(padding: EdgeInsets.zero, children: [
      _MonthSelector(
        year: year,
        selected: monthKey,
        points: points,
        onSelect: (m) =>
            ref.read(selectedExpenseMonthProvider.notifier).set(m),
      ),
      const SizedBox(height: 12),
      if (report.future)
        DenseCard(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
          child: Row(children: [
            Icon(LucideIcons.calendarClock, size: 18, color: c.gold),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                '${report.monthLabel} has no data yet — future or not-yet-filled '
                'month. Add values in the $localLabel grid (Raw Data) and this page '
                'updates automatically.',
                style: AppTextStyles.bodySmall(c.t2),
              ),
            ),
          ]),
        ),
      _kpiGrid(context, report),
      const SizedBox(height: 12),
      _MonthlyBreakdown(report: report),
      const SizedBox(height: 12),
      _charts(context, report, points),
      const SizedBox(height: 12),
      _AnalysisSection(report: report),
      const SizedBox(height: 12),
      _MonthlyTable(data: data, report: report),
      const SizedBox(height: 12),
      _ReferenceSection(data: data, year: year, report: report),
      const SizedBox(height: 24),
    ]);
  }

  // ── 15 KPI cards ────────────────────────────────────────────────
  Widget _kpiGrid(BuildContext context, MonthlyReport r) {
    final c = context.colors;
    Color rateColor(double v) => v >= 30 ? c.up : (v >= 0 ? c.gold : c.dn);
    return KpiGrid(cells: [
      Kpi('OPENING BALANCE', fmtLocal(r.openingBalance), '$localCcy · start', c.t2),
      Kpi('SALARY', fmtLocal(r.salary), localCcy, c.blue),
      Kpi('BONUS', fmtLocal(r.bonus), localCcy, c.blue),
      Kpi('REIMBURSEMENT', fmtLocal(r.reimburse), localCcy, c.blue),
      Kpi('INTEREST', fmtLocal(r.interest), r.hasInterest ? localCcy : 'none', c.blue),
      Kpi('TOTAL INCOME', fmtLocal(r.totalIncome), 'salary+bonus+reimb+int', c.blue),
      Kpi('TOTAL OPENING', fmtLocal(r.totalOpening), 'opening+income', c.cyan),
      Kpi('TOTAL EXPENSE', fmtLocal(r.totalExpense), 'incl. transfer', c.dn),
      Kpi('ACTUAL EXPENSE', fmtLocal(r.actualExpense), 'without transfer', c.dn),
      Kpi('TRANSFER', fmtLocal(r.transfer), 'to $accountAShort', c.gold),
      Kpi('CLOSING BALANCE', fmtLocal(r.closingBalance), '$localCcy · end',
          r.closingBalance >= 0 ? c.cyan : c.dn),
      Kpi('NET SAVINGS', fmtLocalSigned(r.netSavings), 'income−actual',
          context.pnlColor(r.netSavings)),
      Kpi('SAVINGS RATE', '${r.savingsRate.toStringAsFixed(1)}%', 'of income',
          rateColor(r.savingsRate)),
      Kpi('EXPENSE RATIO', '${r.expenseRatio.toStringAsFixed(1)}%', 'of income',
          c.dn),
      Kpi('TRANSFER RATIO', '${r.transferRatio.toStringAsFixed(1)}%',
          'of income', c.gold),
    ]);
  }

  // ── 6 charts ────────────────────────────────────────────────────
  Widget _charts(
      BuildContext context, MonthlyReport r, List<MonthPoint> pts) {
    final c = context.colors;
    final ml = r.monthKey.substring(0, 3).toUpperCase();

    // Donut: expense categories (ex-transfer) with a positive amount.
    final donut = {
      for (final cat in r.categories)
        if (cat.key != 'transfer' && cat.amount > 0) cat.label: cat.amount
    };

    // Month-over-month: income vs actual across all 12 months.
    final labels = [for (final p in pts) p.month.substring(0, 3).toUpperCase()];
    final momIncome = [for (final p in pts) p.income];
    final momActual = [for (final p in pts) p.actual];

    return ChartGrid([
      ChartCard(
        title: 'Expense by Category',
        subtitle: '$localCcy · ${r.monthLabel} · ex-transfer',
        child: DonutChart(data: donut, palette: _palette(context)),
      ),
      ChartCard(
        title: 'Income vs Expense',
        subtitle: '$localCcy · $ml',
        child: GroupedBarChart(
          labels: [ml],
          seriesA: [r.totalIncome],
          seriesB: [r.totalExpense],
          colorA: c.blue,
          colorB: c.dn,
          nameA: 'Income',
          nameB: 'Expense',
        ),
      ),
      ChartCard(
        title: 'Actual Expense vs Transfer',
        subtitle: '$localCcy · $ml',
        child: GroupedBarChart(
          labels: [ml],
          seriesA: [r.actualExpense],
          seriesB: [r.transfer],
          colorA: c.dn,
          colorB: c.gold,
          nameA: 'Actual',
          nameB: 'Transfer',
        ),
      ),
      ChartCard(
        title: 'Opening vs Closing Balance',
        subtitle: '$localCcy · $ml',
        child: GroupedBarChart(
          labels: [ml],
          seriesA: [r.openingBalance],
          seriesB: [r.closingBalance],
          colorA: c.t2,
          colorB: c.cyan,
          nameA: 'Opening',
          nameB: 'Closing',
        ),
      ),
      ChartCard(
        title: 'Month-over-Month',
        subtitle: '$localCcy · income vs actual expense',
        child: GroupedBarChart(
          labels: labels,
          seriesA: momIncome,
          seriesB: momActual,
          colorA: c.blue,
          colorB: c.dn,
          nameA: 'Income',
          nameB: 'Actual',
        ),
      ),
      ChartCard(
        title: 'Monthly Cash Flow',
        subtitle: 'Opening → Income → Expense → Transfer → Closing',
        child: WaterfallChart(steps: [
          WaterfallStep('Opening', r.openingBalance, c.t2, isTotal: true),
          WaterfallStep('Income', r.totalIncome, c.up),
          WaterfallStep('Expense', -r.actualExpense, c.dn),
          WaterfallStep('Transfer', -r.transfer, c.gold),
          WaterfallStep('Closing', r.closingBalance, c.cyan, isTotal: true),
        ]),
      ),
    ]);
  }
}

// ══════════════════════════════════════════════════════════════════
//  MONTH SELECTOR
// ══════════════════════════════════════════════════════════════════

class _MonthSelector extends StatelessWidget {
  final int year;
  final String selected;
  final List<MonthPoint> points;
  final ValueChanged<String> onSelect;
  const _MonthSelector({
    required this.year,
    required this.selected,
    required this.points,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final filled = {for (final p in points) p.month: p.filled};
    return DenseCard(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(LucideIcons.calendarRange, size: 16, color: c.blue),
            const SizedBox(width: 8),
            Text('Monthly Expense Overview',
                style: AppTextStyles.heading3(c.t1)),
            const SizedBox(width: 8),
            Text('$year · select a month',
                style: AppTextStyles.captionXs(c.t3)),
          ]),
          const SizedBox(height: 10),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final m in ExpenseSchema.months)
                _MonthPill(
                  label: ExpenseSchema.monthTitle(m),
                  active: m == selected,
                  hasData: filled[m] ?? false,
                  onTap: () => onSelect(m),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _MonthPill extends StatelessWidget {
  final String label;
  final bool active;
  final bool hasData;
  final VoidCallback onTap;
  const _MonthPill({
    required this.label,
    required this.active,
    required this.hasData,
    required this.onTap,
  });
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final col = active ? c.blue : (hasData ? c.t2 : c.t4);
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 140),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: active ? c.blue.withValues(alpha: 0.12) : c.bg3,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
                color: active ? c.blue.withValues(alpha: 0.4) : c.bd),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Container(
              width: 6,
              height: 6,
              margin: const EdgeInsets.only(right: 6),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: hasData ? c.up : c.bd,
              ),
            ),
            Text(label,
                style: AppTextStyles.monoBold(col).copyWith(fontSize: 12)),
          ]),
        ),
      ),
    );
  }
}

// ══════════════════════════════════════════════════════════════════
//  MONTHLY BREAKDOWN TABLE
// ══════════════════════════════════════════════════════════════════

class _MonthlyBreakdown extends StatelessWidget {
  final MonthlyReport report;
  const _MonthlyBreakdown({required this.report});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    const cols = [
      DenseCol('Category', 5, numeric: false),
      DenseCol('Amount', 4),
      DenseCol('% Total', 3),
      DenseCol('% Actual', 3),
      DenseCol('Δ Prev', 4),
      DenseCol('Δ Avg', 4),
      DenseCol('Status', 3, numeric: false),
    ];
    final rows = <List<Widget>>[];
    for (final cat in report.categories) {
      rows.add([
        Text(cat.label,
            style: AppTextStyles.bodySmall(c.t1)
                .copyWith(fontWeight: FontWeight.w600),
            maxLines: 1,
            overflow: TextOverflow.ellipsis),
        denseNum(context, fmtLocal(cat.amount), c.t1),
        denseNum(context, '${cat.pctOfTotal.toStringAsFixed(1)}%', c.t3),
        denseNum(context, '${cat.pctOfActual.toStringAsFixed(1)}%', c.t3),
        denseNum(context, fmtLocalSigned(cat.diffPrev),
            cat.diffPrev == 0 ? c.t3 : context.pnlColor(-cat.diffPrev)),
        denseNum(context, fmtLocalSigned(cat.diffAvg),
            cat.diffAvg == 0 ? c.t3 : context.pnlColor(-cat.diffAvg)),
        Align(
            alignment: Alignment.centerLeft,
            child: _StatusChip(status: cat.status)),
      ]);
    }
    return DenseTable(
      icon: LucideIcons.pieChart,
      accent: c.dn,
      title: 'Monthly Expense Breakdown',
      subtitle: '${report.monthLabel} · category-wise',
      cols: cols,
      rows: rows,
      footer: [
        denseFootLabel(context, 'Total Expense'),
        denseNum(context, fmtLocal(report.totalExpense), c.dn, bold: true),
        denseNum(context, '100%', c.t3),
        Text('actual ${fmtLocal(report.actualExpense)}',
            style: AppTextStyles.captionXs(c.t3), textAlign: TextAlign.right),
        const SizedBox.shrink(),
        const SizedBox.shrink(),
        const SizedBox.shrink(),
      ],
    );
  }
}

class _StatusChip extends StatelessWidget {
  final String status;
  const _StatusChip({required this.status});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final col = switch (status) {
      'High' => c.dn,
      'Low' => c.up,
      'Normal' => c.t2,
      _ => c.t4,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: col.withValues(alpha: 0.10),
        border: Border.all(color: col.withValues(alpha: 0.22)),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(status == 'Not Available' ? 'N/A' : status,
          style: AppTextStyles.labelXs(col)),
    );
  }
}

// ══════════════════════════════════════════════════════════════════
//  ANALYSIS / INSIGHTS
// ══════════════════════════════════════════════════════════════════

class _AnalysisSection extends StatelessWidget {
  final MonthlyReport report;
  const _AnalysisSection({required this.report});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return DenseCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(LucideIcons.sparkles, size: 15, color: c.accent),
            const SizedBox(width: 8),
            Text('Monthly Analysis', style: AppTextStyles.heading3(c.t1)),
          ]),
          const SizedBox(height: 10),
          for (final line in report.insights)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Icon(
                  line.contains('⚠')
                      ? LucideIcons.alertTriangle
                      : LucideIcons.checkCircle2,
                  size: 13,
                  color: line.contains('⚠') ? c.gold : c.up,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(line.replaceAll('⚠ ', ''),
                      style: AppTextStyles.bodySmall(c.t2)),
                ),
              ]),
            ),
        ],
      ),
    );
  }
}

// ══════════════════════════════════════════════════════════════════
//  MONTHLY TABLE (raw Excel row + normalized view)
// ══════════════════════════════════════════════════════════════════

class _MonthlyTable extends StatelessWidget {
  final Map<String, dynamic> data;
  final MonthlyReport report;
  const _MonthlyTable({required this.data, required this.report});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final raw = ExpenseAnalytics.rawLocalRow(data, report.monthKey);

    // Normalized clean-label view (field → formatted value).
    final normalized = <MapEntry<String, String>>[
      MapEntry('Opening Balance', fmtLocal(report.openingBalance)),
      MapEntry('Salary', fmtLocal(report.salary)),
      MapEntry('Bonus', fmtLocal(report.bonus)),
      MapEntry('Reimbursement', fmtLocal(report.reimburse)),
      MapEntry('Interest', fmtLocal(report.interest)),
      MapEntry('Total Income', fmtLocal(report.totalIncome)),
      MapEntry('Total Opening Balance', fmtLocal(report.totalOpening)),
      for (final cat in report.categories)
        MapEntry(cat.label, fmtLocal(cat.amount)),
      MapEntry('Total Expense', fmtLocal(report.totalExpense)),
      MapEntry('Actual Expense (ex-transfer)', fmtLocal(report.actualExpense)),
      MapEntry('Closing Balance', fmtLocal(report.closingBalance)),
    ];

    return DenseCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(LucideIcons.table, size: 15, color: c.blue),
            const SizedBox(width: 8),
            Text('Monthly Table', style: AppTextStyles.heading3(c.t1)),
            const SizedBox(width: 8),
            Text(report.monthLabel, style: AppTextStyles.captionXs(c.t3)),
          ]),
          const SizedBox(height: 12),
          Text('RAW SHEET ROW${raw != null ? ' · row ${raw['row']}' : ''}',
              style: AppTextStyles.labelXs(c.t3)),
          const SizedBox(height: 6),
          if (raw == null)
            Text('No imported source row (hand-entered month).',
                style: AppTextStyles.bodySmall(c.t3))
          else
            _RawGrid(
              header: (raw['header'] as List).cast<String>(),
              cells: (raw['cells'] as List).cast<String>(),
            ),
          const SizedBox(height: 16),
          Text('NORMALIZED VIEW', style: AppTextStyles.labelXs(c.t3)),
          const SizedBox(height: 6),
          for (final e in normalized) StatRow(e.key, e.value),
        ],
      ),
    );
  }
}

/// The exact Excel row rendered as a horizontally-scrolling column/value grid
/// so the sheet layout is preserved (blank cells kept).
class _RawGrid extends StatelessWidget {
  final List<String> header;
  final List<String> cells;
  const _RawGrid({required this.header, required this.cells});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final n = header.length;
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Container(
        decoration: BoxDecoration(
          border: Border.all(color: c.bd),
          borderRadius: BorderRadius.circular(6),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              for (var i = 0; i < n; i++)
                _cell(context, header[i], i, isHeader: true),
            ]),
            Row(children: [
              for (var i = 0; i < n; i++)
                _cell(context, i < cells.length ? cells[i] : '', i),
            ]),
          ],
        ),
      ),
    );
  }

  Widget _cell(BuildContext context, String text, int i,
      {bool isHeader = false}) {
    final c = context.colors;
    return Container(
      width: 88,
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
      decoration: BoxDecoration(
        color: isHeader ? c.bg3 : Colors.transparent,
        border: Border(
          right: BorderSide(color: c.bd.withValues(alpha: 0.5)),
          bottom: isHeader ? BorderSide(color: c.bd) : BorderSide.none,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (isHeader)
            Text(ExpenseSchema.colLetter(i),
                style: AppTextStyles.captionXs(c.t4)),
          Text(text.isEmpty ? '·' : text,
              style: isHeader
                  ? AppTextStyles.captionXs(c.t2)
                  : AppTextStyles.mono(c.t1).copyWith(fontSize: 11),
              maxLines: 2,
              overflow: TextOverflow.ellipsis),
        ],
      ),
    );
  }
}

// ══════════════════════════════════════════════════════════════════
//  SOURCE REFERENCES
// ══════════════════════════════════════════════════════════════════

class _ReferenceSection extends StatelessWidget {
  final Map<String, dynamic> data;
  final int year;
  final MonthlyReport report;
  const _ReferenceSection(
      {required this.data, required this.year, required this.report});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    // Directly-sourced fields (value → the raw cell it came from).
    final fields = <MapEntry<String, String>>[
      const MapEntry('opening', 'Opening Balance'),
      const MapEntry('salary', 'Salary'),
      const MapEntry('bonus', 'Bonus'),
      const MapEntry('reimburse', 'Reimbursement'),
      const MapEntry('interest', 'Interest'),
      const MapEntry('transfer', 'Transfer'),
      for (final cat in report.categories)
        if (cat.key != 'transfer') MapEntry(cat.key, cat.label),
    ];

    final refs = [
      for (final f in fields)
        MapEntry(f.value, ExpenseAnalytics.localRef(data, year, report.monthKey, f.key)),
    ];

    return DenseCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(LucideIcons.link2, size: 15, color: c.accent),
            const SizedBox(width: 8),
            Text('Source References', style: AppTextStyles.heading3(c.t1)),
            const SizedBox(width: 8),
            Flexible(
              child: Text('every value traces back to its raw cell',
                  style: AppTextStyles.captionXs(c.t3),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
            ),
          ]),
          const SizedBox(height: 10),
          for (final e in refs) _RefRow(label: e.key, ref: e.value),
        ],
      ),
    );
  }
}

class _RefRow extends StatelessWidget {
  final String label;
  final ExpenseRef ref;
  const _RefRow({required this.label, required this.ref});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 7),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: c.bd.withValues(alpha: 0.5))),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 150,
          child: Text(label,
              style: AppTextStyles.bodySmall(c.t1)
                  .copyWith(fontWeight: FontWeight.w600)),
        ),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(ref.label, style: AppTextStyles.captionXs(c.t2)),
              if (!ref.isDerived)
                Text(
                    'Cell ${ref.cellAddress} · original "${ref.originalValue}" · '
                    '${ref.currency} · ${ref.accountType}',
                    style: AppTextStyles.captionXs(c.t4)),
            ],
          ),
        ),
      ]),
    );
  }
}
