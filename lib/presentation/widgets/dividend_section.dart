import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/providers/dividend_provider.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';

/// Dividend income ledger and goal tracker.
///
/// Structured as: goal gap → income KPIs → path to the goal (corpus ladder,
/// projection, SIP needed) → the ledger itself → cash-flow calendar → funds.
/// The ordering is deliberate: the gap to the goal is the only number that
/// answers "am I there yet", so it leads; per-holding detail comes last.
class DividendSection extends ConsumerWidget {
  const DividendSection({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bookAsync = ref.watch(dividendBookProvider);

    return bookAsync.when(
      loading: () => const Padding(
        padding: EdgeInsets.symmetric(vertical: 40),
        child: DensePulseLoader(label: 'Building dividend ledger…'),
      ),
      error: (e, _) => ErrorRetry(
        title: 'Unable to load dividend data',
        detail: '$e',
        onRetry: () => ref.invalidate(dividendBookProvider),
      ),
      data: (book) {
        if (!book.hasData) {
          return const DenseEmptyCard(
            icon: LucideIcons.coins,
            title: 'No holdings to measure',
            sub: 'Add stocks or funds and the dividend ledger builds itself.',
          );
        }
        return Column(children: [
          _GoalGapBar(book: book),
          const SizedBox(height: 12),
          _IncomeKpiGrid(book: book),
          const SizedBox(height: 12),
          _PathToGoal(book: book),
          const SizedBox(height: 12),
          if (book.alerts.isNotEmpty) ...[
            _IncomeAlerts(book: book),
            const SizedBox(height: 12),
          ],
          _IncomeLedger(book: book),
          const SizedBox(height: 12),
          // Side by side when there is room; stacked below ~1250px, where the
          // sector card gets too narrow for its header and bars.
          LayoutBuilder(builder: (context, box) {
            if (box.maxWidth < 1250) {
              return Column(children: [
                _PayoutCalendar(book: book),
                const SizedBox(height: 12),
                _IncomeBySector(book: book),
              ]);
            }
            return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(flex: 3, child: _PayoutCalendar(book: book)),
              const SizedBox(width: 12),
              Expanded(flex: 2, child: _IncomeBySector(book: book)),
            ]);
          }),
          const SizedBox(height: 12),
          _FundIncomeTable(book: book),
        ]);
      },
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  GOAL GAP BAR — "here is now, here is the goal"
// ══════════════════════════════════════════════════════════════

class _GoalGapBar extends ConsumerWidget {
  final DividendBook book;
  const _GoalGapBar({required this.book});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final goal = book.goal;
    final income = book.income;
    final pct = (goal.achievedPct / 100).clamp(0.0, 1.0);
    final accent = goal.onTrack ? c.up : c.gold;

    return DenseCard(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('DIVIDEND INCOME · PER MONTH',
                style: AppTextStyles.labelXs(c.t3)),
            const SizedBox(height: 6),
            Text(formatINR(income.monthlyGross),
                style: AppTextStyles.stat2xl(c.t1).copyWith(fontSize: 26)),
            const SizedBox(height: 3),
            Text('${formatINR(income.annualGross)} a year gross',
                style: AppTextStyles.captionXs(c.t3)),
          ]),
          const SizedBox(width: 24),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(bottom: 20),
              child: Container(
                height: 2,
                decoration: BoxDecoration(
                  gradient: LinearGradient(colors: [c.bd, accent]),
                ),
              ),
            ),
          ),
          const SizedBox(width: 24),
          Flexible(
            child: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Text('GOAL · PER MONTH', style: AppTextStyles.labelXs(c.t3)),
              const SizedBox(height: 6),
              Text(formatINR(goal.monthly),
                  style: AppTextStyles.stat2xl(accent).copyWith(fontSize: 22),
                  maxLines: 1),
              const SizedBox(height: 3),
              Text(
                  goal.onTrack
                      ? 'Goal covered'
                      : 'Short by ${formatINR(goal.gapMonthly)}/month',
                  style: AppTextStyles.captionXs(goal.onTrack ? c.up : c.t3),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
            ]),
          ),
          const SizedBox(width: 16),
          HeaderButton(
            icon: Icon(LucideIcons.target, size: 13, color: c.t2),
            text: 'Set Goal',
            onTap: () => showDialog(
                context: context, builder: (_) => const DividendGoalDialog()),
          ),
        ]),
        const SizedBox(height: 14),

        // ── Progress rail: 20 segments, lit in proportion to the goal ──
        LayoutBuilder(builder: (context, box) {
          const segments = 24;
          final lit = (pct * segments).round();
          return Row(
            children: List.generate(segments, (i) {
              final on = i < lit;
              return Expanded(
                child: Container(
                  height: 12,
                  margin: const EdgeInsets.only(right: 2),
                  decoration: BoxDecoration(
                    color: on ? accent.withValues(alpha: 0.85) : c.bg3,
                    borderRadius: BorderRadius.circular(2),
                    border: on ? null : Border.all(color: c.bd),
                  ),
                ),
              );
            }),
          );
        }),
        const SizedBox(height: 10),
        // Wrap, not Row: four stats plus the assumptions note overflow a
        // narrow window, and these are exactly the figures worth keeping
        // readable when the window is small.
        Wrap(spacing: 20, runSpacing: 8, children: [
          _railStat(context, '${goal.achievedPct.toStringAsFixed(1)}%',
              'OF GOAL', accent),
          _railStat(context, '${income.blendedYield.toStringAsFixed(2)}%',
              'BLENDED YIELD', c.blue),
          _railStat(context, '${income.yieldOnCost.toStringAsFixed(2)}%',
              'YIELD ON COST', c.cyan),
          _railStat(
              context,
              goal.yearsToGoal == null ? '10 yr+' : '${goal.yearsToGoal} yr',
              'TO GOAL',
              goal.yearsToGoal == null ? c.dn : c.up),
        ]),
        const SizedBox(height: 8),
        Text(
            'The rail fills as your monthly dividend income approaches the '
            'goal. BLENDED YIELD is what the whole portfolio pays today; '
            'YIELD ON COST is what it pays against what you originally paid — '
            'on a long-held position that second number is the real one.',
            style: AppTextStyles.captionXs(c.t3)),
        const SizedBox(height: 4),
        Text(
            goal.monthlyInvestment > 0
                ? 'Assumes ${formatINR(goal.monthlyInvestment)}/month added at '
                    '${goal.assumedNewMoneyYieldPct.toStringAsFixed(1)}% and '
                    '${goal.assumedGrowthPct.toStringAsFixed(1)}% DPS growth'
                : 'No fresh capital assumed — only '
                    '${goal.assumedGrowthPct.toStringAsFixed(1)}% DPS growth',
            style: AppTextStyles.captionXs(c.t4)),
      ]),
    );
  }

  Widget _railStat(
      BuildContext context, String value, String label, Color color) {
    final c = context.colors;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Text(value,
          style: AppTextStyles.monoBold(color).copyWith(fontSize: 13)),
      const SizedBox(width: 5),
      Text(label, style: AppTextStyles.labelXs(c.t3)),
    ]);
  }
}

