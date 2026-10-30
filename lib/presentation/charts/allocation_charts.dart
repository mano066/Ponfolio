import 'dart:math' as math;
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/core/theme/app_colors.dart';

/// Color palette for allocation charts — curated, harmonious, and premium.
const _allocationColors = [
  Color(0xFF448AFF), // Blue
  Color(0xFF7C4DFF), // Purple
  Color(0xFFFFD740), // Gold
  Color(0xFF00E676), // Green
  Color(0xFFFF9100), // Orange
  Color(0xFFFF4081), // Pink
  Color(0xFF06B6D4), // Cyan
  Color(0xFFD97706), // Amber
  Color(0xFF78909C), // Slate
  Color(0xFFEC4899), // Magenta
  Color(0xFF14B8A6), // Teal
  Color(0xFFF97316), // Tangerine
];

const _sectorColors = <String, Color>{
  'Banking': Color(0xFF448AFF),
  'IT': Color(0xFF7C4DFF),
  'Financial Services': Color(0xFF06B6D4),
  'FMCG': Color(0xFF00E676),
  'Energy': Color(0xFFFF9100),
  'Pharma': Color(0xFFEC4899),
  'Auto': Color(0xFFFFD740),
  'Infrastructure': Color(0xFF78909C),
  'Telecom': Color(0xFF14B8A6),
  'Metals': Color(0xFFD97706),
  'Power': Color(0xFF42A5F5),
  'Consumer Durables': Color(0xFFF97316),
  'Technology': Color(0xFF9575CD),
  'Other': Color(0xFF546E7A),
};

// ══════════════════════════════════════════
//  ALLOCATION DONUT CHART
// ══════════════════════════════════════════

/// Animated donut chart with center label and hover tooltips.
/// Used for portfolio composition (Equity/MF/Gold/Cash) and market-cap views.
class AllocationDonutChart extends StatefulWidget {
  final Map<String, double> data;
  final double size;
  final String? centerLabel;
  final String? centerValue;
  final List<Color>? colors;

  const AllocationDonutChart({
    super.key,
    required this.data,
    this.size = 220,
    this.centerLabel,
    this.centerValue,
    this.colors,
  });

  @override
  State<AllocationDonutChart> createState() => _AllocationDonutChartState();
}

class _AllocationDonutChartState extends State<AllocationDonutChart>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;
  int _touchedIndex = -1;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 900));
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
    final filteredData = Map<String, double>.fromEntries(
      widget.data.entries.where((e) => e.value > 0),
    );
    if (filteredData.isEmpty) return const SizedBox.shrink();

    final c = context.colors;
    final total = filteredData.values.fold(0.0, (a, b) => a + b);
    if (total <= 0) return const SizedBox.shrink();

    final entries = filteredData.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));

    final colors = widget.colors ?? _allocationColors;

    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) {
        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Donut chart on left
            SizedBox(
              width: widget.size,
              height: widget.size,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  PieChart(
                    PieChartData(
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
                      sections: List.generate(entries.length, (i) {
                        final isTouched = i == _touchedIndex;
                        final entry = entries[i];
                        final pct = entry.value / total * 100;
                        return PieChartSectionData(
                          value: entry.value * _anim.value,
                          color: colors[i % colors.length],
                          radius: isTouched ? widget.size * 0.22 + 8 : widget.size * 0.22,
                          title: isTouched ? '${pct.toStringAsFixed(1)}%' : '',
                          titleStyle: AppTextStyles.monoBold(Colors.white).copyWith(fontSize: 11),
                          titlePositionPercentageOffset: 0.55,
                        );
                      }),
                    ),
                  ),
                  // Center label
                  if (widget.centerLabel != null)
                    Column(mainAxisSize: MainAxisSize.min, children: [
                      Text(widget.centerLabel!, style: AppTextStyles.captionXs(c.t4)),
                      if (widget.centerValue != null)
                        Text(widget.centerValue!, style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 14)),
                    ]),
                ],
              ),
            ),
            const SizedBox(width: 16),
            // Value breakdown on right
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  const SizedBox(height: 8),
                  ...entries.asMap().entries.map((e) {
                    final pct = e.value.value / total * 100;
                    final color = colors[e.key % colors.length];
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: Row(children: [
                        Container(width: 10, height: 10,
                            decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3))),
                        const SizedBox(width: 8),
                        Expanded(child: Text(e.value.key, style: AppTextStyles.bodySmall(c.t1))),
                        Text(formatCompact(e.value.value),
                            style: AppTextStyles.mono(c.t2).copyWith(fontSize: 11)),
                        const SizedBox(width: 8),
                        SizedBox(width: 40, child: Text('${pct.toStringAsFixed(0)}%',
                            style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 11),
                            textAlign: TextAlign.right)),
                      ]),
                    );
                  }),
                  const SizedBox(height: 8),
                  Divider(color: c.bd, height: 1),
                  const SizedBox(height: 8),
                  Row(children: [
                    const SizedBox(width: 18),
                    Expanded(child: Text('Total', style: AppTextStyles.bodySmall(c.t3).copyWith(fontWeight: FontWeight.w700))),
                    Text(formatCompact(total),
                        style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 11)),
                    const SizedBox(width: 8),
                    SizedBox(width: 40, child: Text('100%',
                        style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 11),
                        textAlign: TextAlign.right)),
                  ]),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}

