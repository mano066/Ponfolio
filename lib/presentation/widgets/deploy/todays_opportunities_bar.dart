import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/dip_models.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/providers/deploy_provider.dart';

/// TODAY'S OPPORTUNITIES — the first thing on the dashboard.
///
/// This widget is the answer to "what deserves my attention today", and it has
/// to land in about five seconds. Everything about it is subordinate to that:
/// at most a handful of cards, one line of argument on each, no tables, and a
/// market read that is one word plus one sentence.
///
/// The behaviour it lives or dies by is the QUIET state. The backtest built
/// into this app measured a negative edge for shallow dips against simply
/// buying on a random day, which means most mornings genuinely offer nothing.
/// A bar that manufactures a BUY anyway would be trained-away within a week,
/// so "No strong dip today" is rendered as a real, calm answer rather than as
/// an empty state apologising for itself.
class TodaysOpportunitiesBar extends ConsumerWidget {
  /// Opens the detail sheet for a row the user taps.
  final void Function(OpportunityRow row)? onOpen;

  const TodaysOpportunitiesBar({super.key, this.onOpen});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(opportunitiesProvider);
    final board = async.value ?? OpportunityBoard.empty;

    if (async.hasError && !async.isLoading) {
      // "No strong dip today" is a real verdict here, so it must never stand
      // in for a request that simply did not come back.
      return DenseCard(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 26),
        child: Column(children: [
          Icon(LucideIcons.plugZap, size: 24, color: context.colors.gold),
          const SizedBox(height: 10),
          Text("Could not read today's opportunities",
              style: AppTextStyles.bodyBold(context.colors.t1)
                  .copyWith(fontSize: 13)),
          const SizedBox(height: 12),
          TextButton.icon(
            onPressed: () => ref.invalidate(opportunitiesProvider),
            icon: Icon(LucideIcons.refreshCw,
                size: 13, color: context.colors.accent),
            label: Text('Retry',
                style: AppTextStyles.bodyBold(context.colors.accent)
                    .copyWith(fontSize: 12)),
          ),
        ]),
      );
    }
    if (async.isLoading && board.rows.isEmpty) {
      return const DenseCard(
        child: SizedBox(
          height: 120,
          child: DensePulseLoader(label: 'Reading the market…'),
        ),
      );
    }

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _header(context, ref, board),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
          child: LayoutBuilder(builder: (context, box) {
            // The market read and the cards sit side by side while there is
            // room, and stack when there is not. A horizontal scroller for the
            // cards would hide the risk row, which is the one row that must
            // never need a gesture to discover.
            final stack = box.maxWidth < 900;
            final signal = _MarketSignalBlock(market: board.market);
            final cards = _cards(context, board);
            if (stack) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [signal, const SizedBox(height: 14), cards],
              );
            }
            return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SizedBox(width: 260, child: signal),
              const SizedBox(width: 18),
              Expanded(child: cards),
            ]);
          }),
        ),
      ]),
    );
  }

  Widget _header(BuildContext context, WidgetRef ref, OpportunityBoard board) {
    final c = context.colors;
    final busy = ref.watch(dashboardRefreshingProvider);
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 11, 14, 11),
      decoration: BoxDecoration(
        color: c.bg3,
        border: Border(bottom: BorderSide(color: c.bd)),
      ),
      // The title and the timestamp both give ground as the window narrows;
      // the Update button never does. It is the only control here, and a
      // control that disappears when the window is small is worse than a
      // truncated label.
      child: LayoutBuilder(builder: (context, box) {
        final tight = box.maxWidth < 560;
        return Row(children: [
          Icon(LucideIcons.target, size: 15, color: c.accent),
          const SizedBox(width: 8),
          Flexible(
            child: Text("TODAY'S OPPORTUNITIES",
                style: AppTextStyles.bodyBold(c.t1)
                    .copyWith(fontSize: 13, letterSpacing: 0.6),
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
          ),
          const Spacer(),
          if (board.riskCount > 0 && !tight) ...[
            Icon(LucideIcons.triangleAlert, size: 12, color: c.dn),
            const SizedBox(width: 4),
            Text('${board.riskCount} to avoid',
                style: AppTextStyles.labelXs(c.dn)),
            const SizedBox(width: 12),
          ],
          if (!tight)
            Flexible(
              child: Text(_stamp(board.asOf),
                  style: AppTextStyles.labelXs(c.t3),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
            ),
          const SizedBox(width: 8),
          _UpdateButton(
            busy: busy,
            onTap: () =>
                ref.read(deployRefreshProvider.notifier).manualRefresh(),
          ),
        ]);
      }),
    );
  }

  String _stamp(String asOf) {
    if (asOf.isEmpty) return '';
    final t = DateTime.tryParse(asOf);
    if (t == null) return '';
    final h = t.hour % 12 == 0 ? 12 : t.hour % 12;
    final m = t.minute.toString().padLeft(2, '0');
    return 'Updated $h:$m ${t.hour < 12 ? 'AM' : 'PM'} · hourly';
  }

  Widget _cards(BuildContext context, OpportunityBoard board) {
    if (board.rows.isEmpty) return _QuietBlock(board: board);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (board.isQuiet) ...[
        _QuietBlock(board: board, compact: true),
        const SizedBox(height: 10),
      ],
      Wrap(
        spacing: 10,
        runSpacing: 10,
        children: [
          for (final row in board.rows)
            _OpportunityCard(row: row, onTap: () => onOpen?.call(row)),
        ],
      ),
    ]);
  }
}

