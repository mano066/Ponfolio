import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/conviction_models.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/providers/conviction_provider.dart';
import 'package:aiei_wealth/providers/providers.dart';

/// "Why do I own this, and may I add more?" — the dashboard section.
///
/// Judges every holding on the business, the written thesis and the position
/// size. It never uses the share price or the average cost as a reason, which
/// is the point: those were the inputs behind buying losers and selling
/// winners.
class ConvictionSection extends ConsumerWidget {
  const ConvictionSection({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final async = ref.watch(convictionBoardProvider);
    final board = async.value ?? ConvictionBoard.empty;

    if (async.hasError && !async.isLoading) {
      return DenseCard(
        child: Row(children: [
          Icon(LucideIcons.triangleAlert, size: 14, color: c.dn),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Could not load the conviction board.',
                style: AppTextStyles.bodySmall(c.t2)),
          ),
          TextButton(
              onPressed: () => ref.invalidate(convictionBoardProvider),
              child: const Text('Retry')),
        ]),
      );
    }
    if (async.isLoading && board.isEmpty) {
      return const DenseCard(child: SizedBox(height: 120, child: DensePulseLoader()));
    }

    final season = board.resultsSeason;
    final seasonText = season['label'] == null
        ? ''
        : season['in_season'] == true
            ? 'Results season now: ${season['label']} — review each holding'
            : 'Next results: ${season['label']} in ${season['days_until']} days';

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(2, 0, 2, 10),
        child: Row(children: [
          Icon(LucideIcons.shieldCheck, size: 15, color: c.blue),
          const SizedBox(width: 8),
          Flexible(
            flex: 3,
            child: Text('CONVICTION & POSITION SIZE',
                style: AppTextStyles.bodyBold(c.t1)
                    .copyWith(fontSize: 13, letterSpacing: 0.5),
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
          ),
          const SizedBox(width: 10),
          Expanded(
            flex: 4,
            child: Text('Business, thesis and size — never price or your average',
                style: AppTextStyles.labelXs(c.t3),
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
          ),
          IconButton(
            tooltip: 'Discipline settings',
            iconSize: 16,
            icon: Icon(LucideIcons.settings2, color: c.t3),
            onPressed: () => _showSettings(context, ref, board),
          ),
        ]),
      ),
      DenseCard(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(spacing: 8, runSpacing: 6, children: [
            _CountChip('No thesis', board.count('borrowed_conviction'), c.gold),
            _CountChip('Under 1%', board.count('under_exit_line'), c.dn),
            _CountChip('Below 2%', board.count('below_min'), c.gold),
            _CountChip('Over max', board.count('over_max'), c.dn),
            _CountChip('Review due', board.count('review_due'), c.blue),
            _CountChip('Add allowed', board.count('add_allowed'), c.up),
          ]),
          if (seasonText.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(seasonText, style: AppTextStyles.captionXs(c.t3)),
          ],
          const SizedBox(height: 10),
          if (board.holdings.isEmpty)
            Text('Add equity holdings to judge them here.',
                style: AppTextStyles.bodySmall(c.t3))
          else ...[
            const _HeaderRow(),
            for (final r in board.holdings)
              _HoldingRow(row: r, onTap: () => showConvictionDetail(context, r, board)),
          ],
          const SizedBox(height: 14),
          _WatchlistBlock(board: board),
        ]),
      ),
    ]);
  }
}

// ── tones ──────────────────────────────────────────────────────────────

Color _actionTone(BuildContext context, String action) {
  final c = context.colors;
  return switch (action) {
    'sell_review' || 'reduce' || 'exit_or_grow' => c.dn,
    'write_thesis' || 'trim_over_max' => c.gold,
    'review_due' => c.blue,
    'add_allowed' => c.up,
    _ => c.t3,
  };
}

Color _gradeTone(BuildContext context, String grade) {
  final c = context.colors;
  return switch (grade) {
    'strong' || 'good' => c.up,
    'weak' => c.gold,
    'poor' => c.dn,
    _ => c.t3,
  };
}

