import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_colors.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/presentation/widgets/animated_page_wrapper.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'sip_results_view.dart';
import '../../providers/providers.dart';

/// SIP Investment Simulator — Data-Dense Dashboard style.
class SIPSimulatorScreen extends ConsumerStatefulWidget {
  const SIPSimulatorScreen({super.key});
  @override
  ConsumerState<SIPSimulatorScreen> createState() => _SIPSimulatorScreenState();
}

class _SIPSimulatorScreenState extends ConsumerState<SIPSimulatorScreen> {
  final _searchCtrl = TextEditingController();
  final _amountCtrl = TextEditingController(text: '5000');

  // Custom Entries
  final _ceDateCtrl = TextEditingController();
  final _ceAmountCtrl = TextEditingController(text: '10000');
  String _ceType = 'extra';

  List<Map<String, dynamic>> _basket = [];
  final List<Map<String, dynamic>> _customEntries = [];
  List<Map<String, dynamic>> _searchResults = [];

  String _startDate = '2020-01-01';
  int _sipDay = 1;
  double _stepUp = 0;

  bool _searching = false;
  bool _loading = false;
  bool _portfolioMode = false;
  String _error = '';
  Map<String, dynamic>? _result;

  static const _basketCols = [
    DenseCol('#', 1, numeric: false),
    DenseCol('INSTRUMENT', 5, numeric: false),
    DenseCol('TYPE', 2, numeric: false),
    DenseCol('₹ / MONTH', 3),
    DenseCol('', 1),
  ];

  @override
  void initState() {
    super.initState();
    // Default basket item
    _basket = [{
      'symbol': 'HDFCBANK.NS',
      'label': 'HDFC Bank Ltd.',
      'type': 'Stock',
      'amount': 5000,
    }];
  }

  Future<void> _search(String q) async {
    if (q.trim().length < 2) {
      setState(() => _searchResults = []);
      return;
    }
    setState(() => _searching = true);
    try {
      final res = await ref.read(apiServiceProvider).searchSIPInstruments(q);
      setState(() => _searchResults = List<Map<String, dynamic>>.from(res['results'] ?? []));
    } catch (_) {}
    setState(() => _searching = false);
  }

  void _addToBasket(Map<String, dynamic> inst) {
    if (_basket.length >= 10 || _basket.any((b) => b['symbol'] == inst['symbol'])) return;
    setState(() {
      _basket.add({
        'symbol': inst['symbol'],
        'label': inst['name'] ?? inst['symbol'],
        'type': inst['type'] ?? 'Stock',
        'amount': int.tryParse(_amountCtrl.text) ?? 5000,
      });
      _searchResults = [];
      _searchCtrl.clear();
    });
  }

  void _addCustomEntry() {
    if (_ceDateCtrl.text.isEmpty) return;
    setState(() {
      _customEntries.add({
        'date': _ceDateCtrl.text,
        'amount': int.tryParse(_ceAmountCtrl.text) ?? 0,
        'type': _ceType,
      });
      _customEntries.sort((a, b) => (a['date'] as String).compareTo(b['date'] as String));
      _ceDateCtrl.clear();
    });
  }

  Future<void> _runSim() async {
    if (_basket.isEmpty) return;
    setState(() { _loading = true; _error = ''; _result = null; _portfolioMode = false; });
    try {
      final res = await ref.read(apiServiceProvider).simulateSIP(
        symbols: _basket,
        startDate: _startDate,
        sipDay: _sipDay,
        stepUpPct: _stepUp,
        customEntries: _customEntries.isNotEmpty ? _customEntries : null,
      );
      setState(() => _result = res);
    } catch (e) {
      String errMsg = e.toString();
      // Extract friendly message from DioException
      if (e is DioException && e.response?.data != null) {
        final data = e.response!.data;
        if (data is Map && data.containsKey('detail')) {
          errMsg = data['detail'].toString();
        }
      }
      if (errMsg.contains('rate') || errMsg.contains('Rate') || errMsg.contains('429')) {
        errMsg = 'Yahoo Finance is rate-limited. Please wait 30 seconds and try again.';
      } else if (errMsg.contains('Could not fetch')) {
        errMsg = 'Could not fetch price data. Yahoo Finance may be temporarily unavailable. Try again in a minute.';
      }
      setState(() => _error = errMsg);
    }
    setState(() => _loading = false);
  }

  Future<void> _loadPortfolio() async {
    setState(() { _loading = true; _error = ''; _result = null; _portfolioMode = true; });
    try {
      final res = await ref.read(apiServiceProvider).analyzeMFPortfolio();
      setState(() => _result = res);
    } catch (e) {
      setState(() => _error = e.toString());
    }
    setState(() => _loading = false);
  }

