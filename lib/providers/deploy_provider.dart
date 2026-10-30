import 'dart:async';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/models/deploy_models.dart';
import '../data/models/dip_models.dart';
import 'providers.dart';

/// Providers for the capital-deployment dashboard.
///
/// The board and the plan are cached for offline use; the index tape
/// deliberately is NOT. A stale plan is still your plan, but a stale index level
/// presented as live is simply a lie.

final _rng = Random();

/// How often the dashboard refetches, round the clock.
///
/// One constant rather than four scattered intervals, because the four
/// surfaces must not drift apart: if the tape refreshed on a different clock
/// from the cards, the bar could recommend a level the tape below it no longer
/// showed, and the user would be reading two different moments as one.
///
/// An hour is the deliberate choice. The dip score moves on drawdown, which
/// barely shifts inside an hour, so a faster clock would mostly redraw the
/// same numbers while inviting a reaction to noise — and this app's own
/// backtest is the argument against that. It also means the evening NAV, which
/// AMFI publishes once per day after close, shows up within the hour instead
/// of the next morning.
const kDashboardRefresh = Duration(hours: 1);

/// How often the index tape re-reads the market.
///
/// Separate from [kDashboardRefresh], and much shorter, because the two carry
/// different kinds of number. The deploy board is built on 52-week ranges and
/// valuation bands that move slowly; the tape now carries LIVE levels and a
/// day change from Kite, which are stale within minutes.
///
/// An hour was the old interval and it showed: a tape fetched at app start sat
/// unchanged for the rest of the hour, so a backend that had since learned the
/// day change for every sector index went on displaying "no history" on screen
/// with no way for the user to ask again.
///
/// Five minutes costs one Kite quotes call per tick — a single request
/// covering all 28 instruments — so the rate limit that previously cost a
/// login is nowhere near.
///
/// Now fifteen seconds: between full rebuilds the backend lays ONE batched
/// Kite quotes call over the cached tape, at most every 15s and only while NSE
/// is in session (`_refresh_index_tape_live`). Out of session, or without
/// Kite, the poll is answered from cache and costs nothing upstream.
const kMarketTapeRefresh = Duration(seconds: 15);

// ══════════════════════════════════════════
//  MARKET TAPE  (polling)
// ══════════════════════════════════════════

/// Live index tape.
///
/// Uses the emit-immediately idiom (`Stream.fromFuture(...).asyncExpand`) rather
/// than a bare `Stream.periodic`, which would leave the tape blank for a full
/// poll interval on first paint — the mistake `niftyProvider` makes.
final marketTapeProvider = StreamProvider<MarketTape>((ref) {
  final api = ref.read(apiServiceProvider);

  Future<MarketTape> fetch() async {
    try {
      return MarketTape.fromJson(await api.getMarketIndices());
    } catch (_) {
      // The tape is public market data — it works in guest mode too. A failure
      // degrades to "no data", which renders as grey chips, never as zeros.
      return MarketTape.empty;
    }
  }

  return Stream.fromFuture(fetch()).asyncExpand((first) async* {
    yield first;
    yield* Stream.periodic(kMarketTapeRefresh, (_) => null)
        .asyncMap((_) => fetch());
  });
});

// ══════════════════════════════════════════
//  DEPLOY BOARD
// ══════════════════════════════════════════

/// A refresh request: which generation, and whether the user asked for it.
///
/// The two are carried together because they mean different things to the
/// server. An automatic hourly tick is happy with the server's cache; a person
/// pressing Update is not — they pressed it precisely because they want the
/// current number, so that request sets `force` and bypasses the TTL.
class RefreshRequest {
  final int generation;
  final bool manual;
  const RefreshRequest(this.generation, this.manual);
}

/// Bumped after a successful write, and by the Update button.
class DeployRefreshNotifier extends Notifier<RefreshRequest> {
  @override
  RefreshRequest build() => const RefreshRequest(0, false);

  /// A write landed; refetch, but the server cache is fine.
  void refresh() => state = RefreshRequest(state.generation + 1, false);

  /// The user pressed Update; go past the server cache.
  void manualRefresh() => state = RefreshRequest(state.generation + 1, true);
}

final deployRefreshProvider =
    NotifierProvider<DeployRefreshNotifier, RefreshRequest>(
        DeployRefreshNotifier.new);

