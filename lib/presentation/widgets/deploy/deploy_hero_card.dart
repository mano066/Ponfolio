import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/deploy_models.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/presentation/widgets/deploy/deploy_dialogs.dart';
import 'package:aiei_wealth/providers/deploy_provider.dart';

const _splitCols = <DenseCol>[
  DenseCol('WHERE THE MONEY GOES', 30, numeric: false),
  DenseCol('AMOUNT', 14),
  DenseCol('SHARE', 12),
  DenseCol('UNITS', 14),
  DenseCol('WHY THIS ONE', 30, numeric: false),
];

const _splitColsNarrow = <DenseCol>[
  DenseCol('WHERE THE MONEY GOES', 34, numeric: false),
  DenseCol('AMOUNT', 16),
  DenseCol('WHY THIS ONE', 40, numeric: false),
];

const _presets = [10000.0, 20000.0, 50000.0, 100000.0];

/// "I have spare money today — where should it go?"
///
/// The amount lives in [deployAmountProvider], which the board watches, so
/// committing a number re-proposes the whole split server-side.
class DeployHeroCard extends ConsumerStatefulWidget {
  final DeployBoard board;
  const DeployHeroCard({super.key, required this.board});

  @override
  ConsumerState<DeployHeroCard> createState() => _DeployHeroCardState();
}

class _DeployHeroCardState extends ConsumerState<DeployHeroCard> {
  late final TextEditingController _amt;
  late final FocusNode _focus;

  @override
  void initState() {
    super.initState();
    final current = ref.read(deployAmountProvider);
    _amt = TextEditingController(
        text: current > 0 ? current.toStringAsFixed(0) : '');
    _focus = FocusNode()
      // Commit on blur as well as on Enter — the same idiom as the editable
      // grid's numeric cells. Clicking straight from the field to the Record
      // button must not silently discard what was typed.
      ..addListener(() {
        if (!_focus.hasFocus) _commit();
      });
  }

