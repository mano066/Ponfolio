import 'package:dio/dio.dart';
import 'package:logger/logger.dart';
import '../core/constants.dart';

/// Singleton Dio client with interceptors for the FastAPI backend.
class ApiService {
  static final ApiService _instance = ApiService._internal();
  factory ApiService() => _instance;
  ApiService._internal();

  final _log = Logger(printer: PrettyPrinter(methodCount: 0));

  late final Dio dio = _buildDio();

  Dio _buildDio() {
    final d = Dio(
      BaseOptions(
        baseUrl: AppConstants.apiBase,
        connectTimeout: const Duration(
          milliseconds: AppConstants.connectTimeoutMs,
        ),
        receiveTimeout: const Duration(
          milliseconds: AppConstants.receiveTimeoutMs,
        ),
        headers: {'Content-Type': 'application/json'},
      ),
    );
    d.interceptors.addAll([
      InterceptorsWrapper(
        onRequest: (options, handler) {
          _log.d('→ ${options.method} ${options.path}');
          handler.next(options);
        },
        onError: (error, handler) {
          _log.e('API request failed: ${error.type.name}; HTTP ${error.response?.statusCode ?? 'unavailable'}');
          handler.next(error);
        },
      ),
      // Transparently retries idempotent GETs on transient connection drops
      // (e.g. "Connection closed before full header was received" from stale
      //  keep-alive sockets when the app fires a burst of requests on load).
      _RetryInterceptor(d, _log),
    ]);
    return d;
  }

  /// Cheap liveness check for the login screen. /api/status does no blocking
  /// work, so it answers even while price fetches are slow.
  Future<void> ping() async {
    await dio.get(
      '/status',
      options: Options(receiveTimeout: const Duration(seconds: 5)),
    );
  }

  // ══════════════════════════════════════════
  //  PORTFOLIO
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> getPortfolio() async {
    final r = await dio.get('/portfolio/default');
    return r.data as Map<String, dynamic>;
  }

  /// Annualised return for equity, MF, and the two combined. The combined
  /// figure pools both sets of cashflows server-side — blending two rates
  /// client-side would not be a real XIRR.
  Future<Map<String, dynamic>> getPortfolioXirr() async {
    final r = await dio.get('/portfolio/xirr');
    return r.data as Map<String, dynamic>;
  }

  /// Per-holding diagnosis of why an XIRR is exact, approximate, or missing.
  Future<Map<String, dynamic>> getXirrCoverage() async {
    final r = await dio.get('/portfolio/xirr-coverage');
    return r.data as Map<String, dynamic>;
  }

  /// Saved BUY/SELL ledger for one equity, including execution metadata.
  Future<Map<String, dynamic>> getEquityTransactions(String symbol) async {
    final r = await dio.get(
      '/portfolio/transactions',
      queryParameters: {'symbol': symbol},
    );
    return Map<String, dynamic>.from(r.data as Map);
  }

  /// Realised P&L on sold shares, FIFO-matched from the dated ledger.
  ///
  /// Charges and tax in the payload are computed, not billed — the response
  /// carries its own bases and the UI labels them as estimates.
  Future<Map<String, dynamic>> getClosedPositions() async {
    final r = await dio.get('/portfolio/closed-positions');
    return Map<String, dynamic>.from(r.data as Map);
  }

  /// Force a Kite tradebook pull into the dated equity ledger.
  Future<Map<String, dynamic>> syncKiteTrades() async {
    final r = await dio.post('/kite/sync-trades');
    return r.data as Map<String, dynamic>;
  }

  /// Import a Zerodha Console tradebook without parsing it on the client.
  ///
  /// The backend owns validation, symbol canonicalisation, de-duplication and
  /// reconciliation so desktop and future clients all get identical results.
  Future<Map<String, dynamic>> importTradebook(
    String path, {
    String? filename,
  }) async {
    final form = FormData.fromMap({
      'file': await MultipartFile.fromFile(path, filename: filename),
    });
    final r = await dio.post(
      '/portfolio/import-tradebook',
      data: form,
      options: Options(
        contentType: 'multipart/form-data',
        receiveTimeout: const Duration(minutes: 2),
      ),
    );
    return Map<String, dynamic>.from(r.data as Map);
  }

