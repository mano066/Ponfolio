import 'dart:async';
import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_colors.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/presentation/widgets/animated_page_wrapper.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/services/api_service.dart';

const _presets = ['Nifty 50 Index','Nifty Next 50 Index','Large Cap','Flexi Cap','Mid Cap','Small Cap','ELSS Tax Saver'];
const _maxFunds = 25;

class MFScreenerScreen extends StatefulWidget {
  const MFScreenerScreen({super.key});
  @override
  State<MFScreenerScreen> createState() => _MFScreenerScreenState();
}

class _MFScreenerScreenState extends State<MFScreenerScreen> {
  final _searchCtrl = TextEditingController();
  List<Map<String, dynamic>> _searchResults = [];
  final List<Map<String, dynamic>> _basket = [];
  bool _searching = false;
  Timer? _debounce;
  String _step = 'build'; // build | analyzing | results
  Map<String, dynamic>? _results;
  double _progress = 0;
  int _progressTotal = 0;
  String _progressMsg = '';
  Timer? _pollTimer;
  int? _expandedCode;

  // Full research-table columns (label, width, right-aligned?) — the table
  // scrolls horizontally; '—' in a cell is a DATA GAP, never an estimate.
  static const _cols = <(String, double, bool)>[
    ('RANK', 42, false),
    ('FUND', 200, false),
    ('CATEGORY ✓', 130, false),
    ('PLAN', 96, false),
    ('BENCHMARK', 130, false),
    ('BM 3Y', 60, true),
    ('FUND 3Y', 62, true),
    ('ROLL AVG', 64, true),
    ('ROLL MIN', 64, true),
    ('% POS', 56, true),
    ('% ≥20%', 58, true),
    ('SHARPE', 56, true),
    ('SORTINO', 60, true),
    ('ALPHA', 56, true),
    ('MAX DD', 62, true),
    ('TER', 52, true),
    ('MANAGERS', 120, false),
    ('AUM', 84, true),
    ('INFLOWS', 62, true),
    ('P/E · P/B', 68, true),
    ('REL P/E', 58, true),
    ('VALUATION', 80, false),
    ('OVERLAP', 62, true),
    ('UNDERPERF', 74, true),
    ('SCORE', 52, true),
    ('DECISION', 104, false),
  ];

  void _onSearch(String q) {
    _debounce?.cancel();
    if (q.length < 2) { setState(() => _searchResults = []); return; }
    _debounce = Timer(const Duration(milliseconds: 400), () async {
      setState(() => _searching = true);
      try {
        final data = await ApiService().searchMFAnalysis(q);
        setState(() => _searchResults = List<Map<String, dynamic>>.from(data['funds'] ?? []));
      } catch (_) {}
      setState(() => _searching = false);
    });
  }

  void _addToBasket(Map<String, dynamic> f) {
    if (_basket.length >= _maxFunds) return;
    final code = f['scheme_code'];
    if (_basket.any((b) => b['scheme_code'] == code)) return;
    setState(() => _basket.add(f));
  }

  void _removeFromBasket(int code) {
    setState(() => _basket.removeWhere((b) => b['scheme_code'] == code));
  }

  Future<void> _addFromCategory(String cat) async {
    setState(() => _searching = true);
    try {
      final data = await ApiService().searchMFAnalysis(cat);
      final funds = List<Map<String, dynamic>>.from(data['funds'] ?? []);
      final existing = _basket.map((b) => b['scheme_code']).toSet();
      final toAdd = funds.where((f) => !existing.contains(f['scheme_code'])).toList();
      setState(() {
        _basket.addAll(toAdd.take(_maxFunds - _basket.length));
        _searchResults = [];
        _searchCtrl.clear();
      });
    } catch (_) {}
    setState(() => _searching = false);
  }

  Future<void> _analyze() async {
    if (_basket.isEmpty) return;
    setState(() { _step = 'analyzing'; _results = null; _progress = 0; _expandedCode = null; });
    try {
      await ApiService().startMFAnalysis(
        category: 'Custom Comparison',
        schemeCodes: _basket.map((b) => b['scheme_code'] as int).toList(),
      );
      _startPolling();
    } catch (_) {
      setState(() => _step = 'build');
    }
  }

