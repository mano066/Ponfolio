import 'dart:async';
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
import 'package:aiei_wealth/services/export_service.dart';
import 'package:aiei_wealth/services/import_service.dart';

/// Mutual Funds — expanded version of the Dashboard MF table (Data-Dense style).
class MutualFundsScreen extends ConsumerStatefulWidget {
  const MutualFundsScreen({super.key});
  @override
  ConsumerState<MutualFundsScreen> createState() => _MutualFundsScreenState();
}

class _MutualFundsScreenState extends ConsumerState<MutualFundsScreen> {
  String? _expanded;
  bool _refreshing = false;

  // Transaction Form State
  String? _activeFormMode; // 'buy', 'sell', 'edit'
  Map<String, dynamic>? _editingTransaction;
  int? _editingIndex;

  // Form controllers
  final _dateController = TextEditingController();
  final _amountController = TextEditingController();
  final _unitsController = TextEditingController();
  final _navController = TextEditingController();

  static const _mfIndigo = Color(0xFF5367FF);
  static const _cols = [
    DenseCol('SCHEME', 4, numeric: false),
    DenseCol('UNITS', 2),
    DenseCol('AVG NAV', 2),
    DenseCol('NAV', 2),
    DenseCol('INVESTED', 2),
    DenseCol('CURRENT', 2),
    DenseCol('P&L', 2),
    DenseCol('RET%', 2),
    DenseCol('XIRR', 2),
    DenseCol('WT%', 2),
  ];
  static const double _gutter = 28;

  Future<void> _refreshNAV() async {
    setState(() => _refreshing = true);
    try {
      await ApiService().refreshMFNav();
      ref.invalidate(mfPortfolioProvider);
    } catch (_) {}
    setState(() => _refreshing = false);
  }

  void _showAddFundDialog() {
    showDialog(
      context: context,
      builder: (context) => const _AddFundDialog(),
    ).then((_) {
      ref.invalidate(mfPortfolioProvider);
    });
  }

