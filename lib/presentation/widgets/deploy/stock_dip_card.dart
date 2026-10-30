import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/dip_models.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/providers/deploy_provider.dart';

/// Stock dip panel — "is this a discount, or a company falling apart?".
///
/// The column that earns this card its space is **Why**, not the score. A dip
/// score can be pushed to 84 by a collapsing price alone, and the portfolio
/// contains a live example: a holding 66% off its high with a score in the
/// eighties that must not be bought. So the verdict and its reason are given
/// more room than the number, and a blocked holding is visually separated from
/// the ones that are merely unattractive.
class StockDipCard extends ConsumerStatefulWidget {
  const StockDipCard({super.key});

  @override
  ConsumerState<StockDipCard> createState() => _StockDipCardState();
}

class _StockDipCardState extends ConsumerState<StockDipCard> {
  bool _showAll = false;

  // DenseRow lays cells out as bare Expanded flexes with no gap between them,
  // so a right-aligned numeric column sitting next to a left-aligned text one
  // collides — on screen the header read "SCOREWHY IT IS DOWN" and the cells
  // ran together as "40% confNo price history for this holding." The empty
  // column is the fix that works for the header and the body at once, since
  // denseColumnHeader has no per-column padding to reach for.
  static const _cols = [
    DenseCol('STOCK', 22, numeric: false),
    DenseCol('PRICE', 12),
    DenseCol('OFF HIGH', 12),
    DenseCol('VS INDEX', 12),
    DenseCol('SCORE', 10),
    DenseCol('', 2, numeric: false),
    DenseCol('WHY IT IS DOWN', 32, numeric: false),
  ];

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final async = ref.watch(stockDipsProvider);
    final board = async.value ?? StockDipBoard.empty;

    if (async.isLoading && board.isEmpty) {
      return const DenseCard(child: DensePulseLoader());
    }
    if (board.isEmpty) {
      return const DenseEmptyCard(
        icon: LucideIcons.searchX,
        title: 'No stock analysis yet',
        sub: 'Add equity holdings and the dip panel will explain every '
            'fall it finds.',
      );
    }

