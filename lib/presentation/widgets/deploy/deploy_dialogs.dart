import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/deploy_models.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/providers/deploy_provider.dart';

/// Confirms a batch of buys before recording them.
///
/// A dialog rather than an inline button because this mutates cost basis, units
/// and XIRR — the user should see exactly what is about to be written, and be
/// told plainly that no broker order is placed.
class RecordBuyDialog extends ConsumerStatefulWidget {
  final List<DeploySplit> buys;
  final String title;

  /// Which button to mark busy while this runs.
  final String busyKey;

  const RecordBuyDialog({
    super.key,
    required this.buys,
    required this.title,
    required this.busyKey,
  });

  @override
  ConsumerState<RecordBuyDialog> createState() => _RecordBuyDialogState();
}

class _RecordBuyDialogState extends ConsumerState<RecordBuyDialog> {
  /// Generated ONCE per dialog and reused across retries, so a double-submit or
  /// a retry after a timeout is recognised server-side as a duplicate instead
  /// of recording the money twice.
  late final String _requestId = newDeployRequestId();

  bool _saving = false;
  String? _error;

  double get _total => widget.buys.fold(0.0, (s, b) => s + b.amount);

  Future<void> _submit() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    ref.read(deployBusyProvider.notifier).start(widget.busyKey);
    try {
      final res = await recordDeployment(
        ref,
        requestId: _requestId,
        splits: widget.buys,
      );
      if (!mounted) return;
      final dup = res['status'] == 'duplicate';
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(dup
            ? 'Already recorded — nothing was added twice.'
            : 'Recorded ${formatINR(_total)} across '
                '${widget.buys.length} holding(s).'),
      ));
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = _dioMessage(e));
    } finally {
      ref.read(deployBusyProvider.notifier).finish(widget.busyKey);
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Dialog(
      backgroundColor: c.bg2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          denseTableHeader(
            context,
            icon: LucideIcons.check,
            accent: c.up,
            title: widget.title,
            subtitle: '${widget.buys.length} buy(s) · ${formatINR(_total)}',
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (final b in widget.buys) _line(context, b),
                  const SizedBox(height: 12),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(11),
                    decoration: BoxDecoration(
                      color: c.bg3,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: c.bd),
                    ),
                    child: Text(
                      'This records the buy inside this app only, so your '
                      'average cost and returns stay correct. It does NOT '
                      'place any order with your broker — do that yourself '
                      'first.',
                      style: AppTextStyles.captionXs(c.t3),
                    ),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 10),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(11),
                      decoration: BoxDecoration(
                        color: c.dnBg,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: c.dn.withValues(alpha: 0.4)),
                      ),
                      child: Text(_error!,
                          style: AppTextStyles.bodySmall(c.dn)),
                    ),
                  ],
                  const SizedBox(height: 16),
                  Row(mainAxisAlignment: MainAxisAlignment.end, children: [
                    HeaderButton(
                      text: 'Cancel',
                      onTap: _saving ? null : () => Navigator.of(context).pop(),
                    ),
                    const SizedBox(width: 10),
                    HeaderButton(
                      icon: const Icon(LucideIcons.check,
                          size: 13, color: Colors.white),
                      text: _error == null ? 'Record' : 'Try again',
                      solidColor: c.up,
                      loading: _saving,
                      onTap: _saving ? null : _submit,
                    ),
                  ]),
                ]),
          ),
        ]),
      ),
    );
  }

  Widget _line(BuildContext context, DeploySplit b) {
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(children: [
        Container(
          width: 3,
          height: 26,
          decoration: BoxDecoration(
            color: b.kind == HoldingKind.fund ? c.blue : c.cyan,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(b.label,
                    style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis),
                Text('${kindLabel(b.kind)} · ${b.unitsLabel}',
                    style: AppTextStyles.captionXs(c.t3)),
              ]),
        ),
        Text(formatINR(b.amount),
            style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 13)),
      ]),
    );
  }
}

// ══════════════════════════════════════════
//  PLAN EDITOR
// ══════════════════════════════════════════

/// Editor for the monthly plan and target shares.
///
/// Purpose-built rather than reusing `EditableGrid`: that widget is a
/// fixed-column typed grid over homogeneous rows, whereas this needs to add and
/// remove rows, pick from live holdings, and validate that targets sum sensibly.
class DeployPlanDialog extends ConsumerStatefulWidget {
  const DeployPlanDialog({super.key});

  @override
  ConsumerState<DeployPlanDialog> createState() => _DeployPlanDialogState();
}

class _DeployPlanDialogState extends ConsumerState<DeployPlanDialog> {
  List<SipLeg>? _legs;
  Map<String, double>? _targets;
  int _tab = 0;
  bool _saving = false;
  String? _error;

