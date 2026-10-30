import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_dimensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';

/// ─── Stitch Design System — Common Widgets ───
/// Badges: pill-shaped, 10% opacity bg, hover glow
/// Buttons: solid fills (no gradients), hover glow
/// Section headers: clean, bottom border

/// Badge matching `.badge` variants — Stitch style: pill, hover glow
enum BadgeVariant { up, dn, hold, blue, accent, gold }

class AppBadge extends StatefulWidget {
  final String text;
  final BadgeVariant variant;
  final double? fontSize;
  final Widget? icon;

  const AppBadge({
    super.key,
    required this.text,
    required this.variant,
    this.fontSize,
    this.icon,
  });

  /// Auto-detect variant from verdict string
  factory AppBadge.fromVerdict(String verdict) {
    final v = verdict.toUpperCase();
    BadgeVariant variant;
    if (['BUY', 'BULLISH', 'OVERWEIGHT', 'STRONG', 'POSITIVE', 'ACCUMULATE'].any(v.contains)) {
      variant = BadgeVariant.up;
    } else if (['SELL', 'BEARISH', 'UNDERWEIGHT', 'NEGATIVE', 'AVOID'].any(v.contains)) {
      variant = BadgeVariant.dn;
    } else {
      variant = BadgeVariant.hold;
    }
    return AppBadge(text: verdict, variant: variant);
  }

  @override
  State<AppBadge> createState() => _AppBadgeState();
}

class _AppBadgeState extends State<AppBadge> {
  bool _hovering = false;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    Color bg, fg, border;
    switch (widget.variant) {
      case BadgeVariant.up:
        bg = c.upBg; fg = c.up; border = c.up.withValues(alpha: 0.2);
      case BadgeVariant.dn:
        bg = c.dnBg; fg = c.dn; border = c.dn.withValues(alpha: 0.2);
      case BadgeVariant.hold:
        bg = c.bg3; fg = c.t3; border = c.bd;
      case BadgeVariant.blue:
        bg = c.blueBg; fg = c.blue; border = c.blue.withValues(alpha: 0.2);
      case BadgeVariant.accent:
        bg = c.accentBg; fg = c.accent; border = c.accent.withValues(alpha: 0.2);
      case BadgeVariant.gold:
        bg = c.goldBg; fg = c.gold; border = c.gold.withValues(alpha: 0.2);
    }

    return MouseRegion(
      onEnter: (_) => setState(() => _hovering = true),
      onExit: (_) => setState(() => _hovering = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(
          horizontal: AppDimensions.badgePaddingH,
          vertical: AppDimensions.badgePaddingV,
        ),
        decoration: BoxDecoration(
          color: bg,
          border: Border.all(color: _hovering ? fg.withValues(alpha: 0.4) : border, width: 1),
          // Stitch: pill-shaped for badges
          borderRadius: BorderRadius.circular(AppDimensions.radiusFull),
          // Stitch: hover glow
          boxShadow: _hovering
              ? [BoxShadow(color: fg.withValues(alpha: 0.20), blurRadius: 12)]
              : null,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (widget.icon != null) ...[widget.icon!, const SizedBox(width: 4)],
            Text(
              widget.text,
              style: AppTextStyles.badge(fg).copyWith(fontSize: widget.fontSize),
            ),
          ],
        ),
      ),
    );
  }
}

/// Groww/INDmoney-style card surface: white (or dark) fill, generous radius,
/// hairline border, and a soft ambient shadow in light mode (dark mode leans on
/// the border instead). Use for all content cards in the new look.
BoxDecoration cardSurface(
  BuildContext context, {
  double radius = 16,
  Color? fill,
  Color? borderColor,
  bool elevated = true,
}) {
  final c = context.colors;
  return BoxDecoration(
    color: fill ?? c.bg2,
    borderRadius: BorderRadius.circular(radius),
    border: Border.all(color: borderColor ?? c.bd, width: 1),
    boxShadow: (elevated && !context.isDark)
        ? const [
            BoxShadow(
                color: Color(0x0D101828),
                blurRadius: 18,
                offset: Offset(0, 6)),
          ]
        : null,
  );
}

/// Consistent error state with a Retry action — Stitch style.
/// Used across all data-backed screens so a transient load failure shows a
/// clear message + retry instead of a broken/empty view.
class ErrorRetry extends StatelessWidget {
  final String title;
  final String? detail;
  final VoidCallback onRetry;
  final IconData icon;
  final bool compact;

