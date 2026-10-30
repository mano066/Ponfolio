import 'package:flutter/material.dart';

/// Smoothly animates a numeric value from its previous value to the new one.
/// Perfect for stat cards, P&L displays, portfolio totals, and percentages.
///
/// Usage:
/// ```dart
/// AnimatedCounter(value: totalPnl, prefix: '₹', style: AppTextStyles.statXl(c.t1))
/// ```
class AnimatedCounter extends StatefulWidget {
  final double value;
  final String prefix;
  final String suffix;
  final int decimals;
  final TextStyle? style;
  final Duration duration;
  final Curve curve;
  final bool showSign;

  const AnimatedCounter({
    super.key,
    required this.value,
    this.prefix = '',
    this.suffix = '',
    this.decimals = 2,
    this.style,
    this.duration = const Duration(milliseconds: 800),
    this.curve = Curves.easeOutCubic,
    this.showSign = false,
  });

  /// Shortcut for INR formatting
  factory AnimatedCounter.inr({
    Key? key,
    required double value,
    TextStyle? style,
    Duration duration = const Duration(milliseconds: 800),
    bool showSign = false,
  }) => AnimatedCounter(
    key: key,
    value: value,
    prefix: '₹',
    decimals: 0,
    style: style,
    duration: duration,
    showSign: showSign,
  );

  /// Shortcut for percentage formatting
  factory AnimatedCounter.pct({
    Key? key,
    required double value,
    TextStyle? style,
    Duration duration = const Duration(milliseconds: 800),
  }) => AnimatedCounter(
    key: key,
    value: value,
    suffix: '%',
    decimals: 2,
    style: style,
    duration: duration,
    showSign: true,
  );

  @override
  State<AnimatedCounter> createState() => _AnimatedCounterState();
}

class _AnimatedCounterState extends State<AnimatedCounter>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;
  double _previousValue = 0;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: widget.duration);
    _anim = Tween<double>(begin: 0, end: widget.value).animate(
      CurvedAnimation(parent: _ctrl, curve: widget.curve),
    );
    _ctrl.forward();
  }

  @override
  void didUpdateWidget(AnimatedCounter old) {
    super.didUpdateWidget(old);
    if (old.value != widget.value) {
      _previousValue = _anim.value;
      _anim = Tween<double>(begin: _previousValue, end: widget.value).animate(
        CurvedAnimation(parent: _ctrl, curve: widget.curve),
      );
      _ctrl.forward(from: 0);
    }
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  String _format(double v) {
    final abs = v.abs();
    String formatted;
    if (widget.decimals == 0) {
      // INR-style: 1,23,456
      formatted = _formatIndian(abs.round());
    } else {
      formatted = abs.toStringAsFixed(widget.decimals);
    }
    final sign = widget.showSign && v != 0 ? (v > 0 ? '+' : '-') : (v < 0 ? '-' : '');
    return '$sign${widget.prefix}$formatted${widget.suffix}';
  }

  String _formatIndian(int n) {
    if (n < 1000) return n.toString();
    final s = n.toString();
    final lastThree = s.substring(s.length - 3);
    final rest = s.substring(0, s.length - 3);
    if (rest.isEmpty) return lastThree;
    // Add commas every 2 digits for Indian numbering
    final buf = StringBuffer();
    for (int i = 0; i < rest.length; i++) {
      if (i > 0 && (rest.length - i) % 2 == 0) buf.write(',');
      buf.write(rest[i]);
    }
    return '$buf,$lastThree';
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => Text(_format(_anim.value), style: widget.style),
    );
  }
}

/// A value that flashes briefly when it changes (green flash for up, red for down).
class FlashValue extends StatefulWidget {
  final double value;
  final Widget child;
  final Duration flashDuration;

  const FlashValue({
    super.key,
    required this.value,
    required this.child,
    this.flashDuration = const Duration(milliseconds: 600),
  });

  @override
  State<FlashValue> createState() => _FlashValueState();
}

class _FlashValueState extends State<FlashValue>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _flash;
  double _prevValue = 0;
  bool _isUp = true;

  @override
  void initState() {
    super.initState();
    _prevValue = widget.value;
    _ctrl = AnimationController(vsync: this, duration: widget.flashDuration);
    _flash = Tween<double>(begin: 0.3, end: 0).animate(
      CurvedAnimation(parent: _ctrl, curve: Curves.easeOut),
    );
  }

  @override
  void didUpdateWidget(FlashValue old) {
    super.didUpdateWidget(old);
    if (old.value != widget.value && (widget.value - _prevValue).abs() > 0.001) {
      _isUp = widget.value > _prevValue;
      _prevValue = widget.value;
      _ctrl.forward(from: 0);
    }
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _flash,
      builder: (_, __) => Container(
        decoration: BoxDecoration(
          color: _flash.value > 0
              ? (_isUp ? const Color(0xFF00E676) : const Color(0xFFFF5252))
                  .withValues(alpha: _flash.value)
              : null,
          borderRadius: BorderRadius.circular(4),
        ),
        child: widget.child,
      ),
    );
  }
}
