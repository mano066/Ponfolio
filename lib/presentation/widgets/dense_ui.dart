import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';

/// ─── Data-Dense UI kit ───
/// Shared building blocks for the "Data-Dense Dashboard" look (per ui-ux-pro-max):
/// neutral surfaces, hairline borders, ~12px padding, compact KPI grids and
/// monospace tables. Extracted from the Dashboard so every screen matches it.
///
/// Primitives:
///  • [DenseCard]          — the standard card surface (radius 14)
///  • [Kpi] + [KpiGrid]    — compact divider-separated KPI cells
///  • [DenseCol]           — table column spec
///  • [DenseTable]         — full header + column-header + rows + footer table
///  • [denseTableHeader] / [denseColumnHeader] / [DenseRow] — compose custom tables
///  • [denseNum] / [denseDelta] / [DInstrument] / [DWeightCell] / [DSignalBadge]
///  • [DenseEmptyCard] / [DensePulseLoader]

// ══════════════════════════════════════════════════════════════
//  SURFACE
// ══════════════════════════════════════════════════════════════

/// Standard dense card container. Wrap dense content in this for consistency.
class DenseCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry? padding;
  final bool clip;
  const DenseCard({super.key, required this.child, this.padding, this.clip = false});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      clipBehavior: clip ? Clip.antiAlias : Clip.none,
      decoration: cardSurface(context, radius: 14),
      child: child,
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  KPI GRID
// ══════════════════════════════════════════════════════════════

class Kpi {
  final String label, value, sub;
  final Color color;
  const Kpi(this.label, this.value, this.sub, this.color);
}

/// Divider-separated KPI cells, laid out [perRow] per row with hairline rules
/// between them — mirrors the Dashboard KPI grid.
class KpiGrid extends StatelessWidget {
  final List<Kpi> cells;
  final int perRow;

  /// Optional one-line caption under the cells, saying what the numbers are
  /// for. Cells carry a label and a value; only a caption can carry a meaning.
  final String? note;

  const KpiGrid(
      {super.key, required this.cells, this.perRow = 4, this.note});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    Widget rowOf(List<Kpi> items) => Row(
          children: List.generate(items.length * 2 - 1, (i) {
            if (i.isOdd) return Container(width: 1, height: 38, color: c.bd);
            return Expanded(child: _KpiCell(items[i ~/ 2]));
          }),
        );
    final rows = <List<Kpi>>[];
    for (var i = 0; i < cells.length; i += perRow) {
      rows.add(cells.sublist(i, (i + perRow).clamp(0, cells.length)));
    }
    return DenseCard(
      child: Column(children: [
        for (var r = 0; r < rows.length; r++) ...[
          if (r > 0) Container(height: 1, color: c.bd),
          Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: rowOf(rows[r])),
        ],
        if (note != null) ...[
          Container(height: 1, color: c.bd),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.fromLTRB(14, 7, 14, 8),
            color: c.bg3,
            child: Row(children: [
              Icon(LucideIcons.info, size: 11, color: c.t3),
              const SizedBox(width: 7),
              Expanded(
                  child: Text(note!, style: AppTextStyles.captionXs(c.t3))),
            ]),
          ),
        ],
      ]),
    );
  }
}