Color _statusTone(BuildContext context, String status) {
  final c = context.colors;
  return switch (status) {
    'good' || 'met' => c.up,
    'warn' => c.gold,
    'bad' || 'missed' => c.dn,
    _ => c.t3,
  };
}

class _CountChip extends StatelessWidget {
  final String label;
  final int count;
  final Color tone;
  const _CountChip(this.label, this.count, this.tone);

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final active = count > 0;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: active ? tone.withValues(alpha: 0.12) : c.bg2,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: active ? tone.withValues(alpha: 0.4) : c.bd),
      ),
      child: Text('$label  $count',
          style: AppTextStyles.labelXs(active ? tone : c.t3)),
    );
  }
}

class _Pill extends StatelessWidget {
  final String text;
  final Color tone;
  const _Pill(this.text, this.tone);

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        decoration: BoxDecoration(
          color: tone.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text(text,
            style: AppTextStyles.labelXs(tone),
            maxLines: 1,
            overflow: TextOverflow.ellipsis),
      );
}

class _HeaderRow extends StatelessWidget {
  const _HeaderRow();

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    Widget h(String t, int flex) => Expanded(
        flex: flex, child: Text(t, style: AppTextStyles.tableHeader(c.t3)));
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(children: [
        h('STOCK', 4),
        h('WEIGHT', 2),
        h('BUSINESS', 3),
        h('THESIS', 3),
        h('LAST RESULT', 3),
        h('ACTION', 4),
      ]),
    );
  }
}

class _HoldingRow extends StatelessWidget {
  final ConvictionRow row;
  final VoidCallback onTap;
  const _HoldingRow({required this.row, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final h = row.health;
    final weight = row.weightPct;
    final sizeTone = switch (row.sizeBand) {
      'exit_or_grow' || 'over_max' => c.dn,
      'below_min' => c.gold,
      _ => c.t2,
    };
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 6),
        decoration: BoxDecoration(
            border: Border(top: BorderSide(color: c.rowBorder))),
        child: Row(children: [
          Expanded(
            flex: 4,
            child: Text(row.key + (row.isEtf ? ' · ETF' : ''),
                style: AppTextStyles.bodyBold(c.t1),
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
          ),
          Expanded(
            flex: 2,
            child: Text(weight == null ? '—' : '${weight.toStringAsFixed(1)}%',
                style: AppTextStyles.mono(sizeTone)),
          ),
          Expanded(
            flex: 3,
            child: Align(
              alignment: Alignment.centerLeft,
              child: _Pill(
                  h.score == null
                      ? (row.isEtf ? 'Index' : 'No data')
                      : '${h.score!.toStringAsFixed(0)} ${h.gradeLabel}',
                  _gradeTone(context, h.grade)),
            ),
          ),
          Expanded(
            flex: 3,
            child: Align(
              alignment: Alignment.centerLeft,
              child: _Pill(
                  switch (row.thesisState) {
                    'ok' => 'Written',
                    'stale' => 'Old',
                    'incomplete' => 'Incomplete',
                    _ => 'None',
                  },
                  row.thesisState == 'ok' ? c.up : c.gold),
            ),
          ),
          Expanded(
            flex: 3,
            child: Align(
              alignment: Alignment.centerLeft,
              child: _Pill(
                  switch (row.lastResult) {
                    'met' => 'Met',
                    'missed' => row.missedStreak > 1
                        ? 'Missed ×${row.missedStreak}'
                        : 'Missed',
                    _ => '—',
                  },
                  _statusTone(context, row.lastResult)),
            ),
          ),
          Expanded(
            flex: 4,
            child: Text(row.actionLabel,
                style: AppTextStyles.labelXs(_actionTone(context, row.action)),
                maxLines: 2,
                overflow: TextOverflow.ellipsis),
          ),
        ]),
      ),
    );
  }
}

