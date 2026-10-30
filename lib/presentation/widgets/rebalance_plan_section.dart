import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/providers/providers.dart';
import 'package:aiei_wealth/providers/rebalance_provider.dart';

/// BAND REBALANCE — the rule-based plan, priced after tax.
///
/// Two bands are enforced at once, and they answer different questions.
/// The PER-ASSET band asks whether any one holding has become too big a part
/// of its own category; the CATEGORY band asks whether the four-way mix is
/// still the mix that was chosen. A portfolio can have every stock inside
/// 2–10% of the stock sleeve while stocks have grown to 80% of the book, and
/// it can hold exactly the right four-way split while one name is a third of
/// the equity. Neither band catches the other's failure.
///
/// Distinct again from the risk-profile engine below it, which asks whether
/// the asset-class mix matches a chosen profile rather than what to trade and
/// what the trade costs after the tax withheld on it.
class RebalancePlanSection extends ConsumerWidget {
  const RebalancePlanSection({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final plan = ref.watch(rebalancePlanProvider);
    return plan.when(
      loading: () => const DenseCard(
        clip: true,
        child: SizedBox(
          height: 140,
          child: DensePulseLoader(label: 'Pricing the rebalance…'),
        ),
      ),
      error: (e, _) => DenseCard(
        clip: true,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 28),
          child: ErrorRetry(
            title: 'Unable to build a rebalance plan',
            detail: '$e',
            compact: true,
            onRetry: () {
              ref.invalidate(rebalanceSettingsProvider);
              ref.invalidate(rebalancePlanProvider);
            },
          ),
        ),
      ),
      data: (data) => _Plan(data: data),
    );
  }
}

class _Plan extends ConsumerWidget {
  final Map<String, dynamic> data;
  const _Plan({required this.data});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final policy = _map(data['policy']);
    final triggers = _map(data['triggers']);
    final totals = _map(data['totals']);
    final market = _map(data['market']);
    final crash = _map(data['crash']);
    final volatility = _map(data['volatility']);
    final allocation = _map(data['allocation']);
    final actions = _list(data['actions']);
    final settings = _map(data['settings']);
    final preset = _map(data['strategy_preset']);
    final due = triggers['due'] == true;
    final manual = policy['mode'] == 'manual';

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(
          context,
          icon: LucideIcons.scale,
          accent: c.accent,
          title: 'Band Rebalance · after tax',
          subtitle: 'Every holding between ${_pct(policy['min_weight_pct'])} '
              'and ${_pct(policy['max_weight_pct'])} of its category, and '
              'every category within ${_pts(policy['deviation_pct'])} of target',
          trailing: Row(mainAxisSize: MainAxisSize.min, children: [
            AppBadge(
              text: due ? 'DUE NOW' : 'NOT DUE',
              variant: due ? BadgeVariant.gold : BadgeVariant.hold,
            ),
            const SizedBox(width: 8),
            // Manual is not a different plan — it is the same plan with the
            // question "is today the day" answered by the user instead of by
            // the triggers.
            DFilterChip(
              label: manual ? 'MANUAL' : 'AUTOMATIC',
              selected: manual,
              tone: manual ? c.gold : c.accent,
              onTap: () => ref
                  .read(rebalanceSettingsProvider.notifier)
                  .save(mode: manual ? 'auto' : 'manual'),
            ),
          ]),
        ),
        SectionExplainer(
          accent: c.accent,
          question: 'What do I trim, what do I top up, and what does it cost?',
          reading: 'Every holding outside its band and every category off its '
              'target, sized in rupees and priced after the tax withheld on '
              'the sale.',
          rules: [
            'A holding above ${_pct(policy['max_weight_pct'])} of its CATEGORY '
                'is trimmed back TO that ceiling — not sold out of. One below '
                '${_pct(policy['min_weight_pct'])} is topped up to the floor, '
                'or closed if you no longer want it.',
            'Stocks are weighed against stocks, funds against funds, gold '
                'against gold and debt against debt. A 10% cap on the whole '
                'portfolio would let one name be most of your equity and '
                'still pass.',
            'A band has to be achievable to be enforced: five holdings must '
                'sum to 100% of their sleeve, so the ceiling widens to 20% '
                'for them. A lone holding in a category is never trimmed — it '
                'is the whole sleeve by definition.',
            'The CATEGORY band is separate: each of the four is held within '
                '${_pts(policy['deviation_pct'])} of its target share of the '
                'whole book. Correct that with where the next contribution '
                'goes before correcting it with a sale.',
            'The book is opened on a schedule, on a boom, on a crash, on '
                'drift, or on a threshold you set — but a trade is only '
                'proposed for holdings actually outside their band. That is '
                'the low-turnover combination.',
            'GAIN is what the sale realises; TAX is what is withheld at source '
                'on it; NET is what actually reaches the account and is all '
                'you can reinvest. Units held over a year are sold first '
                'because they are taxed less.',
          ],
          action: 'Fund the top-ups with new money first. Only sell for the '
              'part new money cannot cover, and trim from the largest breach '
              'down.',
        ),
        _StrategyPicker(preset: preset),
        _AddFund(contribution: _map(data['contribution']), preset: preset),
        _SettingsPanel(policy: policy, settings: settings),
        _TriggerStrip(
          triggers: triggers,
          market: market,
          crash: crash,
          volatility: volatility,
        ),
        _AllocationTable(allocation: allocation),
        _CategorySections(
          actions: actions,
          preset: preset,
          allocation: allocation,
          settings: settings,
          policy: policy,
        ),
        if (totals['trims'] != 0 || totals['adds'] != 0)
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
            child: _Totals(totals: totals),
          ),
        _Strategy(notes: _list(data['strategy'])),
        // Last, and closed: the plan is the thing to act on, the history is
        // the thing to check it against.
        const _TradeHistory(),
        _MarkDone(lastDue: triggers['next_calendar_due']?.toString()),
      ]),
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  SETTINGS
// ══════════════════════════════════════════════════════════════

/// The policy controls, collapsed by default.
///
/// Collapsed because the plan is the point of the screen and the settings are
/// something you touch twice a year. Sliders preview live and only commit on
/// release, so dragging does not fire a save (and a re-plan) per pixel.
class _SettingsPanel extends ConsumerStatefulWidget {
  final Map<String, dynamic> policy;
  final Map<String, dynamic> settings;

  const _SettingsPanel({required this.policy, required this.settings});

  @override
  ConsumerState<_SettingsPanel> createState() => _SettingsPanelState();
}

