import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/providers/providers.dart';
import 'package:aiei_wealth/providers/allocation_provider.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/presentation/widgets/animated_page_wrapper.dart';
import 'package:aiei_wealth/presentation/charts/allocation_charts.dart';
import 'package:aiei_wealth/presentation/dialogs/other_assets_dialog.dart';
import 'package:aiei_wealth/providers/dividend_provider.dart';
import 'package:aiei_wealth/presentation/widgets/dividend_section.dart';
import 'package:aiei_wealth/presentation/widgets/rebalance_plan_section.dart';

/// Which group of allocation sections is on screen.
///
/// The screen used to be a single 10-section scroll, which buried the
/// rebalancing engine and the risk alerts several thousand pixels down. Grouping
/// them keeps every view to one or two screens of related analysis.
enum AllocTab { overview, exposure, overlap, holdings, dividends, rebalance }

extension AllocTabMeta on AllocTab {
  String get label => switch (this) {
        AllocTab.overview => 'Overview',
        AllocTab.exposure => 'Exposure & Risk',
        AllocTab.overlap => 'Overlap',
        AllocTab.holdings => 'Holdings',
        AllocTab.dividends => 'Dividend Income',
        AllocTab.rebalance => 'Rebalance',
      };

  IconData get icon => switch (this) {
        AllocTab.overview => LucideIcons.layoutDashboard,
        AllocTab.exposure => LucideIcons.layoutGrid,
        AllocTab.overlap => LucideIcons.gitPullRequest,
        AllocTab.holdings => LucideIcons.briefcase,
        AllocTab.dividends => LucideIcons.coins,
        AllocTab.rebalance => LucideIcons.scale,
      };

  /// The one question this tab exists to answer, shown under the tab strip.
  /// A tab name says what a view is called; this says why you would open it.
  String get purpose => switch (this) {
        AllocTab.overview =>
          'What is my money made of, and does it match the plan I set?',
        AllocTab.exposure =>
          'Which industries and which few names actually decide my result?',
        AllocTab.overlap =>
          'Am I buying the same companies twice through different funds?',
        AllocTab.holdings =>
          'Is each fund and each stock pulling its weight, or too small to matter?',
        AllocTab.dividends =>
          'What cash does this portfolio pay me, and when does it arrive?',
        AllocTab.rebalance =>
          'Given all of the above — what do I buy or trim, and by how much?',
      };
}

/// Asset Allocation — portfolio exposure analytics in the Data-Dense
/// Dashboard style: hairline DenseCards, compact KPI grids, monospace tables.
/// Charts (donut, treemap, heatmaps) keep their data + interactions; only the
/// chrome around them is dense.
///
/// Layout: a persistent header (value, headline findings, category split) above
/// a tab strip that swaps the analysis below it.
class AllocationScreen extends ConsumerStatefulWidget {
  const AllocationScreen({super.key});

  @override
  ConsumerState<AllocationScreen> createState() => _AllocationScreenState();
}

class _AllocationScreenState extends ConsumerState<AllocationScreen> {
  AllocTab _tab = AllocTab.overview;

