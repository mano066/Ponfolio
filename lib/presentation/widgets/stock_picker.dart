import 'dart:async';
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/services/api_service.dart';

class StockPickerModal extends StatefulWidget {
  final List<String> portfolioSymbols;
  final VoidCallback onStockAdded;

  const StockPickerModal({
    super.key,
    required this.portfolioSymbols,
    required this.onStockAdded,
  });

  static Future<void> show(BuildContext context, {
    required List<String> portfolioSymbols,
    required VoidCallback onStockAdded,
  }) {
    return showDialog(
      context: context,
      barrierColor: Colors.black54,
      builder: (_) => StockPickerModal(
        portfolioSymbols: portfolioSymbols,
        onStockAdded: onStockAdded,
      ),
    );
  }

  @override
  State<StockPickerModal> createState() => _StockPickerModalState();
}

class _StockPickerModalState extends State<StockPickerModal> {
  final _searchCtrl = TextEditingController();
  final _qtyCtrl = <String, TextEditingController>{};
  List<Map<String, dynamic>> _results = [];
  bool _loading = false;
  bool _hasSearched = false;
  String _lastQuery = '';
  Timer? _debounce;

  void _onSearchChanged(String query) {
    _debounce?.cancel();
    if (query.trim().length < 2) {
      setState(() {
        _results = [];
        _hasSearched = false;
        _lastQuery = query;
      });
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 400), () {
      _search(query.trim());
    });
  }

  Future<void> _search(String query) async {
    if (query == _lastQuery && _hasSearched) return;
    setState(() { _loading = true; _lastQuery = query; });
    try {
      final results = await ApiService().searchStocks(query);
      if (mounted && query == _searchCtrl.text.trim()) {
        setState(() {
          _results = results;
          _loading = false;
          _hasSearched = true;
        });
      }
    } catch (_) {
      if (mounted) setState(() { _loading = false; _hasSearched = true; });
    }
  }

  Future<void> _addStock(String symbol) async {
    final qtyText = _qtyCtrl[symbol]?.text ?? '1';
    final qty = int.tryParse(qtyText) ?? 0;
    if (qty <= 0) return;
    try {
      await ApiService().addStock(symbol, qty);
      widget.onStockAdded();
      if (mounted) Navigator.of(context).pop();
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Center(child: ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
        child: Container(
          width: 580, constraints: const BoxConstraints(maxHeight: 650),
          decoration: BoxDecoration(
            color: c.bg1.withValues(alpha: 0.95),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: c.bd2),
            boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.4), blurRadius: 40)],
          ),
          child: Material(color: Colors.transparent, child: Column(children: [
            // Search header
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.bd))),
              child: Column(children: [
                Row(children: [
                  Container(
                    width: 32, height: 32,
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(colors: [Color(0xFF3B82F6), Color(0xFF8B5CF6)]),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Icon(LucideIcons.search, size: 16, color: Colors.white),
                  ),
                  const SizedBox(width: 12),
                  Expanded(child: Text('Search All NSE & BSE Stocks', style: AppTextStyles.bodyBold(c.t1))),
                  InkWell(
                    onTap: () => Navigator.of(context).pop(),
                    borderRadius: BorderRadius.circular(20),
                    child: Container(
                      width: 32, height: 32,
                      decoration: BoxDecoration(shape: BoxShape.circle, color: c.bgH),
                      child: Icon(LucideIcons.x, size: 16, color: c.t4),
                    ),
                  ),
                ]),
                const SizedBox(height: 12),
                Container(
                  decoration: BoxDecoration(
                    color: c.bg3,
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: c.bd),
                  ),
                  child: Row(children: [
                    const SizedBox(width: 12),
                    Icon(LucideIcons.search, size: 16, color: c.t4),
                    const SizedBox(width: 8),
                    Expanded(child: TextField(
                      controller: _searchCtrl, autofocus: true,
                      style: AppTextStyles.body(c.t1),
                      decoration: InputDecoration(
                        hintText: 'Search by name or symbol (e.g., TATA, BANK, ADANI)...',
                        hintStyle: AppTextStyles.body(c.t4),
                        border: InputBorder.none, isDense: true,
                        contentPadding: const EdgeInsets.symmetric(vertical: 10),
                      ),
                      onChanged: _onSearchChanged,
                    )),
                    if (_loading) Padding(
                      padding: const EdgeInsets.only(right: 12),
                      child: SizedBox(width: 16, height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2, color: c.blue)),
                    ),
                  ]),
                ),
              ]),
            ),
            // Results
            Expanded(child: _buildBody(c)),
          ])),
        ),
      ),
    ));
  }

  Widget _buildBody(dynamic c) {
    // Empty state — no search yet
    if (!_hasSearched && _searchCtrl.text.trim().length < 2) {
      return Center(child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(LucideIcons.search, size: 48, color: c.t4.withValues(alpha: 0.3)),
          const SizedBox(height: 16),
          Text('Search All Indian Stocks', style: AppTextStyles.bodyBold(c.t2)),
          const SizedBox(height: 4),
          Text('Type at least 2 characters to search across all NSE & BSE listed stocks',
            style: AppTextStyles.bodySmall(c.t4), textAlign: TextAlign.center),
        ]),
      ));
    }

    // Loading
    if (_loading && _results.isEmpty) {
      return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
        SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2, color: c.blue)),
        const SizedBox(height: 12),
        Text('Searching NSE & BSE...', style: AppTextStyles.bodySmall(c.t3)),
      ]));
    }

    // No results
    if (_hasSearched && _results.isEmpty) {
      return Center(child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(LucideIcons.searchX, size: 40, color: c.t4.withValues(alpha: 0.3)),
          const SizedBox(height: 12),
          Text('No stocks found for "$_lastQuery"', style: AppTextStyles.bodyBold(c.t3)),
          const SizedBox(height: 4),
          Text('Try a different search term', style: AppTextStyles.bodySmall(c.t4)),
        ]),
      ));
    }

    // Results count header + list
    return Column(children: [
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(color: c.bg3.withValues(alpha: 0.5)),
        child: Row(children: [
          Text('${_results.length} stocks found', style: AppTextStyles.captionXs(c.t3).copyWith(fontWeight: FontWeight.w600)),
          const Spacer(),
          Text('NSE & BSE', style: AppTextStyles.captionXs(c.t4)),
        ]),
      ),
      Expanded(child: ListView.builder(
        itemCount: _results.length,
        itemBuilder: (_, i) {
          final s = _results[i];
          final sym = s['symbol']?.toString() ?? '';
          final name = s['name']?.toString() ?? s['company']?.toString() ?? sym;
          final sector = s['sector']?.toString() ?? s['exchange']?.toString() ?? '';
          final exchange = s['exchange']?.toString() ?? '';
          final clean = sym.replaceAll(RegExp(r'\.(NS|BO)$', caseSensitive: false), '');
          final isOwned = widget.portfolioSymbols.contains(sym);
          _qtyCtrl.putIfAbsent(sym, () => TextEditingController(text: '1'));

          return Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.bd.withValues(alpha: 0.3)))),
            child: Row(children: [
              Container(width: 5, height: 36, decoration: BoxDecoration(
                color: isOwned ? c.up : c.bg3, borderRadius: BorderRadius.circular(3))),
              const SizedBox(width: 12),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Text(clean, style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 14)),
                  const SizedBox(width: 8),
                  if (exchange.isNotEmpty) Container(
                    padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                    decoration: BoxDecoration(
                      color: exchange.contains('NSE') ? const Color(0x1A3B82F6) : const Color(0x1AF59E0B),
                      border: Border.all(color: exchange.contains('NSE') ? const Color(0x333B82F6) : const Color(0x33F59E0B)),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(exchange, style: AppTextStyles.captionXs(
                      exchange.contains('NSE') ? const Color(0xFF3B82F6) : const Color(0xFFF59E0B),
                    ).copyWith(fontWeight: FontWeight.w700, fontSize: 9)),
                  ),
                  if (sector.isNotEmpty && sector != exchange) ...[
                    const SizedBox(width: 6),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                      decoration: BoxDecoration(color: c.bg3, border: Border.all(color: c.bd), borderRadius: BorderRadius.circular(8)),
                      child: Text(sector, style: AppTextStyles.captionXs(c.t3).copyWith(fontWeight: FontWeight.w600, fontSize: 9)),
                    ),
                  ],
                ]),
                Text(name, style: AppTextStyles.captionXs(c.t4), maxLines: 1, overflow: TextOverflow.ellipsis),
              ])),
              if (isOwned) Padding(
                padding: const EdgeInsets.only(right: 8),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(color: c.upBg, borderRadius: BorderRadius.circular(10)),
                  child: Text('✓ Owned', style: AppTextStyles.captionXs(c.up).copyWith(fontWeight: FontWeight.w700, fontSize: 10)),
                ),
              ),
              SizedBox(width: 56, child: TextField(
                controller: _qtyCtrl[sym],
                keyboardType: TextInputType.number,
                textAlign: TextAlign.center,
                style: AppTextStyles.mono(c.t1).copyWith(fontSize: 12),
                decoration: InputDecoration(
                  hintText: 'Qty', isDense: true,
                  contentPadding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
                ),
              )),
              const SizedBox(width: 8),
              Material(
                color: Colors.transparent,
                child: InkWell(
                  onTap: () => _addStock(sym),
                  borderRadius: BorderRadius.circular(8),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(colors: [Color(0xFF16A34A), Color(0xFF059669)]),
                      borderRadius: BorderRadius.circular(8)),
                    child: Text('+ Add', style: AppTextStyles.captionXs(Colors.white).copyWith(fontWeight: FontWeight.w700)),
                  ),
                ),
              ),
            ]),
          );
        },
      )),
    ]);
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchCtrl.dispose();
    for (final c in _qtyCtrl.values) {
      c.dispose();
    }
    super.dispose();
  }
}