  void _deleteFund(String schemeName) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: context.colors.bg2,
        title: Text('Remove Fund', style: AppTextStyles.heading3(context.colors.t1)),
        content: Text('Are you sure you want to remove "$schemeName" from your portfolio?', style: AppTextStyles.body(context.colors.t2)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: Text('Cancel', style: AppTextStyles.caption(context.colors.t3))),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text('Remove', style: AppTextStyles.caption(context.colors.dn)),
          ),
        ],
      ),
    );

    if (confirm == true) {
      try {
        await ApiService().deleteMFFund({'scheme_name': schemeName});
        ref.invalidate(mfPortfolioProvider);
      } catch (e) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  void _deleteTransaction(String schemeName, int index) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: context.colors.bg2,
        title: Text('Delete Transaction', style: AppTextStyles.heading3(context.colors.t1)),
        content: Text('Are you sure you want to delete this transaction?', style: AppTextStyles.body(context.colors.t2)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: Text('Cancel', style: AppTextStyles.caption(context.colors.t3))),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text('Delete', style: AppTextStyles.caption(context.colors.dn)),
          ),
        ],
      ),
    );

    if (confirm == true) {
      try {
        await ApiService().deleteMFTransaction({
          'scheme_name': schemeName,
          'index': index,
        });
        ref.invalidate(mfPortfolioProvider);
      } catch (e) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _submitTransactionForm(String schemeName) async {
    try {
      final amount = double.tryParse(_amountController.text) ?? 0.0;
      final data = {
        'scheme_name': schemeName,
        'date': _dateController.text,
        'invested': _activeFormMode == 'buy' || (_activeFormMode == 'edit' && _editingTransaction?['invested'] > 0) ? amount : 0.0,
        'redeemed': _activeFormMode == 'sell' || (_activeFormMode == 'edit' && _editingTransaction?['redeemed'] > 0) ? amount : 0.0,
        'units': double.tryParse(_unitsController.text) ?? 0.0,
        'nav': double.tryParse(_navController.text) ?? 0.0,
      };

      if (_activeFormMode == 'edit' && _editingIndex != null) {
        data['index'] = _editingIndex!;
        await ApiService().updateMFTransaction(data);
      } else {
        await ApiService().addMFTransaction(data);
      }

      setState(() {
        _activeFormMode = null;
        _editingTransaction = null;
        _editingIndex = null;
      });
      ref.invalidate(mfPortfolioProvider);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
    }
  }

  void _openForm(String mode, {Map<String, dynamic>? transaction, int? index}) {
    setState(() {
      _activeFormMode = mode;
      _editingTransaction = transaction;
      _editingIndex = index;

      if (transaction != null) {
        _dateController.text = transaction['date'] ?? '';
        final inv = (transaction['invested'] ?? 0).toDouble();
        final red = (transaction['redeemed'] ?? 0).toDouble();
        _amountController.text = (inv > 0 ? inv : red).toString();
        _unitsController.text = (transaction['units'] ?? 0).toDouble().toString();
        _navController.text = (transaction['nav'] ?? 0).toDouble().toString();
      } else {
        _dateController.text = DateTime.now().toString().split(' ')[0];
        _amountController.clear();
        _unitsController.clear();
        _navController.clear();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final mf = ref.watch(mfPortfolioProvider);

    return mf.when(
      loading: () => const DensePulseLoader(label: 'Loading mutual fund data…'),
      error: (e, _) => ErrorRetry(
        title: 'Error loading MF data',
        detail: '$e',
        icon: LucideIcons.alertTriangle,
        onRetry: () => ref.invalidate(mfPortfolioProvider),
      ),
      data: (data) {
        final funds = List<Map<String, dynamic>>.from(data['funds'] ?? []);
        final totalInv = (data['total_invested'] ?? 0).toDouble();
        final totalCur = (data['total_current'] ?? 0).toDouble();
        final totalPnl = (data['total_pnl'] ?? 0).toDouble();
        final totalPnlPct = (data['total_pnl_pct'] ?? 0).toDouble();
        final totalXirr = (data['total_xirr'] ?? 0).toDouble();

        // Largest positions first — what moves the book leads the table.
        final sorted = [...funds]..sort((a, b) => (b['current_value'] ?? 0)
            .toDouble()
            .compareTo((a['current_value'] ?? 0).toDouble()));

        return ListView(padding: EdgeInsets.zero, children: [
          // ── KPI GRID ──
          AnimatedListItem(
            index: 0,
            child: KpiGrid(perRow: 5, cells: [
              Kpi('MF INVESTED', formatINR(totalInv), '', c.t1),
              Kpi('CURRENT VALUE', formatINR(totalCur), '', c.t1),
              Kpi('TOTAL P&L', formatSignedINR(totalPnl), formatPct(totalPnlPct),
                  context.pnlColor(totalPnl)),
              Kpi('RETURN', formatPct(totalPnlPct), 'overall',
                  context.pnlColor(totalPnlPct)),
              Kpi('XIRR', formatPct(totalXirr, decimals: 1), 'annualized',
                  context.pnlColor(totalXirr)),
            ]),
          ),
          const SizedBox(height: 12),

          // ── DENSE HOLDINGS TABLE ──
          AnimatedListItem(
            index: 1,
            child: DenseCard(
              clip: true,
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                denseTableHeader(context,
                    icon: LucideIcons.layers,
                    accent: _mfIndigo,
                    title: 'Mutual Fund Holdings',
                    subtitle: '${funds.length} schemes · by weight',
                    trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                      HeaderButton(
                        icon: const Icon(LucideIcons.plus, size: 13, color: Colors.white),
                        text: 'Add Fund',
                        solidColor: c.up,
                        onTap: _showAddFundDialog,
                      ),
                      const SizedBox(width: 6),
                      HeaderButton(
                        icon: const Icon(LucideIcons.download, size: 13, color: Colors.white),
                        text: 'Export',
                        solidColor: c.blue,
                        onTap: () => exportService.exportMfPortfolioToCsv(funds),
                      ),
                      const SizedBox(width: 6),
                      HeaderButton(
                        icon: const Icon(LucideIcons.upload, size: 13, color: Colors.white),
                        text: 'Import',
                        solidColor: c.accent,
                        onTap: () async {
                          final added = await importService.importMfPortfolioFromCsv();
                          if (added > 0) ref.invalidate(mfPortfolioProvider);
                        },
                      ),
                      const SizedBox(width: 6),
                      HeaderButton(
                        icon: const Icon(LucideIcons.refreshCw, size: 13, color: Colors.white),
                        text: _refreshing ? 'Refreshing…' : 'Refresh NAV',
                        solidColor: c.accent,
                        loading: _refreshing,
                        onTap: _refreshNAV,
                      ),
                    ])),
                denseColumnHeader(context, _cols, leadingWidth: _gutter),
                if (funds.isEmpty)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 34),
                    child: Column(children: [
                      Icon(LucideIcons.layers, size: 24, color: c.t3),
                      const SizedBox(height: 10),
                      Text('No funds yet', style: AppTextStyles.heading3(c.t1)),
                      const SizedBox(height: 4),
                      Text('Click "Add Fund" to start tracking mutual fund holdings',
                          style: AppTextStyles.bodySmall(c.t3)),
                    ]),
                  )
                else
                  ...sorted.asMap().entries.map(
                      (e) => _buildFundRow(context, e.value, e.key, totalCur)),
                _footer(context, funds.length, totalInv, totalCur, totalPnl,
                    totalPnlPct, totalXirr),
              ]),
            ),
          ),
          const SizedBox(height: 36),
        ]);
      },
    );
  }

  Widget _buildFundRow(BuildContext context, Map<String, dynamic> f, int index, double totalCur) {
    final c = context.colors;
    final name = f['scheme_name'] ?? '';
    final category = (f['category'] ?? '').toString();
    final units = (f['units'] ?? 0).toDouble();
    final avgNav = (f['avg_nav'] ?? 0).toDouble();
    final nav = (f['nav'] ?? 0).toDouble();
    final invested = (f['invested'] ?? 0).toDouble();
    final curVal = (f['current_value'] ?? 0).toDouble();
    final pnl = curVal - invested;
    final ret = (f['return_pct'] ?? 0).toDouble();
    final xirr = (f['xirr'] ?? 0).toDouble();
    final wt = totalCur > 0 ? curVal / totalCur * 100 : 0.0;
    final isExp = _expanded == name;
    final txns = List<Map<String, dynamic>>.from(f['transactions'] ?? []);

    return Column(mainAxisSize: MainAxisSize.min, children: [
      DenseRow(
        alt: index.isOdd,
        highlighted: isExp,
        leadingWidth: _gutter,
        leading: Align(
          alignment: Alignment.centerLeft,
          child: Icon(isExp ? LucideIcons.chevronDown : LucideIcons.chevronRight,
              size: 14, color: c.t4),
        ),
        onTap: () {
          setState(() {
            _expanded = isExp ? null : name;
            _activeFormMode = null;
          });
        },
        cols: _cols,
        cells: [
          DInstrument(symbol: name, sub: category, up: pnl >= 0, ellipsis: true),
          denseNum(context, units.toStringAsFixed(3), c.t2),
          denseNum(context, avgNav.toStringAsFixed(2), c.t3),
          denseNum(context, nav.toStringAsFixed(2), c.t1, bold: true),
          denseNum(context, formatINR(invested), c.t3),
          denseNum(context, formatINR(curVal), c.t1),
          denseNum(context, formatSignedINR(pnl), context.pnlColor(pnl)),
          denseDelta(context, ret),
          denseNum(context, formatPct(xirr, decimals: 1), context.pnlColor(xirr)),
          DWeightCell(pct: wt, color: _mfIndigo),
        ],
      ),

      // Expanded Details and Transactions
      if (isExp)
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: c.bg1, border: Border(bottom: BorderSide(color: c.bd))),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            // Action Buttons
            Row(children: [
              _ActionButton(
                icon: LucideIcons.plusCircle,
                label: 'Buy More',
                color: c.up,
                onTap: () => _openForm('buy'),
              ),
              const SizedBox(width: 12),
              _ActionButton(
                icon: LucideIcons.minusCircle,
                label: 'Sell / Redeem',
                color: c.dn,
                onTap: () => _openForm('sell'),
              ),
              const Spacer(),
              _ActionButton(
                icon: LucideIcons.trash2,
                label: 'Remove Fund',
                color: c.dn,
                onTap: () => _deleteFund(name),
              ),
            ]),

            // Inline Transaction Form
            if (_activeFormMode != null) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: c.bg2,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: c.bd),
                ),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(
                    (_activeFormMode == 'buy'
                            ? 'ADD PURCHASE'
                            : _activeFormMode == 'sell'
                                ? 'ADD REDEMPTION'
                                : 'EDIT TRANSACTION'),
                    style: AppTextStyles.labelXs(c.t2),
                  ),
                  const SizedBox(height: 12),
                  Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                    Expanded(child: _buildTextField('DATE (YYYY-MM-DD)', _dateController)),
                    const SizedBox(width: 12),
                    Expanded(child: _buildTextField('AMOUNT (₹)', _amountController)),
                    const SizedBox(width: 12),
                    Expanded(child: _buildTextField('UNITS', _unitsController)),
                    const SizedBox(width: 12),
                    Expanded(child: _buildTextField('NAV (₹)', _navController)),
                    const SizedBox(width: 12),
                    HeaderButton(
                      text: 'Save',
                      solidColor: c.accent,
                      onTap: () => _submitTransactionForm(name),
                    ),
                    const SizedBox(width: 8),
                    HeaderButton(
                      text: 'Cancel',
                      onTap: () => setState(() => _activeFormMode = null),
                    ),
                  ]),
                ]),
              ),
            ],

            // Transaction History Table
            if (txns.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text('TRANSACTION HISTORY', style: AppTextStyles.labelXs(c.t3)),
              const SizedBox(height: 8),
              Container(
                clipBehavior: Clip.antiAlias,
                decoration: BoxDecoration(
                  border: Border.all(color: c.bd),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                    color: c.bg3,
                    child: Row(children: [
                      for (final h in ['DATE', 'INVESTED', 'REDEEMED', 'UNITS', 'NAV'])
                        Expanded(
                            child: Text(h,
                                style: AppTextStyles.tableHeader(c.t3).copyWith(fontSize: 10),
                                textAlign: h == 'DATE' ? TextAlign.left : TextAlign.right)),
                      const SizedBox(width: 60),
                    ]),
                  ),
                  ...txns.asMap().entries.map((entry) {
                    final idx = entry.key;
                    final t = entry.value;
                    return Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      decoration: BoxDecoration(
                        color: idx.isOdd ? c.rowAlt : null,
                        border: idx < txns.length - 1
                            ? Border(bottom: BorderSide(color: c.bd.withValues(alpha: 0.6)))
                            : null,
                      ),
                      child: Row(children: [
                        Expanded(
                            child: Text(t['date'] ?? '',
                                style: AppTextStyles.mono(c.t2).copyWith(fontSize: 12))),
                        Expanded(child: denseNum(context, '₹${(t['invested'] ?? 0).toDouble().toStringAsFixed(0)}', c.up)),
                        Expanded(child: denseNum(context, '₹${(t['redeemed'] ?? 0).toDouble().toStringAsFixed(0)}', c.dn)),
                        Expanded(child: denseNum(context, (t['units'] ?? 0).toDouble().toStringAsFixed(3), c.t2)),
                        Expanded(child: denseNum(context, '₹${(t['nav'] ?? 0).toDouble().toStringAsFixed(2)}', c.t1)),
                        SizedBox(width: 60, child: Row(mainAxisAlignment: MainAxisAlignment.end, children: [
                          IconButton(
                            icon: Icon(LucideIcons.edit2, size: 14, color: c.blue),
                            padding: EdgeInsets.zero, constraints: const BoxConstraints(), splashRadius: 16,
                            onPressed: () => _openForm('edit', transaction: t, index: idx),
                          ),
                          const SizedBox(width: 8),
                          IconButton(
                            icon: Icon(LucideIcons.trash2, size: 14, color: c.dn),
                            padding: EdgeInsets.zero, constraints: const BoxConstraints(), splashRadius: 16,
                            onPressed: () => _deleteTransaction(name, idx),
                          ),
                        ])),
                      ]),
                    );
                  }),
                ]),
              ),
            ],
          ]),
        ),
    ]);
  }

  Widget _footer(BuildContext context, int count, double inv, double cur,
      double pnl, double pnlPct, double xirr) {
    final c = context.colors;
    Widget cell(int flex, Widget child, {bool right = true}) => Expanded(
        flex: flex,
        child: Align(
            alignment: right ? Alignment.centerRight : Alignment.centerLeft,
            child: child));
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
      decoration:
          BoxDecoration(color: c.bg3, border: Border(top: BorderSide(color: c.bd))),
      child: Row(children: [
        const SizedBox(width: _gutter),
        cell(4, denseFootLabel(context, 'TOTAL · $count'), right: false),
        cell(2, const SizedBox()),
        cell(2, const SizedBox()),
        cell(2, const SizedBox()),
        cell(2, denseNum(context, formatINR(inv), c.t2, bold: true)),
        cell(2, denseNum(context, formatINR(cur), c.t1, bold: true)),
        cell(2, denseNum(context, formatSignedINR(pnl), context.pnlColor(pnl), bold: true)),
        cell(2, denseNum(context, formatPct(pnlPct), context.pnlColor(pnlPct), bold: true)),
        cell(2, denseNum(context, formatPct(xirr, decimals: 1), context.pnlColor(xirr), bold: true)),
        cell(2, const SizedBox()),
      ]),
    );
  }

  Widget _buildTextField(String label, TextEditingController controller) {
    final c = context.colors;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: AppTextStyles.labelXs(c.t3)),
        const SizedBox(height: 5),
        TextField(
          controller: controller,
          style: AppTextStyles.mono(c.t1).copyWith(fontSize: 12),
          decoration: InputDecoration(
            isDense: true,
            contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
            filled: true,
            fillColor: c.bg3,
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: c.bd)),
            enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: c.bd)),
            focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: c.accent)),
          ),
        ),
      ],
    );
  }
}