// ══════════════════════════════════════════
//  INTERACTIVE SECTOR TREEMAP with drill-down
// ══════════════════════════════════════════

/// When tapped, shows individual holdings within that sector.
class SectorTreemap extends StatefulWidget {
  final Map<String, double> sectors;
  final double height;
  /// Optional: map sector -> list of {stock, pct, value}
  final Map<String, List<Map<String, dynamic>>>? sectorHoldings;
  final ValueChanged<String>? onSectorTap;

  const SectorTreemap({
    super.key,
    required this.sectors,
    this.height = 260,
    this.sectorHoldings,
    this.onSectorTap,
  });

  @override
  State<SectorTreemap> createState() => _SectorTreemapState();
}

class _SectorTreemapState extends State<SectorTreemap>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;
  String? _selectedSector;
  String? _hoveredSector;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 700));
    _anim = CurvedAnimation(parent: _ctrl, curve: Curves.easeOutCubic);
    _ctrl.forward();
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final sorted = widget.sectors.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    if (sorted.isEmpty) return const SizedBox.shrink();

    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) {
        return Column(children: [
          // Breadcrumb when drilled down
          if (_selectedSector != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(children: [
                InkWell(
                  onTap: () => setState(() => _selectedSector = null),
                  child: Row(children: [
                    Icon(Icons.arrow_back_ios, size: 12, color: c.blue),
                    Text('All Sectors', style: AppTextStyles.bodySmall(c.blue)),
                  ]),
                ),
                Text('  ›  ', style: AppTextStyles.body(c.t3)),
                Text(_selectedSector!, style: AppTextStyles.bodyBold(c.t1)),
              ]),
            ),

          // Main treemap or drill-down view
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 400),
            transitionBuilder: (child, animation) => FadeTransition(
              opacity: animation,
              child: SlideTransition(
                position: Tween(begin: const Offset(0.05, 0), end: Offset.zero).animate(animation),
                child: child,
              ),
            ),
            child: _selectedSector != null
                ? _buildDrillDown(context, _selectedSector!)
                : _buildTreemap(context, sorted),
          ),
        ]);
      },
    );
  }

  Widget _buildTreemap(BuildContext context, List<MapEntry<String, double>> sorted) {
    final c = context.colors;
    final total = sorted.fold(0.0, (a, b) => a + b.value);
    if (total <= 0) return const SizedBox.shrink();

    return LayoutBuilder(builder: (ctx, constraints) {
      final w = constraints.maxWidth;
      final h = widget.height;
      final rects = _squarify(sorted, w, h, total);

      return SizedBox(
        width: w,
        height: h,
        child: ClipRect(child: Stack(
          clipBehavior: Clip.hardEdge,
          children: rects.asMap().entries.map((entry) {
            final i = entry.key;
            final r = entry.value;
            final sec = sorted[i].key;
            final pct = sorted[i].value;
            final color = _sectorColors[sec] ?? _allocationColors[i % _allocationColors.length];
            final isHovered = _hoveredSector == sec;

            // Gate the labels on the tile's CURRENT size, not its final size:
            // mid-animation the tile is a fraction of `r`, and full-size text
            // inside a 10px-tall box overflows the tile's Column. Margin and
            // padding come off the top before anything is allowed to draw.
            const tileInset = 15.0; // margin 1.5*2 + padding 6*2
            final tileW = r.width * _anim.value - tileInset;
            final tileH = r.height * _anim.value - tileInset;

            return Positioned(
              left: r.left * _anim.value,
              top: r.top * _anim.value,
              width: r.width * _anim.value,
              height: r.height * _anim.value,
              child: MouseRegion(
                onEnter: (_) => setState(() => _hoveredSector = sec),
                onExit: (_) => setState(() => _hoveredSector = null),
                child: GestureDetector(
                  onTap: () {
                    setState(() => _selectedSector = sec);
                    widget.onSectorTap?.call(sec);
                  },
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    margin: const EdgeInsets.all(1.5),
                    decoration: BoxDecoration(
                      color: isHovered ? color.withValues(alpha: 0.9) : color.withValues(alpha: 0.75),
                      borderRadius: BorderRadius.circular(6),
                      border: isHovered ? Border.all(color: Colors.white.withValues(alpha: 0.5), width: 1.5) : null,
                      boxShadow: isHovered ? [BoxShadow(color: color.withValues(alpha: 0.4), blurRadius: 12)] : null,
                    ),
                    child: Padding(
                      padding: const EdgeInsets.all(6),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisAlignment: MainAxisAlignment.center,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (tileW > 60 && tileH > 30)
                            Flexible(child: Text(sec,
                                style: AppTextStyles.bodySmall(Colors.white).copyWith(fontSize: r.width > 100 ? 11 : 9, fontWeight: FontWeight.w600),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis)),
                          if (tileW > 40 && tileH > 20)
                            Flexible(
                              child: Text('${pct.toStringAsFixed(1)}%',
                                  style: AppTextStyles.mono(Colors.white.withValues(alpha: 0.85)).copyWith(fontSize: r.width > 80 ? 12 : 9, fontWeight: FontWeight.bold),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis),
                            ),
                          if (isHovered && tileW > 80 && tileH > 45)
                            Flexible(
                              child: Padding(
                                padding: const EdgeInsets.only(top: 2),
                                child: Text('Click to explore →',
                                    style: AppTextStyles.bodySmall(Colors.white.withValues(alpha: 0.7)).copyWith(fontSize: 8),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            );
          }).toList(),
        )),
      );
    });
  }

  /// Drill-down: show holdings inside a selected sector
  Widget _buildDrillDown(BuildContext context, String sector) {
    final c = context.colors;
    final holdings = widget.sectorHoldings?[sector] ?? [];
    final color = _sectorColors[sector] ?? const Color(0xFF448AFF);

    if (holdings.isEmpty) {
      return SizedBox(
        key: ValueKey('drill-$sector'),
        height: widget.height,
        child: Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(Icons.info_outline, color: c.t3, size: 32),
            const SizedBox(height: 8),
            Text('No detailed holdings data available for $sector',
                style: AppTextStyles.body(c.t3)),
            const SizedBox(height: 4),
            Text('This shows look-through data from your mutual fund holdings',
                style: AppTextStyles.bodySmall(c.t3)),
          ]),
        ),
      );
    }

    // Sort by value descending
    final sorted = List<Map<String, dynamic>>.from(holdings)
      ..sort((a, b) => ((b['value'] ?? 0) as num).compareTo((a['value'] ?? 0) as num));
    final totalVal = sorted.fold<double>(0.0, (a, b) => a + ((b['value'] ?? 0) as num).toDouble());

    return SizedBox(
      key: ValueKey('drill-$sector'),
      height: widget.height,
      child: LayoutBuilder(builder: (ctx, constraints) {
        final w = constraints.maxWidth;
        final h = constraints.maxHeight;
        final sectorEntries = sorted.map((h) =>
            MapEntry(h['stock'] as String? ?? '', ((h['value'] ?? 0) as num).toDouble())).toList();
        final rects = _squarify(sectorEntries, w, h, totalVal);

        return ClipRect(child: Stack(
          clipBehavior: Clip.hardEdge,
          children: rects.asMap().entries.map((entry) {
            final i = entry.key;
            final r = entry.value;
            final stock = sorted[i]['stock'] ?? '';
            final pct = totalVal > 0 ? (sorted[i]['value'] ?? 0) / totalVal * 100 : 0;
            final shade = Color.lerp(color, Colors.white, i * 0.08) ?? color;

            return Positioned(
              left: r.left, top: r.top,
              width: r.width, height: r.height,
              child: AnimatedContainer(
                duration: Duration(milliseconds: 300 + i * 60),
                margin: const EdgeInsets.all(1.5),
                decoration: BoxDecoration(
                  color: shade.withValues(alpha: 0.7),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: shade.withValues(alpha: 0.3)),
                ),
                child: ClipRect(
                  child: Padding(
                    padding: const EdgeInsets.all(4),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.center,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (r.width > 50 && r.height > 30)
                          Text(stock.replaceAll('.NS', '').replaceAll('.BO', ''),
                              style: AppTextStyles.bodySmall(Colors.white).copyWith(
                                fontSize: r.width > 80 ? 11 : 9,
                                fontWeight: FontWeight.w700,
                              ),
                              overflow: TextOverflow.ellipsis),
                        if (r.width > 40 && r.height > 22)
                          Text('${pct.toStringAsFixed(1)}%',
                              style: AppTextStyles.mono(Colors.white.withValues(alpha: 0.85)).copyWith(
                                fontSize: r.width > 70 ? 11 : 8,
                              )),
                        if (r.width > 80 && r.height > 48)
                          Text(formatCompact(sorted[i]['value'] ?? 0),
                              style: AppTextStyles.bodySmall(Colors.white.withValues(alpha: 0.65)).copyWith(fontSize: 9)),
                      ],
                    ),
                  ),
                ),
              ),
            );
          }).toList(),
        ));
      }),
    );
  }
}


