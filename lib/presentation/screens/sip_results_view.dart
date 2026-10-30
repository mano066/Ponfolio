import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_colors.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/presentation/charts/portfolio_charts.dart';

/// SIP simulation results — Data-Dense Dashboard style.
class SIPResultsView extends StatefulWidget {
  final Map<String, dynamic> result;
  final bool portfolioMode;

  const SIPResultsView({super.key, required this.result, this.portfolioMode = false});

  @override
  State<SIPResultsView> createState() => _SIPResultsViewState();
}

class _SIPResultsViewState extends State<SIPResultsView> {
  String? _expandedSymbol;

  static const _cols = [
    DenseCol('#', 1, numeric: false),
    DenseCol('INSTRUMENT', 4, numeric: false),
    DenseCol('TYPE', 2, numeric: false),
    DenseCol('SOURCE', 2, numeric: false),
    DenseCol('₹/MO', 2),
    DenseCol('INVESTED', 2),
    DenseCol('CURRENT', 2),
    DenseCol('P&L', 2),
    DenseCol('RET%', 2),
    DenseCol('XIRR', 2),
  ];
  static const double _gutter = 22;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final r = widget.result;
    final isProfit = (r['absolute_return'] ?? 0) >= 0;

    final sipCount = r['sip_count'] ?? 0;
    final totalTx = r['total_transactions'] ?? sipCount;
    final numSymbols = r['num_symbols'] ?? 0;
    final monthlyTotal = (r['monthly_total'] ?? 0).toDouble();
    final totalInvested = (r['total_invested'] ?? 0).toDouble();
    final portfolioValue = (r['portfolio_value'] ?? 0).toDouble();
    final returnPct = (r['return_pct'] ?? 0).toDouble();
    final cagr = (r['cagr'] ?? 0).toDouble();
    final absReturn = portfolioValue - totalInvested;

    final timeline = List<Map<String, dynamic>>.from(r['timeline'] ?? []);
    final perSymbol = List<Map<String, dynamic>>.from(r['per_symbol'] ?? []);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // ── RESULT KPI GRID ──
        KpiGrid(perRow: 3, cells: [
          if (widget.portfolioMode) ...[
            Kpi('PERIOD', '$sipCount mo', '$totalTx transactions', c.t1),
            Kpi('INSTRUMENTS', '$numSymbols', '', c.t1),
          ] else ...[
            Kpi('SIP PERIOD', '$sipCount mo', '$totalTx installments', c.t1),
            Kpi('MONTHLY SIP', formatINR(monthlyTotal), '$numSymbols instruments', c.blue),
          ],
          Kpi('TOTAL INVESTED', formatINR(totalInvested), '', c.t1),
          Kpi('PORTFOLIO VALUE', formatINR(portfolioValue), formatSignedINR(absReturn),
              isProfit ? c.up : c.dn),
          Kpi('ABS RETURN', formatPct(returnPct), 'vs invested',
              context.pnlColor(returnPct)),
          Kpi('XIRR', formatPct(cagr), 'annualized', context.pnlColor(cagr)),
        ]),
        const SizedBox(height: 12),