// ══════════════════════════════════════════════════════════════
//  INCOME KPI GRID
// ══════════════════════════════════════════════════════════════

class _IncomeKpiGrid extends StatelessWidget {
  final DividendBook book;
  const _IncomeKpiGrid({required this.book});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final i = book.income;
    return KpiGrid(
      note: 'Dividends are taxed at your slab, so NET OF TAX is the number '
          'that reaches your bank. INCOME-BEARING is the share of the '
          'portfolio that pays anything at all — the rest is pure growth.',
      cells: [
        Kpi('NET OF TAX', formatINR(i.monthlyNet),
            'per month at ${i.taxSlabPct.toStringAsFixed(0)}% slab', c.t1),
        Kpi('FROM STOCKS', formatINR(i.fromStocks),
            '${i.payerCount} payers, ${i.nonPayerCount} non-payers', c.t1),
        Kpi(
            'FROM FUNDS',
            formatINR(i.fromFunds),
            i.reinvestedInFunds > 0
                ? '${formatINR(i.reinvestedInFunds)} reinvested, not paid'
                : 'IDCW plans only',
            c.t1),
        Kpi('INCOME-BEARING', '${i.incomeBearingPct.toStringAsFixed(0)}%',
            'of ${formatCompact(i.totalValue)} portfolio', c.t1),
      ],
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  PATH TO GOAL — corpus ladder + projection + SIP needed
// ══════════════════════════════════════════════════════════════

class _PathToGoal extends StatefulWidget {
  final DividendBook book;
  const _PathToGoal({required this.book});

  @override
  State<_PathToGoal> createState() => _PathToGoalState();
}

class _PathToGoalState extends State<_PathToGoal> {
  int _tab = 0;
  static const _tabs = ['Corpus needed', 'Income path', 'SIP to close the gap'];

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final book = widget.book;

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(context,
            icon: LucideIcons.trendingUp,
            accent: c.up,
            title: 'Path to ${formatINR(book.goal.annual)} a Year',
            subtitle:
                'What the goal costs, when it arrives, and what closes the gap',
            trailing: book.goal.goalYear != null
                ? Row(mainAxisSize: MainAxisSize.min, children: [
                    Text('ON TRACK FOR', style: AppTextStyles.labelXs(c.t3)),
                    const SizedBox(width: 5),
                    Text('${book.goal.goalYear}',
                        style: AppTextStyles.monoBold(c.up)
                            .copyWith(fontSize: 12)),
                  ])
                : Text('NOT REACHED IN 10 YEARS',
                    style: AppTextStyles.labelXs(c.dn))),
        SectionExplainer(
          accent: c.up,
          question: 'What does my income goal actually cost?',
          reading: 'The same goal from three angles — pick a tab.',
          rules: const [
            'Corpus needed: how much capital the goal takes at each yield. A '
                'higher yield needs less capital but usually carries more risk.',
            'Income path: year-by-year projection if you add nothing further '
                'and payouts keep growing at their historical rate.',
            'SIP to close the gap: the monthly amount that gets you there '
                'inside the horizon.',
            'These are projections from past payout behaviour, not promises — '
                'companies can and do cut dividends.',
          ],
          action: 'Compare the SIP figure with what you actually invest each '
              'month. If it is far larger, move the goal or the date rather '
              'than reaching for higher-yield names.',
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
          child: Row(
              children: _tabs.asMap().entries.map((e) {
            final sel = _tab == e.key;
            return Padding(
              padding: const EdgeInsets.only(right: 4),
              child: GestureDetector(
                onTap: () => setState(() => _tab = e.key),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: sel ? c.up.withValues(alpha: 0.08) : Colors.transparent,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(
                        color: sel ? c.up.withValues(alpha: 0.25) : c.bd),
                  ),
                  child: Text(e.value,
                      style: AppTextStyles.bodySmall(sel ? c.up : c.t3).copyWith(
                          fontWeight:
                              sel ? FontWeight.w600 : FontWeight.normal)),
                ),
              ),
            );
          }).toList()),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 8, 14, 14),
          child: _tab == 0
              ? _corpusLadder(context)
              : _tab == 1
                  ? _incomePath(context)
                  : _sipNeeded(context),
        ),
      ]),
    );
  }

  // ── Tab 0: corpus required at each blended yield ──
  Widget _corpusLadder(BuildContext context) {
    final c = context.colors;
    final book = widget.book;
    final ladder = book.corpusLadder;
    if (ladder.isEmpty) return denseFootLabel(context, 'No goal set');

    final maxCorpus = ladder
        .map((r) => r.corpusRequired)
        .fold<double>(0, (a, b) => a > b ? a : b);
    final currentValue = book.income.totalValue;

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      ...ladder.map((r) {
        // Colour by realism: chasing 6% in India means coal, crude and old
        // utilities — real income now, capped growth later.
        final tone = r.yieldPct <= 4.0
            ? c.up
            : r.yieldPct <= 5.0
                ? c.gold
                : c.dn;
        final reached = currentValue >= r.corpusRequired;
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(children: [
            SizedBox(
                width: 74,
                child: Text('${r.yieldPct.toStringAsFixed(1)}% yield',
                    style: AppTextStyles.monoSmall(c.t2))),
            Expanded(
              child: Stack(children: [
                Container(
                  height: 18,
                  decoration: BoxDecoration(
                    color: c.bg3,
                    borderRadius: BorderRadius.circular(3),
                  ),
                ),
                FractionallySizedBox(
                  widthFactor: maxCorpus > 0
                      ? (r.corpusRequired / maxCorpus).clamp(0.02, 1.0)
                      : 0.02,
                  child: Container(
                    height: 18,
                    decoration: BoxDecoration(
                      color: tone.withValues(alpha: 0.75),
                      borderRadius: BorderRadius.circular(3),
                    ),
                  ),
                ),
              ]),
            ),
            const SizedBox(width: 10),
            SizedBox(
                width: 84,
                child: Text(formatCompact(r.corpusRequired),
                    style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 12),
                    textAlign: TextAlign.right)),
            const SizedBox(width: 8),
            SizedBox(
                width: 66,
                child: reached
                    ? Text('REACHED',
                        style: AppTextStyles.labelXs(c.up),
                        textAlign: TextAlign.right)
                    : Text(r.realism == 'achievable' ? '' : r.realism,
                        style: AppTextStyles.captionXs(tone),
                        textAlign: TextAlign.right,
                        overflow: TextOverflow.ellipsis)),
          ]),
        );
      }),
      const SizedBox(height: 8),
      Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: c.bg3,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: c.bd),
        ),
        child: Row(children: [
          Icon(LucideIcons.info, size: 13, color: c.t3),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'You hold ${formatCompact(currentValue)} today at a '
              '${book.income.blendedYield.toStringAsFixed(2)}% blended yield. '
              'The ~4% row is the honest target — the higher rows need deep-value '
              'and PSU concentration that caps long-run growth.',
              style: AppTextStyles.captionXs(c.t3),
            ),
          ),
        ]),
      ),
    ]);
  }

  // ── Tab 1: year-by-year income path ──
  Widget _incomePath(BuildContext context) {
    final c = context.colors;
    final book = widget.book;
    final proj = book.projection;
    if (proj.isEmpty) return denseFootLabel(context, 'No projection available');

    final maxIncome = proj
        .map((p) => p.annualIncome)
        .fold<double>(book.goal.annual, (a, b) => a > b ? a : b);

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      // Goal line marker
      Row(children: [
        Container(width: 14, height: 2, color: c.gold),
        const SizedBox(width: 6),
        Text('GOAL ${formatINR(book.goal.annual)}',
            style: AppTextStyles.labelXs(c.gold)),
        const Spacer(),
        Text('Bars are annual gross dividend income',
            style: AppTextStyles.captionXs(c.t4)),
      ]),
      const SizedBox(height: 10),
      SizedBox(
        height: 150,
        child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: proj.map((p) {
              final h = maxIncome > 0
                  ? (p.annualIncome / maxIncome).clamp(0.02, 1.0)
                  : 0.02;
              final goalH = maxIncome > 0
                  ? (book.goal.annual / maxIncome).clamp(0.0, 1.0)
                  : 0.0;
              return Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 3),
                  child: Tooltip(
                    message: '${p.year}: ${formatINR(p.annualIncome)}/yr '
                        '(${formatINR(p.monthlyIncome)}/mo) · '
                        '${p.goalPct.toStringAsFixed(0)}% of goal\n'
                        'Corpus ${formatCompact(p.corpus)}',
                    child: Stack(
                        alignment: Alignment.bottomCenter,
                        children: [
                          // Goal line across the plot
                          Positioned(
                            bottom: 130 * goalH,
                            left: 0,
                            right: 0,
                            child: Container(height: 1, color: c.gold),
                          ),
                          Column(
                              mainAxisAlignment: MainAxisAlignment.end,
                              children: [
                                Container(
                                  height: 130 * h,
                                  decoration: BoxDecoration(
                                    color: p.goalReached
                                        ? c.up.withValues(alpha: 0.8)
                                        : c.blue.withValues(alpha: 0.55),
                                    borderRadius: const BorderRadius.vertical(
                                        top: Radius.circular(2)),
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text('${p.year % 100}'.padLeft(2, '0'),
                                    style: AppTextStyles.captionXs(c.t4)),
                              ]),
                        ]),
                  ),
                ),
              );
            }).toList()),
      ),
      const SizedBox(height: 8),
      Text(
        book.goal.goalYear != null
            ? 'At ${book.goal.assumedGrowthPct.toStringAsFixed(1)}% DPS growth'
                '${book.goal.monthlyInvestment > 0 ? ' plus ${formatINR(book.goal.monthlyInvestment)}/month of fresh capital' : ''}, '
                'income crosses the goal in ${book.goal.goalYear} '
                '(${book.goal.yearsToGoal} years).'
            : 'Dividend growth alone does not close the gap inside 10 years — '
                'the "SIP to close the gap" tab sizes the fresh capital needed.',
        style: AppTextStyles.captionXs(c.t3),
      ),
    ]);
  }

  // ── Tab 2: SIP needed per horizon ──
  Widget _sipNeeded(BuildContext context) {
    final c = context.colors;
    final g = widget.book.goal;

    Widget row(String horizon, double sip, Color tone) {
      final unreachable = !sip.isFinite;
      return Container(
        margin: const EdgeInsets.only(bottom: 6),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: tone.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: tone.withValues(alpha: 0.2)),
        ),
        child: Row(children: [
          SizedBox(
              width: 90,
              child: Text(horizon, style: AppTextStyles.bodyBold(c.t1))),
          Expanded(
            child: Text(
                sip <= 0 && !unreachable
                    ? 'Already covered by existing income growth'
                    : unreachable
                        ? 'Not reachable — the book yields nothing to compound'
                        : 'Invest ${formatINR(sip)} a month at '
                            '${g.assumedNewMoneyYieldPct.toStringAsFixed(1)}% into new income',
                style: AppTextStyles.bodySmall(c.t2)),
          ),
          Text(unreachable ? '—' : formatINR(sip),
              style: AppTextStyles.monoBold(tone).copyWith(fontSize: 14)),
        ]),
      );
    }

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      row('In 3 years', g.sipNeeded3y, c.dn),
      row('In 5 years', g.sipNeeded5y, c.gold),
      row('In 10 years', g.sipNeeded10y, c.up),
      const SizedBox(height: 4),
      Text(
        'Solved against the same projection the chart draws: existing income '
        'compounds at ${g.assumedGrowthPct.toStringAsFixed(1)}% and fresh money '
        'earns ${g.assumedNewMoneyYieldPct.toStringAsFixed(1)}% from the following year.',
        style: AppTextStyles.captionXs(c.t4),
      ),
    ]);
  }
}

