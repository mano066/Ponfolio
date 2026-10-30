import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/expense_schema.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';

/// A spreadsheet-style editable grid: a frozen left column (month / date) with
/// the remaining columns in a horizontally-scrolling area. Input cells are
/// editable TextFields; `calc` cells are read-only (auto-computed upstream).
/// Row heights are fixed so the frozen column and scroll area stay aligned.
class EditableGrid extends StatefulWidget {
  final IconData icon;
  final Color accent;
  final String title;
  final String? subtitle;
  final String frozenLabel;
  final double frozenWidth;
  final List<ECol> cols;
  final List<Map<String, dynamic>> rows;

  /// Frozen-cell text for a row (e.g. month title or date).
  final String Function(Map<String, dynamic> row, int index) frozenText;

  /// If true the frozen cell is an editable text field (stock dates).
  final bool frozenEditable;
  final void Function(int index, String value)? onFrozenCommit;

  /// Commit a scrollable cell edit. [value] is double for numbers, String text.
  final void Function(int index, String key, Object value) onCommit;

  /// Whether a row's `opening`-kind cell is editable (only the first month).
  final bool Function(int index) openingEditable;

  /// Column keys excluded from the totals footer (running balances etc.).
  final Set<String> totalSkip;

  final VoidCallback? onAddRow;
  final void Function(int index)? onDeleteRow;

  const EditableGrid({
    super.key,
    required this.icon,
    required this.accent,
    required this.title,
    this.subtitle,
    required this.frozenLabel,
    this.frozenWidth = 74,
    required this.cols,
    required this.rows,
    required this.frozenText,
    required this.onCommit,
    this.frozenEditable = false,
    this.onFrozenCommit,
    bool Function(int index)? openingEditable,
    this.totalSkip = const {},
    this.onAddRow,
    this.onDeleteRow,
  }) : openingEditable = openingEditable ?? _firstOnly;

  static bool _firstOnly(int i) => i == 0;

  static const _headerH = 30.0;
  static const _rowH = 34.0;
  static const _footerH = 34.0;

  @override
  State<EditableGrid> createState() => _EditableGridState();
}

class _EditableGridState extends State<EditableGrid> {
  final _hCtrl = ScrollController();

