import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/dip_models.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/providers/deploy_provider.dart';

/// Ten-year dip-threshold backtest — "does buying this dip actually work?".
///
/// The design rule for this card: **the baseline is not a footnote.** Every
/// forward return is shown beside what simply buying on a random day returned
/// over the same decade, because the raw number is meaningless without it. A
/// threshold that returned +15% over a year sounds excellent until the null
/// says +13.3%, at which point the signal is worth 1.7 points, not fifteen.
///
/// The measured answer for this universe is not the flattering one, and the
/// card is built to show that rather than bury it: shallow dips have a
/// NEGATIVE edge almost everywhere, and the deep thresholds that look
/// spectacular rest on one or two episodes in ten years.
class DipBacktestCard extends ConsumerStatefulWidget {
  /// Restrict to these benchmark symbols — normally the ones the user's own
  /// holdings map to, since a study of an index they do not own is noise.
  final List<String> symbols;

  const DipBacktestCard({super.key, this.symbols = const []});

  @override
  ConsumerState<DipBacktestCard> createState() => _DipBacktestCardState();
}

class _DipBacktestCardState extends ConsumerState<DipBacktestCard> {
  String _horizon = '1y';

  static const _horizonLabels = {
    '3m': '3 MONTHS',
    '6m': '6 MONTHS',
    '1y': '1 YEAR',
    '3y': '3 YEARS',
    '5y': '5 YEARS',
  };

  static const _cols = [
    DenseCol('BENCHMARK', 26, numeric: false),
    DenseCol('DEPTH', 10),
    DenseCol('EPISODES', 11),
    DenseCol('FORWARD', 13),
    DenseCol('BUY ANY DAY', 13),
    DenseCol('EDGE', 12),
    // Spacer: a right-aligned number abutting a left-aligned label collides,
    // since DenseRow puts no gap between its Expanded cells.
    DenseCol('', 2, numeric: false),
    DenseCol('VERDICT', 20, numeric: false),
  ];

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final async = ref.watch(dipBacktestProvider);
    final data = async.value ?? DipBacktest.empty;

    if (async.isLoading && data.studies.isEmpty) {
      return const DenseCard(child: DensePulseLoader(label: 'Backtesting…'));
    }
    if (data.studies.isEmpty) {
      return const DenseEmptyCard(
        icon: LucideIcons.history,
        title: 'Backtest unavailable',
        sub: 'Ten years of index history could not be loaded.',
      );
    }

