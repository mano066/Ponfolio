import 'package:flutter/material.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';

/// Reusable premium table matching `.premium-table` from CSS.
/// Enhanced with hover glassmorphism, animated row entrance, and smooth expand.
class PremiumTable extends StatelessWidget {
  final IconData? headerIcon;
  final Color? headerIconBg;
  final Color? headerIconColor;
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final List<PremiumTableColumn> columns;
  final List<PremiumTableRow> rows;
  final PremiumTableRow? totalsRow;

  const PremiumTable({
    super.key,
    this.headerIcon,
    this.headerIconBg,
    this.headerIconColor,
    required this.title,
    this.subtitle,
    this.trailing,
    required this.columns,
    required this.rows,
    this.totalsRow,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      decoration: BoxDecoration(
        color: c.bg2, borderRadius: BorderRadius.circular(12),
        border: Border.all(color: c.bd),
      ),
      child: Column(children: [
        SectionHeader(
          icon: headerIcon, iconBg: headerIconBg, iconColor: headerIconColor,
          title: title, subtitle: subtitle, trailing: trailing,
        ),
        // Column headers
        Container(
          color: c.bg3,
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          child: Row(children: columns.map((col) => Expanded(
            flex: col.flex,
            child: Text(col.label, style: AppTextStyles.tableHeader(c.t4),
              textAlign: col.alignRight ? TextAlign.right : TextAlign.left),
          )).toList()),
        ),
        // Data rows — with hover highlight
        ...List.generate(rows.length, (i) => _HoverTableRow(
          row: rows[i],
          columns: columns,
          index: i,
        )),
        // Totals row
        if (totalsRow != null)
          Container(
            color: c.bg3,
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Row(children: List.generate(columns.length, (i) {
              final col = columns[i];
              return Expanded(flex: col.flex, child: i < totalsRow!.cells.length
                ? totalsRow!.cells[i]
                : const SizedBox.shrink());
            })),
          ),
      ]),
    );
  }
}

/// Table row with hover highlight effect
class _HoverTableRow extends StatefulWidget {
  final PremiumTableRow row;
  final List<PremiumTableColumn> columns;
  final int index;

  const _HoverTableRow({required this.row, required this.columns, required this.index});

  @override
  State<_HoverTableRow> createState() => _HoverTableRowState();
}

class _HoverTableRowState extends State<_HoverTableRow> {
  bool _hovering = false;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return MouseRegion(
      onEnter: (_) => setState(() => _hovering = true),
      onExit: (_) => setState(() => _hovering = false),
      child: GestureDetector(
        onTap: widget.row.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          padding: EdgeInsets.symmetric(horizontal: 14, vertical: widget.row.verticalPadding),
          decoration: BoxDecoration(
            color: _hovering ? c.bgH.withValues(alpha: 0.5) : Colors.transparent,
            border: Border(
              bottom: BorderSide(color: c.rowBorder),
              left: BorderSide(
                color: _hovering ? c.blue.withValues(alpha: 0.6) : Colors.transparent,
                width: 2,
              ),
            ),
          ),
          child: Row(children: List.generate(widget.columns.length, (i) {
            final col = widget.columns[i];
            return Expanded(flex: col.flex, child: i < widget.row.cells.length
              ? widget.row.cells[i]
              : const SizedBox.shrink());
          })),
        ),
      ),
    );
  }
}

/// Column definition for PremiumTable.
class PremiumTableColumn {
  final String label;
  final int flex;
  final bool alignRight;

  const PremiumTableColumn({
    required this.label,
    this.flex = 2,
    this.alignRight = false,
  });
}

/// Row definition for PremiumTable.
class PremiumTableRow {
  final List<Widget> cells;
  final double verticalPadding;
  final VoidCallback? onTap;

  const PremiumTableRow({
    required this.cells,
    this.verticalPadding = 9,
    this.onTap,
  });
}