  @override
  void dispose() {
    _hCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final hasDelete = widget.onDeleteRow != null;

    return DenseCard(
      clip: true,
      child: Column(children: [
        denseTableHeader(context,
            icon: widget.icon,
            accent: widget.accent,
            title: widget.title,
            subtitle: widget.subtitle,
            trailing: widget.onAddRow == null
                ? null
                : HeaderButton(
                    icon: const Icon(LucideIcons.plus, size: 13, color: Colors.white),
                    text: 'Add row',
                    primary: true,
                    onTap: widget.onAddRow,
                  )),
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          // ── Frozen column ──
          _frozenColumn(context),
          Container(width: 1, color: c.bd),
          // ── Scrollable columns ──
          Expanded(
            child: Scrollbar(
              controller: _hCtrl,
              thumbVisibility: true,
              child: SingleChildScrollView(
                controller: _hCtrl,
                scrollDirection: Axis.horizontal,
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  _scrollHeader(context, hasDelete),
                  for (var i = 0; i < widget.rows.length; i++)
                    _scrollRow(context, i, hasDelete),
                  _scrollFooter(context, hasDelete),
                ]),
              ),
            ),
          ),
        ]),
      ]),
    );
  }

  Widget _frozenColumn(BuildContext context) {
    final c = context.colors;
    return SizedBox(
      width: widget.frozenWidth,
      child: Column(children: [
        Container(
          height: EditableGrid._headerH,
          alignment: Alignment.centerLeft,
          padding: const EdgeInsets.symmetric(horizontal: 10),
          decoration: BoxDecoration(
            color: c.bg3,
            border: Border(
                top: BorderSide(color: c.bd), bottom: BorderSide(color: c.bd)),
          ),
          child: Text(widget.frozenLabel,
              style: AppTextStyles.tableHeader(c.t3).copyWith(fontSize: 10)),
        ),
        for (var i = 0; i < widget.rows.length; i++)
          Container(
            height: EditableGrid._rowH,
            alignment: Alignment.centerLeft,
            padding: const EdgeInsets.symmetric(horizontal: 10),
            decoration: BoxDecoration(
              color: i.isOdd ? c.rowAlt : Colors.transparent,
              border: Border(bottom: BorderSide(color: c.bd.withValues(alpha: 0.6))),
            ),
            child: widget.frozenEditable
                ? _TextCell(
                    key: ValueKey('frz_${widget.title}_$i'),
                    initial: widget.frozenText(widget.rows[i], i),
                    onCommit: (v) => widget.onFrozenCommit?.call(i, v),
                    align: TextAlign.left,
                    color: c.t1)
                : Text(widget.frozenText(widget.rows[i], i),
                    style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12),
                    maxLines: 1, overflow: TextOverflow.ellipsis),
          ),
        Container(
          height: EditableGrid._footerH,
          alignment: Alignment.centerLeft,
          padding: const EdgeInsets.symmetric(horizontal: 10),
          decoration: BoxDecoration(
            color: c.bg3,
            border: Border(top: BorderSide(color: c.bd)),
          ),
          child: Text('TOTAL', style: AppTextStyles.labelXs(c.t2)),
        ),
      ]),
    );
  }

  Widget _scrollHeader(BuildContext context, bool hasDelete) {
    final c = context.colors;
    return Container(
      height: EditableGrid._headerH,
      decoration: BoxDecoration(
        color: c.bg3,
        border:
            Border(top: BorderSide(color: c.bd), bottom: BorderSide(color: c.bd)),
      ),
      child: Row(children: [
        for (final col in widget.cols)
          Container(
            width: col.width,
            padding: const EdgeInsets.symmetric(horizontal: 8),
            alignment: Alignment.centerRight,
            child: Text(col.label,
                style: AppTextStyles.tableHeader(
                        col.kind == ECellKind.calc ? widget.accent : c.t3)
                    .copyWith(fontSize: 10),
                textAlign: TextAlign.right,
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
          ),
        if (hasDelete) const SizedBox(width: 40),
      ]),
    );
  }

  Widget _scrollRow(BuildContext context, int i, bool hasDelete) {
    final c = context.colors;
    final row = widget.rows[i];
    return Container(
      height: EditableGrid._rowH,
      decoration: BoxDecoration(
        color: i.isOdd ? c.rowAlt : Colors.transparent,
        border: Border(bottom: BorderSide(color: c.bd.withValues(alpha: 0.6))),
      ),
      child: Row(children: [
        for (final col in widget.cols) _cell(context, col, row, i),
        if (hasDelete)
          SizedBox(
            width: 40,
            child: IconButton(
              padding: EdgeInsets.zero,
              iconSize: 14,
              splashRadius: 16,
              icon: Icon(LucideIcons.trash2, color: c.dn.withValues(alpha: 0.7)),
              onPressed: () => widget.onDeleteRow?.call(i),
            ),
          ),
      ]),
    );
  }

  Widget _cell(BuildContext context, ECol col, Map<String, dynamic> row, int i) {
    final c = context.colors;
    final editableOpening =
        col.kind == ECellKind.opening && widget.openingEditable(i);
    final isInput = col.kind == ECellKind.input || editableOpening;

    if (col.kind == ECellKind.text) {
      return _cellBox(col.width, _TextCell(
        key: ValueKey('${widget.title}_${col.key}_$i'),
        initial: (row[col.key] ?? '').toString(),
        onCommit: (v) => widget.onCommit(i, col.key, v),
        align: TextAlign.right,
        color: c.t1,
      ));
    }

    if (isInput) {
      return _cellBox(col.width, _NumCell(
        key: ValueKey('${widget.title}_${col.key}_$i'),
        initial: _readVal(row, col.key),
        onCommit: (v) => widget.onCommit(i, col.key, v),
      ));
    }

    // calc / read-only opening
    final v = _readVal(row, col.key);
    final col2 = col.key == 'balance'
        ? c.t1
        : (col.kind == ECellKind.calc ? c.t2 : c.t3);
    return _cellBox(
      col.width,
      Align(
        alignment: Alignment.centerRight,
        child: Text(_grp(v),
            style: AppTextStyles.mono(col2).copyWith(fontSize: 12),
            maxLines: 1, overflow: TextOverflow.ellipsis),
      ),
    );
  }

  Widget _scrollFooter(BuildContext context, bool hasDelete) {
    final c = context.colors;
    return Container(
      height: EditableGrid._footerH,
      decoration: BoxDecoration(
        color: c.bg3,
        border: Border(top: BorderSide(color: c.bd)),
      ),
      child: Row(children: [
        for (final col in widget.cols)
          _cellBox(
            col.width,
            Align(
              alignment: Alignment.centerRight,
              child: Text(
                widget.totalSkip.contains(col.key) || col.kind == ECellKind.text
                    ? ''
                    : _grp(_colTotal(col.key)),
                style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 12),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ),
        if (hasDelete) const SizedBox(width: 40),
      ]),
    );
  }

  /// Read a cell's numeric value, resolving `scrip:NAME` keys from the nested
  /// `scrips` map (per-trade stock buys are stored nested, not flat).
  double _readVal(Map<String, dynamic> row, String key) {
    if (key.startsWith('scrip:')) {
      final scr = row['scrips'];
      return scr is Map ? (scr[key.substring(6)] as num?)?.toDouble() ?? 0 : 0;
    }
    return ExpenseSchema.g(row, key);
  }

  double _colTotal(String key) {
    double s = 0;
    for (final r in widget.rows) {
      if (key.startsWith('scrip:')) {
        final name = key.substring(6);
        final scr = r['scrips'];
        if (scr is Map) s += (scr[name] as num?)?.toDouble() ?? 0;
      } else {
        s += ExpenseSchema.g(r, key);
      }
    }
    return s;
  }

  Widget _cellBox(double w, Widget child) => Container(
        width: w,
        height: EditableGrid._rowH,
        padding: const EdgeInsets.symmetric(horizontal: 4),
        alignment: Alignment.center,
        child: child,
      );

  /// Grouped number for display (western grouping, 2dp only when needed).
  static String _grp(double v) {
    if (v == 0) return '·';
    final neg = v < 0;
    final abs = v.abs();
    final whole = abs.roundToDouble() == abs;
    final intPart = abs.truncate();
    final buf = StringBuffer();
    final s = intPart.toString();
    for (var i = 0; i < s.length; i++) {
      if (i > 0 && (s.length - i) % 3 == 0) buf.write(',');
      buf.write(s[i]);
    }
    var out = buf.toString();
    if (!whole) {
      out += '.${(abs - intPart).toStringAsFixed(2).substring(2)}';
    }
    return '${neg ? '-' : ''}$out';
  }
}

/// Editable numeric cell. Commits on submit or focus loss.
class _NumCell extends StatefulWidget {
  final double initial;
  final void Function(double) onCommit;
  const _NumCell({super.key, required this.initial, required this.onCommit});
  @override
  State<_NumCell> createState() => _NumCellState();
}

class _NumCellState extends State<_NumCell> {
  late final TextEditingController _ctrl;
  final _focus = FocusNode();

  @override
  void initState() {
    super.initState();
    _ctrl = TextEditingController(text: _fmt(widget.initial));
    _focus.addListener(() {
      if (!_focus.hasFocus) _commit();
    });
  }

  static String _fmt(double v) {
    if (v == 0) return '';
    if (v.roundToDouble() == v) return v.toInt().toString();
    return v.toString();
  }

  void _commit() {
    final raw = _ctrl.text.trim().replaceAll(',', '');
    final v = raw.isEmpty ? 0.0 : (double.tryParse(raw) ?? widget.initial);
    if (v != widget.initial) widget.onCommit(v);
  }

  @override
  void didUpdateWidget(covariant _NumCell old) {
    super.didUpdateWidget(old);
    // Resync when the underlying value changes externally (year/section switch,
    // restore, recompute) — but never while the user is mid-edit.
    if (!_focus.hasFocus && widget.initial != old.initial) {
      final t = _fmt(widget.initial);
      if (_ctrl.text != t) _ctrl.text = t;
    }
  }

  @override
  void dispose() {
    _ctrl.dispose();
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return TextField(
      controller: _ctrl,
      focusNode: _focus,
      textAlign: TextAlign.right,
      style: AppTextStyles.mono(c.t1).copyWith(fontSize: 12),
      keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
      inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.\-]'))],
      // Commit live so edits reflect across the whole dashboard immediately
      // (and are never lost when navigating away before blur).
      onChanged: (_) => _commit(),
      onSubmitted: (_) => _commit(),
      decoration: InputDecoration(
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
        hintText: '·',
        hintStyle: AppTextStyles.mono(c.t4).copyWith(fontSize: 12),
        filled: true,
        fillColor: c.bg2,
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: BorderSide(color: c.bd.withValues(alpha: 0.5)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: BorderSide(color: c.blue, width: 1.4),
        ),
      ),
    );
  }
}