class _SettingsPanelState extends ConsumerState<_SettingsPanel> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final policy = widget.policy;
    final settings = widget.settings;
    final low = _d(policy['min_weight_pct']);
    final high = _d(policy['max_weight_pct']);
    final drift = _d(policy['deviation_pct']);
    final enabled = _list(settings['all_triggers']);
    final on = ((settings['triggers'] as List?) ?? const [])
        .map((e) => e.toString())
        .toSet();

    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: c.bg2,
        border: Border(bottom: BorderSide(color: c.bd)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        InkWell(
          onTap: () => setState(() => _open = !_open),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
            child: Row(children: [
              Icon(LucideIcons.sliders, size: 13, color: c.t3),
              const SizedBox(width: 8),
              Text('REBALANCE SETTINGS', style: AppTextStyles.labelXs(c.t2)),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Band ${low.toStringAsFixed(0)}–${high.toStringAsFixed(0)}% '
                  'of category · drift ±${drift.toStringAsFixed(0)} pts · '
                  '${on.length} of ${enabled.length} triggers armed',
                  style: AppTextStyles.captionXs(c.t4),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Icon(_open ? LucideIcons.chevronUp : LucideIcons.chevronDown,
                  size: 14, color: c.t3),
            ]),
          ),
        ),
        if (_open)
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Material(color: Colors.transparent, child: SwitchListTile(
                    title: const Text('Sell long-term holdings only'),
                    subtitle: const Text('Protect short-term and unknown purchase dates. Disable to include short-term sales with estimated tax.'),
                    value: settings['long_term_only'] != false,
                    onChanged: (value) => ref.read(rebalanceSettingsProvider.notifier).save(longTermOnly: value),
                  )),
                  const Text('Estimated tax rates % (before cess; confirm instrument-specific treatment)'),
                  Wrap(spacing: 12, runSpacing: 8, children: [
                    for (final entry in _map(settings['tax_rates']).entries)
                      SizedBox(width: 210, child: TextFormField(
                        key: ValueKey('${entry.key}:${entry.value}'),
                        initialValue: entry.value.toString(),
                        decoration: InputDecoration(labelText: entry.key.replaceAll('_', ' ')),
                        keyboardType: TextInputType.number,
                        onFieldSubmitted: (text) {
                          final value = double.tryParse(text);
                          if (value == null || !value.isFinite || value < 0 || value > 100) return;
                          final rates = <String, double>{for (final e in _map(settings['tax_rates']).entries) e.key: _d(e.value)};
                          rates[entry.key] = value;
                          ref.read(rebalanceSettingsProvider.notifier).save(taxRates: rates);
                        },
                      )),
                  ]),
                  _BandSlider(low: low, high: high),
                  const SizedBox(height: 14),
                  _DriftSlider(value: drift),
                  const SizedBox(height: 16),
                  _cadenceRow(context, settings),
                  const SizedBox(height: 14),
                  _label(context, 'REBALANCE TRIGGERS',
                      'A trigger that is switched off is not watching. '
                          'Turning one on is what lets it open the book.'),
                  const SizedBox(height: 7),
                  Wrap(spacing: 6, runSpacing: 6, children: [
                    for (final t in enabled)
                      DFilterChip(
                        label: (t['label'] ?? t['name']).toString().toUpperCase(),
                        selected: on.contains(t['name']),
                        tone: c.accent,
                        onTap: () => ref
                            .read(rebalanceSettingsProvider.notifier)
                            .toggleTrigger(t['name'].toString()),
                      ),
                  ]),
                  const SizedBox(height: 16),
                  _label(context, 'MARKET BOOM · trim threshold',
                      'How strong a year counts as a boom. The other four '
                          'boom readings are fixed; three of five fires it.'),
                  const SizedBox(height: 7),
                  _ThresholdChips(
                    values: const [10, 15, 20, 25, 30],
                    current: _d(policy['boom_gain_pct']),
                    tone: c.gold,
                    prefix: '+',
                    onPick: (v) => ref
                        .read(rebalanceSettingsProvider.notifier)
                        .save(boomGainPct: v),
                  ),
                  const SizedBox(height: 14),
                  _label(context, 'MARKET CRASH · top-up threshold',
                      'How deep a fall from the 52-week high counts as a '
                          'crash. A crash is the BUY side of the same rule.'),
                  const SizedBox(height: 7),
                  _ThresholdChips(
                    values: const [10, 15, 20, 25, 30],
                    current: _d(policy['crash_drop_pct']),
                    tone: c.dn,
                    prefix: '−',
                    onPick: (v) => ref
                        .read(rebalanceSettingsProvider.notifier)
                        .save(crashDropPct: v),
                  ),
                  const SizedBox(height: 14),
                  _label(context, 'VOLATILITY · annualised',
                      'The Nifty normally runs at 13–16%. A spike argues for '
                          'a wider tolerance and fewer trades, not a trim.'),
                  const SizedBox(height: 7),
                  _ThresholdChips(
                    values: const [18, 22, 25, 30, 35],
                    current: _d(policy['vol_trigger_pct']),
                    tone: c.blue,
                    onPick: (v) => ref
                        .read(rebalanceSettingsProvider.notifier)
                        .save(volTriggerPct: v),
                  ),
                  const SizedBox(height: 16),
                  _label(context, 'YOUR OWN THRESHOLDS',
                      'Open the book when the whole portfolio is up or down '
                          'by this much. Leave a threshold off and its '
                          'trigger has nothing to fire against.'),
                  const SizedBox(height: 8),
                  Row(children: [
                    Expanded(
                      child: _CustomThreshold(
                        label: 'PORTFOLIO GAIN OVER',
                        value: policy['gain_trigger_pct'],
                        tone: c.up,
                        onSet: (v) => ref
                            .read(rebalanceSettingsProvider.notifier)
                            .save(gainTriggerPct: v),
                        onClear: () => ref
                            .read(rebalanceSettingsProvider.notifier)
                            .save(clearGainTrigger: true),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: _CustomThreshold(
                        label: 'PORTFOLIO LOSS OVER',
                        value: policy['loss_trigger_pct'],
                        tone: c.dn,
                        onSet: (v) => ref
                            .read(rebalanceSettingsProvider.notifier)
                            .save(lossTriggerPct: v),
                        onClear: () => ref
                            .read(rebalanceSettingsProvider.notifier)
                            .save(clearLossTrigger: true),
                      ),
                    ),
                  ]),
                ]),
          ),
      ]),
    );
  }

  Widget _cadenceRow(BuildContext context, Map<String, dynamic> settings) {
    final c = context.colors;
    final current =
        RebalanceCadenceMeta.fromWire(settings['cadence']?.toString());
    return Row(children: [
      Text('CALENDAR REVIEW', style: AppTextStyles.labelXs(c.t3)),
      const SizedBox(width: 10),
      for (final option in RebalanceCadence.values)
        Padding(
          padding: const EdgeInsets.only(right: 6),
          child: DFilterChip(
            label: option.label,
            selected: current == option,
            tone: c.accent,
            onTap: () => ref
                .read(rebalanceSettingsProvider.notifier)
                .save(cadence: option.wire),
          ),
        ),
    ]);
  }

  Widget _label(BuildContext context, String title, String help) {
    final c = context.colors;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title, style: AppTextStyles.labelXs(c.t3)),
      const SizedBox(height: 2),
      Text(help, style: AppTextStyles.captionXs(c.t4)),
    ]);
  }
}

/// The per-asset band, as one range slider over 0–100.
///
/// A range slider rather than two, because the two ends are one decision and
/// a range control makes the gap between them the thing you are setting.
class _BandSlider extends ConsumerStatefulWidget {
  final double low, high;
  const _BandSlider({required this.low, required this.high});

  @override
  ConsumerState<_BandSlider> createState() => _BandSliderState();
}

class _BandSliderState extends ConsumerState<_BandSlider> {
  RangeValues? _dragging;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final values = _dragging ??
        RangeValues(widget.low.clamp(0, 100), widget.high.clamp(0, 100));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Text('PER-ASSET BAND', style: AppTextStyles.labelXs(c.t3)),
        const SizedBox(width: 8),
        Text(
            '${values.start.toStringAsFixed(0)}% – '
            '${values.end.toStringAsFixed(0)}% of its category',
            style: AppTextStyles.monoBold(c.accent).copyWith(fontSize: 12)),
      ]),
      const SizedBox(height: 2),
      Text(
          'The floor exists because a position too small to matter still '
          'costs attention and brokerage. The ceiling is concentration risk.',
          style: AppTextStyles.captionXs(c.t4)),
      SliderTheme(
        data: SliderTheme.of(context).copyWith(
          trackHeight: 3,
          activeTrackColor: c.accent,
          inactiveTrackColor: c.bd,
          thumbColor: c.accent,
          overlayColor: c.accent.withValues(alpha: 0.12),
          rangeThumbShape:
              const RoundRangeSliderThumbShape(enabledThumbRadius: 7),
          showValueIndicator: ShowValueIndicator.onDrag,
          valueIndicatorColor: c.accent,
        ),
        child: RangeSlider(
          values: values,
          min: 0,
          max: 100,
          divisions: 100,
          labels: RangeLabels('${values.start.toStringAsFixed(0)}%',
              '${values.end.toStringAsFixed(0)}%'),
          // Preview while dragging, save once — otherwise every pixel of the
          // drag would write settings and re-plan the whole portfolio.
          onChanged: (v) {
            setState(() => _dragging = v);
            ref
                .read(rebalanceBandPreviewProvider.notifier)
                .setBand(v.start, v.end);
          },
          onChangeEnd: (v) async {
            await ref.read(rebalanceSettingsProvider.notifier).save(
                minWeightPct: v.start, maxWeightPct: v.end);
            ref.read(rebalanceBandPreviewProvider.notifier).clear();
            if (mounted) setState(() => _dragging = null);
          },
        ),
      ),
    ]);
  }
}

/// How far a whole category may drift from its target before it is worth a
/// trade, in percentage points of the book.
class _DriftSlider extends ConsumerStatefulWidget {
  final double value;
  const _DriftSlider({required this.value});

  @override
  ConsumerState<_DriftSlider> createState() => _DriftSliderState();
}

class _DriftSliderState extends ConsumerState<_DriftSlider> {
  double? _dragging;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final value = (_dragging ?? widget.value).clamp(0, 50).toDouble();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Text('CATEGORY DRIFT ALLOWED', style: AppTextStyles.labelXs(c.t3)),
        const SizedBox(width: 8),
        Text('± ${value.toStringAsFixed(0)} points of the whole book',
            style: AppTextStyles.monoBold(c.cyan).copyWith(fontSize: 12)),
      ]),
      const SizedBox(height: 2),
      Text(
          'Five points on a 50% target is a tenth of the sleeve, which is '
          'about where the drift outweighs the tax of fixing it.',
          style: AppTextStyles.captionXs(c.t4)),
      SliderTheme(
        data: SliderTheme.of(context).copyWith(
          trackHeight: 3,
          activeTrackColor: c.cyan,
          inactiveTrackColor: c.bd,
          thumbColor: c.cyan,
          overlayColor: c.cyan.withValues(alpha: 0.12),
          thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 7),
          showValueIndicator: ShowValueIndicator.onDrag,
          valueIndicatorColor: c.cyan,
        ),
        child: Slider(
          value: value,
          min: 0,
          max: 50,
          divisions: 50,
          label: '±${value.toStringAsFixed(0)} pts',
          onChanged: (v) {
            setState(() => _dragging = v);
            ref.read(rebalanceBandPreviewProvider.notifier).setDeviation(v);
          },
          onChangeEnd: (v) async {
            await ref
                .read(rebalanceSettingsProvider.notifier)
                .save(deviationPct: v);
            ref.read(rebalanceBandPreviewProvider.notifier).clear();
            if (mounted) setState(() => _dragging = null);
          },
        ),
      ),
    ]);
  }
}

class _ThresholdChips extends StatelessWidget {
  final List<double> values;
  final double current;
  final Color tone;
  final String prefix;
  final ValueChanged<double> onPick;

  const _ThresholdChips({
    required this.values,
    required this.current,
    required this.tone,
    required this.onPick,
    this.prefix = '',
  });

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: 6,
        runSpacing: 6,
        children: [
          for (final v in values)
            DFilterChip(
              label: '$prefix${v.toStringAsFixed(0)}%',
              selected: (current - v).abs() < 0.01,
              tone: tone,
              onTap: () => onPick(v),
            ),
        ],
      );
}

/// One user-supplied percentage, with an explicit way to unset it.
class _CustomThreshold extends StatefulWidget {
  final String label;
  final dynamic value;
  final Color tone;
  final ValueChanged<double> onSet;
  final VoidCallback onClear;

  const _CustomThreshold({
    required this.label,
    required this.value,
    required this.tone,
    required this.onSet,
    required this.onClear,
  });

  @override
  State<_CustomThreshold> createState() => _CustomThresholdState();
}

class _CustomThresholdState extends State<_CustomThreshold> {
  late final TextEditingController _controller = TextEditingController(
      text: widget.value is num ? _trim(widget.value as num) : '');

  static String _trim(num v) =>
      v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toString();

