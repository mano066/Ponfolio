import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/dip_models.dart';
import 'package:aiei_wealth/providers/deploy_provider.dart';

/// Level 3 — the deep analysis, opened only when a card is tapped.
///
/// Everything here was deliberately kept OFF the cards. The dashboard's job is
/// to be readable in five seconds, which it cannot be if it also carries the
/// buying range, the zone ladder, the backtest and the factor breakdown. This
/// is where those live, and the split is the whole reason the cards can stay
/// short.
Future<void> showFundDetail(BuildContext context, FundDip fund) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _Sheet(
        title: fund.schemeName,
        subtitle: '${fund.category} · ${fund.benchmarkLabel}',
        child: _FundDetail(fund: fund),
      ),
    );

Future<void> showStockDetail(BuildContext context, StockDip stock) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _Sheet(
        title: stock.name,
        subtitle: '${stock.symbol} · ${stock.benchmarkLabel}',
        child: _StockDetail(stock: stock),
      ),
    );

class _Sheet extends StatelessWidget {
  final String title;
  final String subtitle;
  final Widget child;

  const _Sheet({
    required this.title,
    required this.subtitle,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return FractionallySizedBox(
      heightFactor: 0.88,
      child: Container(
        decoration: BoxDecoration(
          color: c.bg1,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
          border: Border.all(color: c.bd),
        ),
        child: Column(children: [
          Container(
            padding: const EdgeInsets.fromLTRB(18, 14, 12, 13),
            decoration: BoxDecoration(
              border: Border(bottom: BorderSide(color: c.bd)),
            ),
            child: Row(children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title,
                        style: AppTextStyles.bodyBold(c.t1)
                            .copyWith(fontSize: 15),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis),
                    Text(subtitle, style: AppTextStyles.labelXs(c.t3)),
                  ],
                ),
              ),
              IconButton(
                icon: Icon(LucideIcons.x, size: 18, color: c.t2),
                onPressed: () => Navigator.of(context).pop(),
              ),
            ]),
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(18, 14, 18, 28),
              child: child,
            ),
          ),
        ]),
      ),
    );
  }
}

// ── shared bits ───────────────────────────────────────────────────────────

Widget _block(BuildContext context, String title, Widget child) {
  final c = context.colors;
  return Padding(
    padding: const EdgeInsets.only(bottom: 18),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title.toUpperCase(),
          style: AppTextStyles.labelXs(c.t3).copyWith(letterSpacing: 0.6)),
      const SizedBox(height: 7),
      child,
    ]),
  );
}

Widget _kvGrid(BuildContext context, List<(String, String)> pairs) {
  final c = context.colors;
  return Wrap(
    spacing: 26,
    runSpacing: 9,
    children: [
      for (final (k, v) in pairs)
        SizedBox(
          width: 150,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(k, style: AppTextStyles.captionXs(c.t4)),
            Text(v, style: AppTextStyles.mono(c.t1).copyWith(fontSize: 12.5)),
          ]),
        ),
    ],
  );
}

String _pct(double? v, {int decimals = 1, String suffix = '%'}) =>
    v == null ? '—' : '${v.toStringAsFixed(decimals)}$suffix';

String _money(double? v) => v == null ? '—' : formatINR(v, decimals: 2);

/// Factor bars — how the composite was actually reached.
///
/// An unmeasured factor is drawn as an empty track labelled "not measured",
/// never as a zero bar. Those two look identical at a glance and mean opposite
/// things: one is a factor that scored badly, the other is a factor nobody
/// could compute.
Widget _factorBars(BuildContext context, Map<String, double?> factors,
    Map<String, String> labels, Color tone) {
  final c = context.colors;
  return Column(
    children: [
      for (final entry in factors.entries)
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(children: [
            SizedBox(
              width: 190,
              child: Text(labels[entry.key] ?? entry.key,
                  style: AppTextStyles.labelXs(c.t2),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
            ),
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(3),
                child: LinearProgressIndicator(
                  value: (entry.value ?? 0) / 100,
                  minHeight: 6,
                  backgroundColor: c.bd,
                  valueColor: AlwaysStoppedAnimation(
                      entry.value == null ? c.bd2 : tone),
                ),
              ),
            ),
            const SizedBox(width: 10),
            SizedBox(
              width: 92,
              child: Text(
                entry.value == null
                    ? 'not measured'
                    : entry.value!.toStringAsFixed(0),
                style: entry.value == null
                    ? AppTextStyles.captionXs(c.t4)
                    : AppTextStyles.mono(c.t1).copyWith(fontSize: 12),
                textAlign: TextAlign.right,
              ),
            ),
          ]),
        ),
    ],
  );
}