// ══════════════════════════════════════════════════════════════
//  INCOME ALERTS
// ══════════════════════════════════════════════════════════════

class _IncomeAlerts extends StatelessWidget {
  final DividendBook book;
  const _IncomeAlerts({required this.book});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(context,
            icon: LucideIcons.shieldAlert,
            accent: c.gold,
            title: 'What Would Change the Plan',
            subtitle: 'Risks and mechanics that move the income number',
            trailing: denseNum(
                context, '${book.alerts.length} findings', c.t3)),
        SectionExplainer(
          accent: c.gold,
          question: 'What could break this income?',
          reading: 'The assumptions and risks behind the numbers above.',
          rules: const [
            'Red is critical, orange is a warning, blue is a mechanic worth '
                'knowing (tax, record dates, how a figure was derived).',
            'The most serious finding is an unfunded payout — a company paying '
                'more than it earns is paying you out of borrowings.',
          ],
          action: 'Read these before adding to any high-yield name. A yield '
              'that is about to be cut is worth less than a smaller one that '
              'holds.',
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 6, 12, 12),
          child: Column(
              children: book.alerts.map((a) {
            final level = a['level']?.toString() ?? 'info';
            final tone = level == 'critical'
                ? c.dn
                : level == 'warning'
                    ? c.gold
                    : c.blue;
            final icon = level == 'critical'
                ? LucideIcons.alertOctagon
                : level == 'warning'
                    ? LucideIcons.alertTriangle
                    : LucideIcons.info;
            return Container(
              margin: const EdgeInsets.only(bottom: 5),
              padding: const EdgeInsets.all(9),
              decoration: BoxDecoration(
                color: tone.withValues(alpha: 0.07),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: tone.withValues(alpha: 0.2)),
              ),
              child: Row(children: [
                Icon(icon, size: 13, color: tone),
                const SizedBox(width: 8),
                Expanded(
                    child: Text(a['msg']?.toString() ?? '',
                        style: AppTextStyles.bodySmall(c.t1)
                            .copyWith(fontSize: 11.5))),
              ]),
            );
          }).toList()),
        ),
      ]),
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  INCOME LEDGER — per-stock table, ranked by income
// ══════════════════════════════════════════════════════════════

