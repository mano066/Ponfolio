import 'dart:math' as math;
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_colors.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/presentation/widgets/animated_counter.dart';

// ═══════════════════════════════════════════════════════════════════
//  CONVICTION RING — Animated radial gauge for CIO conviction score
// ═══════════════════════════════════════════════════════════════════

class ConvictionRing extends StatefulWidget {
  final double? score; // 0-100, null = unavailable (CIO call failed)
  final double size;
  const ConvictionRing({super.key, required this.score, this.size = 100});
  @override
  State<ConvictionRing> createState() => _ConvictionRingState();
}

class _ConvictionRingState extends State<ConvictionRing>
    with TickerProviderStateMixin {
  late AnimationController _fillCtrl;
  late Animation<double> _fillAnim;
  late AnimationController _pulseCtrl;
  late Animation<double> _pulseAnim;

  @override
  void initState() {
    super.initState();
    _fillCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1600));
    _fillAnim = CurvedAnimation(parent: _fillCtrl, curve: Curves.easeOutCubic);
    _fillCtrl.forward();
    _pulseCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 2200));
    _pulseAnim = Tween<double>(begin: 0.0, end: 1.0).animate(CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut));
    _pulseCtrl.repeat(reverse: true);
  }

  @override
  void dispose() { _fillCtrl.dispose(); _pulseCtrl.dispose(); super.dispose(); }

  Color _color(double s) {
    if (s >= 80) return const Color(0xFF00E676);
    if (s >= 60) return const Color(0xFF4D8EFF);
    if (s >= 40) return const Color(0xFFEAC32B);
    return const Color(0xFFFF5252);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final score = widget.score;
    // When conviction is unavailable (CIO call failed), show a muted "—" / "N/A"
    // ring instead of fabricating a score.
    if (score == null) {
      return AnimatedBuilder(
        animation: _pulseAnim,
        builder: (_, __) => SizedBox(
          width: widget.size, height: widget.size,
          child: Stack(alignment: Alignment.center, children: [
            CustomPaint(
              size: Size(widget.size, widget.size),
              painter: _ConvictionRingPainter(
                fraction: 0, color: c.t4, trackColor: c.bg3,
                glowIntensity: 0,
              ),
            ),
            Column(mainAxisSize: MainAxisSize.min, children: [
              Text('—', style: TextStyle(fontSize: widget.size * 0.22, fontWeight: FontWeight.w800, color: c.t4, height: 1)),
              Text('N/A', style: AppTextStyles.captionXs(c.t4).copyWith(letterSpacing: 1, fontSize: 8)),
            ]),
          ]),
        ),
      );
    }
    final clr = _color(score);
    return AnimatedBuilder(
      animation: Listenable.merge([_fillAnim, _pulseAnim]),
      builder: (_, __) => SizedBox(
        width: widget.size, height: widget.size,
        child: Stack(alignment: Alignment.center, children: [
          CustomPaint(
            size: Size(widget.size, widget.size),
            painter: _ConvictionRingPainter(
              fraction: (score / 100).clamp(0.0, 1.0) * _fillAnim.value,
              color: clr, trackColor: c.bg3,
              glowIntensity: 0.12 + _pulseAnim.value * 0.12,
            ),
          ),
          Column(mainAxisSize: MainAxisSize.min, children: [
            AnimatedCounter(
              value: score,
              decimals: 0, suffix: '%',
              style: TextStyle(fontSize: widget.size * 0.22, fontWeight: FontWeight.w800, color: clr, height: 1),
              duration: const Duration(milliseconds: 1400),
            ),
            Text('CONVICTION', style: AppTextStyles.captionXs(c.t4).copyWith(letterSpacing: 1, fontSize: 8)),
          ]),
        ]),
      ),
    );
  }
}

class _ConvictionRingPainter extends CustomPainter {
  final double fraction, glowIntensity;
  final Color color, trackColor;
  _ConvictionRingPainter({required this.fraction, required this.color, required this.trackColor, this.glowIntensity = 0.2});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 10;
    if (radius <= 0) return;
    canvas.drawCircle(center, radius, Paint()..color = trackColor..style = PaintingStyle.stroke..strokeWidth = 7..strokeCap = StrokeCap.round);
    if (fraction <= 0) return;
    canvas.drawArc(Rect.fromCircle(center: center, radius: radius), -math.pi / 2, fraction * 2 * math.pi, false,
      Paint()..color = color.withValues(alpha: glowIntensity)..style = PaintingStyle.stroke..strokeWidth = 13..strokeCap = StrokeCap.round..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8));
    canvas.drawArc(Rect.fromCircle(center: center, radius: radius), -math.pi / 2, fraction * 2 * math.pi, false,
      Paint()..color = color..style = PaintingStyle.stroke..strokeWidth = 7..strokeCap = StrokeCap.round);
  }

  @override
  bool shouldRepaint(_ConvictionRingPainter old) => old.fraction != fraction || old.glowIntensity != glowIntensity;
}

// ═══════════════════════════════════════════════════════════════════
//  AGENT CONSENSUS BAR — Shows bullish/neutral/bearish agent counts
// ═══════════════════════════════════════════════════════════════════

class AgentConsensusBar extends StatefulWidget {
  final int bullish;
  final int neutral;
  final int bearish;
  final int total;
  const AgentConsensusBar({super.key, required this.bullish, required this.neutral, required this.bearish, this.total = 9});
  @override
  State<AgentConsensusBar> createState() => _AgentConsensusBarState();
}

