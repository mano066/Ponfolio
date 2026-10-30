import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/deploy_models.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/providers/deploy_provider.dart';

/// Live index tape — "what is the market doing right now?".
///
/// Laid out as grouped bands of fixed-width chips rather than a scrolling
/// ticker or a table. The requirement is to see at a glance which index is up
/// and which is down: a horizontal scroller hides half the symbols behind a
/// gesture, and a 14-row table forces the eye to read down a column of numbers
/// instead of pattern-matching a field of colour. Fixed-width chips in a [Wrap]
/// fold cleanly at any window size while staying aligned in scannable columns.
class MarketTapeCard extends ConsumerStatefulWidget {
  const MarketTapeCard({super.key});

  @override
  ConsumerState<MarketTapeCard> createState() => _MarketTapeCardState();
}

class _MarketTapeCardState extends ConsumerState<MarketTapeCard> {
  bool _compact = false;
  bool _detail = false;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final tape = ref.watch(marketTapeProvider).value ?? MarketTape.empty;

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(
          context,
          icon: LucideIcons.activity,
          accent: c.accent,
          title: 'Market Tape',
          subtitle: tape.hasData
              ? '${tape.available} indices live · ${tape.summary}'
              : 'Waiting for market data…',
          trailing: Row(mainAxisSize: MainAxisSize.min, children: [
            if (tape.hasData)
              AppBadge(
                text: '${tape.up} up   ${tape.down} down',
                variant: tape.up >= tape.down ? BadgeVariant.up : BadgeVariant.dn,
              ),
            const SizedBox(width: 8),
            DFilterChip(
              label: 'COMPACT',
              selected: _compact,
              tone: c.accent,
              onTap: () => setState(() => _compact = !_compact),
            ),
            const SizedBox(width: 4),
            // Chips are for scanning a field of colour; the table is for
            // reading one index properly. Both views, one fetch.
            DFilterChip(
              label: 'DETAIL',
              selected: _detail,
              tone: c.accent,
              onTap: () => setState(() => _detail = !_detail),
            ),
          ]),
        ),
        SectionExplainer(
          accent: c.accent,
          question: 'What is the market doing right now?',
          reading:
              'Every index with today\'s move in points and percent, and where '
              'it sits between its 52-week low and high.',
          rules: const [
            'Green means the index is up today. Red means it is down. The '
                'colour of the whole box is the fastest way to read it.',
            'Under the level is today\'s move in points. The percentage tells '
                'you how big the day was; the points tell you how far it moved.',
            'The bar is the 52-week range. The left edge is the 52-week low (L) '
                'and the right edge is the 52-week high (H). The marker is '
                'where today\'s level sits between them.',
            'A marker near the left means the index is close to its cheapest '
                'level of the year. Near the right means close to its dearest.',
            'OFF HIGH is the same idea as a number: how far it has fallen from '
                'its highest level in the last one year.',
            'A grey box means today\'s price did not arrive. It is not a zero, '
                'and its bar is left empty rather than pinned to the low.',
          ],
          action:
              'When a broad index is down a lot, add to your index or flexi-cap '
              'funds. When only one sector is down, look for that sector\'s '
              'fund or stock in the table above.',
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
          child: tape.indices.isEmpty
              ? _loading(context)
              : _detail
              ? _MetricsTable(quotes: tape.indices)
              : Builder(builder: (context) {
                  // Skipping empty groups here rather than inside the loop
                  // keeps "isLast" honest: the trailing gap belongs to the last
                  // band actually drawn, not the last one in the enum.
                  final groups = IndexGroup.values
                      .where((g) => tape.ofGroup(g).isNotEmpty)
                      .toList();
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      for (final (i, group) in groups.indexed)
                        _GroupBand(
                          label: indexGroupLabel(group),
                          quotes: tape.ofGroup(group),
                          compact: _compact,
                          isLast: i == groups.length - 1,
                        ),
                    ],
                  );
                }),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
          child: Text(
            'Levels can be up to 20 seconds old. Gold and silver are shown '
            'through their ETFs, not the metal price itself.',
            style: AppTextStyles.captionXs(c.t4),
          ),
        ),
      ]),
    );
  }

  Widget _loading(BuildContext context) => const SizedBox(
        height: 90,
        child: DensePulseLoader(label: 'Loading market levels…'),
      );
}

/// Full metric table for every index — the reading view.
///
/// A column here is blank (—) rather than zero whenever the series could not
/// answer it: a 3-month return needs 63 closes behind it and a 200 DMA needs
/// 200, and a short series filling those in would be a different statistic
/// wearing the right label.
class _MetricsTable extends StatelessWidget {
  final List<IndexQuote> quotes;

  const _MetricsTable({required this.quotes});