class _IncomeLedger extends StatefulWidget {
  final DividendBook book;
  const _IncomeLedger({required this.book});

  @override
  State<_IncomeLedger> createState() => _IncomeLedgerState();
}

/// Ledger columns. Widths are flex weights — `DenseRow` wraps every cell in an
/// `Expanded`, so cells must not set their own width.
const _ledgerCols = <DenseCol>[
  DenseCol('STOCK', 24, numeric: false),
  DenseCol('DPS', 13),
  DenseCol('YIELD', 13),
  DenseCol('ON COST', 14),
  DenseCol('PAYOUT', 13),
  DenseCol('5Y DPS CAGR', 17),
  DenseCol('PER YEAR', 17),
  DenseCol('% OF INCOME', 20),
  DenseCol('VERDICT', 22),
];

class _IncomeLedgerState extends State<_IncomeLedger> {
  DividendTier? _filter;
  String? _expanded;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final book = widget.book;
    final rows = _filter == null
        ? book.stocks
        : book.stocks.where((s) => s.tier == _filter).toList();

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(context,
            icon: LucideIcons.receipt,
            accent: c.cyan,
            title: 'The Ledger',
            subtitle: 'Ranked by annual income · tap a row for the reasoning',
            trailing: Row(mainAxisSize: MainAxisSize.min, children: [
              _hdr(context, 'ANCHORS', '${book.anchors.length}', c.up),
              const SizedBox(width: 12),
              _hdr(context, 'GROWERS', '${book.growers.length}', c.blue),
              const SizedBox(width: 12),
              _hdr(context, 'TRAPS', '${book.traps.length}',
                  book.traps.isEmpty ? c.t3 : c.dn),
            ])),
        SectionExplainer(
          accent: c.cyan,
          question: 'Which holdings actually pay me?',
          reading: 'Every payer ranked by the rupees it sends you in a year.',
          rules: const [
            'DPS is the dividend per share used here; YIELD is that against '
                'today\'s price, ON COST against what you paid — on an old '
                'holding, yield on cost is the one that reflects your position.',
            'PAYOUT is the share of profit being paid out. Comfortably under '
                '100% is funded; above it, the payout is not covered by profit.',
            '5Y DPS CAGR shows whether the payment itself is growing.',
            'VERDICT sorts each name: an anchor pays reliably, a grower pays '
                'less now but raises it, a trap looks generous and is not.',
          ],
          action: 'Tap any row to see why it was graded that way. Add to '
              'anchors and growers; treat every trap as a reason to stop '
              'adding, whatever the headline yield says.',
        ),