/// True while any of the three decision surfaces is fetching, so one button
/// can show one spinner rather than three that disagree.
final dashboardRefreshingProvider = Provider<bool>((ref) {
  return ref.watch(opportunitiesProvider).isLoading ||
      ref.watch(fundDipsProvider).isLoading ||
      ref.watch(stockDipsProvider).isLoading;
});

/// The amount the user typed into the hero box. 0 means "nothing to split yet".
class DeployAmountNotifier extends Notifier<double> {
  @override
  double build() => 0;
  void set(double v) => state = v < 0 ? 0 : v;
  void clear() => state = 0;
}

final deployAmountProvider =
    NotifierProvider<DeployAmountNotifier, double>(DeployAmountNotifier.new);

/// The ranked board, including a split for whatever amount is currently typed.
///
/// Watching [deployAmountProvider] here means typing a new amount re-proposes
/// the split without a second endpoint — the backend scores and allocates in one
/// pass, so there is nothing to gain from separating them.
final deployBoardProvider =
    FutureProvider.autoDispose<DeployBoard>((ref) async {
  if (ref.watch(isGuestProvider)) return DeployBoard.empty;
  ref.watch(deployRefreshProvider);
  final amount = ref.watch(deployAmountProvider);

  final api = ref.read(apiServiceProvider);
  return DeployBoard.fromJson(await api.getDeployBoard(amount: amount));
});

// ══════════════════════════════════════════
//  PLAN CONFIG
// ══════════════════════════════════════════

final deployPlanProvider =
    FutureProvider.autoDispose<DeployPlanConfig>((ref) async {
  if (ref.watch(isGuestProvider)) return DeployPlanConfig.empty;
  ref.watch(deployRefreshProvider);
  final api = ref.read(apiServiceProvider);
  return DeployPlanConfig.fromJson(await api.getDeployPlan());
});

// ══════════════════════════════════════════
//  WRITES
// ══════════════════════════════════════════

/// Keys of in-flight writes, so each button can disable only itself.
class DeployBusyNotifier extends Notifier<Set<String>> {
  @override
  Set<String> build() => const {};

  void start(String key) => state = {...state, key};
  void finish(String key) => state = {...state}..remove(key);
  bool isBusy(String key) => state.contains(key);
}

final deployBusyProvider =
    NotifierProvider<DeployBusyNotifier, Set<String>>(DeployBusyNotifier.new);

/// A fresh idempotency key. Generate ONE per confirmation dialog and reuse it
/// across retries — that is what makes a double-submit a server-side no-op.
///
/// Timestamp plus 64 random bits: collisions only matter within one user's log,
/// so this does not need to be a real UUID.
String newDeployRequestId() {
  final now = DateTime.now().microsecondsSinceEpoch.toRadixString(36);
  final salt = List.generate(4, (_) => _rng.nextInt(1 << 16).toRadixString(16))
      .join();
  return 'dep-$now-$salt';
}

/// Record a batch of buys, then refresh everything the write touched.
///
/// Pessimistic on purpose: this mutates cost basis, units and XIRR, so the UI
/// waits for the server rather than guessing and reconciling later.
Future<Map<String, dynamic>> recordDeployment(
  WidgetRef ref, {
  required String requestId,
  required List<DeploySplit> splits,
  String note = '',
}) async {
  final api = ref.read(apiServiceProvider);
  final items = [
    for (final s in splits)
      {
        'kind': s.kind == HoldingKind.fund ? 'fund' : 'stock',
        'key': s.key,
        if (s.kind == HoldingKind.fund) 'amount': s.amount,
        if (s.kind == HoldingKind.stock) 'shares': s.shares ?? 0,
        if (s.price != null) 'price': s.price,
      }
  ];

  final result =
      await api.deployExecute(requestId: requestId, items: items, note: note);

  // Cost basis, units and XIRR all moved — invalidate everything downstream.
  ref.read(deployAmountProvider.notifier).clear();
  ref.invalidate(portfolioProvider);
  ref.invalidate(mfPortfolioProvider);
  ref.invalidate(portfolioXirrProvider);
  ref.read(deployRefreshProvider.notifier).refresh();
  return result;
}