  static const _cols = [
    DenseCol('INDEX', 20, numeric: false),
    DenseCol('LEVEL', 13),
    DenseCol('1D', 9),
    DenseCol('1W', 9),
    DenseCol('1M', 9),
    DenseCol('3M', 9),
    DenseCol('YTD', 9),
    DenseCol('OFF HIGH', 11),
    // Spacers keep each right-aligned number clear of the left-aligned label
    // that follows it; DenseRow leaves no gap between cells of its own.
    DenseCol('', 2, numeric: false),
    DenseCol('50/100/200', 13, numeric: false),
    DenseCol('RSI', 8),
    DenseCol('', 2, numeric: false),
    DenseCol('STATUS', 13, numeric: false),
  ];

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      denseColumnHeader(context, _cols),
      ...quotes.asMap().entries.map((e) => DenseRow(
            cols: _cols,
            alt: e.key.isOdd,
            cells: _cells(context, e.value),
          )),
    ]);
  }

  List<Widget> _cells(BuildContext context, IndexQuote q) {
    final c = context.colors;
    final decimals = q.group == IndexGroup.commodity ? 2 : 0;
    return [
      Text(q.label,
          style: AppTextStyles.bodyBold(q.ok ? c.t1 : c.t4)
              .copyWith(fontSize: 11.5),
          maxLines: 1,
          overflow: TextOverflow.ellipsis),
      denseNum(context, q.last == null ? '—' : q.last!.toStringAsFixed(decimals),
          q.ok ? c.t1 : c.t4),
      _pct(context, q.dayChgPct),
      _pct(context, q.chg1wPct),
      _pct(context, q.chg1mPct),
      _pct(context, q.chg3mPct),
      _pct(context, q.chgYtdPct),
      // A fall is the opportunity on this screen, so off-high is not painted
      // in P&L colours: deeper is more interesting, not more alarming.
      q.offHighPct == null
          ? _dash(context)
          : denseSignedNum(context, -q.offHighPct!,
              q.offHighPct! >= 10 ? c.accent : c.t2, decimals: 1),
      const SizedBox.shrink(),
      _dmaCell(context, q),
      q.rsi14 == null
          ? _dash(context)
          : denseNum(context, q.rsi14!.toStringAsFixed(0),
              q.rsi14! <= 30 ? c.accent : (q.rsi14! >= 70 ? c.gold : c.t2)),
      const SizedBox.shrink(),
      _statusCell(context, q),
    ];
  }

  /// Three dots: above its 50, 100 and 200 day average. A dot is hollow when
  /// that average does not exist yet, which is a different fact from "below".
  Widget _dmaCell(BuildContext context, IndexQuote q) {
    final c = context.colors;
    return Row(mainAxisAlignment: MainAxisAlignment.start, children: [
      for (final w in const [50, 100, 200])
        Padding(
          padding: const EdgeInsets.only(right: 5),
          child: Builder(builder: (_) {
            final above = q.aboveDma(w);
            return Icon(
              above == null
                  ? LucideIcons.minus
                  : (above ? LucideIcons.chevronUp : LucideIcons.chevronDown),
              size: 12,
              color: above == null ? c.t4 : (above ? c.up : c.dn),
            );
          }),
        ),
    ]);
  }

  Widget _statusCell(BuildContext context, IndexQuote q) {
    final c = context.colors;
    final (label, tone) = switch (q.marketStatus) {
      'deep_dip' => ('Deep dip', c.accent),
      'dip' => ('Dip', c.accent),
      'attractive' => ('Attractive', c.up),
      'fair' => ('Normal', c.t2),
      'extended' => ('At its high', c.gold),
      _ => ('—', c.t4),
    };
    return Text(label,
        style: AppTextStyles.labelXs(tone), maxLines: 1);
  }

  Widget _pct(BuildContext context, double? v) => v == null
      ? _dash(context)
      : denseSignedNum(context, v, context.pnlColor(v), decimals: 1);

  Widget _dash(BuildContext context) => Text('—',
      style: AppTextStyles.labelXs(context.colors.t4),
      textAlign: TextAlign.right);
}


/// One labelled band of chips (BROAD MARKET, SECTORS, …).
class _GroupBand extends StatelessWidget {
  final String label;
  final List<IndexQuote> quotes;
  final bool compact;
  final bool isLast;

  const _GroupBand({
    required this.label,
    required this.quotes,
    required this.compact,
    required this.isLast,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: AppTextStyles.labelXs(c.t3)),
      const SizedBox(height: 6),
      Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          for (final q in quotes) _IndexChip(quote: q, compact: compact),
        ],
      ),
      if (!isLast) const SizedBox(height: 14),
    ]);
  }
}

class _IndexChip extends StatelessWidget {
  final IndexQuote quote;
  final bool compact;

  const _IndexChip({required this.quote, required this.compact});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final ok = quote.ok;
    final chg = quote.dayChgPct ?? 0;
    // Without a prior close there is no up or down to paint, so the chip stays
    // neutral rather than reading as a green flat day off a 0 fallback.
    final known = ok && quote.hasDayChange;
    final tone = known ? context.pnlColor(chg) : c.t4;

    // Index levels read better whole; the ETF proxies are two-decimal prices.
    final decimals = quote.group == IndexGroup.commodity ? 2 : 0;
    // The move needs a decimal the level does not: a 12.4-point day on NIFTY
    // rounds to "12 pts" at the level's precision, and a sub-point move on an
    // ETF proxy would round clean away to "0 pts".
    final chgDecimals = quote.group == IndexGroup.commodity ? 2 : 1;