        // Tier filter chips
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 4, 14, 8),
          child: Wrap(spacing: 5, children: [
            _chip(context, 'All ${book.stocks.length}', null, c.t2),
            _chip(context, 'Income anchors', DividendTier.anchor, c.up),
            _chip(context, 'Growers', DividendTier.grower, c.blue),
            _chip(context, 'Modest', DividendTier.modest, c.t3),
            _chip(context, 'Yield traps', DividendTier.trap, c.dn),
            _chip(context, 'Non-payers', DividendTier.none, c.t4),
          ]),
        ),

        denseColumnHeader(context, _ledgerCols),

        if (rows.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 20),
            child: Center(
                child: Text('Nothing in this bucket',
                    style: AppTextStyles.captionXs(c.t3))),
          )
        else
          ...rows.map((s) => _row(context, s)),

        Padding(
          padding: const EdgeInsets.fromLTRB(14, 8, 14, 12),
          child: Text(
            'DPS basis: ${book.dpsBasis.isEmpty ? "trailing 12 months or last full FY, whichever is higher" : book.dpsBasis}. '
            'Yield is computed from DPS ÷ live price, never read from a provider field.',
            style: AppTextStyles.captionXs(c.t4),
          ),
        ),
      ]),
    );
  }

  Widget _hdr(BuildContext context, String label, String value, Color color) {
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Text(label, style: AppTextStyles.labelXs(context.colors.t3)),
      const SizedBox(width: 5),
      Text(value, style: AppTextStyles.monoBold(color).copyWith(fontSize: 12)),
    ]);
  }

  Widget _chip(
      BuildContext context, String label, DividendTier? tier, Color tone) {
    final c = context.colors;
    final sel = _filter == tier;
    return GestureDetector(
      onTap: () => setState(() => _filter = tier),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
        decoration: BoxDecoration(
          color: sel ? tone.withValues(alpha: 0.12) : Colors.transparent,
          borderRadius: BorderRadius.circular(4),
          border:
              Border.all(color: sel ? tone.withValues(alpha: 0.35) : c.bd),
        ),
        child: Text(label.toUpperCase(),
            style: AppTextStyles.labelXs(sel ? tone : c.t3)),
      ),
    );
  }

  Widget _row(BuildContext context, DividendStock s) {
    final c = context.colors;
    final total = widget.book.income.annualGross;
    final shareOfIncome = total > 0 ? s.annualIncome / total * 100 : 0.0;
    final tone = _tierColor(context, s.tier);
    final isOpen = _expanded == s.symbol;

    return Column(children: [
      DenseRow(
        cols: _ledgerCols,
        onTap: () => setState(() => _expanded = isOpen ? null : s.symbol),
        highlighted: isOpen,
        cells: [
          // STOCK — tier-coloured spine + symbol/sector
          Row(children: [
            Container(
              width: 3,
              height: 22,
              decoration: BoxDecoration(
                color: tone,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(width: 7),
            Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(s.symbol,
                        style: AppTextStyles.bodyBold(c.t1)
                            .copyWith(fontSize: 12),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis),
                    Text(s.sector,
                        style: AppTextStyles.captionXs(c.t4),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis),
                  ]),
            ),
          ]),
          Text(s.dps > 0 ? '₹${s.dps.toStringAsFixed(2)}' : '—',
              style: AppTextStyles.monoSmall(c.t2),
              textAlign: TextAlign.right,
              maxLines: 1),
          Text(s.yieldPct > 0 ? '${s.yieldPct.toStringAsFixed(2)}%' : '—',
              style: AppTextStyles.monoBold(s.yieldPct >= 4 ? c.up : c.t2)
                  .copyWith(fontSize: 12),
              textAlign: TextAlign.right,
              maxLines: 1),
          Text(s.yieldOnCost > 0 ? '${s.yieldOnCost.toStringAsFixed(2)}%' : '—',
              style: AppTextStyles.monoSmall(c.cyan),
              textAlign: TextAlign.right,
              maxLines: 1),
          Text(s.payoutRatio > 0 ? '${s.payoutRatio.toStringAsFixed(0)}%' : '—',
              style:
                  AppTextStyles.monoSmall(s.payoutRatio > 100 ? c.dn : c.t2),
              textAlign: TextAlign.right,
              maxLines: 1),
          Text(
              s.yearsPaid >= 2
                  ? '${s.growthCagr >= 0 ? '+' : ''}${s.growthCagr.toStringAsFixed(1)}%'
                  : '—',
              style: AppTextStyles.monoSmall(s.growthCagr > 0
                  ? c.up
                  : s.growthCagr < 0
                      ? c.dn
                      : c.t3),
              textAlign: TextAlign.right,
              maxLines: 1),
          Text(s.annualIncome > 0 ? formatINR(s.annualIncome) : '—',
              style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 12),
              textAlign: TextAlign.right,
              maxLines: 1),
          // % OF INCOME — mini bar + figure
          Row(children: [
            Expanded(
              child: Stack(children: [
                Container(height: 6, color: c.bg3),
                FractionallySizedBox(
                  widthFactor: (shareOfIncome / 100).clamp(0.0, 1.0),
                  child: Container(height: 6, color: tone),
                ),
              ]),
            ),
            const SizedBox(width: 6),
            SizedBox(
                width: 32,
                child: Text('${shareOfIncome.toStringAsFixed(0)}%',
                    style: AppTextStyles.monoXs(c.t3),
                    textAlign: TextAlign.right,
                    maxLines: 1)),
          ]),
          Align(
            alignment: Alignment.centerRight,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
              decoration: BoxDecoration(
                color: tone.withValues(alpha: 0.10),
                border: Border.all(color: tone.withValues(alpha: 0.22)),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(s.tierLabel.toUpperCase(),
                  style: AppTextStyles.labelXs(tone),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
            ),
          ),
        ],
      ),
      if (isOpen) _detail(context, s, tone),
    ]);
  }

  Widget _detail(BuildContext context, DividendStock s, Color tone) {
    final c = context.colors;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 10, 14, 12),
      decoration: BoxDecoration(
        color: c.bg3,
        border: Border(
            left: BorderSide(color: tone, width: 2),
            bottom: BorderSide(color: c.bd)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(s.reason, style: AppTextStyles.bodySmall(c.t1)),
        const SizedBox(height: 8),
        Wrap(spacing: 18, runSpacing: 6, children: [
          _fact(context, 'HOLDING',
              '${s.shares.toStringAsFixed(0)} sh @ ₹${s.avgCost.toStringAsFixed(2)}'),
          _fact(context, 'VALUE', formatINR(s.value)),
          _fact(context, 'PER MONTH', formatINR(s.monthlyIncome)),
          _fact(context, 'YEARS PAID',
              s.yearsPaid > 0 ? '${s.yearsPaid}' : 'none on record'),
          _fact(context, 'DPS FROM', s.dpsSourceLabel),
          _fact(context, 'MARKET CAP', s.mcapClass),
          if (s.tdsApplicable)
            _fact(context, 'TDS', 'Applies — over ₹10,000 from this payer'),
        ]),
      ]),
    );
  }

  Widget _fact(BuildContext context, String label, String value) {
    final c = context.colors;
    return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label, style: AppTextStyles.labelXs(c.t4)),
          const SizedBox(height: 2),
          Text(value,
              style: AppTextStyles.monoSmall(c.t2).copyWith(fontSize: 11)),
        ]);
  }

  Color _tierColor(BuildContext context, DividendTier tier) {
    final c = context.colors;
    switch (tier) {
      case DividendTier.anchor:
        return c.up;
      case DividendTier.grower:
        return c.blue;
      case DividendTier.modest:
        return c.t3;
      case DividendTier.trap:
        return c.dn;
      case DividendTier.none:
        return c.t4;
    }
  }
}

