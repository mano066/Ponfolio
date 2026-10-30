import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/dip_models.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/providers/deploy_provider.dart';

/// Fund dip panel — "at what NAV is this worth adding to?".
///
/// Deliberately answers with LEVELS rather than a score. The deploy board
/// already ranks and allocates; a second score here, built from overlapping
/// inputs, would give the dashboard two different answers to the same
/// question. What a decision actually needs and does not have is the price at
/// which to act, and the evidence that the price means anything.
///
/// Every zone therefore carries what ten years of that benchmark measured at
/// that depth — including, often, that the depth did NOT beat simply buying on
/// a random day. A zone that cannot argue for itself says so.
class FundDipCard extends ConsumerWidget {
  const FundDipCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final async = ref.watch(fundDipsProvider);
    final board = async.value ?? FundDipBoard.empty;

    if (async.isLoading && board.isEmpty) {
      return const DenseCard(child: DensePulseLoader());
    }
    if (board.isEmpty) {
      return const DenseEmptyCard(
        icon: LucideIcons.layers,
        title: 'No funds to analyse yet',
        sub: 'Add mutual funds and this panel will work out the NAV levels '
            'worth adding at.',
      );
    }

    final inZone = board.funds.where((f) => f.inABuyZone).length;

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(
          context,
          icon: LucideIcons.layers,
          accent: c.blue,
          title: 'Funds — Where to Add',
          subtitle: inZone > 0
              ? '${board.funds.length} funds · $inZone already in a buy zone'
              : '${board.funds.length} funds · none in a buy zone yet',
          trailing: inZone > 0
              ? AppBadge(text: '$inZone IN ZONE', variant: BadgeVariant.up)
              : null,
        ),
        SectionExplainer(
          accent: c.blue,
          question: 'At what NAV should I put more into each fund?',
          reading: 'Each fund with its benchmark\'s fall, the NAV levels worth '
              'adding at, and what a decade of history says about each level.',
          rules: const [
            'Zones are cut from the fund\'s own NAV peak — 10%, 15% and 20% '
                'below it. They are NOT cut from what you paid.',
            'Each zone carries its evidence. "Beat buying on a random day" is '
                'the only test that matters; a zone that did not beat it is '
                'shown saying so.',
            '"Too few episodes" means the depth happened once or twice in ten '
                'years. That is an anecdote, not a reason.',
            'Your own purchase range is context only. Below your average does '
                'NOT mean cheap — the benchmark drawdown is what says that.',
          ],
          action: 'Wait for a fund to reach a zone whose evidence is both '
              'reliable and positive. Keep the SIP running regardless.',
        ),
        ...board.funds.map((f) => _FundBlock(fund: f)),
      ]),
    );
  }
}

