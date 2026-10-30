import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/dip_models.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/providers/deploy_provider.dart';

// ══════════════════════════════════════════════════════════════
//  SHARED PIECES
// ══════════════════════════════════════════════════════════════

/// The score, large, with a bar under it.
///
/// A number this prominent has to be readable at a glance and honest at close
/// range, so an unmeasurable score renders as an em dash rather than as a
/// confident zero, and a thin-evidence score is labelled rather than quietly
/// shown at full weight.
class ScoreGauge extends StatelessWidget {
  final double? score;
  final Color tone;
  final bool lowConfidence;
  final double width;

  const ScoreGauge({
    super.key,
    required this.score,
    required this.tone,
    this.lowConfidence = false,
    this.width = 92,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final s = score;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic, children: [
        Text(s == null ? '—' : s.toStringAsFixed(0),
            style: AppTextStyles.monoBold(s == null ? c.t3 : c.t1)
                .copyWith(fontSize: 26, height: 1.0)),
        const SizedBox(width: 3),
        Text('/100', style: AppTextStyles.labelXs(c.t4)),
      ]),
      const SizedBox(height: 5),
      SizedBox(
        width: width,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(3),
          child: LinearProgressIndicator(
            value: (s ?? 0) / 100,
            minHeight: 5,
            backgroundColor: c.bd,
            valueColor: AlwaysStoppedAnimation(s == null ? c.bd2 : tone),
          ),
        ),
      ),
      if (lowConfidence) ...[
        const SizedBox(height: 4),
        Text('thin evidence', style: AppTextStyles.captionXs(c.gold)),
      ],
    ]);
  }
}

/// A one-word verdict chip: FUNDAMENTALS · STRONG.
class StatusChip extends StatelessWidget {
  final String caption;
  final String value;
  final Color tone;

  const StatusChip({
    super.key,
    required this.caption,
    required this.value,
    required this.tone,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(caption, style: AppTextStyles.captionXs(c.t4)),
      const SizedBox(height: 1),
      Text(value.toUpperCase(),
          style: AppTextStyles.bodyBold(tone)
              .copyWith(fontSize: 10, letterSpacing: 0.4),
          maxLines: 1,
          overflow: TextOverflow.ellipsis),
    ]);
  }
}

Widget _sectionHeader(BuildContext context,
    {required IconData icon,
    required Color accent,
    required String title,
    required String subtitle,
    Widget? trailing}) {
  final c = context.colors;
  return Padding(
    padding: const EdgeInsets.fromLTRB(2, 0, 2, 10),
    child: Row(children: [
      Icon(icon, size: 15, color: accent),
      const SizedBox(width: 8),
      Text(title,
          style: AppTextStyles.bodyBold(c.t1)
              .copyWith(fontSize: 13, letterSpacing: 0.5)),
      const SizedBox(width: 10),
      Flexible(
        child: Text(subtitle,
            style: AppTextStyles.labelXs(c.t3),
            maxLines: 1,
            overflow: TextOverflow.ellipsis),
      ),
      const Spacer(),
      ?trailing,
    ]),
  );
}

Widget _reasonList(BuildContext context, List<String> reasons, Color tone) {
  final c = context.colors;
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      for (final r in reasons)
        Padding(
          padding: const EdgeInsets.only(bottom: 2),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Padding(
              padding: const EdgeInsets.only(top: 4, right: 6),
              child: Container(
                width: 3,
                height: 3,
                decoration:
                    BoxDecoration(color: tone, shape: BoxShape.circle),
              ),
            ),
            Expanded(
              child: Text(r,
                  style: AppTextStyles.labelXs(c.t2),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis),
            ),
          ]),
        ),
    ],
  );
}

