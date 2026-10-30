import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/expense_analytics.dart';
import 'package:aiei_wealth/providers/expense_provider.dart';
import 'package:aiei_wealth/providers/providers.dart';
import 'package:aiei_wealth/presentation/charts/expense_charts.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/presentation/screens/expenses_common.dart';

/// ─── Expense dashboard analytic pages ───
/// Read-only KPI + chart + audit views composed from [ExpenseAnalytics]. The
/// editable spreadsheet grids live on the Ledger / Transfer / Investments / Raw
/// pages via the builders in expenses_common.dart.

/// Responsive chart grid: 2 columns when wide, 1 when narrow.
class ChartGrid extends StatelessWidget {
  final List<Widget> children;
  const ChartGrid(this.children, {super.key});
  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (ctx, con) {
      final two = con.maxWidth > 860;
      if (!two) {
        return Column(
          children: [
            for (final w in children) ...[w, const SizedBox(height: 12)],
          ],
        );
      }
      final rows = <Widget>[];
      for (var i = 0; i < children.length; i += 2) {
        rows.add(Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: children[i]),
              const SizedBox(width: 12),
              Expanded(
                  child: i + 1 < children.length
                      ? children[i + 1]
                      : const SizedBox.shrink()),
            ],
          ),
        ));
      }
      return Column(children: rows);
    });
  }
}

List<Color> _palette(BuildContext c) {
  final s = c.colors;
  return [
    s.blue, s.up, s.dn, s.gold, s.accent, s.cyan,
    s.blue.withValues(alpha: 0.6), s.up.withValues(alpha: 0.6),
    s.dn.withValues(alpha: 0.6), s.gold.withValues(alpha: 0.6),
  ];
}

// ══════════════════════════════════════════════════════════════════
//  OVERVIEW
// ══════════════════════════════════════════════════════════════════

/// Aggregated local-ledger money-flow figures for the Overview, all derived from the
/// latest raw dataset via the spec formulas (nothing hard-coded).
class _Flow {
  final double opening, salary, bonus, reimburse, interest, income;
  final double totalExpense, actualExpense, transfer;
  const _Flow({
    required this.opening,
    required this.salary,
    required this.bonus,
    required this.reimburse,
    required this.interest,
    required this.income,
    required this.totalExpense,
    required this.actualExpense,
    required this.transfer,
  });
  double get totalExpenseInclTransfer => actualExpense + transfer;
  double get savingsFromIncome => income - actualExpense;
  double get totalAvailableBeforeTransfer => opening + income - actualExpense;
  double get closing => opening + income - totalExpenseInclTransfer;
  double get growth => closing - opening;
  double _pct(double v) => income > 0 ? v / income * 100 : 0;
  double get savingsRate => _pct(savingsFromIncome);
  double get expenseRatio => _pct(actualExpense);
  double get transferRatio => _pct(transfer);
  double get outflowRatio => _pct(totalExpenseInclTransfer);
  double get growthRatio => _pct(growth);
}