/// Editable free-text cell (e.g. transfer date). Commits on submit / blur.
class _TextCell extends StatefulWidget {
  final String initial;
  final void Function(String) onCommit;
  final TextAlign align;
  final Color color;
  const _TextCell(
      {super.key,
      required this.initial,
      required this.onCommit,
      this.align = TextAlign.left,
      required this.color});
  @override
  State<_TextCell> createState() => _TextCellState();
}

class _TextCellState extends State<_TextCell> {
  late final TextEditingController _ctrl;
  final _focus = FocusNode();

  @override
  void initState() {
    super.initState();
    _ctrl = TextEditingController(text: widget.initial);
    _focus.addListener(() {
      if (!_focus.hasFocus && _ctrl.text.trim() != widget.initial) {
        widget.onCommit(_ctrl.text.trim());
      }
    });
  }

  @override
  void didUpdateWidget(covariant _TextCell old) {
    super.didUpdateWidget(old);
    if (!_focus.hasFocus && widget.initial != old.initial) {
      if (_ctrl.text != widget.initial) _ctrl.text = widget.initial;
    }
  }

  @override
  void dispose() {
    _ctrl.dispose();
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return TextField(
      controller: _ctrl,
      focusNode: _focus,
      textAlign: widget.align,
      style: AppTextStyles.mono(widget.color).copyWith(fontSize: 12),
      onChanged: (v) => widget.onCommit(v.trim()),
      onSubmitted: (v) => widget.onCommit(v.trim()),
      decoration: InputDecoration(
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
        hintText: '—',
        hintStyle: AppTextStyles.mono(c.t4).copyWith(fontSize: 12),
        filled: true,
        fillColor: c.bg2,
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: BorderSide(color: c.bd.withValues(alpha: 0.5)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: BorderSide(color: c.blue, width: 1.4),
        ),
      ),
    );
  }
}