// ══════════════════════════════════════════════════════════════
//  PAYOUT CALENDAR
// ══════════════════════════════════════════════════════════════

class _PayoutCalendar extends StatelessWidget {
  final DividendBook book;
  const _PayoutCalendar({required this.book});

  static const _months = [
    'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
    'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'
  ];

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final cal = book.calendar;
    final maxV = cal.fold<double>(0, (a, b) => a > b ? a : b);
    final peak = book.peakMonth;

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(context,
            icon: LucideIcons.calendarDays,
            accent: c.accent,
            title: 'When the Cash Lands',
            subtitle:
                'Direct equity, averaged over the last 3 fiscal years of ex-dates',
            trailing: peak == null
                ? Text('NO SCHEDULE', style: AppTextStyles.labelXs(c.t3))
                : Row(mainAxisSize: MainAxisSize.min, children: [
                    Text('PEAK', style: AppTextStyles.labelXs(c.t3)),
                    const SizedBox(width: 5),
                    Text(_months[peak - 1],
                        style: AppTextStyles.monoBold(c.accent)
                            .copyWith(fontSize: 12)),
                  ])),
        SectionExplainer(
          accent: c.accent,
          question: 'When does the money arrive?',
          reading: 'Your dividend cash spread across the twelve months.',
          rules: const [
            'Built from the ex-dates of the last three fiscal years, averaged '
                '— so it is the usual pattern, not a confirmed schedule.',
            'Indian payouts cluster heavily around the mid-year season, so '
                'expect tall bars in a few months and empty ones elsewhere.',
            'Hover a bar to read that month\'s amount.',
          ],
          action: 'Plan around the lumpiness. If you intend to live on this '
              'income, keep the quiet months funded from elsewhere rather than '
              'expecting a monthly salary.',
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 8, 14, 14),
          child: maxV <= 0
              ? denseFootLabel(context,
                  'No ex-date history available for the current holdings')
              : SizedBox(
                  height: 128,
                  child: Row(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: List.generate(12, (i) {
                        final v = cal[i];
                        final h = maxV > 0 ? (v / maxV) : 0.0;
                        return Expanded(
                          child: Padding(
                            padding:
                                const EdgeInsets.symmetric(horizontal: 3),
                            child: Tooltip(
                              message: v > 0
                                  ? '${_months[i]}: ${formatINR(v)}'
                                  : '${_months[i]}: no payouts on record',
                              child: Column(
                                  mainAxisAlignment: MainAxisAlignment.end,
                                  children: [
                                    if (v > 0)
                                      Text(formatCompact(v),
                                          style: AppTextStyles.monoXs(c.t3)),
                                    const SizedBox(height: 3),
                                    Container(
                                      height: (90 * h).clamp(2.0, 90.0),
                                      decoration: BoxDecoration(
                                        color: v > 0
                                            ? c.accent.withValues(
                                                alpha: 0.35 + 0.5 * h)
                                            : c.bg3,
                                        borderRadius:
                                            const BorderRadius.vertical(
                                                top: Radius.circular(2)),
                                      ),
                                    ),
                                    const SizedBox(height: 4),
                                    Text(_months[i],
                                        style:
                                            AppTextStyles.captionXs(c.t4)),
                                  ]),
                            ),
                          ),
                        );
                      })),
                ),
        ),
      ]),
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  INCOME BY SECTOR
// ══════════════════════════════════════════════════════════════

