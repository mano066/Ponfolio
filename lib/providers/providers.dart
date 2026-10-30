import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/api_service.dart';
import '../services/local_storage_service.dart';
import '../data/models/portfolio_models.dart';
import '../data/models/closed_positions.dart';
import '../core/constants.dart';

// ══════════════════════════════════════════
//  SINGLETONS
// ══════════════════════════════════════════

final apiServiceProvider = Provider<ApiService>((ref) => ApiService());

/// Overridden in main.dart with the initialized Hive instance.
final localStorageProvider = Provider<LocalStorageService>((ref) {
  throw UnimplementedError('localStorageProvider must be overridden');
});

// ══════════════════════════════════════════
//  THEME
// ══════════════════════════════════════════

class IsDarkModeNotifier extends Notifier<bool> {
  final bool _initialValue;
  IsDarkModeNotifier([this._initialValue = true]);
  @override
  bool build() => _initialValue;
  void toggle() => state = !state;
  void set(bool v) => state = v;
}

final isDarkModeProvider =
    NotifierProvider<IsDarkModeNotifier, bool>(IsDarkModeNotifier.new);

// ══════════════════════════════════════════
//  NAVIGATION
// ══════════════════════════════════════════

class ActiveTabNotifier extends Notifier<AppTab> {
  @override
  AppTab build() => AppTab.dashboard;
  void setTab(AppTab tab) => state = tab;
}

final activeTabProvider =
    NotifierProvider<ActiveTabNotifier, AppTab>(ActiveTabNotifier.new);

// ══════════════════════════════════════════
//  AUTH / PROFILE
// ══════════════════════════════════════════

final profileProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final api = ref.read(apiServiceProvider);
  return api.getProfile();
});

class IsGuestNotifier extends Notifier<bool> {
  bool _disposed = false;

  @override
  bool build() {
    ref.onDispose(() => _disposed = true);
    // Start in guest mode, then rehydrate from the backend session. The backend
    // persists the Google login across restarts (google_auth.get_profile()), so a
    // returning user must not be stranded in guest mode — portfolioProvider
    // short-circuits to empty holdings while isGuest is true, which otherwise
    // hides a perfectly good portfolio until the user signs in again.
    _rehydrate();
    return true;
  }

  /// Ask the backend whether a session already exists.
  ///
  /// main() launches the backend fire-and-forget, so the first attempts can fail
  /// while it is still booting. Retry rather than giving up after one miss.
  Future<void> _rehydrate() async {
    final api = ref.read(apiServiceProvider);
    for (var attempt = 0; attempt < 30 && !_disposed; attempt++) {
      try {
        final profile = await api.getProfile();
        if (_disposed) return;
        if (_isLoggedIn(profile)) state = false;
        return; // Backend answered — nothing more to wait for.
      } catch (_) {
        // Backend not reachable yet; wait and retry.
        await Future<void>.delayed(const Duration(seconds: 2));
      }
    }
  }

  static bool _isLoggedIn(Map<String, dynamic> p) {
    if (p['logged_in'] == true || p['authenticated'] == true) return true;
    final email = p['email'];
    return email is String && email.isNotEmpty;
  }

  void set(bool v) {
    if (!_disposed) state = v;
  }
}
final isGuestProvider = NotifierProvider<IsGuestNotifier, bool>(IsGuestNotifier.new);

// ══════════════════════════════════════════
//  PORTFOLIO — full fetch + live price polling
// ══════════════════════════════════════════

/// Re-read everything that a fresh pull of holdings can change.
///
/// Invalidating `portfolioProvider` alone was why a sync appeared to do
/// nothing: the stock list updated while the funds, the exposure analysis and
/// the rebalance plan went on serving the copies they had already cached, so
/// most of the screen still showed the old book.
void refreshHoldings(WidgetRef ref) {
  ref.invalidate(portfolioProvider);
  ref.invalidate(mfPortfolioProvider);
}

/// Full portfolio fetch (initial load + manual refresh).
final portfolioProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final isGuest = ref.watch(isGuestProvider);
  if (isGuest) {
    return {
      'total_portfolio_value': 0.0,
      'total_invested': 0.0,
      'total_pnl': 0.0,
      'total_pnl_pct': 0.0,
      'holdings': [],
      'kite_connected': false,
      'data_source': 'none',
    };
  }

  final api = ref.read(apiServiceProvider);
  final storage = ref.read(localStorageProvider);
  try {
    final data = await api.getPortfolio().timeout(const Duration(seconds: 20));
    // Cache for offline fallback
    storage.cacheJson(LocalStorageService.keyPortfolio, data);
    return data;
  } catch (e) {
    // Offline fallback
    final cached = storage.getCachedJson(LocalStorageService.keyPortfolio);
    if (cached != null) return {...cached, 'offline': true, 'stale': true};
    rethrow;
  }
});