  @override
  void didUpdateWidget(_CustomThreshold old) {
    super.didUpdateWidget(old);
    // Reflect a change made elsewhere (a clear, say) without stealing focus
    // mid-edit.
    final incoming = widget.value is num ? _trim(widget.value as num) : '';
    if (widget.value != old.value && incoming != _controller.text) {
      _controller.text = incoming;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _commit(String raw) {
    final text = raw.trim();
    if (text.isEmpty) {
      widget.onClear();
      return;
    }
    final parsed = double.tryParse(text);
    if (parsed == null || parsed <= 0) {
      // Not a threshold. Say nothing has been set rather than storing a zero
      // that would fire on every reading.
      widget.onClear();
      _controller.text = '';
      return;
    }
    widget.onSet(parsed);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final set = widget.value is num;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Expanded(
          child: Text(widget.label, style: AppTextStyles.labelXs(c.t3)),
        ),
        if (set)
          InkWell(
            onTap: () {
              _controller.text = '';
              widget.onClear();
            },
            child: Padding(
              padding: const EdgeInsets.all(2),
              child: Icon(LucideIcons.x, size: 12, color: c.t4),
            ),
          ),
      ]),
      const SizedBox(height: 4),
      SizedBox(
        height: 34,
        child: TextField(
          controller: _controller,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          style: AppTextStyles.monoBold(set ? widget.tone : c.t2)
              .copyWith(fontSize: 12),
          decoration: denseFieldDecoration(context,
              hint: 'not set', focusColor: widget.tone, prefix: '% '),
          onSubmitted: _commit,
          onTapOutside: (_) {
            FocusManager.instance.primaryFocus?.unfocus();
            _commit(_controller.text);
          },
        ),
      ),
    ]);
  }
}

// ══════════════════════════════════════════════════════════════
//  TRIGGERS & MARKET
// ══════════════════════════════════════════════════════════════

/// Why the book is open today — or why it is not.
class _TriggerStrip extends StatelessWidget {
  final Map<String, dynamic> triggers;
  final Map<String, dynamic> market;
  final Map<String, dynamic> crash;
  final Map<String, dynamic> volatility;

  const _TriggerStrip({
    required this.triggers,
    required this.market,
    required this.crash,
    required this.volatility,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final fired = _list(triggers['fired']);
    final considered = _list(triggers['considered']);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
      decoration: BoxDecoration(
        color: c.bg3,
        border: Border(bottom: BorderSide(color: c.bd)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _reading(
          context,
          label: 'BOOM',
          available: market['available'] == true,
          state: (market['heat'] ?? 'unknown').toString(),
          tone: switch (market['heat']) {
            'euphoric' || 'boom' => c.gold,
            'warm' => c.t2,
            'calm' => c.up,
            _ => c.t4,
          },
          reason: market['reason']?.toString(),
          benchmark: market['benchmark']?.toString(),
          // "Unknown" must not read as "calm": a dead index feed would
          // otherwise silently suppress a trigger the user armed.
          unavailable: 'No index data, so a boom cannot be ruled in or out. '
              'The calendar, band and drift rules still apply.',
          signals: _list(market['signals']),
        ),
        const SizedBox(height: 8),
        _reading(
          context,
          label: 'CRASH',
          available: crash['available'] == true,
          state: (crash['severity'] ?? 'unknown').toString(),
          tone: switch (crash['severity']) {
            'capitulation' || 'crash' => c.dn,
            'correction' => c.gold,
            'stable' => c.up,
            _ => c.t4,
          },
          reason: crash['reason']?.toString(),
          benchmark: crash['benchmark']?.toString(),
          unavailable: 'No index data, so a fall cannot be measured.',
          signals: _list(crash['signals']),
        ),
        const SizedBox(height: 8),
        Row(children: [
          Text('VOLATILITY', style: AppTextStyles.labelXs(c.t3)),
          const SizedBox(width: 8),
          if (volatility['available'] == true) ...[
            Text('${_d(volatility['vol_pct']).toStringAsFixed(1)}%',
                style: AppTextStyles.monoBold(
                        volatility['elevated'] == true ? c.gold : c.up)
                    .copyWith(fontSize: 12)),
            const SizedBox(width: 8),
            Expanded(
              child: Text(volatility['reason']?.toString() ?? '',
                  style: AppTextStyles.captionXs(c.t3),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
            ),
          ] else
            Expanded(
              child: Text(
                  'No volatility reading on the tape, so that trigger cannot '
                  'fire either way.',
                  style: AppTextStyles.captionXs(c.t4),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
            ),
        ]),
        const SizedBox(height: 10),
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('TRIGGERS', style: AppTextStyles.labelXs(c.t3)),
          const SizedBox(width: 8),
          Expanded(
            child: fired.isEmpty
                ? Text(
                    triggers['mode'] == 'manual'
                        ? 'Nothing is firing, but the book is open because you '
                            'asked to look. Next scheduled review '
                            '${triggers['next_calendar_due'] ?? 'once a first '
                                'rebalance is recorded'}.'
                        : 'Nothing is due. Next scheduled review '
                            '${triggers['next_calendar_due'] ?? 'once a first '
                                'rebalance is recorded'}.',
                    style: AppTextStyles.captionXs(c.t3))
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      for (final f in fired)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 2),
                          child: Text(
                            '· ${f['label'] ?? _triggerLabel(f['name']?.toString())}'
                            ' — ${f['detail'] ?? ''}',
                            style: AppTextStyles.captionXs(c.t2),
                          ),
                        ),
                    ],
                  ),
          ),
        ]),
        // A rule that is switched off and a rule that is on and quiet are
        // different states. Showing only what fired hides the difference, and
        // a user can end up believing a crash rule is watching when it is not.
        if (considered.any((r) => r['enabled'] == false)) ...[
          const SizedBox(height: 6),
          Row(children: [
            Icon(LucideIcons.bellOff, size: 11, color: c.t4),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                  'Not watching: '
                  '${considered.where((r) => r['enabled'] == false).map((r) => r['label'] ?? r['name']).join(' · ')}',
                  style: AppTextStyles.captionXs(c.t4),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis),
            ),
          ]),
        ],
      ]),
    );
  }

  Widget _reading(
    BuildContext context, {
    required String label,
    required bool available,
    required String state,
    required Color tone,
    required String unavailable,
    required List<Map<String, dynamic>> signals,
    String? reason,
    String? benchmark,
  }) {
    final c = context.colors;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Text(label, style: AppTextStyles.labelXs(c.t3)),
        const SizedBox(width: 8),
        Text(state.toUpperCase(),
            style: AppTextStyles.labelXs(tone)
                .copyWith(fontWeight: FontWeight.w700)),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            available
                ? '${reason ?? ''} (${benchmark ?? 'benchmark'})'
                : unavailable,
            style: AppTextStyles.captionXs(available ? c.t3 : c.t4),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ]),
      if (available && signals.isNotEmpty) ...[
        const SizedBox(height: 5),
        Wrap(spacing: 6, runSpacing: 6, children: [
          for (final s in signals) _SignalChip(signal: s, tone: tone),
        ]),
      ],
    ]);
  }

  String _triggerLabel(String? name) => switch (name) {
        'first_run' => 'First run',
        'calendar_semiannual' => 'Six-month review',
        'calendar_annual' => 'Annual review',
        _ => name ?? 'Trigger',
      };
}

class _SignalChip extends StatelessWidget {
  final Map<String, dynamic> signal;
  final Color tone;
  const _SignalChip({required this.signal, required this.tone});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final known = signal['known'] == true;
    final hit = signal['hit'] == true;
    // Three states, not two: a signal that could not be read is not a signal
    // that came back negative.
    final colour = !known ? c.t4 : (hit ? tone : c.t3);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: hit ? tone.withValues(alpha: 0.10) : Colors.transparent,
        borderRadius: BorderRadius.circular(4),
        border:
            Border.all(color: hit ? tone.withValues(alpha: 0.30) : c.bd),
      ),
      child: Text(
        '${!known ? '?' : (hit ? '●' : '○')} '
        '${signal['detail'] ?? signal['name'] ?? ''}',
        style: AppTextStyles.captionXs(colour),
      ),
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  CATEGORY ALLOCATION
// ══════════════════════════════════════════════════════════════

/// The four-way mix against its target — the second of the two bands.
class _AllocationTable extends ConsumerWidget {
  final Map<String, dynamic> allocation;
  const _AllocationTable({required this.allocation});

  static const _cols = [
    DenseCol('CATEGORY', 22, numeric: false),
    DenseCol('HOLDINGS', 10),
    DenseCol('VALUE', 16),
    DenseCol('CURRENT', 11),
    DenseCol('TARGET', 11),
    DenseCol('DRIFT', 11),
    DenseCol('MOVE', 19),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final rows = _list(allocation['rows']);
    final set = allocation['targets_set'] == true;

    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(LucideIcons.chartPie, size: 13, color: c.cyan),
          const SizedBox(width: 7),
          Text('ASSET MIX', style: AppTextStyles.labelXs(c.t2)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              set
                  ? 'Each category within ±${_d(allocation['tolerance_pct']).toStringAsFixed(0)} '
                      'points of the target you set.'
                  // Handing a new user a 50/30/10/10 target they never chose
                  // would fire the drift rule on day one, and a plan that is
                  // permanently due is one the reader learns to ignore.
                  : 'No target set yet, so today\'s split IS the target and '
                      'nothing has drifted. Set targets to start measuring.',
              style: AppTextStyles.captionXs(set ? c.t3 : c.t4),
            ),
          ),
          _TargetEditor(rows: rows, targetsSet: set),
        ]),
        if (allocation['targets_rescaled'] == true) ...[
          const SizedBox(height: 4),
          Text(
              'Your targets did not add up to 100%, so they have been scaled '
              'to. The proportions between them are unchanged.',
              style: AppTextStyles.captionXs(c.gold)),
        ],
        const SizedBox(height: 8),
        denseColumnHeader(context, _cols),
        ...rows.asMap().entries.map((e) => DenseRow(
              cols: _cols,
              alt: e.key.isOdd,
              cells: _cells(context, e.value, set),
            )),
      ]),
    );
  }

  List<Widget> _cells(
      BuildContext context, Map<String, dynamic> row, bool targetsSet) {
    final c = context.colors;
    final drift = _d(row['drift_pct']);
    final over = row['status'] == 'over';
    final within = row['status'] == 'within';
    final manual = _d(row['manual_value']);
    final amount = _d(row['amount']);
    return [
      Row(children: [
        Expanded(
          child: Text(row['label']?.toString() ?? '',
              style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 11.5),
              maxLines: 1,
              overflow: TextOverflow.ellipsis),
        ),
        // A category that is partly hand-entered cannot be fully traded from
        // here, and the row should say so where the eye already is.
        if (manual > 0)
          Tooltip(
            message: '₹${_fullValue(manual)} of this is entered by hand on '
                'the Allocation screen, so it has no units or price to trade.',
            child: Icon(LucideIcons.pencil, size: 11, color: c.t4),
          ),
      ]),
      denseNum(context, '${row['positions'] ?? 0}', c.t3),
      denseNum(context, '₹${_fullValue(_d(row['value']))}', c.t1,
          bold: true),
      denseNum(context, '${_d(row['current_pct']).toStringAsFixed(1)}%', c.t2),
      denseNum(context, '${_d(row['target_pct']).toStringAsFixed(1)}%',
          targetsSet ? c.cyan : c.t4),
      within
          ? denseNum(context, '—', c.t4)
          : denseSignedNum(context, drift, over ? c.dn : c.up,
              decimals: 1, suffix: ' pts'),
      within
          ? Text(targetsSet ? 'On target' : '—',
              style: AppTextStyles.labelXs(c.t4),
              textAlign: TextAlign.right,
              maxLines: 1)
          : Text(
              '${amount >= 0 ? 'Add' : 'Reduce'} '
              '₹${_fullValue(amount.abs())}',
              style: AppTextStyles.labelXs(amount >= 0 ? c.up : c.dn),
              textAlign: TextAlign.right,
              maxLines: 1),
    ];
  }
}