class _IncomeBySector extends StatelessWidget {
  final DividendBook book;
  const _IncomeBySector({required this.book});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final rows = book.bySector;

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(context,
            icon: LucideIcons.pieChart,
            accent: c.gold,
            title: 'Where the Income Comes From',
            subtitle: 'Sector split of dividend cash, not of capital'),
        SectionExplainer(
          accent: c.gold,
          compact: true,
          question: 'Is my income concentrated?',
          reading: 'Which industries the cash comes from.',
          rules: const [
            'This splits the income, not the capital — a small sector can '
                'still produce most of your dividends.',
            'Over 30% from one sector turns amber, over 50% turns red.',
            'Income concentration bites differently from price '
                'concentration: one sector-wide payout cut removes that slice '
                'of your cash flow at once.',
          ],
          action: 'If one sector dominates, add payers from a different one '
              'before adding more of the same — even if the yield on offer '
              'there is lower.',
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 8, 14, 14),
          child: rows.isEmpty
              ? denseFootLabel(context, 'No dividend income yet')
              : Column(
                  children: rows.map((r) {
                  final tone = r.pct > 50
                      ? c.dn
                      : r.pct > 30
                          ? c.gold
                          : c.up;
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Row(children: [
                      SizedBox(
                          width: 92,
                          child: Text(r.sector,
                              style: AppTextStyles.bodySmall(c.t2)
                                  .copyWith(fontSize: 11.5),
                              overflow: TextOverflow.ellipsis)),
                      Expanded(
                        child: Stack(children: [
                          Container(
                            height: 14,
                            decoration: BoxDecoration(
                                color: c.bg3,
                                borderRadius: BorderRadius.circular(2)),
                          ),
                          FractionallySizedBox(
                            widthFactor: (r.pct / 100).clamp(0.01, 1.0),
                            child: Container(
                              height: 14,
                              decoration: BoxDecoration(
                                  color: tone.withValues(alpha: 0.7),
                                  borderRadius: BorderRadius.circular(2)),
                            ),
                          ),
                        ]),
                      ),
                      const SizedBox(width: 8),
                      SizedBox(
                          width: 46,
                          child: Text('${r.pct.toStringAsFixed(0)}%',
                              style: AppTextStyles.monoBold(tone)
                                  .copyWith(fontSize: 11),
                              textAlign: TextAlign.right)),
                      const SizedBox(width: 6),
                      SizedBox(
                          width: 62,
                          child: Text(formatINR(r.income),
                              style: AppTextStyles.monoSmall(c.t3),
                              textAlign: TextAlign.right)),
                    ]),
                  );
                }).toList()),
        ),
      ]),
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  FUND INCOME TABLE
// ══════════════════════════════════════════════════════════════

const _fundCols = <DenseCol>[
  DenseCol('SCHEME', 34, numeric: false),
  DenseCol('PLAN', 14, numeric: false),
  DenseCol('VALUE', 16),
  DenseCol('LOOK-THRU YIELD', 20),
  DenseCol('EARNED INSIDE', 18),
  DenseCol('PAID TO YOU', 17),
];

class _FundIncomeTable extends StatelessWidget {
  final DividendBook book;
  const _FundIncomeTable({required this.book});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final funds = book.funds;
    if (funds.isEmpty) return const SizedBox.shrink();

    final reinvested = book.income.reinvestedInFunds;

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(context,
            icon: LucideIcons.briefcase,
            accent: c.blue,
            title: 'Fund Income — Paid vs Reinvested',
            subtitle:
                'Growth plans earn dividends inside the NAV; only IDCW plans pay you',
            trailing: Row(mainAxisSize: MainAxisSize.min, children: [
              Text('REINVESTED', style: AppTextStyles.labelXs(c.t3)),
              const SizedBox(width: 5),
              Text('${formatINR(reinvested)}/yr',
                  style: AppTextStyles.monoBold(c.gold).copyWith(fontSize: 12)),
            ])),
        SectionExplainer(
          accent: c.blue,
          question: 'Why do my funds pay me nothing?',
          reading: 'Because a Growth plan keeps the dividend instead of '
              'sending it.',
          rules: const [
            'The companies inside your funds do pay dividends — EARNED INSIDE '
                'is that money.',
            'In a Growth plan it is reinvested and shows up as a higher NAV. '
                'PAID TO YOU stays zero, and that is working as intended.',
            'Only an IDCW plan actually transfers cash to your account.',
            'Reinvested income compounds untaxed until you sell; paid income '
                'is taxed at your slab in the year you receive it.',
          ],
          action: 'Do not switch a fund to IDCW just to see income arrive — '
              'you would be taxing your own compounding. Switch only if you '
              'genuinely need the cash flow now.',
        ),
        denseColumnHeader(context, _fundCols),
        ...funds.asMap().entries.map((entry) {
          final f = entry.value;
          final tone = f.distributes ? c.up : c.t4;
          return DenseRow(cols: _fundCols, alt: entry.key.isOdd, cells: [
            Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(f.schemeName,
                      style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
                  Text(f.category,
                      style: AppTextStyles.captionXs(c.t4),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
                ]),
            Center(
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                decoration: BoxDecoration(
                  color: tone.withValues(alpha: 0.10),
                  border: Border.all(color: tone.withValues(alpha: 0.22)),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(f.plan, style: AppTextStyles.labelXs(tone)),
              ),
            ),
            Text(formatINR(f.value),
                style: AppTextStyles.monoSmall(c.t2),
                textAlign: TextAlign.right,
                maxLines: 1),
            Text(
                f.lookthroughYield > 0
                    ? '${f.lookthroughYield.toStringAsFixed(2)}%'
                    : 'not disclosed',
                style: f.lookthroughYield > 0
                    ? AppTextStyles.monoSmall(c.t2)
                    : AppTextStyles.captionXs(c.t4),
                textAlign: TextAlign.right,
                maxLines: 1),
            Text(f.lookthroughIncome > 0 ? formatINR(f.lookthroughIncome) : '—',
                style: AppTextStyles.monoSmall(c.gold),
                textAlign: TextAlign.right,
                maxLines: 1),
            Text(f.cashIncome > 0 ? formatINR(f.cashIncome) : '₹0',
                style: AppTextStyles.monoBold(f.cashIncome > 0 ? c.up : c.t4)
                    .copyWith(fontSize: 12),
                textAlign: TextAlign.right,
                maxLines: 1),
          ]);
        }),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 8, 14, 12),
          child: Text(
            'Look-through yield is weighted across each fund\'s disclosed top '
            'holdings, so a fund that discloses only part of its book is not '
            'treated as holding cash for the rest.',
            style: AppTextStyles.captionXs(c.t4),
          ),
        ),
      ]),
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  GOAL DIALOG
// ══════════════════════════════════════════════════════════════

