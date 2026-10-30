import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/deploy_models.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';

/// Factor keys, in the order they appear in the score bar and the legend.
const _factorOrder = [
  'own_drawdown',
  'index_dip',
  'below_avg_cost',
  'underweight',
];

const _factorShort = {
  'own_drawdown': 'FALL',
  'index_dip': 'INDEX',
  'below_avg_cost': 'COST',
  'underweight': 'WEIGHT',
};

const _factorPlain = {
  'own_drawdown': 'How far it has fallen from its own peak',
  'index_dip': 'How far its market is below its 1-year high',
  'below_avg_cost': 'How far below your average cost it is',
  'underweight': 'How far below your target share it is',
};

const _candidateCols = <DenseCol>[
  DenseCol('HOLDING', 26, numeric: false),
  DenseCol('PRICE / NAV', 13),
  DenseCol('VS COST', 11),
  DenseCol('OFF PEAK', 11),
  DenseCol('WEIGHT', 13),
  DenseCol('SCORE', 18, numeric: false),
  DenseCol('', 4, numeric: false),
];

const _candidateColsNarrow = <DenseCol>[
  DenseCol('HOLDING', 34, numeric: false),
  DenseCol('OFF PEAK', 16),
  DenseCol('SCORE', 24, numeric: false),
  DenseCol('', 6, numeric: false),
];

/// Every holding ranked by how much it deserves new money. Tap a row to see
/// exactly which factors produced its score.
///
/// Hand-rolled rather than [DenseTable] because rows expand — the established
/// escape hatch in this codebase.
class BuyMoreCandidatesTable extends StatefulWidget {
  final DeployBoard board;
  const BuyMoreCandidatesTable({super.key, required this.board});

  @override
  State<BuyMoreCandidatesTable> createState() => _BuyMoreCandidatesTableState();
}

class _BuyMoreCandidatesTableState extends State<BuyMoreCandidatesTable> {
  String? _expanded;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final rows = widget.board.ranked;

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(
          context,
          icon: LucideIcons.crosshair,
          accent: c.up,
          title: 'Where to Buy More',
          subtitle: 'Best first · click any row to see why',
          trailing: const _ScoreLegend(),
        ),
        SectionExplainer(
          accent: c.up,
          question: 'Which of my holdings deserves the next rupee?',
          reading:
              'Every fund and stock you own, given a score out of 100. The '
              'coloured bar shows what made up that score.',
          rules: const [
            'A higher score means it looks cheaper right now, for more than '
                'one reason at the same time.',
            'The four reasons are: it has fallen from its own peak, its market '
                'has fallen, it is below what you paid, and you hold less of '
                'it than you wanted.',
            'CONF is how many of the four reasons could be checked. A score '
                'built on one reason is less trustworthy than one built on all '
                'four, so a low-confidence row gets no money.',
            'A dash means the app could not check that reason. That is not '
                'the same as a zero.',
          ],
          action:
              'Put new money into the top rows. If a row you expected is '
              'missing a reason, set its target share in Edit plan so the app '
              'can judge it properly.',
        ),
        if (rows.isEmpty)
          const DenseEmptyCard(
            icon: LucideIcons.crosshair,
            title: 'Nothing to rank yet',
            sub: 'Add some funds or stocks to your portfolio first.',
          )
        else
          LayoutBuilder(builder: (context, box) {
            final narrow = box.maxWidth < 900;
            final cols = narrow ? _candidateColsNarrow : _candidateCols;
            return Column(children: [
              denseColumnHeader(context, cols),
              for (final (i, cand) in rows.indexed)
                _CandidateRow(
                  cand: cand,
                  cols: cols,
                  alt: i.isOdd,
                  narrow: narrow,
                  expanded: _expanded == cand.key,
                  onTap: () => setState(
                      () => _expanded = _expanded == cand.key ? null : cand.key),
                ),
            ]);
          }),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
          child: Text(
            'Funds are measured against their all-time NAV peak, stocks '
            'against their 52-week high. Nothing here is a recommendation to '
            'buy — it is your own plan, scored.',
            style: AppTextStyles.captionXs(c.t4),
          ),
        ),
      ]),
    );
  }
}