class _AgentConsensusBarState extends State<AgentConsensusBar> with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1000));
    _anim = CurvedAnimation(parent: _ctrl, curve: Curves.easeOutCubic);
    _ctrl.forward();
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final total = widget.total > 0 ? widget.total : 1;
    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('AGENT CONSENSUS', style: AppTextStyles.labelXs(c.t4)),
        const SizedBox(height: 8),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: SizedBox(height: 10, child: Row(children: [
            if (widget.bullish > 0) Expanded(flex: widget.bullish, child: Container(
              decoration: BoxDecoration(
                color: c.up, boxShadow: [BoxShadow(color: c.up.withValues(alpha: 0.4), blurRadius: 6)],
              ),
            )),
            if (widget.neutral > 0) Expanded(flex: widget.neutral, child: Container(color: c.gold)),
            if (widget.bearish > 0) Expanded(flex: widget.bearish, child: Container(color: c.dn)),
          ])),
        ),
        const SizedBox(height: 8),
        Row(children: [
          _dot(c.up), const SizedBox(width: 4),
          Text('${widget.bullish} Bullish', style: AppTextStyles.captionXs(c.up)),
          const SizedBox(width: 14),
          _dot(c.gold), const SizedBox(width: 4),
          Text('${widget.neutral} Neutral', style: AppTextStyles.captionXs(c.gold)),
          const SizedBox(width: 14),
          _dot(c.dn), const SizedBox(width: 4),
          Text('${widget.bearish} Bearish', style: AppTextStyles.captionXs(c.dn)),
        ]),
      ]),
    );
  }

  Widget _dot(Color clr) => Container(width: 8, height: 8, decoration: BoxDecoration(color: clr, shape: BoxShape.circle));
}

// ═══════════════════════════════════════════════════════════════════
//  PRICE TARGET RULER — Redesigned for clarity
// ═══════════════════════════════════════════════════════════════════

class PriceTargetRuler extends StatefulWidget {
  final double? currentPrice;
  final double? targetPrice;
  final double? stopLoss;
  const PriceTargetRuler({super.key, this.currentPrice, this.targetPrice, this.stopLoss});
  @override
  State<PriceTargetRuler> createState() => _PriceTargetRulerState();
}

class _PriceTargetRulerState extends State<PriceTargetRuler> with SingleTickerProviderStateMixin {
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
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final cur = widget.currentPrice;
    if (cur == null) return const SizedBox.shrink();

    // ── Auto-fix: if LLM swapped target and stop loss, correct them ──
    var tgt = widget.targetPrice;
    var sl = widget.stopLoss;
    if (sl != null && tgt != null && sl > tgt) {
      final temp = sl; sl = tgt; tgt = temp;
    }
    if (sl != null && tgt != null && sl > cur && tgt < cur) {
      final temp = sl; sl = tgt; tgt = temp;
    }

    // Percentages (computed after potential swap)
    final slPct = sl != null && cur > 0 ? ((sl - cur) / cur * 100) : null;
    final tgtPct = tgt != null && cur > 0 ? ((tgt - cur) / cur * 100) : null;

    // Risk:Reward ratio
    final downside = sl != null ? (cur - sl).abs() : 0.0;
    final upside = tgt != null ? (tgt - cur).abs() : 0.0;
    final rrRatio = downside > 0 ? (upside / downside) : null;