  void _seed(DeployPlanConfig cfg) {
    _legs ??= List<SipLeg>.from(cfg.legs);
    _targets ??= Map<String, double>.from(cfg.targets);
  }

  double get _targetSum =>
      (_targets ?? {}).values.fold(0.0, (s, v) => s + v);

  double get _legTotal =>
      (_legs ?? []).where((l) => l.active).fold(0.0, (s, l) => s + l.amount);

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await saveDeployPlan(ref, legs: _legs, targets: _targets);
      if (!mounted) return;
      Navigator.of(context).pop();
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = _dioMessage(e));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final cfgAsync = ref.watch(deployPlanProvider);

    return Dialog(
      backgroundColor: c.bg2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640, maxHeight: 640),
        child: cfgAsync.when(
          loading: () => const SizedBox(
              height: 260, child: DensePulseLoader(label: 'Loading plan…')),
          error: (e, _) => SizedBox(
            height: 260,
            child: ErrorRetry(
              title: 'Could not load your plan',
              detail: _dioMessage(e),
              onRetry: () => ref.invalidate(deployPlanProvider),
            ),
          ),
          data: (cfg) {
            _seed(cfg);
            return Column(mainAxisSize: MainAxisSize.min, children: [
              denseTableHeader(
                context,
                icon: LucideIcons.settings2,
                accent: c.gold,
                title: 'Monthly Plan & Targets',
                subtitle:
                    'Plan ${formatINR(_legTotal)}/month · targets ${_targetSum.toStringAsFixed(0)}%',
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                child: Row(children: [
                  DFilterChip(
                    label: 'MONTHLY PLAN',
                    selected: _tab == 0,
                    tone: c.gold,
                    onTap: () => setState(() => _tab = 0),
                  ),
                  const SizedBox(width: 8),
                  DFilterChip(
                    label: 'TARGET SHARES',
                    selected: _tab == 1,
                    tone: c.gold,
                    onTap: () => setState(() => _tab = 1),
                  ),
                ]),
              ),
              Flexible(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                  child: _tab == 0 ? _planTab(context, cfg) : _targetTab(context, cfg),
                ),
              ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                  child: Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(11),
                    decoration: BoxDecoration(
                      color: c.dnBg,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: c.dn.withValues(alpha: 0.4)),
                    ),
                    child:
                        Text(_error!, style: AppTextStyles.bodySmall(c.dn)),
                  ),
                ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
                child: Row(children: [
                  if (_tab == 0 && cfg.suggestedLegs.isNotEmpty)
                    HeaderButton(
                      text: 'Suggest for me',
                      onTap: () => setState(
                          () => _legs = List<SipLeg>.from(cfg.suggestedLegs)),
                    ),
                  if (_tab == 1 && cfg.suggestedTargets.isNotEmpty)
                    HeaderButton(
                      text: 'Use current shares',
                      onTap: () => setState(() => _targets =
                          Map<String, double>.from(cfg.suggestedTargets)),
                    ),
                  const Spacer(),
                  HeaderButton(
                    text: 'Cancel',
                    onTap: _saving ? null : () => Navigator.of(context).pop(),
                  ),
                  const SizedBox(width: 10),
                  HeaderButton(
                    text: 'Save plan',
                    solidColor: c.up,
                    loading: _saving,
                    onTap: _saving ? null : _save,
                  ),
                ]),
              ),
            ]);
          },
        ),
      ),
    );
  }

  // ── monthly plan tab ────────────────────────────────────────────────
  Widget _planTab(BuildContext context, DeployPlanConfig cfg) {
    final c = context.colors;
    final legs = _legs ?? [];
    final used = legs.map((l) => l.key).toSet();
    final available = [
      ...cfg.fundKeys.map((k) => (k, HoldingKind.fund)),
      ...cfg.stockKeys.map((k) => (k, HoldingKind.stock)),
    ].where((e) => !used.contains(e.$1)).toList();

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(
        'One line per fund or stock. Give each its own amount and the day of '
        'the month it is due.',
        style: AppTextStyles.bodySmall(c.t3),
      ),
      const SizedBox(height: 12),
      if (legs.isEmpty)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 16),
          child: Text('No lines yet. Add one below, or press "Suggest for me".',
              style: AppTextStyles.bodySmall(c.t4)),
        ),
      for (final (i, leg) in legs.indexed) _legEditor(context, i, leg),
      const SizedBox(height: 10),
      if (available.isEmpty)
        Text('Every holding already has a line.',
            style: AppTextStyles.captionXs(c.t4))
      else
        Wrap(spacing: 8, runSpacing: 8, children: [
          Text('ADD:', style: AppTextStyles.labelXs(c.t3)),
          for (final (key, kind) in available.take(12))
            DFilterChip(
              label: key.length > 26 ? '${key.substring(0, 26)}…' : key,
              selected: false,
              onTap: () => setState(() => _legs = [
                    ...legs,
                    SipLeg(
                        kind: kind,
                        key: key,
                        label: key,
                        amount: 5000,
                        dueDay: 5),
                  ]),
            ),
        ]),
      const SizedBox(height: 12),
      Text('Total: ${formatINR(_legTotal)} per month',
          style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 13)),
    ]);
  }

  Widget _legEditor(BuildContext context, int index, SipLeg leg) {
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(children: [
        Container(
          width: 3,
          height: 34,
          decoration: BoxDecoration(
            color: leg.kind == HoldingKind.fund ? c.blue : c.cyan,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Text(leg.label,
              style: AppTextStyles.bodySmall(c.t1),
              maxLines: 2,
              overflow: TextOverflow.ellipsis),
        ),
        const SizedBox(width: 10),
        SizedBox(
          width: 110,
          child: TextFormField(
            initialValue: leg.amount.toStringAsFixed(0),
            style: AppTextStyles.mono(c.t1).copyWith(fontSize: 13),
            keyboardType: TextInputType.number,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            decoration: denseFieldDecoration(context, prefix: '₹ '),
            onChanged: (v) => _updateLeg(
                index, leg.copyWith(amount: double.tryParse(v) ?? 0)),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 74,
          child: TextFormField(
            initialValue: leg.dueDay.toString(),
            style: AppTextStyles.mono(c.t1).copyWith(fontSize: 13),
            keyboardType: TextInputType.number,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            decoration: denseFieldDecoration(context, hint: 'day'),
            onChanged: (v) {
              final d = int.tryParse(v) ?? 1;
              _updateLeg(index, leg.copyWith(dueDay: d.clamp(1, 31)));
            },
          ),
        ),
        IconButton(
          icon: Icon(LucideIcons.trash2, size: 15, color: c.t4),
          tooltip: 'Remove this line',
          onPressed: () => setState(
              () => _legs = [...?_legs]..removeAt(index)),
        ),
      ]),
    );
  }

  void _updateLeg(int index, SipLeg updated) {
    final next = [...?_legs];
    next[index] = updated;
    // No setState: the field already shows the typed text, and rebuilding
    // would fight the cursor. Only the footer total lags, which is acceptable.
    _legs = next;
    setState(() {});
  }

  // ── targets tab ─────────────────────────────────────────────────────
  Widget _targetTab(BuildContext context, DeployPlanConfig cfg) {
    final c = context.colors;
    final targets = _targets ?? {};
    final all = [...cfg.fundKeys, ...cfg.stockKeys];
    final sum = _targetSum;
    final off = (sum - 100).abs() > 1 && sum > 0;

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(
        'What share of your whole portfolio each holding should be. The app '
        'sends more money to whatever has drifted below its share.',
        style: AppTextStyles.bodySmall(c.t3),
      ),
      const SizedBox(height: 12),
      for (final key in all)
        Padding(
          padding: const EdgeInsets.only(bottom: 9),
          child: Row(children: [
            Expanded(
              child: Text(key,
                  style: AppTextStyles.bodySmall(c.t1),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis),
            ),
            const SizedBox(width: 10),
            SizedBox(
              width: 92,
              child: TextFormField(
                initialValue:
                    targets[key] == null ? '' : targets[key]!.toStringAsFixed(0),
                style: AppTextStyles.mono(c.t1).copyWith(fontSize: 13),
                keyboardType: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                decoration: denseFieldDecoration(context, hint: '0'),
                onChanged: (v) {
                  final pct = double.tryParse(v) ?? 0;
                  final next = {...targets};
                  if (pct <= 0) {
                    next.remove(key);
                  } else {
                    next[key] = pct.clamp(0, 100);
                  }
                  _targets = next;
                  setState(() {});
                },
              ),
            ),
            const SizedBox(width: 6),
            Text('%', style: AppTextStyles.bodySmall(c.t3)),
          ]),
        ),
      const SizedBox(height: 8),
      Text(
        off
            ? 'Your targets add up to ${sum.toStringAsFixed(0)}%, not 100%. It '
                'still works, but the shares will not be what you expect.'
            : 'Total: ${sum.toStringAsFixed(0)}%',
        style: AppTextStyles.bodySmall(off ? c.gold : c.t2),
      ),
    ]);
  }
}

/// Turns a Dio failure into something a person can act on.
String _dioMessage(Object e) {
  if (e is DioException) {
    final detail = e.response?.data;
    if (detail is Map && detail['detail'] != null) {
      return detail['detail'].toString();
    }
    if (e.type == DioExceptionType.connectionError) {
      return 'Could not reach the backend. Is it running?';
    }
    return e.message ?? 'Request failed.';
  }
  return e.toString();
}