/// Annualised (XIRR) return for equity, MF, and the two combined.
///
/// Kept separate from [portfolioProvider] because the combined figure has to
/// pool equity and MF cashflows into one solve on the server — averaging the
/// two rates client-side would not be an XIRR. Failures degrade to nulls so a
/// backend without trade history never breaks the dashboard.
final portfolioXirrProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  const empty = {
    'equity': {'xirr': null, 'covered_pct': 0.0},
    'mutual_funds': {'xirr': null, 'covered_pct': 0.0},
    'combined': {'xirr': null, 'covered_pct': 0.0},
  };
  if (ref.watch(isGuestProvider)) return empty;
  try {
    return await ref.read(apiServiceProvider).getPortfolioXirr();
  } catch (_) {
    return empty;
  }
});

/// Lightweight live-price poller — updates portfolio in-place every 5s.
final livePriceProvider =
    StreamProvider.autoDispose<Map<String, dynamic>>((ref) {
  final api = ref.read(apiServiceProvider);
  return Stream.periodic(
    const Duration(milliseconds: AppConstants.priceRefreshMs),
    (_) => null,
  ).asyncMap((_) async {
    final isGuest = ref.read(isGuestProvider);
    if (isGuest) return <String, dynamic>{};

    try {
      return await api.getLivePrices();
    } catch (_) {
      return <String, dynamic>{};
    }
  });
});

/// The equity portfolio with the 5-second live poll laid over it.
///
/// `portfolioProvider` is a one-shot fetch, so on its own the dashboard showed
/// whatever prices it loaded with until the user pressed refresh — the
/// "dashboard does not update like the live market" report. The live poll
/// returns the same payload shape (see `/api/portfolio/live-prices`), so each
/// tick simply replaces the numbers. It is laid over rather than invalidating
/// the base provider, because a refetch would flip the dashboard into its
/// loading state every five seconds.
///
/// The base still wins while it is loading or failed, so a manual refresh,
/// a Kite sync or a holding edit is never masked by an older live tick.
final livePortfolioProvider =
    Provider.autoDispose<AsyncValue<Map<String, dynamic>>>((ref) {
  final base = ref.watch(portfolioProvider);
  if (base.isLoading || base.hasError) return base;
  final data = base.value;
  if (data == null) return base;
  // A failed live poll must never take the dashboard down with it: this is a
  // synchronous provider, so anything thrown here would surface as a build
  // error in every screen that watches it.
  Map<String, dynamic>? live;
  try {
    live = ref.watch(livePriceProvider).value;
  } catch (_) {
    live = null;
  }
  if (live == null || live['holdings'] is! List) return base;
  // A tick taken before the base (re)loaded may describe an older holdings
  // list; only a matching-size book is trusted to replace it.
  final baseHoldings = data['holdings'];
  if (baseHoldings is List &&
      (live['holdings'] as List).length != baseHoldings.length) {
    return base;
  }
  return AsyncData<Map<String, dynamic>>({...data, ...live, 'live': true});
});

/// Last price update timestamp string (e.g. "11:23 AM").
class LastUpdatedNotifier extends Notifier<String> {
  @override
  String build() => '—';
  void set(String v) => state = v;
}
final lastUpdatedProvider = NotifierProvider<LastUpdatedNotifier, String>(LastUpdatedNotifier.new);

// ══════════════════════════════════════════
//  MUTUAL FUND PORTFOLIO
// ══════════════════════════════════════════

final mfPortfolioProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final isGuest = ref.watch(isGuestProvider);
  if (isGuest) {
    return {
      'funds': [],
      'total_invested': 0.0,
      'total_current': 0.0,
      'total_pnl': 0.0,
      'total_pnl_pct': 0.0,
    };
  }

  final api = ref.read(apiServiceProvider);
  final storage = ref.read(localStorageProvider);
  try {
    final data = await api.getMFPortfolio().timeout(const Duration(seconds: 20));
    storage.cacheJson(LocalStorageService.keyMFPortfolio, data);
    return data;
  } catch (e) {
    final cached = storage.getCachedJson(LocalStorageService.keyMFPortfolio);
    if (cached != null) return {...cached, 'offline': true, 'stale': true};
    rethrow;
  }
});