class OverviewPage extends ConsumerWidget {
  final List<int> years; // concrete years in view
  final Map<int, Map<String, dynamic>> dataByYear;
  final CurrencyView currency;
  const OverviewPage({
    super.key,
    required this.years,
    required this.dataByYear,
    required this.currency,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final multi = years.length > 1;
    final primary = years.isNotEmpty ? years.first : DateTime.now().year;
    final pdata = dataByYear[primary] ?? const <String, dynamic>{};

    // Aggregate local-ledger figures across the selected years, then apply the spec
    // formulas. For a single year this is exact; for All-Years it treats the
    // span as one continuous flow (noted in the header).
    double salary = 0, bonus = 0, reimburse = 0, interest = 0;
    double income = 0, totalExp = 0, actual = 0, transfer = 0;
    double accountA = 0, accountB = 0, invested = 0, deployed = 0;
    double mutual = 0, gold = 0, silver = 0, nasdaq = 0, para = 0;
    for (final y in years) {
      final d = dataByYear[y];
      if (d == null) continue;
      final k = ExpenseAnalytics.localKpis(d);
      salary += k.salary;
      bonus += k.bonus;
      reimburse += k.reimburse;
      interest += k.interest;
      income += k.income;
      totalExp += k.totalExpense;
      actual += k.actualExpense;
      transfer += k.transfer;
      if (ExpenseAnalytics.accountAClosing(d) != 0) accountA = ExpenseAnalytics.accountAClosing(d);
      if (ExpenseAnalytics.accountBClosing(d) != 0) accountB = ExpenseAnalytics.accountBClosing(d);
      invested += ExpenseAnalytics.investedTotal(d);
      deployed += ExpenseAnalytics.stockDeployed(d);
      final split = ExpenseAnalytics.investmentSplit(d);
      final inv = ExpenseAnalytics.investRows(d);
      mutual += inv.fold<double>(
          0, (a, r) => a + ((r['mutual'] as num?)?.toDouble() ?? 0));
      gold += split['Gold'] ?? 0;
      silver += split['Silver'] ?? 0;
      nasdaq += split['NASDAQ-100'] ?? 0;
      para += split['Para'] ?? 0;
    }
    final opening = dataByYear[primary] != null
        ? ExpenseAnalytics.localKpis(dataByYear[primary]!).opening
        : 0.0;
    final f = _Flow(
      opening: opening,
      salary: salary,
      bonus: bonus,
      reimburse: reimburse,
      interest: interest,
      income: income,
      totalExpense: totalExp,
      actualExpense: actual,
      transfer: transfer,
    );

    // Previous-year comparison (single-year view only).
    final notifier = ref.read(expenseStoreProvider.notifier);
    final prev = (!multi && notifier.hasData(primary - 1))
        ? ExpenseAnalytics.localKpis(notifier.viewFor(primary - 1))
        : null;

    final period = ExpenseAnalytics.periodInfo(pdata, primary);
    final showLocal = currency != CurrencyView.inr;
    final showInr = currency != CurrencyView.local;

    String vsPrev(double cur, double? prv) {
      if (prv == null) return '';
      final d = cur - prv;
      return '${d >= 0 ? '+' : ''}${fmtLocal(d)} vs ${primary - 1}';
    }

    return ListView(padding: EdgeInsets.zero, children: [
      // ── SECTION 1: Selected period summary ──
      const LastUpdatedBar(),
      const SizedBox(height: 10),
      _PeriodSummary(
          primary: primary, multi: multi, years: years, period: period),
      const SizedBox(height: 16),

      if (showLocal) ...[
        // ── SECTION 2: local cash flow ──
        sectionHeader(context, LucideIcons.wallet, kLocal, '$localLabel Cash Flow',
            '$localCcy · where your money came from and went'),
        const SizedBox(height: 10),
        _cards(context, [
          FinanceCard(
            title: 'Opening Balance',
            plain: 'Money I started with',
            value: fmtLocal(f.opening),
            color: c.t2,
            meaning:
                'Money you already had before this period started. Old money, not new income.',
            formula: 'Opening = first filled month opening balance',
            example: 'Opening = ${fmtLocal(f.opening)}',
            sources: ExpenseAnalytics.fieldSources(pdata, primary, 'opening'),
            sourceNote: 'First filled month opening balance',
          ),
          FinanceCard(
            title: 'Total Income',
            plain: 'Money I received',
            value: fmtLocal(f.income),
            color: c.up,
            meaning: 'All money received during the period.',
            formula: 'Salary + Bonus + Reimburse + Interest',
            example:
                '${fmtLocal(f.salary)} + ${fmtLocal(f.bonus)} + ${fmtLocal(f.reimburse)} + ${fmtLocal(f.interest)} = ${fmtLocal(f.income)}',
            sources: const [],
            sourceNote: 'Sum of income columns across filled months',
            delta: vsPrev(f.income, prev?.income),
            deltaColor: c.t3,
          ),
          FinanceCard(
            title: 'Actual Expense',
            plain: 'Money I spent (living)',
            value: fmtLocal(f.actualExpense),
            color: c.dn,
            meaning:
                'Real living expense, excluding the transfer to $accountAShort (transfer is money movement, not spending).',
            formula: 'Total Expense − Transfer',
            example:
                '${fmtLocal(f.totalExpenseInclTransfer)} − ${fmtLocal(f.transfer)} = ${fmtLocal(f.actualExpense)}',
            sources:
                ExpenseAnalytics.fieldSources(pdata, primary, 'actual_expense'),
            sourceNote: 'Sum of actual expense across filled months',
            delta: vsPrev(f.actualExpense, prev?.actualExpense),
            deltaColor: c.t3,
          ),
          FinanceCard(
            title: 'Transfer to $accountAShort',
            plain: 'Money sent to $accountAShort',
            value: fmtLocal(f.transfer),
            color: c.gold,
            meaning: 'Money moved from $localLabel to $accountAShort. Not a daily expense.',
            formula: 'Sum of the Transfer column',
            example: 'Transfer = ${fmtLocal(f.transfer)}',
            sources: ExpenseAnalytics.fieldSources(pdata, primary, 'transfer'),
            sourceNote: 'Sum of Transfer column across filled months',
          ),
          FinanceCard(
            title: 'Total Expense (incl. Transfer)',
            plain: 'All money out of $localLabel',
            value: fmtLocal(f.totalExpenseInclTransfer),
            color: c.dn,
            meaning:
                'Everything leaving $localLabel — real expenses plus the transfer to $accountAShort.',
            formula: 'Actual Expense + Transfer',
            example:
                '${fmtLocal(f.actualExpense)} + ${fmtLocal(f.transfer)} = ${fmtLocal(f.totalExpenseInclTransfer)}',
            sources: const [],
            sourceNote: 'Computed: Actual Expense + Transfer',
          ),
          FinanceCard(
            title: 'Savings From Income',
            plain: 'Money saved from income',
            value: fmtLocalSigned(f.savingsFromIncome),
            color: context.pnlColor(f.savingsFromIncome),
            meaning:
                'Money saved from this period\'s income after real living expenses. Does NOT include opening balance.',
            formula: 'Total Income − Actual Expense',
            example:
                '${fmtLocal(f.income)} − ${fmtLocal(f.actualExpense)} = ${fmtLocal(f.savingsFromIncome)}',
            sources: const [],
            sourceNote: 'Computed: Total Income − Actual Expense',
            delta: vsPrev(f.savingsFromIncome,
                prev == null ? null : prev.income - prev.actualExpense),
            deltaColor: c.t3,
          ),
          FinanceCard(
            title: 'Available Before Transfer',
            plain: 'Money available before transfer',
            value: fmtLocal(f.totalAvailableBeforeTransfer),
            color: c.blue,
            meaning:
                'Total $localLabel money after income and real expenses, before transferring anything to $accountAShort.',
            formula: 'Opening + Total Income − Actual Expense',
            example:
                '${fmtLocal(f.opening)} + ${fmtLocal(f.income)} − ${fmtLocal(f.actualExpense)} = ${fmtLocal(f.totalAvailableBeforeTransfer)}',
            sources: const [],
            sourceNote: 'Computed: Opening + Savings From Income',
          ),
          FinanceCard(
            title: 'Closing $localLabel Balance',
            plain: 'Money left in $localLabel',
            value: fmtLocal(f.closing),
            color: c.cyan,
            meaning:
                'Final $localLabel balance after all expenses and the transfer to $accountAShort.',
            formula: 'Opening + Total Income − Total Expense (incl. Transfer)',
            example:
                '${fmtLocal(f.opening)} + ${fmtLocal(f.income)} − ${fmtLocal(f.totalExpenseInclTransfer)} = ${fmtLocal(f.closing)}',
            sources: const [],
            sourceNote: 'Computed from opening + income − total expense',
            delta: vsPrev(f.closing, prev?.closing),
            deltaColor: c.t3,
          ),
          FinanceCard(
            title: '$localLabel Balance Growth',
            plain: 'How much my balance grew',
            value: fmtLocalSigned(f.growth),
            color: context.pnlColor(f.growth),
            meaning:
                'How much the $localLabel balance increased or decreased over the period.',
            formula: 'Closing − Opening',
            example: '${fmtLocal(f.closing)} − ${fmtLocal(f.opening)} = ${fmtLocal(f.growth)}',
            sources: const [],
            sourceNote: 'Computed: Closing − Opening',
          ),
        ]),
        const SizedBox(height: 16),

        // ── SECTION 7: Money-flow waterfall ──
        sectionHeader(context, LucideIcons.waves, c.blue, 'Money Flow',
            'Opening → Income → Actual Expense → Transfer → Closing'),
        const SizedBox(height: 10),
        ChartCard(
          title: '$localLabel Money Flow',
          subtitle:
              '${fmtLocal(f.opening)} + ${fmtLocal(f.income)} − ${fmtLocal(f.actualExpense)} − ${fmtLocal(f.transfer)} = ${fmtLocal(f.closing)}',
          height: 260,
          child: WaterfallChart(steps: [
            WaterfallStep('Opening', f.opening, c.t2, isTotal: true),
            WaterfallStep('Salary', f.salary, c.up),
            WaterfallStep('Bonus', f.bonus, c.up),
            WaterfallStep('Reimburse', f.reimburse, c.up),
            WaterfallStep('Interest', f.interest, c.up),
            WaterfallStep('Actual Exp', -f.actualExpense, c.dn),
            WaterfallStep('Transfer', -f.transfer, c.gold),
            WaterfallStep('Closing', f.closing, c.cyan, isTotal: true),
          ]),
        ),
        const SizedBox(height: 16),

        // ── SECTION 3: Income breakdown ──
        sectionHeader(context, LucideIcons.trendingUp, c.up, 'Income Breakdown',
            'NT\$ · where income came from'),
        const SizedBox(height: 10),
        _cards(context, [
          FinanceCard(
              title: 'Salary',
              plain: 'Monthly pay',
              value: fmtLocal(f.salary),
              color: c.up,
              meaning: 'Total salary received in the period.',
              formula: 'Sum of Salary column',
              example: 'Salary = ${fmtLocal(f.salary)}',
              sources: ExpenseAnalytics.fieldSources(pdata, primary, 'salary'),
              sourceNote: 'Sum of Salary column'),
          FinanceCard(
              title: 'Bonus',
              plain: 'Extra pay',
              value: fmtLocal(f.bonus),
              color: c.up,
              meaning: 'Total bonus received.',
              formula: 'Sum of Bonus column',
              example: 'Bonus = ${fmtLocal(f.bonus)}',
              sources: ExpenseAnalytics.fieldSources(pdata, primary, 'bonus'),
              sourceNote: 'Sum of Bonus column'),
          FinanceCard(
              title: 'Reimburse',
              plain: 'Money paid back to me',
              value: fmtLocal(f.reimburse),
              color: c.up,
              meaning: 'Reimbursements received.',
              formula: 'Sum of Reimburse column',
              example: 'Reimburse = ${fmtLocal(f.reimburse)}',
              sources:
                  ExpenseAnalytics.fieldSources(pdata, primary, 'reimburse'),
              sourceNote: 'Sum of Reimburse column'),
          FinanceCard(
              title: 'Interest',
              plain: 'Bank interest',
              value: fmtLocal(f.interest),
              color: c.up,
              meaning: 'Interest earned.',
              formula: 'Sum of Interest column',
              example: 'Interest = ${fmtLocal(f.interest)}',
              sources:
                  ExpenseAnalytics.fieldSources(pdata, primary, 'interest'),
              sourceNote: 'Sum of Interest column'),
        ]),
        const SizedBox(height: 10),
        _incomeChart(context, pdata, primary),
        const SizedBox(height: 16),

        // ── SECTION 4: Expense breakdown ──
        sectionHeader(context, LucideIcons.receipt, c.dn, 'Expense Breakdown',
            'NT\$ · living expenses (transfer shown separately)'),
        const SizedBox(height: 10),
        _expenseSection(context, pdata, primary, f),
        const SizedBox(height: 16),

        // ── SECTION 5: Savings & ratios ──
        sectionHeader(context, LucideIcons.percent, c.accent, 'Savings & Ratios',
            '% of income'),
        const SizedBox(height: 10),
        _cards(context, [
          FinanceCard(
              title: 'Savings Rate',
              plain: 'How much income I saved',
              value: '${f.savingsRate.toStringAsFixed(1)}%',
              color: f.savingsRate >= 30
                  ? c.up
                  : (f.savingsRate >= 0 ? c.gold : c.dn),
              meaning: 'How much income is saved after real living expenses.',
              formula: 'Savings From Income / Total Income × 100',
              example:
                  '${fmtLocal(f.savingsFromIncome)} / ${fmtLocal(f.income)} × 100 = ${f.savingsRate.toStringAsFixed(1)}%',
              sources: const [],
              sourceNote: 'Computed ratio'),
          FinanceCard(
              title: 'Expense Ratio',
              plain: 'How much I spent on living',
              value: '${f.expenseRatio.toStringAsFixed(1)}%',
              color: c.dn,
              meaning: 'How much income goes to living expenses.',
              formula: 'Actual Expense / Total Income × 100',
              example:
                  '${fmtLocal(f.actualExpense)} / ${fmtLocal(f.income)} × 100 = ${f.expenseRatio.toStringAsFixed(1)}%',
              sources: const [],
              sourceNote: 'Computed ratio'),
          FinanceCard(
              title: 'Transfer Ratio',
              plain: 'How much I sent to $accountAShort',
              value: '${f.transferRatio.toStringAsFixed(1)}%',
              color: c.gold,
              meaning: 'How much income is moved to $accountAShort.',
              formula: 'Transfer / Total Income × 100',
              example:
                  '${fmtLocal(f.transfer)} / ${fmtLocal(f.income)} × 100 = ${f.transferRatio.toStringAsFixed(1)}%',
              sources: const [],
              sourceNote: 'Computed ratio'),
          FinanceCard(
              title: 'Total Outflow Ratio',
              plain: 'Expense + transfer vs income',
              value: '${f.outflowRatio.toStringAsFixed(1)}%',
              color: c.dn,
              meaning: 'Actual expense plus transfer compared to income.',
              formula: 'Total Expense (incl. Transfer) / Total Income × 100',
              example:
                  '${fmtLocal(f.totalExpenseInclTransfer)} / ${fmtLocal(f.income)} × 100 = ${f.outflowRatio.toStringAsFixed(1)}%',
              sources: const [],
              sourceNote: 'Computed ratio'),
          FinanceCard(
              title: 'Balance Growth Ratio',
              plain: 'Growth vs income',
              value: '${f.growthRatio.toStringAsFixed(1)}%',
              color: context.pnlColor(f.growth),
              meaning: '$localLabel balance growth compared to income.',
              formula: '$localLabel Balance Growth / Total Income × 100',
              example:
                  '${fmtLocal(f.growth)} / ${fmtLocal(f.income)} × 100 = ${f.growthRatio.toStringAsFixed(1)}%',
              sources: const [],
              sourceNote: 'Computed ratio'),
        ]),
        const SizedBox(height: 16),
      ],

      if (showInr) ...[
        // ── SECTION 6: INR accounts / Investments ──
        sectionHeader(context, LucideIcons.landmark, kInv,
            'Bank Accounts & Investments', '₹ INR · kept separate from $localCcy'),
        const SizedBox(height: 6),
        _inrNote(context),
        const SizedBox(height: 10),
        _cards(context, [
          FinanceCard(
              title: '$accountALabel Balance',
              plain: 'INR bank ($accountAShort)',
              value: formatINR(accountA),
              color: kAccountA,
              currencySymbol: '₹',
              meaning: 'Closing balance of $accountALabel.',
              formula: 'Last month $accountAShort balance',
              example: '$accountAShort = ${formatINR(accountA)}',
              sources: const [],
              sourceNote: '$accountALabel section'),
          FinanceCard(
              title: '$accountBLabel Balance',
              plain: 'INR bank ($accountBShort)',
              value: formatINR(accountB),
              color: kAccountB,
              currencySymbol: '₹',
              meaning: 'Closing balance of $accountBLabel.',
              formula: 'Last month $accountBShort balance',
              example: '$accountBShort = ${formatINR(accountB)}',
              sources: const [],
              sourceNote: '$accountBLabel section'),
          FinanceCard(
              title: 'Invested',
              plain: 'Total investments',
              value: formatINR(invested),
              color: kInv,
              currencySymbol: '₹',
              meaning: 'Total invested amount across asset classes.',
              formula: 'Sum of investment tracker total',
              example: 'Invested = ${formatINR(invested)}',
              sources: const [],
              sourceNote: 'Investment tracker'),
          FinanceCard(
              title: 'Stocks Deployed',
              plain: 'Direct equity',
              value: formatINR(deployed),
              color: kStk,
              currencySymbol: '₹',
              meaning: 'Capital deployed into direct stock trades.',
              formula: 'Sum of stock invested',
              example: 'Stocks = ${formatINR(deployed)}',
              sources: const [],
              sourceNote: 'Stock trade log'),
          FinanceCard(
              title: 'Mutual Fund',
              plain: 'MF contributions',
              value: formatINR(mutual),
              color: kInv,
              currencySymbol: '₹',
              meaning: 'Total mutual fund contributions.',
              formula: 'Sum of Mutual column',
              example: 'MF = ${formatINR(mutual)}',
              sources: const [],
              sourceNote: 'Investment tracker'),
          FinanceCard(
              title: 'Gold',
              plain: 'Gold holdings',
              value: formatINR(gold),
              color: kAccountB,
              currencySymbol: '₹',
              meaning: 'Gold allocation.',
              formula: 'Sum of Gold column',
              example: 'Gold = ${formatINR(gold)}',
              sources: const [],
              sourceNote: 'Investment tracker'),
          FinanceCard(
              title: 'Silver',
              plain: 'Silver holdings',
              value: formatINR(silver),
              color: c.t2,
              currencySymbol: '₹',
              meaning: 'Silver allocation.',
              formula: 'Sum of Silver column',
              example: 'Silver = ${formatINR(silver)}',
              sources: const [],
              sourceNote: 'Investment tracker'),
          FinanceCard(
              title: 'NASDAQ-100',
              plain: 'US index',
              value: formatINR(nasdaq),
              color: kStk,
              currencySymbol: '₹',
              meaning: 'NASDAQ-100 allocation.',
              formula: 'Sum of NASDAQ column',
              example: 'NASDAQ = ${formatINR(nasdaq)}',
              sources: const [],
              sourceNote: 'Investment tracker'),
          if (para != 0)
            FinanceCard(
                title: 'Para',
                plain: 'Parametric / other',
                value: formatINR(para),
                color: c.accent,
                currencySymbol: '₹',
                meaning: 'Para allocation.',
                formula: 'Sum of Para column',
                example: 'Para = ${formatINR(para)}',
                sources: const [],
                sourceNote: 'Investment tracker'),
        ]),
        const SizedBox(height: 12),
        _indiaCharts(context, pdata),
        const SizedBox(height: 24),
      ],
    ]);
  }

  // INR visuals — bank balance trends, investment split, per-scrip.
  Widget _indiaCharts(BuildContext context, Map<String, dynamic> d) {
    final accountARows = ExpenseAnalytics.accountARows(d);
    final accountBRows = ExpenseAnalytics.accountBRows(d);
    final split = ExpenseAnalytics.investmentSplit(d);
    final byScrip = ExpenseAnalytics.byScrip(d);
    final scrips = byScrip.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final charts = <Widget>[];
    if (accountARows.isNotEmpty) {
      charts.add(ChartCard(
        title: '$accountALabel Balance',
        subtitle: '₹ INR · month-end',
        child: TrendLineChart(
          labels: [for (final r in accountARows) _monthAbbr('${r['month']}')],
          values: [for (final r in accountARows) (r['balance'] as num?)?.toDouble() ?? 0],
          color: kAccountA,
          allowNegative: true,
        ),
      ));
    }
    if (accountBRows.isNotEmpty) {
      charts.add(ChartCard(
        title: '$accountBLabel Balance',
        subtitle: '₹ INR · month-end',
        child: TrendLineChart(
          labels: [for (final r in accountBRows) _monthAbbr('${r['month']}')],
          values: [for (final r in accountBRows) (r['balance'] as num?)?.toDouble() ?? 0],
          color: kAccountB,
          allowNegative: true,
        ),
      ));
    }
    if (split.isNotEmpty) {
      charts.add(ChartCard(
        title: 'Investment Split',
        subtitle: '₹ INR · by asset class',
        child: DonutChart(data: split, palette: _palette(context)),
      ));
    }
    if (scrips.isNotEmpty) {
      charts.add(ChartCard(
        title: 'Deployed by Scrip',
        subtitle: '₹ INR · direct equity',
        child: GroupedBarChart(
          labels: [for (final e in scrips) e.key],
          seriesA: [for (final e in scrips) e.value],
          seriesB: List.filled(scrips.length, 0),
          colorA: kStk,
          colorB: Colors.transparent,
          nameA: 'Deployed',
          nameB: '',
        ),
      ));
    }
    if (charts.isEmpty) return const SizedBox.shrink();
    return ChartGrid(charts);
  }

  // Responsive card grid (4 / 3 / 2 / 1 columns). Uses a Wrap of fixed-width
  // cards so each card sizes to its own content — no CrossAxisAlignment.stretch
  // (which forces intrinsic-height layout and crashes inside a ListView).
  Widget _cards(BuildContext context, List<Widget> cards) {
    return LayoutBuilder(builder: (ctx, con) {
      final w = con.maxWidth;
      final per = w > 1100
          ? 4
          : w > 780
              ? 3
              : w > 480
                  ? 2
                  : 1;
      const gap = 10.0;
      final cardW = ((w - gap * (per - 1)) / per) - 0.5;
      return Wrap(
        spacing: gap,
        runSpacing: gap,
        children: [
          for (final card in cards) SizedBox(width: cardW, child: card),
        ],
      );
    });
  }

  Widget _incomeChart(BuildContext context, Map<String, dynamic> d, int year) {
    final c = context.colors;
    final pts = ExpenseAnalytics.localPoints(d, year);
    final labels = [for (final p in pts) p.month.substring(0, 3).toUpperCase()];
    return ChartCard(
      title: 'Monthly Income',
      subtitle: 'NT\$ · salary vs total income',
      child: GroupedBarChart(
        labels: labels,
        seriesA: [for (final p in pts) p.income],
        seriesB: [
          for (final p in pts) (p.row['salary'] as num?)?.toDouble() ?? 0
        ],
        colorA: c.up,
        colorB: c.blue,
        nameA: 'Total Income',
        nameB: 'Salary',
      ),
    );
  }

  Widget _expenseSection(
      BuildContext context, Map<String, dynamic> d, int year, _Flow f) {
    final c = context.colors;
    final totals = ExpenseAnalytics.categoryTotals(d); // ex-transfer, desc
    final cats = {for (final e in totals) e.key: e.value};
    final filled = ExpenseAnalytics.filledMonthKeys(d);
    final pts = ExpenseAnalytics.localPoints(d, year);
    final labels = [for (final p in pts) p.month.substring(0, 3).toUpperCase()];
    final avgActual = filled.isEmpty ? 0.0 : f.actualExpense / filled.length;
    // Highest actual-expense month (filled only).
    String hiMonth = '—';
    double hiVal = -1;
    for (final p in pts) {
      if (filled.contains(p.month) && p.actual > hiVal) {
        hiVal = p.actual;
        hiMonth = p.month.substring(0, 3).toUpperCase();
      }
    }
    final topCat = totals.isNotEmpty ? totals.first : null;

    return Column(children: [
      _cards(context, [
        FinanceCard(
            title: 'Total Expense',
            plain: 'All money out',
            value: fmtLocal(f.totalExpenseInclTransfer),
            color: c.dn,
            meaning: 'Actual living expense plus the transfer to $accountAShort.',
            formula: 'Actual Expense + Transfer',
            example:
                '${fmtLocal(f.actualExpense)} + ${fmtLocal(f.transfer)} = ${fmtLocal(f.totalExpenseInclTransfer)}',
            sources: const [],
            sourceNote: 'Computed'),
        FinanceCard(
            title: 'Actual Expense',
            plain: 'Living expense',
            value: fmtLocal(f.actualExpense),
            color: c.dn,
            meaning: 'Real living expense excluding transfer.',
            formula: 'Sum of all expense categories (ex-transfer)',
            example: 'Actual = ${fmtLocal(f.actualExpense)}',
            sources:
                ExpenseAnalytics.fieldSources(d, year, 'actual_expense'),
            sourceNote: 'Sum of category columns'),
        FinanceCard(
            title: 'Transfer',
            plain: 'Sent to $accountAShort',
            value: fmtLocal(f.transfer),
            color: c.gold,
            meaning: 'Money moved to $accountAShort (shown separately).',
            formula: 'Sum of Transfer column',
            example: 'Transfer = ${fmtLocal(f.transfer)}',
            sources: ExpenseAnalytics.fieldSources(d, year, 'transfer'),
            sourceNote: 'Transfer column'),
        FinanceCard(
            title: 'Avg Monthly Expense',
            plain: 'Average per filled month',
            value: fmtLocal(avgActual),
            color: c.t2,
            meaning:
                'Average actual expense across filled months only (future/empty months excluded).',
            formula: 'Actual Expense / Filled Months',
            example:
                '${fmtLocal(f.actualExpense)} / ${filled.length} = ${fmtLocal(avgActual)}',
            sources: const [],
            sourceNote: 'Computed over ${filled.length} filled months'),
      ]),
      const SizedBox(height: 10),
      // Per-category cards.
      _cards(context, [
        for (final e in totals)
          FinanceCard(
            title: e.key,
            plain: 'Category',
            value: fmtLocal(e.value),
            color: c.dn,
            meaning: '${e.key} spending for the period.',
            formula: 'Sum of ${e.key} across filled months',
            example:
                '${e.key} = ${fmtLocal(e.value)} · ${f.actualExpense > 0 ? (e.value / f.actualExpense * 100).toStringAsFixed(1) : '0'}% of actual',
            sources: const [],
            sourceNote: 'Category column',
          ),
      ]),
      const SizedBox(height: 10),
      ChartGrid([
        ChartCard(
          title: 'Expense by Category',
          subtitle: 'NT\$ · ex-transfer',
          child: DonutChart(data: cats, palette: _palette(context)),
        ),
        ChartCard(
          title: 'Monthly Actual Expense',
          subtitle: 'NT\$ · trend'
              '${topCat != null ? ' · top: ${topCat.key}' : ''}'
              '${hiMonth != '—' ? ' · peak: $hiMonth' : ''}',
          child: TrendLineChart(
              labels: labels,
              values: [for (final p in pts) p.actual],
              color: c.dn),
        ),
      ]),
    ]);
  }

  Widget _inrNote(BuildContext context) {
    final c = context.colors;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: kInv.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: kInv.withValues(alpha: 0.25)),
      ),
      child: Row(children: [
        Icon(LucideIcons.info, size: 13, color: kInv),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            'Bank accounts & investments are shown in ₹ INR and are NOT added to the '
            '$localLabel $localCcy totals (no currency conversion enabled).',
            style: AppTextStyles.captionXs(c.t2),
          ),
        ),
      ]),
    );
  }
}