/// "No strong dip today" — a real answer, not an apology.
class _QuietBlock extends StatelessWidget {
  final OpportunityBoard board;
  final bool compact;

  const _QuietBlock({required this.board, this.compact = false});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.symmetric(horizontal: 14, vertical: compact ? 10 : 22),
      decoration: BoxDecoration(
        color: c.bg3,
        borderRadius: BorderRadius.circular(7),
        border: Border.all(color: c.bd),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(LucideIcons.moon, size: 14, color: c.t2),
          const SizedBox(width: 8),
          Text(board.headline ?? 'No strong dip today',
              style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 13)),
        ]),
        const SizedBox(height: 5),
        Text(
          board.detail ??
              'Nothing currently meets the strategy threshold. '
                  'Keep the plan running and wait.',
          style: AppTextStyles.labelXs(c.t3),
        ),
      ]),
    );
  }
}

/// The one-word market read plus one sentence.
class _MarketSignalBlock extends StatelessWidget {
  final MarketSignal market;
  const _MarketSignalBlock({required this.market});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    // Red is RISK, green is a correction worth buying — the same inverted
    // palette the tape uses, so the two never contradict each other.
    final tone = switch (market.signal) {
      'opportunity' => c.up,
      'correction' => c.accent,
      'high_risk' => c.dn,
      'normal' => c.gold,
      _ => c.t3,
    };

    return Container(
      padding: const EdgeInsets.fromLTRB(13, 12, 13, 13),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(7),
        border: Border.all(color: tone.withValues(alpha: 0.35)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text("TODAY'S MARKET", style: AppTextStyles.labelXs(c.t3)),
        const SizedBox(height: 6),
        Row(children: [
          Text(market.emoji, style: const TextStyle(fontSize: 15)),
          const SizedBox(width: 7),
          Flexible(
            child: Text(market.label.toUpperCase(),
                style: AppTextStyles.bodyBold(tone)
                    .copyWith(fontSize: 16, letterSpacing: 0.4),
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
          ),
        ]),
        const SizedBox(height: 7),
        Text(market.summary,
            style: AppTextStyles.labelXs(c.t2), maxLines: 3),
      ]),
    );
  }
}

/// One compact, tappable opportunity card. Never overloaded: an action, a
/// name, a score, one number and one reason.
class _OpportunityCard extends StatefulWidget {
  final OpportunityRow row;
  final VoidCallback? onTap;

  const _OpportunityCard({required this.row, this.onTap});

  @override
  State<_OpportunityCard> createState() => _OpportunityCardState();
}