/// Set or clear the four category targets.
class _TargetEditor extends ConsumerWidget {
  final List<Map<String, dynamic>> rows;
  final bool targetsSet;

  const _TargetEditor({required this.rows, required this.targetsSet});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      DFilterChip(
        label: targetsSet ? 'EDIT TARGETS' : 'SET TARGETS',
        selected: targetsSet,
        tone: c.cyan,
        onTap: () => _open(context, ref),
      ),
    ]);
  }

  Future<void> _open(BuildContext context, WidgetRef ref) async {
    final c = context.colors;
    final values = <String, double>{
      for (final r in rows)
        r['category'].toString(): _d(targetsSet
            ? r['target_pct']
            // Seed from today's split rather than from a house default, so
            // the dialog opens on the user's own portfolio.
            : r['current_pct']),
    };
    final labels = <String, String>{
      for (final r in rows) r['category'].toString(): r['label'].toString(),
    };

    await showDialog<void>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) {
          final total = values.values.fold(0.0, (a, b) => a + b);
          return AlertDialog(
            backgroundColor: c.bg1,
            title: Text('Target asset mix',
                style: AppTextStyles.bodyBold(c.t1)),
            content: SizedBox(
              width: 420,
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Text(
                    'What share of the whole book each category should be. '
                    'They do not have to add up to 100 — anything else is '
                    'scaled, keeping the proportions between them.',
                    style: AppTextStyles.captionXs(c.t3)),
                const SizedBox(height: 14),
                for (final entry in values.entries)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Row(children: [
                      SizedBox(
                        width: 110,
                        child: Text(labels[entry.key] ?? entry.key,
                            style: AppTextStyles.label(c.t2)),
                      ),
                      Expanded(
                        child: Slider(
                          value: entry.value.clamp(0, 100),
                          min: 0,
                          max: 100,
                          divisions: 100,
                          activeColor: c.cyan,
                          inactiveColor: c.bd,
                          onChanged: (v) =>
                              setState(() => values[entry.key] = v),
                        ),
                      ),
                      SizedBox(
                        width: 46,
                        child: Text('${entry.value.toStringAsFixed(0)}%',
                            style: AppTextStyles.monoBold(c.cyan)
                                .copyWith(fontSize: 12),
                            textAlign: TextAlign.right),
                      ),
                    ]),
                  ),
                const SizedBox(height: 6),
                Text(
                    total <= 0
                        ? 'Everything is zero, so there is no mix to hold.'
                        : 'Adds up to ${total.toStringAsFixed(0)}%'
                            '${(total - 100).abs() < 0.5 ? '' : ' — will be scaled to 100%'}',
                    style: AppTextStyles.captionXs(
                        (total - 100).abs() < 0.5 ? c.t4 : c.gold)),
              ]),
            ),
            actions: [
              if (targetsSet)
                TextButton(
                  onPressed: () async {
                    // Back to "no target", which is not the same as a target
                    // of today's split: it also stops the drift rule firing
                    // as the portfolio moves.
                    await ref
                        .read(rebalanceSettingsProvider.notifier)
                        .save(categoryTargets: const {});
                    if (context.mounted) Navigator.pop(context);
                  },
                  child: Text('Clear', style: TextStyle(color: c.t3)),
                ),
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: Text('Cancel', style: TextStyle(color: c.t3)),
              ),
              TextButton(
                onPressed: values.values.every((v) => v <= 0)
                    ? null
                    : () async {
                        await ref
                            .read(rebalanceSettingsProvider.notifier)
                            .save(categoryTargets: values);
                        if (context.mounted) Navigator.pop(context);
                      },
                child: Text('Save', style: TextStyle(color: c.cyan)),
              ),
            ],
          );
        },
      ),
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  ASSET LISTS
// ══════════════════════════════════════════════════════════════

/// One expandable section per category, listing every holding in it.
///
/// The complete list, not just the breaches: the point of the section is to
/// let the user see and pick what is in scope, and a list that hides the
/// holdings inside their band cannot be used to select from.
class _CategorySections extends ConsumerWidget {
  final Map<String, dynamic> preset;
  final List<Map<String, dynamic>> actions;
  final Map<String, dynamic> allocation;
  final Map<String, dynamic> settings;
  final Map<String, dynamic> policy;

  const _CategorySections({
    required this.actions,
    required this.preset,
    required this.allocation,
    required this.settings,
    required this.policy,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rows = _list(allocation['rows']);
    if (actions.isEmpty) {
      return Padding(
        padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
        child: _NothingToWeigh(),
      );
    }
    final all = rows.map((r) => r['category'].toString()).toList();
    final selectedCats =
        (settings['selected_categories'] as List?)?.cast<String>();

    return Column(children: [
      for (final row in rows)
        _CategorySection(
          preset: preset,
          category: row['category'].toString(),
          label: row['label'].toString(),
          holdings: actions
              .where((a) => a['category'] == row['category'])
              .toList()
            ..sort(_byUrgency),
          allCategories: all,
          categorySelected:
              selectedCats == null || selectedCats.contains(row['category']),
          settings: settings,
          policy: policy,
        ),
    ]);
  }

  /// Breaches first, largest first, then the holds by size. The instruction
  /// belongs at the top; the confirmations belong underneath it.
  static int _byUrgency(Map<String, dynamic> a, Map<String, dynamic> b) {
    int rank(Map<String, dynamic> r) => switch (r['action']) {
          'TRIM' => 0,
          'ADD' => 1,
          'SKIP' => 2,
          'REVIEW' => 3,
          _ => 4,
        };
    final byRank = rank(a).compareTo(rank(b));
    if (byRank != 0) return byRank;
    return _d(b['value']).compareTo(_d(a['value']));
  }
}

class _CategorySection extends ConsumerStatefulWidget {
  final Map<String, dynamic> preset;
  final String category, label;
  final List<Map<String, dynamic>> holdings;
  final List<String> allCategories;
  final bool categorySelected;
  final Map<String, dynamic> settings;
  final Map<String, dynamic> policy;

  const _CategorySection({
    required this.preset,
    required this.category,
    required this.label,
    required this.holdings,
    required this.allCategories,
    required this.categorySelected,
    required this.settings,
    required this.policy,
  });

  @override
  ConsumerState<_CategorySection> createState() => _CategorySectionState();
}

class _CategorySectionState extends ConsumerState<_CategorySection> {
  bool? _open;