  void _startPolling() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(milliseconds: 1500), (_) async {
      try {
        final d = await ApiService().getMFAnalysisStatus();
        setState(() {
          _progress = (d['progress'] ?? 0).toDouble();
          _progressTotal = (d['total'] ?? 0) as int;
          _progressMsg = (d['msg'] ?? '').toString();
        });
        if (d['running'] != true) {
          _pollTimer?.cancel();
          if (d['results'] != null) {
            setState(() { _results = d['results'] as Map<String, dynamic>; _step = 'results'; });
          } else {
            setState(() => _step = 'build');
          }
        }
      } catch (_) {}
    });
  }

  bool _isInBasket(int code) => _basket.any((b) => b['scheme_code'] == code);

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return ListView(padding: EdgeInsets.zero, children: [
      // ── HEADER ──
      AnimatedListItem(
        index: 0,
        child: DenseCard(
          child: denseTableHeader(context,
              icon: LucideIcons.microscope,
              accent: c.accent,
              title: 'MF Screener & Comparator',
              subtitle:
                  'Direct-Growth only · Weighted 0-100 research score · Rolling consistency, SIP XIRR, drawdown & benchmark analysis · DATA GAPs flagged, never estimated'),
        ),
      ),
      const SizedBox(height: 12),

      // ── BUILD / RESULTS ──
      if (_step == 'build' || _step == 'results') ...[
        AnimatedListItem(
          index: 1,
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            // Left: Search
            Expanded(flex: 5, child: DenseCard(
              padding: const EdgeInsets.all(14),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('SEARCH & ADD FUNDS', style: AppTextStyles.labelXs(c.t3)),
                const SizedBox(height: 10),
                TextField(controller: _searchCtrl, onChanged: _onSearch,
                  style: AppTextStyles.body(c.t1),
                  decoration: InputDecoration(
                    isDense: true,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    hintText: 'Search by fund name, AMC, or category…',
                    hintStyle: AppTextStyles.bodySmall(c.t4),
                    prefixIcon: Icon(LucideIcons.search, size: 15, color: c.t4),
                    suffixIcon: _searching ? Padding(padding: const EdgeInsets.all(12),
                      child: SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: c.blue))) : null,
                    filled: true,
                    fillColor: c.bg3,
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: c.bd)),
                    enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: c.bd)),
                    focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: c.accent)),
                  )),
                const SizedBox(height: 10),
                // Presets
                Wrap(spacing: 6, runSpacing: 6, children: _presets.map((p) =>
                  Material(color: Colors.transparent, child: InkWell(
                    borderRadius: BorderRadius.circular(6), onTap: () => _addFromCategory(p),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(color: c.bg3, border: Border.all(color: c.bd), borderRadius: BorderRadius.circular(6)),
                      child: Text('+ $p', style: AppTextStyles.captionXs(c.t2)),
                    ),
                  ))).toList()),
                const SizedBox(height: 10),
                // Results list
                if (_searchResults.isNotEmpty) Container(
                  constraints: const BoxConstraints(maxHeight: 300),
                  clipBehavior: Clip.antiAlias,
                  decoration: BoxDecoration(border: Border.all(color: c.bd), borderRadius: BorderRadius.circular(8)),
                  child: ListView.builder(
                    shrinkWrap: true, itemCount: _searchResults.length,
                    itemBuilder: (_, i) {
                      final f = _searchResults[i];
                      final added = _isInBasket(f['scheme_code'] as int);
                      return Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.bd.withValues(alpha: 0.4)))),
                        child: Row(children: [
                          Material(
                            color: added ? c.upBg : c.accentBg, shape: const CircleBorder(),
                            child: InkWell(
                              customBorder: const CircleBorder(),
                              onTap: added ? null : () => _addToBasket(f),
                              child: SizedBox(width: 26, height: 26, child: Center(
                                child: Icon(added ? LucideIcons.check : LucideIcons.plus,
                                    size: 13, color: added ? c.up : c.accent))),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(f['scheme_name'] ?? '', style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12), overflow: TextOverflow.ellipsis),
                            Text('${f['amc'] ?? ''} · Code: ${f['scheme_code']}', style: AppTextStyles.captionXs(c.t4)),
                          ])),
                        ]),
                      );
                    },
                  ),
                ),
              ]),
            )),
            const SizedBox(width: 12),
            // Right: Basket
            Expanded(flex: 3, child: DenseCard(
              padding: const EdgeInsets.all(14),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Text('COMPARISON BASKET', style: AppTextStyles.labelXs(c.t3)),
                  const Spacer(),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(
                      color: (_basket.length >= _maxFunds ? c.dn : c.blue).withValues(alpha: 0.10),
                      border: Border.all(color: (_basket.length >= _maxFunds ? c.dn : c.blue).withValues(alpha: 0.22)),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text('${_basket.length}/$_maxFunds',
                        style: AppTextStyles.labelXs(_basket.length >= _maxFunds ? c.dn : c.blue)),
                  ),
                ]),
                const SizedBox(height: 10),
                if (_basket.isEmpty)
                  Padding(padding: const EdgeInsets.symmetric(vertical: 40),
                    child: Center(child: Text('Search for funds and click + to add', style: AppTextStyles.bodySmall(c.t4), textAlign: TextAlign.center)))
                else
                  ...List.generate(_basket.length, (i) {
                    final f = _basket[i];
                    return Container(
                      margin: const EdgeInsets.only(bottom: 4),
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                      decoration: BoxDecoration(
                          color: c.bg3,
                          border: Border.all(color: c.bd.withValues(alpha: 0.6)),
                          borderRadius: BorderRadius.circular(6)),
                      child: Row(children: [
                        Text('${i + 1}', style: AppTextStyles.monoXs(c.t4)),
                        const SizedBox(width: 8),
                        Expanded(child: Text((f['scheme_name'] ?? '').toString(), style: AppTextStyles.captionXs(c.t1), overflow: TextOverflow.ellipsis)),
                        Material(color: Colors.transparent, child: InkWell(
                          onTap: () => _removeFromBasket(f['scheme_code'] as int),
                          child: Padding(padding: const EdgeInsets.all(2), child: Icon(LucideIcons.x, size: 12, color: c.dn)),
                        )),
                      ]),
                    );
                  }),
                const SizedBox(height: 10),
                Row(children: [
                  if (_basket.isNotEmpty) Material(color: Colors.transparent, child: InkWell(
                    onTap: () => setState(() => _basket.clear()),
                    child: Text('Clear All', style: AppTextStyles.captionXs(c.t4)),
                  )),
                  const Spacer(),
                  HeaderButton(
                    icon: const Icon(LucideIcons.microscope, size: 14, color: Colors.white),
                    text: 'Analyze ${_basket.length} Fund${_basket.length != 1 ? "s" : ""}',
                    solidColor: _basket.isNotEmpty ? c.accent : null,
                    disabled: _basket.isEmpty, onTap: _analyze,
                  ),
                ]),
              ]),
            )),
          ]),
        ),
      ],

      // ── ANALYZING PROGRESS ──
      if (_step == 'analyzing') ...[
        AnimatedListItem(
          index: 1,
          child: DenseCard(
            padding: const EdgeInsets.all(16),
            child: Column(children: [
              Row(children: [
                Icon(LucideIcons.microscope, size: 18, color: c.accent),
                const SizedBox(width: 12),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Analyzing ${_basket.length} funds…', style: AppTextStyles.bodyBold(c.t1)),
                  Text(_progressMsg.isNotEmpty ? _progressMsg : 'Starting…', style: AppTextStyles.captionXs(c.t3)),
                ])),
                Text('${_progress.toInt()}/$_progressTotal',
                    style: AppTextStyles.mono(c.t3).copyWith(fontSize: 12)),
              ]),
              const SizedBox(height: 12),
              ClipRRect(
                borderRadius: BorderRadius.circular(3),
                child: LinearProgressIndicator(
                  value: _progressTotal > 0 ? _progress / _progressTotal : 0.05,
                  minHeight: 6, backgroundColor: c.bg3,
                  valueColor: AlwaysStoppedAnimation(c.accent),
                ),
              ),
            ]),
          ),
        ),
      ],

      // ── RESULTS ──
      if (_step == 'results' && _results != null) ...[
        const SizedBox(height: 12),
        _buildResultsView(c),
        const SizedBox(height: 12),
        Material(color: Colors.transparent, child: InkWell(
          onTap: () => setState(() { _step = 'build'; _results = null; }),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(LucideIcons.arrowLeft, size: 13, color: c.blue),
            const SizedBox(width: 4),
            Text('Back to fund builder', style: AppTextStyles.bodySmall(c.blue)),
          ]),
        )),
      ],
      const SizedBox(height: 36),
    ]);
  }

  // ── Formatting helpers: null = DATA GAP, shown as '—', never estimated ──
  static String _f(dynamic v) => v == null ? '—' : v.toString();
  static String _pct(dynamic v) => v == null ? '—' : '$v%';
  static String _shortName(dynamic name) => (name ?? '')
      .toString()
      .replaceAll(RegExp(r' - Direct Plan.*| - Growth.*', caseSensitive: false), '');

  Widget _buildResultsView(AppColorScheme c) {
    final res = List<Map<String, dynamic>>.from(_results!['results'] ?? []);
    final counts = Map<String, dynamic>.from(_results!['decision_counts'] ?? {});
    final rec = Map<String, dynamic>.from(_results!['recommendation'] ?? {});
    final bic = Map<String, dynamic>.from(_results!['best_in_class'] ?? {});
    final gaps = List<String>.from(_results!['data_gaps'] ?? []);
    int cnt(String k) => (counts[k] ?? 0) as int;

    return Column(children: [
      // ── KPI GRID: one cell per decision label ──
      KpiGrid(perRow: 6, cells: [
        Kpi('ANALYZED', '${_results!['total_analyzed'] ?? res.length}', 'funds', c.blue),
        Kpi('ENTER NOW', '${cnt('ENTER NOW')}', 'dip entry', c.up),
        Kpi('GRADUAL', '${cnt('ENTER GRADUALLY')}', 'phase in', c.accent),
        Kpi('SIP ONLY', '${cnt('SIP ONLY')}', 'no lump sum', c.t1),
        Kpi('WAIT', '${cnt('WAIT')}', 'watchlist', c.gold),
        Kpi('AVOID', '${cnt('AVOID FRESH ENTRY')}', 'fresh entry', c.dn),
      ]),

      // ── RESEARCH VERDICT: primary + alternative + best-in-class ──
      if (rec['primary'] != null) ...[
        const SizedBox(height: 12),
        DenseCard(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          denseTableHeader(context,
              icon: LucideIcons.award,
              accent: c.gold,
              title: 'Research Verdict',
              subtitle: 'Data as of ${_results!['as_of'] ?? '—'} · ${_results!['benchmark_note'] ?? ''}'),
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(child: _recBlock(c, 'PRIMARY PICK', Map<String, dynamic>.from(rec['primary']), c.up)),
                const SizedBox(width: 12),
                Expanded(
                  child: rec['alternative'] != null
                      ? _recBlock(c, 'ALTERNATIVE', Map<String, dynamic>.from(rec['alternative']), c.blue)
                      : const SizedBox(),
                ),
              ]),
              const SizedBox(height: 12),
              Text('BEST IN CLASS', style: AppTextStyles.labelXs(c.t3)),
              const SizedBox(height: 6),
              Wrap(spacing: 6, runSpacing: 6, children: [
                _bicChip(c, 'Best overall', bic['best_overall']),
                _bicChip(c, 'Most consistent', bic['best_consistency']),
                _bicChip(c, 'Best downside protection', bic['best_downside_protection']),
                _bicChip(c, 'Best risk-adjusted', bic['best_risk_adjusted']),
              ]),
              if (gaps.isNotEmpty) ...[
                const SizedBox(height: 10),
                Text('DATA GAPS (never estimated): ${gaps.join(' · ')}',
                    style: AppTextStyles.captionXs(c.t4)),
              ],
            ]),
          ),
        ])),
      ],
      const SizedBox(height: 12),

      // ── FULL RESEARCH TABLE (horizontal scroll) ──
      DenseCard(
        clip: true,
        child: Column(children: [
          denseTableHeader(context,
              icon: LucideIcons.barChart2,
              accent: c.accent,
              title: 'Fund Comparison — full research table, ranked by weighted score',
              subtitle: '${res.length} funds · Scroll horizontally for all columns · Click a row for the scorecard · "—" = DATA GAP, never estimated'),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              // Header row
              Container(
                decoration: BoxDecoration(
                  color: c.bg3,
                  border: Border(top: BorderSide(color: c.bd), bottom: BorderSide(color: c.bd)),
                ),
                child: Row(children: [
                  for (final (label, w, right) in _cols)
                    Container(
                      width: w,
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 7),
                      alignment: right ? Alignment.centerRight : Alignment.centerLeft,
                      child: Text(label, style: AppTextStyles.labelXs(c.t4).copyWith(fontSize: 9)),
                    ),
                ]),
              ),
              ...List.generate(res.length, (i) => _fullTableRow(c, res[i], i)),
            ]),
          ),
        ]),
      ),

      // ── EXPANDED SCORECARD (full width, below the scrolling table) ──
      ...res.where((r) => r['scheme_code'] == _expandedCode && r['error'] == null).map((r) => Padding(
            padding: const EdgeInsets.only(top: 12),
            child: DenseCard(clip: true, child: _buildScorecard(c, r, (r['metrics'] ?? {}) as Map<String, dynamic>)),
          )),
      const SizedBox(height: 8),
      if (_results!['disclaimer'] != null)
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          child: Text(_results!['disclaimer'].toString(), style: AppTextStyles.captionXs(c.t4)),
        ),
    ]);
  }

  static String _aum(dynamic v) {
    if (v == null) return '—';
    final n = (v as num).toDouble();
    if (n >= 100000) return '₹${(n / 100000).toStringAsFixed(1)}L Cr';
    if (n >= 1000) return '₹${(n / 1000).toStringAsFixed(n >= 10000 ? 0 : 1)}k Cr';
    return '₹${n.round()} Cr';
  }

  static String _shortCategory(dynamic cat) => (cat ?? '')
      .toString()
      .replaceAll(RegExp(r'^.*Scheme\s*-\s*'), '')
      .replaceAll(' Fund', '');

  static String _valuationShort(dynamic v) {
    final s = (v ?? '').toString();
    if (s.isEmpty) return 'DATA GAP';
    if (s.startsWith('Relatively')) return 'Undervalued';
    if (s.startsWith('Fairly')) return 'Fair';
    if (s.startsWith('Slightly')) return 'Slightly rich';
    return 'Overvalued';
  }

  Widget _fullTableRow(AppColorScheme c, Map<String, dynamic> r, int i) {
    final totalW = _cols.fold<double>(0, (s, col) => s + col.$2);
    if (r['error'] != null) {
      return Container(
        width: totalW,
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.bd.withValues(alpha: 0.6)))),
        child: Text('${i + 1}  ${r['scheme_name']}: ${r['error']}', style: AppTextStyles.bodySmall(c.dn)),
      );
    }
    final m = (r['metrics'] ?? {}) as Map<String, dynamic>;
    final decision = (r['decision'] ?? 'WAIT').toString();
    final isExpanded = _expandedCode == r['scheme_code'];
    final cagr3y = ((m['cagr_3y'] ?? 0) as num).toDouble();
    final alpha = ((m['alpha'] ?? 0) as num).toDouble();
    final rollMin = ((m['rolling_min'] ?? 0) as num).toDouble();
    final score = r['score'] as num?;
    final scoreColor = score == null ? c.t4 : score >= 70 ? c.up : score >= 58 ? c.gold : c.dn;
    final catOk = r['category_ok'] as bool?;
    final planOk = r['plan_ok'] == true;
    final managers = m['managers']?.toString();
    final mgrCount = managers == null || managers.isEmpty
        ? 0
        : managers.split(RegExp(r'[;,]')).where((s) => s.trim().isNotEmpty).length;
    final underp = m['underperf_months'] as num?;
    final underpColor = underp == null ? c.t4 : underp < 6 ? c.up : underp < 15 ? c.gold : c.dn;
    final relPe = m['relative_pe'] as num?;
    final relPeColor = relPe == null ? c.t4 : relPe < 0.90 ? c.up : relPe <= 1.10 ? c.t2 : relPe <= 1.25 ? c.gold : c.dn;
    final overlap = m['overlap_max'] as num?;
    final overlapColor = overlap == null ? c.t4 : overlap < 30 ? c.up : overlap <= 60 ? c.gold : c.dn;

    Widget num_(dynamic text, Color color, {bool bold = false}) =>
        denseNum(context, text.toString(), color, bold: bold);
    Widget txt(String s, Color color, {bool bold = false}) => Text(s,
        style: AppTextStyles.captionXs(color).copyWith(fontWeight: bold ? FontWeight.w700 : FontWeight.w500),
        maxLines: 1, overflow: TextOverflow.ellipsis);

    final cells = <Widget>[
      Text('${i + 1}', style: AppTextStyles.monoXs(c.t4)),
      txt(_shortName(r['scheme_name']), decision.startsWith('ENTER') ? c.t1 : c.t2, bold: true),
      catOk == null
          ? txt('—', c.t4)
          : txt('${catOk ? '✓' : '✗'} ${_shortCategory(r['scheme_category'])}', catOk ? c.up : c.dn),
      txt(planOk ? '✓ Direct-Growth' : '✗ Check plan', planOk ? c.up : c.dn),
      txt((m['benchmark_official'] ?? '${m['bm_name'] ?? '—'} PR').toString(), c.t3),
      num_(_pct(m['bm_3y_cagr']), c.t2),
      num_(_pct(m['cagr_3y']), cagr3y >= 0 ? c.up : c.dn),
      num_(_pct(m['rolling_avg']), c.t2),
      num_(_pct(m['rolling_min']), rollMin < 0 ? c.dn : c.t2),
      num_(_pct(m['rolling_consistency']), c.t2),
      num_(_pct(m['roll_ge20']), c.t2),
      num_(_f(m['sharpe']), c.t2),
      num_(_f(m['sortino']), c.t2),
      num_(_pct(m['alpha']), alpha > 0 ? c.up : c.dn),
      num_(_pct(m['max_dd']), c.t2),
      num_(_pct(m['ter']), c.t2),
      txt(mgrCount == 0 ? '—' : '$mgrCount named · tenure —', mgrCount == 0 ? c.t4 : c.t2),
      num_(_aum(m['aum_cr']), c.t2),
      num_('—', c.t4), // Inflow trend — DATA GAP (no AUM history feed)
      num_('${_f(m['portfolio_pe'])} · ${_f(m['portfolio_pb'])}',
          m['portfolio_pe'] == null ? c.t4 : c.t2),
      num_(_f(m['relative_pe']), relPeColor),
      txt(_valuationShort(m['valuation']), relPeColor),
      num_(overlap == null ? '—' : '$overlap%', overlapColor), // max vs basket
      num_(underp == null ? '—' : '${underp}m', underpColor),
      num_(score == null ? '—' : '$score', scoreColor, bold: true),
      _decisionBadge(decision),
    ];

    return Material(
      color: isExpanded
          ? c.accent.withValues(alpha: 0.06)
          : i.isOdd
              ? c.bg3.withValues(alpha: 0.35)
              : Colors.transparent,
      child: InkWell(
        onTap: () => setState(() => _expandedCode = isExpanded ? null : r['scheme_code'] as int?),
        child: Container(
          decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.bd.withValues(alpha: 0.5)))),
          child: Row(children: [
            for (var j = 0; j < _cols.length; j++)
              Container(
                width: _cols[j].$2,
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 7),
                alignment: _cols[j].$3 ? Alignment.centerRight : Alignment.centerLeft,
                child: cells[j],
              ),
          ]),
        ),
      ),
    );
  }

  Widget _recBlock(AppColorScheme c, String label, Map<String, dynamic> p, Color accent) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: accent.withValues(alpha: 0.05),
        border: Border.all(color: accent.withValues(alpha: 0.25)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text(label, style: AppTextStyles.labelXs(accent)),
          const Spacer(),
          _decisionBadge((p['decision'] ?? '').toString()),
        ]),
        const SizedBox(height: 6),
        Text(_shortName(p['scheme_name']), style: AppTextStyles.bodyBold(c.t1)),
        Text('Score ${_f(p['score'])}/100', style: AppTextStyles.monoXs(c.t3)),
        const SizedBox(height: 6),
        Text((p['reason'] ?? '').toString(), style: AppTextStyles.captionXs(c.t2)),
        const SizedBox(height: 6),
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(LucideIcons.calendarClock, size: 11, color: c.t3),
          const SizedBox(width: 4),
          Expanded(child: Text((p['entry_plan'] ?? '').toString(), style: AppTextStyles.captionXs(c.t3))),
        ]),
      ]),
    );
  }

  Widget _bicChip(AppColorScheme c, String label, dynamic pick) {
    final name = pick == null ? 'DATA GAP' : _shortName((pick as Map)['scheme_name']);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: c.bg3,
        border: Border.all(color: c.bd),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Text('$label: ', style: AppTextStyles.captionXs(c.t4)),
        Text(name, style: AppTextStyles.captionXs(c.t1).copyWith(fontWeight: FontWeight.w700)),
      ]),
    );
  }

  Widget _decisionBadge(String decision) {
    BadgeVariant variant;
    String label;
    switch (decision) {
      case 'ENTER NOW':
        variant = BadgeVariant.up; label = 'ENTER NOW';
      case 'ENTER GRADUALLY':
        variant = BadgeVariant.accent; label = 'GRADUAL';
      case 'SIP ONLY':
        variant = BadgeVariant.blue; label = 'SIP ONLY';
      case 'WAIT':
        variant = BadgeVariant.gold; label = 'WAIT';
      default:
        variant = BadgeVariant.dn; label = 'AVOID';
    }
    return Align(
      alignment: Alignment.centerRight,
      child: AppBadge(text: label, variant: variant, fontSize: 10),
    );
  }

  Widget _buildScorecard(AppColorScheme c, Map<String, dynamic> r, Map<String, dynamic> m) {
    final checks = List<Map<String, dynamic>>.from(r['checks'] ?? []);
    final comps = List<Map<String, dynamic>>.from(r['components'] ?? []);
    final decision = (r['decision'] ?? 'WAIT').toString();
    final tiles = <List<String>>[
      ['1Y CAGR', _pct(m['cagr_1y'])], ['3Y CAGR', _pct(m['cagr_3y'])], ['5Y CAGR', _pct(m['cagr_5y'])],
      ['7Y CAGR', _pct(m['cagr_7y'])], ['10Y CAGR', _pct(m['cagr_10y'])],
      ['BM 3Y CAGR', _pct(m['bm_3y_cagr'])],
      ['SIP XIRR 3Y', _pct(m['xirr_3y'])], ['SIP XIRR 5Y', _pct(m['xirr_5y'])],
      ['ROLL AVG', _pct(m['rolling_avg'])], ['ROLL MEDIAN', _pct(m['rolling_median'])],
      ['ROLL MIN', _pct(m['rolling_min'])], ['ROLL MAX', _pct(m['rolling_max'])],
      ['% POSITIVE', _pct(m['rolling_consistency'])],
      ['% ≥8%', _pct(m['roll_ge8'])], ['% ≥10%', _pct(m['roll_ge10'])], ['% ≥12%', _pct(m['roll_ge12'])],
      ['% ≥15%', _pct(m['roll_ge15'])], ['% ≥20%', _pct(m['roll_ge20'])],
      ['% BEAT BM', _pct(m['roll_beat_bm'])],
      ['SHARPE', _f(m['sharpe'])], ['SORTINO', _f(m['sortino'])], ['ALPHA', _pct(m['alpha'])],
      ['BETA', _f(m['beta'])], ['INFO RATIO', _f(m['info_ratio'])],
      ['VOLATILITY', _pct(m['volatility'])], ['TRACK ERROR', _pct(m['tracking_error'])],
      ['MAX DRAWDOWN', _pct(m['max_dd'])],
      ['DD RECOVERY', m['max_dd_recovery_days'] == null ? 'Not yet' : '${m['max_dd_recovery_days']}d'],
      ['CURRENT DD', _pct(m['current_dd'])],
      ['DOWNSIDE CAP', _pct(m['down_capture'])], ['UPSIDE CAP', _pct(m['up_capture'])],
      ['UNDERPERF', m['underperf_months'] == null ? '—' : '${m['underperf_months']}m'],
      ['DIRECT TER', _pct(m['ter'])],
      ['AUM', _aum(m['aum_cr'])],
      ['RATING', m['fund_rating'] == null ? '—' : '${m['fund_rating']}★'],
      ['PORTFOLIO P/E', _f(m['portfolio_pe'])], ['CATEGORY P/E', _f(m['category_pe'])],
      ['REL P/E (CAT)', _f(m['relative_pe'])],
      ['PORTFOLIO P/B', _f(m['portfolio_pb'])], ['CATEGORY P/B', _f(m['category_pb'])],
      ['DIV YIELD', _pct(m['div_yield'])], ['ROE', _pct(m['roe'])],
      ['HOLDINGS', _f(m['holdings_count'])],
      ['TOP-5 WT', _pct(m['top5_weight'])], ['TOP-10 WT', _pct(m['top10_weight'])],
      ['TOP-3 SECTORS', _pct(m['top3_sector_weight'])], ['CASH', _pct(m['cash_pct'])],
      ['LARGE CAP', _pct(m['large_cap_pct'])], ['MID CAP', _pct(m['mid_cap_pct'])],
      ['SMALL CAP', _pct(m['small_cap_pct'])],
      ['CAT AVG 1Y', _pct(m['cat_avg_1y'])], ['CAT AVG 3Y', _pct(m['cat_avg_3y'])],
      ['CAT RANK 3Y', m['cat_rank_3y'] == null ? '—' : '#${m['cat_rank_3y']}'],
      ['CAT AVG 5Y', _pct(m['cat_avg_5y'])],
      ['BASKET OVERLAP', m['overlap_max'] == null ? '—' : '${m['overlap_max']}%'],
    ];
    return Container(
      padding: const EdgeInsets.all(16), color: c.bg1,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(r['scheme_name']?.toString() ?? '', style: AppTextStyles.bodyBold(c.t1)),
            Text('${r['fund_house']} · ${r['scheme_category'] ?? ''} · NAV ₹${m['nav']} (${m['nav_date']}) · Age ${m['years']}Y',
                style: AppTextStyles.captionXs(c.t3)),
            Text('Official benchmark: ${m['benchmark_official'] ?? 'DATA GAP'} · Stats computed vs ${m['bm_name'] ?? '—'} (price-return proxy)',
                style: AppTextStyles.captionXs(c.t4)),
            if (m['managers'] != null)
              Text('Managers: ${m['managers']} · tenure DATA GAP (${m['extras_source'] ?? 'provider'})',
                  style: AppTextStyles.captionXs(c.t4)),
            if (m['top_holdings'] != null)
              Text('Top holdings: ${(m['top_holdings'] as List).join(', ')}'
                  '${m['overlap_with'] != null ? ' · Max basket overlap: ${m['overlap_max']}% with ${_shortName(m['overlap_with'])}' : ''}',
                  style: AppTextStyles.captionXs(c.t4)),
            if (m['exit_load'] != null)
              Text('Exit load: ${m['exit_load'].toString().length > 180 ? '${m['exit_load'].toString().substring(0, 180)}…' : m['exit_load']}',
                  style: AppTextStyles.captionXs(c.t4), maxLines: 2, overflow: TextOverflow.ellipsis),
          ])),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Text('${_f(r['score'])}/100', style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 18)),
            const SizedBox(height: 4),
            _decisionBadge(decision),
          ]),
        ]),
        const SizedBox(height: 8),
        Text((r['reason'] ?? '').toString(), style: AppTextStyles.bodySmall(c.t2)),
        const SizedBox(height: 4),
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(LucideIcons.calendarClock, size: 12, color: c.t3),
          const SizedBox(width: 5),
          Expanded(child: Text((r['entry_plan'] ?? '').toString(), style: AppTextStyles.captionXs(c.t3))),
        ]),
        const SizedBox(height: 12),
        // Full metrics grid — '—' marks a DATA GAP, never an estimate
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final kv in tiles)
            Container(width: 112, padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(color: c.bg2, border: Border.all(color: c.bd), borderRadius: BorderRadius.circular(6)),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(kv[0], style: AppTextStyles.labelXs(c.t4).copyWith(fontSize: 9)),
                const SizedBox(height: 2),
                Text(kv[1], style: AppTextStyles.monoBold(kv[1] == '—' ? c.t4 : c.t1).copyWith(fontSize: 12)),
              ])),
        ]),
        if (comps.isNotEmpty) ...[
          const SizedBox(height: 14),
          Text('WEIGHTED SCORE COMPONENTS — renormalized over ${_f(r['scored_weight'])}% of framework weight (DATA GAPs excluded, never estimated)',
              style: AppTextStyles.labelXs(c.t3)),
          const SizedBox(height: 8),
          ...comps.map((cp) {
            final wt = ((cp['weight'] ?? 0) as num).toDouble();
            final sc = cp['score'] as num?;
            final frac = sc == null || wt == 0 ? 0.0 : (sc / wt).clamp(0.0, 1.0).toDouble();
            final color = sc == null ? c.t4 : frac >= 0.7 ? c.up : frac >= 0.45 ? c.gold : c.dn;
            return Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
                SizedBox(width: 240, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(cp['name']?.toString() ?? '', style: AppTextStyles.captionXs(c.t1).copyWith(fontWeight: FontWeight.w600)),
                  Text(cp['detail']?.toString() ?? '', style: AppTextStyles.captionXs(c.t4).copyWith(fontSize: 9), maxLines: 2, overflow: TextOverflow.ellipsis),
                ])),
                const SizedBox(width: 10),
                Expanded(child: ClipRRect(
                  borderRadius: BorderRadius.circular(2),
                  child: LinearProgressIndicator(
                    value: frac, minHeight: 5,
                    backgroundColor: c.bg3,
                    valueColor: AlwaysStoppedAnimation(color),
                  ),
                )),
                const SizedBox(width: 10),
                SizedBox(width: 78, child: Text(
                  sc == null ? 'DATA GAP' : '$sc / ${wt.toInt()}',
                  style: AppTextStyles.monoXs(color), textAlign: TextAlign.right)),
              ]),
            );
          }),
        ],
        const SizedBox(height: 12),
        Text('RESEARCH SCORECARD (${r['greens']} PASS · ${r['yellows'] ?? 0} WATCH · ${r['reds']} FAIL · gray = DATA GAP)',
            style: AppTextStyles.labelXs(c.t3)),
        const SizedBox(height: 8),
        Wrap(spacing: 6, runSpacing: 6, children: checks.map((ch) {
          final s = ch['s']?.toString() ?? 'gray';
          final color = s == 'green' ? c.up : s == 'red' ? c.dn : s == 'yellow' ? c.gold : c.t4;
          final icon = s == 'green'
              ? LucideIcons.checkCircle2
              : s == 'red'
                  ? LucideIcons.xCircle
                  : s == 'yellow'
                      ? LucideIcons.alertTriangle
                      : LucideIcons.minus;
          return Container(
            width: 260, padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
                color: color.withValues(alpha: 0.08),
                border: Border.all(color: color.withValues(alpha: 0.20)),
                borderRadius: BorderRadius.circular(6)),
            child: Row(children: [
              Icon(icon, size: 12, color: color),
              const SizedBox(width: 6),
              Expanded(child: Text(ch['p']?.toString() ?? '', style: AppTextStyles.captionXs(color).copyWith(fontWeight: FontWeight.w600))),
              Text(ch['v']?.toString() ?? '', style: AppTextStyles.mono(color).copyWith(fontSize: 11, fontWeight: FontWeight.w700)),
            ]),
          );
        }).toList()),
      ]),
    );
  }

  @override
  void dispose() { _searchCtrl.dispose(); _debounce?.cancel(); _pollTimer?.cancel(); super.dispose(); }
}