class _KpiCell extends StatelessWidget {
  final Kpi k;
  const _KpiCell(this.k);
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(k.label, style: AppTextStyles.labelXs(c.t3)),
            const SizedBox(height: 6),
            Text(k.value,
                style: AppTextStyles.monoBold(k.color).copyWith(fontSize: 15),
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
            if (k.sub.isNotEmpty) ...[
              const SizedBox(height: 2),
              Text(k.sub,
                  style: AppTextStyles.captionXs(c.t3),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
            ],
          ]),
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  TABLE PRIMITIVES
// ══════════════════════════════════════════════════════════════

class DenseCol {
  final String label;
  final int flex;
  final bool numeric;
  const DenseCol(this.label, this.flex, {this.numeric = true});
}

/// Right-aligned mono number cell.
Widget denseNum(BuildContext context, String text, Color color, {bool bold = false}) {
  final style = (bold ? AppTextStyles.monoBold(color) : AppTextStyles.mono(color))
      .copyWith(fontSize: 12);
  return Text(text, style: style, textAlign: TextAlign.right, maxLines: 1);
}

/// Signed % with an up/down arrow, right-aligned.
Widget denseDelta(BuildContext context, double chg) {
  final col = context.pnlColor(chg);
  return Row(mainAxisAlignment: MainAxisAlignment.end, children: [
    Icon(chg >= 0 ? LucideIcons.arrowUpRight : LucideIcons.arrowDownRight,
        size: 11, color: col),
    Flexible(
      child: Text(formatPct(chg),
          style: AppTextStyles.mono(col).copyWith(fontSize: 12),
          textAlign: TextAlign.right,
          maxLines: 1),
    ),
  ]);
}

/// Signed number with no arrow and a caller-chosen colour.
///
/// A sibling to [denseDelta], NOT a replacement: `denseDelta` hardcodes
/// "down = red", which is right for P&L and wrong wherever a fall is the
/// opportunity (a dip, a discount to cost). Those screens pick their own colour.
Widget denseSignedNum(BuildContext context, double value, Color color,
    {int decimals = 2, String suffix = '%'}) {
  final sign = value > 0 ? '+' : '';
  return Text('$sign${value.toStringAsFixed(decimals)}$suffix',
      style: AppTextStyles.mono(color).copyWith(fontSize: 12),
      textAlign: TextAlign.right,
      maxLines: 1);
}

/// Proportional bar of N coloured segments over a shared total.
///
/// [DWeightCell] only does filled-vs-rest. This is for showing what a value is
/// *made of* — a score's contributing factors, a budget's spent portion.
class DStackedBar extends StatelessWidget {
  /// (value, colour) pairs, drawn left to right.
  final List<(double, Color)> segments;
  final double total;
  final double height;
  final Color? rest;
  final double radius;

  const DStackedBar(
      {super.key,
      required this.segments,
      required this.total,
      this.height = 6,
      this.rest,
      this.radius = 2});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final denom = total > 0 ? total : 1.0;
    final filled = segments.fold<double>(0, (sum, s) => sum + (s.$1 > 0 ? s.$1 : 0));
    final gap = (denom - filled).clamp(0.0, denom);

    // Integer flex weights: a 10000x multiplier keeps sub-percent segments
    // visible instead of collapsing them to flex 0.
    int flexOf(double v) => (v / denom * 10000).round().clamp(0, 10000);

    final children = <Widget>[
      for (final (value, color) in segments)
        if (value > 0)
          Expanded(flex: flexOf(value), child: ColoredBox(color: color)),
      if (gap > 0)
        Expanded(flex: flexOf(gap), child: ColoredBox(color: rest ?? c.bg3)),
    ];
    if (children.isEmpty) {
      children.add(Expanded(child: ColoredBox(color: rest ?? c.bg3)));
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: SizedBox(height: height, child: Row(children: children)),
    );
  }
}

/// Small selectable chip, for filter strips and preset buttons.
class DFilterChip extends StatelessWidget {
  final String label;
  final bool selected;
  final Color? tone;
  final VoidCallback? onTap;

  const DFilterChip(
      {super.key,
      required this.label,
      required this.selected,
      this.tone,
      this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final accent = tone ?? c.blue;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(6),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: selected ? accent.withValues(alpha: 0.14) : c.bg3,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: selected ? accent : c.bd),
        ),
        child: Text(label,
            style: AppTextStyles.label(selected ? accent : c.t3)),
      ),
    );
  }
}

/// The kit's standard text-field decoration.
InputDecoration denseFieldDecoration(BuildContext context,
    {String hint = '', Color? focusColor, String? prefix}) {
  final c = context.colors;
  final accent = focusColor ?? c.blue;
  OutlineInputBorder border(Color color) => OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: BorderSide(color: color),
      );
  return InputDecoration(
    hintText: hint,
    hintStyle: AppTextStyles.mono(c.t4),
    prefixText: prefix,
    prefixStyle: AppTextStyles.monoBold(c.t2),
    isDense: true,
    filled: true,
    fillColor: c.bg3,
    contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
    enabledBorder: border(c.bd),
    border: border(c.bd),
    focusedBorder: border(accent),
  );
}