// ── fund ──────────────────────────────────────────────────────────────────

class _FundDetail extends ConsumerWidget {
  final FundDip fund;
  const _FundDetail({required this.fund});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final p = fund.purchase;
    final study = ref.watch(dipBacktestProvider).value?.bySymbol(fund.benchmark);

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _block(
        context,
        'How the score was reached',
        _factorBars(context, fund.factors, const {
          'benchmark_dip': 'Its category is down',
          'backtest_support': 'History supports this depth',
          'own_drawdown': 'Fall from its own NAV peak',
          'below_avg_nav': 'Below your average NAV',
        }, c.blue),
      ),
      _block(
        context,
        'Your buying history',
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _kvGrid(context, [
            ('Current NAV', _money(fund.nav)),
            ('Lowest you paid', _money(p.lowestBuyNav)),
            ('Weighted average', _money(p.weightedAvgNav)),
            ('Highest you paid', _money(p.highestBuyNav)),
            ('High / low ratio',
                p.highLowRatio == null ? '—' : '${p.highLowRatio!.toStringAsFixed(2)}x'),
            ('Purchases', '${p.buys}'),
            ('NAV vs your average', _pct(p.vsAvgPct)),
            ('Fund NAV peak', _money(fund.peakNav)),
          ]),
          if (p.caution != null) ...[
            const SizedBox(height: 9),
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(LucideIcons.triangleAlert, size: 12, color: c.gold),
              const SizedBox(width: 6),
              Expanded(
                child: Text(p.caution!, style: AppTextStyles.labelXs(c.gold)),
              ),
            ]),
          ],
          if (fund.peakIsPurchaseHigh) ...[
            const SizedBox(height: 7),
            Text(
              'The NAV peak above is your own highest purchase, not the '
              'fund\'s real all-time peak, so the zones below rest on a '
              'weaker anchor than usual.',
              style: AppTextStyles.captionXs(c.t3),
            ),
          ],
        ]),
      ),
      _block(
        context,
        'Buy zones and what history says',
        fund.zones.isEmpty
            ? Text('Not enough NAV history to place buy zones.',
                style: AppTextStyles.labelXs(c.t3))
            : Column(children: [
                for (final z in fund.zones) _zoneRow(context, z),
              ]),
      ),
      if (study != null && study.ok)
        _block(
          context,
          '${study.label} · ${study.years.toStringAsFixed(1)} years tested',
          _backtestTable(context, study),
        ),
    ]);
  }

  Widget _zoneRow(BuildContext context, BuyZone z) {
    final c = context.colors;
    final tone = z.evidence.supportsBuying
        ? c.up
        : (z.evidence.tested && z.evidence.reliable ? c.dn : c.t3);
    return Padding(
      padding: const EdgeInsets.only(bottom: 9),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(z.reached ? LucideIcons.circleCheck : LucideIcons.circle,
            size: 12, color: z.reached ? c.accent : c.t4),
        const SizedBox(width: 8),
        SizedBox(
          width: 150,
          child: Text('${z.label} (−${z.depthPct.toStringAsFixed(0)}%)',
              style: AppTextStyles.labelXs(z.reached ? c.t1 : c.t2)),
        ),
        SizedBox(
          width: 78,
          child: Text(z.navAtOrBelow.toStringAsFixed(2),
              style: AppTextStyles.mono(z.reached ? c.accent : c.t2)
                  .copyWith(fontSize: 12),
              textAlign: TextAlign.right),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Text(z.evidence.note,
              style: AppTextStyles.labelXs(tone), maxLines: 2),
        ),
      ]),
    );
  }

  Widget _backtestTable(BuildContext context, BenchmarkStudy study) {
    final c = context.colors;
    return Column(children: [
      Row(children: [
        SizedBox(
            width: 70,
            child: Text('DEPTH', style: AppTextStyles.captionXs(c.t4))),
        SizedBox(
            width: 74,
            child: Text('EPISODES', style: AppTextStyles.captionXs(c.t4))),
        SizedBox(
            width: 84,
            child: Text('1Y FORWARD', style: AppTextStyles.captionXs(c.t4))),
        SizedBox(
            width: 90,
            child: Text('BUY ANY DAY', style: AppTextStyles.captionXs(c.t4))),
        Expanded(
            child: Text('EDGE', style: AppTextStyles.captionXs(c.t4))),
      ]),
      const SizedBox(height: 6),
      for (final t in study.thresholds)
        Padding(
          padding: const EdgeInsets.only(bottom: 5),
          child: Row(children: [
            SizedBox(
              width: 70,
              child: Text('−${t.thresholdPct.toStringAsFixed(0)}%',
                  style: AppTextStyles.mono(t.reliable ? c.t1 : c.t3)
                      .copyWith(fontSize: 12)),
            ),
            SizedBox(
              width: 74,
              child: Text(
                  t.reliable ? '${t.signals}' : '${t.signals} · too few',
                  style: AppTextStyles.labelXs(t.reliable ? c.t2 : c.gold)),
            ),
            SizedBox(
              width: 84,
              child: Text(_pct(t.at('1y').meanPct),
                  style: AppTextStyles.mono(t.reliable ? c.t1 : c.t3)
                      .copyWith(fontSize: 12)),
            ),
            SizedBox(
              width: 90,
              child: Text(_pct(study.baselineAt('1y').meanPct),
                  style: AppTextStyles.mono(c.t3).copyWith(fontSize: 12)),
            ),
            Expanded(
              child: Text(
                t.edgePp['1y'] == null
                    ? '—'
                    : '${t.edgePp['1y']! >= 0 ? '+' : ''}'
                        '${t.edgePp['1y']!.toStringAsFixed(1)}pp',
                style: AppTextStyles.mono(!t.reliable
                        ? c.t3
                        : (t.beatsBaseline('1y') ? c.up : c.dn))
                    .copyWith(fontSize: 12),
              ),
            ),
          ]),
        ),
    ]);
  }
}