// ══════════════════════════════════════════
//  OVERLAP HEATMAP GRID — Redesigned
// ══════════════════════════════════════════

/// Professional overlap matrix showing stocks shared across funds & direct.
class OverlapHeatmapGrid extends StatelessWidget {
  final List<Map<String, dynamic>> overlapHoldings;
  final List<String> sourceNames;

  const OverlapHeatmapGrid({
    super.key,
    required this.overlapHoldings,
    required this.sourceNames,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    if (overlapHoldings.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(32),
        decoration: BoxDecoration(
          gradient: LinearGradient(colors: [
            const Color(0xFF00E676).withValues(alpha: 0.05),
            c.bg2,
          ]),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFF00E676).withValues(alpha: 0.2)),
        ),
        child: Column(children: [
          Icon(Icons.check_circle, color: const Color(0xFF00E676), size: 36),
          const SizedBox(height: 8),
          Text('Zero Overlap Detected!', style: AppTextStyles.heading3(const Color(0xFF00E676))),
          Text('Your portfolio is well-diversified across sources', style: AppTextStyles.bodySmall(c.t3)),
        ]),
      );
    }

    // Build a clean list for the matrix
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: overlapHoldings.asMap().entries.map((entry) {
        final i = entry.key;
        final h = entry.value;
        final stock = (h['stock'] ?? '') as String;
        final sources = (h['sources'] as List<dynamic>?) ?? [];
        final exposurePct = (h['exposure_pct'] ?? 0).toDouble();
        final totalValue = (h['total_value'] ?? 0).toDouble();
        final sourceCount = (h['source_count'] ?? 0) as int;

        // Find max value for bar scaling
        final maxVal = sources.fold<double>(0, (prev, s) {
          final v = ((s as Map)['value'] ?? 0).toDouble();
          return v > prev ? v : prev;
        });

        return TweenAnimationBuilder<double>(
          key: ValueKey(stock),
          tween: Tween(begin: 0, end: 1),
          duration: Duration(milliseconds: 400 + i * 80),
          curve: Curves.easeOutCubic,
          builder: (_, val, child) => Opacity(
            opacity: val,
            child: Transform.translate(offset: Offset(20 * (1 - val), 0), child: child),
          ),
          child: Container(
            margin: const EdgeInsets.only(bottom: 2),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: i.isEven ? c.bg2 : c.bg1,
              border: Border(bottom: BorderSide(color: c.rowBorder)),
            ),
            child: Row(children: [
              // Stock name with count badge
              SizedBox(
                width: 110,
                child: Row(children: [
                  Container(
                    width: 6, height: 6,
                    decoration: BoxDecoration(
                      color: sourceCount >= 3 ? const Color(0xFFFF4081) : const Color(0xFFFFD740),
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(child: Text(stock.replaceAll('.NS', ''),
                      style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12))),
                ]),
              ),

              // Source bars
              Expanded(
                child: Row(
                  children: sourceNames.map((srcName) {
                    final match = sources.cast<Map?>().firstWhere(
                      (s) => s != null && s['source'] == srcName,
                      orElse: () => null,
                    );
                    final value = match != null ? ((match as Map)['value'] ?? 0).toDouble() : 0.0;
                    final barFraction = maxVal > 0 ? value / maxVal : 0.0;

                    return Expanded(child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 3),
                      child: value > 0
                          ? Tooltip(
                              message: '$srcName: ${formatINR(value)}',
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  ClipRRect(
                                    borderRadius: BorderRadius.circular(3),
                                    child: LinearProgressIndicator(
                                      value: barFraction,
                                      minHeight: 18,
                                      backgroundColor: c.rowBorder,
                                      valueColor: AlwaysStoppedAnimation(
                                        Color.lerp(const Color(0xFF448AFF), const Color(0xFFFF4081), barFraction) ?? const Color(0xFF448AFF),
                                      ),
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(formatCompact(value),
                                      style: AppTextStyles.mono(c.t2).copyWith(fontSize: 9),
                                      textAlign: TextAlign.center),
                                ],
                              ),
                            )
                          : Center(child: Text('—', style: AppTextStyles.body(c.t3.withValues(alpha: 0.3)))),
                    ));
                  }).toList(),
                ),
              ),

              // Total %
              SizedBox(
                width: 60,
                child: Text('${exposurePct.toStringAsFixed(1)}%',
                    style: AppTextStyles.monoBold(
                      exposurePct > 5 ? const Color(0xFFFF4081) : c.blue,
                    ).copyWith(fontSize: 12),
                    textAlign: TextAlign.right),
              ),
            ]),
          ),
        );
      }).toList(),
    );
  }
}