/// Save the SIP plan and/or targets, then refresh the board.
Future<void> saveDeployPlan(
  WidgetRef ref, {
  List<SipLeg>? legs,
  Map<String, double>? targets,
}) async {
  final api = ref.read(apiServiceProvider);
  await api.saveDeployPlan(
    sipLegs: legs?.map((l) => l.toJson()).toList(),
    targets: targets,
  );
  ref.read(deployRefreshProvider.notifier).refresh();
}

// ══════════════════════════════════════════
//  DIP PANELS
// ══════════════════════════════════════════


/// Re-runs [read] on the shared dashboard clock.
///
/// The dip providers previously fetched once and then never again until the
/// user hit refresh, so a dashboard left open all day showed the morning's
/// verdict against the afternoon's tape.
Stream<T> _onDashboardClock<T>(Future<T> Function(bool force) read,
    {bool forceFirst = false}) async* {
  // Only the FIRST read honours `force`. Without that, one press of Update
  // would leave every later hourly tick bypassing the server cache for the
  // rest of the session — turning a deliberate act into a permanent setting.
  yield await read(forceFirst);
  yield* Stream.periodic(kDashboardRefresh, (_) => null)
      .asyncMap((_) => read(false));
}

/// Per-stock dip analysis.
///
/// Fetched once per refresh rather than polled: unlike the tape, this is a
/// verdict built from fundamentals and headlines that change on the scale of
/// quarters, and re-running 19 RSS fetches every twenty seconds would buy
/// nothing but rate limits.
final stockDipsProvider = StreamProvider<StockDipBoard>((ref) {
  // Same gate as deployBoardProvider: this is the user's own holdings, and a
  // guest session must not be shown an analysis of somebody's portfolio just
  // because the backend still has one loaded.
  if (ref.watch(isGuestProvider)) return Stream.value(StockDipBoard.empty);
  final request = ref.watch(deployRefreshProvider);
  final api = ref.read(apiServiceProvider);
  // Deliberately NOT wrapped in a try/catch that returns an empty board.
  // Swallowing the error made a failed fetch render as "No stocks to analyse
  // yet — add equity holdings", which told a user with nineteen holdings to go
  // and add some. "The request failed" and "you own nothing" are different
  // facts and must not share a screen. The error travels in the AsyncValue and
  // the card renders a retry instead.
  return _onDashboardClock(
      (force) async =>
          StockDipBoard.fromJson(await api.getStockDips(force: force)),
      forceFirst: request.manual);
});

/// Per-fund purchase range and buy zones.
final fundDipsProvider = StreamProvider<FundDipBoard>((ref) {
  if (ref.watch(isGuestProvider)) return Stream.value(FundDipBoard.empty);
  final request = ref.watch(deployRefreshProvider);
  final api = ref.read(apiServiceProvider);
  return _onDashboardClock(
      (force) async =>
          FundDipBoard.fromJson(await api.getFundDips(force: force)),
      forceFirst: request.manual);
});

/// Ten-year threshold backtest for the whole index universe.
///
/// Deliberately NOT gated on guest mode: like the index tape, this is public
/// market history with nothing of the user's in it, and it is the one panel
/// that is genuinely useful before signing in.
///
/// Cached hard on the backend (six hours) because it is derived from daily
/// closes that do not move intraday.
/// Not on the hourly clock: it is built from DAILY closes, so an hourly
/// refetch would return the same study at the cost of a decade-long download.
final dipBacktestProvider = FutureProvider<DipBacktest>((ref) async {
  final api = ref.read(apiServiceProvider);
  try {
    return DipBacktest.fromJson(await api.getDipBacktest());
  } catch (_) {
    return DipBacktest.empty;
  }
});

/// The master decision bar.
///
/// Gated on guest mode like the other portfolio providers: it is built from
/// the user's own holdings.
final opportunitiesProvider = StreamProvider<OpportunityBoard>((ref) {
  if (ref.watch(isGuestProvider)) return Stream.value(OpportunityBoard.empty);
  final request = ref.watch(deployRefreshProvider);
  final api = ref.read(apiServiceProvider);
  // Same reasoning as stockDipsProvider: a failed fetch must not render as
  // "no strong dip today", which is a real and meaningful verdict here and
  // would be a lie if nothing was actually measured.
  return _onDashboardClock(
      (force) async =>
          OpportunityBoard.fromJson(await api.getOpportunities(force: force)),
      forceFirst: request.manual);
});