  /// Dense field chrome: bg3 fill, hairline border, radius 8.
  InputDecoration _fieldDec(BuildContext context, {String? hint}) {
    final c = context.colors;
    return InputDecoration(
      hintText: hint,
      hintStyle: AppTextStyles.bodySmall(c.t4),
      filled: true,
      fillColor: c.bg3,
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: c.bd)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: c.bd)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: c.blue)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final monthlyTotal = _basket.fold<int>(0, (s, b) => s + (b['amount'] as int));
    final isGuest = ref.watch(isGuestProvider);

    return ListView(
      padding: const EdgeInsets.all(0),
      children: [
        // ── HEADER ──
        AnimatedListItem(
          index: 0,
          child: DenseCard(
            child: denseTableHeader(
              context,
              icon: LucideIcons.calculator,
              accent: c.blue,
              title: 'SIP Investment Simulator',
              subtitle:
                  'Stocks · ETFs · Mutual Funds · Index — up to 10 instruments · historical backtesting',
              trailing: HeaderButton(
                icon: Icon(LucideIcons.briefcase, size: 14, color: isGuest ? c.t4 : Colors.white),
                text: isGuest ? 'Sign in for Portfolio' : 'My Portfolio',
                primary: !isGuest,
                onTap: isGuest ? () {} : _loadPortfolio,
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),

        // ── MAIN GRID ──
        AnimatedListItem(
          index: 1,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Left: Search + Basket
              Expanded(
                flex: 6,
                child: Column(
                  children: [
                    _searchCard(context),
                    const SizedBox(height: 12),
                    if (_basket.isNotEmpty) _basketCard(context),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              // Right: Controls
              Expanded(flex: 4, child: _settingsCard(context, monthlyTotal)),
            ],
          ),
        ),

        if (_error.isNotEmpty) ...[
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: c.dn.withValues(alpha: 0.08),
              border: Border.all(color: c.dn.withValues(alpha: 0.22)),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(children: [
              Icon(LucideIcons.alertTriangle, size: 14, color: c.dn),
              const SizedBox(width: 8),
              Expanded(child: Text(_error, style: AppTextStyles.bodySmall(c.dn))),
            ]),
          ),
        ],

        const SizedBox(height: 12),

        // ── RESULTS ──
        if (_result != null)
          AnimatedListItem(
            index: 2,
            child: SIPResultsView(result: _result!, portfolioMode: _portfolioMode),
          ),

        const SizedBox(height: 36),
      ],
    );
  }

  // ── SEARCH CARD ──
  Widget _searchCard(BuildContext context) {
    final c = context.colors;
    return DenseCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          denseTableHeader(
            context,
            icon: LucideIcons.search,
            accent: c.blue,
            title: 'Search Instruments',
            subtitle: _searching ? 'searching…' : 'stocks · ETFs · mutual funds',
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _searchCtrl,
                        onChanged: _search,
                        style: AppTextStyles.bodySmall(c.t1),
                        decoration: _fieldDec(context, hint: 'Search stocks, ETFs, mutual funds…'),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: c.bg3,
                        border: Border.all(color: c.bd),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Row(
                        children: [
                          Text('₹', style: AppTextStyles.captionXs(c.t4)),
                          SizedBox(
                            width: 60,
                            child: TextField(
                              controller: _amountCtrl,
                              style: AppTextStyles.mono(c.t1).copyWith(fontSize: 12),
                              textAlign: TextAlign.right,
                              decoration: const InputDecoration(
                                border: InputBorder.none,
                                enabledBorder: InputBorder.none,
                                focusedBorder: InputBorder.none,
                                isDense: true,
                                contentPadding: EdgeInsets.zero,
                              ),
                            ),
                          ),
                          Text('/mo', style: AppTextStyles.captionXs(c.t4)),
                        ],
                      ),
                    ),
                  ],
                ),
                if (_searchResults.isNotEmpty)
                  Container(
                    margin: const EdgeInsets.only(top: 10),
                    constraints: const BoxConstraints(maxHeight: 250),
                    decoration: BoxDecoration(
                      color: c.bg1,
                      border: Border.all(color: c.bd),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: ListView.builder(
                      shrinkWrap: true,
                      itemCount: _searchResults.length,
                      itemBuilder: (ctx, i) {
                        final inst = _searchResults[i];
                        final isAdded = _basket.any((b) => b['symbol'] == inst['symbol']);
                        return Material(
                          color: Colors.transparent,
                          child: InkWell(
                            onTap: () => _addToBasket(inst),
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                              decoration: BoxDecoration(
                                border: Border(bottom: BorderSide(color: c.bd.withValues(alpha: 0.6))),
                              ),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(inst['name'] ?? inst['symbol'],
                                            style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12),
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis),
                                        Text('${inst['symbol']} · ${inst['exchange'] ?? ''}',
                                            style: AppTextStyles.captionXs(c.t4)),
                                      ],
                                    ),
                                  ),
                                  AppBadge(text: inst['type'] ?? 'Stock', variant: BadgeVariant.blue),
                                  const SizedBox(width: 12),
                                  Icon(isAdded ? LucideIcons.checkCircle2 : LucideIcons.plusCircle,
                                      size: 15, color: isAdded ? c.up : c.blue),
                                ],
                              ),
                            ),
                          ),
                        );
                      },
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── BASKET CARD ──
  Widget _basketCard(BuildContext context) {
    final c = context.colors;
    return DenseCard(
      clip: true,
      child: Column(
        children: [
          denseTableHeader(
            context,
            icon: LucideIcons.layers,
            accent: c.up,
            title: 'Investment Basket',
            subtitle: '${_basket.length}/10 instruments',
            trailing: AppBadge(text: '${_basket.length}/10', variant: BadgeVariant.blue),
          ),
          denseColumnHeader(context, _basketCols),
          ..._basket.asMap().entries.map((e) {
            final i = e.key;
            final b = e.value;
            return DenseRow(
              alt: i.isOdd,
              cols: _basketCols,
              cells: [
                Text('${i + 1}', style: AppTextStyles.monoXs(c.t4)),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(b['label'],
                        style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis),
                    Text(
                        (b['symbol'] as String)
                            .replaceAll(RegExp(r'\.(NS|BO)$', caseSensitive: false), ''),
                        style: AppTextStyles.captionXs(c.t4)),
                  ],
                ),
                Align(
                  alignment: Alignment.centerLeft,
                  child: AppBadge(text: b['type'], variant: BadgeVariant.blue),
                ),
                Align(
                  alignment: Alignment.centerRight,
                  child: SizedBox(
                    width: 80,
                    child: TextField(
                      controller: TextEditingController(text: b['amount'].toString()),
                      onChanged: (v) => setState(() => b['amount'] = int.tryParse(v) ?? 0),
                      style: AppTextStyles.mono(c.t1).copyWith(fontSize: 12),
                      textAlign: TextAlign.right,
                      decoration: _fieldDec(context),
                    ),
                  ),
                ),
                Align(
                  alignment: Alignment.centerRight,
                  child: InkWell(
                    onTap: () => setState(() => _basket.removeAt(i)),
                    child: Icon(LucideIcons.trash2, size: 14, color: c.dn),
                  ),
                ),
              ],
            );
          }),
        ],
      ),
    );
  }

  // ── SETTINGS CARD ──
  Widget _settingsCard(BuildContext context, int monthlyTotal) {
    final c = context.colors;
    return DenseCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          denseTableHeader(
            context,
            icon: LucideIcons.settings,
            accent: c.accent,
            title: 'Simulation Settings',
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('SIP START DATE', style: AppTextStyles.labelXs(c.t3)),
                const SizedBox(height: 4),
                TextField(
                  controller: TextEditingController(text: _startDate),
                  onChanged: (v) => _startDate = v,
                  style: AppTextStyles.mono(c.t1).copyWith(fontSize: 12),
                  decoration: _fieldDec(context),
                ),
                const SizedBox(height: 12),

                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('SIP DAY', style: AppTextStyles.labelXs(c.t3)),
                          const SizedBox(height: 4),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10),
                            decoration: BoxDecoration(
                              color: c.bg3,
                              border: Border.all(color: c.bd),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: DropdownButtonHideUnderline(
                              child: DropdownButton<int>(
                                value: _sipDay,
                                isExpanded: true,
                                isDense: true,
                                dropdownColor: c.bg2,
                                style: AppTextStyles.bodySmall(c.t1),
                                padding: const EdgeInsets.symmetric(vertical: 10),
                                items: List.generate(
                                    28,
                                    (i) => DropdownMenuItem(
                                        value: i + 1,
                                        child: Text(
                                            '${i + 1}${i == 0 ? "st" : i == 1 ? "nd" : i == 2 ? "rd" : "th"} of month'))),
                                onChanged: (v) => setState(() => _sipDay = v ?? 1),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('STEP-UP %/YR', style: AppTextStyles.labelXs(c.t3)),
                          const SizedBox(height: 4),
                          TextField(
                            controller: TextEditingController(text: _stepUp.toString()),
                            onChanged: (v) => _stepUp = double.tryParse(v) ?? 0,
                            style: AppTextStyles.mono(c.t1).copyWith(fontSize: 12),
                            decoration: _fieldDec(context),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),

                // Summary box
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: c.bg3,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: c.bd),
                  ),
                  child: Column(
                    children: [
                      _summaryRow(c, 'INSTRUMENTS', '${_basket.length}', c.t1),
                      _summaryRow(c, 'MONTHLY SIP', formatINR(monthlyTotal), c.blue),
                      if (_stepUp > 0) _summaryRow(c, 'ANNUAL STEP-UP', '+${_stepUp.toInt()}%', c.up),
                      _summaryRow(
                          c,
                          'SIP DAY',
                          '$_sipDay${_sipDay == 1 ? "st" : _sipDay == 2 ? "nd" : _sipDay == 3 ? "rd" : "th"}',
                          c.t1),
                      if (_customEntries.isNotEmpty)
                        _summaryRow(c, 'CUSTOM ENTRIES', '${_customEntries.length}', c.gold),
                    ],
                  ),
                ),
                const SizedBox(height: 14),

                // Custom Entries Section
                Text('CUSTOM / EXTRA SIP', style: AppTextStyles.labelXs(c.t3)),
                const SizedBox(height: 6),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _ceDateCtrl,
                        style: AppTextStyles.mono(c.t1).copyWith(fontSize: 12),
                        decoration: _fieldDec(context, hint: 'yyyy-mm-dd'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: TextField(
                        controller: _ceAmountCtrl,
                        style: AppTextStyles.mono(c.t1).copyWith(fontSize: 12),
                        textAlign: TextAlign.right,
                        decoration: _fieldDec(context),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10),
                        decoration: BoxDecoration(
                          color: c.bg3,
                          border: Border.all(color: c.bd),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: DropdownButtonHideUnderline(
                          child: DropdownButton<String>(
                            value: _ceType,
                            isExpanded: true,
                            isDense: true,
                            dropdownColor: c.bg2,
                            style: AppTextStyles.bodySmall(c.t1),
                            padding: const EdgeInsets.symmetric(vertical: 9),
                            items: const [
                              DropdownMenuItem(value: 'extra', child: Text('Extra Lump-sum')),
                              DropdownMenuItem(value: 'override', child: Text('Override Month')),
                              DropdownMenuItem(value: 'skip', child: Text('Skip Month (₹0)')),
                            ],
                            onChanged: (v) => setState(() => _ceType = v ?? 'extra'),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    HeaderButton(
                      text: 'Add',
                      solidColor: c.blue,
                      onTap: _addCustomEntry,
                    ),
                  ],
                ),
                if (_customEntries.isNotEmpty)
                  Container(
                    margin: const EdgeInsets.only(top: 10),
                    constraints: const BoxConstraints(maxHeight: 140),
                    child: ListView.builder(
                      shrinkWrap: true,
                      itemCount: _customEntries.length,
                      itemBuilder: (ctx, i) {
                        final ce = _customEntries[i];
                        final isExtra = ce['type'] == 'extra';
                        final isSkip = ce['type'] == 'skip';
                        return Container(
                          margin: const EdgeInsets.only(bottom: 4),
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: c.bg3,
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: c.bd),
                          ),
                          child: Row(
                            children: [
                              Text(ce['date'], style: AppTextStyles.monoXs(c.t2)),
                              const SizedBox(width: 8),
                              AppBadge(
                                  text: ce['type'].toString().toUpperCase(),
                                  variant: isExtra
                                      ? BadgeVariant.up
                                      : isSkip
                                          ? BadgeVariant.dn
                                          : BadgeVariant.gold),
                              const Spacer(),
                              Text(formatINR(ce['amount'] as num),
                                  style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 12)),
                              const SizedBox(width: 8),
                              InkWell(
                                  onTap: () => setState(() => _customEntries.removeAt(i)),
                                  child: Icon(LucideIcons.x, size: 12, color: c.dn)),
                            ],
                          ),
                        );
                      },
                    ),
                  ),

                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  child: HeaderButton(
                    icon: const Icon(LucideIcons.play, size: 14, color: Colors.white),
                    text: _loading ? 'Simulating…' : 'Run Simulation',
                    primary: true,
                    loading: _loading,
                    onTap: _runSim,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _summaryRow(AppColorScheme c, String label, String value, Color valueColor) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 5),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: AppTextStyles.labelXs(c.t3)),
          Text(value, style: AppTextStyles.monoBold(valueColor).copyWith(fontSize: 12)),
        ],
      ),
    );
  }
}
