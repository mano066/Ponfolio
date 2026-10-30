import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_colors.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/closed_positions.dart';
import 'package:aiei_wealth/providers/providers.dart';
import 'package:aiei_wealth/presentation/widgets/closed_positions_section.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/presentation/widgets/stock_picker.dart';
import 'package:aiei_wealth/services/api_service.dart';
import 'package:aiei_wealth/services/export_service.dart';
import 'package:aiei_wealth/services/import_service.dart';

/// Equities-only view — dense stock table with full detail (Data-Dense style).
class EquitiesScreen extends ConsumerStatefulWidget {
  const EquitiesScreen({super.key});
  @override
  ConsumerState<EquitiesScreen> createState() => _EquitiesScreenState();
}

class _EquitiesScreenState extends ConsumerState<EquitiesScreen> {
  String? _expanded;
  Map<String, dynamic>? _deepData;
  Map<String, dynamic>? _historyData;
  bool _deepLoading = false;
  bool _historyLoading = false;
  String? _historyError;
  bool _tradebookLoading = false;
  bool _pnlLoading = false;
  bool _ledgerLoading = false;

  static const _cols = [
    DenseCol('INSTRUMENT', 3, numeric: false),
    DenseCol('QTY', 1),
    DenseCol('AVG', 2),
    DenseCol('LTP', 2),
    DenseCol('INVESTED', 2),
    DenseCol('CUR VAL', 2),
    DenseCol('P&L', 2),
    DenseCol('NET%', 2),
    DenseCol('XIRR', 2),
    DenseCol('DAY%', 2),
    DenseCol('SIGNAL', 2, numeric: false),
    DenseCol('ADVISOR', 2, numeric: false),
  ];
  static const double _gutter = 28;

  Future<void> _loadDeep(String symbol) async {
    setState(() {
      _deepLoading = true;
      _deepData = null;
    });
    try {
      final result = await ApiService().getDeepAnalysis(symbol);
      if (mounted && _expanded == symbol) _deepData = result;
    } catch (_) {}
    if (mounted && _expanded == symbol) {
      setState(() => _deepLoading = false);
    }
  }

  Future<void> _loadHistory(String symbol) async {
    setState(() {
      _historyLoading = true;
      _historyData = null;
      _historyError = null;
    });
    try {
      final result = await ApiService().getEquityTransactions(symbol);
      if (mounted && _expanded == symbol) {
        setState(() => _historyData = result);
      }
    } catch (_) {
      if (mounted && _expanded == symbol) {
        setState(
          () => _historyError =
              'Could not load trade history. Check the backend connection and retry.',
        );
      }
    } finally {
      if (mounted && _expanded == symbol) {
        setState(() => _historyLoading = false);
      }
    }
  }

