import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';

// ═══════════════════════════════════════════════════════════════════
//  RISK-RETURN SCATTER CHART — Holdings plotted by risk vs return
//  (Data-Dense style: hairline gridlines, mono axis labels, no glow.)
// ═══════════════════════════════════════════════════════════════════

class RiskReturnScatterChart extends StatefulWidget {
  final List<Map<String, dynamic>> holdings;

  const RiskReturnScatterChart({super.key, required this.holdings});

  @override
  State<RiskReturnScatterChart> createState() => _RiskReturnScatterChartState();
}

class _RiskReturnScatterChartState extends State<RiskReturnScatterChart>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200));
    _anim = CurvedAnimation(parent: _ctrl, curve: Curves.easeOutCubic);
    _ctrl.forward();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.holdings.isEmpty) return const SizedBox.shrink();
    final c = context.colors;

    // Build scatter data from holdings.
    // X = today's absolute move (abs day_chg) — a single-day snapshot, NOT volatility.
    // Y = net return since purchase.
    final spots = <ScatterSpot>[];
    final labels = <String>[];
    for (final h in widget.holdings) {
      final risk = ((h['day_chg'] ?? 0) as num).abs().toDouble();
      final ret = ((h['net_chg'] ?? 0) as num).toDouble();
      final sym = (h['symbol'] ?? '').toString().replaceAll(RegExp(r'\.(NS|BO)$', caseSensitive: false), '');
      labels.add(sym);
      spots.add(ScatterSpot(
        risk,
        ret,
        dotPainter: FlDotCirclePainter(
          radius: 5,
          color: ret >= 0 ? c.up.withValues(alpha: 0.8) : c.dn.withValues(alpha: 0.8),
          strokeWidth: 1,
          strokeColor: ret >= 0 ? c.up : c.dn,
        ),
      ));
    }

    if (spots.isEmpty) return const SizedBox.shrink();

    final maxRisk = spots.map((s) => s.x).reduce((a, b) => a > b ? a : b).clamp(1.0, double.infinity);
    final allReturns = spots.map((s) => s.y).toList();
    final maxRet = allReturns.reduce((a, b) => a > b ? a : b).clamp(1.0, double.infinity);
    final minRet = allReturns.reduce((a, b) => a < b ? a : b).clamp(double.negativeInfinity, 0.0);

    final axisLabel = AppTextStyles.monoXs(c.t3).copyWith(fontSize: 9);

    return AnimatedBuilder(
      animation: _anim,
      builder: (_, _) => SizedBox(
        height: 280,
        child: Opacity(
          opacity: _anim.value,
          child: ScatterChart(ScatterChartData(
            minX: 0, maxX: maxRisk * 1.3,
            minY: minRet * 1.3, maxY: maxRet * 1.3,
            gridData: FlGridData(
              show: true, drawVerticalLine: true,
              horizontalInterval: maxRet / 3,
              verticalInterval: maxRisk / 3,
              getDrawingHorizontalLine: (v) => FlLine(color: c.bd.withValues(alpha: 0.6), strokeWidth: 0.5),
              getDrawingVerticalLine: (v) => FlLine(color: c.bd.withValues(alpha: 0.6), strokeWidth: 0.5),
            ),
            titlesData: FlTitlesData(
              topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
              rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
              bottomTitles: AxisTitles(
                axisNameWidget: Text("TODAY'S MOVE %", style: AppTextStyles.labelXs(c.t3)),
                sideTitles: SideTitles(
                  showTitles: true, reservedSize: 28,
                  getTitlesWidget: (v, _) => Text('${v.toStringAsFixed(1)}%', style: axisLabel),
                ),
              ),
              leftTitles: AxisTitles(
                axisNameWidget: Text('NET RETURN %', style: AppTextStyles.labelXs(c.t3)),
                sideTitles: SideTitles(
                  showTitles: true, reservedSize: 48,
                  getTitlesWidget: (v, _) => Text('${v.toStringAsFixed(1)}%', style: axisLabel),
                ),
              ),
            ),
            borderData: FlBorderData(show: false),
            scatterSpots: spots.map((s) => ScatterSpot(
              s.x * _anim.value,
              s.y * _anim.value,
              dotPainter: s.dotPainter,
            )).toList(),
            scatterTouchData: ScatterTouchData(
              touchTooltipData: ScatterTouchTooltipData(
                getTooltipColor: (_) => c.bg1.withValues(alpha: 0.95),
                tooltipBorder: BorderSide(color: c.bd),
                getTooltipItems: (spot) {
                  final idx = spots.indexWhere((s) => (s.x - spot.x / _anim.value).abs() < 0.01 && (s.y - spot.y / _anim.value).abs() < 0.01);
                  final label = idx >= 0 && idx < labels.length ? labels[idx] : '';
                  return ScatterTooltipItem(
                    "$label\nReturn: ${spot.y.toStringAsFixed(2)}%\nToday: ${spot.x.toStringAsFixed(2)}%",
                    textStyle: AppTextStyles.monoXs(c.t2).copyWith(fontSize: 10),
                  );
                },
              ),
            ),
          )),
        ),
      ),
    );
  }
}
