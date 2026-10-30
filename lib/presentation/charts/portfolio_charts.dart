import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';

/// SIP Simulator dual-line chart: Invested vs Value over time
/// Enhanced with gradient glow, animated markers, and glassmorphism tooltips.
class SIPTimelineChart extends StatefulWidget {
  final List<Map<String, dynamic>> yearlyData;
  final double height;

  const SIPTimelineChart({super.key, required this.yearlyData, this.height = 280});

  @override
  State<SIPTimelineChart> createState() => _SIPTimelineChartState();
}

class _SIPTimelineChartState extends State<SIPTimelineChart>
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
    if (widget.yearlyData.isEmpty) return const SizedBox.shrink();
    final c = context.colors;

    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) {
        final progress = _anim.value;
        final investedSpots = <FlSpot>[];
        final valueSpots = <FlSpot>[];
        final dataCount = (widget.yearlyData.length * progress).ceil().clamp(1, widget.yearlyData.length);

        for (int i = 0; i < dataCount; i++) {
          final y = widget.yearlyData[i];
          investedSpots.add(FlSpot(i.toDouble(), (y['invested'] ?? 0).toDouble()));
          valueSpots.add(FlSpot(i.toDouble(), (y['value'] ?? 0).toDouble()));
        }

        final allVals = [
          ...widget.yearlyData.map((y) => (y['invested'] ?? 0).toDouble()),
          ...widget.yearlyData.map((y) => (y['value'] ?? 0).toDouble()),
        ];
        final maxVal = allVals.isEmpty ? 1.0 : allVals.reduce((a, b) => a > b ? a : b);

        return Container(
          height: widget.height,
          padding: const EdgeInsets.only(right: 16, top: 16),
          decoration: BoxDecoration(
            color: c.bg2, borderRadius: BorderRadius.circular(12),
            border: Border.all(color: c.bd),
          ),
          child: LineChart(
            LineChartData(
              minX: 0, maxX: (widget.yearlyData.length - 1).toDouble(),
              minY: 0, maxY: maxVal * 1.1,
              gridData: FlGridData(
                show: true, drawVerticalLine: false,
                horizontalInterval: maxVal / 4,
                getDrawingHorizontalLine: (v) => FlLine(color: c.bd.withValues(alpha: 0.2), strokeWidth: 0.5, dashArray: [4, 4]),
              ),
              titlesData: FlTitlesData(
                topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                bottomTitles: AxisTitles(sideTitles: SideTitles(
                  showTitles: true, interval: 1, reservedSize: 28,
                  getTitlesWidget: (v, _) {
                    final i = v.toInt();
                    if (i < 0 || i >= widget.yearlyData.length) return const SizedBox.shrink();
                    return Padding(padding: const EdgeInsets.only(top: 8),
                      child: Text('${widget.yearlyData[i]['year'] ?? ''}', style: AppTextStyles.captionXs(c.t4)));
                  },
                )),
                leftTitles: AxisTitles(sideTitles: SideTitles(
                  showTitles: true, reservedSize: 60, interval: maxVal / 4,
                  getTitlesWidget: (v, _) => Text(_formatShort(v), style: AppTextStyles.captionXs(c.t4)),
                )),
              ),
              borderData: FlBorderData(show: false),
              lineTouchData: LineTouchData(
                touchTooltipData: LineTouchTooltipData(
                  getTooltipColor: (_) => c.bg1.withValues(alpha: 0.95),
                  tooltipBorder: BorderSide(color: c.bd),
                  tooltipPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  getTooltipItems: (spots) => spots.map((s) {
                    final isInvested = s.barIndex == 0;
                    return LineTooltipItem(
                      '${isInvested ? 'Invested' : 'Value'}: ₹${_formatShort(s.y)}',
                      TextStyle(color: isInvested ? c.t3 : c.up, fontSize: 11, fontWeight: FontWeight.w600),
                    );
                  }).toList(),
                ),
                getTouchedSpotIndicator: (_, spots) => spots.map((_) => TouchedSpotIndicatorData(
                  FlLine(color: c.blue.withValues(alpha: 0.3), strokeWidth: 1, dashArray: [3, 3]),
                  FlDotData(show: true, getDotPainter: (_, __, ___, ____) =>
                    FlDotCirclePainter(radius: 5, color: c.bg1, strokeWidth: 2, strokeColor: c.blue)),
                )).toList(),
              ),
              lineBarsData: [
                // Invested line
                LineChartBarData(
                  spots: investedSpots,
                  color: c.t3.withValues(alpha: 0.5),
                  barWidth: 1.5, isStrokeCapRound: true,
                  dotData: FlDotData(show: false),
                  dashArray: [6, 3],
                  belowBarData: BarAreaData(show: true, color: c.t3.withValues(alpha: 0.03)),
                ),
                // Value line — gradient with glow
                LineChartBarData(
                  spots: valueSpots,
                  gradient: LinearGradient(colors: [c.up, const Color(0xFF00E676)]),
                  barWidth: 2.5, isStrokeCapRound: true,
                  dotData: FlDotData(
                    show: true,
                    getDotPainter: (spot, _, __, i) {
                      // Show dot only at last point
                      if (i == valueSpots.length - 1 && progress > 0.9) {
                        return FlDotCirclePainter(radius: 4, color: c.up, strokeWidth: 2, strokeColor: c.bg2);
                      }
                      return FlDotCirclePainter(radius: 0, color: Colors.transparent);
                    },
                  ),
                  belowBarData: BarAreaData(
                    show: true,
                    gradient: LinearGradient(
                      begin: Alignment.topCenter, end: Alignment.bottomCenter,
                      colors: [c.up.withValues(alpha: 0.15), c.up.withValues(alpha: 0.02), c.up.withValues(alpha: 0.0)],
                      stops: const [0.0, 0.6, 1.0],
                    ),
                  ),
                  shadow: Shadow(color: c.up.withValues(alpha: 0.3), blurRadius: 8, offset: const Offset(0, 4)),
                ),
              ],
            ),
            duration: const Duration(milliseconds: 0), // We handle animation ourselves
          ),
        );
      },
    );
  }

  String _formatShort(double v) {
    if (v >= 10000000) return '${(v / 10000000).toStringAsFixed(1)}Cr';
    if (v >= 100000) return '${(v / 100000).toStringAsFixed(1)}L';
    if (v >= 1000) return '${(v / 1000).toStringAsFixed(0)}K';
    return v.toStringAsFixed(0);
  }
}