        // ── PORTFOLIO GROWTH CHART ──
        if (timeline.isNotEmpty) ...[
          DenseCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              denseTableHeader(
                context,
                icon: LucideIcons.trendingUp,
                accent: isProfit ? c.up : c.dn,
                title: 'Portfolio Growth',
                subtitle: 'invested vs value',
                trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                  _legendDot(c.t3, 'INVESTED', c),
                  const SizedBox(width: 12),
                  _legendDot(isProfit ? c.up : c.dn, 'VALUE', c),
                ]),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
                child: SizedBox(height: 320, child: SIPTimelineChart(yearlyData: timeline)),
              ),
            ]),
          ),
          const SizedBox(height: 12),

          // ── RETURN % OVER TIME ──
          DenseCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              denseTableHeader(
                context,
                icon: LucideIcons.percent,
                accent: c.blue,
                title: 'Return % Over Time',
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
                child: SizedBox(height: 160, child: _ReturnPctChart(timeline: timeline)),
              ),
            ]),
          ),
          const SizedBox(height: 12),
        ],

        // ── PER-SYMBOL RANKING ──
        if (perSymbol.isNotEmpty)
          DenseCard(
            clip: true,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              denseTableHeader(
                context,
                icon: LucideIcons.barChart2,
                accent: c.gold,
                title: 'Performance Ranking',
                subtitle: 'sorted by return %',
              ),
              denseColumnHeader(context, _cols, leadingWidth: _gutter),
              ...perSymbol.asMap().entries.map((e) {
                final i = e.key;
                final s = e.value;
                final sym = s['symbol'] as String;
                final isExpanded = _expandedSymbol == sym;
                final pnl = (s['pnl'] ?? 0).toDouble();
                final pc = context.pnlColor(pnl);
                final source = (s['source'] ?? '').toString();
                final isKite = source.contains('Kite') || source.contains('Zerodha');
                final cleanSym =
                    sym.replaceAll(RegExp(r'\.(NS|BO)$', caseSensitive: false), '');

                return Column(children: [
                  DenseRow(
                    alt: i.isOdd,
                    highlighted: isExpanded,
                    leadingWidth: _gutter,
                    leading: Align(
                      alignment: Alignment.centerLeft,
                      child: Icon(
                          isExpanded ? LucideIcons.chevronDown : LucideIcons.chevronRight,
                          size: 14,
                          color: c.t4),
                    ),
                    onTap: () =>
                        setState(() => _expandedSymbol = isExpanded ? null : sym),
                    cols: _cols,
                    cells: [
                      Align(alignment: Alignment.centerLeft, child: _rankBadge(c, i)),
                      DInstrument(
                          symbol: s['label'] ?? '',
                          sub: '$cleanSym · LTP ₹${s['last_price'] ?? 0}',
                          up: pnl >= 0,
                          ellipsis: true),
                      Align(
                          alignment: Alignment.centerLeft,
                          child: AppBadge(
                              text: _shortType(s['type'] ?? ''), variant: BadgeVariant.blue)),
                      Align(
                          alignment: Alignment.centerLeft,
                          child: _sourceBadge(c, source, isKite)),
                      denseNum(context, formatINR((s['amount_per_month'] ?? 0).toDouble()), c.blue),
                      denseNum(context, formatINR((s['invested'] ?? 0).toDouble()), c.t3),
                      denseNum(context, formatINR((s['current_value'] ?? 0).toDouble()), pc,
                          bold: true),
                      denseNum(context, formatSignedINR(pnl), pc),
                      denseNum(
                          context,
                          '${(s['return_pct'] ?? 0) >= 0 ? "+" : ""}${s['return_pct'] ?? 0}%',
                          pc,
                          bold: true),
                      denseNum(
                          context,
                          '${(s['cagr'] ?? 0) >= 0 ? "+" : ""}${s['cagr'] ?? 0}%',
                          context.pnlColor(((s['cagr'] ?? 0) as num).toDouble()),
                          bold: true),
                    ],
                  ),
                  if (isExpanded) _buildExpandedDetail(c, s),
                ]);
              }),
            ]),
          ),
      ],
    );
  }

  Widget _legendDot(Color color, String label, AppColorScheme c) =>
      Row(mainAxisSize: MainAxisSize.min, children: [
        Container(
            width: 7,
            height: 7,
            decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(2))),
        const SizedBox(width: 4),
        Text(label, style: AppTextStyles.labelXs(c.t3)),
      ]);

  // ─── Expanded Detail (Yearly Bar Chart + Monthly Table + Yearly Cards) ───
  Widget _buildExpandedDetail(AppColorScheme c, Map<String, dynamic> s) {
    final yearly = List<Map<String, dynamic>>.from(s['yearly'] ?? []);
    final monthly = List<Map<String, dynamic>>.from(s['monthly'] ?? []);

    return Container(
      color: c.bg1,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // Yearly Bar Chart
        if (yearly.isNotEmpty) ...[
          Row(children: [
            Text('YEARLY PORTFOLIO — ${s['label']}', style: AppTextStyles.labelXs(c.t2)),
            const Spacer(),
            _legendDot(c.blue, 'INVESTED', c),
            const SizedBox(width: 10),
            _legendDot(c.up, 'PROFIT', c),
            const SizedBox(width: 10),
            _legendDot(c.dn, 'LOSS', c),
          ]),
          const SizedBox(height: 12),
          SizedBox(height: 280, child: _YearlyBarChart(yearly: yearly)),
          const SizedBox(height: 18),
        ],

        // Monthly SIP Breakdown Table
        Text('MONTHLY SIP BREAKDOWN — ${monthly.length} INSTALLMENTS',
            style: AppTextStyles.labelXs(c.t2)),
        const SizedBox(height: 8),
        Container(
          height: 360,
          clipBehavior: Clip.antiAlias,
          decoration: BoxDecoration(
              border: Border.all(color: c.bd), borderRadius: BorderRadius.circular(8)),
          child: Column(children: [
            // Table Header
            Container(
              color: c.bg3,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
              child: Row(children: [
                for (final h in [
                  'DATE',
                  'INVESTED',
                  'NAV',
                  'UNITS',
                  'TOTAL UNITS',
                  'TOTAL INVESTED',
                  'VALUE',
                  'P&L'
                ])
                  Expanded(
                      child: Text(h,
                          style: AppTextStyles.tableHeader(c.t3).copyWith(fontSize: 10))),
              ]),
            ),
            Expanded(
              child: ListView.builder(
                itemCount: monthly.length,
                itemBuilder: (ctx, idx) {
                  final m = monthly[idx];
                  final mp = (m['pnl'] ?? 0) >= 0 ? c.up : c.dn;
                  TextStyle mono(Color col) =>
                      AppTextStyles.mono(col).copyWith(fontSize: 12);
                  TextStyle monoB(Color col) =>
                      AppTextStyles.monoBold(col).copyWith(fontSize: 12);
                  return Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                    decoration: BoxDecoration(
                        color: idx.isOdd ? c.rowAlt : Colors.transparent,
                        border: Border(
                            bottom: BorderSide(color: c.bd.withValues(alpha: 0.6)))),
                    child: Row(children: [
                      Expanded(child: Text(m['date'] ?? '', style: mono(c.t1))),
                      Expanded(
                          child: Text(formatINR((m['invested'] ?? 0).toDouble()),
                              style: mono(c.blue))),
                      Expanded(child: Text('₹${m['nav']}', style: monoB(c.t1))),
                      Expanded(child: Text('${m['units_bought']}', style: mono(c.t2))),
                      Expanded(child: Text('${m['cumulative_units']}', style: mono(c.t1))),
                      Expanded(
                          child: Text(formatINR((m['cumulative_invested'] ?? 0).toDouble()),
                              style: mono(c.t2))),
                      Expanded(
                          child: Text(formatINR((m['current_value'] ?? 0).toDouble()),
                              style: monoB(mp))),
                      Expanded(
                          child: Text(formatSignedINR((m['pnl'] ?? 0).toDouble()),
                              style: monoB(mp))),
                    ]),
                  );
                },
              ),
            ),
          ]),
        ),

        // Yearly Summary Cards
        if (yearly.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text('YEARLY SUMMARY', style: AppTextStyles.labelXs(c.t2)),
          const SizedBox(height: 10),
          Wrap(spacing: 10, runSpacing: 10, children: yearly.map((y) {
            final yPnl = (y['pnl'] ?? 0).toDouble();
            final yRet = (y['return_pct'] ?? 0).toDouble();
            final yColor = yPnl >= 0 ? c.up : c.dn;
            return Container(
              width: 150,
              padding: const EdgeInsets.all(11),
              decoration: BoxDecoration(
                  color: c.bg2,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: c.bd)),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${y['year']}',
                    style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12)),
                const SizedBox(height: 2),
                Text('${y['months']} mo · ${formatINR((y['invested'] ?? 0).toDouble())}',
                    style: AppTextStyles.captionXs(c.t3)),
                const SizedBox(height: 6),
                Text(formatSignedINR(yPnl),
                    style: AppTextStyles.mono(yColor).copyWith(fontSize: 12)),
                Text('${yRet >= 0 ? "+" : ""}${yRet.toStringAsFixed(2)}%',
                    style: AppTextStyles.monoBold(yColor).copyWith(fontSize: 13)),
              ]),
            );
          }).toList()),
        ],
      ]),
    );
  }

  Widget _rankBadge(AppColorScheme c, int i) {
    return Container(
      width: 20,
      height: 20,
      decoration: BoxDecoration(
        color: i == 0 ? c.goldBg : i == 1 ? const Color(0x339CA3AF) : c.bg3,
        shape: BoxShape.circle,
        border: Border.all(color: i == 0 ? c.gold.withValues(alpha: 0.3) : c.bd),
      ),
      child: Center(
          child: Text('${i + 1}',
              style: AppTextStyles.captionXs(
                      i == 0 ? c.gold : i == 1 ? const Color(0xFFD1D5DB) : c.t4)
                  .copyWith(fontWeight: FontWeight.bold))),
    );
  }

  Widget _sourceBadge(AppColorScheme c, String source, bool isKite) {
    if (source.isEmpty) return Text('—', style: AppTextStyles.monoXs(c.t4));
    final col = isKite ? c.up : c.blue;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: col.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: col.withValues(alpha: 0.22)),
      ),
      child: Text(source,
          style: AppTextStyles.labelXs(col).copyWith(fontSize: 9),
          maxLines: 1,
          overflow: TextOverflow.ellipsis),
    );
  }

  /// Shorten long MF category names for badge display
  String _shortType(String type) {
    if (type.isEmpty) return 'N/A';
    final map = {
      'Fund of Funds': 'FoF',
      'Flexi Cap Fund': 'Flexi Cap',
      'Dynamic Asset Allocation or Balanced Advantage': 'Balanced',
      'ELSS': 'ELSS',
      'Large Cap Fund': 'Large Cap',
      'Mid Cap Fund': 'Mid Cap',
      'Small Cap Fund': 'Small Cap',
      'Multi Cap Fund': 'Multi Cap',
      'Sectoral/ Thematic': 'Sectoral',
      'Index Fund': 'Index',
      'Focused Fund': 'Focused',
      'Value Fund': 'Value',
      'Contra Fund': 'Contra',
      'Dividend Yield Fund': 'Div Yield',
      'Large & Mid Cap Fund': 'L&M Cap',
    };
    for (final e in map.entries) {
      if (type.toLowerCase().contains(e.key.toLowerCase())) return e.value;
    }
    // Fallback: take first 12 chars
    return type.length > 12 ? '${type.substring(0, 12)}…' : type;
  }
}