    // Track positions
    final allPrices = [cur, if (tgt != null) tgt, if (sl != null) sl];
    final minP = allPrices.reduce(math.min) * 0.93;
    final maxP = allPrices.reduce(math.max) * 1.07;
    final range = maxP - minP;
    if (range <= 0) return const SizedBox.shrink();
    double posOf(double p) => ((p - minP) / range).clamp(0.0, 1.0);

    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // ── Title + Risk:Reward badge ──
        Row(children: [
          Text('PRICE LEVELS', style: AppTextStyles.labelXs(c.t4)),
          const Spacer(),
          if (rrRatio != null) Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: rrRatio >= 2 ? c.up.withValues(alpha: 0.1) : rrRatio >= 1 ? c.gold.withValues(alpha: 0.1) : c.dn.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: rrRatio >= 2 ? c.up.withValues(alpha: 0.3) : rrRatio >= 1 ? c.gold.withValues(alpha: 0.3) : c.dn.withValues(alpha: 0.3)),
            ),
            child: Text(
              'Risk:Reward  1:${rrRatio.toStringAsFixed(1)}',
              style: AppTextStyles.captionXs(rrRatio >= 2 ? c.up : rrRatio >= 1 ? c.gold : c.dn).copyWith(fontWeight: FontWeight.w700, fontSize: 10),
            ),
          ),
        ]),
        const SizedBox(height: 14),

        // ── Three labeled price boxes (always ordered: SL < Current < Target) ──
        Row(children: [
          if (sl != null) Expanded(child: _priceBox(c, '🛑 STOP LOSS', '₹${sl.round()}',
            '${slPct?.toStringAsFixed(1)}%', c.dn, 'Sell here to\nlimit losses')),
          if (sl != null) const SizedBox(width: 8),
          Expanded(child: _priceBox(c, '📍 CURRENT PRICE', '₹${cur.round()}',
            'You are here', c.blue, null)),
          if (tgt != null) const SizedBox(width: 8),
          if (tgt != null) Expanded(child: _priceBox(c, '🎯 TARGET', '₹${tgt.round()}',
            '+${tgtPct?.toStringAsFixed(1)}%', c.up, 'Sell here to\ntake profit')),
        ]),
        const SizedBox(height: 14),

        // ── Visual track with zones ──
        SizedBox(height: 36, child: LayoutBuilder(builder: (_, constraints) {
          final w = constraints.maxWidth;
          final slPos = sl != null ? posOf(sl) : 0.0;
          final curPos = posOf(cur);
          final tgtPos = tgt != null ? posOf(tgt) : 1.0;

          return Stack(children: [
            // Full track background
            Positioned(top: 12, left: 0, right: 0, child: Container(
              height: 8, decoration: BoxDecoration(color: c.bg3, borderRadius: BorderRadius.circular(4)))),
            // Red zone: SL to current
            if (sl != null) Positioned(top: 12, left: w * slPos * _anim.value, child: Container(
              width: math.max(0, w * (curPos - slPos) * _anim.value), height: 8,
              decoration: BoxDecoration(
                gradient: LinearGradient(colors: [c.dn.withValues(alpha: 0.5), c.dn.withValues(alpha: 0.15)]),
                borderRadius: BorderRadius.circular(4)))),
            // Green zone: current to target
            if (tgt != null) Positioned(top: 12, left: w * curPos * _anim.value, child: Container(
              width: math.max(0, w * (tgtPos - curPos) * _anim.value), height: 8,
              decoration: BoxDecoration(
                gradient: LinearGradient(colors: [c.up.withValues(alpha: 0.15), c.up.withValues(alpha: 0.5)]),
                borderRadius: BorderRadius.circular(4)))),
            // Zone labels
            if (sl != null) Positioned(top: 24, left: w * slPos, child: SizedBox(
              width: math.max(0, w * (curPos - slPos)),
              child: Center(child: Text('LOSS ZONE', style: TextStyle(fontSize: 7, color: c.dn.withValues(alpha: 0.6), fontWeight: FontWeight.w700, letterSpacing: 0.5))))),
            if (tgt != null) Positioned(top: 24, left: w * curPos, child: SizedBox(
              width: math.max(0, w * (tgtPos - curPos)),
              child: Center(child: Text('PROFIT ZONE', style: TextStyle(fontSize: 7, color: c.up.withValues(alpha: 0.6), fontWeight: FontWeight.w700, letterSpacing: 0.5))))),
            // Stop Loss marker
            if (sl != null) Positioned(left: w * slPos * _anim.value - 5, top: 4, child: Container(
              width: 10, height: 10, decoration: BoxDecoration(
                color: c.dn, shape: BoxShape.circle, border: Border.all(color: Colors.white, width: 1.5),
                boxShadow: [BoxShadow(color: c.dn.withValues(alpha: 0.4), blurRadius: 6)]))),
            // Current price marker (larger, prominent)
            Positioned(left: w * curPos * _anim.value - 7, top: 2, child: Container(
              width: 14, height: 14, decoration: BoxDecoration(
                color: c.blue, shape: BoxShape.circle, border: Border.all(color: Colors.white, width: 2),
                boxShadow: [BoxShadow(color: c.blue.withValues(alpha: 0.5), blurRadius: 8)]))),
            // Target marker
            if (tgt != null) Positioned(left: w * tgtPos * _anim.value - 5, top: 4, child: Container(
              width: 10, height: 10, decoration: BoxDecoration(
                color: c.up, shape: BoxShape.circle, border: Border.all(color: Colors.white, width: 1.5),
                boxShadow: [BoxShadow(color: c.up.withValues(alpha: 0.4), blurRadius: 6)]))),
          ]);
        })),

        // ── Summary line ──
        if (sl != null && tgt != null) Padding(
          padding: const EdgeInsets.only(top: 10),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(color: c.bg1, borderRadius: BorderRadius.circular(6), border: Border.all(color: c.bd)),
            child: Row(children: [
              Icon(LucideIcons.info, size: 11, color: c.t4),
              const SizedBox(width: 6),
              Expanded(child: Text.rich(TextSpan(style: TextStyle(fontSize: 10, color: c.t3, height: 1.4), children: [
                const TextSpan(text: 'If price drops '),
                TextSpan(text: '${slPct?.abs().toStringAsFixed(1)}%', style: TextStyle(color: c.dn, fontWeight: FontWeight.w700)),
                const TextSpan(text: ' to stop loss → exit. If it rises '),
                TextSpan(text: '${tgtPct?.toStringAsFixed(1)}%', style: TextStyle(color: c.up, fontWeight: FontWeight.w700)),
                const TextSpan(text: ' to target → take profit.'),
              ]))),
            ]),
          ),
        ),
      ]),
    );
  }

  Widget _priceBox(AppColorScheme c, String label, String price, String subtitle, Color clr, String? tooltip) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
      decoration: BoxDecoration(
        color: clr.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: clr.withValues(alpha: 0.2)),
      ),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text(label, style: TextStyle(fontSize: 8, fontWeight: FontWeight.w700, color: clr, letterSpacing: 0.3)),
        const SizedBox(height: 4),
        Text(price, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: clr)),
        const SizedBox(height: 2),
        Text(subtitle, style: TextStyle(fontSize: 9, color: clr.withValues(alpha: 0.7), fontWeight: FontWeight.w600)),
        if (tooltip != null) ...[
          const SizedBox(height: 4),
          Text(tooltip, style: TextStyle(fontSize: 7.5, color: c.t4, height: 1.3), textAlign: TextAlign.center),
        ],
      ]),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════
