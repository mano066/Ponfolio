import 'dart:async';
import 'package:aiei_wealth/core/constants.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_colors.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/providers/providers.dart';
import 'package:aiei_wealth/presentation/widgets/animated_page_wrapper.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/widgets/deep_analysis_widgets.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/services/api_service.dart';

/// Deep Analysis screen with stock selector and 9-agent analysis cards
/// (Data-Dense Dashboard style — dense cards, hairline borders, mono numbers).
class DeepAnalysisScreen extends ConsumerStatefulWidget {
  const DeepAnalysisScreen({super.key});
  @override
  ConsumerState<DeepAnalysisScreen> createState() => _DeepAnalysisScreenState();
}

class _DeepAnalysisScreenState extends ConsumerState<DeepAnalysisScreen> {
  String? _symbol;
  Map<String, dynamic>? _data;
  bool _loading = false;
  String? _error;
  bool _initialized = false;

  // Progress tracking for 9-agent pipeline
  int _currentAgent = 0;
  Timer? _progressTimer;
  Timer? _clockTimer;
  final _stopwatch = Stopwatch();

  // Stock search
  final _searchCtrl = TextEditingController();
  final _searchLayerLink = LayerLink();
  OverlayEntry? _overlayEntry;
  List<Map<String, dynamic>> _searchResults = [];
  bool _searching = false;
  Timer? _searchDebounce;

  static const _agentStages = [
    {'name': 'Data Collection Agent', 'icon': '📊', 'desc': 'Fetching market data, fundamentals & financials'},
    {'name': 'Fundamental Agent', 'icon': '📈', 'desc': 'Analyzing P/E, P/B, ROE, debt ratios, revenue growth'},
    {'name': 'Technical Agent', 'icon': '📉', 'desc': 'Computing RSI, MACD, Bollinger Bands, support/resistance'},
    {'name': 'Sentiment Agent', 'icon': '📰', 'desc': 'Processing news sentiment and market buzz'},
    {'name': 'Macro Agent', 'icon': '🌍', 'desc': 'Evaluating sector outlook and interest rate sensitivity'},
    {'name': 'Quant Agent', 'icon': '🧮', 'desc': 'Calculating DCF, Graham number, PEG ratio'},
    {'name': 'Risk Agent', 'icon': '🛡️', 'desc': 'Assessing volatility, drawdown risk, portfolio impact'},
    {'name': 'Execution Agent', 'icon': '⚡', 'desc': 'Structuring trade parameters and position sizing'},
    {'name': 'Master CIO', 'icon': '🎯', 'desc': 'Synthesizing all agents into final recommendation'},
  ];

  @override
  void initState() {
    super.initState();
  }

  @override
  void dispose() {
    _progressTimer?.cancel();
    _clockTimer?.cancel();
    _searchDebounce?.cancel();
    _searchCtrl.dispose();
    _removeOverlay();
    super.dispose();
  }

  void _initIfNeeded() {
    if (_initialized) return;
    _initialized = true;
    final portfolio = ref.read(portfolioProvider);
    portfolio.whenData((d) {
      final holdings = List<Map<String, dynamic>>.from(d['holdings'] ?? []);
      if (holdings.isNotEmpty && _symbol == null) {
        setState(() => _symbol = holdings.first['symbol'] as String);
      }
    });
  }

  void _onSearchChanged(String query) {
    _searchDebounce?.cancel();
    if (query.trim().length < 2) {
      setState(() { _searchResults = []; });
      _removeOverlay();
      return;
    }
    _searchDebounce = Timer(const Duration(milliseconds: 400), () {
      _searchStocks(query.trim());
    });
  }

  Future<void> _searchStocks(String query) async {
    setState(() { _searching = true; });
    try {
      final results = await ApiService().searchStocks(query);
      if (mounted) {
        setState(() { _searchResults = results; _searching = false; });
        _showOverlay();
      }
    } catch (_) {
      if (mounted) setState(() { _searching = false; });
    }
  }

  void _removeOverlay() {
    _overlayEntry?.remove();
    _overlayEntry = null;
  }