  @override
  void dispose() {
    _amt.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _commit() {
    final parsed = double.tryParse(_amt.text.replaceAll(',', '').trim()) ?? 0;
    if (parsed != ref.read(deployAmountProvider)) {
      ref.read(deployAmountProvider.notifier).set(parsed);
    }
  }

  void _setPreset(double v) {
    _amt.text = v.toStringAsFixed(0);
    ref.read(deployAmountProvider.notifier).set(v);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final board = widget.board;
    final amount = ref.watch(deployAmountProvider);
    final typed = double.tryParse(_amt.text.replaceAll(',', '').trim()) ?? 0;
    final uncommitted = typed != amount;

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(
          context,
          icon: LucideIcons.wallet,
          accent: c.blue,
          title: 'Extra Money Today',
          subtitle: board.indicesSummary.isEmpty
              ? 'Type an amount to see where it should go'
              : board.indicesSummary,
          trailing: AppBadge(
            text: _moodLabel(board.marketMood),
            variant: _moodVariant(board.marketMood),
          ),
        ),
        SectionExplainer(
          accent: c.blue,
          question: 'I have spare money today. Where should it go?',
          reading:
              'Type the amount. The app splits it across the holdings that '
              'look cheapest right now.',
          rules: const [
            'The split follows the score in the table below. A higher score '
                'gets a bigger share.',
            'Anything already at or above your target share is skipped, even '
                'if its price has fallen.',
            'Each fund buy is at least ₹500. Stocks are bought in whole '
                'shares. Anything too small to place is shown as left over.',
            'Nothing is sent to your broker. Recording a buy only updates the '
                'numbers inside this app.',
          ],
          action:
              'Place the buy in your broker or AMC app first. Then press '
              '"Record these buys" here so your average cost and returns stay '
              'correct.',
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            _amountRow(context, uncommitted),
            const SizedBox(height: 14),
            AnimatedSize(
              duration: const Duration(milliseconds: 180),
              alignment: Alignment.topCenter,
              child: _result(context, board, amount),
            ),
          ]),
        ),
      ]),
    );
  }

  Widget _amountRow(BuildContext context, bool uncommitted) {
    final c = context.colors;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(
        spacing: 14,
        runSpacing: 10,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Text('I HAVE', style: AppTextStyles.labelXs(c.t3)),
          SizedBox(
            width: 200,
            child: TextField(
              controller: _amt,
              focusNode: _focus,
              style: AppTextStyles.mono(c.t1).copyWith(fontSize: 20),
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: denseFieldDecoration(context,
                  hint: '20000', prefix: '₹ ', focusColor: c.blue),
              onSubmitted: (_) => _commit(),
              onChanged: (_) => setState(() {}),
            ),
          ),
          Text('TO PUT IN TODAY', style: AppTextStyles.labelXs(c.t3)),
          for (final p in _presets)
            DFilterChip(
              label: '₹${formatCompact(p)}',
              selected: false,
              onTap: () => setState(() => _setPreset(p)),
            ),
          DFilterChip(
            label: 'CLEAR',
            selected: false,
            tone: c.t3,
            onTap: () => setState(() {
              _amt.clear();
              ref.read(deployAmountProvider.notifier).clear();
            }),
          ),
        ],
      ),
      if (uncommitted) ...[
        const SizedBox(height: 8),
        Text('Press Enter to see the split.',
            style: AppTextStyles.captionXs(c.gold)),
      ],
    ]);
  }

  Widget _result(BuildContext context, DeployBoard board, double amount) {
    final c = context.colors;

    if (amount <= 0) {
      return Row(children: [
        Icon(LucideIcons.arrowUpLeft, size: 15, color: c.t3),
        const SizedBox(width: 8),
        Expanded(
          child: Text('Type an amount above, or tap one of the buttons.',
              style: AppTextStyles.bodySmall(c.t3)),
        ),
      ]);
    }

    final s = board.suggestion;
    if (!s.hasSplits) {
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: c.goldBg,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: c.gold.withValues(alpha: 0.35)),
        ),
        child: Text(_noSplitMessage(s),
            style: AppTextStyles.bodySmall(c.t2)),
      );
    }

    return LayoutBuilder(builder: (context, box) {
      final narrow = box.maxWidth < 900;
      final cols = narrow ? _splitColsNarrow : _splitCols;
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseColumnHeader(context, cols),
        for (final (i, split) in s.splits.indexed)
          DenseRow(
            cols: cols,
            alt: i.isOdd,
            cells: _cells(context, split, s.allocated, narrow),
          ),
        _footer(context, s),
      ]);
    });
  }

  List<Widget> _cells(
      BuildContext context, DeploySplit split, double allocated, bool narrow) {
    final c = context.colors;
    final isFund = split.kind == HoldingKind.fund;
    final instrument = DInstrument(
      symbol: split.label,
      sub: kindLabel(split.kind),
      up: true,
      spine: isFund ? c.blue : c.cyan,
      ellipsis: true,
    );
    final amount = denseNum(context, formatINR(split.amount), c.t1, bold: true);
    final why = Text(
      split.reason.isEmpty ? '—' : split.reason,
      style: AppTextStyles.bodySmall(c.t2),
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
    );

    if (narrow) return [instrument, amount, why];

    return [
      instrument,
      amount,
      DWeightCell(
        pct: allocated > 0 ? split.amount / allocated * 100 : 0,
        color: c.blue,
      ),
      denseNum(context, split.unitsLabel, c.t2),
      why,
    ];
  }

  Widget _footer(BuildContext context, DeploySuggestion s) {
    final c = context.colors;
    final busy = ref.watch(deployBusyProvider).contains('hero');
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 9, 14, 9),
      decoration: BoxDecoration(
        color: c.bg3,
        border: Border(top: BorderSide(color: c.bd)),
      ),
      child: Wrap(
        spacing: 16,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          denseFootLabel(context, 'TOTAL · ${s.splits.length} BUYS'),
          Text(formatINR(s.allocated),
              style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 13)),
          if (s.unallocated > 0)
            Text('${formatINR(s.unallocated)} left over, too small to place',
                style: AppTextStyles.captionXs(c.gold)),
          HeaderButton(
            icon: const Icon(LucideIcons.check, size: 13, color: Colors.white),
            text: 'Record these buys',
            solidColor: c.up,
            loading: busy,
            onTap: busy ? null : () => _openRecord(s.splits),
          ),
        ],
      ),
    );
  }

  void _openRecord(List<DeploySplit> splits) {
    showDialog<void>(
      context: context,
      builder: (_) => RecordBuyDialog(
        buys: splits,
        title: 'Record these buys',
        busyKey: 'hero',
      ),
    );
  }

  String _noSplitMessage(DeploySuggestion s) => switch (s.unallocatedReason) {
        'amount_below_min_ticket' =>
          'That amount is too small to place. You need at least '
              '${formatINR(s.minTicketNeeded ?? 500)} to buy anything today.',
        _ => 'Nothing looks cheap enough to add to right now. Everything is '
            'near its peak, above your average cost, or already at your '
            'target share.',
      };

  String _moodLabel(String mood) => switch (mood) {
        'deep-fall' => 'BIG FALL',
        'falling' => 'FALLING',
        'soft' => 'SOFT',
        'near-high' => 'NEAR HIGH',
        _ => 'UNKNOWN',
      };

  BadgeVariant _moodVariant(String mood) => switch (mood) {
        'deep-fall' || 'falling' => BadgeVariant.dn,
        'soft' => BadgeVariant.gold,
        'near-high' => BadgeVariant.up,
        _ => BadgeVariant.hold,
      };
}