  /// Upload one period's Kite Console P&L statement (.xlsx).
  ///
  /// Filed by the period in its title, so a month re-uploaded replaces itself
  /// instead of doubling the realised figure.
  Future<Map<String, dynamic>> importKitePnl(
    String path, {
    String? filename,
  }) async {
    final form = FormData.fromMap({
      'file': await MultipartFile.fromFile(path, filename: filename),
    });
    final r = await dio.post(
      '/portfolio/import-kite-pnl',
      data: form,
      options: Options(
        contentType: 'multipart/form-data',
        receiveTimeout: const Duration(minutes: 2),
      ),
    );
    return Map<String, dynamic>.from(r.data as Map);
  }

  /// Upload one period's Kite Console funds ledger (.xlsx).
  ///
  /// The only export carrying TDS. Filed by period like the P&L statement.
  Future<Map<String, dynamic>> importKiteLedger(
    String path, {
    String? filename,
  }) async {
    final form = FormData.fromMap({
      'file': await MultipartFile.fromFile(path, filename: filename),
    });
    final r = await dio.post(
      '/portfolio/import-kite-ledger',
      data: form,
      options: Options(
        contentType: 'multipart/form-data',
        receiveTimeout: const Duration(minutes: 2),
      ),
    );
    return Map<String, dynamic>.from(r.data as Map);
  }

  /// TDS and fund movements across every imported ledger period.
  Future<Map<String, dynamic>> getLedgerEntries() async {
    final r = await dio.get('/portfolio/ledger-entries');
    return Map<String, dynamic>.from(r.data as Map);
  }

  /// Which P&L periods are held, and what they sum to.
  Future<Map<String, dynamic>> getPnlStatements() async {
    final r = await dio.get('/portfolio/pnl-statements');
    return Map<String, dynamic>.from(r.data as Map);
  }

  /// Drop one imported period — the way out of an overlapping import.
  Future<Map<String, dynamic>> deletePnlStatement(String period) async {
    final r = await dio.delete('/portfolio/pnl-statements/$period');
    return Map<String, dynamic>.from(r.data as Map);
  }

  Future<Map<String, dynamic>> getLivePrices() async {
    final r = await dio.get('/portfolio/live-prices');
    return r.data as Map<String, dynamic>;
  }

  Future<void> addStock(
    String symbol,
    int shares, {
    double avgCost = 0.0,
  }) async {
    await dio.post(
      '/portfolio/add',
      data: {'symbol': symbol, 'shares': shares, 'avg_cost': avgCost},
    );
  }

  Future<void> deleteStock(String symbol) async {
    await dio.delete('/portfolio/$symbol');
  }

  // ══════════════════════════════════════════
  //  WATCHLIST
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> getWatchlist() async {
    final r = await dio.get('/portfolio/watchlist');
    return r.data as Map<String, dynamic>;
  }

  Future<void> addToWatchlist(String symbol) async {
    await dio.post('/portfolio/watchlist', data: {'symbol': symbol});
  }

  Future<void> removeFromWatchlist(String symbol) async {
    await dio.delete('/portfolio/watchlist/$symbol');
  }

