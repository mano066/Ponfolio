import 'package:flutter/material.dart';

/// A tiny inline sparkline chart for table rows.
/// Auto-colors gradient by trend direction (green=up, red=down).
///
/// Usage:
/// ```dart
/// SparklineChart(data: [100, 102, 98, 105, 110], width: 80, height: 24)
/// ```
class SparklineChart extends StatefulWidget {
  final List<double> data;
  final double width;
  final double height;
  final Color? upColor;
  final Color? dnColor;
  final double strokeWidth;
  final bool animate;

  const SparklineChart({
    super.key,
    required this.data,
    this.width = 80,
    this.height = 24,
    this.upColor,
    this.dnColor,
    this.strokeWidth = 1.5,
    this.animate = true,
  });

  @override
  State<SparklineChart> createState() => _SparklineChartState();
}

class _SparklineChartState extends State<SparklineChart>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _drawAnim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: widget.animate ? const Duration(milliseconds: 800) : Duration.zero,
    );
    _drawAnim = CurvedAnimation(parent: _ctrl, curve: Curves.easeOutCubic);
    _ctrl.forward();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.data.length < 2) return SizedBox(width: widget.width, height: widget.height);

    final isUp = widget.data.last >= widget.data.first;
    final up = widget.upColor ?? const Color(0xFF00E676);
    final dn = widget.dnColor ?? const Color(0xFFFF5252);
    final lineColor = isUp ? up : dn;

    return SizedBox(
      width: widget.width,
      height: widget.height,
      child: AnimatedBuilder(
        animation: _drawAnim,
        builder: (_, __) => CustomPaint(
          painter: _SparklinePainter(
            data: widget.data,
            color: lineColor,
            strokeWidth: widget.strokeWidth,
            progress: _drawAnim.value,
          ),
        ),
      ),
    );
  }
}

class _SparklinePainter extends CustomPainter {
  final List<double> data;
  final Color color;
  final double strokeWidth;
  final double progress;

  _SparklinePainter({
    required this.data,
    required this.color,
    required this.strokeWidth,
    required this.progress,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (data.length < 2) return;

    final minVal = data.reduce((a, b) => a < b ? a : b);
    final maxVal = data.reduce((a, b) => a > b ? a : b);
    final range = maxVal - minVal;
    if (range == 0) return;

    final points = <Offset>[];
    for (int i = 0; i < data.length; i++) {
      final x = (i / (data.length - 1)) * size.width;
      final y = size.height - ((data[i] - minVal) / range) * (size.height * 0.85) - size.height * 0.075;
      points.add(Offset(x, y));
    }

    // Only draw up to progress point
    final drawCount = (points.length * progress).ceil().clamp(2, points.length);

    // Gradient fill below line
    final fillPath = Path();
    fillPath.moveTo(points[0].dx, size.height);
    for (int i = 0; i < drawCount; i++) {
      fillPath.lineTo(points[i].dx, points[i].dy);
    }
    fillPath.lineTo(points[drawCount - 1].dx, size.height);
    fillPath.close();

    final fillPaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [color.withValues(alpha: 0.2), color.withValues(alpha: 0.0)],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height));
    canvas.drawPath(fillPath, fillPaint);

    // Line
    final linePath = Path();
    linePath.moveTo(points[0].dx, points[0].dy);
    for (int i = 1; i < drawCount; i++) {
      // Smooth cubic bezier between points
      final prev = points[i - 1];
      final curr = points[i];
      final cpx = (prev.dx + curr.dx) / 2;
      linePath.cubicTo(cpx, prev.dy, cpx, curr.dy, curr.dx, curr.dy);
    }

    final linePaint = Paint()
      ..color = color
      ..strokeWidth = strokeWidth
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    canvas.drawPath(linePath, linePaint);

    // Dot at the end
    if (progress >= 0.95) {
      final lastPoint = points[drawCount - 1];
      canvas.drawCircle(lastPoint, 2.5, Paint()..color = color);
      canvas.drawCircle(lastPoint, 4, Paint()
        ..color = color.withValues(alpha: 0.2)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5);
    }
  }

  @override
  bool shouldRepaint(_SparklinePainter old) =>
      old.progress != progress || old.data != data || old.color != color;
}