  // Each category is its own 100%. There is deliberately no "share of the
  // whole book" column here: the band is enforced against the CATEGORY, so
  // showing both invites reading a stock's weight against the funds — the one
  // comparison the band is designed not to make. Cross-category belongs to
  // the ASSET MIX table above.
  /// The columns the CHOSEN rule can actually act on.
  ///
  /// A long-term-units column under a strategy that never sells, or a momentum
  /// rank under one that funds by shortfall, is a number the reader cannot
  /// use — and a column that means nothing is worse than a missing one,
  /// because it invites a decision the rule will not honour.
  ///
  ///   1Y+ QTY  only when the rule can sell (S3, S4, S7, S8, S10, M1, Custom)
  ///   RANK     only when it funds by momentum or by weakness (S5, S9, M1)
  ///
  /// The row reads left to right as a ledger entry: what was held, what the
  /// trade is, what is left. Showing only the closing weight would hide the
  /// move; showing only the opening one would hide its effect.
  List<DenseCol> _columns() {
    final showLt = widget.preset['shows_long_term_units'] != false;
    final showRank = widget.preset['shows_rank'] == true;
    final rest = <DenseCol>[
      if (showRank) const DenseCol('#', 4),
      const DenseCol('HELD BEFORE', 6),
      if (showLt) const DenseCol('1Y+ QTY', 6),
      const DenseCol('FILL', 6),
      const DenseCol('VALUE BEFORE', 10),
      const DenseCol('GAIN/LOSS', 7),
      const DenseCol('W% BEFORE', 6),
      // Right-aligned like the numbers around it. Left-aligned, its text sat
      // flush against the right-aligned percent before it, so "22.00% HOLD"
      // read as one field instead of two columns.
      const DenseCol('ACTION', 7),
      const DenseCol('BOUGHT', 5),
      const DenseCol('SOLD', 5),
      const DenseCol('SOLD % OF HELD', 7),
      const DenseCol('HELD AFTER', 6),
      const DenseCol('W% AFTER', 6),
      const DenseCol('NET CASH +/−', 10),
    ];
    // The name column absorbs whatever the optional columns leave, so the row
    // always fills the width and the numbers keep a fixed position across
    // presets — a column that shifts sideways when you change strategy is
    // harder to read than a name that truncates.
    final used = rest.fold<int>(3, (sum, col) => sum + col.flex);
    return [
      const DenseCol('', 3, numeric: false),
      DenseCol('ASSET', (100 - used).clamp(12, 40), numeric: false),
      ...rest,
    ];
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final holdings = widget.holdings;
    final breaches = holdings
        .where((h) => h['action'] == 'TRIM' || h['action'] == 'ADD')
        .length;
    // Outside its band, but nothing is being proposed today.
    final waiting = holdings
        .where((h) =>
            h['status'] != 'within' &&
            h['action'] != 'TRIM' &&
            h['action'] != 'ADD')
        .length;
    // Open whenever the category holds anything: the complete list is what
    // the user selects from, and folding a quiet category hides the holdings
    // they came here to tick.
    final open = _open ?? holdings.isNotEmpty;
    final cols = _columns();
    final selected = widget.categorySelected;

    return Container(
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: c.bd)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        InkWell(
          onTap: () => setState(() => _open = !open),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 9, 14, 9),
            child: Row(children: [
              // Category-wise selection: one tick puts every holding in it
              // into or out of scope.
              _Tick(
                on: selected,
                tone: c.accent,
                onTap: () => ref
                    .read(rebalanceSettingsProvider.notifier)
                    .toggleCategory(widget.category, widget.allCategories),
              ),
              const SizedBox(width: 9),
              Text(widget.label.toUpperCase(),
                  style: AppTextStyles.labelXs(selected ? c.t1 : c.t4)
                      .copyWith(fontWeight: FontWeight.w700)),
              const SizedBox(width: 8),
              Text(
                  '${holdings.length} '
                  '${holdings.length == 1 ? 'holding' : 'holdings'}',
                  style: AppTextStyles.captionXs(c.t4)),
              const SizedBox(width: 8),
              if (breaches > 0)
                AppBadge(
                    text: '$breaches TO TRADE', variant: BadgeVariant.gold)
              // A breach whose trade is deferred — short-term units, or a
              // top-up below the minimum ticket — is still a breach. Counting
              // only proposed TRADES and then printing "all inside their band"
              // told the user the opposite of what the rows underneath showed.
              else if (waiting > 0)
                AppBadge(
                    text: '$waiting OUT OF BAND · NO TRADE YET',
                    variant: BadgeVariant.hold)
              // An empty category has nothing in a band to be inside of, and
              // saying otherwise made three of the four categories vouch for
              // holdings that do not exist.
              else if (holdings.isEmpty)
                Text('nothing held yet',
                    style: AppTextStyles.captionXs(c.t4))
              else
                Text('all inside their band',
                    style: AppTextStyles.captionXs(c.up)),
              const Spacer(),
              if (!selected)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: Text('NOT IN THIS REBALANCE',
                      style: AppTextStyles.captionXs(c.t4)),
                ),
              Icon(open ? LucideIcons.chevronUp : LucideIcons.chevronDown,
                  size: 14, color: c.t3),
            ]),
          ),
        ),
        if (open)
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
            child: holdings.isEmpty
                ? _emptyCategory(context)
                : Column(children: [
                    denseColumnHeader(context, cols),
                    ...holdings.asMap().entries.map((e) {
                      final cells = _cells(context, e.value, holdings);
                      // DenseRow indexes cells BY COLUMN, so a surplus cell is
                      // dropped in silence — the recommendation would simply
                      // disappear. With optional columns on both sides of the
                      // list that is an easy mistake to make and an invisible
                      // one to have made, so it is asserted in debug.
                      assert(
                          cells.length == cols.length,
                          'Column/cell mismatch for '
                          '${widget.preset['id']}: ${cols.length} columns, '
                          '${cells.length} cells');
                      return DenseRow(
                          cols: cols, alt: e.key.isOdd, cells: cells);
                    }),
                  ]),
          ),
      ]),
    );
  }

  Widget _emptyCategory(BuildContext context) {
    final c = context.colors;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 12),
      decoration: BoxDecoration(
        color: c.bg3,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: c.bd),
      ),
      child: Text(
          'Nothing here yet. Holdings are sorted into this category '
          'automatically from their name and scheme category; gold and debt '
          'you track by hand appear once entered on the Allocation screen.',
          style: AppTextStyles.captionXs(c.t4)),
    );
  }

  List<Widget> _cells(BuildContext context, Map<String, dynamic> a,
      List<Map<String, dynamic>> siblings) {
    final c = context.colors;
    final tradable = a['tradable'] == true;
    final selected = a['selected'] == true;
    final note = a['note']?.toString();

    return [
      // Individual selection, within a selected category.
      tradable
          ? _Tick(
              on: selected,
              tone: c.accent,
              onTap: () => ref
                  .read(rebalanceSettingsProvider.notifier)
                  .toggleAsset(
                    a['key'].toString(),
                    siblings
                        .where((s) => s['tradable'] == true)
                        .map((s) => s['key'].toString())
                        .toList(),
                  ),
            )
          : Icon(LucideIcons.pencil, size: 11, color: c.t4),
      Row(children: [
        Expanded(
          child: Text(a['name']?.toString() ?? a['key']?.toString() ?? '—',
              style: AppTextStyles.bodyBold(selected ? c.t1 : c.t4)
                  .copyWith(fontSize: 11.5),
              maxLines: 1,
              overflow: TextOverflow.ellipsis),
        ),
        // A lot about to turn long-term is the one piece of timing advice on
        // this screen, so it travels with the row rather than in a footnote.
        if (note != null)
          Tooltip(
            message: note,
            child: Icon(LucideIcons.hourglass, size: 12, color: c.gold),
          ),
      ]),
      if (widget.preset['shows_rank'] == true)
        denseNum(context, '${a['deploy_rank'] ?? '—'}',
            (a['deploy_rank'] is num && a['deploy_rank'] <= 3)
                ? c.accent
                : c.t4),
      denseNum(context, _qty(a['held_units']), c.t2),
      // The number that makes "Wait for long term" checkable. Tinted gold on
      // exactly the rows where it is the binding constraint, so the eye lands
      // on the cause rather than only on the verdict.
      if (widget.preset['shows_long_term_units'] != false)
        denseNum(context, _qty(a['long_term_units']),
            a['action'] == 'WAIT' ? c.gold : c.t3),
      // The price the trade is written at. A row proposing nothing has no
      // fill, and printing today's quote there would look like an execution.
      _traded(a)
          ? denseNum(context, _d(a['price']).toStringAsFixed(2), c.t2)
          : _dash(context),
      denseNum(context, '₹${_fullValue(_d(a['value']))}', c.t1, bold: true),
      // None, not zero: a holding whose cost never made it into the app has
      // no return, and 0% would read as "flat".
      a['gain_pct'] is num
          ? denseSignedNum(context, _d(a['gain_pct']),
              context.pnlColor(_d(a['gain_pct'])),
              decimals: 1, suffix: '%')
          : _dash(context),
      // The weight the band is judged against, and the place to change that
      // band — the number and the rule that governs it belong together.
      InkWell(
        onTap: () async {
          final controller = TextEditingController(text: _d(a['band']?[1] ?? 10).toStringAsFixed(1));
          final limit = await showDialog<double>(context: context, builder: (dialogContext) => AlertDialog(
            title: Text('Maximum allocation: ${a['name']}'),
            content: TextField(controller: controller, keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Maximum % of this category (0-100)', helperText: 'Example: 20 allows accumulation up to 20%')),
            actions: [TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cancel')),
              TextButton(onPressed: () { final value = double.tryParse(controller.text); if (value != null && value.isFinite && value >= 0 && value <= 100) Navigator.pop(dialogContext, value); }, child: const Text('Save'))],
          ));
          controller.dispose();
          if (limit != null) {
            final notifier = ref.read(rebalanceSettingsProvider.notifier);
            final saved = ref.read(rebalanceSettingsProvider).value;
            final limits = <String, double>{for (final e in _map(saved?['asset_limits']).entries) e.key: _d(e.value)};
            limits[a['key'].toString()] = limit;
            await notifier.save(assetLimits: limits);
          }
        },
        child: Tooltip(
          message: 'Maximum ${a['band']?[1] ?? 10}% of category. Tap to edit.',
          child: denseNum(context, '${_d(a['weight_pct']).toStringAsFixed(2)}%',
              a['status'] == 'within' ? c.t2 : c.gold),
        ),
      ),
      // The verdict, carrying the engine's own wording as its tooltip so the
      // reason for a HOLD is one hover away rather than off-screen.
      Tooltip(
        message: a['reason']?.toString() ?? '',
        child: Text(_actionLabel(a['action']),
            style: AppTextStyles.labelXs(_actionColor(context, a['action']))
                .copyWith(fontWeight: FontWeight.w700),
            textAlign: TextAlign.right,
            maxLines: 1,
            overflow: TextOverflow.ellipsis),
      ),
      _units(context, a['units_bought'], c.up),
      _units(context, a['units_sold'], c.dn),
      denseNum(context, '${_d(a['sold_pct_of_held']).toStringAsFixed(2)}%',
          _d(a['sold_pct_of_held']) > 0 ? c.dn : c.t4),
      denseNum(context, _qty(a['held_after']), c.t2),
      // Gold when the trade does not actually clear the breach. Trimming to
      // the band edge shrinks the book as well as the holding, so a position
      // can be sold into and still finish above its ceiling — without this
      // column that outcome is invisible.
      denseNum(context, '${_d(a['weight_after_pct']).toStringAsFixed(2)}%',
          _stillOutside(a) ? c.gold : c.t1,
          bold: true),
      Row(mainAxisAlignment: MainAxisAlignment.end, children: [
        Flexible(child: _netCash(context, a['net_cash'])),
        if (a['action'] == 'TRIM') ...[
          const SizedBox(width: 4),
          Tooltip(
            message: 'Realises ₹${_fullValue(_d(a['gain']))}, '
                '₹${_fullValue(_d(a['tax']))} withheld, '
                '₹${_fullValue(_d(a['net_proceeds']))} reaches the account.',
            child: Icon(LucideIcons.receipt, size: 11, color: c.gold),
          ),
        ],
      ]),
    ];
  }
}