// ── watchlist ──────────────────────────────────────────────────────────

class _WatchlistBlock extends ConsumerWidget {
  final ConvictionBoard board;
  const _WatchlistBlock({required this.board});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Expanded(
          child: Text('WATCHLIST — NEW IDEAS WAIT HERE FIRST',
              style: AppTextStyles.tableHeader(c.t3),
              maxLines: 1,
              overflow: TextOverflow.ellipsis),
        ),
        TextButton.icon(
          icon: const Icon(LucideIcons.plus, size: 14),
          label: const Text('Add idea'),
          onPressed: () => _showAddIdea(context, ref),
        ),
      ]),
      if (board.watchlist.isEmpty)
        Text('Heard a stock name? Add it here instead of buying it today.',
            style: AppTextStyles.captionXs(c.t3))
      else
        for (final w in board.watchlist)
          InkWell(
            onTap: () => showThesisEditor(context, ref,
                symbol: w.key, name: w.name, thesis: w.thesis, board: board),
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 6),
              decoration: BoxDecoration(
                  border: Border(top: BorderSide(color: c.rowBorder))),
              child: Row(children: [
                Expanded(
                    flex: 4,
                    child: Text(w.key, style: AppTextStyles.bodyBold(c.t1))),
                Expanded(
                  flex: 3,
                  child: Text(
                      w.daysWatched == null ? '' : 'Watched ${w.daysWatched} d',
                      style: AppTextStyles.captionXs(c.t3)),
                ),
                Expanded(
                  flex: 3,
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: _Pill(
                        w.health.score == null
                            ? 'No data'
                            : '${w.health.score!.toStringAsFixed(0)} ${w.health.gradeLabel}',
                        _gradeTone(context, w.health.grade)),
                  ),
                ),
                Expanded(
                  flex: 6,
                  child: Text(
                      w.stage == 'waiting' && w.readyAfter != null
                          ? '${w.stageLabel} (until ${w.readyAfter})'
                          : w.stage == 'ready'
                              ? '${w.stageLabel} — about ${w.initialPositionPct.toStringAsFixed(0)}%'
                              : w.stageLabel,
                      style: AppTextStyles.labelXs(
                          w.stage == 'ready' ? c.up : c.t2),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis),
                ),
                IconButton(
                  tooltip: 'Remove from watchlist',
                  iconSize: 14,
                  icon: Icon(LucideIcons.x, color: c.t4),
                  onPressed: () async {
                    await ref.read(apiServiceProvider).removeFromWatchlist(w.symbol);
                    ref.invalidate(convictionBoardProvider);
                  },
                ),
              ]),
            ),
          ),
    ]);
  }
}

Future<void> _showAddIdea(BuildContext context, WidgetRef ref) async {
  final ctrl = TextEditingController();
  final symbol = await showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Add an idea to watch'),
      content: Column(mainAxisSize: MainAxisSize.min, children: [
        const Text('It waits here at least one results season. Not a rupee '
            'goes in until it passes the three questions and the business check.'),
        const SizedBox(height: 12),
        TextField(
          controller: ctrl,
          autofocus: true,
          textCapitalization: TextCapitalization.characters,
          decoration: const InputDecoration(labelText: 'NSE symbol, e.g. TITAN'),
          onSubmitted: (v) => Navigator.pop(ctx, v),
        ),
      ]),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
        FilledButton(
            onPressed: () => Navigator.pop(ctx, ctrl.text),
            child: const Text('Add to watchlist')),
      ],
    ),
  );
  final sym = symbol?.trim().toUpperCase() ?? '';
  if (sym.isEmpty) return;
  await ref.read(apiServiceProvider).addToWatchlist(sym);
  ref.invalidate(convictionBoardProvider);
}

// ── detail sheet ───────────────────────────────────────────────────────

Future<void> showConvictionDetail(
    BuildContext context, ConvictionRow row, ConvictionBoard board) {
  return showDialog(
    context: context,
    builder: (ctx) => _ConvictionDetail(row: row, board: board),
  );
}