  @override
  Widget build(BuildContext context) {
    final ref = this.ref;
    final portfolio = ref.watch(portfolioProvider);
    ref.watch(mfPortfolioProvider);

    return portfolio.when(
      loading: () => const DensePulseLoader(label: 'Loading allocation…'),
      error: (e, _) => ErrorRetry(
        title: 'Unable to load allocation data',
        detail: '$e',
        onRetry: () {
          ref.invalidate(portfolioProvider);
          ref.invalidate(mfPortfolioProvider);
        },
      ),
      data: (_) {
        final alloc = ref.watch(allocationProvider);
        final riskProfile = ref.watch(riskProfileProvider);
        final targets = ref.watch(targetAllocationProvider);
        final exposureAsync = ref.watch(exposureAnalysisProvider);

        return ListView(padding: EdgeInsets.zero, children: [
          // ── SUMMARY BAR ──
          AnimatedListItem(index: 0, child: _AllocSummaryBar(alloc: alloc)),
          const SizedBox(height: 12),

          // ── HEADLINE FINDINGS — the few numbers worth acting on ──
          AnimatedListItem(
            index: 1,
            child: _HeadlineFindings(
              exposure: exposureAsync.value,
              book: ref.watch(dividendBookProvider).value,
              alloc: alloc,
              onJump: (tab) => setState(() => _tab = tab),
            ),
          ),
          const SizedBox(height: 12),

          // ── CATEGORY KPI GRID ──
          AnimatedListItem(index: 2, child: _CategoryKpiGrid(alloc: alloc)),
          const SizedBox(height: 12),

          // ── SECTION TABS ──
          _SectionTabs(
              selected: _tab, onSelect: (t) => setState(() => _tab = t)),
          const SizedBox(height: 12),

          // ── ACTIVE SECTION ──
          if (_tab == AllocTab.dividends)
            const DividendSection()
          else
            exposureAsync.when(
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 40),
                child: DensePulseLoader(label: 'Analyzing portfolio exposure…'),
              ),
              error: (_, __) => _buildFallbackSections(
                  context, alloc, riskProfile, targets, ref),
              data: (exposure) => _buildTabSections(
                  context, alloc, exposure, riskProfile, targets, ref),
            ),

          const SizedBox(height: 36),
        ]);
      },
    );
  }

  /// Dispatches the active tab to its section builder.
  Widget _buildTabSections(
    BuildContext context,
    AllocationData alloc,
    ExposureAnalysis exposure,
    RiskProfile riskProfile,
    Map<String, double> targets,
    WidgetRef ref,
  ) {
    switch (_tab) {
      case AllocTab.overview:
        return _overviewSections(context, alloc, exposure, riskProfile, targets);
      case AllocTab.exposure:
        return _exposureSections(context, exposure);
      case AllocTab.overlap:
        return _overlapSection(context, exposure);
      case AllocTab.holdings:
        return _holdingsSections(context, alloc, exposure);
      case AllocTab.rebalance:
        // The band plan first: it names individual holdings and prices the
        // trade, so it is the part that can be acted on today. The
        // risk-profile engine below answers the slower question of whether
        // the asset-class mix is still the one you chose.
        return Column(children: [
          const RebalancePlanSection(),
          const SizedBox(height: 12),
          _DeepRebalancingEngine(
            alloc: alloc,
            exposure: exposure,
            riskProfile: riskProfile,
            targets: targets,
            ref: ref,
          ),
        ]);
      case AllocTab.dividends:
        return const DividendSection();
    }
  }

  /// Overview: exposure KPIs, composition donut, current vs target.
  Widget _overviewSections(
    BuildContext context,
    AllocationData alloc,
    ExposureAnalysis exposure,
    RiskProfile riskProfile,
    Map<String, double> targets,
  ) {
    final c = context.colors;

    return Column(children: [
      // ── EXPOSURE KPI STRIP (clickable) ──
      AnimatedListItem(index: 2, child: _ExposureKpiStrip(exposure: exposure)),
      const SizedBox(height: 12),

      // The "Portfolio Composition" card used to sit here: a two-slice donut
      // beside a breakdown of Equities and Mutual Funds. It was removed as a
      // strict subset of the Current vs Target table immediately below, which
      // carries the same rows and the same percentages — Equities 47.5%, Mid
      // Cap 0.8%, Flexi Cap 18.3% — and adds the target, the gap and the
      // verdict beside each one. The same split also appears a third time in
      // the category strip above the tabs.
      //
      // The donut was drawing two numbers. A chart that encodes less than the
      // table beside it is decoration, and it cost a screenful of height above
      // the row the reader actually needs.

      // ── ASSET ALLOCATION — CURRENT VS TARGET ──
      AnimatedListItem(
        index: 4,
        child: DenseCard(
          clip: true,
          child: Column(children: [
            denseTableHeader(context,
                icon: LucideIcons.target,
                accent: c.cyan,
                title: 'Asset Allocation — Current vs Target',
                subtitle: 'Based on ${riskProfile.name} risk profile'),
            SectionExplainer(
              accent: c.cyan,
              question: 'Am I where I said I wanted to be?',
              reading: 'Your real split next to your plan, line by line.',
              rules: const [
                'CURRENT is where the money is now. TARGET is the plan.',
                'GAP under 3% shows On Track — that is close enough, do nothing.',
                'Above target reads Reduce, below target reads Increase.',
                'TARGET is editable — click the pencil and type your own number. '
                    'Every gap and the Rebalance tab then measure against your '
                    'plan instead of the default profile.',
                'Winners drift you off target on their own: a stock that doubles '
                    'grows its share without you buying a thing.',
              ],
              action: 'Point this month\'s fresh money at the rows marked '
                  'Increase. Adding is tax-free; selling to fix a gap is not.',
            ),
            _AssetAllocationTable(
              alloc: alloc,
              exposure: exposure,
              targets: targets,
            ),
          ]),
        ),
      ),
    ]);
  }

  /// Exposure & risk: sector look-through, concentration, alerts.
  Widget _exposureSections(BuildContext context, ExposureAnalysis exposure) {
    final c = context.colors;

    return Column(children: [
      // ── SECTOR EXPOSURE: treemap + over/underweight table ──
      AnimatedListItem(
        index: 2,
        child: DenseCard(
          clip: true,
          child: Column(children: [
            denseTableHeader(context,
                icon: LucideIcons.layoutGrid,
                accent: c.gold,
                title: 'Sector Exposure',
                subtitle: 'Look-through · click a sector to drill in',
                trailing: denseNum(
                    context, '${exposure.sectorDetails.length} sectors', c.t3)),
            SectionExplainer(
              accent: c.gold,
              question: 'Which industries am I really betting on?',
              reading:
                  'Your funds opened up and counted with your direct stocks.',
              rules: const [
                'Bigger box = more money. This is look-through: the stocks '
                    'inside your funds are counted here too.',
                'So a bank you own directly and through three funds shows up '
                    'once, at its real full size.',
                'Click any box to see the individual companies inside it.',
                'The table beside it compares each sector with a benchmark '
                    'weight: Overweight means you hold more than the market does.',
                'One sector over about 35% is the level where a single policy '
                    'or rate decision moves your whole portfolio.',
              ],
              action: 'Stop adding to whatever is deepest Overweight, and send '
                  'that money to an Underweight sector instead. This is the '
                  'view a broker app cannot give you.',
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 4, 14, 14),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    flex: 3,
                    child: SectorTreemap(
                      sectors: exposure.sectorExposure,
                      height: 320,
                      sectorHoldings: exposure.sectorHoldings,
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(flex: 2, child: _SectorDeltaTable(exposure: exposure)),
                ],
              ),
            ),
          ]),
        ),
      ),
      const SizedBox(height: 12),

      // ── CONCENTRATION RISK + RISK ALERTS ──
      AnimatedListItem(index: 3, child: _concentrationRow(context, exposure)),
    ]);
  }

  /// Overlap: which stocks you own more than once, and through what.
  Widget _overlapSection(BuildContext context, ExposureAnalysis exposure) {
    final c = context.colors;

    return Column(children: [
      AnimatedListItem(
        index: 2,
        child: DenseCard(
          clip: true,
          child: Column(children: [
            denseTableHeader(context,
                icon: LucideIcons.gitPullRequest,
                accent: c.dn,
                title: 'Portfolio Overlap',
                subtitle: 'Stocks appearing in multiple funds & direct holdings',
                trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                  _hdrStat(context, 'OVERLAP',
                      '${exposure.overlapPct.toStringAsFixed(1)}%',
                      exposure.overlapPct > 30 ? c.dn : c.up),
                  const SizedBox(width: 14),
                  _hdrStat(context, 'DUPLICATES',
                      '${exposure.duplicatePct.toStringAsFixed(1)}%', c.gold),
                ])),
            SectionExplainer(
              accent: c.dn,
              question: 'Am I paying twice for the same bet?',
              reading:
                  'Stocks you own through more than one fund, or a fund and '
                  'directly.',
              rules: const [
                'One row per repeated stock. Each column is a source — a fund, '
                    'or your direct holdings — and the bar is how much that '
                    'source puts into it.',
                'A pink dot means the stock reaches you through three or more '
                    'sources.',
                'The right-hand % is that stock as a share of your whole '
                    'portfolio; over 5% turns pink.',
                'OVERLAP under 20% means your funds genuinely do different '
                    'jobs. Over 30% means you are buying the same portfolio '
                    'twice and paying two fees for it.',
              ],
              action: 'High overlap is fixed by stopping a SIP, not by selling. '
                  'Pause the most duplicated fund and redirect that amount to '
                  'something it does not already own — mid/small cap, '
                  'international or debt.',
            ),
            if (exposure.overlapHoldings.isNotEmpty)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
                decoration: BoxDecoration(
                  color: c.bg3,
                  border: Border(
                      top: BorderSide(color: c.bd),
                      bottom: BorderSide(color: c.bd)),
                ),
                child: Row(children: [
                  SizedBox(
                      width: 110,
                      child: Text('STOCK',
                          style: AppTextStyles.tableHeader(c.t3)
                              .copyWith(fontSize: 10))),
                  ...exposure.overlapSourceNames.map((name) => Expanded(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 3),
                          child: Text(
                            name == 'Direct Stock'
                                ? 'DIRECT'
                                : name.length > 15
                                    ? '${name.substring(0, 12)}…'.toUpperCase()
                                    : name.toUpperCase(),
                            style: AppTextStyles.tableHeader(c.t3)
                                .copyWith(fontSize: 10),
                            textAlign: TextAlign.center,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      )),
                  SizedBox(
                      width: 60,
                      child: Text('TOTAL',
                          style: AppTextStyles.tableHeader(c.blue)
                              .copyWith(fontSize: 10),
                          textAlign: TextAlign.right)),
                ]),
              ),
            OverlapHeatmapGrid(
              overlapHoldings: exposure.overlapHoldings
                  .map((h) => {
                        'stock': h.stock,
                        'total_value': h.totalValue,
                        'exposure_pct': h.exposurePct,
                        'source_count': h.sourceCount,
                        'sources': h.sources,
                      })
                  .toList(),
              sourceNames: exposure.overlapSourceNames,
            ),
            const SizedBox(height: 6),
          ]),
        ),
      ),
    ]);
  }

  /// Holdings: per-fund and per-stock detail.
  Widget _holdingsSections(
      BuildContext context, AllocationData alloc, ExposureAnalysis exposure) {
    final c = context.colors;

    return Column(children: [
      // ── MUTUAL FUND DEEP ANALYSIS ──
      AnimatedListItem(
        index: 2,
        child: DenseCard(
          clip: true,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            denseTableHeader(context,
                icon: LucideIcons.briefcase,
                accent: c.accent,
                title: 'Mutual Fund Deep Analysis',
                subtitle: 'Look-through market cap, style, overlap & performance',
                trailing: denseNum(
                    context, '${exposure.enrichedFunds.length} funds', c.t3)),
            SectionExplainer(
              accent: c.accent,
              question: 'Is each fund doing the job I bought it for?',
              reading: 'One card per fund: return, what it holds, how unique '
                  'it is.',
              rules: const [
                'XIRR is the honest return number — it accounts for the timing '
                    'of every SIP instalment. Plain return % does not.',
                'The LC / MC / SC bar is what the fund actually holds. A '
                    '"Flexi Cap" that is 85% large cap is an index fund with '
                    'an active fee.',
                'Overlap score is how much of this fund you already own '
                    'elsewhere; over 50% turns pink.',
                'Style (Growth / Value / Blend) tells you whether two funds '
                    'will fall at the same time.',
              ],
              action: 'Keep the funds that hold different things from each '
                  'other. A fund with high overlap and a category-average XIRR '
                  'is the one to stop feeding first.',
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 4, 14, 14),
              child: Wrap(
                spacing: 12,
                runSpacing: 12,
                children: exposure.enrichedFunds.asMap().entries.map((entry) {
                  final fundMap = <String, dynamic>{
                    'scheme_name': entry.value.schemeName,
                    'category': entry.value.category,
                    'current_value': entry.value.currentValue,
                    'invested': entry.value.invested,
                    'pnl': entry.value.pnl,
                    'return_pct': entry.value.returnPct,
                    'xirr': entry.value.xirr,
                    'lc_pct': entry.value.lcPct,
                    'mc_pct': entry.value.mcPct,
                    'sc_pct': entry.value.scPct,
                    'top_sector': entry.value.topSector,
                    'style': entry.value.style,
                    'overlap_score': entry.value.overlapScore,
                  };
                  return SizedBox(
                    width: 380,
                    child: AnimatedFundCard(fund: fundMap, index: entry.key),
                  );
                }).toList(),
              ),
            ),
          ]),
        ),
      ),
      const SizedBox(height: 12),

      // ── DIRECT STOCK ANALYSIS & REBALANCING ──
      AnimatedListItem(
        index: 3,
        child: DenseCard(
          clip: true,
          child: Column(children: [
            denseTableHeader(context,
                icon: LucideIcons.barChart3,
                accent: c.blue,
                title: 'Direct Stock Analysis & Rebalancing',
                subtitle: 'Each stock min 5% of equity · rebalance suggestions',
                trailing: denseNum(
                    context, '${exposure.enrichedStocks.length} stocks', c.t3)),
            SectionExplainer(
              accent: c.blue,
              question: 'Is any position too small to matter, or too big?',
              reading: 'Every direct stock sized against your equity, not your '
                  'total.',
              rules: const [
                'ALLOC% is the stock as a share of your direct equity. MIN is '
                    'the 5% floor this app applies.',
                'Below 5% gets an ADD flag and the exact rupees needed to reach '
                    'the floor — a position that small cannot move your '
                    'portfolio, but still costs you attention.',
                'Above 20% gets a HIGH flag: one company now drives your result.',
                'The banner at the top totals what every under-sized position '
                    'needs together.',
              ],
              action: 'For each ADD row, decide honestly: top it up to 5%, or '
                  'exit it. Holding a token quantity is the one choice that '
                  'pays nothing. Send no new money to a HIGH row.',
            ),
            _StockAnalysisTable(
                stocks: exposure.enrichedStocks, equityTotal: alloc.equityValue),
          ]),
        ),
      ),
    ]);
  }

  /// Concentration bars beside the risk-alert list — shown on the Exposure tab.
  Widget _concentrationRow(BuildContext context, ExposureAnalysis exposure) {
    final c = context.colors;
    return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: DenseCard(
                clip: true,
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      denseTableHeader(context,
                          icon: LucideIcons.alertTriangle,
                          accent: c.gold,
                          title: 'Concentration Risk',
                          subtitle: 'Top holdings weight analysis'),
                      SectionExplainer(
                        accent: c.gold,
                        question: 'How much rides on a few names?',
                        reading: 'The share of everything held by your biggest '
                            'holdings.',
                        rules: const [
                          'Top 5: under 25% healthy · 25–40% moderate · over '
                              '40% high risk.',
                          'Top 10: under 40% healthy · 40–60% moderate · over '
                              '60% high risk.',
                          'The bars below rank your ten largest positions, '
                              'after look-through — so a stock you own both '
                              'directly and inside a fund appears at its true '
                              'combined size.',
                          'Concentration is not automatically bad; it is only '
                              'bad when you did not choose it.',
                        ],
                        action: 'If Top 5 reads High Risk, stop adding to those '
                            'five names. Let new money into everything else '
                            'until the percentage falls on its own.',
                      ),
                      Padding(
                        padding: const EdgeInsets.fromLTRB(14, 4, 14, 14),
                        child: ConcentrationBarChart(
                          top5Pct: exposure.concentration.top5Pct,
                          top10Pct: exposure.concentration.top10Pct,
                          topHoldings: exposure.topHoldings
                              .map((h) => {
                                    'stock': h.stock,
                                    'pct': h.pct,
                                    'value': h.value,
                                  })
                              .toList(),
                        ),
                      ),
                    ]),
              ),
            ),
            const SizedBox(width: 12),
            SizedBox(
              width: 320,
              child: DenseCard(
                clip: true,
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      denseTableHeader(context,
                          icon: LucideIcons.shieldAlert,
                          accent: c.dn,
                          title: 'Risk Alerts'),
                      SectionExplainer(
                        accent: c.dn,
                        compact: true,
                        question: 'Anything broken?',
                        reading: 'Automatic warnings from the numbers.',
                        rules: const [
                          'Raised automatically when a holding, sector or top-5 '
                              'weight crosses a safe limit.',
                          'Orange is a warning — watch it. Red is critical — '
                              'act on it.',
                          '"All Clear" means no limit is currently crossed.',
                        ],
                        action: 'Treat each red alert as a rule for the next '
                            'purchase: whatever it names does not receive more '
                            'money this month.',
                      ),
                      if (exposure.concentration.alerts.isEmpty)
                        Padding(
                          padding: const EdgeInsets.fromLTRB(14, 8, 14, 24),
                          child: Column(children: [
                            Icon(LucideIcons.checkCircle2, color: c.up, size: 22),
                            const SizedBox(height: 8),
                            Text('All Clear',
                                style: AppTextStyles.heading3(c.up)),
                            const SizedBox(height: 2),
                            Text('No concentration risks detected',
                                style: AppTextStyles.captionXs(c.t3)),
                          ]),
                        )
                      else
                        ...exposure.concentration.alerts.map((alert) {
                          final isCritical = alert['level'] == 'critical';
                          final alertColor = isCritical ? c.dn : c.gold;
                          return Container(
                            margin: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 3),
                            padding: const EdgeInsets.all(9),
                            decoration: BoxDecoration(
                              color: alertColor.withValues(alpha: 0.07),
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(
                                  color: alertColor.withValues(alpha: 0.2)),
                            ),
                            child: Row(children: [
                              Icon(
                                isCritical
                                    ? LucideIcons.alertOctagon
                                    : LucideIcons.alertTriangle,
                                size: 13,
                                color: alertColor,
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                  child: Text(
                                alert['msg'] ?? '',
                                style: AppTextStyles.bodySmall(c.t1)
                                    .copyWith(fontSize: 11),
                              )),
                            ]),
                          );
                        }),
                      const SizedBox(height: 10),
                    ]),
              ),
            ),
          ],
        );
  }

  /// Fallback when backend unavailable
  Widget _buildFallbackSections(
    BuildContext context,
    AllocationData alloc,
    RiskProfile riskProfile,
    Map<String, double> targets,
    WidgetRef ref,
  ) {
    final c = context.colors;
    return Column(children: [
      Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: c.goldBg,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: c.gold.withValues(alpha: 0.2)),
        ),
        child: Row(children: [
          Icon(LucideIcons.alertCircle, color: c.gold, size: 16),
          const SizedBox(width: 10),
          Expanded(
              child: Text(
            'Advanced exposure analysis unavailable — showing basic allocation data',
            style: AppTextStyles.bodySmall(c.t2),
          )),
        ]),
      ),
      const SizedBox(height: 12),
      AnimatedListItem(
        index: 2,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: DenseCard(
                clip: true,
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      denseTableHeader(context,
                          icon: LucideIcons.pieChart,
                          accent: c.blue,
                          title: 'Portfolio Composition'),
                      Padding(
                        padding: const EdgeInsets.fromLTRB(14, 4, 14, 14),
                        child: AllocationDonutChart(
                          data: {
                            'Equities': alloc.equityValue,
                            'Mutual Funds': alloc.mfValue,
                            if (alloc.goldValue > 0) 'Gold': alloc.goldValue,
                            if (alloc.cashValue > 0) 'Cash': alloc.cashValue,
                          },
                          centerLabel: 'Total',
                          centerValue: formatCompact(alloc.totalPortfolioValue),
                          size: 180,
                        ),
                      ),
                    ]),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: DenseCard(
                clip: true,
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      denseTableHeader(context,
                          icon: LucideIcons.target,
                          accent: c.accent,
                          title: 'Market-Cap Split'),
                      Padding(
                        padding: const EdgeInsets.fromLTRB(14, 4, 14, 14),
                        child: AllocationDonutChart(
                          data: alloc.marketCapValues,
                          centerLabel: 'MCap',
                          size: 180,
                          colors: [c.blue, c.accent, c.gold, c.up],
                        ),
                      ),
                    ]),
              ),
            ),
          ],
        ),
      ),
    ]);
  }
}