// ══════════════════════════════════════════
//  CLOSED EQUITY POSITIONS (realised P&L)
// ══════════════════════════════════════════

/// FIFO-matched realised P&L on sold shares.
///
/// Depends on the dated ledger rather than on live prices, so it is not part
/// of the price-refresh cycle: it changes only when a tradebook is imported or
/// a trade is recorded. Invalidated by those actions, not polled.
final closedPositionsProvider =
    FutureProvider.autoDispose<ClosedBook>((ref) async {
  if (ref.watch(isGuestProvider)) return const ClosedBook();
  final api = ref.read(apiServiceProvider);
  return ClosedBook.fromJson(
      await api.getClosedPositions().timeout(const Duration(seconds: 20)));
});

// ══════════════════════════════════════════
//  NIFTY 50 (polling every 30s)
// ══════════════════════════════════════════

final niftyProvider = StreamProvider<Map<String, dynamic>>((ref) {
  final api = ref.read(apiServiceProvider);
  return Stream.periodic(
    const Duration(milliseconds: AppConstants.niftyPollMs),
    (_) => null,
  ).asyncMap((_) async {
    try {
      return await api.getNifty50();
    } catch (_) {
      return <String, dynamic>{};
    }
  });
});

// ══════════════════════════════════════════
//  KITE STATUS (polling every 15s)
// ══════════════════════════════════════════

final kiteStatusProvider = StreamProvider<Map<String, dynamic>>((ref) {
  final api = ref.read(apiServiceProvider);

  // The last answer the backend actually gave. A poll that fails says nothing
  // about Kite — the request may have timed out because the backend was busy
  // fetching prices — so the previous state stands until a newer one arrives.
  Map<String, dynamic>? last;

  Future<Map<String, dynamic>> fetch() async {
    final isGuest = ref.read(isGuestProvider);
    if (isGuest) return <String, dynamic>{'connected': false, 'configured': false};
    try {
      return last = await api.getKiteStatus();
    } catch (_) {
      // Reporting 'reconnecting' here was the bug behind "Kite keeps
      // disconnecting": one slow poll painted the sidebar amber, the user
      // tapped it, and that reconnect discarded a perfectly good MCP session
      // — which is what actually forced the Zerodha login. A failed poll is
      // now marked stale and nothing else.
      if (last != null) {
        return <String, dynamic>{...last!, 'status_stale': true};
      }
      return <String, dynamic>{
        'connected': false,
        'configured': false,
        'status_stale': true,
        'last_error': 'Status unavailable; retrying automatically.',
      };
    }
  }

  // Emit immediately, then poll every N ms
  return Stream.fromFuture(fetch()).asyncExpand((first) async* {
    yield first;
    yield* Stream.periodic(
      const Duration(milliseconds: AppConstants.kitePollMs),
      (_) => null,
    ).asyncMap((_) => fetch());
  });
});

/// Kite login loading state.
class KiteLoadingNotifier extends Notifier<bool> {
  @override
  bool build() => false;
  void set(bool v) => state = v;
}
final kiteLoadingProvider = NotifierProvider<KiteLoadingNotifier, bool>(KiteLoadingNotifier.new);

// ══════════════════════════════════════════
//  AI DEEP SIGNALS (polling every 10s)
// ══════════════════════════════════════════

final aiSignalsProvider = StreamProvider<Map<String, dynamic>>((ref) {
  final api = ref.read(apiServiceProvider);
  return Stream.periodic(
    const Duration(milliseconds: AppConstants.signalPollMs),
    (_) => null,
  ).asyncMap((_) async {
    try {
      return await api.getDeepSignals();
    } catch (_) {
      return <String, dynamic>{'signals': <String, dynamic>{}, 'running': false};
    }
  });
});

// ══════════════════════════════════════════
//  AI ADVISOR (polling every 4s)
// ══════════════════════════════════════════

/// Advisor state: running, results per symbol, last_run timestamp.
class AdvisorNotifier extends Notifier<AdvisorState> {
  @override
  AdvisorState build() => const AdvisorState();