// ══════════════════════════════════════════
//  CONCENTRATION RISK BAR CHART
// ══════════════════════════════════════════

class ConcentrationBarChart extends StatelessWidget {
  final double top5Pct;
  final double top10Pct;
  final List<Map<String, dynamic>> topHoldings;

  const ConcentrationBarChart({
    super.key,
    required this.top5Pct,
    required this.top10Pct,
    required this.topHoldings,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      // Summary bars
      _concentrationBar(context, 'Top 5 Holdings', top5Pct, const Color(0xFF7C4DFF),
          top5Pct > 40 ? 'High Risk' : top5Pct > 25 ? 'Moderate' : 'Healthy'),
      const SizedBox(height: 10),
      _concentrationBar(context, 'Top 10 Holdings', top10Pct, const Color(0xFF448AFF),
          top10Pct > 60 ? 'High Risk' : top10Pct > 40 ? 'Moderate' : 'Healthy'),
      const SizedBox(height: 20),

      // Individual holdings
      ...topHoldings.take(10).toList().asMap().entries.map((entry) {
        final idx = entry.key;
        final h = entry.value;
        final stock = h['stock'] ?? '';
        final pct = (h['pct'] ?? 0).toDouble();
        final color = _allocationColors[idx % _allocationColors.length];

        return TweenAnimationBuilder<double>(
          tween: Tween(begin: 0, end: pct / 100),
          duration: Duration(milliseconds: 600 + idx * 100),
          curve: Curves.easeOutCubic,
          builder: (_, val, __) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(children: [
                SizedBox(width: 16, child: Text('${idx + 1}',
                    style: AppTextStyles.mono(c.t3).copyWith(fontSize: 10))),
                const SizedBox(width: 8),
                Expanded(
                  flex: 2,
                  child: Text(stock.toString().replaceAll('.NS', '').replaceAll('.BO', ''),
                      style: AppTextStyles.bodySmall(c.t1).copyWith(fontWeight: FontWeight.w600)),
                ),
                Expanded(
                  flex: 3,
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: Stack(
                      children: [
                        Container(height: 14, decoration: BoxDecoration(
                          color: c.rowBorder,
                          borderRadius: BorderRadius.circular(4),
                        )),
                        FractionallySizedBox(
                          widthFactor: val.clamp(0, 1),
                          child: Container(
                            height: 14,
                            decoration: BoxDecoration(
                              gradient: LinearGradient(colors: [color, color.withValues(alpha: 0.6)]),
                              borderRadius: BorderRadius.circular(4),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                SizedBox(width: 45, child: Text('${pct.toStringAsFixed(1)}%',
                    style: AppTextStyles.mono(c.t2).copyWith(fontSize: 11),
                    textAlign: TextAlign.right)),
              ]),
            );
          },
        );
      }),
    ]);
  }

  Widget _concentrationBar(BuildContext context, String label, double pct, Color color, String status) {
    final c = context.colors;
    final statusColor = status == 'High Risk'
        ? const Color(0xFFFF4081)
        : status == 'Moderate'
            ? const Color(0xFFFFD740)
            : const Color(0xFF00E676);

    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: pct / 100),
      duration: const Duration(milliseconds: 800),
      curve: Curves.easeOutCubic,
      builder: (_, val, __) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(child: Text(label, style: AppTextStyles.bodySmall(c.t2))),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: statusColor.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(status, style: AppTextStyles.badge(statusColor).copyWith(fontSize: 9)),
            ),
            const SizedBox(width: 8),
            Text('${pct.toStringAsFixed(1)}%', style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 13)),
          ]),
          const SizedBox(height: 4),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: Stack(children: [
              Container(height: 10, decoration: BoxDecoration(color: c.rowBorder, borderRadius: BorderRadius.circular(6))),
              FractionallySizedBox(
                widthFactor: val.clamp(0, 1),
                child: Container(
                  height: 10,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(colors: [color, color.withValues(alpha: 0.5)]),
                    borderRadius: BorderRadius.circular(6),
                  ),
                ),
              ),
            ]),
          ),
        ],
      ),
    );
  }
}