// ══════════════════════════════════════════════════════════════
//  SECTION TABS
// ══════════════════════════════════════════════════════════════

class _SectionTabs extends StatelessWidget {
  final AllocTab selected;
  final ValueChanged<AllocTab> onSelect;
  const _SectionTabs({required this.selected, required this.onSelect});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return DenseCard(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 7),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // Six tabs cannot shrink below their labels, and the screen goes down
        // to ~780px at the app's 1024px minimum window. Scroll, not overflow.
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
              children: AllocTab.values.map((tab) {
            final sel = tab == selected;
            return Padding(
              padding: const EdgeInsets.only(right: 4),
              child: GestureDetector(
                onTap: () => onSelect(tab),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 180),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 11, vertical: 7),
                  decoration: BoxDecoration(
                    color: sel
                        ? c.blue.withValues(alpha: 0.10)
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(
                        color: sel
                            ? c.blue.withValues(alpha: 0.28)
                            : Colors.transparent),
                  ),
                  child: Row(children: [
                    Icon(tab.icon, size: 13, color: sel ? c.blue : c.t3),
                    const SizedBox(width: 6),
                    Text(tab.label,
                        style: AppTextStyles.bodySmall(sel ? c.blue : c.t3)
                            .copyWith(
                                fontWeight:
                                    sel ? FontWeight.w600 : FontWeight.normal)),
                  ]),
                ),
              ),
            );
          }).toList()),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(6, 8, 6, 2),
          child: Row(children: [
            Icon(LucideIcons.cornerDownRight, size: 11, color: c.t4),
            const SizedBox(width: 6),
            Expanded(
                child: Text(selected.purpose,
                    style: AppTextStyles.captionXs(c.t3),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis)),
          ]),
        ),
      ]),
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  HEADLINE FINDINGS
// ══════════════════════════════════════════════════════════════

/// A finding worth surfacing above the fold, with the tab that explains it.
class _Finding {
  final String label;
  final String value;
  final String detail;
  final IconData icon;
  final Color tone;
  final AllocTab jumpTo;

  const _Finding({
    required this.label,
    required this.value,
    required this.detail,
    required this.icon,
    required this.tone,
    required this.jumpTo,
  });
}

/// The handful of numbers that should change a decision, pulled out of the
/// sections below so they are not buried behind a scroll.
///
/// Ordered worst-first: whatever is most out of line leads.
class _HeadlineFindings extends StatelessWidget {
  final ExposureAnalysis? exposure;
  final DividendBook? book;
  final AllocationData alloc;
  final ValueChanged<AllocTab> onJump;

  const _HeadlineFindings({
    required this.exposure,
    required this.book,
    required this.alloc,
    required this.onJump,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final findings = _collect(context);
    if (findings.isEmpty) return const SizedBox.shrink();

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(context,
            icon: LucideIcons.zap,
            accent: c.gold,
            title: 'What Matters Right Now',
            subtitle: 'Highest-signal findings · click one to open its section'),
        SectionExplainer(
          accent: c.gold,
          question: 'Where do I start?',
          // Counted, not asserted. While the exposure analysis is still
          // loading only the dividend finding exists, and the line claimed
          // four cards above a single one.
          reading: findings.length == 1
              ? 'Here. The card below is your whole to-do list.'
              : 'Here. The ${_count(findings.length)} cards below are your '
                  'whole to-do list.',
          rules: const [
            'Every card is scored for urgency; only the four worst are shown.',
            'Red = act now. Amber = watch it. Green or blue = already fine.',
            'The colour is the verdict — you do not need to judge the number yourself.',
            'Clicking a card opens the tab that explains where the number came from.',
          ],
          action: 'If every card is green, your allocation is healthy this '
              'month — you can close this page. Only open a tab when a card '
              'turns amber or red.',
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
          child: Row(
              children: findings.map((f) {
            return Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 3),
                child: _card(context, f),
              ),
            );
          }).toList()),
        ),
      ]),
    );
  }

  Widget _card(BuildContext context, _Finding f) {
    final c = context.colors;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: () => onJump(f.jumpTo),
        child: Container(
          padding: const EdgeInsets.all(11),
          decoration: BoxDecoration(
            color: f.tone.withValues(alpha: 0.05),
            borderRadius: BorderRadius.circular(7),
            border: Border.all(color: f.tone.withValues(alpha: 0.2)),
          ),
          child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(children: [
                  Icon(f.icon, size: 12, color: f.tone),
                  const SizedBox(width: 5),
                  Expanded(
                      child: Text(f.label,
                          style: AppTextStyles.labelXs(c.t3),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis)),
                ]),
                const SizedBox(height: 7),
                Text(f.value,
                    style: AppTextStyles.monoBold(f.tone).copyWith(fontSize: 17),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis),
                const SizedBox(height: 3),
                Text(f.detail,
                    style: AppTextStyles.captionXs(c.t3),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis),
              ]),
        ),
      ),
    );
  }

  /// Small counts read better as words than as digits in a sentence.
  String _count(int n) =>
      const {2: 'two', 3: 'three', 4: 'four'}[n] ?? '$n';

  /// Builds the candidate findings, keeps the four most severe.
  List<_Finding> _collect(BuildContext context) {
    final c = context.colors;
    final out = <_Finding>[];
    // Lower rank = more urgent.
    final ranked = <(int, _Finding)>[];

    final e = exposure;
    if (e != null && e.totalValue > 0) {
      final top5 = e.concentration.top5Pct;
      ranked.add((
        top5 > 50 ? 0 : top5 > 40 ? 1 : 6,
        _Finding(
          label: 'TOP 5 CONCENTRATION',
          value: '${top5.toStringAsFixed(1)}%',
          detail: top5 > 40
              ? 'Five names carry the portfolio — one bad quarter hurts'
              : 'Within a sane range for a concentrated book',
          icon: LucideIcons.alertTriangle,
          tone: top5 > 50 ? c.dn : top5 > 40 ? c.gold : c.up,
          jumpTo: AllocTab.exposure,
        )
      ));

      ranked.add((
        e.overlapPct > 40 ? 0 : e.overlapPct > 30 ? 2 : 7,
        _Finding(
          label: 'FUND OVERLAP',
          value: '${e.overlapPct.toStringAsFixed(1)}%',
          detail: e.overlapPct > 30
              ? '${e.overlapHoldings.length} stocks bought more than once — you are paying twice for one bet'
              : 'Funds are pulling in different directions, as intended',
          icon: LucideIcons.gitPullRequest,
          tone: e.overlapPct > 40 ? c.dn : e.overlapPct > 30 ? c.gold : c.up,
          jumpTo: AllocTab.overlap,
        )
      ));

      final sectorPct = e.concentration.topSectorPct;
      ranked.add((
        sectorPct > 35 ? 1 : sectorPct > 25 ? 3 : 8,
        _Finding(
          label: 'TOP SECTOR',
          value: e.concentration.topSectorName,
          detail:
              '${sectorPct.toStringAsFixed(1)}% of look-through exposure sits in one sector',
          icon: LucideIcons.layoutGrid,
          tone: sectorPct > 35 ? c.dn : sectorPct > 25 ? c.gold : c.blue,
          jumpTo: AllocTab.exposure,
        )
      ));

      // Worst target deviation across asset classes.
      if (alloc.rebalanceItems.isNotEmpty) {
        final worst = alloc.rebalanceItems.reduce(
            (a, b) => a.deltaPct.abs() > b.deltaPct.abs() ? a : b);
        final drift = worst.deltaPct.abs();
        ranked.add((
          drift > 15 ? 1 : drift > 8 ? 4 : 9,
          _Finding(
            label: 'LARGEST DRIFT',
            value: '${worst.category} ${worst.deltaPct > 0 ? '+' : ''}'
                '${worst.deltaPct.toStringAsFixed(1)}%',
            detail: '${worst.action} ${formatCompact(worst.amount)} to return '
                'to the ${worst.targetPct.toStringAsFixed(0)}% target',
            icon: LucideIcons.scale,
            tone: drift > 15 ? c.dn : drift > 8 ? c.gold : c.up,
            jumpTo: AllocTab.rebalance,
          )
        ));
      }
    }

    final b = book;
    if (b != null && b.hasData) {
      final g = b.goal;
      ranked.add((
        b.traps.isNotEmpty ? 0 : (g.achievedPct < 25 ? 5 : 8),
        _Finding(
          label: b.traps.isNotEmpty ? 'YIELD TRAP FLAGGED' : 'DIVIDEND GOAL',
          value: b.traps.isNotEmpty
              ? b.traps.first.symbol
              : '${g.achievedPct.toStringAsFixed(0)}%',
          detail: b.traps.isNotEmpty
              ? 'Payout looks unfunded — see the ledger before adding more'
              : '${formatINR(b.income.monthlyGross)}/mo of '
                  '${formatINR(g.monthly)} target',
          icon: LucideIcons.coins,
          tone: b.traps.isNotEmpty
              ? c.dn
              : g.onTrack
                  ? c.up
                  : c.gold,
          jumpTo: AllocTab.dividends,
        )
      ));
    }

    ranked.sort((a, b) => a.$1.compareTo(b.$1));
    for (final r in ranked.take(4)) {
      out.add(r.$2);
    }
    return out;
  }
}


