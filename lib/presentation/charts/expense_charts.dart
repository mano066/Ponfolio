import 'dart:math' as math;
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';

/// ─── Expense dashboard chart kit ───
/// Reusable fl_chart widgets (grouped bars, trend lines, donut) styled to match
/// the data-dense finance look. All are driven by plain label/value lists so
/// the analytics layer stays UI-agnostic.

String _short(double v) {
  final a = v.abs();
  final s = v < 0 ? '-' : '';
  if (a >= 10000000) return '$s${(a / 10000000).toStringAsFixed(1)}Cr';
  if (a >= 100000) return '$s${(a / 100000).toStringAsFixed(1)}L';
  if (a >= 1000) return '$s${(a / 1000).toStringAsFixed(0)}K';
  return '$s${a.toStringAsFixed(0)}';
}

/// Titled card wrapper so charts share the same surface + heading.
class ChartCard extends StatelessWidget {
  final String title;
  final String? subtitle;
  final Widget child;
  final double height;
  const ChartCard({
    super.key,
    required this.title,
    required this.child,
    this.subtitle,
    this.height = 240,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return DenseCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: AppTextStyles.heading3(c.t1)),
          if (subtitle != null) ...[
            const SizedBox(height: 2),
            Text(subtitle!, style: AppTextStyles.captionXs(c.t3)),
          ],
          const SizedBox(height: 12),
          SizedBox(height: height, child: child),
        ],
      ),
    );
  }
}