/// Shown when a fetch FAILED, which is a different fact from "you own
/// nothing" and must not borrow the empty state's wording. The empty state
/// tells the user to add holdings; showing that after a dropped request told a
/// user with nineteen stocks to go and add some.
Widget _loadFailed(
    BuildContext context, String what, VoidCallback onRetry) {
  final c = context.colors;
  return DenseCard(
    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 26),
    child: Column(children: [
      Icon(LucideIcons.plugZap, size: 24, color: c.gold),
      const SizedBox(height: 10),
      Text('Could not load $what',
          style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 13)),
      const SizedBox(height: 4),
      Text('Your holdings are fine — the request did not come back.',
          style: AppTextStyles.labelXs(c.t3)),
      const SizedBox(height: 12),
      TextButton.icon(
        onPressed: onRetry,
        icon: Icon(LucideIcons.refreshCw, size: 13, color: c.accent),
        label: Text('Retry',
            style: AppTextStyles.bodyBold(c.accent).copyWith(fontSize: 12)),
      ),
    ]),
  );
}


// ══════════════════════════════════════════════════════════════
//  MUTUAL FUNDS
// ══════════════════════════════════════════════════════════════

/// MUTUAL FUND — WHERE TO ADD?
///
/// Category tiles first, then the funds themselves ranked by opportunity. The
/// tiles exist so "small caps are more attractive than large caps" is readable
/// before any individual fund is; a category takes its BEST fund's score
/// rather than an average, because averaging would let a fund sitting at its
/// high mask one in a genuine correction.
class FundOpportunitySection extends ConsumerWidget {
  final void Function(FundDip fund)? onOpen;

  const FundOpportunitySection({super.key, this.onOpen});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final async = ref.watch(fundDipsProvider);
    final board = async.value ?? FundDipBoard.empty;

    if (async.hasError && !async.isLoading) {
      return _loadFailed(context, 'your funds',
          () => ref.invalidate(fundDipsProvider));
    }
    if (async.isLoading && board.isEmpty) {
      return const DenseCard(
          child: SizedBox(height: 120, child: DensePulseLoader()));
    }
    if (board.isEmpty) {
      return const DenseEmptyCard(
        icon: LucideIcons.layers,
        title: 'No funds to analyse yet',
        sub: 'Add mutual funds and this section will rank them by opportunity.',
      );
    }

    final ranked = board.ranked;
    final addable =
        ranked.where((f) => f.action == 'add' || f.action == 'attractive').length;

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _sectionHeader(context,
          icon: LucideIcons.layers,
          accent: c.blue,
          title: 'MUTUAL FUND — WHERE TO ADD?',
          subtitle: addable > 0
              ? '$addable of ${ranked.length} worth adding to'
              : 'Nothing in a meaningful dip right now'),
      _CategoryStrip(tiles: board.categories),
      const SizedBox(height: 10),
      Wrap(
        spacing: 10,
        runSpacing: 10,
        children: [
          for (final f in ranked)
            _FundCard(fund: f, onTap: () => onOpen?.call(f)),
        ],
      ),
    ]);
  }
}

class _CategoryStrip extends StatelessWidget {
  final List<CategoryTile> tiles;
  const _CategoryStrip({required this.tiles});

  @override
  Widget build(BuildContext context) {
    if (tiles.isEmpty) return const SizedBox.shrink();
    return SizedBox(
      // Same 3px overflow as the tape tiles had; sized from the rendered
      // content rather than guessed.
      height: 70,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: tiles.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (context, i) => _CategoryTileCard(tile: tiles[i]),
      ),
    );
  }
}

class _CategoryTileCard extends StatelessWidget {
  final CategoryTile tile;
  const _CategoryTileCard({required this.tile});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final tone = _fundTone(context, tile.action);
    return Container(
      width: 148,
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: tone.withValues(alpha: 0.28)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(tile.category.toUpperCase(),
              style: AppTextStyles.labelXs(c.t3),
              maxLines: 1,
              overflow: TextOverflow.ellipsis),
          const SizedBox(height: 2),
          Row(children: [
            Text(
              tile.benchmarkDrawdownPct == null
                  ? '—'
                  : '-${tile.benchmarkDrawdownPct!.toStringAsFixed(1)}%',
              style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 13),
            ),
            const Spacer(),
            Text(tile.score == null ? '—' : tile.score!.toStringAsFixed(0),
                style: AppTextStyles.monoBold(tone).copyWith(fontSize: 13)),
          ]),
          const Spacer(),
          Text(tile.actionLabel.toUpperCase(),
              style: AppTextStyles.bodyBold(tone)
                  .copyWith(fontSize: 9, letterSpacing: 0.4),
              maxLines: 1,
              overflow: TextOverflow.ellipsis),
        ],
      ),
    );
  }
}