  // ══════════════════════════════════════════
  //  CONVICTION & POSITION SIZE
  // ══════════════════════════════════════════
  /// Every holding and watchlist name judged on the business, the written
  /// thesis and the position size — never on the price or the average cost.
  Future<Map<String, dynamic>> getConvictionBoard() async {
    final r = await dio.get('/conviction/board');
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> saveThesis(
      String symbol, Map<String, dynamic> thesis) async {
    final r = await dio.put('/conviction/thesis/$symbol', data: thesis);
    return r.data as Map<String, dynamic>;
  }

  Future<void> deleteThesis(String symbol) async {
    await dio.delete('/conviction/thesis/$symbol');
  }

  /// Your own verdict on a quarter: 'met', 'missed', or 'clear'.
  Future<void> setQuarterResult(String symbol, String quarter, String result,
      {String note = ''}) async {
    await dio.put('/conviction/result/$symbol',
        data: {'quarter': quarter, 'result': result, 'note': note});
  }

  Future<Map<String, dynamic>> saveConvictionSettings(
      Map<String, dynamic> settings) async {
    final r = await dio.put('/conviction/settings', data: settings);
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  DEEP ANALYSIS (async job-based)
  // ══════════════════════════════════════════

  /// Start analysis in background, returns {job_id, status: "running"} instantly.
  Future<Map<String, dynamic>> startDeepAnalysis(String symbol) async {
    final r = await dio.post('/stock/$symbol/deep-analysis/start');
    return r.data as Map<String, dynamic>;
  }

  /// Poll for job progress: current_agent, agents_done[], status, result when done.
  Future<Map<String, dynamic>> getDeepAnalysisStatus(String jobId) async {
    final r = await dio.get('/deep-analysis/status/$jobId');
    return r.data as Map<String, dynamic>;
  }

  /// Legacy synchronous call (may timeout on slow systems).
  Future<Map<String, dynamic>> getDeepAnalysis(String symbol) async {
    final r = await dio.get('/stock/$symbol/deep-analysis');
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getStockNews(String symbol) async {
    final r = await dio.get('/stock/$symbol/news');
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  AI SIGNALS
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> getDeepSignals() async {
    final r = await dio.get('/deep-signals');
    return r.data as Map<String, dynamic>;
  }

  Future<void> startDeepSignals() async {
    await dio.post('/deep-signals/start');
  }

  // ══════════════════════════════════════════
  //  AI ADVISOR / CHAT
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> getAdvisor() async {
    final r = await dio.get('/advisor');
    return r.data as Map<String, dynamic>;
  }

  Future<void> startAdvisor() async {
    await dio.post('/advisor/start');
  }

  Future<Map<String, dynamic>> chat(
    String message,
    List<Map<String, String>> history,
  ) async {
    final r = await dio.post(
      '/chat',
      data: {'message': message, 'history': history},
    );
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  ANALYTICS
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> getAnalytics() async {
    final r = await dio.get('/analytics/portfolio');
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  MUTUAL FUNDS
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> getMFPortfolio() async {
    final r = await dio.get('/mf-portfolio');
    return r.data as Map<String, dynamic>;
  }

  Future<void> addMFTransaction(Map<String, dynamic> data) async {
    await dio.post('/mf-portfolio/transaction', data: data);
  }

  Future<void> updateMFTransaction(Map<String, dynamic> data) async {
    await dio.put('/mf-portfolio/transaction', data: data);
  }

  Future<void> deleteMFTransaction(Map<String, dynamic> data) async {
    await dio.delete('/mf-portfolio/transaction', data: data);
  }

  Future<void> addMFFund(Map<String, dynamic> data) async {
    await dio.post('/mf-portfolio/fund', data: data);
  }

  Future<void> deleteMFFund(Map<String, dynamic> data) async {
    await dio.delete('/mf-portfolio/fund', data: data);
  }

  Future<void> refreshMFNav() async {
    await dio.post('/mf-portfolio/refresh-nav');
  }

  Future<Map<String, dynamic>> searchMFFund(String query) async {
    final r = await dio.get(
      '/mf-portfolio/search-fund',
      queryParameters: {'q': query},
    );
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> analyzeMFPortfolio() async {
    final r = await dio.get('/mf-portfolio/analyze');
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  MF ANALYSIS / SCREENER
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> searchMFAnalysis(String query) async {
    final r = await dio.get(
      '/mf-analysis/search',
      queryParameters: {'q': query},
    );
    return r.data as Map<String, dynamic>;
  }

  Future<void> startMFAnalysis({
    required String category,
    required List<int> schemeCodes,
  }) async {
    await dio.post(
      '/mf-analysis/start',
      data: {'category': category, 'scheme_codes': schemeCodes},
    );
  }

  Future<Map<String, dynamic>> getMFAnalysisStatus() async {
    final r = await dio.get('/mf-analysis/status');
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  SIP SIMULATOR
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> searchSIPInstruments(String query) async {
    final r = await dio.get('/sip/search', queryParameters: {'q': query});
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> simulateSIP({
    required List<Map<String, dynamic>> symbols,
    required String startDate,
    int sipDay = 1,
    double stepUpPct = 0,
    List<Map<String, dynamic>>? customEntries,
  }) async {
    final data = <String, dynamic>{
      'symbols': symbols,
      'start_date': startDate,
      'sip_day': sipDay,
      'step_up_pct': stepUpPct,
    };
    if (customEntries != null && customEntries.isNotEmpty) {
      data['custom_entries'] = customEntries;
    }
    final r = await dio.post('/sip/simulate', data: data);
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> myPortfolioSIP() async {
    final r = await dio.get('/sip/my-portfolio');
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  REPORTS
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> getWealthReport() async {
    final r = await dio.get('/report/wealth');
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  AUTH
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> getProfile() async {
    final r = await dio.get('/auth/profile');
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getGoogleAuthUrl() async {
    final r = await dio.get('/auth/google/url');
    return r.data as Map<String, dynamic>;
  }

  Future<void> logout() async {
    await dio.post('/auth/logout');
  }

  // ══════════════════════════════════════════
  //  DRIVE SYNC
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> driveSync(String direction) async {
    final r = await dio.post(
      '/drive/sync',
      queryParameters: {'direction': direction},
    );
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getDriveStatus() async {
    final r = await dio.get('/drive/status');
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  SETTINGS
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> getSettings() async {
    final r = await dio.get('/settings');
    return r.data as Map<String, dynamic>;
  }

  Future<void> updateSettings(Map<String, dynamic> data) async {
    await dio.put('/settings', data: data);
  }

  Future<Map<String, dynamic>> getOllamaModels() async {
    final r = await dio.get('/settings/ollama-models');
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> testOllama() async {
    final r = await dio.post('/settings/test-ollama');
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  REBALANCING
  // ══════════════════════════════════════════
  /// The plan, built from the saved policy with optional overrides.
  ///
  /// [minWeightPct]/[maxWeightPct]/[deviationPct]/[mode] are previews: the
  /// backend applies them for this one request without saving, so a slider can
  /// be dragged and its effect read off the plan before it is committed.
  ///
  /// [manualGold] and [manualDebt] are the amounts the user tracks by hand on
  /// the allocation screen. They live in local storage, so they have to travel
  /// with every request — left out, every other category reads heavier than it
  /// really is.
  /// The tradebook replayed as one ledger page per date traded.
  ///
  /// Slow on a cold cache — it pulls a year of daily closes per holding — so
  /// callers should treat it as a section that loads, not as part of the plan.
  Future<Map<String, dynamic>> getRebalanceHistory() async {
    final r = await dio.get('/portfolio/rebalance/history');
    return Map<String, dynamic>.from(r.data as Map);
  }

  Future<Map<String, dynamic>> getRebalancePlan({
    String? cadence,
    String residency = 'resident',
    double? minWeightPct,
    double? maxWeightPct,
    double? deviationPct,
    String? mode,
    String? strategy,
    double manualGold = 0,
    double manualDebt = 0,
    double newMoney = 0,
    bool force = false,
  }) async {
    final r = await dio.get('/portfolio/rebalance', queryParameters: {
      if (cadence != null) 'cadence': cadence,
      'residency': residency,
      if (minWeightPct != null) 'min_weight_pct': minWeightPct,
      if (maxWeightPct != null) 'max_weight_pct': maxWeightPct,
      if (deviationPct != null) 'deviation_pct': deviationPct,
      if (mode != null) 'mode': mode,
      if (strategy != null) 'strategy': strategy,
      if (newMoney > 0) 'new_money': newMoney,
      if (manualGold > 0) 'manual_gold': manualGold,
      if (manualDebt > 0) 'manual_debt': manualDebt,
      if (force) 'force': true,
    });
    return r.data as Map<String, dynamic>;
  }

  /// The selectable rebalancing presets (S1–S10, the master, and Custom),
  /// each with what it measured in the 2011–2026 backtest.
  Future<Map<String, dynamic>> getRebalanceStrategies() async {
    final r = await dio.get('/portfolio/rebalance/strategies');
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getRebalanceSettings() async {
    final r = await dio.get('/portfolio/rebalance/settings');
    return r.data as Map<String, dynamic>;
  }

  /// Save part of the rebalance policy. Only what is passed is written.
  ///
  /// The `clear*` flags exist because null already means "leave this alone" on
  /// a partial update, so unsetting a custom threshold or a selection needs to
  /// be sayable in its own right.
  Future<Map<String, dynamic>> saveRebalanceSettings({
    Map<String, double>? taxRates,
    Map<String, double>? assetLimits,
    bool? longTermOnly,
    double? minWeightPct,
    double? maxWeightPct,
    double? deviationPct,
    String? cadence,
    List<String>? triggers,
    double? boomGainPct,
    double? crashDropPct,
    double? gainTriggerPct,
    double? lossTriggerPct,
    double? volTriggerPct,
    Map<String, double>? categoryTargets,
    String? mode,
    String? strategy,
    List<String>? selectedCategories,
    List<String>? selectedAssets,
    bool clearSelectedCategories = false,
    bool clearSelectedAssets = false,
    bool clearGainTrigger = false,
    bool clearLossTrigger = false,
  }) async {
    final r = await dio.put('/portfolio/rebalance/settings', data: {
      if (taxRates != null) 'tax_rates': taxRates,
      if (assetLimits != null) 'asset_limits': assetLimits,
      if (longTermOnly != null) 'long_term_only': longTermOnly,
      if (minWeightPct != null) 'min_weight_pct': minWeightPct,
      if (maxWeightPct != null) 'max_weight_pct': maxWeightPct,
      if (deviationPct != null) 'deviation_pct': deviationPct,
      if (cadence != null) 'cadence': cadence,
      if (triggers != null) 'triggers': triggers,
      if (boomGainPct != null) 'boom_gain_pct': boomGainPct,
      if (crashDropPct != null) 'crash_drop_pct': crashDropPct,
      if (gainTriggerPct != null) 'gain_trigger_pct': gainTriggerPct,
      if (lossTriggerPct != null) 'loss_trigger_pct': lossTriggerPct,
      if (volTriggerPct != null) 'vol_trigger_pct': volTriggerPct,
      if (categoryTargets != null) 'category_targets': categoryTargets,
      if (mode != null) 'mode': mode,
      if (strategy != null) 'strategy': strategy,
      if (selectedCategories != null) 'selected_categories': selectedCategories,
      if (selectedAssets != null) 'selected_assets': selectedAssets,
      if (clearSelectedCategories) 'clear_selected_categories': true,
      if (clearSelectedAssets) 'clear_selected_assets': true,
      if (clearGainTrigger) 'clear_gain_trigger': true,
      if (clearLossTrigger) 'clear_loss_trigger': true,
    });
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> markRebalanceDone({String? date}) async {
    final r = await dio.post('/portfolio/rebalance/mark-done',
        data: {if (date != null) 'date': date});
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  KITE TRADING ENGINE
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> getKiteStatus() async {
    final r = await dio.get('/kite/status');
    return r.data as Map<String, dynamic>;
  }

  /// Throw away the current MCP session and negotiate a clean one.
  ///
  /// Not a logout: the intent to be connected is kept. This is for the case
  /// the backend's automatic recovery cannot fix on its own — a server-side
  /// session that is gone for good, where every resume attempt is refused the
  /// same way and only starting over helps.
  Future<Map<String, dynamic>> reconnectKite() async {
    final r = await dio.post('/kite/reconnect');
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getKiteLoginUrl() async {
    final r = await dio.get('/kite/login');
    return r.data as Map<String, dynamic>;
  }

  Future<void> kiteLogout() async {
    await dio.post('/kite/logout');
  }

  Future<Map<String, dynamic>> kiteSync() async {
    final r = await dio.post('/kite/sync');
    return r.data as Map<String, dynamic>;
  }

  /// Is the Kite session authenticated?
  ///
  /// `syncHoldings: false` skips the portfolio pull, which is what a login
  /// poller wants — it asks every two seconds and only needs the holdings on
  /// the one tick that finally says yes.
  Future<Map<String, dynamic>> kiteCheck({bool syncHoldings = true}) async {
    final r = await dio.post('/kite/check',
        queryParameters: syncHoldings ? null : {'sync_holdings': false});
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  MARKET
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> getNifty50() async {
    final r = await dio.get('/market/nifty50');
    return r.data as Map<String, dynamic>;
  }

  /// Search all NSE/BSE stocks by name or symbol.
  Future<List<Map<String, dynamic>>> searchStocks(String query) async {
    final r = await dio.get('/search', queryParameters: {'q': query});
    return List<Map<String, dynamic>>.from(r.data['results'] ?? []);
  }

  /// Fetch top market movers (gainers & losers).
  Future<Map<String, dynamic>> getMarketMovers() async {
    final r = await dio.get('/market/movers');
    return r.data as Map<String, dynamic>;
  }

  /// Fetch AI top buy picks from deep analysis.
  Future<Map<String, dynamic>> getAITopPicks() async {
    final r = await dio.get('/deep-signals/top-picks');
    return r.data as Map<String, dynamic>;
  }

  /// Fetch live Nifty 50 constituents with per-stock price & day change.
  Future<Map<String, dynamic>> getNifty50Constituents() async {
    final r = await dio.get('/market/nifty50/constituents');
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  STRATEGIES (real backtest)
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> getStrategies() async {
    final r = await dio.get('/strategies');
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  EXPOSURE ANALYSIS
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> getExposureAnalysis() async {
    final r = await dio.get('/portfolio/exposure-analysis');
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  DIVIDEND INCOME
  // ══════════════════════════════════════════

  /// Dividend ledger + goal tracker across direct equity and funds.
  ///
  /// [goalAnnual] / [monthlyInvestment] preview a what-if without persisting;
  /// omit them to use the saved goal. [otherAssetsValue] folds locally-tracked
  /// assets (gold, cash) into the blended-yield denominator.
  Future<Map<String, dynamic>> getDividendAnalysis({
    bool force = false,
    double? goalAnnual,
    double? monthlyInvestment,
    double otherAssetsValue = 0,
  }) async {
    final r = await dio.get(
      '/portfolio/dividend-analysis',
      queryParameters: {
        'force': force,
        'goal_annual': ?goalAnnual,
        'monthly_investment': ?monthlyInvestment,
        'other_assets_value': otherAssetsValue,
      },
    );
    return r.data as Map<String, dynamic>;
  }

  /// Persist the dividend goal and its assumptions.
  Future<void> saveDividendGoal({
    double? goalAnnual,
    double? taxSlabPct,
    double? monthlyInvestment,
    Map<String, double>? overrides,
    Map<String, double>? fundOverrides,
  }) async {
    await dio.put(
      '/portfolio/dividend-goal',
      data: {
        'goal_annual': ?goalAnnual,
        'tax_slab_pct': ?taxSlabPct,
        'monthly_investment': ?monthlyInvestment,
        'overrides': ?overrides,
        'fund_overrides': ?fundOverrides,
      },
    );
  }

  // ══════════════════════════════════════════
  //  CAPITAL DEPLOYMENT
  // ══════════════════════════════════════════

  /// Live tape across broad-market, bank, sector and commodity indices.
  Future<Map<String, dynamic>> getMarketIndices({bool force = false}) async {
    final r = await dio.get(
      '/market/indices',
      queryParameters: {'force': force},
    );
    return r.data as Map<String, dynamic>;
  }

  /// The dashboard's master decision bar: what deserves attention today.
  ///
  /// A `status` of "quiet" is a normal answer, not a failure — it means
  /// nothing met the threshold today.
  Future<Map<String, dynamic>> getOpportunities({
    bool force = false,
    bool withNews = true,
  }) async {
    final r = await dio.get(
      '/portfolio/opportunities',
      queryParameters: {'force': force, 'with_news': withNews},
    );
    return r.data as Map<String, dynamic>;
  }

  /// Per-stock dip analysis. Every fall carries a reason: market-wide,
  /// company-specific, deteriorating, or a corporate action that makes the
  /// comparison meaningless.
  ///
  /// [withNews] is the slow half — 19 holdings means 19 RSS fetches. Turn it
  /// off for a fast first paint; the verdict still works without it, because
  /// it is driven by excess drawdown rather than by headlines.
  Future<Map<String, dynamic>> getStockDips({
    bool force = false,
    bool withNews = true,
  }) async {
    final r = await dio.get(
      '/portfolio/stock-dips',
      queryParameters: {'force': force, 'with_news': withNews},
    );
    return r.data as Map<String, dynamic>;
  }

  /// Per-fund purchase range and buy zones, each zone carrying what ten years
  /// of history measured at that depth.
  Future<Map<String, dynamic>> getFundDips({bool force = false}) async {
    final r = await dio.get(
      '/portfolio/fund-dips',
      queryParameters: {'force': force},
    );
    return r.data as Map<String, dynamic>;
  }

  /// Ten-year dip-threshold study for every index, quoted against a baseline
  /// of buying on a random day.
  Future<Map<String, dynamic>> getDipBacktest({
    bool force = false,
    String? symbol,
  }) async {
    final r = await dio.get(
      '/market/dip-backtest',
      queryParameters: {'force': force, if (symbol != null) 'symbol': symbol},
    );
    return r.data as Map<String, dynamic>;
  }

  /// Holdings ranked by how much they deserve new money, plus a split of
  /// [amount]. Pass 0 for the ranking alone.
  Future<Map<String, dynamic>> getDeployBoard({
    double amount = 0,
    bool force = false,
    double? scoreFloor,
    int? maxCandidates,
  }) async {
    final r = await dio.get(
      '/portfolio/deploy-board',
      queryParameters: {
        'amount': amount,
        'force': force,
        'score_floor': ?scoreFloor,
        'max_candidates': ?maxCandidates,
      },
    );
    return r.data as Map<String, dynamic>;
  }

  /// The saved SIP plan and targets, plus first-run suggestions.
  Future<Map<String, dynamic>> getDeployPlan() async {
    final r = await dio.get('/portfolio/deploy-plan');
    return r.data as Map<String, dynamic>;
  }

  /// Partial update — only the fields supplied are touched.
  Future<Map<String, dynamic>> saveDeployPlan({
    List<Map<String, dynamic>>? sipLegs,
    Map<String, double>? targets,
    Map<String, double>? weights,
    double? scoreFloor,
    double? maxConcentrationPct,
    int? maxCandidates,
    double? minTicketMf,
  }) async {
    final r = await dio.put(
      '/portfolio/deploy-plan',
      data: {
        'sip_legs': ?sipLegs,
        'targets': ?targets,
        'weights': ?weights,
        'score_floor': ?scoreFloor,
        'max_concentration_pct': ?maxConcentrationPct,
        'max_candidates': ?maxCandidates,
        'min_ticket_mf': ?minTicketMf,
      },
    );
    return r.data as Map<String, dynamic>;
  }

  /// Record a batch of buys. Places NO broker order.
  ///
  /// [requestId] must be client-generated and stable for one confirmation, so a
  /// retry or a double-click is recognised server-side as a duplicate rather
  /// than recording the money twice.
  Future<Map<String, dynamic>> deployExecute({
    required String requestId,
    required List<Map<String, dynamic>> items,
    String note = '',
  }) async {
    final r = await dio.post(
      '/portfolio/deploy-execute',
      data: {'request_id': requestId, 'items': items, 'note': note},
    );
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getDeployHistory({int limit = 50}) async {
    final r = await dio.get(
      '/portfolio/deploy-history',
      queryParameters: {'limit': limit},
    );
    return r.data as Map<String, dynamic>;
  }

  // ══════════════════════════════════════════
  //  SWING TRADING
  // ══════════════════════════════════════════
  Future<Map<String, dynamic>> getSwingDailyPicks({
    bool force = false,
    bool hardReset = false,
    String engine = 'v4',
  }) async {
    final r = await dio.get(
      '/swing/daily-picks',
      queryParameters: {
        'force': force,
        'hard_reset': hardReset,
        'engine': engine,
      },
    );
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getSwingAnalysis(String symbol) async {
    final r = await dio.get('/swing/analyze/$symbol');
    return r.data as Map<String, dynamic>;
  }

  /// Daily Pick History: every saved date's picks joined with each pick's
  /// tracked outcome (still tracking / expired / never tracked).
  Future<Map<String, dynamic>> getSwingDailyPickHistory() async {
    final r = await dio.get('/swing/daily-pick-history');
    return r.data as Map<String, dynamic>;
  }

  /// Selectable scan universes (Nifty 50 / 500 / Total Market) + the current one.
  Future<Map<String, dynamic>> getSwingUniverses() async {
    final r = await dio.get('/swing/universe');
    return r.data as Map<String, dynamic>;
  }

  /// Point the scanner at a different index. Persisted per user; takes effect
  /// on the next scan (today's saved picks stay frozen).
  Future<Map<String, dynamic>> setSwingUniverse(String universe) async {
    final r = await dio.put('/swing/universe', data: {'universe': universe});
    return r.data as Map<String, dynamic>;
  }

  // 14-Day Desk — AI-selected, user-executed watchlist.
  Future<Map<String, dynamic>> getSwingDeskList({
    bool reanalyze = false,
  }) async {
    final r = await dio.get(
      '/swing/desk/list',
      queryParameters: {'reanalyze': reanalyze},
    );
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> swingDeskAutoSelect() async {
    final r = await dio.post('/swing/desk/auto-select-from-today');
    return r.data as Map<String, dynamic>;
  }

  /// Priority view: the single #1 action + urgency buckets with live prices.
  Future<Map<String, dynamic>> getSwingDeskFocus() async {
    final r = await dio.get('/swing/desk/focus');
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> swingDeskReanalyze() async {
    final r = await dio.post('/swing/desk/reanalyze');
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> swingDeskRemove(String symbol) async {
    final r = await dio.post('/swing/desk/remove', data: {'symbol': symbol});
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> swingDeskArchive(String symbol) async {
    final r = await dio.post('/swing/desk/archive', data: {'symbol': symbol});
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> swingDeskPaperBuy(
    String symbol, {
    int quantity = 0,
  }) async {
    final r = await dio.post(
      '/swing/desk/paper-buy',
      data: {'symbol': symbol, 'quantity': quantity},
    );
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> swingDeskArmAutoBuy(String symbol) async {
    final r = await dio.post(
      '/swing/desk/arm-auto-buy',
      data: {'symbol': symbol},
    );
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> swingDeskDisarmAutoBuy(String symbol) async {
    final r = await dio.post(
      '/swing/desk/disarm-auto-buy',
      data: {'symbol': symbol},
    );
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getSwingPaperStatus() async {
    final r = await dio.get('/swing/paper/status');
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> swingPaperTrade({
    required String symbol,
    required String action,
    int quantity = 0,
    double price = 0,
    double stopLoss = 0,
    double target = 0,
    String setup = '',
  }) async {
    final r = await dio.post(
      '/swing/paper/trade',
      data: {
        'symbol': symbol,
        'action': action,
        'quantity': quantity,
        'price': price,
        'stop_loss': stopLoss,
        'target': target,
        'setup': setup,
      },
    );
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> swingPaperReset({double? capital}) async {
    final r = await dio.post(
      '/swing/paper/reset',
      data: {'capital': capital ?? 0},
    );
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> swingPaperAutoCheck() async {
    final r = await dio.get('/swing/paper/auto-check');
    return r.data as Map<String, dynamic>;
  }

  /// Reset ALL Swing Trading data for the current user: saved daily picks +
  /// history, the 14-Day Desk, pending/open/closed paper trades, equity
  /// history, and the in-memory scan cache — then reinitializes a clean
  /// paper account at [capital]. Never touches portfolio/MF/watchlist/login
  /// data. Callers must confirm with the user before calling this.
  Future<Map<String, dynamic>> resetAllSwingData({double? capital}) async {
    final r = await dio.post(
      '/swing/reset-all',
      data: {'capital': capital ?? 0},
    );
    return r.data as Map<String, dynamic>;
  }
}

/// Retries idempotent requests (GET/HEAD/OPTIONS) on transient connection-level
/// failures. Non-idempotent methods (POST/PUT/DELETE) are never retried to avoid
/// double-submission. Retry count is tracked per-request via [RequestOptions.extra]
/// so a genuinely broken endpoint still fails fast after [_maxRetries] attempts.
class _RetryInterceptor extends Interceptor {
  _RetryInterceptor(this._dio, this._log);

  final Dio _dio;
  final Logger _log;

  static const _maxRetries = 2;
  static const _retryDelays = [
    Duration(milliseconds: 300),
    Duration(milliseconds: 800),
  ];

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    final options = err.requestOptions;
    final attempt = (options.extra['retry_attempt'] as int?) ?? 0;

    if (_shouldRetry(err) && attempt < _maxRetries) {
      final delay = _retryDelays[attempt];
      options.extra['retry_attempt'] = attempt + 1;
      _log.w(
        'Retry ${attempt + 1}/$_maxRetries: ${options.method} ${options.path} '
        'in ${delay.inMilliseconds}ms (${err.type})',
      );
      await Future.delayed(delay);
      try {
        final response = await _dio.fetch(options);
        return handler.resolve(response);
      } on DioException catch (e) {
        return handler.next(e);
      }
    }
    handler.next(err);
  }

  bool _shouldRetry(DioException err) {
    // Only retry idempotent methods — never replay a POST/PUT/DELETE.
    const idempotent = {'GET', 'HEAD', 'OPTIONS'};
    if (!idempotent.contains(err.requestOptions.method.toUpperCase()))
      return false;

    switch (err.type) {
      case DioExceptionType.connectionError:
      case DioExceptionType.connectionTimeout:
        return true;
      case DioExceptionType.unknown:
        // The transient localhost failure surfaces as `unknown` wrapping an
        // HttpException/SocketException ("Connection closed before full header
        // was received") from a stale keep-alive socket.
        final msg = (err.error?.toString() ?? err.message ?? '');
        return msg.contains('Connection closed') ||
            msg.contains('HttpException') ||
            msg.contains('SocketException');
      default:
        // Do NOT retry receiveTimeout — those endpoints (deep analysis, Kite
        // sync) are legitimately slow, not dropped connections.
        return false;
    }
  }
}