  void update(Map<String, dynamic> data) {
    state = AdvisorState(
      running: data['running'] == true,
      results: Map<String, dynamic>.from(data['results'] ?? {}),
      lastRun: data['last_run'] as String?,
    );
  }

  void setRunning(bool v) => state = state.copyWith(running: v);
}

class AdvisorState {
  final bool running;
  final Map<String, dynamic> results;
  final String? lastRun;

  const AdvisorState({
    this.running = false,
    this.results = const {},
    this.lastRun,
  });

  AdvisorState copyWith({bool? running, Map<String, dynamic>? results, String? lastRun}) =>
      AdvisorState(
        running: running ?? this.running,
        results: results ?? this.results,
        lastRun: lastRun ?? this.lastRun,
      );
}

final advisorProvider =
    NotifierProvider<AdvisorNotifier, AdvisorState>(AdvisorNotifier.new);

/// Advisor polling stream — polls /advisor every 4s, pushes into advisorProvider.
final advisorPollProvider = StreamProvider.autoDispose<void>((ref) {
  final api = ref.read(apiServiceProvider);
  return Stream.periodic(
    const Duration(milliseconds: AppConstants.advisorPollMs),
    (_) => null,
  ).asyncMap((_) async {
    try {
      final data = await api.getAdvisor();
      ref.read(advisorProvider.notifier).update(data);
    } catch (_) {}
  });
});

// ══════════════════════════════════════════
//  DEEP ANALYSIS (on-demand, per-symbol)
// ══════════════════════════════════════════

class DeepAnalysisSymbolNotifier extends Notifier<String?> {
  @override
  String? build() => null;
  void setSymbol(String? s) => state = s;
}

final deepAnalysisSymbolProvider =
    NotifierProvider<DeepAnalysisSymbolNotifier, String?>(
  DeepAnalysisSymbolNotifier.new,
);

/// Counter to force re-fetch (like web's daKey).
class DeepAnalysisKeyNotifier extends Notifier<int> {
  @override
  int build() => 0;
  void increment() => state++;
}
final deepAnalysisKeyProvider = NotifierProvider<DeepAnalysisKeyNotifier, int>(DeepAnalysisKeyNotifier.new);

final deepAnalysisProvider =
    FutureProvider.autoDispose<Map<String, dynamic>?>((ref) async {
  final symbol = ref.watch(deepAnalysisSymbolProvider);
  ref.watch(deepAnalysisKeyProvider); // re-run when key increments
  if (symbol == null) return null;
  final api = ref.read(apiServiceProvider);
  return api.getDeepAnalysis(symbol);
});

// ══════════════════════════════════════════
//  EQUITY TABLE — expanded row
// ══════════════════════════════════════════

/// Which equity holding row is expanded (shows inline deep analysis).
class ExpandedHoldingNotifier extends Notifier<String?> {
  @override
  String? build() => null;
  void set(String? v) => state = v;
  void toggle(String sym) => state = state == sym ? null : sym;
}
final expandedHoldingProvider = NotifierProvider<ExpandedHoldingNotifier, String?>(ExpandedHoldingNotifier.new);

// ══════════════════════════════════════════
//  STOCK PICKER
// ══════════════════════════════════════════

class StockPickerVisibleNotifier extends Notifier<bool> {
  @override
  bool build() => false;
  void set(bool v) => state = v;
  void toggle() => state = !state;
}
final stockPickerVisibleProvider = NotifierProvider<StockPickerVisibleNotifier, bool>(StockPickerVisibleNotifier.new);

// ══════════════════════════════════════════
//  ANALYTICS (on-demand)
// ══════════════════════════════════════════

final analyticsProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final api = ref.read(apiServiceProvider);
  return api.getAnalytics();
});

// ══════════════════════════════════════════
//  WEALTH REPORT (on-demand)
// ══════════════════════════════════════════

final wealthReportProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  ref.watch(wealthReportKeyProvider); // re-run on manual refresh
  final api = ref.read(apiServiceProvider);
  return api.getWealthReport();
});

/// Counter to force re-fetch of wealth report.
class WealthReportKeyNotifier extends Notifier<int> {
  @override
  int build() => 0;
  void refresh() => state++;
}
final wealthReportKeyProvider = NotifierProvider<WealthReportKeyNotifier, int>(WealthReportKeyNotifier.new);

// ══════════════════════════════════════════
//  MARKET MOVERS (Top Gainers / Losers)
// ══════════════════════════════════════════

final marketMoversProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final api = ref.read(apiServiceProvider);
  try {
    return await api.getMarketMovers();
  } catch (_) {
    return <String, dynamic>{'gainers': [], 'losers': []};
  }
});

// ══════════════════════════════════════════
//  NIFTY 50 CONSTITUENTS (for gainers/losers)
// ══════════════════════════════════════════

final nifty50ConstituentsProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final api = ref.read(apiServiceProvider);
  try {
    return await api.getNifty50Constituents();
  } catch (_) {
    return <String, dynamic>{'constituents': []};
  }
});

// ══════════════════════════════════════════
//  STRATEGIES (real backtest, on-demand)
// ══════════════════════════════════════════

final strategiesProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final api = ref.read(apiServiceProvider);
  try {
    return await api.getStrategies();
  } catch (_) {
    return <String, dynamic>{'strategies': []};
  }
});

// ══════════════════════════════════════════
//  AI TOP PICKS (Deep analysis recommendations)
// ══════════════════════════════════════════

final aiTopPicksProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final api = ref.read(apiServiceProvider);
  try {
    return await api.getAITopPicks();
  } catch (_) {
    return <String, dynamic>{'picks': []};
  }
});

// ══════════════════════════════════════════
//  SETTINGS
// ══════════════════════════════════════════

final settingsProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final api = ref.read(apiServiceProvider);
  return api.getSettings();
});

// ══════════════════════════════════════════
//  AI CHATBOT
// ══════════════════════════════════════════

class ChatNotifier extends Notifier<ChatState> {
  @override
  ChatState build() => const ChatState();

  void addUserMessage(String text) {
    state = state.copyWith(
      messages: [
        ...state.messages,
        ChatMessage(role: 'user', content: text, timestamp: DateTime.now()),
      ],
    );
  }

  void addAssistantMessage(String text) {
    state = state.copyWith(
      messages: [
        ...state.messages,
        ChatMessage(role: 'assistant', content: text, timestamp: DateTime.now()),
      ],
      isLoading: false,
    );
  }

  void setLoading(bool v) => state = state.copyWith(isLoading: v);
  void toggleOpen() => state = state.copyWith(isOpen: !state.isOpen);
  void setOpen(bool v) => state = state.copyWith(isOpen: v);

  void clear() => state = state.copyWith(messages: []);

  /// Send a message and get AI response.
  Future<void> send(String text) async {
    addUserMessage(text);
    setLoading(true);
    try {
      final api = ref.read(apiServiceProvider);
      final history = state.messages
          .map((m) => {'role': m.role, 'content': m.content})
          .toList();
      final data = await api.chat(text, history);
      addAssistantMessage(data['reply'] ?? 'No response.');
    } catch (e) {
      addAssistantMessage('Error: $e');
    }
  }
}

class ChatState {
  final List<ChatMessage> messages;
  final bool isOpen;
  final bool isLoading;

  const ChatState({
    this.messages = const [],
    this.isOpen = false,
    this.isLoading = false,
  });

  ChatState copyWith({
    List<ChatMessage>? messages,
    bool? isOpen,
    bool? isLoading,
  }) =>
      ChatState(
        messages: messages ?? this.messages,
        isOpen: isOpen ?? this.isOpen,
        isLoading: isLoading ?? this.isLoading,
      );
}

final chatProvider =
    NotifierProvider<ChatNotifier, ChatState>(ChatNotifier.new);

// ══════════════════════════════════════════
//  SIP SIMULATOR
// ══════════════════════════════════════════

class SIPSimulatorNotifier extends Notifier<SIPSimulatorState> {
  @override
  SIPSimulatorState build() => const SIPSimulatorState();

  void setSymbol(String s) => state = state.copyWith(symbol: s);
  void setMonthly(double v) => state = state.copyWith(monthly: v);
  void setYears(int v) => state = state.copyWith(years: v);
  void setSipDate(int v) => state = state.copyWith(sipDate: v);
  void setStepUp(double v) => state = state.copyWith(stepUpPct: v);
  void setLoading(bool v) => state = state.copyWith(isLoading: v);
  void setResults(Map<String, dynamic>? r) =>
      state = state.copyWith(results: r, isLoading: false);