class _ConvictionDetail extends ConsumerWidget {
  final ConvictionRow row;
  final ConvictionBoard board;
  const _ConvictionDetail({required this.row, required this.board});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final h = row.health;
    final t = row.thesis;

    Widget section(String title, List<Widget> children) => Padding(
          padding: const EdgeInsets.only(top: 14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: AppTextStyles.tableHeader(c.t3)),
            const SizedBox(height: 6),
            ...children,
          ]),
        );

    Widget line(String text, Color tone) => Padding(
          padding: const EdgeInsets.only(bottom: 3),
          child: Text('• $text', style: AppTextStyles.bodySmall(tone)),
        );

    return AlertDialog(
      title: Text('${row.name} (${row.key})'),
      content: SizedBox(
        width: 560,
        child: SingleChildScrollView(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Wrap(spacing: 8, runSpacing: 6, children: [
              _Pill(row.actionLabel, _actionTone(context, row.action)),
              _Pill(
                  row.weightPct == null
                      ? row.sizeLabel
                      : '${row.weightPct!.toStringAsFixed(1)}% · ${row.sizeLabel}',
                  row.sizeBand == 'ok' ? c.t2 : c.gold),
              _Pill(row.thesisLabel, row.thesisState == 'ok' ? c.up : c.gold),
            ]),
            if (row.firedTriggers.isNotEmpty)
              section('SELL TRIGGER HIT', [
                for (final f in row.firedTriggers)
                  line(
                      '${f.text.isEmpty ? (board.triggerMetrics[f.metric] ?? f.metric) : f.text}: '
                      'now ${f.current?.toStringAsFixed(1)} ${f.op} ${f.value?.toStringAsFixed(1)}',
                      c.dn),
              ]),
            section(
                'MAY I ADD MORE?',
                row.addAllowed
                    ? [line('Yes — thesis met, business healthy, size within limits.', c.up)]
                    : [for (final b in row.addBlockers) line(b, c.gold)]),
            if (row.trendFlags.isNotEmpty)
              section('TREND ACROSS QUARTERS',
                  [for (final f in row.trendFlags) line(f, c.gold)]),
            section('BUSINESS HEALTH', [
              if (row.isEtf)
                line('Index fund: there is no single business to score. '
                    'Judge it on the index and your allocation.', c.t2)
              else ...[
                Text(
                    h.score == null
                        ? 'Not enough data'
                        : '${h.score!.toStringAsFixed(0)}/100 · ${h.gradeLabel}'
                            ' · ${h.coverage.toStringAsFixed(0)}% of checks measured'
                            '${h.financial ? ' · judged as a lender' : ''}',
                    style: AppTextStyles.bodyBold(_gradeTone(context, h.grade))),
                const SizedBox(height: 6),
                for (final ck in h.checks)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 2),
                    child: Row(children: [
                      Expanded(
                          flex: 4,
                          child: Text(ck.label, style: AppTextStyles.bodySmall(c.t2))),
                      Expanded(
                          flex: 2,
                          child: Text(ck.valueText,
                              style: AppTextStyles.mono(_statusTone(context, ck.status)))),
                      Expanded(
                          flex: 5,
                          child: Text(ck.rule, style: AppTextStyles.captionXs(c.t4))),
                    ]),
                  ),
              ],
            ]),
            section('YOUR THESIS', [
              if (t == null)
                line('Not written. If you bought this because someone mentioned it, '
                    'this is where to find out whether you still should own it.', c.gold)
              else ...[
                line('What it does: ${t.whatItDoes.isEmpty ? '—' : t.whatItDoes}', c.t1),
                line('Why profit can grow: ${t.growthReason.isEmpty ? '—' : t.growthReason}', c.t1),
                line(
                    'Expected growth: EPS ${t.expectedEpsGrowthPct?.toStringAsFixed(0) ?? '—'}%'
                    ' · sales ${t.expectedSalesGrowthPct?.toStringAsFixed(0) ?? '—'}%',
                    c.t2),
                for (final tr in t.sellTriggers)
                  line(
                      'Sell if: ${tr.text}'
                      '${tr.automatic ? ' (auto: ${board.triggerMetrics[tr.metric] ?? tr.metric} ${tr.op} ${tr.value})' : ''}',
                      c.t2),
                if (t.nextReview != null) line('Next review: ${t.nextReview}', c.t2),
              ],
            ]),
            if (row.quarters.isNotEmpty)
              section('QUARTERLY RESULTS vs THESIS', [
                for (final q in row.quarters.reversed)
                  Row(children: [
                    SizedBox(
                        width: 70,
                        child: Text(q.quarter, style: AppTextStyles.mono(c.t2))),
                    _Pill(
                        '${switch (q.result) { 'met' => 'Met', 'missed' => 'Missed', _ => 'Not judged' }}'
                        '${q.manual ? ' (yours)' : ''}',
                        _statusTone(context, q.result)),
                    const Spacer(),
                    for (final r in const ['met', 'missed', 'clear'])
                      TextButton(
                        onPressed: () async {
                          await ref
                              .read(apiServiceProvider)
                              .setQuarterResult(row.key, q.quarter, r);
                          ref.invalidate(convictionBoardProvider);
                          if (context.mounted) Navigator.pop(context);
                        },
                        child: Text(r == 'clear' ? 'Auto' : r[0].toUpperCase() + r.substring(1)),
                      ),
                  ]),
              ]),
          ]),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
        FilledButton.icon(
          icon: const Icon(LucideIcons.pencil, size: 14),
          label: Text(t == null ? 'Write thesis' : 'Edit thesis'),
          onPressed: () {
            Navigator.pop(context);
            showThesisEditor(context, ref,
                symbol: row.key, name: row.name, thesis: t, board: board);
          },
        ),
      ],
    );
  }
}