    return Container(
      width: compact ? 152 : 190,
      padding: const EdgeInsets.fromLTRB(0, 7, 10, 7),
      decoration: BoxDecoration(
        color: known ? context.pnlBg(chg) : c.bg3,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: c.bd),
      ),
      // IntrinsicHeight is what lets the accent bar stretch: the chip sits in a
      // Wrap, so its height is unbounded, and a bare CrossAxisAlignment.stretch
      // would hand the bar an infinite height and collapse the whole card.
      child: IntrinsicHeight(
        child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Container(
            width: 3,
            margin: const EdgeInsets.only(right: 9),
            decoration: BoxDecoration(
              color: known ? tone : c.bd2,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(quote.label,
                    style: AppTextStyles.labelXs(c.t3),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis),
                const SizedBox(height: 2),
                Row(children: [
                  Expanded(
                    child: Text(
                      ok ? _fmt(quote.last, decimals) : '—',
                      style: AppTextStyles.monoBold(ok ? c.t1 : c.t4)
                          .copyWith(fontSize: 13),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (ok)
                    // A null day move is a dash, never 0.00%: the feed had no
                    // prior close to compare against, which is not a flat day.
                    Text(
                      quote.hasDayChange
                          ? '${chg > 0 ? '+' : ''}${chg.toStringAsFixed(2)}%'
                          : '—',
                      style: AppTextStyles.mono(
                              quote.hasDayChange ? tone : c.t4)
                          .copyWith(fontSize: 11),
                    ),
                ]),
                if (ok && quote.dayChg != null)
                  Text(
                    _signed(quote.dayChg!, chgDecimals),
                    style: AppTextStyles.mono(tone).copyWith(fontSize: 10),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                if (!compact) ...[
                  const SizedBox(height: 6),
                  _RangeBar(pct: quote.rangePct, tone: tone),
                  const SizedBox(height: 3),
                  Row(children: [
                    Expanded(
                      child: Text(
                        ok ? 'L ${_fmt(quote.low52w, decimals)}' : 'L —',
                        style: AppTextStyles.captionXs(c.t4),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    Text(
                      ok ? 'H ${_fmt(quote.high52w, decimals)}' : 'H —',
                      style: AppTextStyles.captionXs(c.t4),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ]),
                  const SizedBox(height: 2),
                  Text(
                    _offHighLabel(),
                    style: AppTextStyles.captionXs(c.t4),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ],
            ),
          ),
        ]),
      ),
    );
  }

  /// Never fabricates a reading. "no data" and "at 1-year high" are different
  /// statements and must look different.
  String _offHighLabel() {
    if (!quote.ok || quote.offHighPct == null) return 'no data';
    if (quote.atHigh) return 'at 1-year high';
    return '−${quote.offHighPct!.toStringAsFixed(1)}% off high';
  }

  String _signed(double v, int decimals) =>
      '${v > 0 ? '+' : v < 0 ? '−' : ''}${_fmt(v.abs(), decimals)} pts';

  String _fmt(double? v, int decimals) {
    if (v == null) return '—';
    final s = v.toStringAsFixed(decimals);
    // Indian digit grouping on the integer part.
    final parts = s.split('.');
    return parts.length > 1
        ? '${_group(parts[0])}.${parts[1]}'
        : _group(parts[0]);
  }

  String _group(String n) {
    if (n.length <= 3) return n;
    final head = n.substring(0, n.length - 3);
    final tail = n.substring(n.length - 3);
    final buf = StringBuffer();
    for (int i = 0; i < head.length; i++) {
      final fromEnd = head.length - i;
      buf.write(head[i]);
      if (fromEnd > 1 && fromEnd.isOdd) buf.write(',');
    }
    return '$buf,$tail';
  }
}

/// Where today's level sits inside the 52-week band: left edge is the 52-week
/// low, right edge the high.
///
/// A null [pct] draws the empty track with no marker. Defaulting an unknown
/// position to 0 would put the index on its 52-week low — the single most
/// action-provoking reading on the tape — purely because a field was missing.
class _RangeBar extends StatelessWidget {
  final double? pct;
  final Color tone;

  const _RangeBar({required this.pct, required this.tone});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final p = pct;
    // Fractional layout, not a LayoutBuilder: the chip measures itself through
    // IntrinsicHeight, and a LayoutBuilder cannot report an intrinsic size.
    return SizedBox(
      width: double.infinity,
      height: 4,
      child: Stack(children: [
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: c.bd,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
        ),
        if (p != null) ...[
          Positioned.fill(
            child: Align(
              alignment: Alignment.centerLeft,
              child: FractionallySizedBox(
                widthFactor: p / 100,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: tone.withValues(alpha: 0.45),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: Align(
              alignment: Alignment(p / 50 - 1, 0),
              child: SizedBox(
                width: 2,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: tone,
                    borderRadius: BorderRadius.circular(1),
                  ),
                ),
              ),
            ),
          ),
        ],
      ]),
    );
  }
}
