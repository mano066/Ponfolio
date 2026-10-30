import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/providers/providers.dart';
import 'package:aiei_wealth/presentation/widgets/animated_page_wrapper.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/services/api_service.dart';

/// AI Signals screen with Top 10 Gainers, Top 10 Losers, Top 10 AI Buy Picks,
/// plus the existing signal cards with polling, progress bar, and signal cards.
class AITriggersScreen extends ConsumerStatefulWidget {
  const AITriggersScreen({super.key});
  @override
  ConsumerState<AITriggersScreen> createState() => _AITriggersScreenState();
}

class _AITriggersScreenState extends ConsumerState<AITriggersScreen> {
  bool _startingAnalysis = false;

  static const _moverCols = [
    DenseCol('#', 1, numeric: false),
    DenseCol('INSTRUMENT', 5, numeric: false),
    DenseCol('PRICE', 3),
    DenseCol('CHG%', 3),
  ];

  Future<void> _startAnalysis() async {
    setState(() => _startingAnalysis = true);
    try { await ApiService().startDeepSignals(); } catch (_) {}
    setState(() => _startingAnalysis = false);
  }

  /// Defensive numeric parse: handles int, double, String, or null.
  double? _num(dynamic v) {
    if (v == null) return null;
    if (v is num) return v.toDouble();
    return num.tryParse(v.toString())?.toDouble();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final signals = ref.watch(aiSignalsProvider);
    final constituentsAsync = ref.watch(nifty50ConstituentsProvider);

    return signals.when(
      loading: () => const DensePulseLoader(label: 'Loading AI signals…'),
      error: (e, _) => ErrorRetry(
        title: 'Error loading signals',
        detail: '$e',
        onRetry: () => ref.invalidate(aiSignalsProvider),
      ),
      data: (data) {
        final sigs = (data['signals'] as Map<String, dynamic>?) ?? {};
        final running = data['running'] == true;
        final entries = sigs.entries.toList();
        final total = entries.length;
        // Count only genuinely-analyzed entries (analysis_ok == true), not ERROR/NO DATA.
        final completed = entries.where((e) => (e.value as Map)['analysis_ok'] == true).length;
        final failed = entries.where((e) =>
            (e.value as Map)['status'] == 'done' &&
            (e.value as Map)['analysis_ok'] != true).length;

        // ── Derive Gainers / Losers from Nifty50 constituents ──
        // Only rank entries with a non-null change_pct (missing != 0).
        final rankable = constituentsAsync.maybeWhen(
          data: (d) => List<Map<String, dynamic>>.from(d['constituents'] ?? [])
              .where((s) => _num(s['change_pct']) != null)
              .toList(),
          orElse: () => <Map<String, dynamic>>[],
        );

        // Sort for gainers (highest change_pct first)
        final gainers = (List<Map<String, dynamic>>.from(rankable)
              ..sort((a, b) => _num(b['change_pct'])!.compareTo(_num(a['change_pct'])!)))
            .take(10)
            .toList();

        // Sort for losers (lowest change_pct first)
        final losers = (List<Map<String, dynamic>>.from(rankable)
              ..sort((a, b) => _num(a['change_pct'])!.compareTo(_num(b['change_pct'])!)))
            .take(10)
            .toList();

        // ── Derive AI Buy Picks from completed signals ──
        final buyPicks = <Map<String, dynamic>>[];
        for (final e in entries) {
          final sig = e.value as Map<String, dynamic>;
          if (sig['analysis_ok'] == true) {
            final verdict = (sig['verdict_owned'] ?? '').toString().toUpperCase();
            final actionType = (sig['action_type'] ?? '').toString().toUpperCase();
            if (verdict.contains('BUY') || actionType.contains('BUY')) {
              buyPicks.add({
                'symbol': e.key,
                'verdict': (sig['verdict_owned'] ?? 'BUY').toString(),
                'action_type': sig['action_type'],
                'conviction_score': _num(sig['conviction_score']),
                'target_price': _num(sig['target_price']),
                'stop_loss': _num(sig['stop_loss']),
                'executive_summary': sig['executive_summary'] ?? '',
                'price': _num(sig['current_price']),
              });
            }
          }
        }
        // Sort by conviction (highest first; nulls last)
        buyPicks.sort((a, b) =>
            ((b['conviction_score'] as double?) ?? -1).compareTo((a['conviction_score'] as double?) ?? -1));

        final constituentsLoading = constituentsAsync.isLoading;

        return ListView(padding: EdgeInsets.zero, children: [
          // ── HEADER ──
          AnimatedListItem(
            index: 0,
            child: DenseCard(
              child: denseTableHeader(context,
                  icon: LucideIcons.zap,
                  accent: c.gold,
                  title: 'AI Signal Triggers',
                  subtitle: '$completed/$total stocks analyzed by 9-agent pipeline'
                      '${failed > 0 ? ' ($failed failed)' : ''}',
                  trailing: HeaderButton(
                    icon: Icon(LucideIcons.zap, size: 14, color: running ? c.t3 : Colors.white),
                    text: running ? 'Analyzing $completed/$total…' : 'Run Full AI Analysis',
                    solidColor: running ? null : c.blue,
                    disabled: running,
                    loading: _startingAnalysis,
                    onTap: _startAnalysis,
                  )),
            ),
          ),

          // Progress bar
          if (running && total > 0) ...[
            const SizedBox(height: 12),
            ClipRRect(borderRadius: BorderRadius.circular(3), child: LinearProgressIndicator(
              value: total > 0 ? completed / total : 0, minHeight: 6,
              backgroundColor: c.bg3,
              valueColor: AlwaysStoppedAnimation(c.blue),
            )),
          ],
          const SizedBox(height: 12),

          // ═══════════════════════════════════
          //  TOP 10 GAINERS & LOSERS (from Nifty50)
          // ═══════════════════════════════════
          AnimatedListItem(
            index: 1,
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(child: _buildMoverSection(
                context,
                title: 'Top 10 Gainers',
                icon: LucideIcons.trendingUp,
                accent: c.up,
                items: gainers,
                loading: constituentsLoading,
                onRetry: () => ref.invalidate(nifty50ConstituentsProvider),
                source: 'NIFTY 50',
              )),
              const SizedBox(width: 12),
              Expanded(child: _buildMoverSection(
                context,
                title: 'Top 10 Losers',
                icon: LucideIcons.trendingDown,
                accent: c.dn,
                items: losers,
                loading: constituentsLoading,
                onRetry: () => ref.invalidate(nifty50ConstituentsProvider),
                source: 'NIFTY 50',
              )),
            ]),
          ),
          const SizedBox(height: 12),

          // ═══════════════════════════════════
          //  TOP 10 AI BUY PICKS (from signals)
          // ═══════════════════════════════════
          AnimatedListItem(
            index: 2,
            child: _buildAIPicksSection(context, buyPicks.take(10).toList()),
          ),
          const SizedBox(height: 12),

          // ═══════════════════════════════════
          //  PORTFOLIO SIGNAL CARDS (existing)
          // ═══════════════════════════════════
          AnimatedListItem(
            index: 3,
            child: DenseCard(
              child: denseTableHeader(context,
                  icon: LucideIcons.briefcase,
                  accent: c.blue,
                  title: 'Portfolio AI Signals',
                  subtitle: '$total stocks · 9-agent deep analysis'),
            ),
          ),
          const SizedBox(height: 12),

          // Signal cards or empty state
          if (entries.isEmpty)
            const AnimatedListItem(
              index: 4,
              child: DenseEmptyCard(
                icon: LucideIcons.zap,
                title: 'No signals yet',
                sub: 'Click "Run Full AI Analysis" to start the 9-agent pipeline',
              ),
            )
          else
            AnimatedListItem(
              index: 4,
              child: Wrap(spacing: 12, runSpacing: 12, children: entries.map((e) {
                final sym = e.key;
                final sig = e.value as Map<String, dynamic>;
                final status = sig['status'] ?? 'pending';
                final verdict = ((sig['verdict_owned'] ?? '') as String).toUpperCase();
                final isBuy = verdict.contains('BUY');
                final isSell = verdict.contains('SELL');
                final cleanSym = sym.replaceAll(RegExp(r'\.(NS|BO)$', caseSensitive: false), '');
                final summary = sig['executive_summary'] as String?;
                final conviction = _num(sig['conviction_score']);
                final accentCol = status == 'done'
                    ? (isBuy ? c.up : isSell ? c.dn : c.t4)
                    : c.blue;

                return SizedBox(width: (MediaQuery.sizeOf(context).width - 220 - 80) / 3, child: DenseCard(
                  padding: const EdgeInsets.all(14),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                      Row(children: [
                        Container(width: 4, height: 26, decoration: BoxDecoration(
                          color: accentCol,
                          borderRadius: BorderRadius.circular(2))),
                        const SizedBox(width: 10),
                        Text(cleanSym, style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 14)),
                      ]),
                      if (status == 'done')
                        DSignalBadge(signal: (sig['verdict_owned'] ?? 'HOLD').toString())
                      else if (status == 'running')
                        const DSignalBadge(signal: 'ANALYZING')
                      else
                        const DSignalBadge(signal: 'PENDING'),
                    ]),
                    if (status == 'done' && summary != null) ...[
                      const SizedBox(height: 10),
                      Container(
                        padding: const EdgeInsets.only(left: 10),
                        decoration: BoxDecoration(border: Border(left: BorderSide(color: c.bd, width: 2))),
                        child: Text(summary, style: AppTextStyles.bodySmall(c.t2), maxLines: 3, overflow: TextOverflow.ellipsis),
                      ),
                    ],
                    if (conviction != null) ...[
                      const SizedBox(height: 10),
                      Row(children: [
                        Icon(LucideIcons.shieldCheck, size: 11, color: c.t4),
                        const SizedBox(width: 6),
                        Text('CONVICTION', style: AppTextStyles.labelXs(c.t4)),
                        const SizedBox(width: 8),
                        Expanded(child: ClipRRect(borderRadius: BorderRadius.circular(2), child: LinearProgressIndicator(
                          value: conviction / 100, minHeight: 4, backgroundColor: c.bg3,
                          color: conviction > 70 ? c.up : conviction > 40 ? c.gold : c.dn))),
                        const SizedBox(width: 8),
                        Text('${conviction.toInt()}%', style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 12)),
                      ]),
                    ],
                  ]),
                ));
              }).toList()),
            ),
          const SizedBox(height: 36),
        ]);
      },
    );
  }

  // ═══════════════════════════════════════════
  //  Top Gainers / Losers Section
  // ═══════════════════════════════════════════

  Widget _buildMoverSection(BuildContext context, {
    required String title,
    required IconData icon,
    required Color accent,
    required List<Map<String, dynamic>> items,
    required bool loading,
    required VoidCallback onRetry,
    required String source,
  }) {
    final c = context.colors;
    return DenseCard(
      clip: true,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        denseTableHeader(context,
            icon: icon,
            accent: accent,
            title: title,
            trailing: Text(source, style: AppTextStyles.labelXs(c.t3))),
        denseColumnHeader(context, _moverCols),
        if (loading)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 28),
            child: DensePulseLoader(label: 'Loading market data…'),
          )
        else if (items.isEmpty)
          Padding(
            padding: const EdgeInsets.all(16),
            child: ErrorRetry(
              compact: true,
              icon: icon,
              title: 'No market data',
              detail: 'Nifty 50 constituents unavailable',
              onRetry: onRetry,
            ),
          )
        else
          ...items.asMap().entries.map((entry) {
            final idx = entry.key;
            final item = entry.value;
            final sym = (item['symbol'] ?? '').toString().replaceAll(RegExp(r'\.(NS|BO)$', caseSensitive: false), '');
            final name = (item['name'] ?? item['company'] ?? sym).toString();
            final price = _num(item['price']);
            final chg = _num(item['change_pct']) ?? 0;

            return DenseRow(
              alt: idx.isOdd,
              cols: _moverCols,
              cells: [
                Text('${idx + 1}',
                    style: AppTextStyles.monoXs(idx < 3 ? accent : c.t4)
                        .copyWith(fontWeight: idx < 3 ? FontWeight.w700 : FontWeight.w500)),
                DInstrument(symbol: sym, sub: name, up: chg >= 0, ellipsis: true),
                denseNum(context,
                    (price != null && price > 0) ? formatINR(price, decimals: 2) : '—',
                    c.t1, bold: true),
                denseDelta(context, chg),
              ],
            );
          }),
      ]),
    );
  }

  // ═══════════════════════════════════════════
  //  AI Top Buy Picks Section
  // ═══════════════════════════════════════════

  Widget _buildAIPicksSection(BuildContext context, List<Map<String, dynamic>> picks) {
    final c = context.colors;
    return DenseCard(
      clip: true,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        denseTableHeader(context,
            icon: LucideIcons.target,
            accent: c.accent,
            title: 'Top 10 AI Buy Picks',
            subtitle: 'Stocks with BUY verdict from deep analysis, ranked by conviction',
            trailing: Text('AI POWERED', style: AppTextStyles.labelXs(c.accent))),
        if (picks.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 28),
            child: Column(children: [
              Icon(LucideIcons.target, size: 24, color: c.t3),
              const SizedBox(height: 10),
              Text('No AI buy picks available yet', style: AppTextStyles.heading3(c.t1)),
              const SizedBox(height: 4),
              Text('Run "Full AI Analysis" above to generate buy recommendations',
                  style: AppTextStyles.bodySmall(c.t3)),
            ]),
          )
        else
          Padding(
            padding: const EdgeInsets.all(14),
            child: Wrap(spacing: 12, runSpacing: 12, children: picks.asMap().entries.map((entry) {
              final idx = entry.key;
              final pick = entry.value;
              final sym = (pick['symbol'] ?? '').toString().replaceAll(RegExp(r'\.(NS|BO)$', caseSensitive: false), '');
              final price = pick['price'] as double?;
              final conviction = pick['conviction_score'] as double?;
              final target = pick['target_price'] as double?;
              final summary = (pick['executive_summary'] ?? '').toString();
              // Verdict: prefer explicit verdict; carry action_type as a distinct label.
              final verdict = (pick['verdict'] ?? 'BUY').toString();
              final actionType = (pick['action_type'] ?? '').toString();
              // Upside %: may be negative on a BUY (red flag) — surface as Downside.
              final upside = (price != null && price > 0 && target != null && target > 0)
                  ? ((target - price) / price * 100)
                  : null;
              final hasUpside = upside != null;
              final upsideUp = hasUpside && upside >= 0;

              return SizedBox(
                width: (MediaQuery.sizeOf(context).width - 220 - 80) / 3 - 8,
                child: Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: c.bg1,
                    border: Border.all(color: c.bd),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      Container(
                        width: 22, height: 22,
                        decoration: BoxDecoration(
                          color: c.up.withValues(alpha: 0.10),
                          border: Border.all(color: c.up.withValues(alpha: 0.22)),
                          borderRadius: BorderRadius.circular(5),
                        ),
                        child: Center(child: Text('${idx + 1}',
                            style: AppTextStyles.monoXs(c.up).copyWith(fontWeight: FontWeight.w700, fontSize: 10))),
                      ),
                      const SizedBox(width: 8),
                      Expanded(child: Text(sym, style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 13))),
                      DSignalBadge(signal: verdict),
                    ]),
                    if (actionType.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: c.accent.withValues(alpha: 0.08),
                            border: Border.all(color: c.accent.withValues(alpha: 0.20)),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(actionType, style: AppTextStyles.labelXs(c.accent).copyWith(fontSize: 9)),
                        ),
                      ),
                    ],
                    const SizedBox(height: 10),
                    Row(children: [
                      if (price != null && price > 0) Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('PRICE', style: AppTextStyles.labelXs(c.t4).copyWith(fontSize: 9)),
                        const SizedBox(height: 2),
                        Text(formatINR(price, decimals: 2), style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 12)),
                      ])),
                      if (target != null && target > 0) Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('TARGET', style: AppTextStyles.labelXs(c.t4).copyWith(fontSize: 9)),
                        const SizedBox(height: 2),
                        Text(formatINR(target), style: AppTextStyles.monoBold(c.up).copyWith(fontSize: 12)),
                      ])),
                      if (hasUpside) Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                        Text(upsideUp ? 'UPSIDE' : 'DOWNSIDE', style: AppTextStyles.labelXs(c.t4).copyWith(fontSize: 9)),
                        const SizedBox(height: 2),
                        Text(formatPct(upside, decimals: 1), style: AppTextStyles.monoBold(upsideUp ? c.up : c.dn).copyWith(fontSize: 12)),
                      ])),
                    ]),
                    if (conviction != null) ...[
                      const SizedBox(height: 10),
                      Row(children: [
                        Icon(LucideIcons.shieldCheck, size: 10, color: c.t4),
                        const SizedBox(width: 4),
                        Text('CONVICTION', style: AppTextStyles.labelXs(c.t4).copyWith(fontSize: 9)),
                        const SizedBox(width: 6),
                        Expanded(child: ClipRRect(borderRadius: BorderRadius.circular(2), child: LinearProgressIndicator(
                          value: conviction / 100, minHeight: 4, backgroundColor: c.bg3,
                          color: conviction > 70 ? c.up : conviction > 40 ? c.gold : c.dn))),
                        const SizedBox(width: 6),
                        Text('${conviction.toInt()}%', style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 11)),
                      ]),
                    ],
                    if (summary.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Container(
                        padding: const EdgeInsets.only(left: 8),
                        decoration: BoxDecoration(border: Border(left: BorderSide(color: c.up.withValues(alpha: 0.3), width: 2))),
                        child: Text(summary, style: AppTextStyles.captionXs(c.t3), maxLines: 2, overflow: TextOverflow.ellipsis),
                      ),
                    ],
                  ]),
                ),
              );
            }).toList()),
          ),
      ]),
    );
  }
}