//  VALUATION GAUGE — Horizontal bar: Undervalued ↔ Overvalued
// ═══════════════════════════════════════════════════════════════════

class ValuationGauge extends StatefulWidget {
  final String? assessment; // "Undervalued", "Fair", "Overvalued"
  const ValuationGauge({super.key, this.assessment});
  @override
  State<ValuationGauge> createState() => _ValuationGaugeState();
}

class _ValuationGaugeState extends State<ValuationGauge> with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;
  @override
  void initState() { super.initState(); _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1000)); _anim = CurvedAnimation(parent: _ctrl, curve: Curves.easeOutCubic); _ctrl.forward(); }
  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  double _position(String? a) {
    if (a == null) return 0.5;
    final u = a.toUpperCase();
    if (u.contains('UNDER')) return 0.2;
    if (u.contains('FAIR') || u.contains('NEUTRAL')) return 0.5;
    if (u.contains('OVER')) return 0.8;
    return 0.5;
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final pos = _position(widget.assessment);
    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Text('Undervalued', style: AppTextStyles.captionXs(c.up)),
          Text('Fair Value', style: AppTextStyles.captionXs(c.t4)),
          Text('Overvalued', style: AppTextStyles.captionXs(c.dn)),
        ]),
        const SizedBox(height: 6),
        SizedBox(height: 18, child: LayoutBuilder(builder: (_, constraints) {
          final w = constraints.maxWidth;
          return Stack(children: [
            // Gradient track
            Container(height: 8, margin: const EdgeInsets.only(top: 5), decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(4),
              gradient: LinearGradient(colors: [c.up.withValues(alpha: 0.4), c.gold.withValues(alpha: 0.3), c.dn.withValues(alpha: 0.4)]),
            )),
            // Indicator dot
            Positioned(left: (w * pos * _anim.value) - 6, top: 0, child: Container(
              width: 14, height: 14, decoration: BoxDecoration(
                color: pos < 0.4 ? c.up : pos > 0.6 ? c.dn : c.gold,
                shape: BoxShape.circle, border: Border.all(color: Colors.white, width: 2),
                boxShadow: [BoxShadow(color: (pos < 0.4 ? c.up : pos > 0.6 ? c.dn : c.gold).withValues(alpha: 0.5), blurRadius: 6)],
              ),
            )),
          ]);
        })),
      ]),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════
//  SENTIMENT ARC — Semi-circle gauge for sentiment score
// ═══════════════════════════════════════════════════════════════════

class SentimentArc extends StatefulWidget {
  final String? sentiment; // "Positive", "Neutral", "Negative"
  final double? score; // 0-10
  final double size;
  const SentimentArc({super.key, this.sentiment, this.score, this.size = 80});
  @override
  State<SentimentArc> createState() => _SentimentArcState();
}

class _SentimentArcState extends State<SentimentArc> with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;
  @override
  void initState() { super.initState(); _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200)); _anim = CurvedAnimation(parent: _ctrl, curve: Curves.easeOutBack); _ctrl.forward(); }
  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  double _fraction() {
    if (widget.score != null) return (widget.score! / 10).clamp(0.0, 1.0);
    final s = (widget.sentiment ?? '').toUpperCase();
    if (s.contains('POS') || s.contains('BULL')) return 0.8;
    if (s.contains('NEG') || s.contains('BEAR')) return 0.2;
    return 0.5;
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final frac = _fraction();
    final clr = frac >= 0.6 ? c.up : frac <= 0.4 ? c.dn : c.gold;
    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => SizedBox(
        width: widget.size, height: widget.size * 0.6,
        child: CustomPaint(
          painter: _SentimentArcPainter(
            fraction: frac * _anim.value, color: clr, trackColor: c.bg3,
          ),
          child: Center(child: Padding(
            padding: const EdgeInsets.only(top: 10),
            child: Text(widget.sentiment ?? '—', style: AppTextStyles.captionXs(clr).copyWith(fontWeight: FontWeight.w700)),
          )),
        ),
      ),
    );
  }
}

class _SentimentArcPainter extends CustomPainter {
  final double fraction;
  final Color color, trackColor;
  _SentimentArcPainter({required this.fraction, required this.color, required this.trackColor});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height);
    final radius = math.min(size.width / 2, size.height) - 6;
    if (radius <= 0) return;
    canvas.drawArc(Rect.fromCircle(center: center, radius: radius), math.pi, math.pi, false,
      Paint()..color = trackColor..style = PaintingStyle.stroke..strokeWidth = 6..strokeCap = StrokeCap.round);
    if (fraction <= 0) return;
    canvas.drawArc(Rect.fromCircle(center: center, radius: radius), math.pi, fraction * math.pi, false,
      Paint()..color = color.withValues(alpha: 0.3)..style = PaintingStyle.stroke..strokeWidth = 10..strokeCap = StrokeCap.round..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4));
    canvas.drawArc(Rect.fromCircle(center: center, radius: radius), math.pi, fraction * math.pi, false,
      Paint()..color = color..style = PaintingStyle.stroke..strokeWidth = 6..strokeCap = StrokeCap.round);
    // Needle dot
    final angle = math.pi + fraction * math.pi;
    final tip = Offset(center.dx + radius * math.cos(angle), center.dy + radius * math.sin(angle));
    canvas.drawCircle(tip, 5, Paint()..color = color);
    canvas.drawCircle(tip, 2.5, Paint()..color = Colors.white);
  }

  @override
  bool shouldRepaint(_SentimentArcPainter old) => old.fraction != fraction;
}