class _FundBlock extends StatelessWidget {
  final FundDip fund;
  const _FundBlock({required this.fund});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 11, 14, 12),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: c.bd.withValues(alpha: 0.6))),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _header(context),
        const SizedBox(height: 9),
        _zones(context),
        if (fund.purchase.hasHistory) ...[
          const SizedBox(height: 9),
          _purchaseRow(context),
        ],
        if (fund.nextTriggerLabel != null) ...[
          const SizedBox(height: 7),
          _trigger(context),
        ],
      ]),
    );
  }

  Widget _header(BuildContext context) {
    final c = context.colors;
    final dd = fund.benchmarkDrawdownPct;
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(fund.schemeName,
              style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12.5),
              maxLines: 1,
              overflow: TextOverflow.ellipsis),
          const SizedBox(height: 2),
          Row(children: [
            Text(fund.benchmarkLabel,
                style: AppTextStyles.labelXs(c.blue), maxLines: 1),
            if (dd != null) ...[
              Text('  ·  ', style: AppTextStyles.labelXs(c.t3)),
              Text('index ${dd.toStringAsFixed(1)}% off its high',
                  style: AppTextStyles.labelXs(c.t3), maxLines: 1),
            ],
          ]),
        ]),
      ),
      const SizedBox(width: 10),
      Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
        Text(fund.nav == null ? '—' : formatINR(fund.nav!, decimals: 2),
            style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 13)),
        Text('NAV', style: AppTextStyles.labelXs(c.t3)),
      ]),
    ]);
  }

  Widget _zones(BuildContext context) {
    if (fund.zones.isEmpty) {
      return Text('Not enough NAV history to place buy zones.',
          style: AppTextStyles.labelXs(context.colors.t3));
    }
    return Column(
      children: [
        for (final z in fund.zones)
          Padding(
            padding: const EdgeInsets.only(bottom: 3),
            child: _ZoneRow(zone: z, weakAnchor: fund.peakIsPurchaseHigh),
          ),
      ],
    );
  }

  /// The user's own buying range, plus the caution that keeps it from being
  /// read as a valuation.
  Widget _purchaseRow(BuildContext context) {
    final c = context.colors;
    final p = fund.purchase;
    String nav(double? v) => v == null ? '—' : v.toStringAsFixed(2);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 7),
      decoration: BoxDecoration(
        color: c.bg3,
        borderRadius: BorderRadius.circular(5),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(spacing: 14, runSpacing: 3, children: [
          _stat(context, 'YOUR LOW', nav(p.lowestBuyNav)),
          _stat(context, 'YOUR AVG', nav(p.weightedAvgNav)),
          _stat(context, 'YOUR HIGH', nav(p.highestBuyNav)),
          _stat(context, 'HIGH/LOW',
              p.highLowRatio == null ? '—' : '${p.highLowRatio!.toStringAsFixed(2)}x'),
          _stat(context, 'BUYS', '${p.buys}'),
        ]),
        const SizedBox(height: 4),
        Text(p.positionLabel,
            style: AppTextStyles.labelXs(c.t2), maxLines: 1),
        if (p.caution != null)
          Padding(
            padding: const EdgeInsets.only(top: 3),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(LucideIcons.alertTriangle, size: 10, color: c.gold),
              const SizedBox(width: 4),
              Expanded(
                child: Text(p.caution!,
                    style: AppTextStyles.labelXs(c.gold)),
              ),
            ]),
          ),
      ]),
    );
  }

  Widget _stat(BuildContext context, String label, String value) {
    final c = context.colors;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: AppTextStyles.labelXs(c.t3)),
      Text(value, style: AppTextStyles.mono(c.t1).copyWith(fontSize: 11)),
    ]);
  }

  Widget _trigger(BuildContext context) {
    final c = context.colors;
    return Row(children: [
      Icon(LucideIcons.target, size: 11, color: c.accent),
      const SizedBox(width: 5),
      Expanded(
        child: Text(
          'Next: ${fund.nextTriggerLabel} at '
          '${fund.nextTriggerNav?.toStringAsFixed(2) ?? '—'}'
          '${fund.nextTriggerFallPct == null ? '' : ' — a '
              '${fund.nextTriggerFallPct!.toStringAsFixed(1)}% fall from here'}',
          style: AppTextStyles.labelXs(c.accent),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ),
    ]);
  }
}

class _ZoneRow extends StatelessWidget {
  final BuyZone zone;

  /// True when the peak behind this level is only the user's own highest
  /// purchase rather than the fund's real NAV peak.
  final bool weakAnchor;

  const _ZoneRow({required this.zone, required this.weakAnchor});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final ev = zone.evidence;

    // Colour follows the EVIDENCE, not the depth. A deeper zone that fired
    // twice in a decade is not a stronger signal than a shallower one that
    // fired twelve times and beat the baseline, and painting depth alone
    // would say the opposite.
    final tone = !ev.tested
        ? c.t3
        : !ev.reliable
            ? c.t3
            : ev.supportsBuying
                ? c.up
                : c.dn;

    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      SizedBox(
        width: 12,
        child: Icon(
          zone.reached ? LucideIcons.checkCircle2 : LucideIcons.circle,
          size: 10,
          color: zone.reached ? c.accent : c.t3,
        ),
      ),
      const SizedBox(width: 5),
      SizedBox(
        width: 96,
        child: Text('${zone.label} (−${zone.depthPct.toStringAsFixed(0)}%)',
            style: AppTextStyles.labelXs(zone.reached ? c.t1 : c.t2),
            maxLines: 1,
            overflow: TextOverflow.ellipsis),
      ),
      SizedBox(
        width: 68,
        child: Text(zone.navAtOrBelow.toStringAsFixed(2),
            style: AppTextStyles.mono(zone.reached ? c.accent : c.t2)
                .copyWith(fontSize: 11),
            textAlign: TextAlign.right),
      ),
      const SizedBox(width: 9),
      Expanded(
        child: Row(children: [
          if (ev.supportsBuying)
            Icon(LucideIcons.check, size: 10, color: tone)
          else if (ev.tested && ev.reliable)
            Icon(LucideIcons.x, size: 10, color: tone)
          else
            Icon(LucideIcons.helpCircle, size: 10, color: tone),
          const SizedBox(width: 4),
          Expanded(
            child: Text(
              weakAnchor
                  ? '${ev.note}  (level based on your own buying range, not a '
                      'true NAV peak)'
                  : ev.note,
              style: AppTextStyles.labelXs(tone),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ]),
      ),
    ]);
  }
}