Color _fundTone(BuildContext context, String action) {
  final c = context.colors;
  return switch (action) {
    'add' => c.up,
    'attractive' => c.up,
    'watch' => c.gold,
    'wait' => c.accent,
    _ => c.t3,
  };
}

class _FundCard extends StatefulWidget {
  final FundDip fund;
  final VoidCallback? onTap;
  const _FundCard({required this.fund, this.onTap});

  @override
  State<_FundCard> createState() => _FundCardState();
}

class _FundCardState extends State<_FundCard> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final f = widget.fund;
    final tone = _fundTone(context, f.action);

    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          width: 300,
          padding: const EdgeInsets.fromLTRB(13, 11, 13, 12),
          decoration: BoxDecoration(
            color: c.bg2,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
                color: _hover ? tone.withValues(alpha: 0.5) : c.bd),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(f.schemeName,
                  style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12.5),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis),
              const SizedBox(height: 2),
              Text(f.category, style: AppTextStyles.labelXs(c.blue)),
              const SizedBox(height: 10),
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(
                  child: ScoreGauge(
                      score: f.score,
                      tone: tone,
                      lowConfidence: f.lowConfidence),
                ),
                const SizedBox(width: 10),
                // Fixed width, not intrinsic: a long benchmark label such as
                // "Silver (ETF)" made this column wider than the space the
                // Expanded had left, overflowing the card by 34px.
                SizedBox(
                  width: 148,
                  child:
                      Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  _kv(context, 'NAV',
                      f.nav == null ? '—' : formatINR(f.nav!, decimals: 2)),
                  _kv(context, 'My avg',
                      f.purchase.weightedAvgNav == null
                          ? '—'
                          : formatINR(f.purchase.weightedAvgNav!, decimals: 2)),
                  _kv(
                    context,
                    f.benchmarkLabel.isEmpty ? 'Benchmark' : f.benchmarkLabel,
                    f.benchmarkDrawdownPct == null
                        ? '—'
                        : '-${f.benchmarkDrawdownPct!.toStringAsFixed(1)}%',
                  ),
                ]),
                ),
              ]),
              const SizedBox(height: 10),
              Row(children: [
                Text(f.actionEmoji, style: const TextStyle(fontSize: 11)),
                const SizedBox(width: 5),
                Text(f.actionLabel.toUpperCase(),
                    style: AppTextStyles.bodyBold(tone)
                        .copyWith(fontSize: 11, letterSpacing: 0.5)),
                if (f.deepFallRisk) ...[
                  const SizedBox(width: 8),
                  Icon(LucideIcons.triangleAlert, size: 11, color: c.dn),
                  const SizedBox(width: 3),
                  Flexible(
                    child: Text('deep fall',
                        style: AppTextStyles.labelXs(c.dn), maxLines: 1),
                  ),
                ],
              ]),
              const SizedBox(height: 8),
              _reasonList(context, f.reasons, tone),
              if (f.nextTriggerLabel != null) ...[
                const SizedBox(height: 8),
                Row(children: [
                  Icon(LucideIcons.target, size: 10, color: c.t3),
                  const SizedBox(width: 5),
                  Flexible(
                    child: Text(
                      'Next: ${f.nextTriggerLabel} at '
                      '${f.nextTriggerNav?.toStringAsFixed(2) ?? '—'}',
                      style: AppTextStyles.captionXs(c.t3),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ]),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _kv(BuildContext context, String k, String v) {
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          Flexible(
            child: Text('$k  ',
                style: AppTextStyles.captionXs(c.t4),
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
          ),
          Text(v, style: AppTextStyles.mono(c.t1).copyWith(fontSize: 11)),
        ],
      ),
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  STOCKS
// ══════════════════════════════════════════════════════════════

/// STOCK — WHERE TO BUY?
///
/// The card leads with the fall reason rather than the score, because the
/// score cannot distinguish a discount from a collapse and the reason can. A
/// blocked holding keeps its score visible but struck through: it was
/// computed, it is real, and it is not the answer.
class StockOpportunitySection extends ConsumerWidget {
  final void Function(StockDip stock)? onOpen;

  const StockOpportunitySection({super.key, this.onOpen});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final async = ref.watch(stockDipsProvider);
    final board = async.value ?? StockDipBoard.empty;

    if (async.hasError && !async.isLoading) {
      return _loadFailed(context, 'your stocks',
          () => ref.invalidate(stockDipsProvider));
    }
    if (async.isLoading && board.isEmpty) {
      return const DenseCard(
          child: SizedBox(height: 120, child: DensePulseLoader()));
    }
    if (board.isEmpty) {
      return const DenseEmptyCard(
        icon: LucideIcons.searchX,
        title: 'No stocks to analyse yet',
        sub: 'Add equity holdings and this section will explain every fall.',
      );
    }

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _sectionHeader(context,
          icon: LucideIcons.trendingDown,
          accent: c.accent,
          title: 'STOCK — WHERE TO BUY?',
          subtitle: '${board.buyable.length} of ${board.stocks.length} '
              'worth buying · ${board.blockedCount} to avoid'),
      Wrap(
        spacing: 10,
        runSpacing: 10,
        children: [
          for (final s in board.stocks)
            _StockCard(stock: s, onTap: () => onOpen?.call(s)),
        ],
      ),
      const SizedBox(height: 8),
      Text(board.valuationNote, style: AppTextStyles.captionXs(c.t4)),
    ]);
  }
}

