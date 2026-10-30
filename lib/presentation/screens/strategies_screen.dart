import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/providers/providers.dart';
import 'package:aiei_wealth/presentation/widgets/animated_page_wrapper.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';

/// Quantitative Strategies — real backtested portfolios from the backtest
/// backend (`strategiesProvider`). No fabricated numbers: every metric comes
/// from the API and any null renders as an em-dash. Data-Dense Dashboard style.
class StrategiesScreen extends ConsumerStatefulWidget {
  const StrategiesScreen({super.key});
  @override
  ConsumerState<StrategiesScreen> createState() => _StrategiesScreenState();
}

class _StrategiesScreenState extends ConsumerState<StrategiesScreen> {
  String? _selected;

  /// Defensive numeric parse: handles int, double, String, or null.
  double? _num(dynamic v) {
    if (v == null) return null;
    if (v is num) return v.toDouble();
    return num.tryParse(v.toString())?.toDouble();
  }

  /// Risk accent color from the backend `risk_label`.
  Color _riskColor(BuildContext context, String risk) {
    final c = context.colors;
    final r = risk.toLowerCase();
    if (r.contains('low')) return c.up;
    if (r.contains('high')) return c.dn; // covers "High" / "V.High"
    return c.gold; // moderate / medium / unknown
  }

  /// Human-friendly "As of" date. Falls back to the raw string if not ISO.
  String _asOf(String? iso) {
    if (iso == null || iso.isEmpty) return '—';
    final d = DateTime.tryParse(iso);
    if (d == null) return iso;
    const months = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
    ];
    return '${d.day} ${months[d.month - 1]} ${d.year}';
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final strategiesAsync = ref.watch(strategiesProvider);

    return ListView(padding: EdgeInsets.zero, children: [
      // ── Header ──
      AnimatedListItem(
        index: 0,
        child: DenseCard(
          child: denseTableHeader(context,
              icon: LucideIcons.layers,
              accent: c.accent,
              title: 'Quantitative Strategies',
              subtitle:
                  'Backtested portfolios · Equal-weighted · Quarterly rebalance · 3Y daily data'),
        ),
      ),
      const SizedBox(height: 12),

      // ── Body: async states ──
      strategiesAsync.when(
        loading: () => const Padding(
          padding: EdgeInsets.symmetric(vertical: 80),
          child: DensePulseLoader(label: 'Loading backtested strategies…'),
        ),
        error: (e, _) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 60),
          child: ErrorRetry(
            title: 'Unable to load strategies',
            detail: '$e',
            onRetry: () => ref.invalidate(strategiesProvider),
          ),
        ),
        data: (data) {
          final strategies =
              List<Map<String, dynamic>>.from((data['strategies'] as List?) ?? const []);

          if (strategies.isEmpty) {
            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 60),
              child: ErrorRetry(
                title: 'No strategies available',
                detail: 'The backtest engine returned no strategies. Try again shortly.',
                icon: LucideIcons.layers,
                onRetry: () => ref.invalidate(strategiesProvider),
              ),
            );
          }