/// Instrument cell: colored bar + symbol + subtitle (sector/category).
class DInstrument extends StatelessWidget {
  final String symbol, sub;
  final bool up, ellipsis;

  /// Overrides the spine colour. [up] only offers up/down, but some screens
  /// encode something else there — asset kind, or a status like "overdue".
  final Color? spine;
  const DInstrument(
      {super.key,
      required this.symbol,
      required this.sub,
      required this.up,
      this.spine,
      this.ellipsis = false});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Row(children: [
      Container(
        width: 4,
        height: 22,
        decoration: BoxDecoration(
            color: spine ?? (up ? c.up : c.dn),
            borderRadius: BorderRadius.circular(2)),
      ),
      const SizedBox(width: 8),
      Expanded(
        child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(symbol,
                  style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
              if (sub.isNotEmpty)
                Text(sub,
                    style: AppTextStyles.captionXs(c.t3),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis),
            ]),
      ),
    ]);
  }
}

/// Weight cell: percentage + mini progress bar.
class DWeightCell extends StatelessWidget {
  final double pct;
  final Color? color;
  const DWeightCell({super.key, required this.pct, this.color});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final col = color ?? c.blue;
    return Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('${pct.toStringAsFixed(1)}%', style: AppTextStyles.monoXs(c.t2)),
          const SizedBox(height: 3),
          ClipRRect(
            borderRadius: BorderRadius.circular(2),
            child: SizedBox(
              height: 3,
              child: Row(children: [
                Expanded(
                    flex: pct.round().clamp(0, 100),
                    child: Container(color: col)),
                Expanded(
                    flex: (100 - pct.round()).clamp(0, 100),
                    child: Container(color: c.bd)),
              ]),
            ),
          ),
        ]);
  }
}

/// Signal / verdict badge (BUY / SELL / HOLD / ANALYZING …).
class DSignalBadge extends StatelessWidget {
  final String signal;
  final Alignment align;
  const DSignalBadge({super.key, required this.signal, this.align = Alignment.centerRight});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final s = signal.toUpperCase();
    Color col;
    if (['BUY', 'BULLISH', 'ACCUMULATE', 'OVERWEIGHT'].any(s.contains)) {
      col = c.up;
    } else if (['SELL', 'BEARISH', 'UNDERWEIGHT', 'AVOID'].any(s.contains)) {
      col = c.dn;
    } else if (s.contains('ANALY')) {
      col = c.accent;
    } else {
      col = c.t3;
    }
    return Align(
      alignment: align,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
        decoration: BoxDecoration(
          color: col.withValues(alpha: 0.10),
          border: Border.all(color: col.withValues(alpha: 0.22)),
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text(s.contains('ANALY') ? '···' : s,
            style: AppTextStyles.labelXs(col)),
      ),
    );
  }
}

/// Inset for one table cell, applied only to the side its text is anchored to.
///
/// A right-aligned number sits flush against its column's right edge and the
/// next left-aligned cell sits flush against its left edge — the same x — so
/// the two read as one word ('DAY%' beside 'SIGNAL' rendered 'DAY%SIGNAL').
/// Padding the anchored side puts the full 6px where those two meet while
/// costing 3px per column rather than 6px, which matters: the equity table
/// carries twelve columns at a 780px minimum width and padding both sides
/// overflowed it.
EdgeInsets denseCellInset(DenseCol col) => col.numeric
    ? const EdgeInsets.only(right: 3)
    : const EdgeInsets.only(left: 3);

/// Table header bar: icon + title + subtitle + optional trailing widget.
Widget denseTableHeader(
  BuildContext context, {
  required IconData icon,
  required Color accent,
  required String title,
  String? subtitle,
  Widget? trailing,
}) {
  final c = context.colors;
  return Padding(
    padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
    child: Row(children: [
      Icon(icon, size: 15, color: accent),
      const SizedBox(width: 8),
      // One Expanded absorbs all the slack, so the trailing widget keeps its
      // natural width and the title/subtitle ellipsize into whatever is left.
      // A Spacer beside loose Flexible texts does not work here: the Spacer
      // claims its share of the free space whether the texts used theirs or
      // not, and the row overflows by the difference in a narrow card.
      Expanded(
        child: Row(children: [
          Flexible(
              child: Text(title,
                  style: AppTextStyles.heading3(c.t1),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis)),
          if (subtitle != null) ...[
            const SizedBox(width: 8),
            Flexible(
                child: Text(subtitle,
                    style: AppTextStyles.captionXs(c.t3),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis)),
          ],
        ]),
      ),
      if (trailing != null) ...[const SizedBox(width: 8), trailing],
    ]),
  );
}