// ══════════════════════════════════════════
//  ANIMATED FUND CARD (for MF section)
// ══════════════════════════════════════════

class AnimatedFundCard extends StatefulWidget {
  final Map<String, dynamic> fund;
  final int index;

  const AnimatedFundCard({super.key, required this.fund, required this.index});

  @override
  State<AnimatedFundCard> createState() => _AnimatedFundCardState();
}

class _AnimatedFundCardState extends State<AnimatedFundCard> with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _scaleAnim;
  bool _isHovered = false;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: Duration(milliseconds: 500 + widget.index * 100));
    _scaleAnim = CurvedAnimation(parent: _ctrl, curve: Curves.easeOutBack);
    _ctrl.forward();
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final fund = widget.fund;
    final schemeName = fund['scheme_name'] ?? '';
    final category = fund['category'] ?? '';
    final currentValue = (fund['current_value'] ?? 0).toDouble();
    final invested = (fund['invested'] ?? 0).toDouble();
    final pnl = (fund['pnl'] ?? 0).toDouble();
    final returnPct = (fund['return_pct'] ?? 0).toDouble();
    final xirr = (fund['xirr'] ?? 0).toDouble();
    final lcPct = (fund['lc_pct'] ?? 0).toDouble();
    final mcPct = (fund['mc_pct'] ?? 0).toDouble();
    final scPct = (fund['sc_pct'] ?? 0).toDouble();
    final topSector = fund['top_sector'] ?? 'N/A';
    final style = fund['style'] ?? 'Blend';
    final overlapScore = (fund['overlap_score'] ?? 0).toDouble();

    final isProfit = pnl >= 0;

    return ScaleTransition(
      scale: _scaleAnim,
      child: MouseRegion(
        onEnter: (_) => setState(() => _isHovered = true),
        onExit: (_) => setState(() => _isHovered = false),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: c.bg2,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: _isHovered ? c.blue.withValues(alpha: 0.4) : c.bd),
            boxShadow: _isHovered ? [
              BoxShadow(color: c.blue.withValues(alpha: 0.1), blurRadius: 16, spreadRadius: -4),
            ] : null,
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            // Header
            Row(children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [c.blue.withValues(alpha: 0.15), c.blue.withValues(alpha: 0.05)],
                  ),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(Icons.account_balance, size: 18, color: c.blue),
              ),
              const SizedBox(width: 10),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(schemeName, style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12),
                    maxLines: 1, overflow: TextOverflow.ellipsis),
                Text(category, style: AppTextStyles.bodySmall(c.t3).copyWith(fontSize: 10)),
              ])),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: (isProfit ? c.up : c.dn).withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text('${isProfit ? '+' : ''}${returnPct.toStringAsFixed(1)}%',
                    style: AppTextStyles.monoBold(isProfit ? c.up : c.dn).copyWith(fontSize: 11)),
              ),
            ]),
            const SizedBox(height: 12),

            // Value row
            Row(children: [
              _miniStat(c, 'Value', formatCompact(currentValue)),
              _miniStat(c, 'Invested', formatCompact(invested)),
              _miniStat(c, 'P&L', '${isProfit ? '+' : ''}${formatCompact(pnl)}', isProfit ? c.up : c.dn),
              _miniStat(c, 'XIRR', '${xirr.toStringAsFixed(1)}%',
                  xirr >= 0 ? c.up : c.dn),
            ]),
            const SizedBox(height: 12),

            // Market cap distribution bar
            Text('MARKET CAP SPLIT', style: AppTextStyles.label(c.t3).copyWith(fontSize: 9)),
            const SizedBox(height: 4),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: SizedBox(
                height: 10,
                child: Row(children: [
                  if (lcPct > 0) Flexible(flex: lcPct.round().clamp(1, 100),
                      child: Container(color: const Color(0xFF448AFF))),
                  if (mcPct > 0) Flexible(flex: mcPct.round().clamp(1, 100),
                      child: Container(color: const Color(0xFF7C4DFF))),
                  if (scPct > 0) Flexible(flex: scPct.round().clamp(1, 100),
                      child: Container(color: const Color(0xFFFF9100))),
                  if (lcPct == 0 && mcPct == 0 && scPct == 0)
                    Expanded(child: Container(color: c.rowBorder)),
                ]),
              ),
            ),
            const SizedBox(height: 4),
            Row(children: [
              _capLabel(c, 'LC', lcPct, const Color(0xFF448AFF)),
              _capLabel(c, 'MC', mcPct, const Color(0xFF7C4DFF)),
              _capLabel(c, 'SC', scPct, const Color(0xFFFF9100)),
              const Spacer(),
              Text('Top: $topSector', style: AppTextStyles.bodySmall(c.t3).copyWith(fontSize: 9)),
            ]),
            const SizedBox(height: 8),

            // Style + Overlap
            Row(children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: const Color(0xFF7C4DFF).withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(style, style: AppTextStyles.badge(const Color(0xFF7C4DFF)).copyWith(fontSize: 9)),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: (overlapScore > 50 ? const Color(0xFFFF4081) : c.up).withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text('Overlap: ${overlapScore.toStringAsFixed(0)}%',
                    style: AppTextStyles.badge(overlapScore > 50 ? const Color(0xFFFF4081) : c.up).copyWith(fontSize: 9)),
              ),
            ]),
          ]),
        ),
      ),
    );
  }

  Widget _miniStat(AppColorScheme c, String label, String value, [Color? valueColor]) {
    return Expanded(child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: AppTextStyles.bodySmall(c.t3).copyWith(fontSize: 9)),
        Text(value, style: AppTextStyles.mono(valueColor ?? c.t1).copyWith(fontSize: 11)),
      ],
    ));
  }

  Widget _capLabel(AppColorScheme c, String label, double pct, Color color) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Container(width: 6, height: 6, decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(1))),
        const SizedBox(width: 3),
        Text('$label ${pct.toStringAsFixed(0)}%',
            style: AppTextStyles.mono(c.t2).copyWith(fontSize: 9)),
      ]),
    );
  }
}