// ═══════════════════════════════════════════════════════════════════
//  RISK METER — Gauge from Low → Extreme
// ═══════════════════════════════════════════════════════════════════

class RiskMeter extends StatefulWidget {
  final String? riskLevel; // "Low", "Moderate", "High", "Very High"
  final double? maxDrawdown;
  const RiskMeter({super.key, this.riskLevel, this.maxDrawdown});
  @override
  State<RiskMeter> createState() => _RiskMeterState();
}

class _RiskMeterState extends State<RiskMeter> with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;
  @override
  void initState() { super.initState(); _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200)); _anim = CurvedAnimation(parent: _ctrl, curve: Curves.easeOutBack); _ctrl.forward(); }
  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  double _fraction() {
    final r = (widget.riskLevel ?? '').toUpperCase();
    if (r.contains('LOW')) return 0.2;
    if (r.contains('MODERATE') || r.contains('MEDIUM')) return 0.45;
    if (r.contains('VERY') || r.contains('EXTREME')) return 0.9;
    if (r.contains('HIGH')) return 0.7;
    return 0.5;
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final frac = _fraction();
    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Text('Low', style: AppTextStyles.captionXs(c.up)),
          Text('Moderate', style: AppTextStyles.captionXs(c.gold)),
          Text('High', style: AppTextStyles.captionXs(const Color(0xFFFF9100))),
          Text('Extreme', style: AppTextStyles.captionXs(c.dn)),
        ]),
        const SizedBox(height: 6),
        SizedBox(height: 18, child: LayoutBuilder(builder: (_, constraints) {
          final w = constraints.maxWidth;
          return Stack(children: [
            Container(height: 8, margin: const EdgeInsets.only(top: 5), decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(4),
              gradient: LinearGradient(colors: [c.up, c.gold, const Color(0xFFFF9100), c.dn]),
            )),
            Positioned(left: (w * frac * _anim.value) - 6, top: 0, child: Container(
              width: 14, height: 14, decoration: BoxDecoration(
                color: frac < 0.35 ? c.up : frac < 0.55 ? c.gold : frac < 0.75 ? const Color(0xFFFF9100) : c.dn,
                shape: BoxShape.circle, border: Border.all(color: Colors.white, width: 2),
                boxShadow: [BoxShadow(color: c.dn.withValues(alpha: 0.3), blurRadius: 6)],
              ),
            )),
          ]);
        })),
        if (widget.maxDrawdown != null) ...[
          const SizedBox(height: 8),
          Row(children: [
            Icon(LucideIcons.alertTriangle, size: 12, color: c.dn),
            const SizedBox(width: 4),
            Text('Max Drawdown: ', style: AppTextStyles.captionXs(c.t4)),
            Text('${widget.maxDrawdown!.toStringAsFixed(1)}%', style: AppTextStyles.captionXs(c.dn).copyWith(fontWeight: FontWeight.w700)),
          ]),
        ],
      ]),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════
//  DCF COMPARISON BAR — Current price vs intrinsic value
// ═══════════════════════════════════════════════════════════════════

class DCFComparisonBar extends StatefulWidget {
  final double? currentPrice;
  final double? dcfValue;
  final double? grahamValue;
  const DCFComparisonBar({super.key, this.currentPrice, this.dcfValue, this.grahamValue});
  @override
  State<DCFComparisonBar> createState() => _DCFComparisonBarState();
}

class _DCFComparisonBarState extends State<DCFComparisonBar> with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;
  @override
  void initState() { super.initState(); _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1000)); _anim = CurvedAnimation(parent: _ctrl, curve: Curves.easeOutCubic); _ctrl.forward(); }
  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final cur = widget.currentPrice ?? 0;
    final dcf = widget.dcfValue;
    final graham = widget.grahamValue;
    if (cur <= 0 && dcf == null) return const SizedBox.shrink();
    final maxVal = [cur, dcf ?? 0, graham ?? 0].reduce(math.max) * 1.1;
    if (maxVal <= 0) return const SizedBox.shrink();

    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _bar(c, 'Current Price', cur, maxVal, c.blue),
        if (dcf != null) ...[const SizedBox(height: 8), _bar(c, 'DCF Intrinsic', dcf, maxVal, dcf > cur ? c.up : c.dn)],
        if (graham != null) ...[const SizedBox(height: 8), _bar(c, 'Graham Number', graham, maxVal, graham > cur ? c.up : c.gold)],
        if (dcf != null && cur > 0) ...[
          const SizedBox(height: 10),
          Row(children: [
            Icon(dcf > cur ? LucideIcons.arrowUpRight : LucideIcons.arrowDownRight, size: 14, color: dcf > cur ? c.up : c.dn),
            const SizedBox(width: 4),
            Text('${((dcf - cur) / cur * 100).toStringAsFixed(1)}% ${dcf > cur ? "upside" : "downside"} to DCF value',
              style: AppTextStyles.captionXs(dcf > cur ? c.up : c.dn).copyWith(fontWeight: FontWeight.w700)),
          ]),
        ],
      ]),
    );
  }

  Widget _bar(AppColorScheme c, String label, double value, double maxVal, Color clr) {
    final frac = (value / maxVal).clamp(0.0, 1.0) * _anim.value;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text(label, style: AppTextStyles.captionXs(c.t3)),
        Text('₹${value.round()}', style: AppTextStyles.captionXs(clr).copyWith(fontWeight: FontWeight.w700)),
      ]),
      const SizedBox(height: 4),
      ClipRRect(borderRadius: BorderRadius.circular(3), child: SizedBox(height: 8, child: Stack(children: [
        Container(color: c.bg3),
        FractionallySizedBox(widthFactor: frac, child: Container(
          decoration: BoxDecoration(color: clr, borderRadius: BorderRadius.circular(3),
            boxShadow: [BoxShadow(color: clr.withValues(alpha: 0.4), blurRadius: 4)]),
        )),
      ]))),
    ]);
  }
}