// ── stock ─────────────────────────────────────────────────────────────────

class _StockDetail extends StatelessWidget {
  final StockDip stock;
  const _StockDetail({required this.stock});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final r = stock.reasonForFall;

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _block(
        context,
        'Why it is down',
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Text(r.emoji, style: const TextStyle(fontSize: 13)),
            const SizedBox(width: 6),
            Flexible(
              child: Text(r.label,
                  style:
                      AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 13)),
            ),
          ]),
          const SizedBox(height: 6),
          Text(r.why, style: AppTextStyles.labelXs(c.t2)),
          if (r.deteriorationFlags.isNotEmpty) ...[
            const SizedBox(height: 8),
            for (final f in r.deteriorationFlags)
              Padding(
                padding: const EdgeInsets.only(bottom: 3),
                child: Row(children: [
                  Icon(LucideIcons.triangleAlert, size: 11, color: c.dn),
                  const SizedBox(width: 6),
                  Expanded(
                      child: Text(f, style: AppTextStyles.labelXs(c.dn))),
                ]),
              ),
          ],
        ]),
      ),
      _block(
        context,
        'How the score was reached',
        _factorBars(context, stock.factors, const {
          'drawdown': 'Price fall from its high',
          'valuation': 'Valuation',
          'fundamental': 'Balance sheet & returns',
          'growth': 'Growth',
          'news': 'News tone',
        }, c.accent),
      ),
      _block(
        context,
        'Position',
        _kvGrid(context, [
          ('Price', _money(stock.price)),
          ('Your average cost', _money(stock.avgCost)),
          ('Profit / loss', _pct(stock.plPct)),
          ('Off its 52-week high', _pct(stock.drawdownPct)),
          ('Its index is off', _pct(stock.benchmarkDrawdownPct)),
          ('Worse than its index',
              _pct(r.excessDrawdownPp, suffix: 'pp')),
          ('Confidence', _pct(stock.confidence, decimals: 0)),
        ]),
      ),
      _block(
        context,
        'News checked',
        r.headlinesChecked == 0
            ? Text(
                'No headlines were checked for this holding, so the news '
                'factor was left out of the score rather than assumed good.',
                style: AppTextStyles.labelXs(c.t3))
            : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${r.headlinesChecked} recent headlines · '
                    '${stock.newsLabel}',
                    style: AppTextStyles.labelXs(c.t2)),
                if (r.severeHeadlines.isNotEmpty) ...[
                  const SizedBox(height: 7),
                  for (final h in r.severeHeadlines.take(2))
                    Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(LucideIcons.newspaper, size: 11, color: c.gold),
                            const SizedBox(width: 6),
                            Expanded(
                                child: Text(h,
                                    style: AppTextStyles.labelXs(c.gold))),
                          ]),
                    ),
                ],
              ]),
      ),
      _block(
        context,
        'What is not available',
        Text(
            'The 5-year average P/E of a single stock needs a historical EPS '
            'series, and no feed in use carries one. Valuation here is '
            'measured against the sector and against absolute levels, never '
            'against its own past — so that comparison is absent rather than '
            'estimated.',
            style: AppTextStyles.captionXs(c.t3)),
      ),
    ]);
  }
}