/// Sets the annual dividend goal and the monthly capital assumed alongside it.
class DividendGoalDialog extends ConsumerStatefulWidget {
  const DividendGoalDialog({super.key});

  @override
  ConsumerState<DividendGoalDialog> createState() => _DividendGoalDialogState();
}

class _DividendGoalDialogState extends ConsumerState<DividendGoalDialog> {
  late final TextEditingController _goal;
  late final TextEditingController _sip;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final book = ref.read(dividendBookProvider).value;
    final draft = ref.read(dividendGoalDraftProvider);
    _goal = TextEditingController(
        text: (draft.goalAnnual ?? book?.goal.annual ?? 120000)
            .toStringAsFixed(0));
    _sip = TextEditingController(
        text: (draft.monthlyInvestment ?? book?.goal.monthlyInvestment ?? 0)
            .toStringAsFixed(0));
  }

  @override
  void dispose() {
    _goal.dispose();
    _sip.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final goal = double.tryParse(_goal.text.trim());
    final sip = double.tryParse(_sip.text.trim());
    if (goal == null || goal < 0) {
      setState(() => _error = 'Enter a valid annual goal');
      return;
    }
    if (sip == null || sip < 0) {
      setState(() => _error = 'Enter a valid monthly amount');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      ref.read(dividendGoalDraftProvider.notifier).setGoal(goal);
      ref.read(dividendGoalDraftProvider.notifier).setMonthlyInvestment(sip);
      await saveDividendGoal(ref);
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = 'Could not save: $e';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final goalValue = double.tryParse(_goal.text.trim()) ?? 0;

    return Dialog(
      backgroundColor: c.bg1,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(color: c.bd),
      ),
      child: SizedBox(
        width: 440,
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Icon(LucideIcons.target, size: 16, color: c.up),
                  const SizedBox(width: 8),
                  Text('Dividend Income Goal',
                      style: AppTextStyles.heading3(c.t1)),
                ]),
                const SizedBox(height: 4),
                Text(
                    'The goal drives the gap, the corpus ladder and the '
                    'projection. Nothing here places an order.',
                    style: AppTextStyles.captionXs(c.t3)),
                const SizedBox(height: 18),

                Text('ANNUAL GOAL (₹)', style: AppTextStyles.labelXs(c.t3)),
                const SizedBox(height: 6),
                TextField(
                  controller: _goal,
                  keyboardType: TextInputType.number,
                  style: AppTextStyles.mono(c.t1),
                  onChanged: (_) => setState(() {}),
                  decoration: _fieldDecoration(context, '120000'),
                ),
                const SizedBox(height: 6),
                Text('≈ ${formatINR(goalValue / 12)} a month',
                    style: AppTextStyles.captionXs(c.t3)),
                const SizedBox(height: 8),
                Wrap(spacing: 6, children: [
                  for (final preset in [60000.0, 120000.0, 300000.0, 600000.0])
                    GestureDetector(
                      onTap: () => setState(
                          () => _goal.text = preset.toStringAsFixed(0)),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 9, vertical: 4),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(4),
                          border: Border.all(color: c.bd),
                        ),
                        child: Text('${formatINR(preset / 12)}/mo',
                            style: AppTextStyles.labelXs(c.t3)),
                      ),
                    ),
                ]),

                const SizedBox(height: 18),
                Text('MONTHLY CAPITAL YOU WILL ADD (₹)',
                    style: AppTextStyles.labelXs(c.t3)),
                const SizedBox(height: 6),
                TextField(
                  controller: _sip,
                  keyboardType: TextInputType.number,
                  style: AppTextStyles.mono(c.t1),
                  decoration: _fieldDecoration(context, '0'),
                ),
                const SizedBox(height: 6),
                Text(
                    'Used only to project when the goal arrives — leave at 0 to '
                    'see what existing holdings do on their own.',
                    style: AppTextStyles.captionXs(c.t4)),

                if (_error != null) ...[
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.all(9),
                    decoration: BoxDecoration(
                      color: c.dnBg,
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: c.dn.withValues(alpha: 0.3)),
                    ),
                    child: Row(children: [
                      Icon(LucideIcons.alertCircle, size: 13, color: c.dn),
                      const SizedBox(width: 8),
                      Expanded(
                          child: Text(_error!,
                              style: AppTextStyles.bodySmall(c.dn))),
                    ]),
                  ),
                ],

                const SizedBox(height: 20),
                Row(mainAxisAlignment: MainAxisAlignment.end, children: [
                  TextButton(
                    onPressed:
                        _saving ? null : () => Navigator.of(context).pop(),
                    child:
                        Text('Cancel', style: AppTextStyles.bodySmall(c.t3)),
                  ),
                  const SizedBox(width: 8),
                  HeaderButton(
                    icon: _saving
                        ? const SizedBox(
                            width: 13,
                            height: 13,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white))
                        : const Icon(LucideIcons.check,
                            size: 13, color: Colors.white),
                    text: _saving ? 'Saving…' : 'Save Goal',
                    solidColor: c.up,
                    onTap: _saving ? null : _save,
                  ),
                ]),
              ]),
        ),
      ),
    );
  }

  InputDecoration _fieldDecoration(BuildContext context, String hint) {
    final c = context.colors;
    return InputDecoration(
      hintText: hint,
      hintStyle: AppTextStyles.mono(c.t4),
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
      filled: true,
      fillColor: c.bg2,
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: BorderSide(color: c.bd),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: BorderSide(color: c.up.withValues(alpha: 0.5)),
      ),
    );
  }
}