// ═══════════════════════════════════════════════════════════════════
//  AGENT RADAR CHART — Spider chart of all agent scores
// ═══════════════════════════════════════════════════════════════════

class AgentRadarChart extends StatefulWidget {
  final Map<String, double> scores; // agent_name -> score (0-10)
  const AgentRadarChart({super.key, required this.scores});
  @override
  State<AgentRadarChart> createState() => _AgentRadarChartState();
}

class _AgentRadarChartState extends State<AgentRadarChart> with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;

  @override
  void initState() { super.initState(); _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400)); _anim = CurvedAnimation(parent: _ctrl, curve: Curves.easeOutCubic); _ctrl.forward(); }
  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final entries = widget.scores.entries.toList();
    if (entries.isEmpty) return const SizedBox.shrink();

    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => SizedBox(
        height: 260,
        child: RadarChart(RadarChartData(
          radarShape: RadarShape.polygon,
          tickCount: 5,
          ticksTextStyle: TextStyle(fontSize: 0, color: Colors.transparent),
          radarBorderData: BorderSide(color: c.bd.withValues(alpha: 0.3)),
          gridBorderData: BorderSide(color: c.bd.withValues(alpha: 0.2), width: 0.5),
          tickBorderData: BorderSide(color: c.bd.withValues(alpha: 0.1)),
          titlePositionPercentageOffset: 0.2,
          titleTextStyle: AppTextStyles.captionXs(c.t3).copyWith(fontSize: 9),
          getTitle: (i, _) {
            if (i < 0 || i >= entries.length) return RadarChartTitle(text: '');
            return RadarChartTitle(text: entries[i].key);
          },
          dataSets: [
            RadarDataSet(
              fillColor: c.accent.withValues(alpha: 0.15 * _anim.value),
              borderColor: c.accent.withValues(alpha: 0.8 * _anim.value),
              borderWidth: 2,
              entryRadius: 3,
              dataEntries: entries.map((e) => RadarEntry(value: e.value * _anim.value)).toList(),
            ),
          ],
        )),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════
//  ENHANCED AGENT CARD — With verdict badge, confidence, info, mini-chart
// ═══════════════════════════════════════════════════════════════════

class EnhancedAgentCard extends StatefulWidget {
  final String title;
  final IconData icon;
  final Color accentColor;
  final String? verdict;
  final double? score;
  final String? keyInsight;
  final String tooltip;
  final Widget? visualization;
  final List<Widget> metrics;

  const EnhancedAgentCard({
    super.key,
    required this.title,
    required this.icon,
    required this.accentColor,
    this.verdict,
    this.score,
    this.keyInsight,
    this.tooltip = '',
    this.visualization,
    this.metrics = const [],
  });

  @override
  State<EnhancedAgentCard> createState() => _EnhancedAgentCardState();
}

class _EnhancedAgentCardState extends State<EnhancedAgentCard> {
  bool _hovering = false;
  bool _showTooltip = false;

  Color _verdictColor(String? v, AppColorScheme c) {
    if (v == null) return c.t3;
    final u = v.toUpperCase();
    if (['BULLISH', 'BUY', 'STRONG', 'POSITIVE', 'UNDERVALUED', 'LOW', 'UPTREND'].any(u.contains)) return c.up;
    if (['BEARISH', 'SELL', 'WEAK', 'NEGATIVE', 'OVERVALUED', 'DOWNTREND', 'VERY HIGH', 'HIGH'].any(u.contains)) return c.dn;
    return c.gold;
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final vColor = _verdictColor(widget.verdict, c);

    return MouseRegion(
      onEnter: (_) => setState(() => _hovering = true),
      onExit: (_) => setState(() => _hovering = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        decoration: BoxDecoration(
          color: c.bg2, borderRadius: BorderRadius.circular(16),
          border: Border.all(color: _hovering ? widget.accentColor.withValues(alpha: 0.3) : c.bd),
          boxShadow: _hovering ? [BoxShadow(color: widget.accentColor.withValues(alpha: 0.12), blurRadius: 16)] : [],
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          // Header with verdict badge
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.bd))),
            child: Row(children: [
              Container(width: 30, height: 30, decoration: BoxDecoration(
                color: widget.accentColor.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(8),
                border: Border.all(color: widget.accentColor.withValues(alpha: 0.15))),
                child: Icon(widget.icon, size: 15, color: widget.accentColor)),
              const SizedBox(width: 10),
              Expanded(child: Text(widget.title, style: AppTextStyles.sectionTitle(c.t1))),
              if (widget.verdict != null) Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(color: vColor.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: vColor.withValues(alpha: 0.3))),
                child: Text(widget.verdict!, style: AppTextStyles.captionXs(vColor).copyWith(fontWeight: FontWeight.w700, fontSize: 10)),
              ),
              if (widget.tooltip.isNotEmpty) ...[
                const SizedBox(width: 8),
                _InfoBtn(isShowing: _showTooltip, onToggle: () => setState(() => _showTooltip = !_showTooltip)),
              ],
            ]),
          ),
          // Tooltip
          if (_showTooltip && widget.tooltip.isNotEmpty) Container(
            margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(color: widget.accentColor.withValues(alpha: 0.06), borderRadius: BorderRadius.circular(8),
              border: Border.all(color: widget.accentColor.withValues(alpha: 0.15))),
            child: Text(widget.tooltip, style: AppTextStyles.captionXs(c.t2).copyWith(height: 1.5)),
          ),
          // Visualization
          if (widget.visualization != null) Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 4), child: widget.visualization!),
          // Metrics
          if (widget.metrics.isNotEmpty) Padding(
            padding: const EdgeInsets.all(16),
            child: Column(children: widget.metrics),
          ),
          // Key Insight
          if (widget.keyInsight != null) Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(color: c.bg1, borderRadius: BorderRadius.circular(8),
                border: Border(left: BorderSide(color: widget.accentColor, width: 2))),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Icon(LucideIcons.lightbulb, size: 12, color: widget.accentColor),
                const SizedBox(width: 8),
                Expanded(child: Text(widget.keyInsight!, style: AppTextStyles.bodySmall(c.t2))),
              ]),
            ),
          ),
        ]),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════