  Future<void> _deleteStock(
    BuildContext context,
    String symbol,
    String cleanName,
  ) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: context.colors.bg2,
        title: Text(
          'Remove Stock',
          style: AppTextStyles.heading3(context.colors.t1),
        ),
        content: Text(
          'Remove "$cleanName" from your portfolio?',
          style: AppTextStyles.body(context.colors.t2),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(
              'Cancel',
              style: AppTextStyles.caption(context.colors.t3),
            ),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(
              'Remove',
              style: AppTextStyles.caption(context.colors.dn),
            ),
          ),
        ],
      ),
    );
    if (confirm == true) {
      try {
        await ApiService().deleteStock(symbol);
        ref.invalidate(portfolioProvider);
      } catch (e) {
        if (!mounted) return;
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _importTradebook() async {
    if (_tradebookLoading) return;
    setState(() => _tradebookLoading = true);
    try {
      final result = await importService.importTradebookFromCsv();
      if (!mounted || result == null) return;

      ref.invalidate(portfolioProvider);
      final added = (result['added'] as num?)?.toInt() ?? 0;
      final existing = (result['already_present'] as num?)?.toInt() ?? 0;
      final report = result['report'] is Map
          ? Map<String, dynamic>.from(result['report'] as Map)
          : const <String, dynamic>{};
      final skipped = (report['skipped'] as num?)?.toInt() ?? 0;
      final message = added > 0
          ? 'Trade history updated: $added new, $existing already saved'
          : 'Trade history is up to date: $existing trades already saved';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(skipped > 0 ? '$message · $skipped skipped' : message),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Tradebook import failed. Choose a Zerodha Console tradebook CSV and try again. ($e)',
          ),
        ),
      );
    } finally {
      if (mounted) setState(() => _tradebookLoading = false);
    }
  }

  /// Import one period's Kite Console funds ledger.
  ///
  /// The ledger is the only export that carries TDS — neither the tradebook
  /// nor the P&L charge block mentions it — so without this the cost of
  /// trading is short by whatever was withheld.
  Future<void> _importKiteLedger() async {
    if (_ledgerLoading) return;
    setState(() => _ledgerLoading = true);
    try {
      final result = await importService.importKiteLedger();
      if (!mounted || result == null) return;

      ref.invalidate(closedPositionsProvider);
      final period = result['period'] is Map
          ? Map<String, dynamic>.from(result['period'] as Map)
          : const <String, dynamic>{};
      final span = '${period['from'] ?? '?'} → ${period['to'] ?? '?'}';
      final tds = (result['tds_deducted'] as num?)?.toDouble() ?? 0;
      final blocked =
          (result['tds_provisional_outstanding'] as num?)?.toDouble() ?? 0;
      final entries = (result['entries'] as num?)?.toInt() ?? 0;
      final replaced = result['replaced'] == true;
      final conflicts = (result['conflicts'] as List? ?? const []).length;

      final money = NumberFormat.currency(
        locale: 'en_IN',
        symbol: '₹',
        decimalDigits: 0,
      );
      final parts = <String>[
        replaced ? 'Ledger replaced for $span' : 'Ledger imported: $span',
        'TDS ${money.format(tds)}',
        if (blocked.abs() > 0.5) '${money.format(blocked)} still blocked',
        '$entries entries',
      ];
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            conflicts > 0
                ? '${parts.join(' · ')} — WARNING: overlaps $conflicts other '
                      'period(s), remove one or TDS doubles'
                : parts.join(' · '),
          ),
          duration: Duration(seconds: conflicts > 0 ? 9 : 5),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Ledger import failed. Use the XLSX from Console → Reports → '
            'Ledger. ($e)',
          ),
        ),
      );
    } finally {
      if (mounted) setState(() => _ledgerLoading = false);
    }
  }

  /// Import one period's Kite Console P&L statement.
  ///
  /// The statement is what makes the closed book measured rather than
  /// reconstructed: it carries Zerodha's own realised figure and the charges
  /// actually billed. Filed by the period printed in its title, so importing
  /// one month at a time accumulates and re-importing a month replaces it.
  Future<void> _importKitePnl() async {
    if (_pnlLoading) return;
    setState(() => _pnlLoading = true);
    try {
      final result = await importService.importKitePnl();
      if (!mounted || result == null) return;

      ref.invalidate(closedPositionsProvider);
      final period = result['period'] is Map
          ? Map<String, dynamic>.from(result['period'] as Map)
          : const <String, dynamic>{};
      final span = '${period['from'] ?? '?'} → ${period['to'] ?? '?'}';
      final realized = (result['realized_pnl'] as num?)?.toDouble();
      final charges = (result['charges_actual'] as num?)?.toDouble();
      final closed = (result['symbols_closed'] as num?)?.toInt() ?? 0;
      final replaced = result['replaced'] == true;
      final conflicts = (result['conflicts'] as List? ?? const []).length;

      final money = NumberFormat.currency(
        locale: 'en_IN',
        symbol: '₹',
        decimalDigits: 0,
      );
      final parts = <String>[
        replaced ? 'Statement replaced for $span' : 'Statement imported: $span',
        if (realized != null) 'realised ${money.format(realized)}',
        if (charges != null) 'charges ${money.format(charges)}',
        '$closed closed',
      ];
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            conflicts > 0
                ? '${parts.join(' · ')} — WARNING: overlaps $conflicts other '
                      'period(s), remove one or totals double'
                : parts.join(' · '),
          ),
          duration: Duration(seconds: conflicts > 0 ? 9 : 5),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'P&L import failed. Use the XLSX from Console → Reports → P&L. ($e)',
          ),
        ),
      );
    } finally {
      if (mounted) setState(() => _pnlLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final portfolio = ref.watch(livePortfolioProvider);
    final holdings = ref.watch(enrichedHoldingsProvider);

    return portfolio.when(
      loading: () => const DensePulseLoader(label: 'Loading equity holdings…'),
      error: (e, _) => ErrorRetry(
        title: 'Error loading equities',
        detail: '$e',
        icon: LucideIcons.alertTriangle,
        onRetry: () => ref.invalidate(portfolioProvider),
      ),
      data: (pData) {
        final totalInvested = (pData['total_invested'] ?? 0).toDouble();
        final totalValue = (pData['total_portfolio_value'] ?? 0).toDouble();
        final totalPnl = (pData['total_pnl'] ?? 0).toDouble();
        final totalPnlPct = (pData['total_pnl_pct'] ?? 0).toDouble();
        // Book XIRR travels with the portfolio payload, so it stays consistent
        // with the per-holding XIRR in the rows below. Null when no holding has
        // dated trades on record.
        final rawXirr = pData['total_xirr'];
        final totalXirr = rawXirr is num ? rawXirr.toDouble() : null;
        final xirrCovered = (pData['xirr_covered_pct'] ?? 0).toDouble();
        final priceSource = pData['data_source']?.toString() ?? 'none';
        final stalePriced = (pData['stale_priced_count'] as num?)?.toInt() ?? 0;
        final sourceSummary = switch (priceSource) {
          'kite' when stalePriced > 0 => 'Zerodha live + snapshot prices',
          'kite' => 'Live prices from Zerodha',
          'mixed' => 'Prices from Zerodha + Yahoo',
          'yfinance' when stalePriced > 0 => 'Yahoo + Zerodha snapshot prices',
          'yfinance' => 'Prices from Yahoo',
          _ when stalePriced > 0 => 'Using Zerodha snapshot prices',
          _ => 'Prices currently unavailable',
        };

        return ListView(
          padding: EdgeInsets.zero,
          children: [
            // ── KPI GRID ──
            KpiGrid(
              cells: [
                Kpi('INVESTED', formatINR(totalInvested), '', c.t1),
                Kpi('CURRENT VALUE', formatINR(totalValue), '', c.t1),
                Kpi(
                  'TOTAL P&L',
                  formatSignedINR(totalPnl),
                  formatPct(totalPnlPct),
                  context.pnlColor(totalPnl),
                ),
                Kpi(
                  'RETURN',
                  formatPct(totalPnlPct),
                  'absolute',
                  context.pnlColor(totalPnlPct),
                ),
                Kpi(
                  'XIRR',
                  formatXirr(totalXirr),
                  totalXirr == null
                      ? 'no trade history'
                      : 'annualised · ${xirrCovered.toStringAsFixed(0)}% of book',
                  totalXirr == null ? c.t3 : context.pnlColor(totalXirr),
                ),
              ],
            ),
            const SizedBox(height: 12),

            // ── DENSE HOLDINGS TABLE ──
            DenseCard(
              clip: true,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  denseTableHeader(
                    context,
                    icon: LucideIcons.trendingUp,
                    accent: c.up,
                    title: 'Equity Holdings',
                    subtitle: '${holdings.length} stocks · $sourceSummary',
                    trailing: _headerActions(context, holdings),
                  ),
                  denseColumnHeader(context, _cols, leadingWidth: _gutter),
                  if (holdings.isEmpty)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 34),
                      child: Column(
                        children: [
                          Icon(LucideIcons.trendingUp, size: 24, color: c.t3),
                          const SizedBox(height: 10),
                          Text(
                            'No stocks yet',
                            style: AppTextStyles.heading3(c.t1),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            'Add a stock or connect Zerodha Kite to import holdings',
                            style: AppTextStyles.bodySmall(c.t3),
                          ),
                        ],
                      ),
                    )
                  else
                    ...holdings.asMap().entries.map(
                      (e) => _row(context, e.value, e.key.isOdd),
                    ),
                  // Totals footer
                  _footer(
                    context,
                    holdings.length,
                    totalInvested,
                    totalValue,
                    totalPnl,
                    totalPnlPct,
                    totalXirr,
                  ),
                ],
              ),
            ),
            // Realised P&L on what has already been sold. It sits below the
            // holdings deliberately: the open book is the decision, the closed
            // book is the record. They are never summed — one is a valuation,
            // the other is settled cash.
            const SizedBox(height: 22),
            Builder(
              builder: (context) {
                final closed = ref.watch(closedPositionsProvider);
                return ClosedPositionsSection(
                  book: closed.value ?? const ClosedBook(),
                  loading: closed.isLoading,
                  error: closed.hasError ? closed.error : null,
                  onRetry: () => ref.invalidate(closedPositionsProvider),
                );
              },
            ),
            const SizedBox(height: 36),
          ],
        );
      },
    );
  }

  /// Header actions. Below 1080px the five data actions fold into one menu:
  /// six buttons overflowed the 780px minimum content width by 29px, and
  /// hiding an action behind a labelled menu beats clipping it off-screen.
  Widget _headerActions(BuildContext context, List<Map<String, dynamic>> holdings) {
    final c = context.colors;
    void addStock() {
      final syms = holdings.map((h) => h['symbol'].toString()).toList();
      StockPickerModal.show(
        context,
        portfolioSymbols: syms,
        onStockAdded: () => ref.invalidate(portfolioProvider),
      );
    }

    final actions = <({String label, IconData icon, Color tone, VoidCallback tap, bool busy, String hint})>[
      (
        label: 'Tradebook',
        icon: LucideIcons.history,
        tone: c.gold,
        tap: _importTradebook,
        busy: _tradebookLoading,
        hint: 'Import Zerodha tradebook XLSX or CSV',
      ),
      (
        label: 'P&L',
        icon: LucideIcons.fileCheck,
        tone: c.up,
        tap: _importKitePnl,
        busy: _pnlLoading,
        hint: 'Import Kite P&L statement XLSX',
      ),
      (
        label: 'Ledger',
        icon: LucideIcons.bookOpen,
        tone: c.accent,
        tap: _importKiteLedger,
        busy: _ledgerLoading,
        hint: 'Import Kite funds ledger XLSX for TDS',
      ),
      (
        label: 'Export',
        icon: LucideIcons.download,
        tone: c.blue,
        tap: () => exportService.exportPortfolioToCsv(holdings),
        busy: false,
        hint: 'Export holdings to CSV',
      ),
      (
        label: 'Import',
        icon: LucideIcons.upload,
        tone: c.accent,
        tap: () async {
          final added = await importService.importPortfolioFromCsv();
          if (added > 0) ref.invalidate(portfolioProvider);
        },
        busy: false,
        hint: 'Import holdings from CSV',
      ),
    ];

    final add = HeaderButton(
      icon: const Icon(LucideIcons.plus, size: 13, color: Colors.white),
      text: 'Add',
      solidColor: c.up,
      onTap: addStock,
    );

    if (MediaQuery.sizeOf(context).width >= 1080) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final action in actions) ...[
            Semantics(
              button: true,
              label: action.hint,
              child: HeaderButton(
                icon: Icon(action.icon, size: 13, color: Colors.white),
                text: action.label,
                solidColor: action.tone,
                loading: action.busy,
                disabled: action.busy,
                onTap: action.tap,
              ),
            ),
            const SizedBox(width: 6),
          ],
          add,
        ],
      );
    }

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        PopupMenuButton<int>(
          tooltip: 'Import and export',
          icon: Icon(LucideIcons.ellipsis, size: 16, color: c.t2),
          padding: EdgeInsets.zero,
          onSelected: (i) => actions[i].tap(),
          itemBuilder: (_) => [
            for (var i = 0; i < actions.length; i++)
              PopupMenuItem(
                value: i,
                enabled: !actions[i].busy,
                child: Row(
                  children: [
                    Icon(actions[i].icon, size: 14, color: actions[i].tone),
                    const SizedBox(width: 10),
                    Text(actions[i].label,
                        style: AppTextStyles.bodySmall(c.t1)),
                  ],
                ),
              ),
          ],
        ),
        const SizedBox(width: 4),
        add,
      ],
    );
  }

  Widget _row(BuildContext context, Map<String, dynamic> h, bool alt) {
    final c = context.colors;
    final sym = (h['symbol'] ?? '').toString();
    final clean = sym.cleanSymbol;
    final qty = (h['shares'] ?? 0) as num;
    final avg = (h['avg_cost'] ?? 0).toDouble();
    final ltp = (h['ltp'] ?? h['current_price'] ?? 0).toDouble();
    final invested = (h['invested'] ?? qty * avg).toDouble();
    final curVal = (h['total_value'] ?? qty * ltp).toDouble();
    final pnl = (h['pnl'] ?? curVal - invested).toDouble();
    final netChg = (h['net_chg'] ?? 0).toDouble();
    final (xirr, xirrExact) = xirrOf(h);
    final dayChg = (h['day_chg'] ?? 0).toDouble();
    final signal = (h['signal'] ?? 'HOLD').toString();
    final sector = (h['sector'] ?? '').toString();
    final isExp = _expanded == sym;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        DenseRow(
          alt: alt,
          highlighted: isExp,
          leadingWidth: _gutter,
          leading: Align(
            alignment: Alignment.centerLeft,
            child: Icon(
              isExp ? LucideIcons.chevronDown : LucideIcons.chevronRight,
              size: 14,
              color: c.t4,
            ),
          ),
          onTap: () {
            setState(() => _expanded = isExp ? null : sym);
            if (!isExp) {
              _loadHistory(sym);
              _loadDeep(sym);
            }
          },
          cols: _cols,
          cells: [
            DInstrument(symbol: clean, sub: sector, up: netChg >= 0),
            denseNum(context, '$qty', c.t2),
            denseNum(context, avg.toStringAsFixed(2), c.t3),
            denseNum(context, ltp.toStringAsFixed(2), c.t1, bold: true),
            denseNum(context, formatINR(invested), c.t3),
            denseNum(context, formatINR(curVal), c.t2),
            denseNum(context, formatSignedINR(pnl), context.pnlColor(pnl)),
            denseDelta(context, netChg),
            // NET% is absolute since cost; XIRR annualises the same position from
            // its dated trades. '—' means the ledger has none for this stock.
            denseNum(
              context,
              formatXirr(xirr, exact: xirrExact),
              xirr == null ? c.t4 : context.pnlColor(xirr),
            ),
            denseNum(context, formatPct(dayChg), context.pnlColor(dayChg)),
            DSignalBadge(signal: signal),
            _advisorBadge(context, h['advisor_verdict']),
          ],
        ),
        if (isExp) _expandedDetails(c, sym, clean, h),
      ],
    );
  }

  Widget _expandedDetails(
    AppColorScheme c,
    String symbol,
    String clean,
    Map<String, dynamic> holding,
  ) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _transactionHistory(c, clean, holding),
        _expandedAnalysis(c, symbol, clean),
      ],
    );
  }

  Widget _transactionHistory(
    AppColorScheme c,
    String clean,
    Map<String, dynamic> holding,
  ) {
    final raw = _historyData?['transactions'];
    final transactions = raw is List
        ? raw
              .whereType<Map>()
              .map(Map<String, dynamic>.from)
              .toList()
              .reversed
              .toList()
        : const <Map<String, dynamic>>[];
    final buys =
        (_historyData?['buys'] as num?)?.toInt() ??
        transactions.where((row) => row['type'] == 'BUY').length;
    final sells =
        (_historyData?['sells'] as num?)?.toInt() ??
        transactions.where((row) => row['type'] == 'SELL').length;
    final basis = (holding['xirr_basis'] ?? 'none').toString();

    String xirrNote;
    if (basis == 'none') {
      xirrNote =
          'XIRR is unavailable because no dated trades are stored for this holding.';
    } else if (basis == 'partial') {
      xirrNote =
          'XIRR is approximate because the saved ledger does not cover the full holding.';
    } else if (basis == 'unsolved') {
      xirrNote =
          'The dated ledger is complete, but its cashflows did not produce a valid annualised rate.';
    } else {
      xirrNote =
          'XIRR uses this complete dated ledger and the holding’s current value.';
    }

    return Container(
      width: double.infinity,
      color: c.bg2,
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(LucideIcons.history, size: 15, color: c.gold),
              const SizedBox(width: 8),
              Text(
                'BUY & SELL HISTORY',
                style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 11),
              ),
              const SizedBox(width: 10),
              if (!_historyLoading && _historyError == null)
                Text(
                  '${transactions.length} trades · $buys buys · $sells sells',
                  style: AppTextStyles.captionXs(c.t3),
                ),
            ],
          ),
          const SizedBox(height: 5),
          Text(xirrNote, style: AppTextStyles.bodySmall(c.t3)),
          const SizedBox(height: 12),
          if (_historyLoading)
            Row(
              children: [
                SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: c.gold,
                  ),
                ),
                const SizedBox(width: 10),
                Text(
                  'Loading $clean trade history…',
                  style: AppTextStyles.bodySmall(c.t3),
                ),
              ],
            )
          else if (_historyError != null)
            Row(
              children: [
                Icon(LucideIcons.circleAlert, size: 15, color: c.dn),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    _historyError!,
                    style: AppTextStyles.bodySmall(c.dn),
                  ),
                ),
              ],
            )
          else if (transactions.isEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
              decoration: BoxDecoration(
                color: c.bg1,
                border: Border.all(color: c.bd),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Row(
                children: [
                  Icon(LucideIcons.fileClock, size: 16, color: c.t4),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'No BUY or SELL history saved for $clean. Import a Zerodha Console tradebook CSV to calculate XIRR.',
                      style: AppTextStyles.bodySmall(c.t3),
                    ),
                  ),
                ],
              ),
            )
          else
            Semantics(
              label: '$clean buy and sell transaction history',
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: SizedBox(
                  width: 880,
                  child: Column(
                    children: [
                      _historyRow(c, const {
                        'time': 'DATE / TIME',
                        'type': 'SIDE',
                        'qty': 'QTY',
                        'price': 'PRICE',
                        'amount': 'AMOUNT',
                        'exchange': 'EXCHANGE',
                        'id': 'TRADE / ORDER ID',
                      }, header: true),
                      ...transactions.map(
                        (row) => _historyRow(c, {
                          'time': (row['executed_at'] ?? row['date'] ?? '—')
                              .toString()
                              .replaceFirst('T', ' '),
                          'type': (row['type'] ?? '—').toString(),
                          'qty': (row['qty'] ?? '—').toString(),
                          'price': row['price'] is num
                              ? '₹${(row['price'] as num).toStringAsFixed(2)}'
                              : '—',
                          'amount': row['amount'] is num
                              ? formatINR((row['amount'] as num).toDouble())
                              : '—',
                          'exchange': (row['exchange'] ?? '—').toString(),
                          'id':
                              (row['trade_id']?.toString().isNotEmpty ?? false)
                              ? row['trade_id'].toString()
                              : ((row['order_id']?.toString().isNotEmpty ??
                                        false)
                                    ? row['order_id'].toString()
                                    : '—'),
                        }),
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _historyRow(
    AppColorScheme c,
    Map<String, String> values, {
    bool header = false,
  }) {
    Widget cell(String key, double width, {TextAlign align = TextAlign.left}) {
      final value = values[key] ?? '—';
      final side = key == 'type' && !header;
      final color = side
          ? (value == 'SELL' ? c.dn : c.up)
          : (header ? c.t4 : c.t2);
      return SizedBox(
        width: width,
        child: Text(
          value,
          textAlign: align,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style:
              (header
                      ? AppTextStyles.captionXs(color)
                      : AppTextStyles.mono(color))
                  .copyWith(
                    fontSize: header ? 9 : 11,
                    fontWeight: side ? FontWeight.w700 : null,
                  ),
        ),
      );
    }

    return Container(
      height: header ? 30 : 36,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: header ? c.bg3 : c.bg1,
        border: Border(
          left: BorderSide(color: c.bd),
          right: BorderSide(color: c.bd),
          top: BorderSide(color: c.bd),
          bottom: header ? BorderSide.none : BorderSide(color: c.bd),
        ),
      ),
      child: Row(
        children: [
          cell('time', 170),
          cell('type', 70),
          cell('qty', 70, align: TextAlign.right),
          cell('price', 110, align: TextAlign.right),
          cell('amount', 120, align: TextAlign.right),
          cell('exchange', 90, align: TextAlign.right),
          const SizedBox(width: 18),
          cell('id', 190),
        ],
      ),
    );
  }

  Widget _footer(
    BuildContext context,
    int count,
    double inv,
    double val,
    double pnl,
    double pnlPct,
    double? xirr,
  ) {
    final c = context.colors;
    Widget cell(int flex, Widget child, {bool right = true}) => Expanded(
      flex: flex,
      child: Align(
        alignment: right ? Alignment.centerRight : Alignment.centerLeft,
        child: child,
      ),
    );
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
      decoration: BoxDecoration(
        color: c.bg3,
        border: Border(top: BorderSide(color: c.bd)),
      ),
      child: Row(
        children: [
          const SizedBox(width: _gutter),
          cell(3, denseFootLabel(context, 'TOTAL · $count'), right: false),
          cell(1, const SizedBox()),
          cell(2, const SizedBox()),
          cell(2, const SizedBox()),
          cell(2, denseNum(context, formatINR(inv), c.t2, bold: true)),
          cell(2, denseNum(context, formatINR(val), c.t1, bold: true)),
          cell(
            2,
            denseNum(
              context,
              formatSignedINR(pnl),
              context.pnlColor(pnl),
              bold: true,
            ),
          ),
          cell(
            2,
            denseNum(
              context,
              formatPct(pnlPct),
              context.pnlColor(pnlPct),
              bold: true,
            ),
          ),
          cell(
            2,
            denseNum(
              context,
              formatXirr(xirr),
              xirr == null ? c.t3 : context.pnlColor(xirr),
              bold: true,
            ),
          ),
          cell(2, const SizedBox()),
          cell(2, const SizedBox()),
          cell(2, const SizedBox()),
        ],
      ),
    );
  }

  Widget _advisorBadge(BuildContext context, dynamic advisorData) {
    final c = context.colors;
    final data = advisorData is Map<String, dynamic> ? advisorData : null;
    final verdict = (data?['verdict'] ?? '—').toString();
    if (verdict == '—') {
      return Align(
        alignment: Alignment.centerRight,
        child: Text('—', style: AppTextStyles.mono(c.t4)),
      );
    }
    return DSignalBadge(signal: verdict);
  }

  Widget _expandedAnalysis(AppColorScheme c, String symbol, String clean) {
    if (_deepLoading) {
      return Container(
        color: c.bg1,
        padding: const EdgeInsets.all(20),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
              width: 15,
              height: 15,
              child: CircularProgressIndicator(strokeWidth: 2, color: c.accent),
            ),
            const SizedBox(width: 12),
            Text('AI analyzing $clean…', style: AppTextStyles.bodySmall(c.t3)),
          ],
        ),
      );
    }
    if (_deepData == null) {
      return Container(
        color: c.bg1,
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Text(
              'No analysis data available',
              style: AppTextStyles.bodySmall(c.t4),
            ),
            const Spacer(),
            _removeButton(clean, symbol),
          ],
        ),
      );
    }
    final cio = (_deepData!['cio_report'] ?? {}) as Map<String, dynamic>;
    final agents = (_deepData!['agents'] ?? {}) as Map<String, dynamic>;
    final decision = (cio['final_decision'] ?? 'HOLD').toString().toUpperCase();
    final f = (agents['fundamental'] ?? {}) as Map<String, dynamic>;
    final t = (agents['technical'] ?? {}) as Map<String, dynamic>;

    return Container(
      color: c.bg1,
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              DSignalBadge(signal: decision, align: Alignment.centerLeft),
              const SizedBox(width: 14),
              if (cio['conviction_score'] != null) ...[
                Text('Conviction ', style: AppTextStyles.captionXs(c.t4)),
                Text(
                  '${cio['conviction_score']}%',
                  style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 12),
                ),
                const SizedBox(width: 16),
              ],
              if (cio['target_price'] != null) ...[
                Text('Target ', style: AppTextStyles.captionXs(c.t4)),
                Text(
                  '₹${cio['target_price']}',
                  style: AppTextStyles.monoBold(c.up).copyWith(fontSize: 12),
                ),
                const SizedBox(width: 16),
              ],
              if (cio['stop_loss'] != null) ...[
                Text('Stop ', style: AppTextStyles.captionXs(c.t4)),
                Text(
                  '₹${cio['stop_loss']}',
                  style: AppTextStyles.monoBold(c.dn).copyWith(fontSize: 12),
                ),
              ],
              const Spacer(),
              _removeButton(clean, symbol),
            ],
          ),
          if (cio['rationale'] != null || cio['executive_summary'] != null) ...[
            const SizedBox(height: 10),
            Text(
              cio['rationale']?.toString() ??
                  cio['executive_summary']?.toString() ??
                  '',
              style: AppTextStyles.bodySmall(c.t2),
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
            ),
          ],
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              if (f['pe_ratio'] != null)
                _chip(c, 'P/E', f['pe_ratio'].toString()),
              if (f['roe'] != null) _chip(c, 'ROE', f['roe'].toString()),
              if (t['trend'] != null) _chip(c, 'Trend', t['trend'].toString()),
              if (t['momentum'] != null)
                _chip(c, 'Momentum', t['momentum'].toString()),
              if (t['support_level'] != null)
                _chip(c, 'Support', '₹${t['support_level']}'),
              if (t['resistance_level'] != null)
                _chip(c, 'Resistance', '₹${t['resistance_level']}'),
            ],
          ),
        ],
      ),
    );
  }

  Widget _removeButton(String clean, String symbol) => HeaderButton(
    icon: const Icon(LucideIcons.trash2, size: 13),
    text: 'Remove',
    onTap: () => _deleteStock(context, symbol, clean),
  );

  Widget _chip(AppColorScheme c, String label, String value) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
    decoration: BoxDecoration(
      color: c.bg3,
      borderRadius: BorderRadius.circular(6),
      border: Border.all(color: c.bd),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('$label ', style: AppTextStyles.captionXs(c.t4)),
        Text(
          value,
          style: AppTextStyles.captionXs(
            c.t1,
          ).copyWith(fontWeight: FontWeight.w700),
        ),
      ],
    ),
  );
}