// ══════════════════════════════════════════════════════════════
//  SHARED MICRO-HELPERS
// ══════════════════════════════════════════════════════════════

/// Header stat: uppercase label + mono value, for denseTableHeader trailing.
Widget _hdrStat(BuildContext context, String label, String value, Color color) {
  return Row(mainAxisSize: MainAxisSize.min, children: [
    Text(label, style: AppTextStyles.labelXs(context.colors.t3)),
    const SizedBox(width: 5),
    Text(value, style: AppTextStyles.monoBold(color).copyWith(fontSize: 12)),
  ]);
}

/// Small square-cornered status chip (matches DSignalBadge chrome).
Widget _miniBadge(BuildContext context, String text, Color color,
    {Alignment align = Alignment.centerRight}) {
  return Align(
    alignment: align,
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        border: Border.all(color: color.withValues(alpha: 0.22)),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(text.toUpperCase(), style: AppTextStyles.labelXs(color)),
    ),
  );
}


// ══════════════════════════════════════════════════════════════
//  SUMMARY BAR
// ══════════════════════════════════════════════════════════════

class _AllocSummaryBar extends StatelessWidget {
  final AllocationData alloc;
  const _AllocSummaryBar({required this.alloc});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final pnl = alloc.totalPortfolioValue - alloc.totalInvested;
    final pnlPct =
        alloc.totalInvested > 0 ? pnl / alloc.totalInvested * 100 : 0.0;
    final pnlC = context.pnlColor(pnl);

    return DenseCard(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('PORTFOLIO VALUE', style: AppTextStyles.labelXs(c.t3)),
            const SizedBox(height: 6),
            Text(formatINR(alloc.totalPortfolioValue),
                style: AppTextStyles.stat2xl(c.t1).copyWith(fontSize: 26)),
            const SizedBox(height: 4),
            Row(children: [
              Icon(
                  pnl >= 0
                      ? LucideIcons.arrowUpRight
                      : LucideIcons.arrowDownRight,
                  size: 14,
                  color: pnlC),
              const SizedBox(width: 2),
              Text('${formatSignedINR(pnl)} (${formatPct(pnlPct)})',
                  style: AppTextStyles.monoBold(pnlC).copyWith(fontSize: 12)),
            ]),
          ]),
          const SizedBox(width: 20),
          Container(width: 1, height: 52, color: c.bd),
          const SizedBox(width: 20),
          // Wrap inside Expanded: the three stats plus the button overflow the
          // card at the app's 1024px minimum window, where this screen is only
          // ~780px wide. They stack onto a second line instead.
          Expanded(
            child: Wrap(spacing: 20, runSpacing: 8, children: [
              _InlineStat(
                  label: 'INVESTED', value: formatINR(alloc.totalInvested)),
              _InlineStat(
                  label: 'TOTAL P&L', value: formatSignedINR(pnl), color: pnlC),
              _InlineStat(
                  label: 'RETURN',
                  value: formatPct(alloc.totalPnlPct),
                  color: context.pnlColor(alloc.totalPnlPct)),
            ]),
          ),
          const SizedBox(width: 12),
          HeaderButton(
            icon:
                const Icon(LucideIcons.plusCircle, size: 13, color: Colors.white),
            text: 'Add Assets',
            solidColor: c.blue,
            onTap: () => showDialog(
                context: context, builder: (_) => const OtherAssetsDialog()),
          ),
        ]),
        const SizedBox(height: 10),
        // The one thing a value bar cannot say for itself: every percentage on
        // this page is a share of THIS number, so an asset left unentered
        // inflates all of them.
        Row(children: [
          Icon(LucideIcons.info, size: 11, color: c.t3),
          const SizedBox(width: 7),
          Expanded(
            child: Text(
              'Everything below is measured against this total — stocks, funds, '
              'and whatever you entered under Add Assets. Gold, cash, debt or '
              'property left out there will make every percentage on this page '
              'read too high.',
              style: AppTextStyles.captionXs(c.t3),
            ),
          ),
        ]),
      ]),
    );
  }
}

class _InlineStat extends StatelessWidget {
  final String label, value;
  final Color? color;
  const _InlineStat({required this.label, required this.value, this.color});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label, style: AppTextStyles.labelXs(c.t3)),
          const SizedBox(height: 5),
          Text(value,
              style:
                  AppTextStyles.monoBold(color ?? c.t1).copyWith(fontSize: 14)),
        ]);
  }
}


// ══════════════════════════════════════════════════════════════
//  CATEGORY KPI GRID
// ══════════════════════════════════════════════════════════════

class _CategoryKpiGrid extends StatelessWidget {
  final AllocationData alloc;
  const _CategoryKpiGrid({required this.alloc});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final total = alloc.totalPortfolioValue;
    String pctOf(double v) => total > 0
        ? '${(v / total * 100).toStringAsFixed(1)}% of portfolio'
        : '';
    return KpiGrid(
      note: 'Your money split by asset type. Equity (funds + stocks) moves '
          'together in a crash, so treat those two as one number; gold, cash '
          'and debt are what cushion it.',
      cells: [
        Kpi('MUTUAL FUNDS', formatINR(alloc.mfValue), pctOf(alloc.mfValue),
            c.t1),
        Kpi('DIRECT STOCKS', formatINR(alloc.equityValue),
            pctOf(alloc.equityValue), c.t1),
        Kpi('GOLD', formatINR(alloc.goldValue), pctOf(alloc.goldValue), c.t1),
        Kpi('CASH + DEBT', formatINR(alloc.cashValue + alloc.debtValue),
            pctOf(alloc.cashValue + alloc.debtValue), c.t1),
      ],
    );
  }
}


// ══════════════════════════════════════════════════════════════
//  EXPOSURE KPI STRIP (clickable, expands detail)
// ══════════════════════════════════════════════════════════════

class _ExposureKpiStrip extends StatefulWidget {
  final ExposureAnalysis exposure;
  const _ExposureKpiStrip({required this.exposure});

  @override
  State<_ExposureKpiStrip> createState() => _ExposureKpiStripState();
}

class _ExposureKpiStripState extends State<_ExposureKpiStrip> {
  String? _expandedKPI;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final exposure = widget.exposure;

    // OVERLAP, TOP 5 CONC and TOP SECTOR used to sit here too. All three are
    // candidate cards in "What Matters Right Now" a few hundred pixels above,
    // printing the same numbers to the same decimal place. The two components
    // drew from one pool, so whichever card ranked into the top four was
    // guaranteed to appear twice. A figure repeated twice in one
    // viewport does not reinforce itself; it makes the reader check whether
    // they are actually the same thing. The cards keep them because they are
    // clickable and carry the verdict ("Within a sane range"); this strip is
    // the leftovers that have nowhere else to live.
    final kpis = <Map<String, dynamic>>[
      {'label': 'UNIQUE HOLDINGS', 'value': '${exposure.uniqueHoldings}',
       'icon': LucideIcons.layers, 'color': c.blue,
       'detail': 'Stocks: ${exposure.enrichedStocks.length} | Funds: ${exposure.enrichedFunds.length} | Total tracked: ${exposure.uniqueHoldings}'},
      {'label': '#1 HOLDING', 'value': exposure.concentration.singleStockName,
       'icon': LucideIcons.crown, 'color': c.gold,
       'detail': '${exposure.concentration.singleStockName} is your largest holding at ${exposure.concentration.singleStockPct.toStringAsFixed(1)}% of portfolio.'},
      {'label': 'RISK ALERTS', 'value': '${exposure.concentration.alerts.length}',
       'icon': LucideIcons.shieldAlert,
       'color': exposure.concentration.alerts.isNotEmpty ? c.dn : c.up,
       'detail': exposure.concentration.alerts.isEmpty
           ? 'No active risk alerts. Portfolio is well-balanced.'
           : exposure.concentration.alerts.map((a) => a['msg']).join(' • ')},
    ];

