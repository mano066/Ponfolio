import 'package:flutter/material.dart';

/// Wraps a scrollable list of children and animates each one in
/// with a staggered fade + slide-up effect on mount.
///
/// Usage:
/// ```dart
/// AnimatedPageWrapper(children: [statCards, table, chart])
/// ```
class AnimatedPageWrapper extends StatefulWidget {
  final List<Widget> children;
  final EdgeInsets padding;
  final Duration itemDuration;
  final Duration staggerDelay;
  final double slideOffset;

  const AnimatedPageWrapper({
    super.key,
    required this.children,
    this.padding = const EdgeInsets.all(0),
    this.itemDuration = const Duration(milliseconds: 500),
    this.staggerDelay = const Duration(milliseconds: 60),
    this.slideOffset = 24,
  });

  @override
  State<AnimatedPageWrapper> createState() => _AnimatedPageWrapperState();
}

class _AnimatedPageWrapperState extends State<AnimatedPageWrapper>
    with TickerProviderStateMixin {
  final List<AnimationController> _ctrls = [];
  final List<Animation<double>> _fadeAnims = [];
  final List<Animation<Offset>> _slideAnims = [];

  @override
  void initState() {
    super.initState();
    _buildAnimations();
  }

  void _buildAnimations() {
    for (int i = 0; i < widget.children.length; i++) {
      final ctrl = AnimationController(vsync: this, duration: widget.itemDuration);
      _ctrls.add(ctrl);
      _fadeAnims.add(CurvedAnimation(parent: ctrl, curve: Curves.easeOutCubic));
      _slideAnims.add(Tween<Offset>(
        begin: Offset(0, widget.slideOffset),
        end: Offset.zero,
      ).animate(CurvedAnimation(parent: ctrl, curve: Curves.easeOutCubic)));

      // Stagger the start
      Future.delayed(widget.staggerDelay * i, () {
        if (mounted) ctrl.forward();
      });
    }
  }

  @override
  void dispose() {
    for (final c in _ctrls) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      padding: widget.padding,
      itemCount: widget.children.length,
      itemBuilder: (_, i) {
        if (i >= _ctrls.length) return widget.children[i];
        return AnimatedBuilder(
          animation: _ctrls[i],
          builder: (_, __) => Transform.translate(
            offset: _slideAnims[i].value,
            child: Opacity(
              opacity: _fadeAnims[i].value,
              child: widget.children[i],
            ),
          ),
        );
      },
    );
  }
}

/// Wrap a single widget with staggered entrance animation.
/// Use inside existing ListViews or Columns.
class AnimatedListItem extends StatefulWidget {
  final Widget child;
  final int index;
  final Duration duration;
  final Duration staggerDelay;
  final double slideOffset;
  final Axis slideAxis;

  const AnimatedListItem({
    super.key,
    required this.child,
    this.index = 0,
    this.duration = const Duration(milliseconds: 450),
    this.staggerDelay = const Duration(milliseconds: 50),
    this.slideOffset = 20,
    this.slideAxis = Axis.vertical,
  });

  @override
  State<AnimatedListItem> createState() => _AnimatedListItemState();
}

class _AnimatedListItemState extends State<AnimatedListItem>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _fade;
  late final Animation<double> _slide;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: widget.duration);
    _fade = CurvedAnimation(parent: _ctrl, curve: Curves.easeOut);
    _slide = Tween<double>(begin: widget.slideOffset, end: 0).animate(
      CurvedAnimation(parent: _ctrl, curve: Curves.easeOutCubic),
    );
    Future.delayed(widget.staggerDelay * widget.index, () {
      if (mounted) _ctrl.forward();
    });
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (_, __) {
        final offset = widget.slideAxis == Axis.vertical
            ? Offset(0, _slide.value)
            : Offset(_slide.value, 0);
        return Transform.translate(
          offset: offset,
          child: Opacity(opacity: _fade.value, child: widget.child),
        );
      },
    );
  }
}

/// Smooth page-level crossfade transition for tab switching.
class PageCrossFade extends StatelessWidget {
  final Widget child;
  final Duration duration;

  const PageCrossFade({
    super.key,
    required this.child,
    this.duration = const Duration(milliseconds: 250),
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: duration,
      switchInCurve: Curves.easeOut,
      switchOutCurve: Curves.easeIn,
      transitionBuilder: (child, anim) => FadeTransition(
        opacity: anim,
        child: SlideTransition(
          position: Tween<Offset>(
            begin: const Offset(0, 0.02),
            end: Offset.zero,
          ).animate(anim),
          child: child,
        ),
      ),
      child: child,
    );
  }
}
