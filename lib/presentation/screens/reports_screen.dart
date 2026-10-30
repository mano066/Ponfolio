import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_colors.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/presentation/widgets/animated_page_wrapper.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/providers/providers.dart';
import 'package:aiei_wealth/services/export_service.dart';

/// Wealth Report — built from the same live providers as the Dashboard.
/// Shows: summary stats, AI intelligence, risk assessment, advisor recs,
/// asset allocation, sector/category breakdown, full holdings tables, and totals.
/// Styled with the shared Data-Dense kit (dense_ui).
class ReportsScreen extends ConsumerWidget {
  const ReportsScreen({super.key});

  static const _eqCols = [
    DenseCol('INSTRUMENT', 3, numeric: false),
    DenseCol('QTY', 1),
    DenseCol('AVG', 2),
    DenseCol('LTP', 2),
    DenseCol('INVESTED', 2),
    DenseCol('VALUE', 2),
    DenseCol('P&L', 2),
    DenseCol('NET%', 2),
    DenseCol('WT%', 2),
    DenseCol('DAY%', 2),
  ];

  static const _mfCols = [
    DenseCol('SCHEME', 4, numeric: false),
    DenseCol('UNITS', 2),
    DenseCol('AVG NAV', 2),
    DenseCol('NAV', 2),
    DenseCol('INVESTED', 2),
    DenseCol('VALUE', 2),
    DenseCol('P&L', 2),
    DenseCol('RET%', 2),
    DenseCol('WT%', 2),
    DenseCol('XIRR', 2),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final portfolioAsync = ref.watch(portfolioProvider);
    final mfAsync = ref.watch(mfPortfolioProvider);
    final signalsAsync = ref.watch(aiSignalsProvider);
    final advisor = ref.watch(advisorProvider);
    final niftyAsync = ref.watch(niftyProvider);

    return portfolioAsync.when(
      loading: () => const DensePulseLoader(label: 'Building wealth report…'),
      error: (e, _) => ErrorRetry(
        title: 'Error loading portfolio',
        detail: '$e',
        onRetry: () {
          ref.invalidate(portfolioProvider);
          ref.invalidate(mfPortfolioProvider);
        },
      ),
      data: (pData) {
        // ───── Stock data (live) ─────
        final holdings = List<Map<String, dynamic>>.from(pData['holdings'] ?? []);
        final totalInvested = (pData['total_invested'] ?? 0).toDouble();
        final totalValue = (pData['total_portfolio_value'] ?? 0).toDouble();
        final totalPnl = (pData['total_pnl'] ?? 0).toDouble();
        final totalPnlPct = (pData['total_pnl_pct'] ?? 0).toDouble();
        final kiteConnected = pData['kite_connected'] == true;
        final dataSource = (pData['data_source'] ?? 'Manual').toString();

        // ───── MF data (live) ─────
        double mfInvested = 0, mfCurrent = 0, mfPnl = 0, mfPnlPct = 0;
        double? mfTotalXirr;
        var funds = <Map<String, dynamic>>[];
        mfAsync.whenData((mfData) {
          mfInvested = (mfData['total_invested'] ?? 0).toDouble();
          mfCurrent = (mfData['total_current'] ?? 0).toDouble();
          mfPnl = (mfData['total_pnl'] ?? 0).toDouble();
          mfPnlPct = (mfData['total_pnl_pct'] ?? 0).toDouble();
          final xr = mfData['total_xirr'];
          mfTotalXirr = xr is num ? xr.toDouble() : null;
          funds = List<Map<String, dynamic>>.from(mfData['funds'] ?? []);
        });

        // ───── Combined ─────
        final combinedInvested = totalInvested + mfInvested;
        final combinedValue = totalValue + mfCurrent;
        final combinedPnl = totalPnl + mfPnl;
        final combinedPnlPct = combinedInvested > 0
            ? ((combinedValue - combinedInvested) / combinedInvested) * 100
            : 0.0;
        final eqWeightPct = combinedValue > 0 ? (totalValue / combinedValue) : 0.0;
        final mfWeightPct = combinedValue > 0 ? (mfCurrent / combinedValue) : 0.0;

        // ───── AI Signals aggregation ─────
        final signalMap = signalsAsync.when(
          data: (d) => Map<String, dynamic>.from(d['signals'] ?? {}),
          loading: () => <String, dynamic>{},
          error: (_, _) => <String, dynamic>{},
        );
        int buyCount = 0, sellCount = 0, holdCount = 0;
        for (final entry in signalMap.entries) {
          final sig = entry.value;
          if (sig is Map && sig['status'] == 'done') {
            final verdict = (sig['verdict_owned'] ?? '').toString().toUpperCase();
            if (verdict.contains('BUY')) buyCount++;
            else if (verdict.contains('SELL')) sellCount++;
            else holdCount++;
          }
        }
        final totalSignals = buyCount + sellCount + holdCount;

        // ───── Risk: concentration warnings ─────
        final concentrationWarnings = <Map<String, dynamic>>[];
        for (final h in holdings) {
          final hVal = (h['total_value'] ?? 0).toDouble();
          final weight = totalValue > 0 ? (hVal / totalValue * 100) : 0.0;
          if (weight > 25) {
            concentrationWarnings.add({
              'symbol': (h['symbol'] ?? '').toString().cleanSymbol,
              'weight': weight,
              'level': weight > 40 ? 'HIGH' : 'MODERATE',
            });
          }
        }

        // ───── Sector breakdown from holdings ─────
        final sectorMap = <String, _SectorBucket>{};
        for (final h in holdings) {
          final sector = (h['sector'] ?? 'Unknown').toString();
          final hVal = (h['total_value'] ?? 0).toDouble();
          final hPnl = (h['pnl'] ?? 0).toDouble();
          sectorMap.putIfAbsent(sector, () => _SectorBucket(sector, 0, 0));
          sectorMap[sector]!.value += hVal;
          sectorMap[sector]!.pnl += hPnl;
        }
        final sectors = sectorMap.values.toList()..sort((a, b) => b.value.compareTo(a.value));

        // ───── MF category breakdown ─────
        final catMap = <String, _SectorBucket>{};
        for (final f in funds) {
          final cat = (f['category'] ?? 'Unknown').toString();
          final fVal = (f['current_value'] ?? 0).toDouble();
          final fPnl = fVal - (f['invested'] ?? 0).toDouble();
          catMap.putIfAbsent(cat, () => _SectorBucket(cat, 0, 0));
          catMap[cat]!.value += fVal;
          catMap[cat]!.pnl += fPnl;
        }
        final categories = catMap.values.toList()..sort((a, b) => b.value.compareTo(a.value));

        // ───── Top gainer / loser from holdings ─────
        Map<String, dynamic>? topGainer, topLoser;
        if (holdings.isNotEmpty) {
          final sorted = List<Map<String, dynamic>>.from(holdings)
            ..sort((a, b) => ((b['day_chg'] ?? 0) as num).compareTo((a['day_chg'] ?? 0) as num));
          topGainer = sorted.first;
          topLoser = sorted.last;
        }

        // ───── Nifty50 context ─────
        final niftyData = niftyAsync.when(
          data: (d) => d, loading: () => <String, dynamic>{}, error: (_, _) => <String, dynamic>{});
        final niftyVal = (niftyData['last_price'] ?? niftyData['close'] ?? niftyData['value'] ?? 0).toDouble();
        final niftyChg = (niftyData['change_pct'] ?? niftyData['pct_change'] ?? 0).toDouble();

        // ───── Timestamp ─────
        final now = DateTime.now();
        final timeStr = '${now.day}/${now.month}/${now.year} ${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}';

        return ListView(padding: const EdgeInsets.all(0), children: [
          // ── HEADER ──
          AnimatedListItem(
            index: 0,
            child: DenseCard(
              child: denseTableHeader(
                context,
                icon: LucideIcons.fileText,
                accent: c.blue,
                title: 'Live Wealth Report',
                subtitle:
                    'Generated $timeStr · Source: $dataSource${kiteConnected ? ' (Kite Connected)' : ''}',
                trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                  if (niftyVal > 0) ...[
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                          color: c.bg3,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: c.bd)),
                      child: Row(children: [
                        Text('NIFTY 50  ', style: AppTextStyles.labelXs(c.t3)),
                        Text(niftyVal.toStringAsFixed(2),
                            style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 12)),
                        const SizedBox(width: 4),
                        Icon(
                            niftyChg >= 0
                                ? LucideIcons.arrowUpRight
                                : LucideIcons.arrowDownRight,
                            size: 12,
                            color: context.pnlColor(niftyChg)),
                        Text('${niftyChg >= 0 ? "+" : ""}${niftyChg.toStringAsFixed(2)}%',
                            style: AppTextStyles.monoBold(context.pnlColor(niftyChg))
                                .copyWith(fontSize: 11)),
                      ]),
                    ),
                    const SizedBox(width: 8),
                  ],
                  HeaderButton(
                    icon: const Icon(LucideIcons.refreshCw, size: 14, color: Colors.white),
                    text: 'Refresh',
                    solidColor: c.accent,
                    onTap: () {
                      ref.invalidate(portfolioProvider);
                      ref.invalidate(mfPortfolioProvider);
                    },
                  ),
                  const SizedBox(width: 8),
                  HeaderButton(
                    icon: const Icon(LucideIcons.download, size: 14, color: Colors.white),
                    text: 'Export PDF',
                    solidColor: c.blue,
                    onTap: () => exportService.exportWealthReportPdf(pData),
                  ),
                ]),
              ),
            ),
          ),
          const SizedBox(height: 12),

          // ── SUMMARY KPI GRID ──
          AnimatedListItem(
            index: 1,
            child: KpiGrid(perRow: 5, cells: [
              Kpi('TOTAL WEALTH', formatINR(combinedValue),
                  'EQ ${formatINR(totalValue)} · MF ${formatINR(mfCurrent)}', c.t1),
              Kpi('TOTAL INVESTED', formatINR(combinedInvested),
                  'EQ ${formatINR(totalInvested)} · MF ${formatINR(mfInvested)}', c.t1),
              Kpi('TOTAL P&L', formatSignedINR(combinedPnl),
                  'EQ ${formatSignedINR(totalPnl)} · MF ${formatSignedINR(mfPnl)}',
                  context.pnlColor(combinedPnl)),
              Kpi('RETURN', formatPct(combinedPnlPct),
                  'EQ ${formatPct(totalPnlPct)} · MF ${formatPct(mfPnlPct)}',
                  context.pnlColor(combinedPnlPct)),
              Kpi('PORTFOLIO MIX', '${holdings.length + funds.length} assets',
                  '${holdings.length} equities · ${funds.length} mutual funds', c.t1),
            ]),
          ),
          const SizedBox(height: 12),

          // ── AI INTELLIGENCE + RISK ASSESSMENT ──
          AnimatedListItem(
            index: 2,
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              // AI Intelligence Summary
              Expanded(
                flex: 3,
                child: DenseCard(
                  clip: true,
                  child: Column(children: [
                    denseTableHeader(
                      context,
                      icon: LucideIcons.brain,
                      accent: c.accent,
                      title: 'AI Intelligence Summary',
                      subtitle: totalSignals > 0 ? '$totalSignals stocks analyzed' : null,
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
                      child: totalSignals == 0
                          ? Padding(
                              padding: const EdgeInsets.symmetric(vertical: 18),
                              child: Column(children: [
                                Icon(LucideIcons.brain, size: 22, color: c.t4.withValues(alpha: 0.4)),
                                const SizedBox(height: 8),
                                Text('Run AI Analysis to see intelligence summary',
                                    style: AppTextStyles.bodySmall(c.t4)),
                              ]),
                            )
                          : Column(children: [
                              // Signal distribution bar
                              Container(
                                height: 20,
                                clipBehavior: Clip.antiAlias,
                                decoration: BoxDecoration(
                                    borderRadius: BorderRadius.circular(4), color: c.bg3),
                                child: Row(children: [
                                  if (buyCount > 0)
                                    Expanded(
                                        flex: buyCount,
                                        child: Container(
                                          color: c.up,
                                          child: Center(
                                              child: Text('$buyCount BUY',
                                                  style: AppTextStyles.labelXs(Colors.white)
                                                      .copyWith(fontSize: 9))),
                                        )),
                                  if (holdCount > 0)
                                    Expanded(
                                        flex: holdCount,
                                        child: Container(
                                          color: c.t4,
                                          child: Center(
                                              child: Text('$holdCount HOLD',
                                                  style: AppTextStyles.labelXs(Colors.white)
                                                      .copyWith(fontSize: 9))),
                                        )),
                                  if (sellCount > 0)
                                    Expanded(
                                        flex: sellCount,
                                        child: Container(
                                          color: c.dn,
                                          child: Center(
                                              child: Text('$sellCount SELL',
                                                  style: AppTextStyles.labelXs(Colors.white)
                                                      .copyWith(fontSize: 9))),
                                        )),
                                ]),
                              ),
                              const SizedBox(height: 14),
                              Row(mainAxisAlignment: MainAxisAlignment.spaceAround, children: [
                                _signalStat(c, 'BUY SIGNALS', buyCount, c.up, LucideIcons.arrowUpRight),
                                _signalStat(c, 'HOLD SIGNALS', holdCount, c.t3, LucideIcons.minus),
                                _signalStat(c, 'SELL SIGNALS', sellCount, c.dn, LucideIcons.arrowDownRight),
                              ]),
                            ]),
                    ),
                  ]),
                ),
              ),
              const SizedBox(width: 12),
              // Risk Assessment
              Expanded(
                flex: 2,
                child: DenseCard(
                  child: Column(children: [
                    denseTableHeader(
                      context,
                      icon: LucideIcons.alertTriangle,
                      accent: c.gold,
                      title: 'Risk Assessment',
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
                      child: Column(children: [
                        if (concentrationWarnings.isEmpty)
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: c.up.withValues(alpha: 0.08),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: c.up.withValues(alpha: 0.22)),
                            ),
                            child: Row(children: [
                              Icon(LucideIcons.checkCircle2, size: 15, color: c.up),
                              const SizedBox(width: 10),
                              Expanded(
                                  child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                    Text('Portfolio Diversified',
                                        style: AppTextStyles.bodyBold(c.up).copyWith(fontSize: 12)),
                                    Text('No single stock exceeds 25% of equity',
                                        style: AppTextStyles.captionXs(c.t3)),
                                  ])),
                            ]),
                          )
                        else
                          ...concentrationWarnings.map((w) {
                            final isHigh = w['level'] == 'HIGH';
                            final warnColor = isHigh ? c.dn : c.gold;
                            return Padding(
                              padding: const EdgeInsets.only(bottom: 8),
                              child: Container(
                                padding: const EdgeInsets.all(10),
                                decoration: BoxDecoration(
                                  color: warnColor.withValues(alpha: 0.08),
                                  borderRadius: BorderRadius.circular(8),
                                  border: Border.all(color: warnColor.withValues(alpha: 0.22)),
                                ),
                                child: Row(children: [
                                  Icon(LucideIcons.alertTriangle, size: 14, color: warnColor),
                                  const SizedBox(width: 8),
                                  Expanded(
                                      child: Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                        Text('${w['symbol']} — ${w['level']} concentration',
                                            style: AppTextStyles.bodyBold(warnColor)
                                                .copyWith(fontSize: 12)),
                                        Text(
                                            '${(w['weight'] as double).toStringAsFixed(1)}% of equity',
                                            style: AppTextStyles.captionXs(c.t3)),
                                      ])),
                                ]),
                              ),
                            );
                          }),
                        const SizedBox(height: 10),
                        // Asset mix
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                              color: c.bg3,
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: c.bd)),
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text('ASSET MIX', style: AppTextStyles.labelXs(c.t3)),
                            const SizedBox(height: 8),
                            Row(children: [
                              Container(
                                  width: 8,
                                  height: 8,
                                  decoration: BoxDecoration(
                                      color: c.blue, borderRadius: BorderRadius.circular(2))),
                              const SizedBox(width: 5),
                              Text('EQ ${(eqWeightPct * 100).toStringAsFixed(1)}%',
                                  style: AppTextStyles.monoXs(c.t2)),
                              const SizedBox(width: 14),
                              Container(
                                  width: 8,
                                  height: 8,
                                  decoration: BoxDecoration(
                                      color: c.accent, borderRadius: BorderRadius.circular(2))),
                              const SizedBox(width: 5),
                              Text('MF ${(mfWeightPct * 100).toStringAsFixed(1)}%',
                                  style: AppTextStyles.monoXs(c.t2)),
                            ]),
                            const SizedBox(height: 6),
                            ClipRRect(
                              borderRadius: BorderRadius.circular(2),
                              child: SizedBox(
                                height: 4,
                                child: Row(children: [
                                  if (eqWeightPct > 0)
                                    Expanded(
                                        flex: (eqWeightPct * 100).round(),
                                        child: Container(color: c.blue)),
                                  if (mfWeightPct > 0)
                                    Expanded(
                                        flex: (mfWeightPct * 100).round(),
                                        child: Container(color: c.accent)),
                                ]),
                              ),
                            ),
                          ]),
                        ),
                      ]),
                    ),
                  ]),
                ),
              ),
            ]),
          ),
          const SizedBox(height: 12),

          // ── ADVISOR RECOMMENDATIONS ──
          if (advisor.results.isNotEmpty) ...[
            AnimatedListItem(
              index: 3,
              child: DenseCard(
                clip: true,
                child: Column(children: [
                  denseTableHeader(
                    context,
                    icon: LucideIcons.messageSquare,
                    accent: c.blue,
                    title: 'AI Advisor Recommendations',
                    subtitle: '${advisor.results.length} stocks',
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
                    child: Wrap(spacing: 10, runSpacing: 10, children: advisor.results.entries.map((entry) {
                      final sym = entry.key.replaceAll(RegExp(r'\.(NS|BO)$', caseSensitive: false), '');
                      final av = entry.value;
                      if (av is! Map<String, dynamic>) return const SizedBox.shrink();
                      final verdict = (av['verdict'] ?? '—').toString();
                      final actionSummary = av['action_summary']?.toString();
                      final target = av['target_price']?.toString();
                      final stopLoss = av['stop_loss']?.toString();

                      return Container(
                        width: (MediaQuery.sizeOf(context).width - 220 - 80) / 4 - 12,
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: c.bg1,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: c.bd),
                        ),
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Row(children: [
                            Expanded(
                                child: Text(sym,
                                    style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis)),
                            DSignalBadge(signal: verdict),
                          ]),
                          if (actionSummary != null) ...[
                            const SizedBox(height: 6),
                            Text(actionSummary,
                                style: AppTextStyles.captionXs(c.t3),
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis),
                          ],
                          if (target != null || stopLoss != null) ...[
                            const SizedBox(height: 6),
                            Row(children: [
                              if (target != null)
                                Text('T ₹$target', style: AppTextStyles.monoXs(c.up).copyWith(fontSize: 10)),
                              if (target != null && stopLoss != null)
                                Text('  ·  ', style: AppTextStyles.monoXs(c.t4).copyWith(fontSize: 10)),
                              if (stopLoss != null)
                                Text('SL ₹$stopLoss', style: AppTextStyles.monoXs(c.dn).copyWith(fontSize: 10)),
                            ]),
                          ],
                        ]),
                      );
                    }).toList()),
                  ),
                ]),
              ),
            ),
            const SizedBox(height: 12),
          ],

          // ── ASSET ALLOCATION + PORTFOLIO HIGHLIGHTS ──
          AnimatedListItem(
            index: 4,
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(
                flex: 3,
                child: DenseCard(
                  child: Column(children: [
                    denseTableHeader(context,
                        icon: LucideIcons.pieChart, accent: c.blue, title: 'Asset Allocation'),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
                      child: Column(children: [
                        ClipRRect(
                          borderRadius: BorderRadius.circular(4),
                          child: SizedBox(
                            height: 14,
                            child: Row(children: [
                              if (eqWeightPct > 0)
                                Expanded(
                                    flex: (eqWeightPct * 100).round().clamp(1, 99),
                                    child: Container(color: c.blue)),
                              if (mfWeightPct > 0)
                                Expanded(
                                    flex: (mfWeightPct * 100).round().clamp(1, 99),
                                    child: Container(color: c.accent)),
                            ]),
                          ),
                        ),
                        const SizedBox(height: 14),
                        Row(mainAxisAlignment: MainAxisAlignment.spaceAround, children: [
                          _allocItem(context, 'Direct Equity', c.blue, eqWeightPct, totalValue, holdings.length),
                          _allocItem(context, 'Mutual Funds', c.accent, mfWeightPct, mfCurrent, funds.length),
                        ]),
                      ]),
                    ),
                  ]),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                flex: 2,
                child: DenseCard(
                  child: Column(children: [
                    denseTableHeader(context,
                        icon: LucideIcons.star, accent: c.gold, title: 'Portfolio Highlights'),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
                      child: Column(children: [
                        _highlightCard(context, 'TOP GAINER (TODAY)', topGainer),
                        const SizedBox(height: 8),
                        _highlightCard(context, 'TOP LOSER (TODAY)', topLoser),
                      ]),
                    ),
                  ]),
                ),
              ),
            ]),
          ),
          const SizedBox(height: 12),

          // ── SECTOR & CATEGORY BREAKDOWN ──
          AnimatedListItem(
            index: 5,
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(
                child: DenseCard(
                  child: Column(children: [
                    denseTableHeader(context,
                        icon: LucideIcons.barChart2,
                        accent: c.blue,
                        title: 'Sector Exposure',
                        subtitle: 'equity'),
                    _breakdownList(context, sectors, totalValue, c.blue),
                  ]),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: DenseCard(
                  child: Column(children: [
                    denseTableHeader(context,
                        icon: LucideIcons.layers,
                        accent: c.accent,
                        title: 'Category Exposure',
                        subtitle: 'mutual funds'),
                    funds.isEmpty
                        ? Padding(
                            padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
                            child: Text('No mutual fund data', style: AppTextStyles.bodySmall(c.t4)))
                        : _breakdownList(context, categories, mfCurrent, c.accent),
                  ]),
                ),
              ),
            ]),
          ),
          const SizedBox(height: 12),

          // ── EQUITY HOLDINGS TABLE (full) ──
          AnimatedListItem(
            index: 6,
            child: DenseTable(
              icon: LucideIcons.trendingUp,
              accent: c.up,
              title: 'Direct Equity Holdings',
              subtitle: '${holdings.length} holdings',
              trailing: densePnlTrailing(context, totalPnl, totalPnlPct),
              cols: _eqCols,
              rows: holdings.map((h) {
                final sym = (h['symbol'] ?? '').toString().cleanSymbol;
                final sector = (h['sector'] ?? '').toString();
                final ltp = (h['current_price'] ?? 0).toDouble();
                final avgCost = (h['avg_cost'] ?? 0).toDouble();
                final qty = (h['shares'] ?? 0);
                final invested = avgCost * (qty as num).toDouble();
                final curVal = (h['total_value'] ?? 0).toDouble();
                final pnl = (h['pnl'] ?? (curVal - invested)).toDouble();
                final netChg = (h['net_chg'] ?? 0).toDouble();
                final dayChg = (h['day_chg'] ?? 0).toDouble();
                final weight = totalValue > 0 ? (curVal / totalValue * 100) : 0.0;
                return [
                  DInstrument(symbol: sym, sub: sector, up: pnl >= 0),
                  denseNum(context, '$qty', c.t2),
                  denseNum(context, avgCost.toStringAsFixed(2), c.t3),
                  denseNum(context, ltp.toStringAsFixed(2), c.t1, bold: true),
                  denseNum(context, formatINR(invested), c.t3),
                  denseNum(context, formatINR(curVal), c.t2),
                  denseNum(context, formatSignedINR(pnl), context.pnlColor(pnl)),
                  denseDelta(context, netChg),
                  DWeightCell(pct: weight),
                  denseNum(context, formatPct(dayChg), context.pnlColor(dayChg)),
                ];
              }).toList(),
              footer: [
                denseFootLabel(context, 'TOTAL · ${holdings.length}'),
                const SizedBox.shrink(),
                const SizedBox.shrink(),
                const SizedBox.shrink(),
                denseNum(context, formatINR(totalInvested), c.t2, bold: true),
                denseNum(context, formatINR(totalValue), c.t1, bold: true),
                denseNum(context, formatSignedINR(totalPnl), context.pnlColor(totalPnl), bold: true),
                denseNum(context, formatPct(totalPnlPct), context.pnlColor(totalPnlPct), bold: true),
                denseNum(context, '100%', c.t3),
                const SizedBox.shrink(),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // ── MUTUAL FUND HOLDINGS TABLE (full) ──
          if (funds.isNotEmpty) ...[
            AnimatedListItem(
              index: 7,
              child: DenseTable(
                icon: LucideIcons.briefcase,
                accent: c.accent,
                title: 'Mutual Fund Holdings',
                subtitle: '${funds.length} schemes',
                trailing: densePnlTrailing(context, mfPnl, mfPnlPct),
                cols: _mfCols,
                rows: funds.map((f) {
                  final invested = (f['invested'] ?? 0).toDouble();
                  final curVal = (f['current_value'] ?? 0).toDouble();
                  final pnl = curVal - invested;
                  final retPct = (f['return_pct'] ??
                          (invested > 0 ? ((curVal - invested) / invested * 100) : 0))
                      .toDouble();
                  final xirrRaw = f['xirr'];
                  final double? xirr = xirrRaw is num ? xirrRaw.toDouble() : null;
                  final weight = mfCurrent > 0 ? (curVal / mfCurrent * 100) : 0.0;
                  return [
                    DInstrument(
                        symbol: (f['scheme_name'] ?? '').toString(),
                        sub: (f['category'] ?? '').toString(),
                        up: pnl >= 0,
                        ellipsis: true),
                    denseNum(context, (f['units'] ?? 0).toDouble().toStringAsFixed(3), c.t2),
                    denseNum(context, (f['avg_nav'] ?? 0).toDouble().toStringAsFixed(2), c.t3),
                    denseNum(context, (f['nav'] ?? 0).toDouble().toStringAsFixed(2), c.t1, bold: true),
                    denseNum(context, formatINR(invested), c.t3),
                    denseNum(context, formatINR(curVal), c.t2),
                    denseNum(context, formatSignedINR(pnl), context.pnlColor(pnl)),
                    denseNum(context, formatPct(retPct), context.pnlColor(retPct)),
                    DWeightCell(pct: weight, color: c.accent),
                    denseNum(context, xirr == null ? '—' : formatPct(xirr),
                        xirr == null ? c.t3 : context.pnlColor(xirr)),
                  ];
                }).toList(),
                footer: [
                  denseFootLabel(context, 'TOTAL · ${funds.length}'),
                  const SizedBox.shrink(),
                  const SizedBox.shrink(),
                  const SizedBox.shrink(),
                  denseNum(context, formatINR(mfInvested), c.t2, bold: true),
                  denseNum(context, formatINR(mfCurrent), c.t1, bold: true),
                  denseNum(context, formatSignedINR(mfPnl), context.pnlColor(mfPnl), bold: true),
                  denseNum(context, formatPct(mfPnlPct), context.pnlColor(mfPnlPct), bold: true),
                  denseNum(context, '100%', c.t3),
                  denseNum(context, mfTotalXirr == null ? '—' : formatPct(mfTotalXirr!),
                      mfTotalXirr == null ? c.t3 : context.pnlColor(mfTotalXirr!), bold: true),
                ],
              ),
            ),
            const SizedBox(height: 12),
          ],

          // ── GRAND TOTAL FOOTER ──
          AnimatedListItem(
            index: 8,
            child: DenseCard(
              padding: const EdgeInsets.all(14),
              child: Row(children: [
                Icon(LucideIcons.checkCircle2, size: 16, color: c.up),
                const SizedBox(width: 10),
                Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('End of Wealth Report', style: AppTextStyles.heading3(c.t1)),
                  Text(
                      'Total ${formatINR(combinedValue)} · ${holdings.length} equities · ${funds.length} mutual funds',
                      style: AppTextStyles.captionXs(c.t3)),
                ])),
                Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  Text('TOTAL P&L', style: AppTextStyles.labelXs(c.t3)),
                  const SizedBox(height: 4),
                  Text('${formatSignedINR(combinedPnl)}  ${formatPct(combinedPnlPct)}',
                      style: AppTextStyles.monoBold(context.pnlColor(combinedPnl))
                          .copyWith(fontSize: 14)),
                ]),
              ]),
            ),
          ),
          const SizedBox(height: 36),
        ]);
      },
    );
  }

  // ─── Helper widgets ────────────────────────────────────────

  Widget _signalStat(AppColorScheme c, String label, int count, Color color, IconData icon) {
    return Column(children: [
      Text('$count', style: AppTextStyles.monoBold(color).copyWith(fontSize: 15)),
      const SizedBox(height: 4),
      Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 11, color: color),
        const SizedBox(width: 4),
        Text(label, style: AppTextStyles.labelXs(c.t3)),
      ]),
    ]);
  }

  Widget _allocItem(BuildContext context, String title, Color color, double pct, double value, int count) {
    final c = context.colors;
    return Column(children: [
      Row(mainAxisSize: MainAxisSize.min, children: [
        Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(2))),
        const SizedBox(width: 6),
        Text(title, style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12)),
      ]),
      const SizedBox(height: 4),
      Text('${(pct * 100).toStringAsFixed(1)}% · $count items', style: AppTextStyles.captionXs(c.t3)),
      Text(formatINR(value), style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 13)),
    ]);
  }

  Widget _highlightCard(BuildContext context, String title, Map<String, dynamic>? data) {
    if (data == null) return const SizedBox.shrink();
    final c = context.colors;
    final sym = (data['symbol'] ?? '').toString().cleanSymbol;
    final ltp = (data['current_price'] ?? 0).toDouble();
    final dayChg = (data['day_chg'] ?? 0).toDouble();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
          color: c.bg1, borderRadius: BorderRadius.circular(8), border: Border.all(color: c.bd)),
      child: Row(children: [
        Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: AppTextStyles.labelXs(c.t3)),
          const SizedBox(height: 2),
          Text(sym, style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12)),
        ])),
        Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Text(ltp.toStringAsFixed(2), style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 12)),
          Text(formatPct(dayChg),
              style: AppTextStyles.mono(context.pnlColor(dayChg)).copyWith(fontSize: 11)),
        ]),
      ]),
    );
  }

  Widget _breakdownList(BuildContext context, List<_SectorBucket> items, double total, Color progressColor) {
    final c = context.colors;
    if (items.isEmpty) {
      return Padding(
          padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
          child: Text('No data', style: AppTextStyles.bodySmall(c.t3)));
    }
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
      child: Column(
        children: items.take(10).map((item) {
          final weight = total > 0 ? (item.value / total) : 0.0;
          return Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Column(children: [
              Row(children: [
                Expanded(
                    child: Text(item.name,
                        style: AppTextStyles.bodySmall(c.t1),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis)),
                Text('${(weight * 100).toStringAsFixed(1)}%', style: AppTextStyles.monoXs(c.t3)),
                const SizedBox(width: 12),
                SizedBox(
                    width: 80,
                    child: Text(formatSignedINR(item.pnl),
                        style: AppTextStyles.mono(context.pnlColor(item.pnl)).copyWith(fontSize: 12),
                        textAlign: TextAlign.right)),
              ]),
              const SizedBox(height: 5),
              ClipRRect(
                borderRadius: BorderRadius.circular(2),
                child: SizedBox(
                  height: 4,
                  child: Row(children: [
                    Expanded(
                        flex: (weight * 100).round().clamp(0, 100),
                        child: Container(color: progressColor)),
                    Expanded(
                        flex: (100 - (weight * 100).round()).clamp(0, 100),
                        child: Container(color: c.bg3)),
                  ]),
                ),
              ),
            ]),
          );
        }).toList(),
      ),
    );
  }
}

/// Helper class for sector/category aggregation
class _SectorBucket {
  final String name;
  double value;
  double pnl;
  _SectorBucket(this.name, this.value, this.pnl);
}