/// Sector allocation pie chart with animated entry and hover effects
class SectorPieChart extends StatefulWidget {
  final Map<String, double> sectors;
  final double size;

  const SectorPieChart({super.key, required this.sectors, this.size = 200});

  @override
  State<SectorPieChart> createState() => _SectorPieChartState();
}

class _SectorPieChartState extends State<SectorPieChart>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;
  int _touchedIndex = -1;

  static const _sectorColors = [
    Color(0xFF448AFF), Color(0xFF7C4DFF), Color(0xFFFFD740),
    Color(0xFF00E676), Color(0xFFFF9100), Color(0xFFFF4081),
    Color(0xFF78909C), Color(0xFF06B6D4), Color(0xFFD97706),
    Color(0xFFEC4899),
  ];

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 800));
    _anim = CurvedAnimation(parent: _ctrl, curve: Curves.easeOutBack);
    _ctrl.forward();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.sectors.isEmpty) return const SizedBox.shrink();
    final c = context.colors;
    final total = widget.sectors.values.fold(0.0, (a, b) => a + b);
    if (total <= 0) return const SizedBox.shrink();

    final entries = widget.sectors.entries.toList()..sort((a, b) => b.value.compareTo(a.value));

    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
        SizedBox(
          width: widget.size, height: widget.size,
          child: PieChart(PieChartData(
            pieTouchData: PieTouchData(
              touchCallback: (event, response) {
                setState(() {
                  if (!event.isInterestedForInteractions || response == null || response.touchedSection == null) {
                    _touchedIndex = -1;
                  } else {
                    _touchedIndex = response.touchedSection!.touchedSectionIndex;
                  }
                });
              },
            ),
            sectionsSpace: 2,
            centerSpaceRadius: widget.size * 0.28,
            startDegreeOffset: -90, // Start from top
            sections: List.generate(entries.length, (i) {
              final pct = entries[i].value / total * 100;
              final isTouched = i == _touchedIndex;
              final radius = (widget.size * 0.22) * _anim.value + (isTouched ? 8 : 0);
              return PieChartSectionData(
                value: entries[i].value,
                color: _sectorColors[i % _sectorColors.length],
                radius: radius,
                title: pct >= 8 ? '${pct.toStringAsFixed(0)}%' : '',
                titleStyle: TextStyle(
                  fontSize: isTouched ? 12 : 10,
                  fontWeight: FontWeight.w700,
                  color: Colors.white,
                  shadows: [Shadow(color: Colors.black.withValues(alpha: 0.4), blurRadius: 4)],
                ),
                badgePositionPercentageOffset: isTouched ? 1.1 : 0.98,
              );
            }),
          )),
        ),
        const SizedBox(width: 24),
        Expanded(child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: List.generate(entries.length.clamp(0, 8), (i) {
            final pct = entries[i].value / total * 100;
            final isTouched = i == _touchedIndex;
            return AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              padding: EdgeInsets.symmetric(vertical: 3, horizontal: isTouched ? 4 : 0),
              decoration: BoxDecoration(
                color: isTouched ? _sectorColors[i % _sectorColors.length].withValues(alpha: 0.08) : Colors.transparent,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Row(children: [
                AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  width: isTouched ? 12 : 10,
                  height: isTouched ? 12 : 10,
                  decoration: BoxDecoration(
                    color: _sectorColors[i % _sectorColors.length],
                    borderRadius: BorderRadius.circular(isTouched ? 3 : 2),
                    boxShadow: isTouched ? [BoxShadow(
                      color: _sectorColors[i % _sectorColors.length].withValues(alpha: 0.4),
                      blurRadius: 6,
                    )] : null,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(child: Text(entries[i].key,
                  style: AppTextStyles.captionXs(isTouched ? c.t1 : c.t2).copyWith(
                    fontWeight: isTouched ? FontWeight.w600 : FontWeight.normal),
                  overflow: TextOverflow.ellipsis)),
                Text('${pct.toStringAsFixed(1)}%',
                  style: AppTextStyles.mono(isTouched ? c.t1 : c.t3).copyWith(
                    fontSize: 11, fontWeight: isTouched ? FontWeight.w700 : FontWeight.normal)),
              ]),
            );
          }),
        )),
      ]),
    );
  }
}