          return AnimatedListItem(
            index: 1,
            child: Wrap(
              spacing: 12,
              runSpacing: 12,
              children: strategies.map((s) => _strategyCard(context, s)).toList(),
            ),
          );
        },
      ),
      const SizedBox(height: 36),
    ]);
  }

  Widget _strategyCard(BuildContext context, Map<String, dynamic> s) {
    final c = context.colors;

    final id = (s['id'] ?? '').toString();
    final name = (s['name'] ?? 'Strategy').toString();
    final description = (s['description'] ?? '').toString();
    final risk = (s['risk_label'] ?? '—').toString();

    final cagr = _num(s['cagr_3y']);
    final benchCagr = _num(s['benchmark_cagr']);
    final maxDd = _num(s['max_drawdown']);
    final winRate = _num(s['win_rate']);

    final holdings =
        List<Map<String, dynamic>>.from((s['holdings'] as List?) ?? const []);
    final asOf = _asOf(s['as_of_date'] as String?);

    final isSelected = _selected == id;
    final riskColor = _riskColor(context, risk);

    // CAGR color + arrow derived from sign (never hardcoded).
    final cagrPositive = cagr == null || cagr >= 0;
    final cagrColor = cagr == null ? c.t2 : context.pnlColor(cagr);

    return SizedBox(
      width: (MediaQuery.sizeOf(context).width - 220 - 80) / 2,
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        child: GestureDetector(
          onTap: () => setState(() => _selected = isSelected ? null : id),
          child: Container(
            clipBehavior: Clip.antiAlias,
            decoration: cardSurface(context, radius: 14,
                borderColor: isSelected ? c.accent.withValues(alpha: 0.45) : null),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              // ── Header: name + risk, 3Y CAGR trailing ──
              denseTableHeader(context,
                  icon: LucideIcons.shield,
                  accent: riskColor,
                  title: name,
                  subtitle: 'Risk: $risk',
                  trailing: Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Row(mainAxisSize: MainAxisSize.min, children: [
                          if (cagr != null)
                            Icon(
                              cagrPositive
                                  ? LucideIcons.arrowUpRight
                                  : LucideIcons.arrowDownRight,
                              size: 14,
                              color: cagrColor,
                            ),
                          Text(
                            cagr == null ? '—' : formatPct(cagr),
                            style: AppTextStyles.monoBold(cagrColor)
                                .copyWith(fontSize: 15),
                          ),
                        ]),
                        const SizedBox(height: 2),
                        Text('3Y CAGR · BACKTESTED',
                            style: AppTextStyles.labelXs(c.t3)),
                      ])),

              if (description.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
                  child: Text(description, style: AppTextStyles.bodySmall(c.t3)),
                ),

              // ── Metrics strip: divider-separated mono cells ──
              Container(
                decoration: BoxDecoration(
                  color: c.bg3,
                  border: Border(
                      top: BorderSide(color: c.bd),
                      bottom: BorderSide(color: c.bd)),
                ),
                child: Row(children: [
                  _metric(context, 'NIFTY 3Y CAGR',
                      benchCagr == null ? '—' : formatPct(benchCagr), c.t2),
                  Container(width: 1, height: 34, color: c.bd),
                  _metric(context, 'MAX DRAWDOWN',
                      maxDd == null ? '—' : formatPct(maxDd),
                      maxDd == null ? c.t2 : c.dn),
                  Container(width: 1, height: 34, color: c.bd),
                  _metric(context, 'WIN RATE VS NIFTY',
                      winRate == null ? '—' : formatPct(winRate, decimals: 1),
                      c.t2),
                ]),
              ),

              // ── Current holdings ──
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 0),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('CURRENT HOLDINGS', style: AppTextStyles.labelXs(c.t3)),
                  const SizedBox(height: 8),
                  if (holdings.isEmpty)
                    Text('—', style: AppTextStyles.bodySmall(c.t3))
                  else
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: holdings.map((h) {
                        final symbol = (h['symbol'] ?? '').toString().cleanSymbol;
                        final hName = (h['name'] ?? '').toString();
                        final label = hName.isEmpty ? symbol : '$symbol — $hName';
                        return Container(
                          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                          decoration: BoxDecoration(
                            color: c.bg3,
                            border: Border.all(color: c.bd),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            label,
                            style: AppTextStyles.monoXs(c.t2)
                                .copyWith(fontWeight: FontWeight.w600),
                          ),
                        );
                      }).toList(),
                    ),
                ]),
              ),

              // ── Footer: as-of date + coming-soon (disabled) action ──
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('As of $asOf', style: AppTextStyles.captionXs(c.t4)),
                      HeaderButton(
                        icon: Icon(LucideIcons.rocket, size: 14, color: c.t4),
                        text: 'Deploy · Coming soon',
                        disabled: true,
                      ),
                    ]),
              ),
            ]),
          ),
        ),
      ),
    );
  }

  /// One metric cell in the per-card metrics strip.
  Widget _metric(BuildContext context, String label, String value, Color valueColor) {
    final c = context.colors;
    return Expanded(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label, style: AppTextStyles.labelXs(c.t3)),
          const SizedBox(height: 4),
          Text(value,
              style: AppTextStyles.monoBold(valueColor).copyWith(fontSize: 13)),
        ]),
      ),
    );
  }
}