  Future<void> simulate() async {
    if (state.symbol.isEmpty) return;
    setLoading(true);
    try {
      final api = ref.read(apiServiceProvider);
      final data = await api.simulateSIP(
        symbols: [
          {'symbol': state.symbol, 'amount': state.monthly, 'label': state.symbol}
        ],
        startDate: '2020-01-01',
        sipDay: state.sipDate,
        stepUpPct: state.stepUpPct,
      );
      setResults(data);
    } catch (e) {
      setResults({'error': '$e'});
    }
  }
}

class SIPSimulatorState {
  final String symbol;
  final double monthly;
  final int years;
  final int sipDate;
  final double stepUpPct;
  final bool isLoading;
  final Map<String, dynamic>? results;

  const SIPSimulatorState({
    this.symbol = '',
    this.monthly = 5000,
    this.years = 5,
    this.sipDate = 1,
    this.stepUpPct = 0,
    this.isLoading = false,
    this.results,
  });

  SIPSimulatorState copyWith({
    String? symbol,
    double? monthly,
    int? years,
    int? sipDate,
    double? stepUpPct,
    bool? isLoading,
    Map<String, dynamic>? results,
  }) =>
      SIPSimulatorState(
        symbol: symbol ?? this.symbol,
        monthly: monthly ?? this.monthly,
        years: years ?? this.years,
        sipDate: sipDate ?? this.sipDate,
        stepUpPct: stepUpPct ?? this.stepUpPct,
        isLoading: isLoading ?? this.isLoading,
        results: results ?? this.results,
      );
}

final sipSimulatorProvider =
    NotifierProvider<SIPSimulatorNotifier, SIPSimulatorState>(
  SIPSimulatorNotifier.new,
);

// ══════════════════════════════════════════
//  MF SCREENER
// ══════════════════════════════════════════

class MFScreenerNotifier extends Notifier<MFScreenerState> {
  @override
  MFScreenerState build() => const MFScreenerState();

  void setQuery(String q) => state = state.copyWith(query: q);
  void setLoading(bool v) => state = state.copyWith(isLoading: v);
  void setResults(Map<String, dynamic>? r) =>
      state = state.copyWith(results: r, isLoading: false);
  void setSearchResults(List<Map<String, dynamic>> r) =>
      state = state.copyWith(searchResults: r);

  Future<void> search(String query) async {
    setQuery(query);
    if (query.length < 2) return;
    try {
      final api = ref.read(apiServiceProvider);
      final data = await api.searchMFAnalysis(query);
      final results =
          List<Map<String, dynamic>>.from(data['results'] ?? []);
      setSearchResults(results);
    } catch (_) {}
  }

  Future<void> startAnalysis(Map<String, dynamic> params) async {
    setLoading(true);
    try {
      final api = ref.read(apiServiceProvider);
      await api.startMFAnalysis(
        category: params['category']?.toString() ?? 'Custom',
        schemeCodes: List<int>.from(params['scheme_codes'] ?? []),
      );
      // Poll for completion
      for (int i = 0; i < 60; i++) {
        await Future.delayed(const Duration(seconds: 3));
        final status = await api.getMFAnalysisStatus();
        if (status['running'] != true) {
          setResults(status['results'] as Map<String, dynamic>? ?? status);
          return;
        }
      }
      setResults({'error': 'Analysis timed out'});
    } catch (e) {
      setResults({'error': '$e'});
    }
  }
}

class MFScreenerState {
  final String query;
  final bool isLoading;
  final List<Map<String, dynamic>> searchResults;
  final Map<String, dynamic>? results;

  const MFScreenerState({
    this.query = '',
    this.isLoading = false,
    this.searchResults = const [],
    this.results,
  });

  MFScreenerState copyWith({
    String? query,
    bool? isLoading,
    List<Map<String, dynamic>>? searchResults,
    Map<String, dynamic>? results,
  }) =>
      MFScreenerState(
        query: query ?? this.query,
        isLoading: isLoading ?? this.isLoading,
        searchResults: searchResults ?? this.searchResults,
        results: results ?? this.results,
      );
}

final mfScreenerProvider =
    NotifierProvider<MFScreenerNotifier, MFScreenerState>(
  MFScreenerNotifier.new,
);

// ══════════════════════════════════════════
//  COMPUTED / DERIVED PROVIDERS
// ══════════════════════════════════════════