/// Per-stock performance bar chart with spring animation and gradient glow
class PerformanceBarChart extends StatefulWidget {
  final List<Map<String, dynamic>> holdings;
  final double height;

  const PerformanceBarChart({super.key, required this.holdings, this.height = 240});

  @override
  State<PerformanceBarChart> createState() => _PerformanceBarChartState();
}

class _PerformanceBarChartState extends State<PerformanceBarChart>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1000));
    _anim = CurvedAnimation(parent: _ctrl, curve: Curves.easeOutBack);
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

    final sorted = List<Map<String, dynamic>>.from(widget.holdings)
      ..sort((a, b) => ((b['net_chg'] ?? 0) as num).compareTo((a['net_chg'] ?? 0) as num));
    final display = sorted.take(12).toList();

    final maxChg = display.map((h) => ((h['net_chg'] ?? 0) as num).abs().toDouble()).fold(1.0, (a, b) => a > b ? a : b);

    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => Container(
        height: widget.height,
        padding: const EdgeInsets.only(left: 8, right: 16, top: 16, bottom: 8),
        decoration: BoxDecoration(
          color: c.bg2, borderRadius: BorderRadius.circular(12),
          border: Border.all(color: c.bd),
        ),
        child: BarChart(BarChartData(
          alignment: BarChartAlignment.spaceAround,
          maxY: maxChg * 1.2, minY: -maxChg * 1.2,
          gridData: FlGridData(
            show: true, drawVerticalLine: false,
            horizontalInterval: maxChg / 2,
            getDrawingHorizontalLine: (v) {
              if (v.abs() < 0.001) return FlLine(color: c.t4.withValues(alpha: 0.4), strokeWidth: 1); // zero line
              return FlLine(color: c.bd.withValues(alpha: 0.2), strokeWidth: 0.5, dashArray: [4, 4]);
            },
          ),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            leftTitles: AxisTitles(sideTitles: SideTitles(
              showTitles: true, reservedSize: 44, interval: maxChg / 2,
              getTitlesWidget: (v, _) => Text('${v.toStringAsFixed(1)}%', style: AppTextStyles.captionXs(c.t4)),
            )),
            bottomTitles: AxisTitles(sideTitles: SideTitles(
              showTitles: true, reservedSize: 32,
              getTitlesWidget: (v, _) {
                final i = v.toInt();
                if (i < 0 || i >= display.length) return const SizedBox.shrink();
                final sym = (display[i]['symbol'] ?? '').toString()
                    .replaceAll(RegExp(r'\.(NS|BO)$', caseSensitive: false), '');
                return Padding(padding: const EdgeInsets.only(top: 8),
                  child: RotatedBox(quarterTurns: -1,
                    child: Text(sym, style: AppTextStyles.captionXs(c.t3).copyWith(fontSize: 9))));
              },
            )),
          ),
          borderData: FlBorderData(show: false),
          barTouchData: BarTouchData(
            touchTooltipData: BarTouchTooltipData(
              getTooltipColor: (_) => c.bg1.withValues(alpha: 0.95),
              tooltipBorder: BorderSide(color: c.bd),
              getTooltipItem: (_, gi, rod, ri) {
                final sym = gi < display.length
                    ? (display[gi]['symbol'] ?? '').toString().replaceAll(RegExp(r'\.(NS|BO)$', caseSensitive: false), '')
                    : '';
                return BarTooltipItem(
                  '$sym\n${rod.toY >= 0 ? "+" : ""}${rod.toY.toStringAsFixed(2)}%',
                  TextStyle(color: c.t2, fontSize: 10, fontWeight: FontWeight.w500),
                  children: [TextSpan(
                    text: '',
                    style: TextStyle(color: rod.toY >= 0 ? c.up : c.dn, fontSize: 12, fontWeight: FontWeight.w700),
                  )],
                );
              },
            ),
          ),
          barGroups: List.generate(display.length, (i) {
            final chg = ((display[i]['net_chg'] ?? 0) as num).toDouble() * _anim.value;
            return BarChartGroupData(x: i, barRods: [
              BarChartRodData(
                toY: chg, width: 16,
                borderRadius: BorderRadius.only(
                  topLeft: Radius.circular(chg >= 0 ? 4 : 0),
                  topRight: Radius.circular(chg >= 0 ? 4 : 0),
                  bottomLeft: Radius.circular(chg < 0 ? 4 : 0),
                  bottomRight: Radius.circular(chg < 0 ? 4 : 0),
                ),
                gradient: LinearGradient(
                  begin: Alignment.bottomCenter, end: Alignment.topCenter,
                  colors: chg >= 0
                    ? [c.up.withValues(alpha: 0.5), c.up]
                    : [c.dn, c.dn.withValues(alpha: 0.5)],
                ),
                backDrawRodData: BackgroundBarChartRodData(
                  show: true, toY: 0,
                  color: c.bd.withValues(alpha: 0.1),
                ),
              ),
            ]);
          }),
        )),
      ),
    );
  }
}