// ── thesis editor ──────────────────────────────────────────────────────

Future<void> showThesisEditor(BuildContext context, WidgetRef ref,
    {required String symbol,
    required String name,
    Thesis? thesis,
    required ConvictionBoard board}) {
  return showDialog(
    context: context,
    builder: (ctx) =>
        ThesisEditor(symbol: symbol, name: name, thesis: thesis, board: board),
  );
}

class _TriggerDraft {
  final TextEditingController text;
  final TextEditingController value;
  String? metric;
  String op;
  _TriggerDraft({String t = '', this.metric, this.op = '<', double? v})
      : text = TextEditingController(text: t),
        value = TextEditingController(text: v == null ? '' : _fmt(v));

  SellTrigger toTrigger() {
    final v = double.tryParse(value.text.trim());
    return SellTrigger(
        text: text.text.trim(),
        metric: metric != null && v != null ? metric : null,
        op: metric != null && v != null ? op : null,
        value: metric != null ? v : null);
  }
}

String _fmt(double v) =>
    v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toString();

class ThesisEditor extends ConsumerStatefulWidget {
  final String symbol, name;
  final Thesis? thesis;
  final ConvictionBoard board;
  const ThesisEditor(
      {super.key,
      required this.symbol,
      required this.name,
      this.thesis,
      required this.board});

  @override
  ConsumerState<ThesisEditor> createState() => _ThesisEditorState();
}