/// Plain-English explainer strip that sits directly under a section header.
///
/// Every analysis card answers one question and implies one decision, but the
/// numbers alone never say which. [question] and [reading] stay visible so a
/// first-time reader knows what they are looking at; the thresholds and the
/// action expand on tap, so no card permanently carries a paragraph of prose.
///
/// Keep [question] short — it shares a line with the toggle at the 780px
/// minimum content width.
class SectionExplainer extends StatefulWidget {
  /// The question this section answers, in the reader's own words.
  final String question;

  /// One line naming what the numbers on screen actually are.
  final String reading;

  /// Threshold rules — "over 40% = high risk" style lines.
  final List<String> rules;

  /// The decision this section should drive.
  final String action;

  /// Section accent, so the strip reads as part of the card above it.
  final Color accent;

  /// Drops the hairline above — use when the strip opens a card.
  final bool borderTop;

  /// Hides the toggle's text label, for cards narrower than ~340px.
  final bool compact;

  const SectionExplainer({
    super.key,
    required this.question,
    required this.reading,
    required this.action,
    required this.accent,
    this.rules = const [],
    this.borderTop = true,
    this.compact = false,
  });

  @override
  State<SectionExplainer> createState() => _SectionExplainerState();
}

class _SectionExplainerState extends State<SectionExplainer> {
  bool _open = false;

  @override
  void didUpdateWidget(SectionExplainer old) {
    super.didUpdateWidget(old);
    // Tab switches swap one section's card for another's at the same slot, and
    // an unkeyed widget of the same type inherits the old State — which would
    // hand the new tab an explainer someone already expanded elsewhere.
    // The question identifies the section, so a change of question is a change
    // of card: collapse it again.
    if (old.question != widget.question) _open = false;
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: c.bg3,
        border: Border(
          top: widget.borderTop ? BorderSide(color: c.bd) : BorderSide.none,
          bottom: BorderSide(color: c.bd),
        ),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        InkWell(
          onTap: () => setState(() => _open = !_open),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 8, 12, 8),
            child: Row(children: [
              Icon(LucideIcons.helpCircle, size: 12, color: widget.accent),
              const SizedBox(width: 8),
              Expanded(
                child: Text.rich(
                  TextSpan(children: [
                    TextSpan(
                        text: widget.question,
                        style: AppTextStyles.bodySmall(c.t2)
                            .copyWith(fontWeight: FontWeight.w600)),
                    TextSpan(
                        text: '  ${widget.reading}',
                        style: AppTextStyles.captionXs(c.t3)),
                  ]),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 8),
              if (!widget.compact)
                Text(_open ? 'Hide' : 'How to read',
                    style: AppTextStyles.labelXs(widget.accent)),
              Icon(_open ? LucideIcons.chevronUp : LucideIcons.chevronDown,
                  size: 12, color: widget.accent),
            ]),
          ),
        ),
        AnimatedCrossFade(
          firstChild: const SizedBox(width: double.infinity, height: 0),
          secondChild: Padding(
            padding: const EdgeInsets.fromLTRB(34, 0, 14, 11),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ...widget.rules.map((r) => Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Padding(
                                padding: const EdgeInsets.only(top: 5),
                                child: Container(
                                  width: 3,
                                  height: 3,
                                  decoration: BoxDecoration(
                                      color: c.t3, shape: BoxShape.circle),
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                  child: Text(r,
                                      style: AppTextStyles.bodySmall(c.t2)
                                          .copyWith(fontSize: 11))),
                            ]),
                      )),
                  if (widget.rules.isNotEmpty) const SizedBox(height: 4),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
                    decoration: BoxDecoration(
                      color: widget.accent.withValues(alpha: 0.06),
                      borderRadius: BorderRadius.circular(5),
                      border: Border.all(
                          color: widget.accent.withValues(alpha: 0.18)),
                    ),
                    child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(LucideIcons.arrowRightCircle,
                              size: 11, color: widget.accent),
                          const SizedBox(width: 7),
                          Expanded(
                              child: Text(widget.action,
                                  style: AppTextStyles.bodySmall(c.t1)
                                      .copyWith(fontSize: 11))),
                        ]),
                  ),
                ]),
          ),
          crossFadeState:
              _open ? CrossFadeState.showSecond : CrossFadeState.showFirst,
          duration: const Duration(milliseconds: 220),
        ),
      ]),
    );
  }
}

