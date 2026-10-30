import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/deploy_models.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/presentation/widgets/deploy/deploy_dialogs.dart';
import 'package:aiei_wealth/providers/deploy_provider.dart';

const _sipCols = <DenseCol>[
  DenseCol('FUND / STOCK', 34, numeric: false),
  DenseCol('DAY', 9),
  DenseCol('PLANNED', 15),
  // Not "DONE" — the status badge already uses that word for a different
  // meaning, and two DONEs in one row is a real ambiguity.
  DenseCol('PAID', 15),
  DenseCol('STATUS', 13, numeric: false),
  DenseCol('', 14, numeric: false),
];

const _sipColsNarrow = <DenseCol>[
  DenseCol('FUND / STOCK', 40, numeric: false),
  DenseCol('PLANNED', 20),
  DenseCol('STATUS', 20, numeric: false),
  DenseCol('', 20, numeric: false),
];

/// "Did I do this month's SIP?" — one line per fund/stock, each with its own
/// amount and its own due day, checked against real recorded transactions.
class SipChecklistCard extends ConsumerWidget {
  final DeployBoard board;
  const SipChecklistCard({super.key, required this.board});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final plan = board.sipPlan;

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(
          context,
          icon: LucideIcons.calendarCheck,
          accent: c.gold,
          title: "This Month's Plan",
          subtitle: plan.hasPlan
              ? '${_monthName(plan.month)} · ${plan.doneCount} of '
                  '${plan.totalCount} done'
              : 'No monthly plan set up yet',
          trailing: HeaderButton(
            icon: const Icon(LucideIcons.settings2, size: 13),
            text: plan.hasPlan ? 'Edit plan' : 'Set up plan',
            onTap: () => showDialog<void>(
              context: context,
              builder: (_) => const DeployPlanDialog(),
            ),
          ),
        ),
        SectionExplainer(
          accent: c.gold,
          question: 'Did I do this month\'s SIP?',
          reading:
              'Your monthly plan, one line for each fund or stock, each with '
              'its own date and its own amount.',
          rules: const [
            'DUE means the date has not come yet this month.',
            'DUE NOW means the date has arrived.',
            'OVERDUE means the date has passed and nothing has been recorded.',
            'PARTIAL means some money went in, but less than you planned.',
            'DONE means the full amount for this month is recorded. This is '
                'read from your real transactions, so a SIP the AMC debited '
                'counts even if you did not record it here.',
          ],
          action:
              'Clear every OVERDUE line first. Only put extra money to work '
              'after this month\'s plan is done.',
        ),
        if (!plan.hasPlan)
          _emptyState(context)
        else ...[
          _budgetRail(context, plan),
          LayoutBuilder(builder: (context, box) {
            final narrow = box.maxWidth < 640;
            final cols = narrow ? _sipColsNarrow : _sipCols;
            return Column(children: [
              denseColumnHeader(context, cols, leadingWidth: 7),
              for (final (i, leg) in plan.legs.indexed)
                _LegRow(leg: leg, cols: cols, alt: i.isOdd, narrow: narrow),
            ]);
          }),
        ],
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
          child: Text(
            'The dates are the ones you set. A line goes overdue three days '
            'after its date if nothing has been recorded against it.',
            style: AppTextStyles.captionXs(c.t4),
          ),
        ),
      ]),
    );
  }

  Widget _emptyState(BuildContext context) {
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 4),
      child: Text(
        'Set up your monthly plan to track it here — one line per fund or '
        'stock, each with its own amount and the day of the month it is due.',
        style: AppTextStyles.bodySmall(c.t3),
      ),
    );
  }

  Widget _budgetRail(BuildContext context, SipPlanStatus plan) {
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text('${formatINR(plan.deployedTotal)} of '
              '${formatINR(plan.budgetTotal)} done',
              style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 13)),
          const Spacer(),
          if (plan.remaining > 0)
            Text('${formatINR(plan.remaining)} still to go',
                style: AppTextStyles.captionXs(c.t3)),
        ]),
        const SizedBox(height: 7),
        DStackedBar(
          segments: [(plan.deployedTotal, c.gold)],
          total: plan.budgetTotal,
          height: 8,
        ),
      ]),
    );
  }

  String _monthName(String ym) {
    final parts = ym.split('-');
    if (parts.length != 2) return ym;
    const names = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December'
    ];
    final m = int.tryParse(parts[1]) ?? 0;
    return m >= 1 && m <= 12 ? '${names[m - 1]} ${parts[0]}' : ym;
  }
}