    final shown = _showAll ? board.stocks : board.stocks.take(8).toList();

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(
          context,
          icon: LucideIcons.trendingDown,
          accent: c.accent,
          title: 'Stocks — Buy the Dip?',
          subtitle: _subtitle(board),
          trailing: board.blockedCount > 0
              ? AppBadge(
                  text: '${board.blockedCount} BLOCKED',
                  variant: BadgeVariant.dn,
                )
              : null,
        ),
        SectionExplainer(
          accent: c.accent,
          question: 'Which of these falls are opportunities?',
          reading: 'Every holding, how far it has fallen, how much of that '
              'fall its own index explains, and a verdict.',
          rules: const [
            'VS INDEX is the number that matters. It is how much worse than '
                'its own sector the stock has fallen. Near zero means the '
                'market did this, not the company.',
            'A red DO NOT AVERAGE is a hard block from the fundamentals — '
                'shrinking revenue, shrinking earnings, losses or heavy debt. '
                'It overrides the score, which a collapsing price inflates.',
            'CHECK BY HAND means a split or demerger sits in the price '
                'history, so the fall and the year-on-year figures are not '
                'comparing like with like. No verdict is possible.',
            'A score with a low confidence is one loud factor, not a '
                'conclusion. Nothing is recommended without a known price.',
          ],
          action: 'Add only to the holdings whose fall its market explains. '
              'Leave the blocked ones alone until the earnings recover, and '
              'check the split-affected ones by hand before doing anything.',
        ),
        denseColumnHeader(context, _cols),
        ...shown.asMap().entries.map((e) => DenseRow(
              cols: _cols,
              alt: e.key.isOdd,
              highlighted: e.value.averagingBlocked,
              cells: _cells(context, e.value),
            )),
        if (!_showAll && board.stocks.length > 8)
          _moreButton(context, board.stocks.length - 8),
        _footNote(context, board),
      ]),
    );
  }

  String _subtitle(StockDipBoard board) {
    final buyable = board.buyable.length;
    final parts = <String>['${board.stocks.length} holdings'];
    if (buyable > 0) parts.add('$buyable worth adding to');
    if (board.blockedCount > 0) parts.add('${board.blockedCount} to avoid');
    if (board.corporateActionCount > 0) {
      parts.add('${board.corporateActionCount} need a manual check');
    }
    return parts.join(' · ');
  }

  List<Widget> _cells(BuildContext context, StockDip s) {
    final c = context.colors;
    return [
      // Name + the instruction, which belongs next to the name rather than at
      // the far right where it would be read last.
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(s.name,
            style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12),
            maxLines: 1,
            overflow: TextOverflow.ellipsis),
        const SizedBox(height: 2),
        _actionChip(context, s),
      ]),
      s.price == null
          ? _unknown(context, 'no price')
          : denseNum(context, formatINR(s.price!, decimals: 1), c.t1),
      s.drawdownPct == null
          ? _unknown(context, '—')
          // A fall is the opportunity here, so it is NOT painted red the way
          // denseDelta would paint it. Depth is emphasis, not alarm.
          : denseSignedNum(context, -s.drawdownPct!, _depthColor(context, s),
              decimals: 1),
      _excessCell(context, s),
      _scoreCell(context, s),
      const SizedBox.shrink(),
      _whyCell(context, s),
    ];
  }

  /// How much worse than its own benchmark the stock has fallen.
  ///
  /// Rendered as the headline discriminator: near zero is reassuring (green),
  /// a large positive is the company's own doing (amber/red).
  Widget _excessCell(BuildContext context, StockDip s) {
    final c = context.colors;
    final excess = s.reasonForFall.excessDrawdownPp;
    if (excess == null) {
      return _unknown(context, 'no bench');
    }
    final colour = excess <= 4
        ? c.up
        : excess >= 15
            ? c.dn
            : c.gold;
    return Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
      denseSignedNum(context, excess, colour, decimals: 1, suffix: 'pp'),
      if (s.benchmarkDrawdownPct != null)
        Text('${s.benchmarkLabel} ${s.benchmarkDrawdownPct!.toStringAsFixed(1)}%',
            style: AppTextStyles.labelXs(c.t3),
            textAlign: TextAlign.right,
            maxLines: 1,
            overflow: TextOverflow.ellipsis),
    ]);
  }

  Widget _scoreCell(BuildContext context, StockDip s) {
    final c = context.colors;
    if (s.score == null) return _unknown(context, '—');
    // A blocked holding's score is struck through: it was computed, it is
    // real, and it is not the answer. Hiding it would look like a gap.
    final blocked = s.averagingBlocked;
    return Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
      Text(
        s.score!.toStringAsFixed(0),
        style: AppTextStyles.monoBold(blocked ? c.t3 : c.t1).copyWith(
          fontSize: 13,
          decoration: blocked ? TextDecoration.lineThrough : null,
        ),
        textAlign: TextAlign.right,
      ),
      if (s.lowConfidence)
        Text('${s.confidence.toStringAsFixed(0)}% conf',
            style: AppTextStyles.labelXs(c.gold),
            textAlign: TextAlign.right,
            maxLines: 1),
    ]);
  }

  Widget _whyCell(BuildContext context, StockDip s) {
    final c = context.colors;
    final r = s.reasonForFall;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Text(r.emoji, style: const TextStyle(fontSize: 11)),
        const SizedBox(width: 4),
        Flexible(
          child: Text(r.label,
              style: AppTextStyles.bodyBold(_reasonColor(context, r.reason))
                  .copyWith(fontSize: 11),
              maxLines: 1,
              overflow: TextOverflow.ellipsis),
        ),
      ]),
      if (r.deteriorationFlags.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 2),
          child: Text(r.deteriorationFlags.join(' · '),
              style: AppTextStyles.labelXs(c.dn),
              maxLines: 2,
              overflow: TextOverflow.ellipsis),
        )
      else if (r.why.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 2),
          child: Text(r.why,
              style: AppTextStyles.labelXs(c.t3),
              maxLines: 2,
              overflow: TextOverflow.ellipsis),
        ),
      if (r.severeHeadlines.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 2),
          child: Row(children: [
            Icon(LucideIcons.newspaper, size: 10, color: c.gold),
            const SizedBox(width: 3),
            Flexible(
              child: Text(r.severeHeadlines.first,
                  style: AppTextStyles.labelXs(c.gold),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
            ),
          ]),
        ),
    ]);
  }

  Widget _actionChip(BuildContext context, StockDip s) {
    final variant = switch (s.action) {
      DipAction.accumulate => BadgeVariant.up,
      DipAction.consider => BadgeVariant.up,
      DipAction.watch => BadgeVariant.hold,
      DipAction.avoid => BadgeVariant.gold,
      DipAction.doNotAverage => BadgeVariant.dn,
    };
    final text = s.corporateActionSuspected
        ? 'CHECK BY HAND'
        : s.actionLabel.toUpperCase();
    return AppBadge(text: text, variant: variant, fontSize: 8);
  }

  Color _depthColor(BuildContext context, StockDip s) {
    final c = context.colors;
    if (s.averagingBlocked) return c.dn;
    final dd = s.drawdownPct ?? 0;
    if (dd >= 20) return c.accent;
    if (dd >= 10) return c.blue;
    return c.t2;
  }

  Color _reasonColor(BuildContext context, FallReason r) {
    final c = context.colors;
    return switch (r) {
      FallReason.marketWide => c.up,
      FallReason.companySoft => c.gold,
      FallReason.uncertain => c.gold,
      FallReason.deterioration => c.dn,
      FallReason.corporateAction => c.gold,
      FallReason.notFalling => c.t2,
      FallReason.unknown => c.t3,
    };
  }

  Widget _unknown(BuildContext context, String text) => Text(
        text,
        style: AppTextStyles.labelXs(context.colors.t3),
        textAlign: TextAlign.right,
        maxLines: 1,
      );

  Widget _moreButton(BuildContext context, int more) {
    final c = context.colors;
    return InkWell(
      onTap: () => setState(() => _showAll = true),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(vertical: 11),
        decoration:
            BoxDecoration(border: Border(top: BorderSide(color: c.bd))),
        child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          Text('Show $more more',
              style: AppTextStyles.bodyBold(c.accent).copyWith(fontSize: 12)),
          const SizedBox(width: 4),
          Icon(LucideIcons.chevronDown, size: 14, color: c.accent),
        ]),
      ),
    );
  }

  /// States the one metric the dashboard promises and cannot deliver.
  ///
  /// A silently missing "valuation vs its own history" column reads as a bug
  /// and, worse, leaves the user assuming valuation was considered.
  Widget _footNote(BuildContext context, StockDipBoard board) {
    final c = context.colors;
    if (board.valuationNote.isEmpty) return const SizedBox.shrink();
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
      decoration: BoxDecoration(
        color: c.bg3,
        border: Border(top: BorderSide(color: c.bd)),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(LucideIcons.info, size: 12, color: c.t3),
        const SizedBox(width: 6),
        Expanded(
          child: Text(board.valuationNote,
              style: AppTextStyles.labelXs(c.t3)),
        ),
      ]),
    );
  }
}