// ─── Return % Over Time Line Chart ───
class _ReturnPctChart extends StatelessWidget {
  final List<Map<String, dynamic>> timeline;
  const _ReturnPctChart({required this.timeline});

  @override
  Widget build(BuildContext context) {
    if (timeline.isEmpty) return const SizedBox.shrink();
    final c = context.colors;

    final spots = <FlSpot>[];
    for (int i = 0; i < timeline.length; i++) {
      spots.add(FlSpot(i.toDouble(), (timeline[i]['pnl_pct'] ?? 0).toDouble()));
    }

    final maxY = spots.map((s) => s.y.abs()).fold(1.0, (a, b) => a > b ? a : b);

    return LineChart(LineChartData(
      minX: 0, maxX: (timeline.length - 1).toDouble(),
      minY: -maxY * 1.2, maxY: maxY * 1.2,
      gridData: FlGridData(
        show: true, drawVerticalLine: false,
        getDrawingHorizontalLine: (v) => FlLine(color: c.bd.withValues(alpha: 0.2), strokeWidth: 1),
      ),
      titlesData: FlTitlesData(
        topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        bottomTitles: AxisTitles(sideTitles: SideTitles(
          showTitles: true, reservedSize: 24,
          interval: (timeline.length / 8).ceilToDouble().clamp(1, double.infinity),
          getTitlesWidget: (v, _) {
            final i = v.toInt();
            if (i < 0 || i >= timeline.length) return const SizedBox.shrink();
            return Text((timeline[i]['date'] ?? '').toString().substring(0, 7),
                style: AppTextStyles.monoXs(c.t4).copyWith(fontSize: 9));
          },
        )),
        leftTitles: AxisTitles(sideTitles: SideTitles(
          showTitles: true, reservedSize: 40,
          getTitlesWidget: (v, _) => Text('${v.toStringAsFixed(0)}%',
              style: AppTextStyles.monoXs(c.t4).copyWith(fontSize: 9)),
        )),
      ),
      borderData: FlBorderData(show: false),
      extraLinesData: ExtraLinesData(horizontalLines: [HorizontalLine(y: 0, color: c.t4.withValues(alpha: 0.4), strokeWidth: 1, dashArray: [4, 4])]),
      lineTouchData: LineTouchData(
        touchTooltipData: LineTouchTooltipData(
          getTooltipColor: (_) => c.bg1.withValues(alpha: 0.95),
          tooltipBorder: BorderSide(color: c.bd),
          getTooltipItems: (spots) => spots.map((s) => LineTooltipItem(
            '${s.y.toStringAsFixed(2)}%',
            TextStyle(color: c.blue, fontSize: 11, fontWeight: FontWeight.w600),
          )).toList(),
        ),
      ),
      lineBarsData: [
        LineChartBarData(
          spots: spots,
          color: c.blue, barWidth: 2, isStrokeCapRound: true,
          dotData: const FlDotData(show: false),
          belowBarData: BarAreaData(show: true, color: c.blue.withValues(alpha: 0.08)),
        ),
      ],
    ));
  }
}

