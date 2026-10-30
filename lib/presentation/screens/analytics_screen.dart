import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_colors.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/providers/providers.dart';
import 'package:aiei_wealth/presentation/charts/portfolio_charts.dart';
import 'package:aiei_wealth/presentation/widgets/animated_page_wrapper.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/presentation/widgets/portfolio_analytics_widgets.dart';

/// Portfolio Analytics — Data-Dense Dashboard style: a compact KPI grid of
/// risk metrics, a dense health-factor card, monospace sector/ranking tables
/// and muted charts inside standard DenseCards.
class AnalyticsScreen extends ConsumerWidget {
  const AnalyticsScreen({super.key});

  /// Accessible sector series colors resolved from theme tokens so the
  /// allocation bars + pie stay legible on the light surface. Ordered palette
  /// cycles through the token accents for any additional sectors.
  static Color _sectorColor(AppColorScheme c, String key) {
    switch (key) {
      case 'Finance':
        return c.blue;
      case 'Technology':
        return c.accent;
      case 'Energy':
        return c.gold;
      case 'Consumer':
        return c.up;
      case 'Infrastructure':
        return c.cyan;
      case 'Telecom':
        return c.dn;
      default:
        return c.t3;
    }
  }

  /// Max annualized-volatility used for gauge scaling (0–[_kVolMax]%).
  static const double _kVolMax = 60;

  /// Parse a metric that may be a real double or a genuine null ("not
  /// computable"). Returns null when the field is absent or null — never
  /// substitutes a fake default.
  static double? _num(Object? v) => v == null ? null : (v as num).toDouble();

  /// Calculate a portfolio health score (0-100) from the analytics metrics.
  /// Each of the four components (beta, sharpe, diversification, volatility)
  /// carries equal weight, but any null component is skipped and the weight
  /// re-normalized across the components that ARE computable. Returns null
  /// when nothing is computable so callers can render "N/A".
  double? _computeHealthScore(Map<String, dynamic> data) {
    double sum = 0;
    double weight = 0;

    // Beta factor (ideal ~1.0, penalize extremes).
    final beta = _num(data['portfolio_beta']);
    if (beta != null) {
      double b;
      if (beta <= 1.0) {
        b = 1;
      } else if (beta <= 1.5) {
        b = (1 - (beta - 1.0) / 1.0);
      } else {
        b = 0.2; // high beta = low score
      }
      sum += b.clamp(0.0, 1.0);
      weight += 1;
    }

    // Sharpe ratio (higher = better, cap at 5).
    final sharpe = _num(data['sharpe_ratio']);
    if (sharpe != null) {
      sum += (sharpe.clamp(0.0, 5.0) / 5);
      weight += 1;
    }

    // Diversification (0-100%).
    final diversification = _num(data['diversification_score']);
    if (diversification != null) {
      sum += (diversification.clamp(0.0, 100.0) / 100);
      weight += 1;
    }

    // Volatility (lower = better) — annualized %, scaled against _kVolMax.
    final vol = _num(data['volatility']);
    if (vol != null) {
      sum += (1 - (vol.clamp(0.0, _kVolMax) / _kVolMax));
      weight += 1;
    }

    if (weight == 0) return null;
    return (sum / weight * 100).clamp(0, 100);
  }

  /// Largest-remainder (Hamilton) rounding: integer percentages that sum to
  /// exactly 100 (avoids independent .round() drifting off 100).
  static List<MapEntry<String, int>> _percentAllocations(
      List<MapEntry<String, double>> entries, double total) {
    if (total <= 0 || entries.isEmpty) {
      return entries.map((e) => MapEntry(e.key, 0)).toList();
    }
    final exact = entries.map((e) => e.value / total * 100).toList();
    final floors = exact.map((v) => v.floor()).toList();
    var remainder = 100 - floors.fold<int>(0, (a, b) => a + b);
    // Distribute the leftover to the largest fractional parts.
    final order = List<int>.generate(exact.length, (i) => i)
      ..sort((a, b) => (exact[b] - floors[b]).compareTo(exact[a] - floors[a]));
    for (var i = 0; i < order.length && remainder > 0; i++, remainder--) {
      floors[order[i]] += 1;
    }
    return [for (var i = 0; i < entries.length; i++) MapEntry(entries[i].key, floors[i])];
  }