// ══════════════════════════════════════════
// ACTION BUTTON COMPONENT
// ══════════════════════════════════════════
class _ActionButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _ActionButton({required this.icon, required this.label, required this.color, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(6),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          border: Border.all(color: color.withValues(alpha: 0.22)),
          borderRadius: BorderRadius.circular(6),
        ),
        child: Row(children: [
          Icon(icon, size: 13, color: color),
          const SizedBox(width: 6),
          Text(label, style: AppTextStyles.labelXs(color)),
        ]),
      ),
    );
  }
}

// ══════════════════════════════════════════
// ADD FUND DIALOG
// ══════════════════════════════════════════
class _AddFundDialog extends StatefulWidget {
  const _AddFundDialog();

  @override
  State<_AddFundDialog> createState() => _AddFundDialogState();
}

class _AddFundDialogState extends State<_AddFundDialog> {
  final _searchController = TextEditingController();
  Timer? _debounce;
  List<dynamic> _results = [];
  bool _isLoading = false;
  bool _isAdding = false;

  @override
  void dispose() {
    _searchController.dispose();
    _debounce?.cancel();
    super.dispose();
  }

  void _onSearchChanged(String query) {
    if (_debounce?.isActive ?? false) _debounce!.cancel();
    _debounce = Timer(const Duration(milliseconds: 500), () async {
      if (query.length < 3) {
        setState(() => _results = []);
        return;
      }
      setState(() => _isLoading = true);
      try {
        final res = await ApiService().searchMFFund(query);
        setState(() => _results = res['results'] ?? []);
      } catch (e) {
        setState(() => _results = []);
      } finally {
        setState(() => _isLoading = false);
      }
    });
  }