// ══════════════════════════════════════════════════════════════════
//  OVERVIEW BUILDING BLOCKS
// ══════════════════════════════════════════════════════════════════

/// A section heading strip.
Widget sectionHeader(BuildContext context, IconData icon, Color accent,
    String title, String subtitle) {
  final c = context.colors;
  return Row(children: [
    Container(
      padding: const EdgeInsets.all(6),
      decoration: BoxDecoration(
          color: accent.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(8)),
      child: Icon(icon, size: 15, color: accent),
    ),
    const SizedBox(width: 10),
    Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(title, style: AppTextStyles.heading3(c.t1)),
          Text(subtitle, style: AppTextStyles.captionXs(c.t3)),
        ]),
  ]);
}

/// Section 1 — selected period summary (year, period, filled/future months).
class _PeriodSummary extends StatelessWidget {
  final int primary;
  final bool multi;
  final List<int> years;
  final Map<String, dynamic> period;
  const _PeriodSummary(
      {required this.primary,
      required this.multi,
      required this.years,
      required this.period});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final label =
        multi ? 'All years (${years.first}–${years.last})' : '$primary';
    return DenseCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(LucideIcons.calendarRange, size: 15, color: c.blue),
          const SizedBox(width: 8),
          Text('Selected Period', style: AppTextStyles.heading3(c.t1)),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 18, runSpacing: 6, children: [
          _kv(context, 'Year', label),
          _kv(context, 'Period', '${period['periodLabel']}'),
          _kv(context, 'Filled months', '${period['filledCount']}'),
          _kv(context, 'Future / empty', '${period['futureCount']}'),
          _kv(context, 'Last filled', '${period['lastFilled']}'),
        ]),
        const SizedBox(height: 8),
        Row(children: [
          Icon(LucideIcons.info, size: 12, color: c.t3),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              '$localLabel overview is calculated in $localCcy. Bank accounts & investments '
              'are shown separately in ₹ INR (not mixed into one total).',
              style: AppTextStyles.captionXs(c.t3),
            ),
          ),
        ]),
      ]),
    );
  }

  Widget _kv(BuildContext context, String k, String v) {
    final c = context.colors;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Text('$k: ', style: AppTextStyles.captionXs(c.t3)),
      Text(v, style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 12)),
    ]);
  }
}