// ─── Yearly Stacked Bar Chart ───
class _YearlyBarChart extends StatelessWidget {
  final List<Map<String, dynamic>> yearly;
  const _YearlyBarChart({required this.yearly});

  @override
  Widget build(BuildContext context) {
    if (yearly.isEmpty) return const SizedBox.shrink();
    final c = context.colors;

    final maxVal = yearly.map((y) {
      final inv = (y['cumulative_invested'] ?? 0).toDouble();
      final pnl = (y['pnl'] ?? 0).toDouble();
      return inv + (pnl > 0 ? pnl : 0);
    }).fold(1.0, (a, b) => a > b ? a : b);

    return BarChart(BarChartData(
      alignment: BarChartAlignment.spaceAround,
      maxY: maxVal * 1.15,
      gridData: FlGridData(
        show: true, drawVerticalLine: false,
        getDrawingHorizontalLine: (v) => FlLine(color: c.bd.withValues(alpha: 0.3), strokeWidth: 1),
      ),
      titlesData: FlTitlesData(
        topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        bottomTitles: AxisTitles(sideTitles: SideTitles(
          showTitles: true, reservedSize: 28,
          getTitlesWidget: (v, _) {
            final i = v.toInt();
            if (i < 0 || i >= yearly.length) return const SizedBox.shrink();
            return Text('${yearly[i]['year']}',
                style: AppTextStyles.monoXs(c.t2).copyWith(fontSize: 10));
          },
        )),
        leftTitles: AxisTitles(sideTitles: SideTitles(
          showTitles: true, reservedSize: 55,
          getTitlesWidget: (v, _) {
            if (v >= 100000) {
              return Text('₹${(v / 100000).toStringAsFixed(1)}L',
                  style: AppTextStyles.monoXs(c.t3).copyWith(fontSize: 9));
            }
            return Text('₹${(v / 1000).toStringAsFixed(0)}K',
                style: AppTextStyles.monoXs(c.t3).copyWith(fontSize: 9));
          },
        )),
      ),
      borderData: FlBorderData(show: false),
      barTouchData: BarTouchData(
        touchTooltipData: BarTouchTooltipData(
          getTooltipColor: (_) => c.bg2.withValues(alpha: 0.95),
          tooltipBorder: BorderSide(color: c.bd),
          getTooltipItem: (group, gi, rod, ri) {
            final y = yearly[group.x.toInt()];
            final pnl = (y['pnl'] ?? 0).toDouble();
            final isP = pnl >= 0;
            return BarTooltipItem(
              '${y['year']}\nInvested: ${formatINR((y['cumulative_invested'] ?? 0).toDouble())}\nP&L: ${isP ? "+" : ""}${formatINR(pnl)} (${isP ? "+" : ""}${y['return_pct']}%)\nValue: ${formatINR((y['value'] ?? 0).toDouble())}',
              TextStyle(color: c.t1, fontSize: 11, fontWeight: FontWeight.w600),
            );
          },
        ),
      ),
      barGroups: List.generate(yearly.length, (i) {
        final y = yearly[i];
        final invested = (y['cumulative_invested'] ?? 0).toDouble();
        final pnl = (y['pnl'] ?? 0).toDouble();
        final profit = pnl > 0 ? pnl : 0.0;
        final loss = pnl < 0 ? pnl.abs() : 0.0;

        return BarChartGroupData(x: i, barRods: [
          BarChartRodData(
            toY: invested + profit,
            width: 28,
            borderRadius: BorderRadius.circular(4),
            rodStackItems: [
              if (loss > 0) BarChartRodStackItem(0, loss, c.dn),
              BarChartRodStackItem(loss > 0 ? loss : 0, (loss > 0 ? loss : 0) + invested, c.blue),
              if (profit > 0) BarChartRodStackItem((loss > 0 ? loss : 0) + invested, (loss > 0 ? loss : 0) + invested + profit, c.up),
            ],
            color: Colors.transparent,
          ),
        ]);
      }),
    ));
  }
}