class _CandidateRow extends StatelessWidget {
  final DeployCandidate cand;
  final List<DenseCol> cols;
  final bool alt;
  final bool narrow;
  final bool expanded;
  final VoidCallback onTap;

  const _CandidateRow({
    required this.cand,
    required this.cols,
    required this.alt,
    required this.narrow,
    required this.expanded,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final isFund = cand.kind == HoldingKind.fund;

    final instrument = DInstrument(
      symbol: cand.name,
      sub: cand.sector.isEmpty ? kindLabel(cand.kind) : cand.sector,
      up: true,
      spine: isFund ? c.blue : c.cyan,
      ellipsis: true,
    );

    final offPeak = cand.factor('own_drawdown').value;
    final vsCost = cand.factor('below_avg_cost').value;

    final cells = narrow
        ? [
            instrument,
            _magnitude(context, offPeak),
            _ScoreCell(cand: cand),
            _chevron(context),
          ]
        : [
            instrument,
            denseNum(
                context,
                cand.price == null
                    ? '—'
                    : formatINR(cand.price!, decimals: isFund ? 2 : 2),
                c.t1),
            _magnitude(context, vsCost),
            _magnitude(context, offPeak),
            _weight(context),
            _ScoreCell(cand: cand),
            _chevron(context),
          ];

    return Column(children: [
      DenseRow(
        cols: cols,
        alt: alt,
        highlighted: expanded,
        onTap: onTap,
        cells: cells,
      ),
      if (expanded) _FactorDetail(cand: cand),
    ]);
  }

  /// A "—" here means the app could not judge it. Never render 0 for unknown.
  Widget _magnitude(BuildContext context, double? value) {
    final c = context.colors;
    if (value == null) {
      return denseNum(context, '—', c.t4);
    }
    // A bigger fall is a better opportunity on this screen, so this is NOT
    // context.pnlColor — down is not red here.
    final tone = value > 0 ? c.up : c.t3;
    return Align(
      alignment: Alignment.centerRight,
      child: denseSignedNum(context, value, tone, decimals: 1),
    );
  }

  Widget _weight(BuildContext context) {
    final c = context.colors;
    final actual = cand.actualPct ?? 0;
    if (cand.targetPct == null) {
      return Align(
        alignment: Alignment.centerRight,
        child: Text('${actual.toStringAsFixed(1)}%  no target',
            style: AppTextStyles.captionXs(c.t4),
            maxLines: 1,
            overflow: TextOverflow.ellipsis),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('${actual.toStringAsFixed(1)}% / ${cand.targetPct!.toStringAsFixed(0)}%',
            style: AppTextStyles.monoXs(c.t2), maxLines: 1),
        const SizedBox(height: 3),
        DStackedBar(
          segments: [(actual, cand.atOrOverTarget ? c.t3 : c.gold)],
          total: cand.targetPct!,
          height: 3,
        ),
      ],
    );
  }

  Widget _chevron(BuildContext context) => Align(
        alignment: Alignment.centerRight,
        child: Icon(
          expanded ? LucideIcons.chevronUp : LucideIcons.chevronDown,
          size: 13,
          color: context.colors.t4,
        ),
      );
}

/// The score cell: number, confidence, and a bar showing its make-up.
class _ScoreCell extends StatelessWidget {
  final DeployCandidate cand;
  const _ScoreCell({required this.cand});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    if (!cand.scored) {
      return Align(
        alignment: Alignment.centerLeft,
        child: Text('not enough data',
            style: AppTextStyles.captionXs(c.t4), maxLines: 1),
      );
    }

    final score = cand.score!;
    final tone = score >= 60
        ? c.up
        : score >= 35
            ? c.gold
            : c.t3;