    return DenseCard(
      clip: true,
      child: Column(children: [
        SectionExplainer(
          accent: c.blue,
          borderTop: false,
          question: 'What is my portfolio made of?',
          reading: 'Three numbers that appear nowhere else on this page.',
          rules: const [
            'UNIQUE HOLDINGS — how many different companies you really own, after '
                'opening up the funds. Owning 5 funds is not owning 5 things.',
            'OVERLAP — how much of your money is the same stock bought twice. '
                'Over 30% means your funds are copies of each other.',
            'TOP 5 CONC — what share of everything sits in your five biggest '
                'names. Over 40% and five companies decide your year.',
            'TOP SECTOR / #1 HOLDING — your single biggest bets, whether you '
                'chose them or they simply grew into it.',
            'RISK ALERTS — automatic warnings; 0 is what you want.',
          ],
          action: 'Tap any tile to see the number explained in a sentence. '
              'Anything shown in red is worth fixing before you invest more.',
        ),
        Row(
          children: List.generate(kpis.length * 2 - 1, (i) {
            if (i.isOdd) return Container(width: 1, height: 44, color: c.bd);
            final kpi = kpis[i ~/ 2];
            final isExpanded = _expandedKPI == kpi['label'];
            final color = kpi['color'] as Color;
            return Expanded(
              child: InkWell(
                onTap: () => setState(() =>
                    _expandedKPI = isExpanded ? null : kpi['label'] as String),
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
                  color: isExpanded
                      ? color.withValues(alpha: 0.06)
                      : Colors.transparent,
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Row(children: [
                          Icon(kpi['icon'] as IconData, size: 12, color: color),
                          const SizedBox(width: 6),
                          Flexible(
                              child: Text(kpi['label'] as String,
                                  style: AppTextStyles.labelXs(c.t3),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis)),
                        ]),
                        const SizedBox(height: 6),
                        Text(kpi['value'] as String,
                            style: AppTextStyles.monoBold(color)
                                .copyWith(fontSize: 15),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis),
                      ]),
                ),
              ),
            );
          }),
        ),
        AnimatedCrossFade(
          firstChild: const SizedBox(width: double.infinity, height: 0),
          secondChild: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: c.bg3,
              border: Border(top: BorderSide(color: c.bd)),
            ),
            child: Row(children: [
              Icon(LucideIcons.info, size: 13, color: c.t3),
              const SizedBox(width: 8),
              Expanded(
                  child: Text(
                _expandedKPI != null
                    ? (kpis.firstWhere((k) => k['label'] == _expandedKPI,
                            orElse: () => <String, dynamic>{'detail': ''})['detail']
                        as String? ??
                        '')
                    : '',
                style: AppTextStyles.bodySmall(c.t2),
              )),
            ]),
          ),
          crossFadeState: _expandedKPI != null
              ? CrossFadeState.showSecond
              : CrossFadeState.showFirst,
          duration: const Duration(milliseconds: 250),
        ),
      ]),
    );
  }
}


// ══════════════════════════════════════════════════════════════
//  SECTOR OVER/UNDERWEIGHT TABLE
// ══════════════════════════════════════════════════════════════

class _SectorDeltaTable extends StatelessWidget {
  final ExposureAnalysis exposure;
  const _SectorDeltaTable({required this.exposure});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('OVERWEIGHT / UNDERWEIGHT', style: AppTextStyles.labelXs(c.t3)),
      const SizedBox(height: 8),
      ...exposure.sectorDetails.take(10).map((sd) {
        Color statusColor;
        if (sd.status == 'Overweight') {
          statusColor = c.dn;
        } else if (sd.status == 'Underweight') {
          statusColor = c.blue;
        } else {
          statusColor = c.t3;
        }
        return Container(
          padding: const EdgeInsets.symmetric(vertical: 6),
          decoration: BoxDecoration(
              border: Border(
                  bottom: BorderSide(color: c.bd.withValues(alpha: 0.6)))),
          child: Row(children: [
            Expanded(
                flex: 3,
                child: Text(sd.sector,
                    style: AppTextStyles.bodySmall(c.t1).copyWith(fontSize: 12),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis)),
            SizedBox(
                width: 48,
                child: Text('${sd.currentPct.toStringAsFixed(1)}%',
                    style: AppTextStyles.monoXs(c.t2),
                    textAlign: TextAlign.right)),
            const SizedBox(width: 8),
            SizedBox(
                width: 48,
                child: Text(
                  '${sd.delta >= 0 ? '+' : ''}${sd.delta.toStringAsFixed(1)}%',
                  style: AppTextStyles.monoXs(statusColor)
                      .copyWith(fontWeight: FontWeight.w700),
                  textAlign: TextAlign.right,
                )),
            const SizedBox(width: 8),
            SizedBox(
                width: 86,
                child: _miniBadge(context, sd.status, statusColor)),
          ]),
        );
      }),
    ]);
  }
}


// ══════════════════════════════════════════════════════════════
//  STOCK ANALYSIS TABLE (dense)
// ══════════════════════════════════════════════════════════════

class _StockAnalysisTable extends StatelessWidget {
  final List<EnrichedStock> stocks;
  final double equityTotal;
  const _StockAnalysisTable({required this.stocks, required this.equityTotal});

  static const double _minPct = 5.0; // Minimum 5% per stock

  static const _cols = [
    DenseCol('INSTRUMENT', 3, numeric: false),
    DenseCol('MCAP', 1, numeric: false),
    DenseCol('VALUE', 2),
    DenseCol('ALLOC%', 2),
    DenseCol('MIN', 1),
    DenseCol('GAP', 2),
    DenseCol('REBALANCE', 2),
    DenseCol('P&L', 2),
    DenseCol('STATUS', 2, numeric: false),
  ];

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    if (stocks.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 28),
        child: Column(children: [
          Icon(LucideIcons.barChart3, size: 22, color: c.t3),
          const SizedBox(height: 8),
          Text('No direct stocks in portfolio',
              style: AppTextStyles.bodySmall(c.t3)),
        ]),
      );
    }

    // Sort by value descending
    final sorted = List<EnrichedStock>.from(stocks)
      ..sort((a, b) => b.currentValue.compareTo(a.currentValue));

    // Compute rebalancing data
    final eqTotal = equityTotal > 0 ? equityTotal : 1.0;
    final underCount =
        sorted.where((s) => s.currentValue / eqTotal * 100 < _minPct).length;
    final totalRebalanceNeeded = sorted.fold(0.0, (sum, s) {
      final pct = s.currentValue / eqTotal * 100;
      if (pct < _minPct) return sum + (_minPct / 100 * eqTotal - s.currentValue);
      return sum;
    });
    final totalPnl = sorted.fold(0.0, (sum, s) => sum + s.pnl);

    return Column(children: [
      // Under-allocation banner
      if (underCount > 0)
        Container(
          margin: const EdgeInsets.fromLTRB(14, 0, 14, 10),
          padding: const EdgeInsets.all(9),
          decoration: BoxDecoration(
            color: c.dn.withValues(alpha: 0.05),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: c.dn.withValues(alpha: 0.15)),
          ),
          child: Row(children: [
            Icon(LucideIcons.alertTriangle, size: 13, color: c.dn),
            const SizedBox(width: 8),
            Expanded(
                child: RichText(
                    text: TextSpan(children: [
              TextSpan(
                  text:
                      '$underCount stock${underCount > 1 ? 's' : ''} below 5% minimum',
                  style: AppTextStyles.bodySmall(c.dn)
                      .copyWith(fontWeight: FontWeight.w600)),
              TextSpan(text: ' — need ', style: AppTextStyles.bodySmall(c.t2)),
              TextSpan(
                  text: '₹${formatCompact(totalRebalanceNeeded)}',
                  style: AppTextStyles.monoBold(c.dn).copyWith(fontSize: 12)),
              TextSpan(
                  text: ' to rebalance', style: AppTextStyles.bodySmall(c.t2)),
            ]))),
          ]),
        ),

      denseColumnHeader(context, _cols),
      ...sorted.asMap().entries.map((entry) {
        final s = entry.value;

        // Compute allocation metrics
        final allocPct = s.currentValue / eqTotal * 100;
        final isBelow = allocPct < _minPct;
        final gap = allocPct - _minPct;
        final rebalanceAmt =
            isBelow ? (_minPct / 100 * eqTotal - s.currentValue) : 0.0;

        // MCap chip color (categorical, matches chart palette)
        final mcapColor = s.mcapClass == 'Large Cap'
            ? const Color(0xFF448AFF)
            : s.mcapClass == 'Mid Cap'
                ? const Color(0xFF7C4DFF)
                : const Color(0xFFFF9100);
        final mcapLabel = s.mcapClass == 'Large Cap'
            ? 'LC'
            : s.mcapClass == 'Mid Cap'
                ? 'MC'
                : 'SC';

        // Status
        final statusLabel = isBelow ? 'ADD' : allocPct > 20 ? 'HIGH' : 'OK';
        final statusColor = isBelow ? c.dn : allocPct > 20 ? c.gold : c.up;

        return DenseRow(
          alt: entry.key.isOdd,
          cols: _cols,
          cells: [
            Row(children: [
              if (isBelow)
                Padding(
                  padding: const EdgeInsets.only(right: 4),
                  child: Icon(LucideIcons.alertTriangle, size: 10, color: c.dn),
                ),
              Flexible(
                child: DInstrument(
                    symbol: s.symbol.cleanSymbol,
                    sub: s.sector,
                    up: s.pnl >= 0),
              ),
            ]),
            _miniBadge(context, mcapLabel, mcapColor,
                align: Alignment.centerLeft),
            denseNum(context, formatCompact(s.currentValue), c.t1),
            denseNum(context, '${allocPct.toStringAsFixed(1)}%',
                isBelow ? c.dn : c.t1, bold: true),
            denseNum(context, '${_minPct.toStringAsFixed(0)}%', c.t3),
            denseNum(context, '${gap >= 0 ? '+' : ''}${gap.toStringAsFixed(1)}%',
                isBelow ? c.dn : c.up),
            isBelow
                ? denseNum(context, '+₹${formatCompact(rebalanceAmt)}', c.dn,
                    bold: true)
                : denseNum(context, '—', c.t4),
            denseNum(context, '${s.pnl >= 0 ? '+' : ''}${formatCompact(s.pnl)}',
                context.pnlColor(s.pnl)),
            _miniBadge(context, statusLabel, statusColor),
          ],
        );
      }),

      // Totals footer
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
        decoration: BoxDecoration(
            color: c.bg3, border: Border(top: BorderSide(color: c.bd))),
        child: Row(children: [
          Expanded(
              flex: 3,
              child: denseFootLabel(context, 'TOTAL · ${sorted.length}')),
          const Expanded(flex: 1, child: SizedBox()),
          Expanded(
              flex: 2,
              child: denseNum(context, formatCompact(equityTotal), c.t1,
                  bold: true)),
          Expanded(flex: 2, child: denseNum(context, '100%', c.blue, bold: true)),
          const Expanded(flex: 1, child: SizedBox()),
          const Expanded(flex: 2, child: SizedBox()),
          Expanded(
              flex: 2,
              child: totalRebalanceNeeded > 0
                  ? denseNum(context,
                      '+₹${formatCompact(totalRebalanceNeeded)}', c.dn,
                      bold: true)
                  : const SizedBox()),
          Expanded(
              flex: 2,
              child: denseNum(
                  context,
                  '${totalPnl >= 0 ? '+' : ''}${formatCompact(totalPnl)}',
                  context.pnlColor(totalPnl),
                  bold: true)),
          const Expanded(flex: 2, child: SizedBox()),
        ]),
      ),
    ]);
  }
}


