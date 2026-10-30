import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/deploy_models.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/providers/deploy_provider.dart';

/// MARKET TAPE — compact index tiles, scrolled horizontally.
///
/// Replaces the 31-row metrics table on the dashboard. The table was a fine
/// reading surface and a poor scanning one: the question here is "what is the
/// market doing", which is answered by a field of colour, not by reading down
/// a column of numbers.
///
/// **The palette is inverted relative to a P&L view, on purpose.** Red marks
/// an index at its own high — the risky place to deploy a dip reserve — and
/// green marks a genuine correction. That is the opposite of how a holdings
/// screen colours a fall, and it is correct here: this tape exists to find
/// places worth buying, so it must not paint the best of them in the colour
/// the rest of the app uses for loss.
class MarketTapeStrip extends ConsumerWidget {
  const MarketTapeStrip({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final tape = ref.watch(marketTapeProvider).value ?? MarketTape.empty;

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
          decoration: BoxDecoration(
            color: c.bg3,
            border: Border(bottom: BorderSide(color: c.bd)),
          ),
          child: Row(children: [
            Icon(LucideIcons.activity, size: 14, color: c.blue),
            const SizedBox(width: 8),
            Text('MARKET TAPE',
                style: AppTextStyles.bodyBold(c.t1)
                    .copyWith(fontSize: 12, letterSpacing: 0.6)),
            const SizedBox(width: 10),
            Flexible(
              child: Text(
                tape.hasData ? tape.summary : 'Waiting for market data…',
                style: AppTextStyles.labelXs(c.t3),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const Spacer(),
            if (tape.hasData)
              Text('${tape.up} up · ${tape.down} down',
                  style: AppTextStyles.labelXs(c.t3)),
          ]),
        ),
        if (tape.indices.isEmpty)
          const SizedBox(
            height: 96,
            child: DensePulseLoader(label: 'Loading market levels…'),
          )
        else
          _bands(context, tape),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 4, 14, 10),
          child: Text(
            'Green marks a correction worth looking at. Red marks an index at '
            'its high, where a dip reserve has nothing to buy. Gold and silver '
            'are shown through their ETFs, not the metal price.',
            style: AppTextStyles.captionXs(c.t4),
          ),
        ),
      ]),
    );
  }

  Widget _bands(BuildContext context, MarketTape tape) {
    final groups =
        IndexGroup.values.where((g) => tape.ofGroup(g).isNotEmpty).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final group in groups)
          _Band(label: indexGroupLabel(group), quotes: tape.ofGroup(group)),
      ],
    );
  }
}

/// One band of index tiles, wrapped to fit the width.
///
/// This band used to scroll horizontally, and the sector band has thirteen
/// tiles: at a fixed 176px each that is ~2,380px of content, so IT, PHARMA,
/// AUTO and FMCG sat off-screen to the LEFT with no hint they existed, and a
/// half-scrolled band left the tile at the edge sliced in two. A tape is
/// meant to be read at a glance, and an index you have to remember to scroll
/// for is an index you do not see. Wrapping shows every one of them.
class _Band extends StatelessWidget {
  final String label;
  final List<IndexQuote> quotes;

  /// Below this a tile's value and its day-change percentage stop fitting on
  /// one line, so the column count is chosen to keep tiles at least this wide.
  static const double _minTile = 168;

  /// A band with two tiles must not spread them across the whole card: Gold
  /// and Silver rendered ~800px wide each, dwarfing the thirteen sector tiles
  /// above them. Tiles grow only to fill a row they nearly fit.
  static const double _maxTile = 220;
  static const double _gap = 8;

  const _Band({required this.label, required this.quotes});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 2),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: AppTextStyles.labelXs(c.t3)),
        const SizedBox(height: 7),
        LayoutBuilder(builder: (context, box) {
          final width = box.maxWidth;
          final columns = width.isFinite
              ? ((width + _gap) / (_minTile + _gap))
                  .floor()
                  .clamp(1, quotes.isEmpty ? 1 : quotes.length)
              : quotes.length;
          // Tiles share the row rather than keeping a fixed width, so the last
          // one ends flush with the card instead of leaving a ragged gap.
          final tile = width.isFinite
              ? ((width - (columns - 1) * _gap) / columns).clamp(
                  _minTile, _maxTile)
              : _minTile;
          return Wrap(
            spacing: _gap,
            runSpacing: _gap,
            children: [
              for (final quote in quotes)
                SizedBox(
                  width: tile,
                  // Measured on the running app: the tile content is 95px, so
                  // the old 92 clipped every tile with an overflow stripe.
                  height: 100,
                  child: _IndexTile(quote: quote),
                ),
            ],
          );
        }),
      ]),
    );
  }
}

class _IndexTile extends StatelessWidget {
  final IndexQuote quote;
  const _IndexTile({required this.quote});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final ok = quote.ok;
    final chg = quote.dayChgPct ?? 0;
    final tone = _statusTone(context);