  // ── Rating helpers (labels + colors for the KPI cells) ──
  static String _sharpeLabel(double v) {
    if (v < 0) return 'negative';
    if (v < 1) return 'poor';
    if (v < 2) return 'fair';
    if (v < 3) return 'good';
    return 'excellent';
  }

  static Color _sharpeColor(double v, AppColorScheme c) {
    if (v < 0) return c.dn;
    if (v < 1) return c.gold;
    if (v < 2) return c.t1;
    return c.up;
  }

  static String _healthLabel(double s) {
    if (s >= 80) return 'excellent';
    if (s >= 60) return 'good';
    if (s >= 40) return 'fair';
    if (s >= 20) return 'poor';
    return 'critical';
  }

  static Color _healthColor(double s, AppColorScheme c) {
    if (s >= 80) return c.up;
    if (s >= 60) return c.blue;
    if (s >= 40) return c.gold;
    return c.dn;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final portfolio = ref.watch(portfolioProvider);
    final analytics = ref.watch(analyticsProvider);

    final holdings = portfolio.when(
      data: (d) => List<Map<String, dynamic>>.from(d['holdings'] ?? []),
      loading: () => <Map<String, dynamic>>[], error: (_, _) => <Map<String, dynamic>>[],
    );
    final totalValue = portfolio.when(
      data: (d) => (d['total_portfolio_value'] ?? 0).toDouble(),
      loading: () => 0.0, error: (_, _) => 0.0,
    );

    // Sector allocation
    final sectorMap = <String, double>{};
    for (final h in holdings) {
      final s = (h['sector'] ?? 'Other') as String;
      sectorMap[s] = (sectorMap[s] ?? 0) + (h['total_value'] ?? 0).toDouble();
    }
    // Percentages via largest-remainder rounding so the bars always sum to 100.
    final sortedEntries = sectorMap.entries.toList()..sort((a, b) => b.value.compareTo(a.value));
    final sectors = _percentAllocations(sortedEntries, totalValue);

    // Holdings ranked (display list only; top/worst come from analytics).
    final ranked = [...holdings]..sort((a, b) => ((b['net_chg'] ?? 0) as num).compareTo((a['net_chg'] ?? 0) as num));

    return ListView(padding: EdgeInsets.zero, children: [
      // ── RISK KPI GRID + HEALTH (analytics-backed) ──
      analytics.when(
        loading: () => const Padding(
          padding: EdgeInsets.symmetric(vertical: 48),
          child: DensePulseLoader(label: 'Computing analytics…'),
        ),
        error: (e, _) => ErrorRetry(
          title: 'Error loading analytics',
          detail: '$e',
          compact: true,
          onRetry: () => ref.invalidate(analyticsProvider),
        ),
        data: (data) {
          // Every metric may be a genuine null ("not computable") — never
          // substitute a fake default.
          final beta = _num(data['portfolio_beta']);
          final sharpe = _num(data['sharpe_ratio']);
          final oneYearReturn = _num(data['one_year_return']);
          final diversification = _num(data['diversification_score']);
          final numSectors = (data['num_sectors'] as num?)?.toInt();
          final volatility = _num(data['volatility'] ?? data['volatility_index']);
          final nifty1y = _num(data['nifty_1y_return']);
          final healthScore = _computeHealthScore(data);

          // Top / worst performer come from the analytics endpoint (single
          // source of truth for both symbol AND percentage).
          final topPerf = data['top_performer']?.toString();
          final topChg = _num(data['top_performer_pct']);
          final worstPerfRaw = data['worst_performer'];
          final worstPerf = worstPerfRaw?.toString();
          final worstChg = _num(data['worst_performer_pct']);
          final hasWorst = worstPerf != null && worstPerf.isNotEmpty;

          final divRating = diversification == null
              ? null
              : diversification >= 70
                  ? 'well diversified'
                  : diversification >= 40
                      ? 'moderate'
                      : 'concentrated';
          final divAccent = diversification == null
              ? c.t3
              : diversification >= 70
                  ? c.up
                  : diversification >= 40
                      ? c.gold
                      : c.dn;
          final volAccent = volatility == null
              ? c.t3
              : volatility < 15
                  ? c.up
                  : volatility < 30
                      ? c.t1
                      : c.dn;

          return Column(children: [
            // ── KPI GRID (2 rows × 4) ──
            AnimatedListItem(
              index: 0,
              child: KpiGrid(cells: [
                Kpi(
                    'PORTFOLIO BETA',
                    beta != null ? beta.toStringAsFixed(2) : '—',
                    'vs NIFTY 50',
                    beta == null
                        ? c.t3
                        : beta > 1.2
                            ? c.dn
                            : beta < 0.8
                                ? c.up
                                : c.t1),
                Kpi(
                    'SHARPE RATIO',
                    sharpe != null ? sharpe.toStringAsFixed(2) : '—',
                    sharpe != null ? '${_sharpeLabel(sharpe)} · risk-adjusted' : 'not computable',
                    sharpe != null ? _sharpeColor(sharpe, c) : c.t3),
                Kpi(
                    '1Y RETURN',
                    oneYearReturn != null ? formatPct(oneYearReturn) : '—',
                    nifty1y != null
                        ? 'NIFTY ${formatPct(nifty1y)} · trailing 12M'
                        : 'trailing 12M (historical)',
                    oneYearReturn != null ? context.pnlColor(oneYearReturn) : c.t3),
                Kpi(
                    'DIVERSIFICATION',
                    diversification != null ? '${diversification.toStringAsFixed(0)}%' : '—',
                    [
                      ?divRating,
                      if (numSectors != null) '$numSectors ${numSectors == 1 ? "sector" : "sectors"}',
                    ].join(' · '),
                    divAccent),
                Kpi(
                    'VOLATILITY',
                    volatility != null ? '${volatility.toStringAsFixed(1)}%' : '—',
                    'annualized σ of daily returns',
                    volAccent),
                Kpi(
                    'TOP PERFORMER',
                    (topPerf == null || topPerf.isEmpty) ? '—' : topPerf.cleanSymbol,
                    topChg != null ? '${formatPct(topChg)} net return' : '',
                    (topPerf == null || topPerf.isEmpty) ? c.t3 : c.up),
                Kpi(
                    'WORST PERFORMER',
                    hasWorst ? worstPerf.cleanSymbol : '—',
                    hasWorst && worstChg != null ? '${formatPct(worstChg)} net return' : '',
                    hasWorst ? c.dn : c.t3),
                Kpi(
                    'HEALTH SCORE',
                    healthScore != null ? '${healthScore.round()}/100' : '—',
                    healthScore != null ? _healthLabel(healthScore) : 'not computable',
                    healthScore != null ? _healthColor(healthScore, c) : c.t3),
              ]),
            ),
            const SizedBox(height: 12),

            // ── PORTFOLIO HEALTH FACTORS ──
            AnimatedListItem(
              index: 1,
              child: _healthCard(context, c,
                  score: healthScore,
                  beta: beta,
                  sharpe: sharpe,
                  diversification: diversification,
                  volatility: volatility),
            ),
          ]);
        },
      ),
      const SizedBox(height: 12),

      // ── SECTOR ALLOCATION + HOLDINGS RANKED ──
      AnimatedListItem(
        index: 2,
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(child: _sectorCard(context, c, sortedEntries, sectors, totalValue)),
          const SizedBox(width: 12),
          Expanded(child: _rankedCard(context, c, ranked)),
        ]),
      ),
      const SizedBox(height: 12),

      // ── RISK-RETURN SCATTER + SECTOR PIE ──
      AnimatedListItem(
        index: 3,
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(
            child: DenseCard(
              clip: true,
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                denseTableHeader(context,
                    icon: LucideIcons.crosshair,
                    accent: c.cyan,
                    title: 'Risk vs Return',
                    subtitle: "each dot = a stock · today's move vs net return"),
                Padding(
                  padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
                  child: RiskReturnScatterChart(holdings: holdings),
                ),
              ]),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: DenseCard(
              clip: true,
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                denseTableHeader(context,
                    icon: LucideIcons.pieChart,
                    accent: c.accent,
                    title: 'Sector Distribution',
                    subtitle: '${sectorMap.length} sectors by value'),
                Padding(
                  padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
                  child: SectorPieChart(sectors: sectorMap),
                ),
              ]),
            ),
          ),
        ]),
      ),
      const SizedBox(height: 12),

      // ── PERFORMANCE BAR CHART (full width) ──
      AnimatedListItem(
        index: 4,
        child: DenseCard(
          clip: true,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            denseTableHeader(context,
                icon: LucideIcons.barChart3,
                accent: c.blue,
                title: 'Stock Performance',
                subtitle: 'net return % per holding'),
            PerformanceBarChart(holdings: holdings, height: 280),
          ]),
        ),
      ),
      const SizedBox(height: 36),
    ]);
  }

  // ── Portfolio health factor card ──
  Widget _healthCard(
    BuildContext context,
    AppColorScheme c, {
    required double? score,
    required double? beta,
    required double? sharpe,
    required double? diversification,
    required double? volatility,
  }) {
    final accent = score != null ? _healthColor(score, c) : c.t3;
    return DenseCard(
      clip: true,
      child: Column(children: [
        denseTableHeader(context,
            icon: LucideIcons.heartPulse,
            accent: accent,
            title: 'Portfolio Health',
            subtitle: 'equal-weighted: beta · sharpe · diversification · volatility',
            trailing: Text(score != null ? '${score.round()}/100' : 'N/A',
                style: AppTextStyles.monoBold(accent).copyWith(fontSize: 14))),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 2, 14, 12),
          child: Row(children: [
            Expanded(
                child: _factor(context, c, 'DIVERSIFICATION', diversification,
                    max: 100, suffix: '%', color: c.blue)),
            const SizedBox(width: 20),
            Expanded(
                child: _factor(context, c, 'RISK (BETA)', beta,
                    max: 3, suffix: '', color: (beta ?? 1) <= 1.5 ? c.up : c.gold)),
            const SizedBox(width: 20),
            Expanded(
                child: _factor(context, c, 'SHARPE RATIO', sharpe,
                    max: 5, suffix: '', color: (sharpe ?? 0) >= 2 ? c.up : c.gold)),
            const SizedBox(width: 20),
            Expanded(
                child: _factor(context, c, 'VOLATILITY', volatility,
                    max: _kVolMax,
                    suffix: '%',
                    color: (volatility ?? 0) <= _kVolMax * 0.6 ? c.up : c.dn)),
          ]),
        ),
      ]),
    );
  }

  Widget _factor(BuildContext context, AppColorScheme c, String label, double? value,
      {required double max, required String suffix, required Color color}) {
    final frac = value != null ? (value / max).clamp(0.0, 1.0) : 0.0;
    final barColor = value != null ? color : c.t4;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text(label, style: AppTextStyles.labelXs(c.t3)),
        Text(
            value != null
                ? '${value.toStringAsFixed(value == value.roundToDouble() ? 0 : 2)}$suffix'
                : 'N/A',
            style: AppTextStyles.monoBold(barColor).copyWith(fontSize: 12)),
      ]),
      const SizedBox(height: 5),
      ClipRRect(
        borderRadius: BorderRadius.circular(2),
        child: LinearProgressIndicator(
            value: frac, minHeight: 3, backgroundColor: c.bg3, color: barColor),
      ),
    ]);
  }

  // ── Sector allocation dense table ──
  static const _sectorCols = [
    DenseCol('SECTOR', 3, numeric: false),
    DenseCol('VALUE', 2),
    DenseCol('WT%', 2),
  ];

  Widget _sectorCard(BuildContext context, AppColorScheme c,
      List<MapEntry<String, double>> entries, List<MapEntry<String, int>> pcts, double totalValue) {
    return DenseCard(
      clip: true,
      child: Column(children: [
        denseTableHeader(context,
            icon: LucideIcons.barChart2,
            accent: c.blue,
            title: 'Sector Allocation',
            subtitle: '${entries.length} sectors · by value'),
        denseColumnHeader(context, _sectorCols),
        if (entries.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 26),
            child: Text('No holdings', style: AppTextStyles.bodySmall(c.t3)),
          )
        else
          ...List.generate(entries.length, (i) {
            final e = entries[i];
            final clr = _sectorColor(c, e.key);
            return DenseRow(
              alt: i.isOdd,
              cols: _sectorCols,
              cells: [
                Row(children: [
                  Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(color: clr, borderRadius: BorderRadius.circular(2))),
                  const SizedBox(width: 8),
                  Flexible(
                      child: Text(e.key,
                          style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis)),
                ]),
                denseNum(context, formatINR(e.value), c.t2),
                DWeightCell(pct: pcts[i].value.toDouble(), color: clr),
              ],
            );
          }),
        if (entries.isNotEmpty)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
            decoration: BoxDecoration(color: c.bg3, border: Border(top: BorderSide(color: c.bd))),
            child: Row(children: [
              Expanded(flex: 3, child: denseFootLabel(context, 'TOTAL · ${entries.length}')),
              Expanded(flex: 2, child: denseNum(context, formatINR(totalValue), c.t1, bold: true)),
              Expanded(flex: 2, child: denseNum(context, '100%', c.t2, bold: true)),
            ]),
          ),
      ]),
    );
  }

  // ── Holdings ranked dense table (fixed-height scroll like before) ──
  static const _rankCols = [
    DenseCol('INSTRUMENT', 3, numeric: false),
    DenseCol('NET RET%', 2),
  ];
  static const double _rankGutter = 26;

  Widget _rankedCard(BuildContext context, AppColorScheme c, List<Map<String, dynamic>> ranked) {
    return DenseCard(
      clip: true,
      child: Column(children: [
        denseTableHeader(context,
            icon: LucideIcons.trendingUp,
            accent: c.up,
            title: 'Holdings Ranked by Return',
            subtitle: '${ranked.length} holdings · best first'),
        denseColumnHeader(context, _rankCols, leadingWidth: _rankGutter),
        SizedBox(
          height: 360,
          child: ranked.isEmpty
              ? Center(child: Text('No holdings', style: AppTextStyles.bodySmall(c.t3)))
              : ListView.builder(
                  padding: EdgeInsets.zero,
                  itemCount: ranked.length,
                  itemBuilder: (_, i) {
                    final h = ranked[i];
                    final sym = (h['symbol'] ?? '').toString().cleanSymbol;
                    final sector = (h['sector'] ?? '').toString();
                    final netChg = (h['net_chg'] ?? 0).toDouble();
                    return DenseRow(
                      alt: i.isOdd,
                      leadingWidth: _rankGutter,
                      leading: Align(
                        alignment: Alignment.centerLeft,
                        child: Text('${i + 1}',
                            style: AppTextStyles.monoXs(i == 0 ? c.gold : i < 3 ? c.blue : c.t4)),
                      ),
                      cols: _rankCols,
                      cells: [
                        DInstrument(symbol: sym, sub: sector, up: netChg >= 0),
                        denseDelta(context, netChg),
                      ],
                    );
                  },
                ),
        ),
      ]),
    );
  }
}