  void _showOverlay() {
    _removeOverlay();
    if (_searchResults.isEmpty) return;
    final c = context.colors;
    _overlayEntry = OverlayEntry(builder: (ctx) {
      return Positioned(
        width: MediaQuery.sizeOf(context).width - 220 - 32,
        child: CompositedTransformFollower(
          link: _searchLayerLink,
          showWhenUnlinked: false,
          offset: const Offset(0, 44),
          child: Material(
            elevation: 6,
            borderRadius: BorderRadius.circular(8),
            color: c.bg2,
            child: Container(
              constraints: const BoxConstraints(maxHeight: 320),
              decoration: BoxDecoration(
                color: c.bg2,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: c.bd),
              ),
              child: ListView.builder(
                shrinkWrap: true,
                padding: EdgeInsets.zero,
                itemCount: _searchResults.length,
                itemBuilder: (_, i) {
                  final r = _searchResults[i];
                  final sym = r['symbol']?.toString() ?? '';
                  final name = r['name']?.toString() ?? r['company']?.toString() ?? sym;
                  final exchange = r['exchange']?.toString() ?? '';
                  final clean = sym.replaceAll(RegExp(r'\.(NS|BO)$', caseSensitive: false), '');

                  return InkWell(
                    onTap: () => _selectSearchResult(sym),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
                      decoration: BoxDecoration(
                        border: Border(bottom: BorderSide(color: c.bd.withValues(alpha: 0.6))),
                      ),
                      child: Row(children: [
                        Icon(LucideIcons.trendingUp, size: 13, color: c.blue),
                        const SizedBox(width: 10),
                        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Row(children: [
                            Text(clean, style: AppTextStyles.bodyBold(c.t1).copyWith(fontSize: 12)),
                            if (exchange.isNotEmpty) ...[
                              const SizedBox(width: 6),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                                decoration: BoxDecoration(
                                  color: exchange.contains('NSE') ? c.blueBg : c.goldBg,
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(exchange, style: AppTextStyles.labelXs(
                                  exchange.contains('NSE') ? c.blue : c.gold,
                                ).copyWith(fontSize: 8)),
                              ),
                            ],
                          ]),
                          Text(name, style: AppTextStyles.captionXs(c.t4), maxLines: 1, overflow: TextOverflow.ellipsis),
                        ])),
                        Icon(LucideIcons.zap, size: 13, color: c.accent),
                        const SizedBox(width: 4),
                        Text('ANALYZE', style: AppTextStyles.labelXs(c.accent)),
                      ]),
                    ),
                  );
                },
              ),
            ),
          ),
        ),
      );
    });
    Overlay.of(context).insert(_overlayEntry!);
  }

  void _selectSearchResult(String symbol) {
    _removeOverlay();
    setState(() {
      _symbol = symbol;
      _searchCtrl.clear();
      _searchResults = [];
    });
    _runAnalysis();
  }

  Future<void> _runAnalysis() async {
    if (_symbol == null) return;
    setState(() { _loading = true; _error = null; _data = null; _currentAgent = 0; });
    _stopwatch.reset();
    _stopwatch.start();

    _clockTimer?.cancel();
    _clockTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted && _loading) setState(() {});
    });

    try {
      final startResp = await ApiService().startDeepAnalysis(_symbol!);
      final jobId = startResp['job_id'] as String;

      _progressTimer?.cancel();
      _progressTimer = Timer.periodic(const Duration(seconds: 2), (t) async {
        if (!mounted) { t.cancel(); return; }
        try {
          final status = await ApiService().getDeepAnalysisStatus(jobId);
          final agentIdx = (status['current_agent_idx'] as int?) ?? 0;
          setState(() => _currentAgent = agentIdx.clamp(0, _agentStages.length - 1));

          if (status['status'] == 'done') {
            t.cancel();
            _stopwatch.stop();
            _clockTimer?.cancel();
            setState(() {
              _data = status['result'] as Map<String, dynamic>?;
              _loading = false;
            });
          } else if (status['status'] == 'error') {
            t.cancel();
            _stopwatch.stop();
            _clockTimer?.cancel();
            setState(() {
              _error = status['error']?.toString() ?? 'Unknown error';
              _loading = false;
            });
          }
        } catch (e) {
          // Poll failure is transient — keep trying
        }
      });
    } catch (e) {
      setState(() => _error = e.toString());
      _stopwatch.stop();
      _clockTimer?.cancel();
      setState(() => _loading = false);
    }
  }

  String _clean(String sym) => sym.replaceAll(RegExp(r'\.(NS|BO)$', caseSensitive: false), '');

  Color _verdictColor(String? v) {
    if (v == null) return context.colors.t1;
    final u = v.toUpperCase();
    if (['BULLISH', 'BUY', 'STRONG', 'POSITIVE', 'UNDERVALUED', 'LOW', 'UPTREND'].any(u.contains)) return context.colors.up;
    if (['BEARISH', 'SELL', 'WEAK', 'NEGATIVE', 'OVERVALUED', 'DOWNTREND', 'VERY HIGH'].any(u.contains)) return context.colors.dn;
    return context.colors.t1;
  }

  /// Count how many agents are bullish/bearish/neutral from the data.
  Map<String, int> _countConsensus(Map<String, dynamic> agents) {
    int bullish = 0, bearish = 0, neutral = 0;
    for (final entry in agents.entries) {
      if (entry.value is! Map) continue;
      // Exclude the risk agent: its risk_level (HIGH/LOW) is a risk magnitude,
      // not a directional bull/bear verdict, so it must not skew consensus.
      if (entry.key == 'risk') continue;
      final agent = entry.value as Map<String, dynamic>;
      final verdict = (agent['verdict'] ?? agent['trend'] ?? agent['sentiment'] ?? agent['sector_outlook'] ?? '').toString().toUpperCase();
      if (verdict.isEmpty) continue;
      if (['BULLISH', 'BUY', 'STRONG', 'POSITIVE', 'UNDERVALUED', 'UPTREND'].any(verdict.contains)) {
        bullish++;
      } else if (['BEARISH', 'SELL', 'WEAK', 'NEGATIVE', 'OVERVALUED', 'DOWNTREND'].any(verdict.contains)) {
        bearish++;
      } else {
        neutral++;
      }
    }
    return {'bullish': bullish, 'bearish': bearish, 'neutral': neutral};
  }

  /// Parse the CIO conviction score defensively. Backend returns int or NULL;
  /// a missing/failed CIO call must NOT be shown as a fabricated number.
  double? _parseConviction(dynamic raw) {
    if (raw == null) return null;
    if (raw is num) return raw.toDouble().clamp(0, 100);
    final parsed = double.tryParse(raw.toString());
    return parsed?.clamp(0, 100);
  }

  /// Format a percentage-valued metric (double %, or null) as e.g. "18.4%".
  /// Renders "—" when null/non-numeric. No leading sign (these are levels).
  String _fmtPct(dynamic raw) {
    if (raw is num) return '${raw.toStringAsFixed(1)}%';
    if (raw is String) {
      final v = double.tryParse(raw);
      if (v != null) return '${v.toStringAsFixed(1)}%';
      return raw.isEmpty ? '—' : raw;
    }
    return '—';
  }

  /// Revenue CAGR: backend emits EXACTLY ONE of revenue_cagr_3yr / _2yr.
  String _revenueCagrLabel(Map<String, dynamic> f) =>
      f['revenue_cagr_3yr'] != null ? '3-Year Revenue CAGR' : '2-Year Revenue CAGR';

  String _revenueCagrValue(Map<String, dynamic> f) {
    final v = f['revenue_cagr_3yr'] ?? f['revenue_cagr_2yr'];
    return _fmtPct(v);
  }

  /// Altman Z is not valid for banks/financials — backend sets
  /// altman_applicable=false and altman_z_score=null in that case.
  bool _altmanApplicable(Map<String, dynamic> f) =>
      f['altman_applicable'] != false && f['altman_z_score'] != null;

  String _altmanValue(Map<String, dynamic> f) =>
      _altmanApplicable(f) ? '${f['altman_z_score']}' : 'N/A (not valid for financials)';

  /// Extract numeric scores from agents for the radar chart. Only plots axes
  /// whose agent actually returned a numeric score — no fabricated 5.0
  /// defaults, and the Execution axis (which carries no score) is excluded.
  Map<String, double> _extractScores(Map<String, dynamic> agents) {
    final scores = <String, double>{};
    final labels = {
      'fundamental': 'Fundamental', 'technical': 'Technical', 'quant': 'Quant',
      'news': 'Sentiment', 'macro': 'Macro', 'risk': 'Risk',
    };
    for (final entry in labels.entries) {
      final agent = agents[entry.key];
      if (agent is Map) {
        final s = agent['score'];
        if (s is num) {
          scores[entry.value] = s.toDouble().clamp(0, 10);
        }
      }
    }
    return scores;
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final activeTab = ref.watch(activeTabProvider);
    if (activeTab == AppTab.deepAnalysis) {
      _initIfNeeded();
    }
    final portfolio = ref.watch(portfolioProvider);
    final holdings = portfolio.when(
      data: (d) => List<Map<String, dynamic>>.from(d['holdings'] ?? []),
      loading: () => <Map<String, dynamic>>[], error: (_, _) => <Map<String, dynamic>>[],
    );

    return ListView(padding: EdgeInsets.zero, children: [
      // ─── Header with stock selector + search ───
      AnimatedListItem(
        index: 0,
        child: DenseCard(
          child: Column(children: [
            denseTableHeader(context,
                icon: LucideIcons.target,
                accent: c.accent,
                title: 'Deep Analysis',
                subtitle: '9-agent multi-dimensional orchestration pipeline',
                trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    decoration: BoxDecoration(
                      color: c.bg3,
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: c.bd),
                    ),
                    child: DropdownButton<String>(
                      value: holdings.any((h) => h['symbol'] == _symbol) ? _symbol : null,
                      isDense: true, underline: const SizedBox(),
                      hint: Text('Portfolio', style: AppTextStyles.mono(c.t4).copyWith(fontSize: 12)),
                      dropdownColor: c.bg2, style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 12),
                      items: holdings.map((h) {
                        final sym = h['symbol'] as String;
                        return DropdownMenuItem(value: sym, child: Text(_clean(sym)));
                      }).toList(),
                      onChanged: (v) {
                        if (v != null) {
                          setState(() => _symbol = v);
                          _searchCtrl.clear();
                          _runAnalysis();
                        }
                      },
                    ),
                  ),
                  const SizedBox(width: 8),
                  HeaderButton(
                    icon: const Icon(LucideIcons.zap, size: 13, color: Colors.white),
                    text: 'Run Full Analysis',
                    solidColor: c.accent,
                    onTap: _runAnalysis,
                  ),
                ])),
            // Search any stock
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
              child: CompositedTransformTarget(
                link: _searchLayerLink,
                child: Container(
                  decoration: BoxDecoration(
                    color: c.bg3, borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: c.bd),
                  ),
                  child: Row(children: [
                    const SizedBox(width: 12),
                    Icon(LucideIcons.search, size: 14, color: c.blue),
                    const SizedBox(width: 8),
                    Expanded(child: TextField(
                      controller: _searchCtrl,
                      style: AppTextStyles.bodySmall(c.t1),
                      decoration: InputDecoration(
                        hintText: 'Search any NSE/BSE stock to analyze (e.g., TATA, BAJAJ, HDFC)...',
                        hintStyle: AppTextStyles.bodySmall(c.t4),
                        border: InputBorder.none, isDense: true,
                        contentPadding: const EdgeInsets.symmetric(vertical: 9),
                      ),
                      onChanged: _onSearchChanged,
                      onTap: () {
                        if (_searchResults.isNotEmpty) _showOverlay();
                      },
                    )),
                    if (_searching) Padding(
                      padding: const EdgeInsets.only(right: 12),
                      child: SizedBox(width: 14, height: 14,
                        child: CircularProgressIndicator(strokeWidth: 2, color: c.blue)),
                    ),
                    if (_symbol != null) Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                        decoration: BoxDecoration(
                          color: c.accent.withValues(alpha: 0.10),
                          border: Border.all(color: c.accent.withValues(alpha: 0.22)),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text('ANALYZING · ${_clean(_symbol!)}',
                            style: AppTextStyles.labelXs(c.accent)),
                      ),
                    ),
                  ]),
                ),
              ),
            ),
          ]),
        ),
      ),
      const SizedBox(height: 12),

      // Content
      if (_loading) Center(child: EnhancedLoadingView(
        symbol: _symbol ?? '',
        currentAgent: _currentAgent,
        elapsed: _stopwatch.elapsed,
        agentStages: _agentStages,
      ))
      else if (_error != null) _buildError(c)
      else if (_data != null) _buildAnalysis(c),

      const SizedBox(height: 36),
    ]);
  }

  Widget _buildError(AppColorScheme c) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 40),
    child: ErrorRetry(
      title: 'Analysis failed',
      detail: _error,
      icon: LucideIcons.shieldAlert,
      onRetry: _runAnalysis,
    ),
  );

  Widget _buildAnalysis(AppColorScheme c) {
    final cio = (_data!['cio_report'] ?? {}) as Map<String, dynamic>;
    final agents = (_data!['agents'] ?? {}) as Map<String, dynamic>;
    final f = (agents['fundamental'] ?? {}) as Map<String, dynamic>;
    final t = (agents['technical'] ?? {}) as Map<String, dynamic>;
    final q = (agents['quant'] ?? {}) as Map<String, dynamic>;
    final n = (agents['news'] ?? {}) as Map<String, dynamic>;
    final m = (agents['macro'] ?? {}) as Map<String, dynamic>;
    final ri = (agents['risk'] ?? {}) as Map<String, dynamic>;
    final e = (agents['execution'] ?? {}) as Map<String, dynamic>;
    final decision = (cio['final_decision'] ?? 'HOLD').toString().toUpperCase();
    final isBuy = decision.contains('BUY');
    final isSell = decision.contains('SELL');
    final vc = isBuy ? c.up : isSell ? c.dn : c.gold;

    final consensus = _countConsensus(agents);
    final radarScores = _extractScores(agents);

    // Try to get current price from portfolio holdings
    final portfolio = ref.read(portfolioProvider);
    double? currentPrice;
    portfolio.whenData((d) {
      final holdings = List<Map<String, dynamic>>.from(d['holdings'] ?? []);
      for (final h in holdings) {
        if (h['symbol'] == _symbol) {
          currentPrice = (h['ltp'] ?? h['current_price'] ?? 0).toDouble();
          break;
        }
      }
    });

    final double? convictionScore = _parseConviction(cio['conviction_score']);
    final targetPrice = (cio['target_price'] is num) ? (cio['target_price'] as num).toDouble() : null;
    final stopLoss = (cio['stop_loss'] is num) ? (cio['stop_loss'] as num).toDouble() : null;

    return Column(children: [
      // ═══════════════════════════════════════════════════
      //  ROW 1: CIO VERDICT CARD
      // ═══════════════════════════════════════════════════
      AnimatedListItem(
        index: 1,
        child: DenseCard(
          clip: true,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            denseTableHeader(context,
                icon: LucideIcons.target,
                accent: vc,
                title: 'CIO Verdict · ${_clean(_symbol ?? '')}',
                subtitle:
                    '${consensus['bullish']} bullish · ${consensus['neutral']} neutral · ${consensus['bearish']} bearish agents',
                trailing: DSignalBadge(signal: decision)),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                // ── ZONE 1: VERDICT + YOUR POSITION (side by side) ──
                Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  // LEFT: Verdict + conviction
                  Container(
                    width: 132, padding: const EdgeInsets.symmetric(vertical: 12),
                    decoration: BoxDecoration(
                      color: vc.withValues(alpha: 0.05),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: vc.withValues(alpha: 0.2)),
                    ),
                    child: Column(children: [
                      Text(_clean(_symbol ?? ''), style: AppTextStyles.labelXs(c.t3)),
                      const SizedBox(height: 4),
                      Text(cio['action_type']?.toString() ?? decision,
                          style: AppTextStyles.labelXs(vc).copyWith(fontSize: 12),
                          textAlign: TextAlign.center),
                      const SizedBox(height: 8),
                      ConvictionRing(score: convictionScore, size: 76),
                    ]),
                  ),
                  const SizedBox(width: 14),
                  // RIGHT: Position + Action Plan
                  Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    // YOUR POSITION box
                    if (cio['portfolio'] != null && cio['portfolio']['is_held'] == true)
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: c.bg3, borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: c.bd),
                        ),
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Row(children: [
                            Icon(LucideIcons.briefcase, size: 11, color: c.accent),
                            const SizedBox(width: 6),
                            Text('YOUR POSITION', style: AppTextStyles.labelXs(c.accent)),
                          ]),
                          const SizedBox(height: 8),
                          Row(children: [
                            _positionChip(c, 'Shares', '${cio['portfolio']['shares']}', c.t1),
                            const SizedBox(width: 8),
                            _positionChip(c, 'Avg Cost', '₹${cio['portfolio']['avg_cost']}', c.t1),
                            const SizedBox(width: 8),
                            _positionChip(c, 'P&L',
                              '₹${cio['portfolio']['pnl']} (${cio['portfolio']['pnl_pct']}%)',
                              (cio['portfolio']['pnl'] as num) >= 0 ? c.up : c.dn),
                            const SizedBox(width: 8),
                            _positionChip(c, 'Weight',
                              '${cio['portfolio']['portfolio_weight_pct']}%',
                              (cio['portfolio']['portfolio_weight_pct'] as num) > 15 ? c.dn : c.t1),
                          ]),
                        ]),
                      )
                    else
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: c.bg3, borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: c.bd),
                        ),
                        child: Row(children: [
                          Icon(LucideIcons.info, size: 11, color: c.t3),
                          const SizedBox(width: 8),
                          Text('Not in your portfolio — evaluating as new entry',
                            style: AppTextStyles.bodySmall(c.t3)),
                        ]),
                      ),
                    const SizedBox(height: 10),

                    // ── ACTION PLAN ──
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: vc.withValues(alpha: 0.04),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: vc.withValues(alpha: 0.2)),
                      ),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Row(children: [
                          Icon(LucideIcons.clipboardList, size: 13, color: vc),
                          const SizedBox(width: 8),
                          Text('ACTION PLAN', style: AppTextStyles.labelXs(vc)),
                          const Spacer(),
                          if (cio['action_math'] != null && cio['action_math']['risk_reward'] != null)
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                              decoration: BoxDecoration(
                                color: c.bg3, borderRadius: BorderRadius.circular(4),
                                border: Border.all(color: c.bd),
                              ),
                              child: Text('R:R ${cio['action_math']['risk_reward']}',
                                  style: AppTextStyles.monoXs(c.accent)),
                            ),
                        ]),
                        const SizedBox(height: 8),
                        // Action steps from LLM
                        if (cio['action_steps'] is List)
                          ...List<Widget>.from((cio['action_steps'] as List).map((step) =>
                              _actionStep(c, step.toString(), vc,
                                  icon: isBuy
                                      ? LucideIcons.plus
                                      : isSell
                                          ? LucideIcons.minus
                                          : LucideIcons.check)))
                        else
                          // Fallback: build from action_math
                          ...(() {
                            final am = cio['action_math'] as Map<String, dynamic>? ?? {};
                            final steps = <Widget>[];
                            final avgCost = (am['new_avg_cost'] is num) ? (am['new_avg_cost'] as num).toDouble() : currentPrice ?? 0;
                            // Compute percentages locally from prices
                            final slPct = (stopLoss != null && avgCost > 0) ? ((stopLoss - avgCost) / avgCost * 100).toStringAsFixed(1) : '?';
                            final tgtPct = (targetPrice != null && avgCost > 0) ? ((targetPrice - avgCost) / avgCost * 100).toStringAsFixed(1) : '?';

                            if (am['suggested_add_shares'] != null && (am['suggested_add_shares'] as num) > 0 && isBuy) {
                              final addCostStr = (am['add_cost'] is num) ? '₹${(am['add_cost'] as num).toInt()}' : '';
                              steps.add(_actionStep(c, 'Buy ${am['suggested_add_shares']} shares @ ₹${am['add_price']}  ($addCostStr cost)', c.up));
                            }
                            if (am['new_avg_cost'] != null && am['old_shares'] != null && (am['old_shares'] as num) > 0) {
                              steps.add(_actionStep(c, 'New avg: ₹${am['new_avg_cost']}  →  ${am['new_total_shares']} shares total', c.t2));
                            }
                            if (stopLoss != null) {
                              steps.add(_actionStep(c, 'Stop Loss: ₹${stopLoss.round()}  ($slPct%)', c.dn));
                            }
                            if (targetPrice != null) {
                              steps.add(_actionStep(c, 'Target: ₹${targetPrice.round()}  (+$tgtPct%)  —  sell ${am['sell_qty_at_target'] ?? "50%"} at target', c.up));
                            }
                            if (steps.isEmpty) {
                              steps.add(_actionStep(c, decision == 'HOLD' ? 'Hold current position, no action needed' : 'See agent reports below for details', c.t3));
                            }
                            return steps;
                          })(),
                      ]),
                    ),
                  ])),
                ]),
                const SizedBox(height: 14),

                // ── ZONE 2: PRICE RULER ──
                if (targetPrice != null || stopLoss != null) ...[
                  PriceTargetRuler(currentPrice: currentPrice, targetPrice: targetPrice, stopLoss: stopLoss),
                  const SizedBox(height: 14),
                ],

                // ── ZONE 3: RATIONALE ──
                Text(cio['rationale']?.toString() ?? cio['executive_summary']?.toString() ?? '',
                  style: AppTextStyles.bodySmall(c.t2), maxLines: 4, overflow: TextOverflow.ellipsis),
                const SizedBox(height: 10),

                // Bull / Bear / Risk — separate boxes
                Row(children: [
                  if (cio['bull_case'] != null) Expanded(child: Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: c.up.withValues(alpha: 0.04), borderRadius: BorderRadius.circular(6),
                      border: Border(left: BorderSide(color: c.up, width: 2))),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Row(children: [
                        Icon(LucideIcons.trendingUp, size: 11, color: c.up),
                        const SizedBox(width: 4),
                        Text('BULL', style: AppTextStyles.labelXs(c.up).copyWith(fontSize: 9)),
                      ]),
                      const SizedBox(height: 4),
                      Text(cio['bull_case'].toString(), style: AppTextStyles.captionXs(c.t2),
                        maxLines: 2, overflow: TextOverflow.ellipsis),
                    ]),
                  )),
                  if (cio['bull_case'] != null && cio['bear_case'] != null) const SizedBox(width: 8),
                  if (cio['bear_case'] != null) Expanded(child: Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: c.dn.withValues(alpha: 0.04), borderRadius: BorderRadius.circular(6),
                      border: Border(left: BorderSide(color: c.dn, width: 2))),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Row(children: [
                        Icon(LucideIcons.trendingDown, size: 11, color: c.dn),
                        const SizedBox(width: 4),
                        Text('BEAR', style: AppTextStyles.labelXs(c.dn).copyWith(fontSize: 9)),
                      ]),
                      const SizedBox(height: 4),
                      Text(cio['bear_case'].toString(), style: AppTextStyles.captionXs(c.t2),
                        maxLines: 2, overflow: TextOverflow.ellipsis),
                    ]),
                  )),
                  if (cio['key_risk'] != null) ...[
                    const SizedBox(width: 8),
                    Expanded(child: Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: c.gold.withValues(alpha: 0.04), borderRadius: BorderRadius.circular(6),
                        border: Border(left: BorderSide(color: c.gold, width: 2))),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Row(children: [
                          Icon(LucideIcons.alertTriangle, size: 11, color: c.gold),
                          const SizedBox(width: 4),
                          Text('KEY RISK', style: AppTextStyles.labelXs(c.gold).copyWith(fontSize: 9)),
                        ]),
                        const SizedBox(height: 4),
                        Text(cio['key_risk'].toString(), style: AppTextStyles.captionXs(c.t3),
                          maxLines: 2, overflow: TextOverflow.ellipsis),
                      ]),
                    )),
                  ],
                ]),
              ]),
            ),
          ]),
        ),
      ),
      const SizedBox(height: 12),

      // ═══════════════════════════════════════════════════
      //  ROW 2: RADAR CHART + RECOMMENDED ALLOCATION
      // ═══════════════════════════════════════════════════
      AnimatedListItem(
        index: 2,
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          // Radar Chart
          Expanded(flex: 3, child: DenseCard(
            clip: true,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              denseTableHeader(context,
                  icon: LucideIcons.hexagon,
                  accent: c.accent,
                  title: 'Agent Score Radar',
                  subtitle: 'each axis = agent score (0–10) · larger area = stronger conviction',
                  trailing: Text('${radarScores.length} dimensions',
                      style: AppTextStyles.monoXs(c.t3))),
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
                child: AgentRadarChart(scores: radarScores),
              ),
            ]),
          )),
          const SizedBox(width: 12),
          // Recommended Allocation
          Expanded(flex: 2, child: DenseCard(
            clip: true,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              denseTableHeader(context,
                  icon: LucideIcons.target,
                  accent: c.accent,
                  title: 'Allocation Advice',
                  subtitle: 'suggested position sizing'),
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 2, 14, 14),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  // Parse allocation — extract number if present, otherwise show as text
                  ...(() {
                    final raw = e['position_size_recommendation']?.toString() ?? '3-5%';
                    // Try to extract a percentage number
                    final pctMatch = RegExp(r'(\d+(?:\.\d+)?)\s*%').firstMatch(raw);
                    final pctVal = pctMatch?.group(1) ?? '';
                    // Clean the rest as explanation
                    final explanation = raw.replaceAll(RegExp(r'^\d+(?:\.\d+)?\s*%\s*'), '').replaceAll(RegExp(r'^\(|\)$'), '').trim();

                    return <Widget>[
                      Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                        Text(pctVal.isEmpty ? '—' : '$pctVal%',
                            style: AppTextStyles.monoBold(c.accent).copyWith(fontSize: 22)),
                        const SizedBox(width: 6),
                        Padding(padding: const EdgeInsets.only(bottom: 3),
                          child: Text('of portfolio', style: AppTextStyles.captionXs(c.t4))),
                      ]),
                      if (explanation.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Text(explanation, style: AppTextStyles.bodySmall(c.t3), maxLines: 2, overflow: TextOverflow.ellipsis),
                      ],
                    ];
                  })(),
                  const SizedBox(height: 12),
                  // Risk + Horizon chips
                  Row(children: [
                    Expanded(child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      decoration: BoxDecoration(color: c.bg3, borderRadius: BorderRadius.circular(6), border: Border.all(color: c.bd)),
                      child: Column(children: [
                        Text('RISK', style: AppTextStyles.labelXs(c.t3)),
                        const SizedBox(height: 3),
                        Text(ri['risk_level']?.toString() ?? '—',
                            style: AppTextStyles.monoBold(_verdictColor(ri['risk_level']?.toString()))
                                .copyWith(fontSize: 12)),
                      ]),
                    )),
                    const SizedBox(width: 8),
                    Expanded(child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      decoration: BoxDecoration(color: c.bg3, borderRadius: BorderRadius.circular(6), border: Border.all(color: c.bd)),
                      child: Column(children: [
                        Text('HORIZON', style: AppTextStyles.labelXs(c.t3)),
                        const SizedBox(height: 3),
                        Text(cio['investment_horizon']?.toString() ?? '—',
                            style: AppTextStyles.monoBold(c.blue).copyWith(fontSize: 11)),
                      ]),
                    )),
                  ]),
                  // Entry strategy
                  if (e['entry_strategy'] != null) ...[
                    const SizedBox(height: 10),
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(color: c.bg3, borderRadius: BorderRadius.circular(6),
                        border: Border(left: BorderSide(color: c.accent, width: 2))),
                      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Icon(LucideIcons.crosshair, size: 11, color: c.accent),
                        const SizedBox(width: 6),
                        Expanded(child: Text(e['entry_strategy'].toString(),
                          style: AppTextStyles.bodySmall(c.t2), maxLines: 2, overflow: TextOverflow.ellipsis)),
                      ]),
                    ),
                  ],
                ]),
              ),
            ]),
          )),
        ]),
      ),
      const SizedBox(height: 12),

      // ═══════════════════════════════════════════════════
      //  ROW 3: FUNDAMENTAL + TECHNICAL + QUANT
      // ═══════════════════════════════════════════════════
      AnimatedListItem(
        index: 3,
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          // Fundamental Agent
          Expanded(child: EnhancedAgentCard(
            title: 'Fundamental Agent',
            icon: LucideIcons.pieChart,
            accentColor: c.up,
            verdict: f['valuation_assessment']?.toString() ?? f['verdict']?.toString(),
            score: (f['score'] is num) ? (f['score'] as num).toDouble() : null,
            keyInsight: f['key_insight']?.toString(),
            tooltip: 'Analyzes the company\'s financial health: earnings quality, balance sheet strength, profitability ratios (ROE, ROCE), debt levels, and revenue growth trends.',
            visualization: ValuationGauge(assessment: f['valuation_assessment']?.toString()),
            metrics: [
              MetricRow(label: 'P/E Ratio', value: f['pe_ratio']),
              MetricRow(label: 'P/B Ratio', value: f['pb_ratio']),
              MetricRow(label: 'ROE', value: f['roe'], valueColor: _verdictColor(f['roe']?.toString())),
              MetricRow(label: 'ROCE', value: _fmtPct(f['roce']), valueColor: _verdictColor(f['roce']?.toString())),
              MetricRow(label: 'ROA', value: _fmtPct(f['roa']), valueColor: _verdictColor(f['roa']?.toString())),
              MetricRow(label: 'Debt/Equity', value: f['debt_to_equity']),
              const SizedBox(height: 4),
              MetricRow(label: _revenueCagrLabel(f), value: _revenueCagrValue(f), valueColor: _verdictColor(_revenueCagrValue(f))),
              MetricRow(label: 'Revenue Growth', value: f['revenue_growth'], valueColor: _verdictColor(f['revenue_growth']?.toString())),
              MetricRow(label: 'EPS Trend', value: f['eps_trend'], valueColor: _verdictColor(f['eps_trend']?.toString())),
              MetricRow(label: 'Altman Z-Score', value: _altmanValue(f), valueColor: _altmanApplicable(f) ? _verdictColor(f['altman_zone']?.toString()) : null),
              if (f['dupont_roe_driver'] != null) MetricRow(label: 'ROE Driver', value: f['dupont_roe_driver']?.toString(), valueColor: _verdictColor(f['dupont_roe_driver']?.toString())),
              if (f['interest_coverage'] != null) MetricRow(label: 'Interest Coverage', value: '${f['interest_coverage']}x'),
            ],
          )),
          const SizedBox(width: 12),
          // Technical Agent
          Expanded(child: EnhancedAgentCard(
            title: 'Technical Agent',
            icon: LucideIcons.trendingUp,
            accentColor: c.blue,
            verdict: t['trend']?.toString() ?? t['verdict']?.toString(),
            score: (t['score'] is num) ? (t['score'] as num).toDouble() : null,
            keyInsight: t['key_insight']?.toString(),
            tooltip: 'Computes technical indicators: RSI (momentum), MACD (trend), Bollinger Bands (volatility), and identifies key support/resistance price levels.',
            metrics: [
              MetricRow(label: 'Trend', value: t['trend'], valueColor: _verdictColor(t['trend']?.toString())),
              MetricRow(label: 'Momentum', value: t['momentum'], valueColor: _verdictColor(t['momentum']?.toString())),
              MetricRow(label: 'Support', value: t['support_level'] != null ? '₹${t['support_level']}' : null, valueColor: c.up),
              MetricRow(label: 'Resistance', value: t['resistance_level'] != null ? '₹${t['resistance_level']}' : null, valueColor: c.dn),
              if (t['rsi'] != null) MetricRow(label: 'RSI', value: t['rsi']),
              if (t['macd_signal'] != null) MetricRow(label: 'MACD Signal', value: t['macd_signal']),
              if (t['adx'] != null) MetricRow(label: 'ADX (Trend)', value: '${t['adx']} — ${t['adx_signal'] ?? ''}', valueColor: _verdictColor(t['adx_signal']?.toString())),
              if (t['stochastic_k'] != null) MetricRow(label: 'Stochastic', value: '%K=${t['stochastic_k']} (${t['stochastic_signal'] ?? ''})', valueColor: _verdictColor(t['stochastic_signal']?.toString())),
              if (t['ichimoku_status'] != null) MetricRow(label: 'Ichimoku', value: t['ichimoku_status']?.toString(), valueColor: _verdictColor(t['ichimoku_status']?.toString())),
              if (t['fib_618'] != null) MetricRow(label: 'Fib 61.8%', value: '₹${t['fib_618']}', valueColor: c.gold),
            ],
          )),
          const SizedBox(width: 12),
          // Quant Agent
          Expanded(child: EnhancedAgentCard(
            title: 'Quant Agent',
            icon: LucideIcons.calculator,
            accentColor: c.accent,
            verdict: q['verdict']?.toString(),
            score: (q['score'] is num) ? (q['score'] as num).toDouble() : null,
            keyInsight: q['key_insight']?.toString(),
            tooltip: 'Runs quantitative valuation models: Discounted Cash Flow (DCF) for intrinsic value, Graham Number for margin of safety, and PEG Ratio for growth-adjusted valuation.',
            visualization: DCFComparisonBar(
              currentPrice: currentPrice,
              dcfValue: (q['dcf_intrinsic_value'] is num) ? (q['dcf_intrinsic_value'] as num).toDouble() : null,
              grahamValue: (q['graham_number'] is num) ? (q['graham_number'] as num).toDouble() : null,
            ),
            metrics: [
              if (q['peg_ratio'] != null) MetricRow(
                label: q['peg_source'] == 'computed'
                    ? 'PEG Ratio (est.)'
                    : 'PEG Ratio',
                value: q['peg_ratio']),
              if (q['fcf_yield_pct'] != null) MetricRow(label: 'FCF Yield', value: '${q['fcf_yield_pct']}%', valueColor: _verdictColor(q['fcf_yield_pct'] is num && (q['fcf_yield_pct'] as num) > 5 ? 'Bullish' : 'Neutral')),
              if (q['ev_revenue'] != null) MetricRow(label: 'EV/Revenue', value: '${q['ev_revenue']}'),
              if (q['undervalue_consensus'] != null) MetricRow(label: 'Model Consensus', value: '${q['undervalue_consensus']} undervalued', valueColor: c.accent),
              MetricRow(label: 'Quant Score', value: q['score'] != null ? '${q['score']}/10' : null, valueColor: c.accent),
            ],
          )),
        ]),
      ),
      const SizedBox(height: 12),

      // ═══════════════════════════════════════════════════
      //  ROW 4: SENTIMENT + MACRO + RISK
      // ═══════════════════════════════════════════════════
      AnimatedListItem(
        index: 4,
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          // Sentiment Agent
          Expanded(child: EnhancedAgentCard(
            title: 'Sentiment Agent',
            icon: LucideIcons.newspaper,
            accentColor: c.gold,
            verdict: n['sentiment']?.toString() ?? n['verdict']?.toString(),
            score: (n['score'] is num) ? (n['score'] as num).toDouble() : null,
            keyInsight: n['key_insight']?.toString(),
            tooltip: 'Processes recent news articles, social media mentions, and market buzz to determine overall market sentiment for this stock. Positive sentiment often precedes price increases.',
            visualization: SentimentArc(sentiment: n['sentiment']?.toString(), score: (n['score'] is num) ? (n['score'] as num).toDouble() : null),
            metrics: [
              MetricRow(label: 'Sentiment', value: n['sentiment'], valueColor: _verdictColor(n['sentiment']?.toString())),
              MetricRow(label: 'Score', value: n['score'] != null ? '${n['score']}/10' : null),
              if (n['target_upside_pct'] != null) MetricRow(label: 'Target Upside', value: '${n['target_upside_pct']}%', valueColor: _verdictColor('${n['target_upside_pct']}')),
              if (n['target_dispersion_pct'] != null) MetricRow(label: 'Analyst Dispersion', value: '${n['target_dispersion_pct']}% spread'),
            ],
          )),
          const SizedBox(width: 12),
          // Macro Agent
          Expanded(child: EnhancedAgentCard(
            title: 'Macro Agent',
            icon: LucideIcons.globe,
            accentColor: c.cyan,
            verdict: m['sector_outlook']?.toString() ?? m['verdict']?.toString(),
            score: (m['score'] is num) ? (m['score'] as num).toDouble() : null,
            keyInsight: m['key_insight']?.toString(),
            tooltip: 'Evaluates macroeconomic factors: sector-wide trends, interest rate sensitivity, government policy impacts, and broader market conditions that affect this stock.',
            metrics: [
              MetricRow(label: 'Sector Outlook', value: m['sector_outlook'], valueColor: _verdictColor(m['sector_outlook']?.toString())),
              MetricRow(label: 'Rate Sensitivity', value: m['interest_rate_sensitivity'], valueColor: _verdictColor(m['interest_rate_sensitivity']?.toString())),
              if (m['currency_impact'] != null) MetricRow(label: 'Currency Impact', value: m['currency_impact']?.toString(), valueColor: _verdictColor(m['currency_impact']?.toString())),
              if (m['sector_cycle_position'] != null) MetricRow(label: 'Cycle Position', value: m['sector_cycle_position']?.toString()),
              MetricRow(label: 'Macro Score', value: m['score'] != null ? '${m['score']}/10' : null, valueColor: c.cyan),
            ],
          )),
          const SizedBox(width: 12),
          // Risk Agent
          Expanded(child: EnhancedAgentCard(
            title: 'Risk Agent',
            icon: LucideIcons.shieldAlert,
            accentColor: c.dn,
            verdict: ri['risk_level']?.toString() ?? ri['verdict']?.toString(),
            score: (ri['score'] is num) ? (ri['score'] as num).toDouble() : null,
            keyInsight: ri['key_insight']?.toString(),
            tooltip: 'Assesses investment risk: portfolio volatility impact, maximum potential drawdown, correlation risk, and liquidity risk. Lower risk levels indicate safer investments.',
            visualization: RiskMeter(
              riskLevel: ri['risk_level']?.toString(),
              maxDrawdown: (ri['max_drawdown_estimate_pct'] is num) ? (ri['max_drawdown_estimate_pct'] as num).toDouble() : null,
            ),
            metrics: [
              MetricRow(label: 'Risk Level', value: ri['risk_level'], valueColor: _verdictColor(ri['risk_level']?.toString())),
              MetricRow(label: 'Volatility', value: ri['volatility_profile'], valueColor: _verdictColor(ri['volatility_profile']?.toString())),
              if (ri['sharpe_ratio'] != null) MetricRow(label: 'Sharpe Ratio', value: '${ri['sharpe_ratio']} (${ri['sharpe_rating'] ?? ''})', valueColor: _verdictColor(ri['sharpe_rating']?.toString())),
              if (ri['sortino_ratio'] != null) MetricRow(label: 'Sortino Ratio', value: '${ri['sortino_ratio']}'),
              if (ri['liquidity_turnover_cr'] != null) MetricRow(label: 'Daily Turnover', value: '₹${ri['liquidity_turnover_cr']} Cr'),
            ],
          )),
        ]),
      ),
    ]);
  }

  Widget _positionChip(AppColorScheme c, String label, String value, Color valueColor) => Expanded(
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(color: c.bg2, borderRadius: BorderRadius.circular(6), border: Border.all(color: c.bd)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.center, children: [
        Text(label.toUpperCase(), style: AppTextStyles.labelXs(c.t4).copyWith(fontSize: 8)),
        const SizedBox(height: 2),
        FittedBox(fit: BoxFit.scaleDown, child: Text(value,
            style: AppTextStyles.monoBold(valueColor).copyWith(fontSize: 11))),
      ]),
    ),
  );

  Widget _actionStep(AppColorScheme c, String text, Color color,
          {IconData icon = LucideIcons.chevronRight}) =>
      Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Padding(
            padding: const EdgeInsets.only(top: 2, right: 8),
            child: Icon(icon, size: 12, color: color),
          ),
          Expanded(child: Text(text, style: AppTextStyles.bodySmall(c.t1))),
        ]),
      );
}