    return Container(
      padding: const EdgeInsets.fromLTRB(11, 9, 11, 9),
      decoration: BoxDecoration(
        color: ok ? tone.withValues(alpha: 0.06) : c.bg3,
        borderRadius: BorderRadius.circular(7),
        border: Border.all(
            color: ok ? tone.withValues(alpha: 0.30) : c.bd),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(quote.label,
              style: AppTextStyles.labelXs(c.t3),
              maxLines: 1,
              overflow: TextOverflow.ellipsis),
          const SizedBox(height: 3),
          Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Expanded(
              child: Text(
                ok ? _fmt(quote.last) : '—',
                style: AppTextStyles.monoBold(ok ? c.t1 : c.t4)
                    .copyWith(fontSize: 15, height: 1.0),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (ok && quote.hasDayChange)
              // Today's move keeps the CONVENTIONAL up/down colours: it is a
              // price change, not an opportunity reading, and flipping it here
              // would make the tile argue with itself.
              Text(
                '${chg > 0 ? '+' : ''}${chg.toStringAsFixed(2)}%',
                style: AppTextStyles.mono(context.pnlColor(chg))
                    .copyWith(fontSize: 11),
              )
            else if (ok && quote.spanChgPct != null)
              // No adjacent session, so no day move exists — but the move
              // since the last close on record does, and stating its period
              // makes it informative instead of blank. Rendered in the muted
              // tone with its span attached so it can never be read as today:
              // printing this figure AS a day change is what made FMCG show
              // -6.88% against a -0.34% Nifty.
              Tooltip(
                message: 'Change since the previous close on record '
                    '(${quote.prevBarDate ?? 'unknown'}), '
                    '${quote.dayChgSpanDays} days ago. This index is quoted '
                    'live but its daily history stops there, so there is no '
                    'same-day comparison to make.',
                child: Text(
                  '${quote.spanChgPct! > 0 ? '+' : ''}'
                  '${quote.spanChgPct!.toStringAsFixed(2)}%'
                  '${quote.dayChgSpanDays == null ? '' : ' · ${quote.dayChgSpanDays}d'}',
                  style: AppTextStyles.mono(c.t3).copyWith(fontSize: 10),
                ),
              )
            else if (ok)
              Tooltip(
                message: 'No prior close on record for this index.',
                child: Text('—',
                    style: AppTextStyles.mono(c.t4).copyWith(fontSize: 11)),
              ),
          ]),
          const SizedBox(height: 6),
          if (ok && quote.offHighPct != null)
            Text('↓ ${quote.offHighPct!.toStringAsFixed(1)}% from 52W high',
                style: AppTextStyles.captionXs(c.t3), maxLines: 1)
          else
            // Naming the reason beats a bare "no data": the index level IS
            // live, it is only the daily history that the feed does not carry,
            // and without that there is no high to measure a drawdown from.
            Text(quote.historyUnavailable ? 'no history for this index'
                                          : 'no data',
                style: AppTextStyles.captionXs(c.t4), maxLines: 1),
          if (ok && quote.aboveLowPct != null)
            Text('↑ ${quote.aboveLowPct!.toStringAsFixed(1)}% from 52W low',
                style: AppTextStyles.captionXs(c.t4), maxLines: 1),
          // The level is live but the daily bars stopped, so the 52-week
          // figures above are measured to that date and not to today. Saying
          // so is the difference between a stale number and a wrong one.
          if (ok && quote.staleHistory && quote.prevBarDate != null)
            Text('history to ${quote.prevBarDate}',
                style: AppTextStyles.captionXs(c.gold), maxLines: 1),
          const Spacer(),
          _statusChip(context, tone),
        ],
      ),
    );
  }

  Color _statusTone(BuildContext context) {
    final c = context.colors;
    return switch (quote.marketStatus) {
      'overheated' => c.dn,
      'normal' => c.gold,
      'dip' => c.accent,
      'attractive' => c.up,
      'high_risk' => c.dn,
      _ => c.t3,
    };
  }

  Widget _statusChip(BuildContext context, Color tone) {
    final c = context.colors;
    final (label, icon) = switch (quote.marketStatus) {
      'overheated' => ('OVERHEATED', LucideIcons.flame),
      'normal' => ('NORMAL', LucideIcons.minus),
      'dip' => ('DIP', LucideIcons.trendingDown),
      'attractive' => ('ATTRACTIVE', LucideIcons.trendingDown),
      'high_risk' => ('HIGH RISK', LucideIcons.triangleAlert),
      _ => (quote.historyUnavailable ? 'NO HISTORY' : '—',
            LucideIcons.circleHelp),
    };
    if (!quote.ok) {
      return Text('NOT AVAILABLE', style: AppTextStyles.labelXs(c.t4));
    }
    return Row(children: [
      Icon(icon, size: 10, color: tone),
      const SizedBox(width: 4),
      Text(label,
          style: AppTextStyles.bodyBold(tone)
              .copyWith(fontSize: 9.5, letterSpacing: 0.5)),
    ]);
  }

  String _fmt(double? v) {
    if (v == null) return '—';
    final decimals = quote.group == IndexGroup.commodity ? 2 : 0;
    final s = v.toStringAsFixed(decimals);
    final parts = s.split('.');
    return parts.length > 1
        ? '${_group(parts[0])}.${parts[1]}'
        : _group(parts[0]);
  }

  /// Indian digit grouping (1,00,000 rather than 100,000).
  String _group(String digits) {
    if (digits.length <= 3) return digits;
    final head = digits.substring(0, digits.length - 3);
    final tail = digits.substring(digits.length - 3);
    final buf = StringBuffer();
    for (var i = 0; i < head.length; i++) {
      if (i > 0 && (head.length - i) % 2 == 0) buf.write(',');
      buf.write(head[i]);
    }
    return '$buf,$tail';
  }
}