  Future<void> _addFund(Map<String, dynamic> fund) async {
    setState(() => _isAdding = true);
    try {
      await ApiService().addMFFund({
        'scheme_name': fund['scheme_name'],
        'scheme_code': fund['scheme_code'],
        'category': 'Mutual Fund',
      });
      if (mounted) {
        Navigator.pop(context);
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Added ${fund['scheme_name']}')));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
    } finally {
      setState(() => _isAdding = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;

    return Dialog(
      backgroundColor: c.bg2,
      shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: BorderSide(color: c.bd)),
      child: Container(
        width: 500,
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              Row(children: [
                Icon(LucideIcons.plusCircle, size: 15, color: c.accent),
                const SizedBox(width: 8),
                Text('Add Mutual Fund', style: AppTextStyles.heading3(c.t1)),
              ]),
              IconButton(icon: Icon(LucideIcons.x, size: 16, color: c.t3), onPressed: () => Navigator.pop(context)),
            ]),
            const SizedBox(height: 14),
            TextField(
              controller: _searchController,
              onChanged: _onSearchChanged,
              style: AppTextStyles.body(c.t1),
              decoration: InputDecoration(
                isDense: true,
                contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
                hintText: 'Search scheme name (e.g., Parag Parikh Flexi Cap)…',
                hintStyle: AppTextStyles.bodySmall(c.t4),
                prefixIcon: Icon(LucideIcons.search, color: c.t3, size: 15),
                filled: true,
                fillColor: c.bg3,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: c.bd)),
                enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: c.bd)),
                focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: c.accent)),
              ),
            ),
            const SizedBox(height: 14),
            if (_isLoading)
              const Padding(padding: EdgeInsets.symmetric(vertical: 20), child: DensePulseLoader(label: 'Searching…'))
            else if (_results.isNotEmpty)
              Container(
                height: 300,
                clipBehavior: Clip.antiAlias,
                decoration: BoxDecoration(border: Border.all(color: c.bd), borderRadius: BorderRadius.circular(8)),
                child: ListView.separated(
                  itemCount: _results.length,
                  separatorBuilder: (context, index) => Divider(height: 1, color: c.bd.withValues(alpha: 0.6)),
                  itemBuilder: (context, index) {
                    final fund = _results[index];
                    return ListTile(
                      dense: true,
                      title: Text(fund['scheme_name'] ?? '',
                          style: AppTextStyles.bodySmall(c.t1)),
                      trailing: _isAdding
                        ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                        : HeaderButton(
                            text: 'Add',
                            solidColor: c.up,
                            onTap: () => _addFund(fund),
                          ),
                    );
                  },
                ),
              )
            else if (_searchController.text.length >= 3)
              Padding(
                  padding: const EdgeInsets.all(16),
                  child: Center(child: Text('No results found', style: AppTextStyles.bodySmall(c.t3)))),
          ],
        ),
      ),
    );
  }
}