/// A KPI card that tells a simple money story: plain-language label, value,
/// an info icon (meaning + formula + worked example + source), and a
/// "View Source" button tracing back to the raw cells. All values are passed
/// in already-computed from the latest raw dataset — nothing is hard-coded.
class FinanceCard extends StatelessWidget {
  final String title;
  final String plain; // plain-language meaning label
  final String value;
  final Color color;
  final String meaning;
  final String formula;
  final String example;
  final List<Map<String, dynamic>> sources;
  final String sourceNote;
  final String? delta;
  final Color? deltaColor;
  final String currencySymbol; // for the info example only
  const FinanceCard({
    super.key,
    required this.title,
    required this.plain,
    required this.value,
    required this.color,
    required this.meaning,
    required this.formula,
    required this.example,
    required this.sources,
    required this.sourceNote,
    this.delta,
    this.deltaColor,
    this.currencySymbol = 'NT\$',
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return DenseCard(
      padding: const EdgeInsets.fromLTRB(12, 10, 8, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(children: [
            Expanded(
              child: Text(title.toUpperCase(),
                  style: AppTextStyles.labelXs(c.t3),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis),
            ),
            _iconBtn(context, LucideIcons.info, () => _info(context)),
          ]),
          const SizedBox(height: 6),
          Text(value,
              style: AppTextStyles.monoBold(color).copyWith(fontSize: 18),
              maxLines: 1,
              overflow: TextOverflow.ellipsis),
          const SizedBox(height: 3),
          Text(plain,
              style: AppTextStyles.captionXs(c.t2),
              maxLines: 1,
              overflow: TextOverflow.ellipsis),
          if (delta != null && delta!.isNotEmpty) ...[
            const SizedBox(height: 3),
            Text(delta!,
                style: AppTextStyles.captionXs(deltaColor ?? c.t3),
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
          ],
          const SizedBox(height: 4),
          InkWell(
            onTap: () => _source(context),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(LucideIcons.link2, size: 11, color: c.t4),
              const SizedBox(width: 4),
              Text('View Source', style: AppTextStyles.captionXs(c.t4)),
            ]),
          ),
        ],
      ),
    );
  }

  Widget _iconBtn(BuildContext context, IconData icon, VoidCallback onTap) =>
      InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(6),
        child: Padding(
          padding: const EdgeInsets.all(4),
          child: Icon(icon, size: 13, color: context.colors.t4),
        ),
      );

  void _info(BuildContext context) {
    final c = context.colors;
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: c.bg2,
        title: Text(title, style: AppTextStyles.heading3(c.t1)),
        content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _row(context, 'Value', value, valueColor: color),
              const SizedBox(height: 8),
              _label(context, 'Meaning'),
              Text(meaning, style: AppTextStyles.bodySmall(c.t2)),
              const SizedBox(height: 8),
              _label(context, 'Formula'),
              Text(formula, style: AppTextStyles.mono(c.t2).copyWith(fontSize: 12)),
              const SizedBox(height: 8),
              _label(context, 'Example (current period)'),
              Text(example, style: AppTextStyles.mono(c.t2).copyWith(fontSize: 12)),
              const SizedBox(height: 8),
              _label(context, 'Source'),
              Text(sourceNote, style: AppTextStyles.captionXs(c.t3)),
            ]),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Close'))
        ],
      ),
    );
  }

  void _source(BuildContext context) {
    final c = context.colors;
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: c.bg2,
        title: Text('$title — Source', style: AppTextStyles.heading3(c.t1)),
        content: SizedBox(
          width: 460,
          child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(sourceNote, style: AppTextStyles.bodySmall(c.t2)),
                const SizedBox(height: 10),
                if (sources.isEmpty)
                  Text('Computed value — no single source cell.',
                      style: AppTextStyles.captionXs(c.t3))
                else ...[
                  Text('RAW CELLS', style: AppTextStyles.labelXs(c.t3)),
                  const SizedBox(height: 4),
                  Flexible(
                    child: SingleChildScrollView(
                      child: Column(children: [
                        for (final s in sources)
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 2),
                            child: Row(children: [
                              SizedBox(
                                  width: 90,
                                  child: Text('${s['month']}',
                                      style: AppTextStyles.captionXs(c.t2))),
                              SizedBox(
                                  width: 120,
                                  child: Text('${s['column']}',
                                      style: AppTextStyles.captionXs(c.t3),
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis)),
                              SizedBox(
                                  width: 60,
                                  child: Text('${s['cell']}',
                                      style: AppTextStyles.monoXs(c.blue))),
                              Expanded(
                                  child: Text('${s['original']}',
                                      style: AppTextStyles.monoXs(c.t2),
                                      textAlign: TextAlign.right)),
                            ]),
                          ),
                      ]),
                    ),
                  ),
                ],
              ]),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Close'))
        ],
      ),
    );
  }

  Widget _label(BuildContext context, String t) =>
      Text(t.toUpperCase(), style: AppTextStyles.labelXs(context.colors.t3));
  Widget _row(BuildContext context, String k, String v, {Color? valueColor}) {
    final c = context.colors;
    return Row(children: [
      Text('$k: ', style: AppTextStyles.captionXs(c.t3)),
      Text(v,
          style:
              AppTextStyles.monoBold(valueColor ?? c.t1).copyWith(fontSize: 13)),
    ]);
  }
}