//  ENHANCED LOADING VIEW — Animated pipeline with pulse effects
// ═══════════════════════════════════════════════════════════════════

class EnhancedLoadingView extends StatefulWidget {
  final String symbol;
  final int currentAgent;
  final Duration elapsed;
  final List<Map<String, String>> agentStages;

  const EnhancedLoadingView({
    super.key,
    required this.symbol,
    required this.currentAgent,
    required this.elapsed,
    required this.agentStages,
  });

  @override
  State<EnhancedLoadingView> createState() => _EnhancedLoadingViewState();
}

class _EnhancedLoadingViewState extends State<EnhancedLoadingView> with SingleTickerProviderStateMixin {
  late AnimationController _pulseCtrl;
  late Animation<double> _pulseAnim;

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200));
    _pulseAnim = Tween<double>(begin: 0.0, end: 1.0).animate(CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut));
    _pulseCtrl.repeat(reverse: true);
  }

  @override
  void dispose() { _pulseCtrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final progress = (widget.currentAgent + 1) / widget.agentStages.length;
    final elapsedStr = '${widget.elapsed.inMinutes}:${(widget.elapsed.inSeconds % 60).toString().padLeft(2, '0')}';
    // Estimate: ~15s per agent average
    final estRemaining = ((widget.agentStages.length - widget.currentAgent - 1) * 15);
    final etaStr = estRemaining > 60 ? '~${(estRemaining / 60).ceil()}m' : '~${estRemaining}s';

    return Container(
      constraints: const BoxConstraints(maxWidth: 650),
      margin: const EdgeInsets.symmetric(vertical: 20),
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: c.bg2, borderRadius: BorderRadius.circular(16),
        border: Border.all(color: c.bd),
        boxShadow: [BoxShadow(color: c.accent.withValues(alpha: 0.06), blurRadius: 24)],
      ),
      child: AnimatedBuilder(
        animation: _pulseAnim,
        builder: (_, __) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          // Title + elapsed + ETA
          Row(children: [
            Container(
              width: 48, height: 48,
              decoration: BoxDecoration(
                gradient: LinearGradient(colors: [
                  Color.lerp(const Color(0xFF6366F1), const Color(0xFF818CF8), _pulseAnim.value)!,
                  const Color(0xFF8B5CF6),
                ]),
                borderRadius: BorderRadius.circular(12),
                boxShadow: [BoxShadow(color: const Color(0xFF6366F1).withValues(alpha: 0.2 + _pulseAnim.value * 0.2), blurRadius: 12 + _pulseAnim.value * 6)],
              ),
              child: const Center(child: Text('🧠', style: TextStyle(fontSize: 22))),
            ),
            const SizedBox(width: 16),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Analyzing ${widget.symbol.replaceAll(RegExp(r"\.(NS|BO)$", caseSensitive: false), "")}',
                style: AppTextStyles.heading3(c.t1)),
              Text('9-Agent Orchestration Pipeline', style: AppTextStyles.bodySmall(c.t3)),
            ])),
            Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Container(padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(color: c.bg3, borderRadius: BorderRadius.circular(8)),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Icon(LucideIcons.clock, size: 14, color: c.t3), const SizedBox(width: 6),
                  Text(elapsedStr, style: AppTextStyles.mono(c.t2).copyWith(fontSize: 14)),
                ])),
              const SizedBox(height: 4),
              Text('ETA: $etaStr', style: AppTextStyles.captionXs(c.t4)),
            ]),
          ]),
          const SizedBox(height: 24),

          // Progress bar
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text('Overall Progress', style: AppTextStyles.label(c.t3)),
            Text('${(progress * 100).toInt()}%', style: AppTextStyles.monoBold(c.blue)),
          ]),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: SizedBox(height: 10, child: Stack(children: [
              Container(decoration: BoxDecoration(color: c.bg3, borderRadius: BorderRadius.circular(6))),
              FractionallySizedBox(widthFactor: progress, child: Container(
                decoration: BoxDecoration(
                  gradient: const LinearGradient(colors: [Color(0xFF6366F1), Color(0xFF818CF8), Color(0xFF06B6D4)]),
                  borderRadius: BorderRadius.circular(6),
                  boxShadow: [BoxShadow(color: const Color(0xFF6366F1).withValues(alpha: 0.4 + _pulseAnim.value * 0.2), blurRadius: 8 + _pulseAnim.value * 4)],
                ),
              )),
            ])),
          ),
          const SizedBox(height: 24),

          // Agent pipeline
          ...List.generate(widget.agentStages.length, (i) {
            final stage = widget.agentStages[i];
            final isDone = i < widget.currentAgent;
            final isActive = i == widget.currentAgent;

            return AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              margin: const EdgeInsets.only(bottom: 4),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: isActive ? c.blueBg.withValues(alpha: 0.3) : Colors.transparent,
                borderRadius: BorderRadius.circular(8),
                border: isActive ? Border.all(color: c.blue.withValues(alpha: 0.2 + _pulseAnim.value * 0.15)) : null,
                boxShadow: isActive ? [BoxShadow(color: c.blue.withValues(alpha: 0.06 + _pulseAnim.value * 0.06), blurRadius: 12)] : [],
              ),
              child: Row(children: [
                // Status icon with pulse
                SizedBox(width: 28, child: Center(child: isDone
                  ? Icon(LucideIcons.checkCircle2, size: 18, color: c.up)
                  : isActive
                    ? Container(
                        width: 20, height: 20,
                        decoration: BoxDecoration(shape: BoxShape.circle,
                          boxShadow: [BoxShadow(color: c.blue.withValues(alpha: 0.2 + _pulseAnim.value * 0.3), blurRadius: 8 + _pulseAnim.value * 4)]),
                        child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: c.blue)))
                    : Icon(LucideIcons.circle, size: 16, color: c.t4.withValues(alpha: 0.4)),
                )),
                const SizedBox(width: 12),
                Text(stage['icon']!, style: TextStyle(fontSize: 16, color: isDone || isActive ? null : c.t4)),
                const SizedBox(width: 10),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(stage['name']!, style: AppTextStyles.bodyBold(
                    isDone ? c.up : isActive ? c.t1 : c.t4).copyWith(fontSize: 13)),
                  if (isActive) Text(stage['desc']!, style: AppTextStyles.captionXs(c.t3)),
                ])),
                if (isDone) Text('Done', style: AppTextStyles.captionXs(c.up)),
                if (isActive) Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: c.blueBg, borderRadius: BorderRadius.circular(4),
                    boxShadow: [BoxShadow(color: c.blue.withValues(alpha: _pulseAnim.value * 0.2), blurRadius: 6)],
                  ),
                  child: Text('Running', style: AppTextStyles.captionXs(c.blue).copyWith(fontWeight: FontWeight.w700)),
                ),
              ]),
            );
          }),
        ]),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════