class _OpportunityCardState extends State<_OpportunityCard> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final row = widget.row;
    final tone = switch (row.action) {
      'buy' || 'add' => c.up,
      'watch' => c.gold,
      'avoid' => c.dn,
      _ => c.t3,
    };

    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          width: 232,
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 11),
          decoration: BoxDecoration(
            color: _hover ? tone.withValues(alpha: 0.10) : c.bg2,
            borderRadius: BorderRadius.circular(7),
            border: Border.all(
                color: _hover ? tone.withValues(alpha: 0.55) : c.bd),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(children: [
                Text(row.emoji, style: const TextStyle(fontSize: 11)),
                const SizedBox(width: 5),
                Text(row.label,
                    style: AppTextStyles.bodyBold(tone)
                        .copyWith(fontSize: 11, letterSpacing: 0.7)),
                const Spacer(),
                if (row.score != null)
                  Text(row.score!.toStringAsFixed(0),
                      style: AppTextStyles.monoBold(c.t1)
                          .copyWith(fontSize: 17, height: 1.0)),
              ]),
              const SizedBox(height: 7),
              Text(row.name,
                  style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12.5),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
              if (row.subtitle.isNotEmpty)
                Text(row.subtitle,
                    style: AppTextStyles.labelXs(c.t3),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis),
              const SizedBox(height: 7),
              Row(children: [
                if (row.price != null)
                  Text(
                    '${row.priceLabel} ${formatINR(row.price!, decimals: 2)}',
                    style: AppTextStyles.mono(c.t2).copyWith(fontSize: 11),
                  ),
                if (row.price != null && row.metric != null)
                  Text('  ·  ', style: AppTextStyles.labelXs(c.t4)),
                if (row.metric != null)
                  Flexible(
                    child: Text(row.metric!,
                        style: AppTextStyles.mono(c.t2).copyWith(fontSize: 11),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis),
                  ),
              ]),
              if (row.why != null) ...[
                const SizedBox(height: 6),
                // The line that makes the score trustworthy. "82" alone is a
                // number; "82 — silver is 36.8% off its high" is a signal.
                Text(row.why!,
                    style: AppTextStyles.labelXs(
                        row.isRisk ? c.dn : c.t3),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis),
              ],
              if (row.lowConfidence) ...[
                const SizedBox(height: 5),
                Row(children: [
                  Icon(LucideIcons.circleHelp, size: 10, color: c.gold),
                  const SizedBox(width: 4),
                  Text('Thin evidence',
                      style: AppTextStyles.labelXs(c.gold)),
                ]),
              ],
            ],
          ),
        ),
      ),
    );
  }
}


/// The manual Update control.
///
/// Sits beside the timestamp rather than in the app bar because that is where
/// the question arises: the stamp says when this was measured, and the button
/// is the answer to "measure it again now". It forces past the server cache,
/// which the hourly tick deliberately does not.
class _UpdateButton extends StatefulWidget {
  final bool busy;
  final VoidCallback onTap;

  const _UpdateButton({required this.busy, required this.onTap});

  @override
  State<_UpdateButton> createState() => _UpdateButtonState();
}

class _UpdateButtonState extends State<_UpdateButton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _spin = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 900));
  bool _hover = false;

  @override
  void didUpdateWidget(_UpdateButton old) {
    super.didUpdateWidget(old);
    // The spinner follows the ACTUAL fetch, not a fixed timer, so it cannot
    // stop while the request is still out — which would read as "done".
    if (widget.busy && !_spin.isAnimating) {
      _spin.repeat();
    } else if (!widget.busy && _spin.isAnimating) {
      _spin.stop();
      _spin.value = 0;
    }
  }

  @override
  void dispose() {
    _spin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final tone = widget.busy ? c.t3 : c.accent;
    return MouseRegion(
      cursor: widget.busy
          ? SystemMouseCursors.wait
          : SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        // Ignored while busy: a second press cannot make the answer arrive
        // sooner and only queues another sweep.
        onTap: widget.busy ? null : widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
          decoration: BoxDecoration(
            color: _hover && !widget.busy
                ? tone.withValues(alpha: 0.12)
                : Colors.transparent,
            borderRadius: BorderRadius.circular(5),
            border: Border.all(color: tone.withValues(alpha: 0.45)),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            RotationTransition(
              turns: _spin,
              child: Icon(LucideIcons.refreshCw, size: 11, color: tone),
            ),
            const SizedBox(width: 5),
            Text(widget.busy ? 'Updating…' : 'Update',
                style: AppTextStyles.bodyBold(tone).copyWith(fontSize: 10.5)),
          ]),
        ),
      ),
    );
  }
}