/// Two-series grouped bar chart (e.g. Income vs Expense by month).
class GroupedBarChart extends StatelessWidget {
  final List<String> labels;
  final List<double> seriesA;
  final List<double> seriesB;
  final Color colorA;
  final Color colorB;
  final String nameA;
  final String nameB;
  const GroupedBarChart({
    super.key,
    required this.labels,
    required this.seriesA,
    required this.seriesB,
    required this.colorA,
    required this.colorB,
    required this.nameA,
    required this.nameB,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final maxV = [
      ...seriesA,
      ...seriesB,
      1.0,
    ].reduce((a, b) => math.max(a, b));
    return Column(
      children: [
        Row(children: [
          _legend(context, colorA, nameA),
          const SizedBox(width: 14),
          _legend(context, colorB, nameB),
        ]),
        const SizedBox(height: 10),
        Expanded(
          child: BarChart(
            BarChartData(
              alignment: BarChartAlignment.spaceAround,
              maxY: maxV * 1.15,
              barTouchData: BarTouchData(
                touchTooltipData: BarTouchTooltipData(
                  getTooltipColor: (_) => c.bg1.withValues(alpha: 0.95),
                  tooltipBorder: BorderSide(color: c.bd),
                  getTooltipItem: (group, _, rod, rodIndex) => BarTooltipItem(
                    '${rodIndex == 0 ? nameA : nameB}\n${_short(rod.toY)}',
                    TextStyle(
                        color: rodIndex == 0 ? colorA : colorB,
                        fontSize: 11,
                        fontWeight: FontWeight.w600),
                  ),
                ),
              ),
              gridData: FlGridData(
                show: true,
                drawVerticalLine: false,
                horizontalInterval: maxV / 4,
                getDrawingHorizontalLine: (_) =>
                    FlLine(color: c.bd.withValues(alpha: 0.25), strokeWidth: 0.5),
              ),
              titlesData: FlTitlesData(
                topTitles:
                    const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                rightTitles:
                    const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 40,
                        interval: maxV / 4,
                        getTitlesWidget: (v, _) => Text(_short(v),
                            style: AppTextStyles.captionXs(c.t4)))),
                bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 24,
                        getTitlesWidget: (v, _) {
                          final i = v.toInt();
                          if (i < 0 || i >= labels.length) {
                            return const SizedBox.shrink();
                          }
                          return Padding(
                              padding: const EdgeInsets.only(top: 6),
                              child: Text(labels[i],
                                  style: AppTextStyles.captionXs(c.t4)));
                        })),
              ),
              borderData: FlBorderData(show: false),
              barGroups: [
                for (var i = 0; i < labels.length; i++)
                  BarChartGroupData(x: i, barsSpace: 2, barRods: [
                    BarChartRodData(
                        toY: i < seriesA.length ? seriesA[i] : 0,
                        color: colorA,
                        width: 6,
                        borderRadius: BorderRadius.circular(2)),
                    BarChartRodData(
                        toY: i < seriesB.length ? seriesB[i] : 0,
                        color: colorB,
                        width: 6,
                        borderRadius: BorderRadius.circular(2)),
                  ]),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _legend(BuildContext context, Color color, String name) => Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
              width: 9,
              height: 9,
              decoration: BoxDecoration(
                  color: color, borderRadius: BorderRadius.circular(2))),
          const SizedBox(width: 5),
          Text(name, style: AppTextStyles.captionXs(context.colors.t3)),
        ],
      );
}

/// Single-series trend line with a soft gradient fill.
class TrendLineChart extends StatelessWidget {
  final List<String> labels;
  final List<double> values;
  final Color color;
  final bool allowNegative;
  const TrendLineChart({
    super.key,
    required this.labels,
    required this.values,
    required this.color,
    this.allowNegative = false,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    if (values.isEmpty) return const SizedBox.shrink();
    final maxV = values.reduce((a, b) => math.max(a, b));
    final minV = allowNegative ? values.reduce((a, b) => math.min(a, b)) : 0.0;
    final span = (maxV - minV).abs();
    final pad = span == 0 ? 1.0 : span * 0.15;
    return LineChart(
      LineChartData(
        minY: minV - (allowNegative ? pad : 0),
        maxY: maxV + pad,
        gridData: FlGridData(
          show: true,
          drawVerticalLine: false,
          getDrawingHorizontalLine: (_) =>
              FlLine(color: c.bd.withValues(alpha: 0.25), strokeWidth: 0.5),
        ),
        titlesData: FlTitlesData(
          topTitles:
              const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles:
              const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          leftTitles: AxisTitles(
              sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 42,
                  getTitlesWidget: (v, _) => Text(_short(v),
                      style: AppTextStyles.captionXs(c.t4)))),
          bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 24,
                  interval: 1,
                  getTitlesWidget: (v, _) {
                    final i = v.toInt();
                    if (i < 0 || i >= labels.length) {
                      return const SizedBox.shrink();
                    }
                    return Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text(labels[i],
                            style: AppTextStyles.captionXs(c.t4)));
                  })),
        ),
        borderData: FlBorderData(show: false),
        lineTouchData: LineTouchData(
          touchTooltipData: LineTouchTooltipData(
            getTooltipColor: (_) => c.bg1.withValues(alpha: 0.95),
            tooltipBorder: BorderSide(color: c.bd),
            getTooltipItems: (spots) => spots
                .map((s) => LineTooltipItem(_short(s.y),
                    TextStyle(
                        color: color,
                        fontSize: 11,
                        fontWeight: FontWeight.w600)))
                .toList(),
          ),
        ),
        lineBarsData: [
          LineChartBarData(
            spots: [
              for (var i = 0; i < values.length; i++)
                FlSpot(i.toDouble(), values[i]),
            ],
            isCurved: true,
            curveSmoothness: 0.25,
            color: color,
            barWidth: 2,
            isStrokeCapRound: true,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
              show: true,
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  color.withValues(alpha: 0.25),
                  color.withValues(alpha: 0.0),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// A single step in a [WaterfallChart].
class WaterfallStep {
  final String label;
  final double delta; // signed change (ignored for total steps)
  final bool isTotal; // draw from 0 to running value (Opening / Closing)
  final Color color;
  const WaterfallStep(this.label, this.delta, this.color,
      {this.isTotal = false});
}

/// Cash-flow waterfall: Opening → +Income → −Expense → −Transfer → Closing.
/// Each intermediate bar floats between the running balance before and after
/// its delta; the two total steps draw from zero.
class WaterfallChart extends StatelessWidget {
  final List<WaterfallStep> steps;
  const WaterfallChart({super.key, required this.steps});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    // Compute floating [fromY, toY] for each bar and the axis range.
    var running = 0.0;
    final bars = <List<double>>[]; // [from, to]
    var minY = 0.0, maxY = 0.0;
    for (final s in steps) {
      double from, to;
      if (s.isTotal) {
        from = 0;
        to = running;
      } else {
        from = running;
        to = running + s.delta;
        running = to;
      }
      bars.add([from, to]);
      minY = math.min(minY, math.min(from, to));
      maxY = math.max(maxY, math.max(from, to));
    }
    final span = (maxY - minY).abs();
    final pad = span == 0 ? 1.0 : span * 0.12;
    final interval = span == 0 ? 1.0 : span / 4;

    return BarChart(
      BarChartData(
        alignment: BarChartAlignment.spaceAround,
        minY: minY - pad,
        maxY: maxY + pad,
        barTouchData: BarTouchData(
          touchTooltipData: BarTouchTooltipData(
            getTooltipColor: (_) => c.bg1.withValues(alpha: 0.95),
            tooltipBorder: BorderSide(color: c.bd),
            getTooltipItem: (group, _, rod, _) {
              final s = steps[group.x];
              final v = s.isTotal ? rod.toY : s.delta;
              return BarTooltipItem(
                '${s.label}\n${v >= 0 && !s.isTotal ? '+' : ''}${_short(v)}',
                TextStyle(
                    color: s.color,
                    fontSize: 11,
                    fontWeight: FontWeight.w600),
              );
            },
          ),
        ),
        gridData: FlGridData(
          show: true,
          drawVerticalLine: false,
          horizontalInterval: interval,
          getDrawingHorizontalLine: (_) =>
              FlLine(color: c.bd.withValues(alpha: 0.25), strokeWidth: 0.5),
        ),
        titlesData: FlTitlesData(
          topTitles:
              const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles:
              const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          leftTitles: AxisTitles(
              sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 42,
                  interval: interval,
                  getTitlesWidget: (v, _) => Text(_short(v),
                      style: AppTextStyles.captionXs(c.t4)))),
          bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 24,
                  getTitlesWidget: (v, _) {
                    final i = v.toInt();
                    if (i < 0 || i >= steps.length) {
                      return const SizedBox.shrink();
                    }
                    return Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text(steps[i].label,
                            style: AppTextStyles.captionXs(c.t4),
                            textAlign: TextAlign.center));
                  })),
        ),
        borderData: FlBorderData(show: false),
        barGroups: [
          for (var i = 0; i < steps.length; i++)
            BarChartGroupData(x: i, barRods: [
              BarChartRodData(
                fromY: bars[i][0],
                toY: bars[i][1],
                color: steps[i].color,
                width: 22,
                borderRadius: BorderRadius.circular(2),
              ),
            ]),
        ],
      ),
    );
  }
}