    final studies = _selected(data);
    final rows = <List<Widget>>[];
    for (final s in studies) {
      for (final t in s.thresholds) {
        if (t.signals == 0) continue;
        rows.add(_row(context, s, t));
      }
    }

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(
          context,
          icon: LucideIcons.history,
          accent: c.gold,
          title: 'Does Buying the Dip Work?',
          subtitle: '${studies.length} benchmarks · '
              'up to ten years of daily closes',
          trailing: Wrap(
            spacing: 4,
            children: [
              for (final h in const ['6m', '1y', '3y'])
                DFilterChip(
                  label: _horizonLabels[h]!,
                  selected: _horizon == h,
                  tone: c.gold,
                  onTap: () => setState(() => _horizon = h),
                ),
            ],
          ),
        ),
        SectionExplainer(
          accent: c.gold,
          question: 'Has buying this fall actually paid, historically?',
          reading: 'For each drawdown depth: how often it happened, what came '
              'next, and what buying on any random day returned instead.',
          rules: const [
            'EDGE is the only column that answers the question. It is FORWARD '
                'minus BUY ANY DAY. A positive forward return with a negative '
                'edge means the market rose and the signal added nothing.',
            'EPISODES counts separate selloffs, not days. A bear market that '
                'sat below the line for months is one observation.',
            'Under five episodes the row is greyed out. Once or twice in a '
                'decade is an anecdote however good it looks.',
            'The measured result is uncomfortable: shallow dips mostly have a '
                'negative edge, and the deep ones that look spectacular are '
                'exactly the ones with too few episodes to trust.',
          ],
          action: 'Treat this as the reason to keep the SIP running and only '
              'deploy the reserve at depths that both fired often enough and '
              'beat the baseline.',
        ),
        denseColumnHeader(context, _cols),
        ...rows.asMap().entries.map((e) =>
            DenseRow(cells: e.value, cols: _cols, alt: e.key.isOdd)),
        _footer(context, data),
      ]),
    );
  }

  List<BenchmarkStudy> _selected(DipBacktest data) {
    final ok = data.studies.where((s) => s.ok).toList();
    if (widget.symbols.isEmpty) return ok.take(4).toList();
    final wanted = widget.symbols.toSet();
    return ok.where((s) => wanted.contains(s.symbol)).toList();
  }

  List<Widget> _row(BuildContext context, BenchmarkStudy s, ThresholdStudy t) {
    final c = context.colors;
    final fwd = t.at(_horizon);
    final base = s.baselineAt(_horizon);
    final edge = t.edgePp[_horizon];

    // A row that cannot be trusted is drawn grey throughout rather than being
    // hidden. "It happened twice" is a real answer to "what does history say".
    final dim = !t.reliable;
    final bodyTone = dim ? c.t3 : c.t1;

    return [
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(s.label,
            style: AppTextStyles.bodyBold(bodyTone).copyWith(fontSize: 11.5),
            maxLines: 1,
            overflow: TextOverflow.ellipsis),
        Text(
          '${s.years.toStringAsFixed(1)}y'
          '${s.historyTrimmed > 0 ? ' · trimmed at a split' : ''}'
          '${s.activeThresholdPct == t.thresholdPct ? ' · HERE NOW' : ''}',
          style: AppTextStyles.labelXs(
              s.activeThresholdPct == t.thresholdPct ? c.accent : c.t3),
          maxLines: 1,
        ),
      ]),
      denseNum(context, '−${t.thresholdPct.toStringAsFixed(0)}%', bodyTone),
      Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
        denseNum(context, '${t.signals}', bodyTone),
        if (dim)
          Text('too few', style: AppTextStyles.labelXs(c.gold), maxLines: 1),
      ]),
      fwd.isUnknown
          ? _dash(context)
          : Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
              denseSignedNum(context, fwd.meanPct!, bodyTone, decimals: 1),
              Text('n=${fwd.n}',
                  style: AppTextStyles.labelXs(c.t3), maxLines: 1),
            ]),
      base.isUnknown
          ? _dash(context)
          : denseSignedNum(context, base.meanPct!, c.t3, decimals: 1),
      edge == null
          ? _dash(context)
          : denseSignedNum(context, edge, dim ? c.t3 : (edge > 0 ? c.up : c.dn),
              decimals: 1, suffix: 'pp'),
      const SizedBox.shrink(),
      _verdict(context, t, edge, dim),
    ];
  }

  Widget _verdict(
      BuildContext context, ThresholdStudy t, double? edge, bool dim) {
    final c = context.colors;
    if (dim) {
      return Text('Too few episodes to rely on',
          style: AppTextStyles.labelXs(c.t3), maxLines: 2);
    }
    if (edge == null) {
      return Text('Not enough completed windows',
          style: AppTextStyles.labelXs(c.t3), maxLines: 2);
    }
    if (edge > 0) {
      return Row(children: [
        Icon(LucideIcons.check, size: 11, color: c.up),
        const SizedBox(width: 4),
        Flexible(
          child: Text('Beat buying any day',
              style: AppTextStyles.labelXs(c.up), maxLines: 1),
        ),
      ]);
    }
    return Row(children: [
      Icon(LucideIcons.x, size: 11, color: c.dn),
      const SizedBox(width: 4),
      Flexible(
        child: Text('No better than any day',
            style: AppTextStyles.labelXs(c.dn), maxLines: 1),
      ),
    ]);
  }

  Widget _dash(BuildContext context) => Text('—',
      style: AppTextStyles.labelXs(context.colors.t3),
      textAlign: TextAlign.right);

  Widget _footer(BuildContext context, DipBacktest data) {
    final c = context.colors;
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
          child: Text(
            'Thresholds are also selected on the first 60% of history and '
            'scored on the part never seen, so a depth that only looks good '
            'in hindsight is caught. Rows under '
            '${data.minSignalsForReliable} episodes are shown but never used '
            'to pick a level.',
            style: AppTextStyles.labelXs(c.t3),
          ),
        ),
      ]),
    );
  }
}