class _ThesisEditorState extends ConsumerState<ThesisEditor> {
  late final TextEditingController _what, _why, _eps, _sales, _source, _review;
  late final List<_TriggerDraft> _triggers;
  String? _error;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final t = widget.thesis;
    _what = TextEditingController(text: t?.whatItDoes ?? '');
    _why = TextEditingController(text: t?.growthReason ?? '');
    _eps = TextEditingController(
        text: t?.expectedEpsGrowthPct == null ? '' : _fmt(t!.expectedEpsGrowthPct!));
    _sales = TextEditingController(
        text: t?.expectedSalesGrowthPct == null ? '' : _fmt(t!.expectedSalesGrowthPct!));
    _source = TextEditingController(text: t?.source ?? '');
    _review = TextEditingController(text: t?.nextReview ?? '');
    _triggers = [
      for (final tr in t?.sellTriggers ?? const <SellTrigger>[])
        _TriggerDraft(t: tr.text, metric: tr.metric, op: tr.op ?? '<', v: tr.value),
    ];
    if (_triggers.isEmpty) {
      _triggers.add(_TriggerDraft(
          t: 'Sales shrink', metric: 'revenue_growth_pct', op: '<', v: 0));
    }
  }

  @override
  void dispose() {
    for (final ctrl in [_what, _why, _eps, _sales, _source, _review]) {
      ctrl.dispose();
    }
    for (final tr in _triggers) {
      tr.text.dispose();
      tr.value.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    final thesis = Thesis(
      whatItDoes: _what.text.trim(),
      growthReason: _why.text.trim(),
      source: _source.text.trim(),
      expectedEpsGrowthPct: double.tryParse(_eps.text.trim()),
      expectedSalesGrowthPct: double.tryParse(_sales.text.trim()),
      sellTriggers: [
        for (final d in _triggers)
          if (d.text.text.trim().isNotEmpty || d.metric != null) d.toTrigger()
      ],
      nextReview: _review.text.trim().isEmpty ? null : _review.text.trim(),
    );
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await ref.read(apiServiceProvider).saveThesis(widget.symbol, thesis.toJson());
      ref.invalidate(convictionBoardProvider);
      if (mounted) Navigator.pop(context);
    } catch (e) {
      setState(() {
        _saving = false;
        _error = 'Could not save: $e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final metrics = widget.board.triggerMetrics;
    InputDecoration dec(String label, [String? hint]) =>
        InputDecoration(labelText: label, hintText: hint, isDense: true);

    return AlertDialog(
      title: Text('Thesis — ${widget.name}'),
      content: SizedBox(
        width: 580,
        child: SingleChildScrollView(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Answer these before adding a rupee. Use business reasons, '
                'never the share price.',
                style: AppTextStyles.captionXs(c.t3)),
            const SizedBox(height: 10),
            TextField(
                controller: _what,
                maxLines: 2,
                decoration: dec('1. What does it sell, and who pays it?',
                    'Two simple lines')),
            const SizedBox(height: 8),
            TextField(
                controller: _why,
                maxLines: 2,
                decoration: dec('2. Why can its profit grow for 5 years?',
                    'Capacity, market share, pricing power…')),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(
                  child: TextField(
                      controller: _eps,
                      keyboardType: TextInputType.number,
                      decoration: dec('Expected EPS growth %/yr'))),
              const SizedBox(width: 10),
              Expanded(
                  child: TextField(
                      controller: _sales,
                      keyboardType: TextInputType.number,
                      decoration: dec('Expected sales growth %/yr'))),
            ]),
            const SizedBox(height: 14),
            Text('3. What business event would make you sell?',
                style: AppTextStyles.bodyBold(c.t1)),
            Text('Add a number to have the app check it each quarter.',
                style: AppTextStyles.captionXs(c.t3)),
            for (final d in _triggers)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Row(children: [
                  Expanded(
                      flex: 5,
                      child: TextField(
                          controller: d.text, decoration: dec('Sell if…'))),
                  const SizedBox(width: 6),
                  Expanded(
                    flex: 4,
                    child: DropdownButtonFormField<String?>(
                      initialValue: d.metric,
                      isExpanded: true,
                      decoration: dec('Auto-check'),
                      items: [
                        const DropdownMenuItem(value: null, child: Text('Manual only')),
                        for (final e in metrics.entries)
                          DropdownMenuItem(value: e.key, child: Text(e.value)),
                      ],
                      onChanged: (v) => setState(() => d.metric = v),
                    ),
                  ),
                  const SizedBox(width: 6),
                  SizedBox(
                    width: 76,
                    child: DropdownButtonFormField<String>(
                      initialValue: d.op,
                      isExpanded: true,
                      iconSize: 18,
                      decoration: dec('').copyWith(
                          contentPadding: const EdgeInsets.symmetric(
                              horizontal: 6, vertical: 8)),
                      items: [
                        for (final o in widget.board.triggerOps)
                          DropdownMenuItem(value: o, child: Text(o)),
                      ],
                      onChanged: d.metric == null
                          ? null
                          : (v) => setState(() => d.op = v ?? '<'),
                    ),
                  ),
                  const SizedBox(width: 6),
                  SizedBox(
                      width: 64,
                      child: TextField(
                          controller: d.value,
                          enabled: d.metric != null,
                          keyboardType: TextInputType.number,
                          decoration: dec('Value'))),
                  IconButton(
                    iconSize: 14,
                    icon: Icon(LucideIcons.trash2, color: c.t4),
                    onPressed: () => setState(() => _triggers.remove(d)),
                  ),
                ]),
              ),
            if (_triggers.length < 6)
              TextButton.icon(
                icon: const Icon(LucideIcons.plus, size: 14),
                label: const Text('Add a sell trigger'),
                onPressed: () => setState(() => _triggers.add(_TriggerDraft())),
              ),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(
                  child: TextField(
                      controller: _source,
                      decoration: dec('Where did you hear of it?', 'Friend, YouTube…'))),
              const SizedBox(width: 10),
              Expanded(
                  child: TextField(
                      controller: _review,
                      decoration: dec('Next review (YYYY-MM-DD)'))),
            ]),
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(_error!, style: AppTextStyles.bodySmall(c.dn)),
            ],
          ]),
        ),
      ),
      actions: [
        if (widget.thesis != null)
          TextButton(
            onPressed: _saving
                ? null
                : () async {
                    await ref.read(apiServiceProvider).deleteThesis(widget.symbol);
                    ref.invalidate(convictionBoardProvider);
                    if (context.mounted) Navigator.pop(context);
                  },
            child: Text('Delete', style: TextStyle(color: c.dn)),
          ),
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
            onPressed: _saving ? null : _save, child: const Text('Save thesis')),
      ],
    );
  }
}