/// Donut/pie with an inline legend — used for category & asset splits.
class DonutChart extends StatelessWidget {
  final Map<String, double> data;
  final List<Color> palette;
  const DonutChart({super.key, required this.data, required this.palette});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    if (data.isEmpty) {
      return Center(
          child: Text('No data', style: AppTextStyles.captionXs(c.t3)));
    }
    final entries = data.entries.toList();
    final total = entries.fold<double>(0, (a, e) => a + e.value);
    return Row(
      children: [
        Expanded(
          flex: 3,
          child: PieChart(
            PieChartData(
              sectionsSpace: 2,
              centerSpaceRadius: 42,
              sections: [
                for (var i = 0; i < entries.length; i++)
                  PieChartSectionData(
                    value: entries[i].value,
                    color: palette[i % palette.length],
                    title: total > 0
                        ? '${(entries[i].value / total * 100).round()}%'
                        : '',
                    radius: 46,
                    titleStyle: AppTextStyles.captionXs(Colors.white)
                        .copyWith(fontWeight: FontWeight.w700),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          flex: 2,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (var i = 0; i < entries.length; i++)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(children: [
                    Container(
                        width: 9,
                        height: 9,
                        decoration: BoxDecoration(
                            color: palette[i % palette.length],
                            borderRadius: BorderRadius.circular(2))),
                    const SizedBox(width: 6),
                    Expanded(
                        child: Text(entries[i].key,
                            style: AppTextStyles.captionXs(c.t2),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis)),
                    Text(_short(entries[i].value),
                        style: AppTextStyles.mono(c.t3).copyWith(fontSize: 11)),
                  ]),
                ),
            ],
          ),
        ),
      ],
    );
  }
}