    // Each factor's contribution, so the bar explains the number beside it.
    final segments = <(double, Color)>[
      for (final key in _factorOrder)
        if (cand.factor(key).known)
          (cand.factor(key).score! / 4, _factorColor(context, key)),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(children: [
          Text(score.toStringAsFixed(0),
              style: AppTextStyles.monoBold(tone).copyWith(fontSize: 14)),
          const SizedBox(width: 6),
          Text('conf ${cand.confidence}%',
              style: AppTextStyles.captionXs(
                  cand.confidence < 40 ? c.gold : c.t4)),
          if (!cand.eligible && cand.confidence < 40) ...[
            const SizedBox(width: 4),
            Icon(LucideIcons.alertTriangle, size: 10, color: c.gold),
          ],
        ]),
        const SizedBox(height: 4),
        DStackedBar(segments: segments, total: 100, height: 4),
      ],
    );
  }
}

/// Expanded panel: every factor, its real magnitude, and its 0-100 score.
class _FactorDetail extends StatelessWidget {
  final DeployCandidate cand;
  const _FactorDetail({required this.cand});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(18, 12, 14, 14),
      decoration: BoxDecoration(
        color: c.bg1,
        border: Border(
          left: BorderSide(color: c.blue, width: 2),
          bottom: BorderSide(color: c.bd),
        ),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (cand.why.isNotEmpty) ...[
          Text(cand.why.join('  ·  '),
              style: AppTextStyles.bodySmall(c.t1)),
          const SizedBox(height: 12),
        ],
        for (final key in _factorOrder) _factorRow(context, key),
        const SizedBox(height: 10),
        Text(_footnote(), style: AppTextStyles.captionXs(c.t4)),
      ]),
    );
  }

  Widget _factorRow(BuildContext context, String key) {
    final c = context.colors;
    final f = cand.factor(key);
    final known = f.known;
    final tone = _factorColor(context, key);

    return Padding(
      padding: const EdgeInsets.only(bottom: 7),
      child: Row(children: [
        Container(width: 8, height: 8, decoration: BoxDecoration(
            color: known ? tone : c.bd2, shape: BoxShape.circle)),
        const SizedBox(width: 9),
        SizedBox(
          width: 240,
          child: Text(_factorPlain[key] ?? key,
              style: AppTextStyles.bodySmall(known ? c.t2 : c.t4),
              maxLines: 1,
              overflow: TextOverflow.ellipsis),
        ),
        const SizedBox(width: 10),
        SizedBox(
          width: 110,
          child: Text(
            known && f.value != null
                ? '${f.value!.toStringAsFixed(1)} ${f.unit}'
                : 'could not check',
            style: AppTextStyles.monoXs(known ? c.t1 : c.t4),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: DStackedBar(
            segments: known ? [(f.score!, tone)] : const [],
            total: 100,
            height: 4,
          ),
        ),
        const SizedBox(width: 10),
        SizedBox(
          width: 34,
          child: Text(known ? f.score!.toStringAsFixed(0) : '—',
              style: AppTextStyles.monoXs(known ? c.t2 : c.t4),
              textAlign: TextAlign.right),
        ),
      ]),
    );
  }

  String _footnote() {
    if (cand.missingFactors.isEmpty) {
      return 'All four checks were possible, so this score is fully informed.';
    }
    final n = cand.missingFactors.length;
    return '$n of 4 checks could not be made, so this score is based on the '
        'rest. Setting a target share and keeping your cost basis up to date '
        'fills most gaps.';
  }
}

class _ScoreLegend extends StatelessWidget {
  const _ScoreLegend();

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Wrap(
      spacing: 10,
      runSpacing: 4,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        for (final key in _factorOrder)
          Row(mainAxisSize: MainAxisSize.min, children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: _factorColor(context, key),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(width: 4),
            Text(_factorShort[key] ?? key, style: AppTextStyles.captionXs(c.t3)),
          ]),
      ],
    );
  }
}

Color _factorColor(BuildContext context, String key) {
  final c = context.colors;
  return switch (key) {
    'own_drawdown' => c.up,
    'index_dip' => c.accent,
    'below_avg_cost' => c.cyan,
    'underweight' => c.gold,
    _ => c.t3,
  };
}