// ══════════════════════════════════════════════════════════════════
//  INCOME
// ══════════════════════════════════════════════════════════════════

class IncomePage extends StatelessWidget {
  final Map<String, dynamic> data;
  final int year;
  const IncomePage({super.key, required this.data, required this.year});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final pts = ExpenseAnalytics.localPoints(data, year);
    final labels = [for (final p in pts) p.month.substring(0, 3).toUpperCase()];
    final salary = [for (final p in pts) (p.row['salary'] as num?)?.toDouble() ?? 0];
    final income = [for (final p in pts) p.income];
    final actual = [for (final p in pts) p.actual];
    final k = ExpenseAnalytics.localKpis(data);

    return ListView(padding: EdgeInsets.zero, children: [
      KpiGrid(cells: [
        Kpi('TOTAL INCOME', fmtLocal(k.income), '$localCcy · year', c.blue),
        Kpi('SALARY', fmtLocal(k.salary), localCcy, c.blue),
        Kpi('BONUS', fmtLocal(k.bonus), localCcy, c.blue),
        Kpi('REIMBURSE', fmtLocal(k.reimburse), localCcy, c.blue),
        Kpi('INTEREST', fmtLocal(k.interest), localCcy, c.blue),
        Kpi('SAVINGS FROM INCOME', fmtLocalSigned(k.netSavings), 'ex-transfer',
            context.pnlColor(k.netSavings)),
        Kpi('FINAL SAVINGS', fmtLocalSigned(k.finalSavings), 'incl. transfer',
            context.pnlColor(k.finalSavings)),
        Kpi('SAVINGS RATE', '${k.savingsRate.toStringAsFixed(1)}%', 'of income',
            k.savingsRate >= 30 ? c.up : c.gold),
      ]),
      const SizedBox(height: 12),
      ChartGrid([
        ChartCard(
          title: 'Salary Trend',
          subtitle: '$localCcy · monthly',
          child: TrendLineChart(labels: labels, values: salary, color: c.blue),
        ),
        ChartCard(
          title: 'Income vs Actual Expense',
          subtitle: '$localCcy · monthly',
          child: GroupedBarChart(
            labels: labels,
            seriesA: income,
            seriesB: actual,
            colorA: c.blue,
            colorB: c.dn,
            nameA: 'Income',
            nameB: 'Actual',
          ),
        ),
      ]),
      const SizedBox(height: 12),
      DenseCard(
        child: Column(children: [
          const StatRow('Income Component', 'Amount', header: true),
          StatRow('Salary', fmtLocal(k.salary)),
          StatRow('Bonus', fmtLocal(k.bonus)),
          StatRow('Reimburse', fmtLocal(k.reimburse)),
          StatRow('Interest', fmtLocal(k.interest)),
          StatRow('Total Income', fmtLocal(k.income), valueColor: c.blue),
        ]),
      ),
    ]);
  }
}

