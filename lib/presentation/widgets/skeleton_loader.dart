import 'package:flutter/material.dart';

/// Shimmer/skeleton loading widget matching web `.skeleton` CSS class.
/// Enhanced with diagonal sweep, scale pulse, and smoother transitions.
class SkeletonLoader extends StatefulWidget {
  final double? width;
  final double? height;
  final double borderRadius;
  final EdgeInsets? margin;

  const SkeletonLoader({
    super.key,
    this.width,
    this.height = 16,
    this.borderRadius = 6,
    this.margin,
  });

  /// A common skeleton row (label + value placeholder)
  factory SkeletonLoader.row({Key? key, double? width}) => SkeletonLoader(
    key: key, width: width ?? double.infinity, height: 14, borderRadius: 4,
    margin: const EdgeInsets.only(bottom: 12),
  );

  /// A skeleton card (matches stat-card shape)
  factory SkeletonLoader.card({Key? key}) => SkeletonLoader(
    key: key, width: double.infinity, height: 100, borderRadius: 12,
  );

  /// A skeleton circle (avatar/icon)
  factory SkeletonLoader.circle({Key? key, double size = 40}) => SkeletonLoader(
    key: key, width: size, height: size, borderRadius: size / 2,
  );

  /// A table row skeleton
  factory SkeletonLoader.tableRow({Key? key}) => SkeletonLoader(
    key: key, width: double.infinity, height: 42, borderRadius: 0,
    margin: const EdgeInsets.only(bottom: 1),
  );

  @override
  State<SkeletonLoader> createState() => _SkeletonLoaderState();
}

class _SkeletonLoaderState extends State<SkeletonLoader>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _animation;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1800))
      ..repeat();
    _animation = Tween<double>(begin: -2, end: 2).animate(
      CurvedAnimation(parent: _ctrl, curve: Curves.easeInOutSine),
    );
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final baseColor = isDark ? const Color(0xFF161B2E) : const Color(0xFFE5E7EB);
    final shimmerColor = isDark ? const Color(0xFF242A42) : const Color(0xFFF3F4F6);
    final highlightColor = isDark ? const Color(0xFF2E3556) : const Color(0xFFFAFAFB);

    return AnimatedBuilder(
      animation: _animation,
      builder: (_, child) => Container(
        width: widget.width,
        height: widget.height,
        margin: widget.margin,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(widget.borderRadius),
          // Diagonal sweep for more premium feel
          gradient: LinearGradient(
            begin: Alignment(_animation.value - 1, _animation.value * 0.3 - 0.5),
            end: Alignment(_animation.value + 1, _animation.value * 0.3 + 0.5),
            colors: [baseColor, shimmerColor, highlightColor, shimmerColor, baseColor],
            stops: const [0.0, 0.3, 0.5, 0.7, 1.0],
          ),
        ),
      ),
    );
  }
}

/// A full skeleton loading view for portfolio/table screens.
/// Enhanced with staggered appearance animation.
class SkeletonTableView extends StatefulWidget {
  final int rows;
  final int cards;

  const SkeletonTableView({super.key, this.rows = 8, this.cards = 4});

  @override
  State<SkeletonTableView> createState() => _SkeletonTableViewState();
}

class _SkeletonTableViewState extends State<SkeletonTableView>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _fade;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 600));
    _fade = CurvedAnimation(parent: _ctrl, curve: Curves.easeOut);
    _ctrl.forward();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _fade,
      child: Column(children: [
        // Stat cards skeleton
        Row(children: List.generate(widget.cards, (i) => Expanded(
          child: Padding(
            padding: EdgeInsets.only(right: i < widget.cards - 1 ? 12 : 0),
            child: SkeletonLoader.card(),
          ),
        ))),
        const SizedBox(height: 20),
        // Table skeleton
        SkeletonLoader(width: double.infinity, height: 44, borderRadius: 0), // header
        ...List.generate(widget.rows, (_) => SkeletonLoader.tableRow()),
      ]),
    );
  }
}