/// BUY / SELL, in the ledger's vocabulary rather than the engine's. A reader
/// placing the order thinks in the broker's verbs, not in ADD and TRIM.
String _actionLabel(dynamic action) => switch (action) {
      'ADD' => 'BUY',
      'TRIM' => 'SELL',
      'WAIT' => 'WAIT',
      'SKIP' => 'SKIP',
      'REVIEW' => 'MANUAL',
      _ => 'HOLD',
    };

Color _actionColor(BuildContext context, dynamic action) {
  final c = context.colors;
  return switch (action) {
    'ADD' => c.up,
    'TRIM' => c.dn,
    'WAIT' || 'SKIP' || 'REVIEW' => c.gold,
    _ => c.t4,
  };
}

/// True once the plan writes a fill for this row — a proposal of zero units
/// has no price, and showing one would read as an execution.
bool _traded(Map<String, dynamic> a) =>
    _d(a['units_bought']) > 0 || _d(a['units_sold']) > 0;

/// Did the trade leave the holding outside the band it was judged against?
bool _stillOutside(Map<String, dynamic> a) {
  final band = a['band'];
  if (band is! List || band.length < 2) return false;
  final after = _d(a['weight_after_pct']);
  if (after <= 0) return false;
  return after > _d(band[1]) || after < _d(band[0]);
}

Widget _dash(BuildContext context) => Text('—',
    style: AppTextStyles.labelXs(context.colors.t4),
    textAlign: TextAlign.right);

/// Share counts on the two trade columns. Zero prints as 0, not as a dash:
/// this is a ledger, and "nothing bought" is a fact worth stating plainly
/// next to a row where something was sold.
Widget _units(BuildContext context, dynamic v, Color tone) {
  final q = _d(v);
  return denseNum(context, _qty(v) == '—' ? '0' : _qty(v),
      q > 0 ? tone : context.colors.t4,
      bold: q > 0);
}

/// Positive for a sale, negative for a purchase, blank-looking at zero.
Widget _netCash(BuildContext context, dynamic v) {
  final c = context.colors;
  final n = _d(v);
  if (n == 0) {
    return Text('0.00',
        style: AppTextStyles.labelXs(c.t4), textAlign: TextAlign.right);
  }
  return Text('${n > 0 ? '+' : '−'}₹${_fullValue(n.abs())}',
      style: AppTextStyles.monoBold(n > 0 ? c.up : c.dn).copyWith(fontSize: 11),
      textAlign: TextAlign.right,
      maxLines: 1);
}

/// A checkbox that reads at the density of this table.
class _Tick extends StatelessWidget {
  final bool on;
  final Color tone;
  final VoidCallback onTap;

  const _Tick({required this.on, required this.tone, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(3),
      child: Container(
        width: 14,
        height: 14,
        decoration: BoxDecoration(
          color: on ? tone.withValues(alpha: 0.18) : Colors.transparent,
          borderRadius: BorderRadius.circular(3),
          border: Border.all(color: on ? tone : c.bd2),
        ),
        child: on ? Icon(LucideIcons.check, size: 10, color: tone) : null,
      ),
    );
  }
}

class _Totals extends StatelessWidget {
  final Map<String, dynamic> totals;
  const _Totals({required this.totals});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final cash = _d(totals['cash_after_plan']);
    final skipped = totals['skipped'];
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: c.bg3,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: c.bd),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(spacing: 22, runSpacing: 8, children: [
          _stat(context, 'TO TRIM',
              '₹${_fullValue(_d(totals['sell_value']))}', c.dn),
          _stat(context, 'TO ADD',
              '₹${_fullValue(_d(totals['buy_value']))}', c.up),
          _stat(context, 'TAX WITHHELD',
              '₹${_fullValue(_d(totals['tax_estimated']))}', c.gold),
          _stat(context, 'NET FROM SALES',
              '₹${_fullValue(_d(totals['net_proceeds']))}', c.t1),
          _stat(
              context,
              cash >= 0 ? 'CASH LEFT OVER' : 'NEW MONEY NEEDED',
              '₹${_fullValue(cash.abs())}',
              cash >= 0 ? c.up : c.gold),
        ]),
        // The totals describe the SELECTED plan, so a narrowed selection has
        // to say so or the numbers look like the whole portfolio's.
        if (skipped is num && skipped > 0) ...[
          const SizedBox(height: 8),
          Text(
              'These totals cover the selected holdings only. $skipped '
              'breach${skipped == 1 ? '' : 'es'} outside your selection '
              'are not included.',
              style: AppTextStyles.captionXs(c.gold)),
        ],
      ]),
    );
  }

  Widget _stat(BuildContext context, String label, String value, Color tone) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: AppTextStyles.labelXs(context.colors.t3)),
        const SizedBox(height: 2),
        Text(value,
            style: AppTextStyles.monoBold(tone).copyWith(fontSize: 13)),
      ]);
}

class _NothingToWeigh extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 22, horizontal: 14),
      decoration: BoxDecoration(
        color: c.bg3,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: c.bd),
      ),
      child: Column(children: [
        Icon(LucideIcons.scale, size: 22, color: c.t3),
        const SizedBox(height: 8),
        Text('Nothing to weigh yet', style: AppTextStyles.bodyBold(c.t1)),
        const SizedBox(height: 4),
        Text(
            'Add stocks, funds, gold or debt and both bands will apply to '
            'them — each holding against its own category, and each category '
            'against your target mix.',
            style: AppTextStyles.captionXs(c.t3),
            textAlign: TextAlign.center),
      ]),
    );
  }
}

class _Strategy extends StatelessWidget {
  final List<Map<String, dynamic>> notes;
  const _Strategy({required this.notes});

  @override
  Widget build(BuildContext context) {
    if (notes.isEmpty) return const SizedBox.shrink();
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('HOW TO RUN THIS', style: AppTextStyles.labelXs(c.t3)),
        const SizedBox(height: 7),
        for (final n in notes)
          Padding(
            padding: const EdgeInsets.only(bottom: 7),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Container(
                width: 3,
                height: 30,
                margin: const EdgeInsets.only(right: 9, top: 1),
                decoration: BoxDecoration(
                  color: c.accent.withValues(alpha: 0.5),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              Expanded(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(n['title']?.toString() ?? '',
                          style: AppTextStyles.bodyBold(c.t1)
                              .copyWith(fontSize: 11.5)),
                      const SizedBox(height: 1),
                      Text(n['body']?.toString() ?? '',
                          style: AppTextStyles.captionXs(c.t3)),
                    ]),
              ),
            ]),
          ),
      ]),
    );
  }
}

class _MarkDone extends ConsumerStatefulWidget {
  final String? lastDue;
  const _MarkDone({this.lastDue});

  @override
  ConsumerState<_MarkDone> createState() => _MarkDoneState();
}

class _MarkDoneState extends ConsumerState<_MarkDone> {
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
      child: Row(children: [
        Expanded(
          child: Text(
            // Without this the calendar trigger can never stop firing, and a
            // permanently "due" plan is one the reader learns to ignore.
            'Recording a rebalance restarts the clock. Do it after you have '
            'actually placed the trades, not when you read the plan.',
            style: AppTextStyles.captionXs(c.t4),
          ),
        ),
        const SizedBox(width: 12),
        DFilterChip(
          label: _busy ? 'SAVING…' : 'MARK REBALANCED TODAY',
          selected: false,
          tone: c.accent,
          onTap: _busy ? null : _mark,
        ),
      ]),
    );
  }

  Future<void> _mark() async {
    setState(() => _busy = true);
    try {
      await ref.read(apiServiceProvider).markRebalanceDone();
      ref.invalidate(rebalancePlanProvider);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not record the rebalance: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }
}

/// STRATEGY PICKER — choose which backtested rule drives the plan.
///
/// One button per preset: S1–S10 from the 2011–2026 study, M1 the master
/// assembled from the mechanisms that replicated, and Custom for the sliders.
/// S10 is the default because it was the best of the ten on the measured
/// schedule; M1 beat it there but lost on an annual calendar, so it is offered
/// rather than defaulted to.
///
/// The measured return is shown on the chosen preset and labelled with what it
/// is: the record of a ten-stock NSE basket on one historical path, not a
/// projection for this portfolio. A number this prominent has to carry that
/// Where a preset placed among the sixteen, after tax.
///
/// Gold for the podium, plain otherwise. The denominator is always shown: "1"
/// alone invites the reading "first out of the ones worth showing", which is
/// not what it means.
class _RankBadge extends StatelessWidget {
  final int rank;
  final int of;
  const _RankBadge({required this.rank, required this.of});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final tone = rank <= 3 ? c.gold : c.t3;
    return Tooltip(
      message: 'Ranked $rank of $of by after-tax XIRR on the measured '
          'backtest — monthly Rs 10,000 into a ten-stock NSE basket, '
          '2011-2026. That is the record of that basket on that path, not a '
          'forecast for your portfolio.',
      child: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
        Text('RANK', style: AppTextStyles.labelXs(c.t4)),
        const SizedBox(height: 1),
        Row(crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic, children: [
          Text('$rank',
              style: AppTextStyles.monoBold(tone).copyWith(fontSize: 14)),
          Text(' / $of',
              style: AppTextStyles.labelXs(c.t4)),
        ]),
      ]),
    );
  }
}

/// The tradebook, one ledger page per date you traded.
///
/// The plan above says what to do next; this says what was already done and
/// what it did to the weights. Same columns, so the two read as one table seen
/// at two moments rather than as two unrelated reports.
///
/// Collapsed by default: building it costs a year of daily closes per holding,
/// and nobody needs it to answer "what do I buy today".
class _TradeHistory extends ConsumerStatefulWidget {
  const _TradeHistory();

  @override
  ConsumerState<_TradeHistory> createState() => _TradeHistoryState();
}

class _TradeHistoryState extends ConsumerState<_TradeHistory> {
  bool _open = false;