/// Right-aligned P&L trailing widget for a table header.
Widget densePnlTrailing(BuildContext context, double pnl, double pnlPct) {
  return Row(mainAxisSize: MainAxisSize.min, children: [
    Icon(pnl >= 0 ? LucideIcons.arrowUpRight : LucideIcons.arrowDownRight,
        size: 13, color: context.pnlColor(pnl)),
    const SizedBox(width: 2),
    Text('${formatSignedINR(pnl)}  ${formatPct(pnlPct)}',
        style: AppTextStyles.monoBold(context.pnlColor(pnl)).copyWith(fontSize: 12)),
  ]);
}

/// The grey column-header strip. [leadingWidth] reserves a left gutter (e.g. for
/// an expand chevron) so cells align with the rows below.
Widget denseColumnHeader(BuildContext context, List<DenseCol> cols,
    {double leadingWidth = 0}) {
  final c = context.colors;
  return Container(
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
    decoration: BoxDecoration(
      color: c.bg3,
      border: Border(top: BorderSide(color: c.bd), bottom: BorderSide(color: c.bd)),
    ),
    child: Row(children: [
      if (leadingWidth > 0) SizedBox(width: leadingWidth),
      // A 3px inset per side. Without it a right-aligned numeric header sits
      // flush against the next left-aligned one and the two read as a single
      // word — 'DAY%' beside 'SIGNAL' rendered as 'DAY%SIGNAL'. The same
      // inset is applied to the row cells so values stay under their header.
      ...cols.map((col) => Expanded(
            flex: col.flex,
            child: Padding(
              padding: denseCellInset(col),
              child: Text(col.label,
                  style: AppTextStyles.tableHeader(c.t3).copyWith(fontSize: 10),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: col.numeric ? TextAlign.right : TextAlign.left),
            ),
          )),
    ]),
  );
}

/// A single hover-highlighted table row. Supports an optional [leading] widget
/// (chevron gutter) and [onTap].
class DenseRow extends StatefulWidget {
  final List<Widget> cells;
  final List<DenseCol> cols;
  final bool alt;
  final bool highlighted;
  final Widget? leading;
  final double leadingWidth;
  final VoidCallback? onTap;
  const DenseRow({
    super.key,
    required this.cells,
    required this.cols,
    this.alt = false,
    this.highlighted = false,
    this.leading,
    this.leadingWidth = 0,
    this.onTap,
  });
  @override
  State<DenseRow> createState() => _DenseRowState();
}

class _DenseRowState extends State<DenseRow> {
  bool _h = false;
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final row = MouseRegion(
      cursor: widget.onTap != null ? SystemMouseCursors.click : MouseCursor.defer,
      onEnter: (_) => setState(() => _h = true),
      onExit: (_) => setState(() => _h = false),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: (_h || widget.highlighted)
              ? c.blue.withValues(alpha: 0.06)
              : (widget.alt ? c.rowAlt : Colors.transparent),
          border: Border(bottom: BorderSide(color: c.bd.withValues(alpha: 0.6))),
        ),
        child: Row(children: [
          if (widget.leadingWidth > 0)
            SizedBox(width: widget.leadingWidth, child: widget.leading),
          // Matches the header inset above, so a right-aligned number never
          // touches the cell beside it either.
          ...List.generate(
              widget.cols.length,
              (i) => Expanded(
                    flex: widget.cols[i].flex,
                    child: Padding(
                      padding: denseCellInset(widget.cols[i]),
                      child: widget.cells[i],
                    ),
                  )),
        ]),
      ),
    );
    if (widget.onTap == null) return row;
    return GestureDetector(onTap: widget.onTap, child: row);
  }
}