// ══════════════════════════════════════════
//  REBALANCING HEATMAP
// ══════════════════════════════════════════

class RebalancingHeatmap extends StatelessWidget {
  final Map<String, double> currentAlloc;
  final Map<String, double> targetAlloc;

  const RebalancingHeatmap({super.key, required this.currentAlloc, required this.targetAlloc});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final allCategories = {...currentAlloc.keys, ...targetAlloc.keys}.toList()
      ..sort((a, b) => (currentAlloc[b] ?? 0).compareTo(currentAlloc[a] ?? 0));

    return Column(
      children: allCategories.map((cat) {
        final current = currentAlloc[cat] ?? 0;
        final target = targetAlloc[cat] ?? 0;
        final diff = current - target;
        final absDiff = diff.abs();
        final isOver = diff > 0;
        final intensity = (absDiff / 20).clamp(0.0, 1.0);
        final cellColor = absDiff < 2
            ? const Color(0xFF00E676).withValues(alpha: 0.1)
            : isOver
                ? Color.lerp(const Color(0xFFFF4081).withValues(alpha: 0.05), const Color(0xFFFF4081).withValues(alpha: 0.3), intensity)!
                : Color.lerp(const Color(0xFF448AFF).withValues(alpha: 0.05), const Color(0xFF448AFF).withValues(alpha: 0.3), intensity)!;

        return Container(
          margin: const EdgeInsets.only(bottom: 2),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(color: cellColor, borderRadius: BorderRadius.circular(6)),
          child: Row(children: [
            Expanded(flex: 3, child: Text(cat, style: AppTextStyles.bodySmall(c.t1).copyWith(fontWeight: FontWeight.w600))),
            SizedBox(width: 55, child: Text('${current.toStringAsFixed(1)}%',
                style: AppTextStyles.mono(c.t2).copyWith(fontSize: 11), textAlign: TextAlign.right)),
            SizedBox(width: 10, child: Text('→', style: AppTextStyles.body(c.t3).copyWith(fontSize: 10), textAlign: TextAlign.center)),
            SizedBox(width: 55, child: Text('${target.toStringAsFixed(1)}%',
                style: AppTextStyles.mono(c.t1).copyWith(fontSize: 11), textAlign: TextAlign.right)),
            SizedBox(width: 55, child: Text(
              '${diff >= 0 ? '+' : ''}${diff.toStringAsFixed(1)}%',
              style: AppTextStyles.monoBold(
                absDiff < 2 ? c.up : isOver ? const Color(0xFFFF4081) : const Color(0xFF448AFF),
              ).copyWith(fontSize: 11),
              textAlign: TextAlign.right,
            )),
          ]),
        );
      }).toList(),
    );
  }
}