// ══════════════════════════════════════════════════════════════
//  ASSET ALLOCATION TABLE (Current vs Target, editable targets)
// ══════════════════════════════════════════════════════════════

class _AssetAllocationTable extends ConsumerStatefulWidget {
  final AllocationData alloc;
  final ExposureAnalysis exposure;
  final Map<String, double> targets;
  const _AssetAllocationTable(
      {required this.alloc, required this.exposure, required this.targets});

  @override
  ConsumerState<_AssetAllocationTable> createState() =>
      _AssetAllocationTableState();
}

class _AssetAllocationTableState extends ConsumerState<_AssetAllocationTable> {
  String? _editingKey; // which target is being edited
  final _editController = TextEditingController();

  @override
  void dispose() {
    _editController.dispose();
    super.dispose();
  }

  void _startEdit(String targetKey, double currentTarget) {
    setState(() {
      _editingKey = targetKey;
      _editController.text = currentTarget.toStringAsFixed(0);
    });
  }

  void _commitEdit() {
    if (_editingKey == null) return;
    final val = double.tryParse(_editController.text);
    if (val != null) {
      ref.read(customTargetsProvider.notifier).update(_editingKey!, val);
    }
    setState(() => _editingKey = null);
  }

  void _cancelEdit() {
    setState(() => _editingKey = null);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final alloc = widget.alloc;
    final exposure = widget.exposure;
    final targets = widget.targets;
    final total =
        alloc.totalPortfolioValue > 0 ? alloc.totalPortfolioValue : 1.0;
    final hasCustom = ref.watch(customTargetsProvider).isNotEmpty;

    // Build asset class rows
    final rows = <_AssetRow>[];

    // 1. Equities
    if (alloc.equityValue > 0 || targets.containsKey('Large Cap')) {
      final eqPct = alloc.equityValue / total * 100;
      final eqTargetPct = (targets['Large Cap'] ?? 0) +
          (targets['Mid Cap'] ?? 0) +
          (targets['Small Cap'] ?? 0);
      rows.add(_AssetRow('Equities', eqPct, eqTargetPct,
          const Color(0xFF448AFF), LucideIcons.barChart2));
      // Sub-rows by mcap (editable)
      final mcapGroups = <String, double>{};
      for (final s in exposure.enrichedStocks) {
        final cls = s.mcapClass.isNotEmpty ? s.mcapClass : 'Large Cap';
        mcapGroups[cls] = (mcapGroups[cls] ?? 0) + s.currentValue;
      }
      if (mcapGroups.isEmpty && alloc.equityValue > 0) {
        mcapGroups['Large Cap'] = alloc.equityValue;
      }
      for (final cap in ['Large Cap', 'Mid Cap', 'Small Cap', 'Micro Cap']) {
        final val = mcapGroups[cap] ?? 0;
        final pct = val / total * 100;
        final tgt = targets[cap] ?? 0;
        if (pct > 0 || tgt > 0) {
          rows.add(_AssetRow('  $cap', pct, tgt,
              const Color(0xFF448AFF).withValues(alpha: 0.6), null,
              isSub: true, targetKey: cap));
        }
      }
    }

    // 2. Mutual Funds (editable at Flexi Cap key)
    if (alloc.mfValue > 0 || targets.containsKey('Flexi Cap')) {
      final mfPct = alloc.mfValue / total * 100;
      final mfTargetPct = targets['Flexi Cap'] ?? 10;
      rows.add(_AssetRow('Mutual Funds', mfPct, mfTargetPct,
          const Color(0xFF7C4DFF), LucideIcons.briefcase,
          targetKey: 'Flexi Cap'));
      final sortedCats = alloc.mfCategoryTotals.entries.toList()
        ..sort((a, b) => b.value.compareTo(a.value));
      for (final cat in sortedCats) {
        final pct = cat.value / total * 100;
        rows.add(_AssetRow('  ${cat.key}', pct, 0,
            const Color(0xFF7C4DFF).withValues(alpha: 0.6), null,
            isSub: true, hideTarget: true));
      }
    }

    // 3. International (editable)
    {
      final pct = alloc.internationalValue / total * 100;
      final tgt = targets['International'] ?? 5;
      rows.add(_AssetRow('International', pct, tgt, const Color(0xFF00E676),
          LucideIcons.globe,
          targetKey: 'International'));
    }

    // 4. Debt (editable)
    {
      final pct = alloc.debtValue / total * 100;
      final tgt = targets['Debt'] ?? 5;
      rows.add(_AssetRow(
          'Debt', pct, tgt, const Color(0xFF06B6D4), LucideIcons.landmark,
          targetKey: 'Debt'));
    }

    // 5. Gold (editable)
    {
      final pct = alloc.goldValue / total * 100;
      final tgt = targets['Gold'] ?? 5;
      rows.add(_AssetRow(
          'Gold', pct, tgt, const Color(0xFFFFD740), LucideIcons.gem,
          targetKey: 'Gold'));
    }

    // 6. Cash
    if (alloc.cashValue > 0) {
      final pct = alloc.cashValue / total * 100;
      rows.add(_AssetRow(
          'Cash', pct, 0, const Color(0xFF78909C), LucideIcons.wallet));
    }

    // 7. REITs
    if (alloc.reitsValue > 0) {
      final pct = alloc.reitsValue / total * 100;
      rows.add(_AssetRow(
          'REITs', pct, 0, const Color(0xFFF97316), LucideIcons.building));
    }

    return Column(children: [
      // Column header strip
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
        decoration: BoxDecoration(
          color: c.bg3,
          border: Border(
              top: BorderSide(color: c.bd), bottom: BorderSide(color: c.bd)),
        ),
        child: Row(children: [
          Expanded(
              flex: 3,
              child: Text('ASSET CLASS',
                  style:
                      AppTextStyles.tableHeader(c.t3).copyWith(fontSize: 10))),
          SizedBox(
              width: 65,
              child: Text('CURRENT',
                  style: AppTextStyles.tableHeader(c.t3).copyWith(fontSize: 10),
                  textAlign: TextAlign.right)),
          SizedBox(
              width: 75,
              child: Row(mainAxisAlignment: MainAxisAlignment.end, children: [
                Text('TARGET',
                    style:
                        AppTextStyles.tableHeader(c.t3).copyWith(fontSize: 10)),
                const SizedBox(width: 3),
                Icon(LucideIcons.edit3, size: 8, color: c.t4),
              ])),
          SizedBox(
              width: 65,
              child: Text('GAP',
                  style: AppTextStyles.tableHeader(c.t3).copyWith(fontSize: 10),
                  textAlign: TextAlign.right)),
          SizedBox(
              width: 86,
              child: Row(mainAxisAlignment: MainAxisAlignment.end, children: [
                Text('STATUS',
                    style:
                        AppTextStyles.tableHeader(c.t3).copyWith(fontSize: 10)),
                if (hasCustom) ...[
                  const SizedBox(width: 4),
                  InkWell(
                    onTap: () =>
                        ref.read(customTargetsProvider.notifier).reset(),
                    child: Tooltip(
                        message: 'Reset to defaults',
                        child:
                            Icon(LucideIcons.rotateCcw, size: 9, color: c.blue)),
                  ),
                ],
              ])),
        ]),
      ),
      ...rows.map((r) {
        final gap = r.currentPct - r.targetPct;
        final absGap = gap.abs();
        final status = r.hideTarget
            ? ''
            : absGap < 3
                ? 'On Track'
                : gap > 0
                    ? 'Reduce'
                    : 'Increase';
        final statusColor = r.hideTarget
            ? c.t4
            : absGap < 3
                ? c.up
                : gap > 0
                    ? c.dn
                    : c.blue;
        final isEditing = _editingKey != null && _editingKey == r.targetKey;

        return Container(
          padding: EdgeInsets.symmetric(
              horizontal: r.isSub ? 22 : 14, vertical: r.isSub ? 5 : 8),
          decoration: BoxDecoration(
            color: r.isSub ? c.rowAlt : Colors.transparent,
            border:
                Border(bottom: BorderSide(color: c.bd.withValues(alpha: 0.6))),
          ),
          child: Row(children: [
            // Icon + name
            if (!r.isSub && r.icon != null) ...[
              Container(
                width: 4,
                height: 22,
                decoration: BoxDecoration(
                    color: r.color, borderRadius: BorderRadius.circular(2)),
              ),
              const SizedBox(width: 8),
              Icon(r.icon, size: 13, color: r.color),
              const SizedBox(width: 6),
            ],
            Expanded(
                flex: 3,
                child: Text(
                  r.label,
                  style: r.isSub
                      ? AppTextStyles.captionXs(c.t3).copyWith(fontSize: 11)
                      : AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12),
                )),
            SizedBox(
                width: 65,
                child: denseNum(context, '${r.currentPct.toStringAsFixed(1)}%',
                    r.isSub ? c.t3 : c.t2)),
            // Editable target cell
            SizedBox(
              width: 75,
              child: r.hideTarget
                  ? denseNum(context, '—', c.t4)
                  : isEditing
                      ? SizedBox(
                          height: 22,
                          child: Row(
                              mainAxisAlignment: MainAxisAlignment.end,
                              children: [
                                SizedBox(
                                  width: 40,
                                  child: TextField(
                                    controller: _editController,
                                    autofocus: true,
                                    textAlign: TextAlign.center,
                                    keyboardType: TextInputType.number,
                                    style: AppTextStyles.mono(c.blue)
                                        .copyWith(fontSize: 11),
                                    decoration: InputDecoration(
                                      isDense: true,
                                      contentPadding:
                                          const EdgeInsets.symmetric(
                                              horizontal: 4, vertical: 3),
                                      border: OutlineInputBorder(
                                          borderRadius:
                                              BorderRadius.circular(4),
                                          borderSide:
                                              BorderSide(color: c.blue)),
                                      enabledBorder: OutlineInputBorder(
                                          borderRadius:
                                              BorderRadius.circular(4),
                                          borderSide: BorderSide(
                                              color: c.blue
                                                  .withValues(alpha: 0.4))),
                                      focusedBorder: OutlineInputBorder(
                                          borderRadius:
                                              BorderRadius.circular(4),
                                          borderSide:
                                              BorderSide(color: c.blue)),
                                    ),
                                    onSubmitted: (_) => _commitEdit(),
                                  ),
                                ),
                                const SizedBox(width: 2),
                                Text('%',
                                    style: AppTextStyles.mono(c.t3)
                                        .copyWith(fontSize: 10)),
                                InkWell(
                                    onTap: _commitEdit,
                                    child: Padding(
                                      padding: const EdgeInsets.only(left: 2),
                                      child: Icon(LucideIcons.check,
                                          size: 10, color: c.up),
                                    )),
                                InkWell(
                                    onTap: _cancelEdit,
                                    child: Padding(
                                      padding: const EdgeInsets.only(left: 2),
                                      child: Icon(LucideIcons.x,
                                          size: 10, color: c.t4),
                                    )),
                              ]),
                        )
                      : InkWell(
                          onTap: r.targetKey != null
                              ? () => _startEdit(r.targetKey!, r.targetPct)
                              : null,
                          child: Row(
                              mainAxisAlignment: MainAxisAlignment.end,
                              children: [
                                Text('${r.targetPct.toStringAsFixed(1)}%',
                                    style: AppTextStyles.mono(
                                            r.isSub ? c.t4 : c.t1)
                                        .copyWith(fontSize: 12)),
                                if (r.targetKey != null)
                                  Padding(
                                    padding: const EdgeInsets.only(left: 3),
                                    child: Icon(LucideIcons.edit3,
                                        size: 8,
                                        color: c.t4.withValues(alpha: 0.5)),
                                  ),
                              ]),
                        ),
            ),
            SizedBox(
                width: 65,
                child: r.hideTarget
                    ? const SizedBox()
                    : denseNum(context,
                        '${gap >= 0 ? '+' : ''}${gap.toStringAsFixed(1)}%',
                        statusColor,
                        bold: true)),
            SizedBox(
                width: 86,
                child: status.isEmpty
                    ? const SizedBox.shrink()
                    : _miniBadge(context, status, statusColor)),
          ]),
        );
      }),
    ]);
  }
}