/// Full dense table: header + column header + rows + optional footer + view-all.
class DenseTable extends StatelessWidget {
  final IconData icon;
  final Color accent;
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final List<DenseCol> cols;
  final List<List<Widget>> rows;
  final List<Widget>? footer;
  final int overflow;
  final VoidCallback? onViewAll;
  const DenseTable({
    super.key,
    required this.icon,
    required this.accent,
    required this.title,
    this.subtitle,
    this.trailing,
    required this.cols,
    required this.rows,
    this.footer,
    this.overflow = 0,
    this.onViewAll,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return DenseCard(
      clip: true,
      child: Column(children: [
        denseTableHeader(context,
            icon: icon, accent: accent, title: title, subtitle: subtitle, trailing: trailing),
        denseColumnHeader(context, cols),
        ...rows.asMap().entries.map((e) =>
            DenseRow(cells: e.value, cols: cols, alt: e.key.isOdd)),
        if (footer != null)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
            decoration: BoxDecoration(
              color: c.bg3,
              border: Border(top: BorderSide(color: c.bd)),
            ),
            child: Row(
              children: List.generate(cols.length, (i) {
                final col = cols[i];
                return Expanded(
                  flex: col.flex,
                  child: Padding(
                    padding: denseCellInset(col),
                    child: Align(
                      alignment: col.numeric
                          ? Alignment.centerRight
                          : Alignment.centerLeft,
                      child: footer![i],
                    ),
                  ),
                );
              }),
            ),
          ),
        if (overflow > 0 && onViewAll != null)
          InkWell(
            onTap: onViewAll,
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 11),
              decoration: BoxDecoration(border: Border(top: BorderSide(color: c.bd))),
              child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                Text('View all $overflow more',
                    style: AppTextStyles.bodyBold(accent).copyWith(fontSize: 12)),
                const SizedBox(width: 4),
                Icon(LucideIcons.chevronRight, size: 14, color: accent),
              ]),
            ),
          ),
      ]),
    );
  }
}

/// Footer label (left-aligned, muted) for a totals row.
Widget denseFootLabel(BuildContext context, String text) =>
    Text(text, style: AppTextStyles.labelXs(context.colors.t2));

// ══════════════════════════════════════════════════════════════
//  EMPTY + LOADING
// ══════════════════════════════════════════════════════════════

class DenseEmptyCard extends StatelessWidget {
  final IconData icon;
  final String title, sub;
  const DenseEmptyCard(
      {super.key, required this.icon, required this.title, required this.sub});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return DenseCard(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 32),
      child: Column(children: [
        Icon(icon, size: 26, color: c.t3),
        const SizedBox(height: 12),
        Text(title, style: AppTextStyles.heading3(c.t1)),
        const SizedBox(height: 5),
        Text(sub, style: AppTextStyles.bodySmall(c.t3), textAlign: TextAlign.center),
      ]),
    );
  }
}

class DensePulseLoader extends StatefulWidget {
  final String label;
  const DensePulseLoader({super.key, this.label = 'Loading…'});
  @override
  State<DensePulseLoader> createState() => _DensePulseLoaderState();
}

class _DensePulseLoaderState extends State<DensePulseLoader>
    with SingleTickerProviderStateMixin {
  late AnimationController _c;
  @override
  void initState() {
    super.initState();
    _c = AnimationController(vsync: this, duration: const Duration(seconds: 1))
      ..repeat(reverse: true);
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final clr = context.colors;
    return Center(
      child: AnimatedBuilder(
          animation: _c,
          builder: (context, child) =>
              Column(mainAxisSize: MainAxisSize.min, children: [
                Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: clr.blue.withValues(alpha: 0.06 + _c.value * 0.06),
                        border: Border.all(
                            color: clr.blue
                                .withValues(alpha: 0.15 + _c.value * 0.15))),
                    child: Icon(LucideIcons.wallet,
                        size: 20,
                        color: clr.blue.withValues(alpha: 0.4 + _c.value * 0.6))),
                const SizedBox(height: 14),
                Text(widget.label, style: AppTextStyles.bodySmall(clr.t3)),
              ])),
    );
  }
}
