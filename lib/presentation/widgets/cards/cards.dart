import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_dimensions.dart';
import 'package:aiei_wealth/core/theme/app_colors.dart';

/// ─── Stitch Design System Cards ───
/// All containers: solid bg2, 1px bd border, 16px radius
/// Hover: glow box-shadow 0 0 12px [Color]33 (20%)
/// No gradients, no top gradient bars
/// Depth via tonal surface layers

/// Glassmorphic card matching `.glass-card` from CSS
class GlassCard extends StatelessWidget {
  final Widget child;
  final EdgeInsets? padding;
  final double borderRadius;

  const GlassCard({
    super.key,
    required this.child,
    this.padding,
    this.borderRadius = AppDimensions.radiusLg,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return ClipRRect(
      borderRadius: BorderRadius.circular(borderRadius),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
        child: Container(
          decoration: BoxDecoration(
            color: c.glass,
            borderRadius: BorderRadius.circular(borderRadius),
            border: Border.all(color: c.glassBorder, width: 1),
          ),
          padding: padding,
          child: child,
        ),
      ),
    );
  }
}

/// Premium card — Stitch: solid bg, border, hover glow
/// No gradient top bar, no lift effect
class PremiumCard extends StatefulWidget {
  final Widget child;
  final EdgeInsets? padding;
  final double borderRadius;
  final bool glow;
  final Gradient? topGradient; // kept for compat but ignored in Stitch mode
  final VoidCallback? onTap;
  final bool isSelected;
  final Color? accentColor; // optional accent for left border

  const PremiumCard({
    super.key,
    required this.child,
    this.padding,
    this.borderRadius = AppDimensions.radiusLg,
    this.glow = false,
    this.topGradient,
    this.onTap,
    this.isSelected = false,
    this.accentColor,
  });

  @override
  State<PremiumCard> createState() => _PremiumCardState();
}

class _PremiumCardState extends State<PremiumCard>
    with SingleTickerProviderStateMixin {
  bool _hovering = false;
  late AnimationController _glowCtrl;
  late Animation<double> _glowAnim;

  @override
  void initState() {
    super.initState();
    _glowCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    );
    _glowAnim = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _glowCtrl, curve: Curves.easeInOut),
    );
    if (widget.glow) _glowCtrl.repeat(reverse: true);
  }

  @override
  void didUpdateWidget(PremiumCard old) {
    super.didUpdateWidget(old);
    if (widget.glow && !old.glow) {
      _glowCtrl.repeat(reverse: true);
    } else if (!widget.glow && old.glow) {
      _glowCtrl.stop();
      _glowCtrl.value = 0;
    }
  }

  @override
  void dispose() {
    _glowCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final accent = widget.accentColor ?? c.blue;
    return MouseRegion(
      cursor: widget.onTap != null ? SystemMouseCursors.click : SystemMouseCursors.basic,
      onEnter: (_) => setState(() => _hovering = true),
      onExit: (_) => setState(() => _hovering = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedBuilder(
          animation: _glowAnim,
          builder: (_, __) => AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            decoration: BoxDecoration(
              // Stitch: solid surface-container
              color: c.bg2,
              borderRadius: BorderRadius.circular(widget.borderRadius),
              border: Border.all(
                color: widget.isSelected
                    ? accent.withValues(alpha: 0.40)
                    : _hovering ? c.bd2 : c.bd,
                width: 1,
              ),
              // Stitch: hover glow, no lift
              boxShadow: [
                if (_hovering)
                  BoxShadow(
                    color: accent.withValues(alpha: 0.20),
                    blurRadius: 12,
                  ),
                if (widget.glow)
                  BoxShadow(
                    color: accent.withValues(alpha: 0.08 + _glowAnim.value * 0.12),
                    blurRadius: 12 + _glowAnim.value * 8,
                  ),
              ],
            ),
            child: widget.padding != null
                ? Padding(padding: widget.padding!, child: widget.child)
                : widget.child,
          ),
        ),
      ),
    );
  }
}

/// Stat card — Stitch: solid bg, thin accent left border, hover glow
/// No gradient top bar
enum StatCardVariant { blue, up, dn, accent, gold }

class StatCard extends StatefulWidget {
  final StatCardVariant variant;
  final Widget child;
  final EdgeInsets padding;

  const StatCard({
    super.key,
    required this.variant,
    required this.child,
    this.padding = const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
  });

  @override
  State<StatCard> createState() => _StatCardState();
}

class _StatCardState extends State<StatCard> {
  bool _hovering = false;

  Color _accentColor(AppColorScheme c) {
    switch (widget.variant) {
      case StatCardVariant.blue: return c.blue;
      case StatCardVariant.up: return c.up;
      case StatCardVariant.dn: return c.dn;
      case StatCardVariant.accent: return c.accent;
      case StatCardVariant.gold: return c.gold;
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final accent = _accentColor(c);

    return MouseRegion(
      onEnter: (_) => setState(() => _hovering = true),
      onExit: (_) => setState(() => _hovering = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        decoration: BoxDecoration(
          // Stitch: solid surface-container
          color: c.bg2,
          borderRadius: BorderRadius.circular(AppDimensions.radiusLg),
          border: Border.all(
            color: _hovering ? accent.withValues(alpha: 0.25) : c.bd,
            width: 1,
          ),
          // Stitch: hover glow pattern
          boxShadow: _hovering
              ? [BoxShadow(color: accent.withValues(alpha: 0.20), blurRadius: 12)]
              : [],
        ),
        child: IntrinsicHeight(child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Stitch: thin left accent line instead of gradient top bar
            AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              width: 3,
              decoration: BoxDecoration(
                color: accent.withValues(alpha: _hovering ? 0.80 : 0.40),
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(AppDimensions.radiusLg),
                  bottomLeft: Radius.circular(AppDimensions.radiusLg),
                ),
                boxShadow: _hovering
                    ? [BoxShadow(color: accent.withValues(alpha: 0.40), blurRadius: 6)]
                    : [],
              ),
            ),
            Expanded(
              child: Padding(padding: widget.padding, child: widget.child),
            ),
          ],
        )),
      ),
    );
  }
}