// ══════════════════════════════════════════════════════════════════
//  CATEGORIES
// ══════════════════════════════════════════════════════════════════

class CategoriesPage extends StatelessWidget {
  final Map<String, dynamic> data;
  const CategoriesPage({super.key, required this.data});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final totals = ExpenseAnalytics.categoryTotals(data);
    final actualTotal = totals.fold<double>(0, (a, e) => a + e.value);
    final cats = {for (final e in totals) e.key: e.value};
    final top = totals.isNotEmpty ? totals.first : null;
    final low = totals.isNotEmpty ? totals.last : null;
    final avg = totals.isEmpty ? 0.0 : actualTotal / totals.length;

    return ListView(padding: EdgeInsets.zero, children: [
      KpiGrid(cells: [
        Kpi('ACTUAL EXPENSE', fmtLocal(actualTotal), 'ex-transfer', c.dn),
        Kpi('TOP CATEGORY', top?.key ?? '—',
            top != null ? fmtLocal(top.value) : '', c.dn),
        Kpi('LOWEST CATEGORY', low?.key ?? '—',
            low != null ? fmtLocal(low.value) : '', c.up),
        Kpi('AVG / CATEGORY', fmtLocal(avg), localCcy, c.t2),
      ]),
      const SizedBox(height: 12),
      ChartGrid([
        ChartCard(
          title: 'Category Share',
          subtitle: '$localCcy · ex-transfer',
          child: DonutChart(data: cats, palette: _palette(context)),
        ),
        ChartCard(
          title: 'Category Totals',
          subtitle: '$localCcy · descending',
          height: 240,
          child: GroupedBarChart(
            labels: [for (final e in totals) e.key.substring(0, 3)],
            seriesA: [for (final e in totals) e.value],
            seriesB: List.filled(totals.length, 0),
            colorA: c.dn,
            colorB: Colors.transparent,
            nameA: 'Spend',
            nameB: '',
          ),
        ),
      ]),
      const SizedBox(height: 12),
      DenseCard(
        child: Column(children: [
          const StatRow('Category', 'Total / Share', header: true),
          for (final e in totals)
            StatRow(
              e.key,
              '${fmtLocal(e.value)}   ${actualTotal > 0 ? (e.value / actualTotal * 100).toStringAsFixed(1) : '0'}%',
            ),
        ]),
      ),
    ]);
  }
}