//  METRIC ROW — Simple key-value pair for agent cards
// ═══════════════════════════════════════════════════════════════════

class MetricRow extends StatelessWidget {
  final String label;
  final dynamic value;
  final Color? valueColor;
  const MetricRow({super.key, required this.label, this.value, this.valueColor});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text(label, style: AppTextStyles.body(c.t3)),
        Text(value?.toString() ?? '--', style: AppTextStyles.bodyBold(valueColor ?? c.t1)),
      ],
    ));
  }
}

// ═══════════════════════════════════════════════════════════════════
//  INFO BUTTON — Small toggleable info icon
// ═══════════════════════════════════════════════════════════════════

class _InfoBtn extends StatefulWidget {
  final bool isShowing;
  final VoidCallback onToggle;
  const _InfoBtn({required this.isShowing, required this.onToggle});
  @override
  State<_InfoBtn> createState() => _InfoBtnState();
}

class _InfoBtnState extends State<_InfoBtn> {
  bool _hovering = false;
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hovering = true),
      onExit: (_) => setState(() => _hovering = false),
      child: GestureDetector(onTap: widget.onToggle, child: AnimatedContainer(
        duration: const Duration(milliseconds: 150), width: 22, height: 22,
        decoration: BoxDecoration(
          color: widget.isShowing ? c.blue.withValues(alpha: 0.15) : _hovering ? c.bg3 : Colors.transparent,
          shape: BoxShape.circle,
          border: Border.all(color: widget.isShowing ? c.blue.withValues(alpha: 0.3) : Colors.transparent)),
        child: Icon(LucideIcons.info, size: 12, color: widget.isShowing ? c.blue : (_hovering ? c.t2 : c.t4)),
      )),
    );
  }
}