class _StockCard extends StatefulWidget {
  final StockDip stock;
  final VoidCallback? onTap;
  const _StockCard({required this.stock, this.onTap});

  @override
  State<_StockCard> createState() => _StockCardState();
}

class _StockCardState extends State<_StockCard> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final s = widget.stock;
    final tone = switch (s.action) {
      DipAction.accumulate || DipAction.consider => c.up,
      DipAction.watch => c.gold,
      DipAction.avoid => c.accent,
      DipAction.doNotAverage => c.dn,
    };

    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          width: 300,
          padding: const EdgeInsets.fromLTRB(13, 11, 13, 12),
          decoration: BoxDecoration(
            color: s.averagingBlocked ? c.dn.withValues(alpha: 0.05) : c.bg2,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
                color: s.averagingBlocked
                    ? c.dn.withValues(alpha: 0.4)
                    : (_hover ? tone.withValues(alpha: 0.5) : c.bd)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(children: [
                Expanded(
                  child: Text(s.name,
                      style:
                          AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12.5),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
                ),
                Text(
                  s.price == null ? '—' : formatINR(s.price!, decimals: 1),
                  style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 12.5),
                ),
              ]),
              const SizedBox(height: 2),
              Row(children: [
                Text(s.benchmarkLabel, style: AppTextStyles.labelXs(c.blue)),
                const Spacer(),
                Text(
                  s.drawdownPct == null
                      ? 'no price history'
                      : '-${s.drawdownPct!.toStringAsFixed(1)}% off high',
                  style: AppTextStyles.captionXs(c.t3),
                ),
              ]),
              const SizedBox(height: 10),
              // Expanded rather than a bare child + Spacer: a Row measures its
              // NON-flex children with unbounded width, and the score block
              // contains a Flexible, which is illegal under an unbounded
              // constraint. That threw a RenderFlex assertion on every paint
              // and cascaded into "RenderBox was not laid out".
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(child: _score(context, s, tone)),
                const SizedBox(width: 10),
                SizedBox(
                  width: 112,
                  child:
                      Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  StatusChip(
                      caption: 'FUNDAMENTALS',
                      value: s.healthLabel,
                      tone: _healthTone(context, s.health)),
                  const SizedBox(height: 4),
                  StatusChip(
                      caption: 'VALUATION',
                      value: s.valuationLabel,
                      tone: _valuationTone(context, s.valuation)),
                  const SizedBox(height: 4),
                  StatusChip(
                      caption: 'NEWS',
                      value: s.newsLabel,
                      tone: _newsTone(context, s.newsSentiment)),
                ]),
                ),
              ]),
              const SizedBox(height: 10),
              _fallReason(context, s),
              const SizedBox(height: 8),
              _reasonList(context, s.reasons, tone),
              if (s.mainRisk != null) ...[
                const SizedBox(height: 8),
                Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Icon(LucideIcons.shieldAlert, size: 11, color: c.dn),
                  const SizedBox(width: 5),
                  Expanded(
                    child: Text('Main risk: ${s.mainRisk}',
                        style: AppTextStyles.captionXs(c.dn),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis),
                  ),
                ]),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _score(BuildContext context, StockDip s, Color tone) {
    final c = context.colors;
    if (!s.averagingBlocked) {
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        ScoreGauge(
            score: s.score, tone: tone, lowConfidence: s.lowConfidence),
        const SizedBox(height: 7),
        Row(children: [
          Text(s.actionEmoji, style: const TextStyle(fontSize: 11)),
          const SizedBox(width: 5),
          Flexible(
            child: Text(
                s.corporateActionSuspected
                    ? 'CHECK BY HAND'
                    : s.actionLabel.toUpperCase(),
                style: AppTextStyles.bodyBold(tone)
                    .copyWith(fontSize: 10, letterSpacing: 0.5),
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
          ),
        ]),
      ]);
    }
    // Blocked: the score stays visible but struck through. Hiding it would
    // look like a gap in the data; leaving it plain would look like advice.
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(s.score == null ? '—' : s.score!.toStringAsFixed(0),
          style: AppTextStyles.monoBold(c.t3).copyWith(
              fontSize: 26, height: 1.0,
              decoration: TextDecoration.lineThrough)),
      const SizedBox(height: 7),
      Row(children: [
        Icon(LucideIcons.ban, size: 12, color: c.dn),
        const SizedBox(width: 5),
        Flexible(
          child: Text('DO NOT AVERAGE',
              style: AppTextStyles.bodyBold(c.dn)
                  .copyWith(fontSize: 10, letterSpacing: 0.5),
              maxLines: 1),
        ),
      ]),
    ]);
  }

  /// The most important block on the card: WHY the price fell.
  Widget _fallReason(BuildContext context, StockDip s) {
    final c = context.colors;
    final r = s.reasonForFall;
    final (label, tone) = switch (r.reason) {
      FallReason.marketWide => ('TEMPORARY · MARKET-WIDE', c.up),
      FallReason.companySoft => ('COMPANY, NO DAMAGE VISIBLE', c.gold),
      FallReason.uncertain => ('UNCERTAIN · CAUSE UNCLEAR', c.accent),
      FallReason.deterioration => ('STRUCTURAL · FUNDAMENTALS WEAK', c.dn),
      FallReason.corporateAction => ('CORPORATE ACTION', c.gold),
      FallReason.notFalling => ('NOT MEANINGFULLY DOWN', c.t2),
      FallReason.unknown => ('NOT ENOUGH INFORMATION', c.t3),
    };
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(9, 7, 9, 8),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(5),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('FALL REASON', style: AppTextStyles.captionXs(c.t4)),
        const SizedBox(height: 2),
        Row(children: [
          Text(r.emoji, style: const TextStyle(fontSize: 10)),
          const SizedBox(width: 5),
          Flexible(
            child: Text(label,
                style: AppTextStyles.bodyBold(tone)
                    .copyWith(fontSize: 10, letterSpacing: 0.4),
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
          ),
          if (r.excessDrawdownPp != null) ...[
            const Spacer(),
            Text('${r.excessDrawdownPp! >= 0 ? '+' : ''}'
                '${r.excessDrawdownPp!.toStringAsFixed(1)}pp vs sector',
                style: AppTextStyles.captionXs(c.t3)),
          ],
        ]),
      ]),
    );
  }
}

Color _healthTone(BuildContext context, String key) {
  final c = context.colors;
  return switch (key) {
    'strong' => c.up,
    'stable' => c.blue,
    'weakening' => c.accent,
    'deteriorating' => c.dn,
    _ => c.t3,
  };
}

Color _valuationTone(BuildContext context, String key) {
  final c = context.colors;
  return switch (key) {
    'cheap' => c.up,
    'fair' => c.gold,
    'expensive' => c.dn,
    _ => c.t3,
  };
}

Color _newsTone(BuildContext context, String key) {
  final c = context.colors;
  return switch (key) {
    'positive' => c.up,
    'neutral' => c.gold,
    'concern' => c.accent,
    'major_risk' => c.dn,
    _ => c.t3,
  };
}