  static const _cols = [
    DenseCol('ASSET', 16, numeric: false),
    DenseCol('HELD BEFORE', 8),
    DenseCol('FILL', 7),
    DenseCol('VALUE BEFORE', 11),
    DenseCol('W% BEFORE', 8),
    DenseCol('ACTION', 7),
    DenseCol('BOUGHT', 6),
    DenseCol('SOLD', 6),
    DenseCol('SOLD % OF HELD', 8),
    DenseCol('HELD AFTER', 8),
    DenseCol('W% AFTER', 7),
    DenseCol('NET CASH +/−', 8),
  ];

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: c.bg2,
        border: Border(top: BorderSide(color: c.bd)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        InkWell(
          onTap: () => setState(() => _open = !_open),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 11, 14, 11),
            child: Row(children: [
              Icon(LucideIcons.history, size: 13, color: c.accent),
              const SizedBox(width: 7),
              Text('TRADE HISTORY', style: AppTextStyles.labelXs(c.t2)),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Your tradebook replayed, one page per date you traded — '
                  'what was held, what filled, and what it did to the weights.',
                  style: AppTextStyles.captionXs(c.t4),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Icon(_open ? LucideIcons.chevronUp : LucideIcons.chevronDown,
                  size: 14, color: c.t4),
            ]),
          ),
        ),
        if (_open) _body(context),
      ]),
    );
  }

  Widget _body(BuildContext context) {
    final c = context.colors;
    return ref.watch(rebalanceHistoryProvider).when(
          loading: () => const Padding(
            padding: EdgeInsets.symmetric(vertical: 28),
            child: DensePulseLoader(label: 'Replaying your tradebook…'),
          ),
          error: (e, _) => Padding(
            padding: const EdgeInsets.fromLTRB(14, 0, 14, 16),
            child: Text('Could not replay the tradebook: $e',
                style: AppTextStyles.captionXs(c.dn)),
          ),
          data: (data) => _pageView(context, data),
        );
  }

  Widget _pageView(BuildContext context, Map<String, dynamic> data) {
    final c = context.colors;
    final pages = _list(data['pages']);
    if (pages.isEmpty) {
      return Padding(
        padding: const EdgeInsets.fromLTRB(14, 0, 14, 16),
        child: Text(
            data['note']?.toString() ??
                'No equity transactions on file to replay.',
            style: AppTextStyles.captionXs(c.t4)),
      );
    }
    // -1 means "the most recent", so the section opens on today rather than on
    // whatever happened to be the first trade in the book.
    final want = ref.watch(rebalanceHistoryPageProvider);
    final at = (want < 0 || want >= pages.length) ? pages.length - 1 : want;
    final page = pages[at];
    final rows = _list(page['rows']);

    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _pager(context, at, pages),
        const SizedBox(height: 8),
        denseColumnHeader(context, _cols),
        ...rows.asMap().entries.map((e) => DenseRow(
              cols: _cols,
              alt: e.key.isOdd,
              cells: _cells(context, e.value),
            )),
        const SizedBox(height: 7),
        _footer(context, _map(page['totals']), data),
      ]),
    );
  }

  Widget _pager(BuildContext context, int at, List<Map<String, dynamic>> pages) {
    final c = context.colors;
    final totals = _map(pages[at]['totals']);
    void go(int to) => ref
        .read(rebalanceHistoryPageProvider.notifier)
        .show(to.clamp(0, pages.length - 1));

    return Row(children: [
      _PagerButton(
          icon: LucideIcons.chevronsLeft, enabled: at > 0, onTap: () => go(0)),
      const SizedBox(width: 4),
      _PagerButton(
          icon: LucideIcons.chevronLeft,
          enabled: at > 0,
          onTap: () => go(at - 1)),
      const SizedBox(width: 10),
      Text(pages[at]['date']?.toString() ?? '—',
          style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 12)),
      const SizedBox(width: 8),
      Text('page ${at + 1} of ${pages.length}',
          style: AppTextStyles.captionXs(c.t4)),
      const SizedBox(width: 10),
      _PagerButton(
          icon: LucideIcons.chevronRight,
          enabled: at < pages.length - 1,
          onTap: () => go(at + 1)),
      const SizedBox(width: 4),
      _PagerButton(
          icon: LucideIcons.chevronsRight,
          enabled: at < pages.length - 1,
          onTap: () => go(pages.length - 1)),
      const SizedBox(width: 14),
      Expanded(
        child: Text(
          '${totals['traded'] ?? 0} of ${totals['positions'] ?? 0} holdings '
          'traded · book ₹${_fullValue(_d(totals['value_before']))} → '
          '₹${_fullValue(_d(totals['value_after']))}',
          style: AppTextStyles.captionXs(c.t3),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ),
      _NetCashChip(value: _d(totals['net_cash'])),
    ]);
  }

  Widget _footer(BuildContext context, Map<String, dynamic> totals,
      Map<String, dynamic> data) {
    final c = context.colors;
    final missing = (totals['unpriced_keys'] as List?)
            ?.map((k) => k.toString())
            .toList() ??
        const <String>[];
    final lines = <String>[
      'Value before uses the previous session\'s close; fill is the price the '
          'ledger recorded. W% after uses the review-day close. Net cash is '
          'positive for a sale.',
      if (missing.isNotEmpty)
        'Weights on this page exclude ${missing.join(', ')} — no price history '
            'that far back, so ${missing.length == 1 ? 'it is' : 'they are'} '
            'held but not weighed.',
      if (data['reconciles'] == false)
        'The replay does not close on your current holdings, so treat these '
            'quantities as approximate.',
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final line in lines)
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(line,
                style: AppTextStyles.captionXs(
                    line.startsWith('Value') ? c.t4 : c.gold)),
          ),
      ],
    );
  }

  List<Widget> _cells(BuildContext context, Map<String, dynamic> r) {
    final c = context.colors;
    final action = r['action']?.toString() ?? 'HOLD';
    final sold = _d(r['sold']);
    return [
      Text(r['name']?.toString() ?? r['key']?.toString() ?? '—',
          style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 11.5),
          maxLines: 1,
          overflow: TextOverflow.ellipsis),
      denseNum(context, _held(r['held_before']), c.t2),
      r['fill'] == null
          ? _dash(context)
          : denseNum(context, _d(r['fill']).toStringAsFixed(2), c.t2),
      // A holding with no price history is still HELD — it just cannot be
      // weighed, and a zero here would read as "worth nothing".
      r['value_before'] == null
          ? _dash(context)
          : denseNum(context, '₹${_fullValue(_d(r['value_before']))}', c.t1,
              bold: true),
      r['weight_before_pct'] == null
          ? _dash(context)
          : denseNum(context,
              '${_d(r['weight_before_pct']).toStringAsFixed(2)}%', c.t2),
      Text(action,
          style: AppTextStyles.labelXs(switch (action) {
            'BUY' => c.up,
            'SELL' => c.dn,
            'BOTH' => c.gold,
            _ => c.t4,
          }).copyWith(fontWeight: FontWeight.w700),
          textAlign: TextAlign.right,
          maxLines: 1),
      _units(context, r['bought'], c.up),
      _units(context, r['sold'], c.dn),
      denseNum(context, '${_d(r['sold_pct_of_held']).toStringAsFixed(2)}%',
          sold > 0 ? c.dn : c.t4),
      // Zero, not a dash: a position closed out is a fact the ledger states.
      // A dash here reads as "unknown", which is the opposite of what a
      // 100%-sold row means.
      denseNum(context, _held(r['held_after']),
          _d(r['held_after']) == 0 ? c.t4 : c.t2),
      r['weight_after_pct'] == null
          ? _dash(context)
          : denseNum(context,
              '${_d(r['weight_after_pct']).toStringAsFixed(2)}%', c.t1,
              bold: true),
      _netCash(context, r['net_cash']),
    ];
  }
}

/// One step of the pager.
class _PagerButton extends StatelessWidget {
  final IconData icon;
  final bool enabled;
  final VoidCallback onTap;
  const _PagerButton(
      {required this.icon, required this.enabled, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return InkWell(
      onTap: enabled ? onTap : null,
      borderRadius: BorderRadius.circular(4),
      child: Container(
        width: 24,
        height: 24,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: enabled ? c.bd2 : c.bd),
        ),
        child: Icon(icon, size: 13, color: enabled ? c.t2 : c.t4),
      ),
    );
  }
}

/// What the day cost or raised, as one chip.
class _NetCashChip extends StatelessWidget {
  final double value;
  const _NetCashChip({required this.value});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final tone = value > 0 ? c.up : (value < 0 ? c.dn : c.t4);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        value == 0
            ? 'no cash moved'
            : '${value > 0 ? 'raised' : 'spent'} ₹${_fullValue(value.abs())}',
        style: AppTextStyles.labelXs(tone).copyWith(fontWeight: FontWeight.w700),
      ),
    );
  }
}

/// Money waiting to be placed, and the button that places it.
///
/// Without a contribution the table answers "am I off balance". With one it
/// answers the question people actually arrive with — "I have 1,000, where
/// does it go" — and the answer depends on the preset: gap fills the biggest
/// shortfalls, a tilt concentrates into three names, equal splits it across
/// everything.
///
/// The amount is not applied as it is typed. A plan that reshuffled on every
/// keystroke would be unreadable, and each change is a round trip to the
/// engine; Process is the commit.
class _AddFund extends ConsumerStatefulWidget {
  final Map<String, dynamic> contribution;
  final Map<String, dynamic> preset;
  const _AddFund({required this.contribution, required this.preset});

  @override
  ConsumerState<_AddFund> createState() => _AddFundState();
}

class _AddFundState extends ConsumerState<_AddFund> {
  late final TextEditingController _amount = TextEditingController();

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  void _process() {
    final value = double.tryParse(_amount.text.replaceAll(',', '').trim());
    if (value == null || !value.isFinite || value < 0) return;
    ref.read(rebalanceNewMoneyProvider.notifier).set(value);
  }