// ══════════════════════════════════════════════════════════════════
//  TRANSFERS & ACCOUNTS
// ══════════════════════════════════════════════════════════════════

class TransferPage extends StatelessWidget {
  final Map<String, dynamic> data;
  final int year;
  final ExpenseStore notifier;
  const TransferPage({
    super.key,
    required this.data,
    required this.year,
    required this.notifier,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final accountA = ExpenseAnalytics.accountARows(data);
    final labels = [
      for (final r in accountA) _monthAbbr('${r['month']}')
    ];
    final localOut = [for (final r in accountA) (r['local_amount'] as num?)?.toDouble() ?? 0];
    final inrIn = [
      for (final r in accountA) (r['inr_received'] as num?)?.toDouble() ?? 0
    ];
    final rate = [
      for (final r in accountA)
        ((r['local_amount'] as num?)?.toDouble() ?? 0) > 0
            ? ((r['inr_received'] as num?)?.toDouble() ?? 0) /
                ((r['local_amount'] as num?)!.toDouble())
            : 0.0
    ];

    return ListView(padding: EdgeInsets.zero, children: [
      KpiGrid(cells: [
        Kpi('${localCcy.toUpperCase()} TRANSFERRED', fmtLocal(localOut.fold(0.0, (a, b) => a + b)),
            'to $accountAShort', kLocal),
        Kpi('INR RECEIVED',
            formatINR(inrIn.fold(0.0, (a, b) => a + b)), 'into $accountAShort', kAccountA),
        Kpi('${accountAShort.toUpperCase()} BALANCE', formatINR(ExpenseAnalytics.accountAClosing(data)),
            accountALabel, kAccountA),
        Kpi('${accountBShort.toUpperCase()} BALANCE', formatINR(ExpenseAnalytics.accountBClosing(data)),
            accountBLabel, kAccountB),
      ]),
      const SizedBox(height: 12),
      if (accountA.isNotEmpty)
        ChartGrid([
          ChartCard(
            title: '$localCcy Transferred vs INR Received',
            subtitle: 'per remittance month',
            child: GroupedBarChart(
              labels: labels,
              seriesA: localOut,
              seriesB: inrIn,
              colorA: kLocal,
              colorB: kAccountA,
              nameA: localCcy,
              nameB: 'INR',
            ),
          ),
          ChartCard(
            title: 'Exchange Rate (INR / $localCcy)',
            subtitle: 'effective on transfer',
            child: TrendLineChart(labels: labels, values: rate, color: c.gold),
          ),
        ]),
      const SizedBox(height: 12),
      accountAGrid(notifier, year, data),
      const SizedBox(height: 12),
      accountBGrid(notifier, year, data),
      const SizedBox(height: 24),
    ]);
  }
}

/// Month abbreviation from a month key (e.g. 'jan' -> 'Jan').
String _monthAbbr(String m) =>
    m.isEmpty ? '' : (m[0].toUpperCase() + m.substring(1)).padRight(3).substring(0, 3);

// ══════════════════════════════════════════════════════════════════
//  INVESTMENTS
// ══════════════════════════════════════════════════════════════════

class InvestmentsPage extends StatelessWidget {
  final Map<String, dynamic> data;
  final int year;
  final ExpenseStore notifier;
  const InvestmentsPage({
    super.key,
    required this.data,
    required this.year,
    required this.notifier,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final split = ExpenseAnalytics.investmentSplit(data);
    final byScrip = ExpenseAnalytics.byScrip(data);
    final scripEntries = byScrip.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));

    return ListView(padding: EdgeInsets.zero, children: [
      KpiGrid(cells: [
        Kpi('INVESTED', formatINR(ExpenseAnalytics.investedTotal(data)),
            'MF+Gold+NASDAQ', kInv),
        Kpi('STOCKS DEPLOYED', formatINR(ExpenseAnalytics.stockDeployed(data)),
            'direct equity', kStk),
        Kpi('ASSET CLASSES', '${split.length}', 'tracked', c.t2),
        Kpi('SCRIPS', '${byScrip.length}', 'holdings', c.cyan),
      ]),
      const SizedBox(height: 12),
      ChartGrid([
        ChartCard(
          title: 'Investment Split',
          subtitle: 'INR · by asset class',
          child: DonutChart(data: split, palette: _palette(context)),
        ),
        if (scripEntries.isNotEmpty)
          ChartCard(
            title: 'Deployed by Scrip',
            subtitle: 'INR · direct equity',
            child: GroupedBarChart(
              labels: [for (final e in scripEntries) e.key],
              seriesA: [for (final e in scripEntries) e.value],
              seriesB: List.filled(scripEntries.length, 0),
              colorA: kStk,
              colorB: Colors.transparent,
              nameA: 'Deployed',
              nameB: '',
            ),
          ),
      ]),
      const SizedBox(height: 12),
      investGrid(notifier, year, data),
      const SizedBox(height: 12),
      stockGrid(notifier, year, data),
      const SizedBox(height: 24),
    ]);
  }
}

// ══════════════════════════════════════════════════════════════════
//  DATA AUDIT
// ══════════════════════════════════════════════════════════════════

class AuditPage extends ConsumerWidget {
  final Map<String, dynamic> data;
  final int year;
  const AuditPage({super.key, required this.data, required this.year});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final st = ref.watch(expenseStoreProvider);
    final storage = ref.read(localStorageProvider);
    final coverage = ExpenseAnalytics.coverage(data);
    final metrics = ExpenseAnalytics.auditMetrics(data);
    final issues = ExpenseAnalytics.audit(data, year);
    final rowsImported = coverage.values.fold<int>(0, (a, b) => a + b);

    String fmt(String? iso) {
      if (iso == null) return '—';
      final d = DateTime.tryParse(iso);
      if (d == null) return iso;
      String p(int n) => n.toString().padLeft(2, '0');
      return '${d.year}-${p(d.month)}-${p(d.day)} ${p(d.hour)}:${p(d.minute)}';
    }

    final metricRows = <MapEntry<String, String>>[
      MapEntry('Sections with data', '${metrics['sections']}'),
      MapEntry('Total rows', '${metrics['rows']}'),
      MapEntry('Total columns ($localLabel)', '${metrics['columns']}'),
      MapEntry('Blank values', '${metrics['blank']}'),
      MapEntry('Zero values', '${metrics['zero']}'),
      MapEntry('Future / unfilled months', '${metrics['future_months']}'),
      MapEntry('New categories', '${metrics['new_categories']}'),
      MapEntry('Total mismatches', '${metrics['mismatches']}'),
      MapEntry('Duplicate months', '${metrics['duplicate_months']}'),
      MapEntry('Negative balances', '${metrics['negative_balances']}'),
    ];

    Color sevColor(String s) => switch (s) {
          'error' => c.dn,
          'warn' => c.gold,
          _ => c.t3,
        };
    IconData sevIcon(String s) => switch (s) {
          'error' => LucideIcons.xCircle,
          'warn' => LucideIcons.alertTriangle,
          _ => LucideIcons.info,
        };