class _AssetRow {
  final String label;
  final double currentPct;
  final double targetPct;
  final Color color;
  final IconData? icon;
  final bool isSub;
  final bool hideTarget;
  final String? targetKey; // key for editing in provider

  const _AssetRow(this.label, this.currentPct, this.targetPct, this.color,
      this.icon,
      {this.isSub = false, this.hideTarget = false, this.targetKey});
}


// ══════════════════════════════════════════════════════════════
//  DEEP REBALANCING ENGINE
// ══════════════════════════════════════════════════════════════

class _DeepRebalancingEngine extends StatefulWidget {
  final AllocationData alloc;
  final ExposureAnalysis exposure;
  final RiskProfile riskProfile;
  final Map<String, double> targets;
  final WidgetRef ref;

  const _DeepRebalancingEngine({
    required this.alloc,
    required this.exposure,
    required this.riskProfile,
    required this.targets,
    required this.ref,
  });

  @override
  State<_DeepRebalancingEngine> createState() => _DeepRebalancingEngineState();
}

class _DeepRebalancingEngineState extends State<_DeepRebalancingEngine> {
  int _selectedTab = 0;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final alloc = widget.alloc;
    final targets = widget.targets;

    // Compute asset-class level current allocation
    final currentAlloc = <String, double>{};
    final total = alloc.totalPortfolioValue;
    if (total > 0) {
      if (alloc.equityValue > 0) {
        currentAlloc['Equities'] = alloc.equityValue / total * 100;
      }
      if (alloc.mfValue > 0) {
        currentAlloc['Mutual Funds'] = alloc.mfValue / total * 100;
      }
      if (alloc.goldValue > 0) {
        currentAlloc['Gold'] = alloc.goldValue / total * 100;
      }
      if (alloc.debtValue > 0) {
        currentAlloc['Debt'] = alloc.debtValue / total * 100;
      }
      if (alloc.internationalValue > 0) {
        currentAlloc['International'] = alloc.internationalValue / total * 100;
      }
      if (alloc.cashValue > 0) {
        currentAlloc['Cash'] = alloc.cashValue / total * 100;
      }
      if (alloc.reitsValue > 0) {
        currentAlloc['REITs'] = alloc.reitsValue / total * 100;
      }
    }

    // Derive asset-class level targets from mcap targets
    final assetTargets = <String, double>{
      'Equities': (targets['Large Cap'] ?? 0) +
          (targets['Mid Cap'] ?? 0) +
          (targets['Small Cap'] ?? 0),
      'Mutual Funds': targets['Flexi Cap'] ?? 10,
      'International': targets['International'] ?? 5,
      'Debt': targets['Debt'] ?? 5,
      'Gold': targets['Gold'] ?? 5,
    };

    // Generate rebalancing items at asset-class level
    final rebalanceItems = <RebalanceItem>[];
    final allCategories = {...currentAlloc.keys, ...assetTargets.keys};
    for (final cat in allCategories) {
      final current = currentAlloc[cat] ?? 0;
      final target = assetTargets[cat] ?? 0;
      final gap = current - target;
      if (gap.abs() > 2) {
        final amount = (gap.abs() / 100 * total);
        rebalanceItems.add(RebalanceItem(
          category: cat,
          currentPct: current,
          targetPct: target,
          deltaPct: gap,
          action: gap > 0 ? 'Sell/Reduce' : 'Buy/Increase',
          amount: amount,
        ));
      }
    }
    rebalanceItems.sort((a, b) => b.deltaPct.abs().compareTo(a.deltaPct.abs()));