// ══════════════════════════════════════════
//  SQUARIFY LAYOUT HELPER
// ══════════════════════════════════════════

class _Rect {
  final double left, top, width, height;
  const _Rect(this.left, this.top, this.width, this.height);
}

List<_Rect> _squarify(List<MapEntry<String, double>> entries, double w, double h, double total) {
  if (entries.isEmpty || total <= 0) return [];
  final rects = <_Rect>[];
  double x = 0, y = 0, remainingW = w, remainingH = h;
  double remainingTotal = total;
  bool horizontal = remainingW >= remainingH;

  int i = 0;
  while (i < entries.length) {
    final row = <int>[];
    double rowSum = 0;
    double bestAspect = double.infinity;

    while (i + row.length < entries.length) {
      final idx = i + row.length;
      final val = entries[idx].value;
      final newSum = rowSum + val;
      final side = horizontal
          ? remainingH
          : remainingW;
      final rowLen = newSum / remainingTotal * (horizontal ? remainingW : remainingH);

      double worstAspect = 0;
      for (final ri in row) {
        final itemLen = entries[ri].value / newSum * side;
        final aspect = math.max(rowLen / itemLen, itemLen / rowLen);
        worstAspect = math.max(worstAspect, aspect);
      }
      {
        final itemLen = val / newSum * side;
        final aspect = math.max(rowLen / itemLen, itemLen / rowLen);
        worstAspect = math.max(worstAspect, aspect);
      }

      if (row.isEmpty || worstAspect <= bestAspect) {
        row.add(idx);
        rowSum = newSum;
        bestAspect = worstAspect;
      } else {
        break;
      }
    }

    final rowLen = rowSum / remainingTotal * (horizontal ? remainingW : remainingH);
    double offset = 0;
    for (final ri in row) {
      final fraction = entries[ri].value / rowSum;
      final itemLen = fraction * (horizontal ? remainingH : remainingW);
      if (horizontal) {
        rects.add(_Rect(x, y + offset, rowLen, itemLen));
      } else {
        rects.add(_Rect(x + offset, y, itemLen, rowLen));
      }
      offset += itemLen;
    }

    if (horizontal) {
      x += rowLen;
      remainingW -= rowLen;
    } else {
      y += rowLen;
      remainingH -= rowLen;
    }
    remainingTotal -= rowSum;
    horizontal = remainingW >= remainingH;
    i += row.length;
  }

  return rects;
}