class _LegRow extends ConsumerWidget {
  final SipLeg leg;
  final List<DenseCol> cols;
  final bool alt;
  final bool narrow;

  const _LegRow({
    required this.leg,
    required this.cols,
    required this.alt,
    required this.narrow,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final tone = _statusColor(context, leg.status);
    final busyKey = 'sip:${leg.key}';
    final busy = ref.watch(deployBusyProvider).contains(busyKey);

    final instrument = DInstrument(
      symbol: leg.label,
      sub: leg.kind == HoldingKind.fund ? 'Fund · monthly' : 'Stock · monthly',
      up: leg.status == SipStatus.done,
      spine: tone,
      ellipsis: true,
    );

    final planned = denseNum(context, formatINR(leg.amount), c.t1);
    // Status uses AppBadge, not DSignalBadge: that badge's keyword table only
    // knows market verdicts (BUY/SELL), so calendar words fall through to grey.
    final status = Align(
      alignment: Alignment.centerLeft,
      child: AppBadge(
        text: sipStatusLabel(leg.status),
        variant: _statusVariant(leg.status),
      ),
    );
    final action = _action(context, ref, busy, busyKey);

    final cells = narrow
        ? [instrument, planned, status, action]
        : [
            instrument,
            denseNum(context, _ordinal(leg.dueDay), c.t2),
            planned,
            denseNum(context, formatINR(leg.deployedThisMonth),
                leg.deployedThisMonth > 0 ? c.up : c.t4),
            status,
            action,
          ];

    return DenseRow(
      cols: cols,
      alt: alt,
      leadingWidth: 7,
      // The status spine goes in the leading gutter rather than via
      // DenseRow(highlighted:), which paints a blue tint — the wrong colour
      // for "overdue".
      leading: Container(
        width: 3,
        height: 22,
        decoration: BoxDecoration(
          color: tone,
          borderRadius: BorderRadius.circular(2),
        ),
      ),
      cells: cells,
    );
  }

  Widget _action(
      BuildContext context, WidgetRef ref, bool busy, String busyKey) {
    final c = context.colors;
    if (leg.status == SipStatus.done) {
      return Align(
        alignment: Alignment.centerLeft,
        child: Icon(LucideIcons.check, size: 15, color: c.up),
      );
    }
    if (leg.status == SipStatus.inactive || leg.missingHolding) {
      return const SizedBox.shrink();
    }
    final remaining = leg.shortfall > 0 ? leg.shortfall : leg.amount;
    return Align(
      alignment: Alignment.centerLeft,
      child: HeaderButton(
        icon: const Icon(LucideIcons.plus, size: 12),
        text: 'Record',
        loading: busy,
        onTap: busy
            ? null
            : () => showDialog<void>(
                  context: context,
                  builder: (_) => RecordBuyDialog(
                    title: 'Record ${leg.label}',
                    busyKey: busyKey,
                    buys: [
                      DeploySplit(
                        kind: leg.kind,
                        key: leg.key,
                        label: leg.label,
                        amount: remaining,
                        reason: 'This month\'s planned amount',
                      )
                    ],
                  ),
                ),
      ),
    );
  }

  Color _statusColor(BuildContext context, SipStatus s) {
    final c = context.colors;
    return switch (s) {
      SipStatus.done => c.up,
      SipStatus.partial => c.blue,
      SipStatus.due => c.gold,
      SipStatus.overdue => c.dn,
      SipStatus.scheduled => c.t3,
      _ => c.t4,
    };
  }

  BadgeVariant _statusVariant(SipStatus s) => switch (s) {
        SipStatus.done => BadgeVariant.up,
        SipStatus.partial => BadgeVariant.blue,
        SipStatus.due => BadgeVariant.gold,
        SipStatus.overdue => BadgeVariant.dn,
        _ => BadgeVariant.hold,
      };

  String _ordinal(int d) {
    if (d >= 11 && d <= 13) return '${d}th';
    return switch (d % 10) {
      1 => '${d}st',
      2 => '${d}nd',
      3 => '${d}rd',
      _ => '${d}th',
    };
  }
}