    final tabs = ['Overview', 'Action Plan', 'Heatmap'];

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(context,
            icon: LucideIcons.refreshCcw,
            accent: c.cyan,
            title: 'Deep Rebalancing Engine',
            subtitle: 'Portfolio optimization vs risk-profile targets',
            trailing: Row(mainAxisSize: MainAxisSize.min, children: [
              // Risk profile selector
              ...RiskProfile.values.map((rp) {
                final isSelected = widget.riskProfile == rp;
                return Padding(
                  padding: const EdgeInsets.only(left: 4),
                  child: InkWell(
                    onTap: () =>
                        widget.ref.read(riskProfileProvider.notifier).set(rp),
                    borderRadius: BorderRadius.circular(6),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 9, vertical: 4),
                      decoration: BoxDecoration(
                        color: isSelected
                            ? c.cyan.withValues(alpha: 0.10)
                            : Colors.transparent,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(
                            color: isSelected
                                ? c.cyan.withValues(alpha: 0.3)
                                : c.bd),
                      ),
                      child: Text(
                          rp.name[0].toUpperCase() + rp.name.substring(1),
                          style: AppTextStyles.labelXs(
                              isSelected ? c.cyan : c.t3)),
                    ),
                  ),
                );
              }),
            ])),
        SectionExplainer(
          accent: c.cyan,
          question: 'So what do I actually do?',
          reading: 'The other tabs describe the portfolio; this one gives '
              'instructions.',
          rules: const [
            'Pick a risk profile at the top right — it sets every target. '
                'Switching it previews a different plan before you commit to it.',
            'Overview: a health score, calculated as 100 minus twice your '
                'largest gap. Over 80 is green, 50–80 amber, under 50 red. It '
                'measures drift from your plan only — not volatility or quality.',
            'Action Plan: the shopping list. Only gaps wider than 2% appear, '
                'worst first, each with the exact rupee amount.',
            'Heatmap: the same thing as colour — red overweight, blue '
                'underweight, green already within 2%.',
          ],
          action: 'Work the Buy/Increase rows with new money and leave the '
              'Sell/Reduce rows alone unless the gap is extreme — selling '
              'triggers capital-gains tax, while adding does not.',
        ),

        // Tab bar
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 0),
          child: Row(
              children: tabs.asMap().entries.map((entry) {
            final isSelected = _selectedTab == entry.key;
            return Padding(
              padding: const EdgeInsets.only(right: 4),
              child: GestureDetector(
                onTap: () => setState(() => _selectedTab = entry.key),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: isSelected
                        ? c.blue.withValues(alpha: 0.08)
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(
                        color: isSelected
                            ? c.blue.withValues(alpha: 0.25)
                            : c.bd),
                  ),
                  child: Text(entry.value,
                      style: AppTextStyles.bodySmall(isSelected ? c.blue : c.t3)
                          .copyWith(
                        fontWeight:
                            isSelected ? FontWeight.w600 : FontWeight.normal,
                      )),
                ),
              ),
            );
          }).toList()),
        ),

        // Tab content
        Padding(
          padding: const EdgeInsets.all(14),
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 300),
            child: _selectedTab == 0
                ? _buildOverviewTab(
                    context, currentAlloc, assetTargets, rebalanceItems)
                : _selectedTab == 1
                    ? _buildActionPlanTab(context, rebalanceItems, total)
                    : _buildHeatmapTab(context, currentAlloc, assetTargets),
          ),
        ),
      ]),
    );
  }

  Widget _buildOverviewTab(BuildContext context, Map<String, double> current,
      Map<String, double> targets, List<RebalanceItem> items) {
    final c = context.colors;
    final maxDeviation = items.isEmpty
        ? 0.0
        : items.map((e) => e.deltaPct.abs()).reduce((a, b) => a > b ? a : b);
    final healthScore = (100 - maxDeviation * 2).clamp(0, 100);
    final healthColor =
        healthScore > 80 ? c.up : healthScore > 50 ? c.gold : c.dn;

    return Column(
        key: const ValueKey('overview'),
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Health score
          Row(children: [
            Container(
              width: 76,
              height: 76,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border:
                    Border.all(color: healthColor.withValues(alpha: 0.3)),
                color: healthColor.withValues(alpha: 0.06),
              ),
              child: Center(
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                Text(healthScore.toStringAsFixed(0),
                    style: AppTextStyles.monoBold(healthColor)
                        .copyWith(fontSize: 18)),
                Text('SCORE', style: AppTextStyles.labelXs(healthColor)),
              ])),
            ),
            const SizedBox(width: 16),
            Expanded(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  Text('Portfolio Health', style: AppTextStyles.heading3(c.t1)),
                  const SizedBox(height: 4),
                  Text(
                      healthScore > 80
                          ? 'Your portfolio is well-balanced. Minor adjustments recommended.'
                          : healthScore > 50
                              ? 'Some categories need rebalancing. ${items.length} adjustments suggested.'
                              : 'Significant rebalancing needed. ${items.length} categories off-target.',
                      style: AppTextStyles.bodySmall(c.t2)),
                  const SizedBox(height: 8),
                  Wrap(spacing: 14, runSpacing: 6, children: [
                    _hdrStat(context, 'ACTIONS', '${items.length}', c.blue),
                    _hdrStat(context, 'MAX GAP',
                        '${maxDeviation.toStringAsFixed(1)}%',
                        maxDeviation > 10 ? c.dn : c.gold),
                    _hdrStat(context, 'PROFILE',
                        widget.riskProfile.name.toUpperCase(), c.cyan),
                  ]),
                ])),
          ]),
          const SizedBox(height: 10),
          Row(children: [
            Icon(LucideIcons.info, size: 11, color: c.t3),
            const SizedBox(width: 7),
            Expanded(
              child: Text(
                'Score = 100 − (2 × your largest gap of '
                '${maxDeviation.toStringAsFixed(1)}%). It measures drift from '
                'your targets only — a 100 here means "on plan", not "low risk".',
                style: AppTextStyles.captionXs(c.t3),
              ),
            ),
          ]),
          const SizedBox(height: 14),

          // Quick summary bars
          ...items.take(6).map((item) {
            final isOver = item.deltaPct > 0;
            final color = isOver ? c.dn : c.blue;
            return Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(children: [
                SizedBox(
                    width: 100,
                    child: Text(item.category,
                        style: AppTextStyles.bodySmall(c.t1)
                            .copyWith(fontSize: 11))),
                Expanded(
                    child: ClipRRect(
                  borderRadius: BorderRadius.circular(3),
                  child: Stack(children: [
                    Container(height: 6, color: c.bd),
                    FractionallySizedBox(
                      widthFactor: (item.deltaPct.abs() / 30).clamp(0, 1),
                      child: Container(height: 6, color: color),
                    ),
                  ]),
                )),
                const SizedBox(width: 8),
                SizedBox(
                    width: 55,
                    child: denseNum(
                        context,
                        '${isOver ? '+' : ''}${item.deltaPct.toStringAsFixed(1)}%',
                        color,
                        bold: true)),
                SizedBox(
                    width: 66,
                    child: Text(
                      isOver ? 'Reduce' : 'Increase',
                      style: AppTextStyles.captionXs(color),
                      textAlign: TextAlign.right,
                    )),
              ]),
            );
          }),
        ]);
  }

  Widget _buildActionPlanTab(
      BuildContext context, List<RebalanceItem> items, double totalValue) {
    final c = context.colors;
    if (items.isEmpty) {
      return SizedBox(
        key: const ValueKey('action'),
        height: 120,
        child: Center(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(LucideIcons.checkCircle2, color: c.up, size: 26),
          const SizedBox(height: 8),
          Text('Portfolio is balanced!', style: AppTextStyles.heading3(c.up)),
          Text('All categories within ±2% of target',
              style: AppTextStyles.bodySmall(c.t3)),
        ])),
      );
    }

    return Column(key: const ValueKey('action'), children: [
      Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Row(children: [
          Icon(LucideIcons.info, size: 11, color: c.t3),
          const SizedBox(width: 7),
          Expanded(
            child: Text(
              'Read it as one instruction per row: move CURRENT to TARGET by '
              'the AMOUNT shown. Gaps under 2% are left out on purpose — they '
              'are not worth a transaction.',
              style: AppTextStyles.captionXs(c.t3),
            ),
          ),
        ]),
      ),
      // Header
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
        decoration: BoxDecoration(
          color: c.bg3,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: c.bd),
        ),
        child: Row(children: [
          Expanded(
              flex: 3,
              child: Text('CATEGORY',
                  style:
                      AppTextStyles.tableHeader(c.t3).copyWith(fontSize: 10))),
          SizedBox(
              width: 60,
              child: Text('CURRENT',
                  style: AppTextStyles.tableHeader(c.t3).copyWith(fontSize: 10),
                  textAlign: TextAlign.right)),
          const SizedBox(width: 10),
          SizedBox(
              width: 60,
              child: Text('TARGET',
                  style: AppTextStyles.tableHeader(c.t3).copyWith(fontSize: 10),
                  textAlign: TextAlign.right)),
          SizedBox(
              width: 60,
              child: Text('GAP',
                  style: AppTextStyles.tableHeader(c.t3).copyWith(fontSize: 10),
                  textAlign: TextAlign.right)),
          SizedBox(
              width: 90,
              child: Text('ACTION',
                  style: AppTextStyles.tableHeader(c.t3).copyWith(fontSize: 10),
                  textAlign: TextAlign.center)),
          SizedBox(
              width: 80,
              child: Text('AMOUNT',
                  style: AppTextStyles.tableHeader(c.t3).copyWith(fontSize: 10),
                  textAlign: TextAlign.right)),
        ]),
      ),
      const SizedBox(height: 4),
      ...items.map((item) {
        final isOver = item.deltaPct > 0;
        final actionColor = isOver ? c.dn : c.blue;

        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            border: Border(
                bottom: BorderSide(color: c.bd.withValues(alpha: 0.6))),
          ),
          child: Row(children: [
            Expanded(
                flex: 3,
                child: Row(children: [
                  Container(
                      width: 4,
                      height: 22,
                      decoration: BoxDecoration(
                          color: actionColor,
                          borderRadius: BorderRadius.circular(2))),
                  const SizedBox(width: 8),
                  Expanded(
                      child: Text(item.category,
                          style: AppTextStyles.bodyBold(c.t1)
                              .copyWith(fontSize: 12))),
                ])),
            SizedBox(
                width: 60,
                child: denseNum(context,
                    '${item.currentPct.toStringAsFixed(1)}%', c.t2)),
            SizedBox(
                width: 10,
                child: Text('→',
                    style: AppTextStyles.body(c.t3).copyWith(fontSize: 10),
                    textAlign: TextAlign.center)),
            SizedBox(
                width: 60,
                child: denseNum(context,
                    '${item.targetPct.toStringAsFixed(1)}%', c.t1)),
            SizedBox(
                width: 60,
                child: denseNum(
                    context,
                    '${item.deltaPct >= 0 ? '+' : ''}${item.deltaPct.toStringAsFixed(1)}%',
                    actionColor,
                    bold: true)),
            SizedBox(
                width: 90,
                child: _miniBadge(context, item.action, actionColor,
                    align: Alignment.center)),
            SizedBox(
                width: 80,
                child: denseNum(
                    context, '₹${formatCompact(item.amount)}', actionColor,
                    bold: true)),
          ]),
        );
      }),
      const SizedBox(height: 10),

      // Summary
      Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: c.cyan.withValues(alpha: 0.05),
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: c.cyan.withValues(alpha: 0.15)),
        ),
        child: Row(children: [
          Icon(LucideIcons.lightbulb, size: 14, color: c.cyan),
          const SizedBox(width: 8),
          Expanded(
              child: Text(
            'Total rebalancing: ${items.where((i) => i.deltaPct > 0).length} sell actions + ${items.where((i) => i.deltaPct < 0).length} buy actions. '
            'Estimated movement: ₹${formatCompact(items.fold<double>(0, (a, b) => a + b.amount))}',
            style: AppTextStyles.bodySmall(c.t2).copyWith(fontSize: 11),
          )),
        ]),
      ),
    ]);
  }

  Widget _buildHeatmapTab(BuildContext context, Map<String, double> current,
      Map<String, double> targets) {
    final c = context.colors;
    return Column(key: const ValueKey('heatmap'), children: [
      Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Row(children: [
          Icon(LucideIcons.info, size: 11, color: c.t3),
          const SizedBox(width: 7),
          Expanded(
            child: Text(
              'Each row reads current → target → difference. Red means you hold '
              'too much of it, blue too little, green is within 2% and needs '
              'nothing. Stronger colour means a wider gap.',
              style: AppTextStyles.captionXs(c.t3),
            ),
          ),
        ]),
      ),
      RebalancingHeatmap(currentAlloc: current, targetAlloc: targets),
    ]);
  }
}

// The portfolio donut and its hierarchical breakdown lived here, with the
// _CategoryNode and _SubItem types they alone used. All of it went with the
// Portfolio Composition card: the chart encoded two numbers and the
// breakdown was a strict subset of the Current vs Target table below it.

/// Proportional allocation bar (hairline track, 4px).
class _AllocationBar extends StatelessWidget {
  final double pct;
  final Color color;
  final double maxPct;

  const _AllocationBar({required this.pct, required this.color, this.maxPct = 100});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final fillRatio = maxPct > 0 ? (pct / maxPct).clamp(0.0, 1.0) : 0.0;
    return Container(
      height: 4,
      decoration: BoxDecoration(
        color: c.bd,
        borderRadius: BorderRadius.circular(2),
      ),
      child: FractionallySizedBox(
        alignment: Alignment.centerLeft,
        widthFactor: fillRatio,
        child: Container(
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
      ),
    );
  }
}