  const ErrorRetry({
    super.key,
    this.title = 'Unable to load',
    this.detail,
    required this.onRetry,
    this.icon = LucideIcons.wifiOff,
    this.compact = false,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: compact ? 40 : 48, color: c.dn.withValues(alpha: 0.5)),
          SizedBox(height: compact ? 12 : 16),
          Text(title, style: AppTextStyles.heading3(c.t2)),
          if (detail != null && detail!.isNotEmpty) ...[
            const SizedBox(height: 6),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Text(
                detail!,
                style: AppTextStyles.bodySmall(c.t3),
                textAlign: TextAlign.center,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
          const SizedBox(height: 16),
          HeaderButton(
            icon: const Icon(LucideIcons.refreshCw, size: 14, color: Colors.white),
            text: 'Retry',
            primary: true,
            onTap: onRetry,
          ),
        ],
      ),
    );
  }
}

/// Section header — Stitch: clean, bottom border separator
class SectionHeader extends StatelessWidget {
  final IconData? icon;
  final Color? iconBg;
  final Color? iconColor;
  final String title;
  final String? subtitle;
  final Widget? trailing;

  const SectionHeader({
    super.key,
    this.icon,
    this.iconBg,
    this.iconColor,
    required this.title,
    this.subtitle,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppDimensions.sectionHeaderPaddingH,
        vertical: AppDimensions.sectionHeaderPaddingV,
      ),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: c.bd, width: 1)),
      ),
      child: Row(
        children: [
          if (icon != null) ...[
            Container(
              width: AppDimensions.sectionHeaderIconSize,
              height: AppDimensions.sectionHeaderIconSize,
              decoration: BoxDecoration(
                color: (iconBg ?? c.blueBg),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: (iconColor ?? c.blue).withValues(alpha: 0.15)),
              ),
              child: Icon(icon, size: 16, color: iconColor ?? c.blue),
            ),
            const SizedBox(width: AppDimensions.sectionHeaderGap),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(title, style: AppTextStyles.sectionTitle(c.t1)),
                if (subtitle != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(subtitle!, style: AppTextStyles.sectionSubtitle(c.t3)),
                  ),
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

/// Header action button — Stitch: solid colors, no gradients, hover glow
class HeaderButton extends StatefulWidget {
  final Widget? icon;
  final String? text;
  final VoidCallback? onTap;
  final bool primary;
  final Gradient? gradient; // kept for compat — converted to solid in Stitch
  final bool disabled;
  final bool loading;
  final Color? solidColor; // Stitch: explicit solid fill color

  const HeaderButton({
    super.key,
    this.icon,
    this.text,
    this.onTap,
    this.primary = false,
    this.gradient,
    this.disabled = false,
    this.loading = false,
    this.solidColor,
  });

  @override
  State<HeaderButton> createState() => _HeaderButtonState();
}

class _HeaderButtonState extends State<HeaderButton> {
  bool _hovering = false;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    // Stitch: convert gradient to solid — use first color of gradient or solidColor
    final hasFill = widget.solidColor != null || widget.gradient != null || widget.primary;
    final fillColor = widget.solidColor
        ?? (widget.gradient != null ? widget.gradient!.colors.first : null)
        ?? (widget.primary ? c.blue : null);

    return MouseRegion(
      cursor: widget.disabled ? SystemMouseCursors.basic : SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hovering = true),
      onExit: (_) => setState(() => _hovering = false),
      child: GestureDetector(
        onTap: widget.disabled || widget.loading ? null : widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            // Stitch: solid color fill, NO gradient
            color: widget.disabled
                ? c.bg3
                : hasFill
                    ? (_hovering ? fillColor : fillColor?.withValues(alpha: 0.85))
                    : (_hovering ? c.bg3 : c.bg2),
            border: hasFill && !widget.disabled
                ? null
                : Border.all(color: _hovering ? c.bd2 : c.bd, width: 1),
            borderRadius: BorderRadius.circular(AppDimensions.radiusSm),
            // Stitch: hover glow
            boxShadow: _hovering && !widget.disabled
                ? [BoxShadow(color: (fillColor ?? c.blue).withValues(alpha: 0.20), blurRadius: 12)]
                : null,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (widget.loading)
                SizedBox(
                  width: 14, height: 14,
                  child: CircularProgressIndicator(strokeWidth: 2, color: hasFill ? Colors.white : c.t3),
                )
              else if (widget.icon != null)
                widget.icon!,
              if (widget.text != null) ...[
                if (widget.icon != null || widget.loading) const SizedBox(width: 6),
                Text(
                  widget.text!,
                  style: AppTextStyles.headerBtn(
                    widget.disabled ? c.t4 : hasFill ? Colors.white : (_hovering ? c.t1 : c.t2),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