// ── settings ───────────────────────────────────────────────────────────

const _settingFields = <(String, String)>[
  ('exit_or_grow_below_pct', 'Exit-or-grow below (%)'),
  ('min_position_pct', 'Real position from (%)'),
  ('initial_position_pct', 'First buy size (%)'),
  ('max_position_pct', 'Maximum per stock (%)'),
  ('watch_min_days', 'Watchlist wait (days)'),
  ('thesis_max_age_days', 'Re-answer thesis after (days)'),
  ('misses_before_reduce', 'Missed quarters before reduce'),
  ('min_health_to_add', 'Min business health to add'),
];

Future<void> _showSettings(
    BuildContext context, WidgetRef ref, ConvictionBoard board) async {
  final ctrls = {
    for (final (key, _) in _settingFields)
      key: TextEditingController(
          text: board.settings[key] == null ? '' : _fmt((board.settings[key] as num).toDouble())),
  };
  final saved = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Discipline settings'),
      content: SizedBox(
        width: 380,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          for (final (key, label) in _settingFields)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: TextField(
                controller: ctrls[key],
                keyboardType: TextInputType.number,
                decoration: InputDecoration(labelText: label, isDense: true),
              ),
            ),
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
        FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Save')),
      ],
    ),
  );
  if (saved == true) {
    await ref.read(apiServiceProvider).saveConvictionSettings({
      for (final e in ctrls.entries)
        if (double.tryParse(e.value.text.trim()) != null)
          e.key: double.parse(e.value.text.trim()),
    });
    ref.invalidate(convictionBoardProvider);
  }
  for (final ctrl in ctrls.values) {
    ctrl.dispose();
  }
}