  void _clear() {
    _amount.clear();
    ref.read(rebalanceNewMoneyProvider.notifier).clear();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    // What the ENGINE did, not what is typed in the box. The two differ for
    // the whole time a new amount sits unprocessed, and the sentence under
    // the button has to describe the plan on screen.
    ref.watch(rebalanceNewMoneyProvider);
    final placed = _d(widget.contribution['amount']);
    final deployed = _d(widget.contribution['deployed']);
    final left = _d(widget.contribution['left']);
    final names = widget.contribution['positions'];
    final order = widget.preset['deploy_label']?.toString() ?? 'largest shortfall first';

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(14, 11, 14, 12),
      decoration: BoxDecoration(
        color: c.bg2,
        border: Border(bottom: BorderSide(color: c.bd)),
      ),
      child: Row(children: [
        Icon(LucideIcons.walletCards, size: 13, color: c.accent),
        const SizedBox(width: 7),
        Text('ADD FUND', style: AppTextStyles.labelXs(c.t2)),
        const SizedBox(width: 12),
        SizedBox(
          width: 130,
          height: 28,
          child: TextField(
            controller: _amount,
            keyboardType: TextInputType.number,
            style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 12),
            onSubmitted: (_) => _process(),
            decoration: InputDecoration(
              isDense: true,
              prefixText: '₹ ',
              prefixStyle: AppTextStyles.labelXs(c.t4),
              hintText: '1000',
              hintStyle: AppTextStyles.labelXs(c.t4),
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(4),
                  borderSide: BorderSide(color: c.bd2)),
              enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(4),
                  borderSide: BorderSide(color: c.bd2)),
            ),
          ),
        ),
        const SizedBox(width: 8),
        _MiniButton(label: 'PROCESS', tone: c.accent, onTap: _process),
        if (placed > 0) ...[
          const SizedBox(width: 6),
          _MiniButton(label: 'CLEAR', tone: c.t4, onTap: _clear),
        ],
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            placed <= 0
                ? 'Enter an amount and press Process. It is placed $order, '
                  'the way this strategy was measured.'
                : '₹${_fullValue(deployed)} placed across $names '
                  'holding${names == 1 ? '' : 's'}, $order. '
                  '₹${_fullValue(left)} left over — whole shares rarely '
                  'absorb the last rupee.',
            style: AppTextStyles.captionXs(placed > 0 ? c.t3 : c.t4),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ]),
    );
  }
}

/// A compact text button at the density of this panel.
class _MiniButton extends StatelessWidget {
  final String label;
  final Color tone;
  final VoidCallback onTap;
  const _MiniButton(
      {required this.label, required this.tone, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(4),
      child: Container(
        height: 28,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: tone.withValues(alpha: 0.14),
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: tone.withValues(alpha: 0.5)),
        ),
        child: Text(label,
            style: AppTextStyles.labelXs(tone)
                .copyWith(fontWeight: FontWeight.w700)),
      ),
    );
  }
}

/// sentence or it reads as a promise.
class _StrategyPicker extends ConsumerWidget {
  final Map<String, dynamic> preset;
  const _StrategyPicker({required this.preset});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final all = ref.watch(rebalanceStrategiesProvider);
    final selectedId = preset['id']?.toString() ?? 'S10';

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(14, 11, 14, 12),
      decoration: BoxDecoration(
        color: c.bg2,
        border: Border(bottom: BorderSide(color: c.bd)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(LucideIcons.listChecks, size: 13, color: c.accent),
          const SizedBox(width: 7),
          Text('REBALANCING STRATEGY', style: AppTextStyles.labelXs(c.t2)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Each preset sets the trim ceiling, the order top-ups are '
              'funded in, and whether income is put back to work.',
              style: AppTextStyles.captionXs(c.t4),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ]),
        const SizedBox(height: 8),
        all.when(
          loading: () => SizedBox(
            height: 26,
            child: Text('Loading strategies…',
                style: AppTextStyles.captionXs(c.t4)),
          ),
          error: (e, _) => Text('Could not load the strategy list: $e',
              style: AppTextStyles.captionXs(c.dn)),
          data: (payload) {
            final list = _list(payload['strategies']);
            final fallback = payload['default']?.toString() ?? 'S10';
            return Wrap(spacing: 5, runSpacing: 5, children: [
              for (final s in list)
                _StrategyChip(
                  id: s['id'].toString(),
                  label: s['id'].toString(),
                  selected: s['id'] == selectedId,
                  isDefault: s['id'] == fallback,
                  onTap: () async {
                    await ref
                        .read(rebalanceSettingsProvider.notifier)
                        .setStrategy(s['id'].toString());
                    ref.invalidate(rebalancePlanProvider);
                  },
                ),
            ]);
          },
        ),
        const SizedBox(height: 9),
        _SelectedStrategy(preset: preset),
      ]),
    );
  }
}

/// One preset button. Compact on purpose — twelve of them sit in a row.
class _StrategyChip extends StatelessWidget {
  final String id, label;
  final bool selected, isDefault;
  final VoidCallback onTap;

  const _StrategyChip({
    required this.id,
    required this.label,
    required this.selected,
    required this.isDefault,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    // The master is toned differently: it is not one of the ten, and the
    // difference should be visible before it is clicked.
    final tone = id == 'M1' ? c.gold : id == 'CUSTOM' ? c.t3 : c.accent;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(6),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 6),
        decoration: BoxDecoration(
          color: selected ? tone.withValues(alpha: 0.16) : c.bg3,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(
              color: selected ? tone : c.bd, width: selected ? 1.2 : 1),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Text(label,
              style: AppTextStyles.label(selected ? tone : c.t3)
                  .copyWith(fontWeight: FontWeight.w700)),
          if (isDefault) ...[
            const SizedBox(width: 5),
            Text('DEFAULT', style: AppTextStyles.captionXs(c.t4)),
          ],
        ]),
      ),
    );
  }
}

/// What the chosen preset actually does, and what it measured.
class _SelectedStrategy extends StatelessWidget {
  final Map<String, dynamic> preset;
  const _SelectedStrategy({required this.preset});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final measured = _map(preset['measured']);
    final neverSells = preset['never_sells'] == true;
    final ceiling = _d(preset['effective_max_weight_pct']);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 9),
      decoration: BoxDecoration(
        color: c.bg3,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: c.bd),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                      '${preset['id'] ?? ''} · '
                      '${preset['name'] ?? ''}',
                      style: AppTextStyles.bodyBold(c.t1)
                          .copyWith(fontSize: 12)),
                  const SizedBox(height: 2),
                  Text(preset['tagline']?.toString() ?? '',
                      style: AppTextStyles.captionXs(c.t3)),
                ]),
          ),
          // Where this preset placed against the other fifteen, so picking one
          // is a comparison rather than a leap of faith.
          if (preset['rank'] is num) ...[
            const SizedBox(width: 12),
            _RankBadge(rank: (preset['rank'] as num).toInt(),
                of: (preset['rank_of'] as num?)?.toInt() ?? 16),
          ],
          if (measured['xirr_pct'] is num) ...[
            const SizedBox(width: 12),
            Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Text('BACKTESTED', style: AppTextStyles.labelXs(c.t4)),
              const SizedBox(height: 1),
              Text('${_d(measured['xirr_pct']).toStringAsFixed(2)}%',
                  style: AppTextStyles.monoBold(c.accent)
                      .copyWith(fontSize: 14)),
            ]),
          ],
        ]),
        const SizedBox(height: 7),
        Wrap(spacing: 6, runSpacing: 5, children: [
          _fact(context,
              neverSells ? 'Never sells' : 'Trims above ${_pct(ceiling)}',
              neverSells ? c.up : c.gold),
          _fact(context, 'Funds ${preset['deploy_label'] ?? ''}', c.accent),
          if (preset['reinvest_income'] == true)
            _fact(context, 'Reinvests income', c.up),
        ]),
        // The two places the live plan cannot do what the backtest did. Both
        // are stated on the preset itself rather than buried in a footnote,
        // because they change what the number above means.
        if (preset['deploy_note'] != null) ...[
          const SizedBox(height: 6),
          Text('· ${preset['deploy_note']}',
              style: AppTextStyles.captionXs(c.t4)),
        ],
        if (preset['income_note'] != null) ...[
          const SizedBox(height: 4),
          Text('· ${preset['income_note']}',
              style: AppTextStyles.captionXs(c.t4)),
        ],
        if (measured['xirr_pct'] is num) ...[
          const SizedBox(height: 6),
          Text(preset['measured_note']?.toString() ?? '',
              style: AppTextStyles.captionXs(c.t4)),
        ],
      ]),
    );
  }

  Widget _fact(BuildContext context, String text, Color tone) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
        decoration: BoxDecoration(
          color: tone.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: tone.withValues(alpha: 0.28)),
        ),
        child: Text(text, style: AppTextStyles.captionXs(tone)),
      );
}

/// A ledger quantity, where zero is a real answer rather than a missing one.
String _held(dynamic v) {
  if (v is! num) return '—';
  final q = v.toDouble();
  return q == q.roundToDouble() ? q.toStringAsFixed(0) : q.toStringAsFixed(2);
}

/// Share counts. Whole numbers for equities; decimals only where a fractional
/// unit is real, as it is for mutual funds.
String _qty(dynamic v) {
  if (v is! num) return '—';
  final q = v.toDouble();
  if (q == 0) return '—';
  return q == q.roundToDouble() ? q.toStringAsFixed(0) : q.toStringAsFixed(2);
}

// ── payload helpers ──
//
// The plan arrives as decoded JSON, where every number is num and every branch
// may be absent. Reading it through these keeps a missing key rendering as a
// dash instead of throwing halfway down a build.

double _d(dynamic v) => (v is num) ? v.toDouble() : 0.0;

String _pct(dynamic v) => '${_d(v).toStringAsFixed(0)}%';

String _pts(dynamic v) => '±${_d(v).toStringAsFixed(0)} pts';

Map<String, dynamic> _map(dynamic v) =>
    v is Map ? Map<String, dynamic>.from(v) : const {};

List<Map<String, dynamic>> _list(dynamic v) => v is List
    ? v.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList()
    : const [];

String _fullValue(num value) => value.toStringAsFixed(0);