    return ListView(padding: EdgeInsets.zero, children: [
      KpiGrid(cells: [
        Kpi('ROWS IMPORTED', '$rowsImported', 'across sections', c.up),
        Kpi('SECTIONS', '${coverage.values.where((v) => v > 0).length}',
            'with data', c.blue),
        Kpi('ISSUES', '${issues.where((i) => i.severity != 'info').length}',
            'warnings/errors', c.gold),
        Kpi('YEAR', '$year', 'audited sheet', c.t2),
      ]),
      const SizedBox(height: 12),
      DenseCard(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(LucideIcons.cloud, size: 15, color: c.blue),
            const SizedBox(width: 8),
            Text('Google Drive Sync', style: AppTextStyles.heading3(c.t1)),
            const Spacer(),
            _AuditSyncChip(status: st.syncStatus),
          ]),
          const SizedBox(height: 8),
          StatRow('Sync status', st.syncStatus),
          StatRow('Data version', st.versionId),
          StatRow('Last saved', fmt(st.lastSavedIso ?? storage.getExpenseLastSaved())),
          StatRow('Last recalculated', fmt(st.lastRecalcIso)),
          StatRow('Last uploaded',
              fmt(st.lastUploadedIso ?? storage.getExpenseLastUploaded())),
          StatRow('History entries', '${storage.getExpenseHistory().length}'),
          StatRow('Local versions', '${storage.getExpenseVersionIndex().length}'),
        ]),
      ),
      const SizedBox(height: 12),
      DenseCard(
        child: Column(children: [
          const StatRow('Metric', 'Value', header: true),
          for (final e in metricRows) StatRow(e.key, e.value),
        ]),
      ),
      const SizedBox(height: 12),
      DenseCard(
        child: Column(children: [
          const StatRow('Section', 'Rows imported', header: true),
          for (final e in coverage.entries) StatRow(e.key, '${e.value}'),
        ]),
      ),
      const SizedBox(height: 12),
      DenseCard(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Data Quality Checks', style: AppTextStyles.heading3(c.t1)),
            const SizedBox(height: 10),
            for (final i in issues)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 5),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Icon(sevIcon(i.severity), size: 14, color: sevColor(i.severity)),
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                    margin: const EdgeInsets.only(right: 8),
                    decoration: BoxDecoration(
                        color: sevColor(i.severity).withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(4)),
                    child: Text(i.section,
                        style: AppTextStyles.captionXs(sevColor(i.severity))),
                  ),
                  Expanded(
                      child: Text(i.message,
                          style: AppTextStyles.bodySmall(c.t2))),
                ]),
              ),
          ],
        ),
      ),
      const SizedBox(height: 24),
    ]);
  }
}

/// Global "Last Updated" indicator shown on the Overview: last saved, last
/// recalculated, last Drive sync, and the current data version id — all read
/// live from the shared provider (never hard-coded).
class LastUpdatedBar extends ConsumerWidget {
  const LastUpdatedBar({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final st = ref.watch(expenseStoreProvider);
    final storage = ref.read(localStorageProvider);

    String fmt(String? iso) {
      if (iso == null || iso.isEmpty) return '—';
      final d = DateTime.tryParse(iso);
      if (d == null) return iso;
      String p(int n) => n.toString().padLeft(2, '0');
      return '${d.year}-${p(d.month)}-${p(d.day)} ${p(d.hour)}:${p(d.minute)}';
    }

    final (Color sc, String sl) = switch (st.syncStatus) {
      'success' => (c.up, 'synced'),
      'pending' => (c.gold, 'pending'),
      'failed' => (c.dn, 'failed'),
      'conflict' => (c.dn, 'conflict'),
      _ => (c.t3, 'off'),
    };

    return DenseCard(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (st.recalcFailed)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(children: [
              Icon(LucideIcons.alertOctagon, size: 14, color: c.dn),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                    'Raw data was saved, but dashboard recalculation failed.',
                    style: AppTextStyles.bodySmall(c.dn)),
              ),
            ]),
          ),
        Wrap(spacing: 18, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
          Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(LucideIcons.refreshCw, size: 13, color: st.recalcFailed ? c.dn : c.up),
            const SizedBox(width: 6),
            Text('Last Updated', style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12)),
          ]),
          _kv(context, 'Saved', fmt(st.lastSavedIso ?? storage.getExpenseLastSaved())),
          _kv(context, 'Recalculated', fmt(st.lastRecalcIso)),
          _kv(context, 'Drive sync', '${fmt(st.lastUploadedIso ?? storage.getExpenseLastUploaded())}  ($sl)', valueColor: sc),
          _kv(context, 'Version', st.versionId, valueColor: c.blue),
        ]),
      ]),
    );
  }

  Widget _kv(BuildContext context, String k, String v, {Color? valueColor}) {
    final c = context.colors;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Text('$k: ', style: AppTextStyles.captionXs(c.t3)),
      Text(v, style: AppTextStyles.monoXs(valueColor ?? c.t2)),
    ]);
  }
}

/// Recent-changes panel for the Raw Data Viewer: shows the latest saved edits
/// with their cell reference, previous value, new value and time — so the raw
/// viewer reflects "what changed" after every save.
class RawChangesPanel extends ConsumerWidget {
  const RawChangesPanel({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    ref.watch(expenseStoreProvider); // rebuild after each save
    final storage = ref.read(localStorageProvider);
    final history = storage.getExpenseHistory().reversed.take(8).toList();
    if (history.isEmpty) return const SizedBox.shrink();
    return DenseCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(LucideIcons.history, size: 15, color: c.accent),
          const SizedBox(width: 8),
          Text('Recent Changes', style: AppTextStyles.heading3(c.t1)),
          const SizedBox(width: 8),
          Text('latest saved edits · restore via Data Entry → Version history',
              style: AppTextStyles.captionXs(c.t3)),
        ]),
        const SizedBox(height: 8),
        for (final h in history)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 3),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Container(
                margin: const EdgeInsets.only(right: 8, top: 1),
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                decoration: BoxDecoration(
                    color: c.blue.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(4)),
                child: Text('${h['action']}'.toUpperCase(),
                    style: AppTextStyles.captionXs(c.blue)),
              ),
              Expanded(
                child: Text(
                  '${h['sourceSection']}'
                  '${'${h['month']}'.isEmpty ? '' : ' · ${h['month']}'}'
                  ' · ${h['sourceColumn']}'
                  '${'${h['sourceCellAddress']}'.isEmpty ? '' : ' (${h['sourceCellAddress']})'}'
                  '  ${h['oldValue']} → ${h['newValue']}',
                  style: AppTextStyles.bodySmall(c.t2),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 8),
              Text('${h['timestamp']}', style: AppTextStyles.captionXs(c.t4)),
            ]),
          ),
      ]),
    );
  }
}

/// Compact Drive sync status chip for the audit page.
class _AuditSyncChip extends StatelessWidget {
  final String status;
  const _AuditSyncChip({required this.status});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final (Color color, String label) = switch (status) {
      'success' => (c.up, 'Synced'),
      'pending' => (c.gold, 'Pending'),
      'failed' => (c.dn, 'Failed'),
      'conflict' => (c.dn, 'Conflict'),
      _ => (c.t3, 'Not connected'),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Text(label, style: AppTextStyles.captionXs(color)),
    );
  }
}