/// Enriched holdings: merges portfolio holdings with AI signal + advisor verdict.
final enrichedHoldingsProvider =
    Provider.autoDispose<List<Map<String, dynamic>>>((ref) {
  final portfolio = ref.watch(livePortfolioProvider);
  final signals = ref.watch(aiSignalsProvider);
  final advisor = ref.watch(advisorProvider);

  return portfolio.when(
    data: (pData) {
      final holdings =
          List<Map<String, dynamic>>.from(pData['holdings'] ?? []);
      final signalMap = signals.when(
        data: (d) => Map<String, dynamic>.from(d['signals'] ?? {}),
        loading: () => <String, dynamic>{},
        error: (_, _) => <String, dynamic>{},
      );

      return holdings.map((h) {
        final sym = h['symbol'] as String? ?? '';
        // AI Signal from deep-signals
        final ds = signalMap[sym];
        String signal = 'HOLD';
        if (ds is Map) {
          final status = ds['status'];
          if (status == 'done') {
            signal = (ds['verdict_owned'] ?? 'HOLD').toString();
          } else if (status == 'running') {
            signal = 'ANALYZING...';
          }
        }
        // Advisor verdict
        final av = advisor.results[sym];

        return {
          ...h,
          'signal': signal,
          'advisor_verdict': av,
        };
      }).toList();
    },
    loading: () => <Map<String, dynamic>>[],
    error: (_, _) => <Map<String, dynamic>>[],
  );
});

/// Combined wealth totals (stocks + MF).
final combinedWealthProvider =
    Provider.autoDispose<Map<String, double>>((ref) {
  final portfolio = ref.watch(livePortfolioProvider);
  final mf = ref.watch(mfPortfolioProvider);

  double eqInv = 0, eqVal = 0, mfInv = 0, mfVal = 0;

  portfolio.whenData((d) {
    eqInv = (d['total_invested'] ?? 0).toDouble();
    eqVal = (d['total_portfolio_value'] ?? 0).toDouble();
  });
  mf.whenData((d) {
    mfInv = (d['total_invested'] ?? 0).toDouble();
    mfVal = (d['total_current'] ?? 0).toDouble();
  });

  final combInv = eqInv + mfInv;
  final combVal = eqVal + mfVal;
  final combPnl = combVal - combInv;
  final combPnlPct = combInv > 0 ? (combPnl / combInv) * 100 : 0.0;

  return {
    'eq_invested': eqInv,
    'eq_value': eqVal,
    'eq_pnl': eqVal - eqInv,
    'eq_pnl_pct': eqInv > 0 ? ((eqVal - eqInv) / eqInv) * 100 : 0,
    'mf_invested': mfInv,
    'mf_value': mfVal,
    'mf_pnl': mfVal - mfInv,
    'mf_pnl_pct': mfInv > 0 ? ((mfVal - mfInv) / mfInv) * 100 : 0,
    'combined_invested': combInv,
    'combined_value': combVal,
    'combined_pnl': combPnl,
    'combined_pnl_pct': combPnlPct,
  };
});

// ══════════════════════════════════════════
//  SWING TRADING
// ══════════════════════════════════════════

// Tracks the last key value for which we sent a forced (fresh) scan request.
// Polling re-runs share the same key and must NOT force — otherwise every poll
// (and every tab revisit) would kick off a brand-new scan in a loop.
int _swingLastForcedKey = -1;
// Tracks the last key for which a deliberate "Hard Rescan Today" was requested.
// A hard reset discards today's saved canonical picks and re-scans; a normal
// scan/refresh never does (it returns the saved list once one exists).
int _swingLastHardResetKey = 0;

/// Selected swing engine: 'v4' (default), 'v4.1' (v4's scan re-ranked to
/// penalise cross-sectional ATR% and reward closeness to the 52-week high) or
/// 'v5' (regime-adaptive ensemble). Drives which picks the daily list shows.
/// v4 stays the default; the others are candidates on isolated storage variants.
class SwingEngineNotifier extends Notifier<String> {
  @override
  String build() => 'v4';
  void select(String engine) => state = engine;
}
final swingEngineProvider =
    NotifierProvider<SwingEngineNotifier, String>(SwingEngineNotifier.new);

final swingPicksProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final key = ref.watch(swingPicksKeyProvider);
  final hardKey = ref.watch(swingHardResetKeyProvider);
  final engine = ref.watch(swingEngineProvider);
  // Don't auto-scan — wait for user to click "Scan Now"
  if (key == 0 && hardKey == 0) {
    return <String, dynamic>{'picks': [], 'scanning': false, 'awaiting_user': true};
  }
  final api = ref.read(apiServiceProvider);
  // A hard reset fires once per "Hard Rescan" press and replaces today's saved
  // picks. A normal scan/refresh only scans when today has no saved picks yet.
  final hardReset = hardKey != 0 && hardKey != _swingLastHardResetKey;
  if (hardReset) _swingLastHardResetKey = hardKey;
  final force = hardReset || key != _swingLastForcedKey;
  if (force) _swingLastForcedKey = key;
  final result =
      await api.getSwingDailyPicks(force: force, hardReset: hardReset, engine: engine);

  // If still scanning, keep polling every 3 seconds until results arrive
  if (result['scanning'] == true) {
    final link = ref.keepAlive();
    bool disposed = false;
    ref.onDispose(() => disposed = true);
    Future.delayed(const Duration(seconds: 3), () {
      if (!disposed) {
        link.close();
        ref.invalidateSelf();
      }
    });
  }
  return result;
});

class SwingPicksKeyNotifier extends Notifier<int> {
  @override
  int build() => 0;
  void refresh() => state++;
}
final swingPicksKeyProvider = NotifierProvider<SwingPicksKeyNotifier, int>(SwingPicksKeyNotifier.new);

/// Bumped only by a deliberate "Hard Rescan Today" action — replaces today's
/// saved canonical picks with a fresh scan.
class SwingHardResetKeyNotifier extends Notifier<int> {
  @override
  int build() => 0;
  void refresh() => state++;
}
final swingHardResetKeyProvider =
    NotifierProvider<SwingHardResetKeyNotifier, int>(SwingHardResetKeyNotifier.new);

// Tracks the last key for which a forced (refresh=true) desk re-analysis was
// requested — same "force only once per press" idea as the picks scan above,
// so tab revisits at the same key serve the cached desk instead of rebuilding.
int _swingDeskLastForcedKey = -1;

final swingDeskProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final key = ref.watch(swingDeskKeyProvider);
  final api = ref.read(apiServiceProvider);
  // First load (key 0) serves the stored desk (auto-reanalyzed on a new day); a
  // manual refresh bumps the key and forces a re-analysis exactly once per key.
  final reanalyze = key != 0 && key != _swingDeskLastForcedKey;
  if (reanalyze) _swingDeskLastForcedKey = key;
  return api.getSwingDeskList(reanalyze: reanalyze);
});

class SwingDeskKeyNotifier extends Notifier<int> {
  @override
  int build() => 0;
  void refresh() => state++;
}
final swingDeskKeyProvider =
    NotifierProvider<SwingDeskKeyNotifier, int>(SwingDeskKeyNotifier.new);

/// Focus ladder: per-stock entry positions with LIVE prices (Kite → Yahoo).
/// Reloads whenever the desk reloads, and self-refreshes every 5s while
/// watched so the LTPs and live P/L stay current during market hours.
final swingDeskFocusProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  ref.watch(swingDeskProvider); // desk change → fresh focus ranking
  final api = ref.read(apiServiceProvider);
  final timer = Timer(const Duration(seconds: 5), () => ref.invalidateSelf());
  ref.onDispose(timer.cancel);
  return api.getSwingDeskFocus();
});

/// Daily Pick History: every saved date's picks joined with tracked outcomes.
/// Refreshes whenever the desk changes (a re-analysis can move a pick from
/// "tracking" to "expired" and change its final result).
final swingDailyPickHistoryProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  ref.watch(swingDeskProvider);
  final api = ref.read(apiServiceProvider);
  return api.getSwingDailyPickHistory();
});

/// Selectable scan universes (Nifty 50 / 500 / Total Market) + the current one.
/// Not autoDispose: the picker sits in a header that rebuilds often, and the
/// list only changes when the user picks a different index.
final swingUniverseProvider =
    FutureProvider<Map<String, dynamic>>((ref) async {
  final api = ref.read(apiServiceProvider);
  return api.getSwingUniverses();
});

final swingPaperStatusProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  ref.watch(swingPaperKeyProvider);
  final api = ref.read(apiServiceProvider);
  return api.getSwingPaperStatus();
});

class SwingPaperKeyNotifier extends Notifier<int> {
  @override
  int build() => 0;
  void refresh() => state++;
}
final swingPaperKeyProvider = NotifierProvider<SwingPaperKeyNotifier, int>(SwingPaperKeyNotifier.new);
