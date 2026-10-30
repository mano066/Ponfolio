/// Models for the dip-buying panels: per-stock analysis, per-fund buy zones,
/// and the ten-year threshold backtest.
///
/// Pure Dart — no Riverpod, no Flutter, so these stay unit-testable without a
/// `ProviderContainer` or a widget pump.
///
/// Same rule as [deploy_models]: **a null number means UNKNOWN, and unknown is
/// never parsed into 0.** It matters more here than anywhere else in the app.
/// A stock whose fundamentals failed to download must not render identically
/// to one whose fundamentals are genuinely bad, and a backtest horizon with no
/// completed observations must not show a confident 0%.
library;

// ── parse helpers ─────────────────────────────────────────────────────────

double? _dn(dynamic v) {
  if (v == null) return null;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString());
}

int _i(dynamic v, [int fallback = 0]) {
  if (v == null) return fallback;
  if (v is num) return v.toInt();
  return int.tryParse(v.toString()) ?? fallback;
}

String _s(dynamic v, [String fallback = '']) => v?.toString() ?? fallback;

List<Map<String, dynamic>> _maps(dynamic v) => v is List
    ? v.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList()
    : const [];

List<String> _strings(dynamic v) =>
    v is List ? v.map((e) => e.toString()).toList() : const [];

Map<String, dynamic> _map(dynamic v) =>
    v is Map ? Map<String, dynamic>.from(v) : const {};

// ══════════════════════════════════════════
//  REASON FOR FALL
// ══════════════════════════════════════════

/// Why a stock is down — the distinction the whole stock panel exists to draw.
///
/// A 20% fall alongside a sector that fell 18% is [marketWide] and may be an
/// opportunity. The same 20% fall against a flat sector is not, and a 20% fall
/// on collapsing earnings is [deterioration], which blocks averaging outright.
enum FallReason {
  marketWide,
  companySoft,
  uncertain,
  deterioration,
  notFalling,
  corporateAction,
  unknown,
}

FallReason fallReasonFrom(String? key) => switch (key) {
      'market_wide' => FallReason.marketWide,
      'company_soft' => FallReason.companySoft,
      'uncertain' => FallReason.uncertain,
      'deterioration' => FallReason.deterioration,
      'not_falling' => FallReason.notFalling,
      'corporate_action' => FallReason.corporateAction,
      _ => FallReason.unknown,
    };

/// What to do about a holding. [doNotAverage] is a hard verdict from the
/// backend's deterioration gate, not a low score — it cannot be outvoted by
/// the arithmetic.
enum DipAction { accumulate, consider, watch, avoid, doNotAverage }

DipAction dipActionFrom(String? key) => switch (key) {
      'accumulate' => DipAction.accumulate,
      'consider' => DipAction.consider,
      'avoid' => DipAction.avoid,
      'do_not_average' => DipAction.doNotAverage,
      _ => DipAction.watch,
    };

class ReasonForFall {
  final FallReason reason;
  final String label;
  final String emoji;
  final String why;

  /// How much worse than its own benchmark the stock has fallen, in points.
  /// Null when there is no benchmark to measure against — and null must NOT be
  /// read as "no excess", which would blame the company for a market fall.
  final double? excessDrawdownPp;

  final List<String> deteriorationFlags;
  final List<String> severeHeadlines;
  final int headlinesChecked;

  const ReasonForFall({
    required this.reason,
    required this.label,
    required this.emoji,
    required this.why,
    this.excessDrawdownPp,
    this.deteriorationFlags = const [],
    this.severeHeadlines = const [],
    this.headlinesChecked = 0,
  });

  factory ReasonForFall.fromJson(Map<String, dynamic> j) {
    final news = _map(j['news']);
    return ReasonForFall(
      reason: fallReasonFrom(j['reason'] as String?),
      label: _s(j['label']),
      emoji: _s(j['emoji']),
      why: _s(j['why']),
      excessDrawdownPp: _dn(j['excess_drawdown_pp']),
      deteriorationFlags: _strings(j['deterioration_flags']),
      severeHeadlines: _strings(news['severe_headlines']),
      headlinesChecked: _i(news['checked']),
    );
  }

  static const empty = ReasonForFall(
    reason: FallReason.unknown,
    label: 'Not enough information',
    emoji: '—',
    why: '',
  );
}

// ══════════════════════════════════════════
//  STOCK DIP
// ══════════════════════════════════════════

class StockDip {
  final String symbol;
  final String name;
  final double? price;
  final double? avgCost;
  final double? drawdownPct;
  final String benchmarkLabel;
  final double? benchmarkDrawdownPct;

  /// Composite 0-100 over whichever factors were known. Null when nothing was.
  final double? score;

  /// Share of total factor weight that was actually measurable. A high score
  /// at low confidence is one loud factor, not a verdict.
  final double confidence;
  final bool lowConfidence;

  final Map<String, double?> factors;
  final ReasonForFall reasonForFall;
  final bool averagingBlocked;
  final bool corporateActionSuspected;
  final DipAction action;
  final String actionLabel;
  final String actionEmoji;

  /// One-word chips, each derived from a sub-score that already exists so a
  /// chip can never disagree with the number it came from. Every one has an
  /// "unknown" state — for several real holdings the fundamentals simply do
  /// not download, and a chip reading "Stable" for a company nobody measured
  /// would be the most misleading thing on the screen.
  final String health;
  final String healthLabel;
  final String valuation;
  final String valuationLabel;
  final String newsSentiment;
  final String newsLabel;

  /// The single thing most likely to break this holding. Null when there is
  /// nothing specific to say — a risk line on every card teaches the reader
  /// to skip it.
  final String? mainRisk;

  /// Two or three checkable lines. Allowed to include the unflattering one.
  final List<String> reasons;

  const StockDip({
    required this.symbol,
    required this.name,
    required this.confidence,
    required this.factors,
    required this.reasonForFall,
    required this.action,
    required this.actionLabel,
    required this.actionEmoji,
    this.price,
    this.avgCost,
    this.drawdownPct,
    this.benchmarkLabel = '',
    this.benchmarkDrawdownPct,
    this.score,
    this.lowConfidence = false,
    this.averagingBlocked = false,
    this.corporateActionSuspected = false,
    this.health = 'unknown',
    this.healthLabel = 'Not available',
    this.valuation = 'unknown',
    this.valuationLabel = 'Not available',
    this.newsSentiment = 'unknown',
    this.newsLabel = 'Not checked',
    this.mainRisk,
    this.reasons = const [],
  });

  factory StockDip.fromJson(Map<String, dynamic> j) {
    final raw = _map(j['factors']);
    return StockDip(
      symbol: _s(j['symbol']),
      name: _s(j['name'], _s(j['symbol'])),
      price: _dn(j['price']),
      avgCost: _dn(j['avg_cost']),
      drawdownPct: _dn(j['drawdown_pct']),
      benchmarkLabel: _s(j['benchmark_label']),
      benchmarkDrawdownPct: _dn(j['benchmark_drawdown_pct']),
      score: _dn(j['score']),
      confidence: _dn(j['confidence']) ?? 0,
      lowConfidence: j['low_confidence'] == true,
      factors: {for (final e in raw.entries) e.key: _dn(e.value)},
      reasonForFall: j['reason_for_fall'] is Map
          ? ReasonForFall.fromJson(_map(j['reason_for_fall']))
          : ReasonForFall.empty,
      averagingBlocked: j['averaging_blocked'] == true,
      corporateActionSuspected: j['corporate_action_suspected'] == true,
      action: dipActionFrom(j['action'] as String?),
      actionLabel: _s(j['action_label']),
      actionEmoji: _s(j['action_emoji']),
      health: _s(j['health'], 'unknown'),
      healthLabel: _s(j['health_label'], 'Not available'),
      valuation: _s(j['valuation'], 'unknown'),
      valuationLabel: _s(j['valuation_label'], 'Not available'),
      newsSentiment: _s(j['news_sentiment'], 'unknown'),
      newsLabel: _s(j['news_label'], 'Not checked'),
      mainRisk: j['main_risk'] == null ? null : _s(j['main_risk']),
      reasons: _strings(j['reasons']),
    );
  }

  /// Profit or loss against the user's own cost, in percent. Null unless both
  /// sides are known.
  double? get plPct {
    final p = price, c = avgCost;
    if (p == null || c == null || c <= 0) return null;
    return (p - c) / c * 100;
  }

  /// True when the panel is deliberately withholding a buy verdict rather
  /// than having judged the holding and found it wanting.
  bool get isUnjudged =>
      corporateActionSuspected ||
      reasonForFall.reason == FallReason.unknown ||
      lowConfidence;
}

class StockDipBoard {
  final String asOf;
  final List<StockDip> stocks;
  final int blockedCount;
  final int corporateActionCount;

  /// Why valuation-versus-history is missing everywhere. Surfaced rather than
  /// hidden: a promised metric that silently vanishes reads as a bug.
  final String valuationNote;
  final bool sectorPeAvailable;

  const StockDipBoard({
    required this.asOf,
    required this.stocks,
    this.blockedCount = 0,
    this.corporateActionCount = 0,
    this.valuationNote = '',
    this.sectorPeAvailable = false,
  });

  factory StockDipBoard.fromJson(Map<String, dynamic> j) => StockDipBoard(
        asOf: _s(j['as_of']),
        stocks: _maps(j['stocks']).map(StockDip.fromJson).toList(),
        blockedCount: _i(j['blocked_count']),
        corporateActionCount: _i(j['corporate_action_count']),
        valuationNote: _s(j['valuation_note']),
        sectorPeAvailable: j['sector_pe_available'] == true,
      );

  static const empty = StockDipBoard(asOf: '', stocks: []);

  bool get isEmpty => stocks.isEmpty;

  /// Only holdings the panel is actually recommending, best first.
  List<StockDip> get buyable => stocks
      .where((s) =>
          s.action == DipAction.accumulate || s.action == DipAction.consider)
      .toList();
}

// ══════════════════════════════════════════
//  FUND DIP
// ══════════════════════════════════════════

/// What ten years of history measured at one drawdown depth on one benchmark.
class ZoneEvidence {
  final bool tested;
  final bool reliable;
  final int? signals;
  final double? forwardMeanPct;

  /// Signal minus baseline, in points. **Negative is common and is the whole
  /// point** — a zone must be able to argue against itself.
  final double? edgePp;
  final String note;

  const ZoneEvidence({
    required this.tested,
    required this.reliable,
    required this.note,
    this.signals,
    this.forwardMeanPct,
    this.edgePp,
  });

  factory ZoneEvidence.fromJson(Map<String, dynamic> j) => ZoneEvidence(
        tested: j['tested'] == true,
        reliable: j['reliable'] == true,
        signals: j['signals'] == null ? null : _i(j['signals']),
        forwardMeanPct: _dn(j['forward_mean_pct']),
        edgePp: _dn(j['edge_pp']),
        note: _s(j['note']),
      );

  /// True only when the depth was tested, rests on enough episodes, AND beat
  /// simply buying on a random day.
  bool get supportsBuying =>
      tested && reliable && edgePp != null && edgePp! > 0;
}

class BuyZone {
  final String zone;
  final String label;
  final double depthPct;
  final double navAtOrBelow;
  final bool reached;
  final double? distancePct;
  final ZoneEvidence evidence;

  const BuyZone({
    required this.zone,
    required this.label,
    required this.depthPct,
    required this.navAtOrBelow,
    required this.reached,
    required this.evidence,
    this.distancePct,
  });

  factory BuyZone.fromJson(Map<String, dynamic> j) => BuyZone(
        zone: _s(j['zone']),
        label: _s(j['label']),
        depthPct: _dn(j['depth_pct']) ?? 0,
        navAtOrBelow: _dn(j['nav_at_or_below']) ?? 0,
        reached: j['reached'] == true,
        distancePct: _dn(j['distance_pct']),
        evidence: ZoneEvidence.fromJson(_map(j['evidence'])),
      );
}

class PurchaseRange {
  final int buys;
  final double? lowestBuyNav;
  final double? highestBuyNav;
  final double? weightedAvgNav;
  final double? highLowRatio;
  final String positionLabel;
  final double? vsAvgPct;

  /// Present whenever the position could be misread as a valuation. Shown
  /// verbatim: "below my average" is a fact about the user's own history and
  /// says nothing about whether the fund is cheap.
  final String? caution;

  const PurchaseRange({
    required this.buys,
    required this.positionLabel,
    this.lowestBuyNav,
    this.highestBuyNav,
    this.weightedAvgNav,
    this.highLowRatio,
    this.vsAvgPct,
    this.caution,
  });

  factory PurchaseRange.fromJson(
          Map<String, dynamic> purchase, Map<String, dynamic> position) =>
      PurchaseRange(
        buys: _i(purchase['buys']),
        lowestBuyNav: _dn(purchase['lowest_buy_nav']),
        highestBuyNav: _dn(purchase['highest_buy_nav']),
        weightedAvgNav: _dn(purchase['weighted_avg_nav']),
        highLowRatio: _dn(purchase['high_low_ratio']),
        positionLabel: _s(position['label']),
        vsAvgPct: _dn(position['vs_avg_pct']),
        caution: position['caution'] == null ? null : _s(position['caution']),
      );

  bool get hasHistory => buys > 0;
}

class FundDip {
  final String schemeName;
  final String category;
  final double? nav;
  final double? returnPct;

  /// Yahoo symbol, used to pair a fund with its backtest study.
  final String benchmark;
  final String benchmarkLabel;
  final double? benchmarkDrawdownPct;
  final double? peakNav;

  /// True when the peak is only the user's own highest purchase (or today's
  /// NAV), not the fund's real all-time peak. Zones built on it are weaker and
  /// the UI must not present them as though they were the real thing.
  final bool peakIsPurchaseHigh;

  /// 0-100 over whichever factors were measurable. Null when none were.
  final double? score;
  final double confidence;
  final bool lowConfidence;
  final Map<String, double?> factors;

  /// add / attractive / watch / wait / none.
  final String action;
  final String actionLabel;
  final String actionEmoji;

  /// Two or three checkable lines, including — deliberately — the line that
  /// argues against the score when history does not support the depth.
  final List<String> reasons;

  /// True when the category has fallen far enough that a discount and a
  /// repricing look the same. Shown beside the score, never instead of it.
  final bool deepFallRisk;
  final double? ownDrawdownPct;

  final PurchaseRange purchase;
  final List<BuyZone> zones;
  final String? nextTriggerLabel;
  final double? nextTriggerNav;
  final double? nextTriggerFallPct;

  const FundDip({
    required this.schemeName,
    required this.category,
    required this.purchase,
    required this.zones,
    this.nav,
    this.returnPct,
    this.benchmark = '',
    this.benchmarkLabel = '',
    this.benchmarkDrawdownPct,
    this.peakNav,
    this.peakIsPurchaseHigh = false,
    this.score,
    this.confidence = 0,
    this.lowConfidence = false,
    this.factors = const {},
    this.action = 'watch',
    this.actionLabel = 'Watch',
    this.actionEmoji = '',
    this.reasons = const [],
    this.deepFallRisk = false,
    this.ownDrawdownPct,
    this.nextTriggerLabel,
    this.nextTriggerNav,
    this.nextTriggerFallPct,
  });

  factory FundDip.fromJson(Map<String, dynamic> j) {
    final trigger = _map(j['next_trigger']);
    return FundDip(
      schemeName: _s(j['scheme_name']),
      category: _s(j['category']),
      nav: _dn(j['nav']),
      returnPct: _dn(j['return_pct']),
      benchmark: _s(j['benchmark']),
      benchmarkLabel: _s(j['benchmark_label']),
      benchmarkDrawdownPct: _dn(j['benchmark_drawdown_pct']),
      peakNav: _dn(j['peak_nav']),
      peakIsPurchaseHigh: j['peak_is_purchase_high'] == true,
      purchase:
          PurchaseRange.fromJson(_map(j['purchase']), _map(j['position'])),
      zones: _maps(j['zones']).map(BuyZone.fromJson).toList(),
      nextTriggerLabel: trigger.isEmpty ? null : _s(trigger['label']),
      nextTriggerNav: _dn(trigger['nav_at_or_below']),
      nextTriggerFallPct: _dn(trigger['fall_needed_pct']),
      score: _dn(j['score']),
      confidence: _dn(j['confidence']) ?? 0,
      lowConfidence: j['low_confidence'] == true,
      factors: {
        for (final e in _map(j['factors']).entries) e.key: _dn(e.value)
      },
      action: _s(j['action'], 'watch'),
      actionLabel: _s(j['action_label'], 'Watch'),
      actionEmoji: _s(j['action_emoji']),
      reasons: _strings(j['reasons']),
      deepFallRisk: j['deep_fall_risk'] == true,
      ownDrawdownPct: _dn(j['own_drawdown_pct']),
    );
  }

  /// Zones the NAV has already fallen into, deepest first.
  List<BuyZone> get reachedZones =>
      zones.where((z) => z.reached).toList().reversed.toList();

  bool get inABuyZone => zones.any((z) => z.reached);
}

class FundDipBoard {
  final String asOf;
  final List<FundDip> funds;

  const FundDipBoard({required this.asOf, required this.funds});

  factory FundDipBoard.fromJson(Map<String, dynamic> j) => FundDipBoard(
        asOf: _s(j['as_of']),
        funds: _maps(j['funds']).map(FundDip.fromJson).toList(),
      );

  static const empty = FundDipBoard(asOf: '', funds: []);

  bool get isEmpty => funds.isEmpty;

  /// Funds ranked by opportunity, best first. Unknown scores sort last —
  /// they were never candidates for the top of the list.
  List<FundDip> get ranked {
    final out = [...funds];
    out.sort((a, b) => (b.score ?? -1).compareTo(a.score ?? -1));
    return out;
  }

  /// One tile per category, so "Small Cap is more attractive than Large Cap"
  /// is readable before any individual fund is. A category takes the score of
  /// its best fund rather than an average: averaging would let one fund at
  /// its high mask another in a genuine correction.
  List<CategoryTile> get categories {
    final byCategory = <String, List<FundDip>>{};
    for (final f in funds) {
      (byCategory[f.category.isEmpty ? 'Other' : f.category] ??= []).add(f);
    }
    final tiles = byCategory.entries.map((e) {
      final best = e.value.reduce(
          (a, b) => (a.score ?? -1) >= (b.score ?? -1) ? a : b);
      return CategoryTile(
        category: e.key,
        fundCount: e.value.length,
        score: best.score,
        benchmarkLabel: best.benchmarkLabel,
        benchmarkDrawdownPct: best.benchmarkDrawdownPct,
        action: best.action,
        actionLabel: best.actionLabel,
      );
    }).toList();
    tiles.sort((a, b) => (b.score ?? -1).compareTo(a.score ?? -1));
    return tiles;
  }
}

/// One category tile: "SMALL CAP  -14.6%  Score 82  ATTRACTIVE".
class CategoryTile {
  final String category;
  final int fundCount;
  final double? score;
  final String benchmarkLabel;
  final double? benchmarkDrawdownPct;
  final String action;
  final String actionLabel;

  const CategoryTile({
    required this.category,
    required this.fundCount,
    required this.action,
    required this.actionLabel,
    this.score,
    this.benchmarkLabel = '',
    this.benchmarkDrawdownPct,
  });
}

// ══════════════════════════════════════════
//  BACKTEST
// ══════════════════════════════════════════

class ForwardStats {
  final int n;
  final double? meanPct;
  final double? medianPct;
  final double? positiveRatePct;
  final double? worstPct;
  final double? worstDrawdownPct;

  const ForwardStats({
    required this.n,
    this.meanPct,
    this.medianPct,
    this.positiveRatePct,
    this.worstPct,
    this.worstDrawdownPct,
  });

  factory ForwardStats.fromJson(Map<String, dynamic> j) => ForwardStats(
        n: _i(j['n']),
        meanPct: _dn(j['mean_pct']),
        medianPct: _dn(j['median_pct']),
        positiveRatePct: _dn(j['positive_rate_pct']),
        worstPct: _dn(j['worst_pct']),
        worstDrawdownPct: _dn(j['worst_drawdown_pct']),
      );

  static const unknown = ForwardStats(n: 0);

  /// No completed observations yet. The caller must render a dash, not a zero.
  bool get isUnknown => n == 0 || meanPct == null;
}

class ThresholdStudy {
  final double thresholdPct;
  final int signals;
  final bool reliable;
  final Map<String, ForwardStats> forward;
  final Map<String, double?> edgePp;

  const ThresholdStudy({
    required this.thresholdPct,
    required this.signals,
    required this.reliable,
    required this.forward,
    required this.edgePp,
  });

  factory ThresholdStudy.fromJson(Map<String, dynamic> j) {
    final fwd = _map(j['forward']);
    final edge = _map(j['edge']);
    return ThresholdStudy(
      thresholdPct: _dn(j['threshold_pct']) ?? 0,
      signals: _i(j['signals']),
      reliable: j['reliable'] == true,
      forward: {
        for (final e in fwd.entries)
          e.key: ForwardStats.fromJson(Map<String, dynamic>.from(e.value as Map))
      },
      edgePp: {
        for (final e in edge.entries)
          e.key: _dn(Map<String, dynamic>.from(e.value as Map)['mean_pp'])
      },
    );
  }

  ForwardStats at(String horizon) => forward[horizon] ?? ForwardStats.unknown;

  /// The only honest read of a dip threshold: did it beat buying on a random
  /// day, on enough separate episodes to mean anything?
  bool beatsBaseline(String horizon) {
    final e = edgePp[horizon];
    return reliable && e != null && e > 0;
  }
}

class BenchmarkStudy {
  final String symbol;
  final String label;
  final bool ok;
  final double years;
  final double? currentDrawdownPct;
  final double? activeThresholdPct;
  final double? bestThresholdPct;
  final Map<String, ForwardStats> baseline;
  final List<ThresholdStudy> thresholds;

  /// Bars discarded before a split. Non-zero means the study covers less than
  /// the decade it asked for, and the UI should say so.
  final int historyTrimmed;
  final String note;

  const BenchmarkStudy({
    required this.symbol,
    required this.label,
    required this.ok,
    required this.years,
    required this.baseline,
    required this.thresholds,
    this.currentDrawdownPct,
    this.activeThresholdPct,
    this.bestThresholdPct,
    this.historyTrimmed = 0,
    this.note = '',
  });

  factory BenchmarkStudy.fromJson(Map<String, dynamic> j) {
    final base = _map(j['baseline']);
    return BenchmarkStudy(
      symbol: _s(j['symbol']),
      label: _s(j['label']),
      ok: j['status'] == 'ok',
      years: _dn(j['years']) ?? 0,
      currentDrawdownPct: _dn(j['current_drawdown_pct']),
      activeThresholdPct: _dn(j['active_threshold_pct']),
      bestThresholdPct: _dn(j['best_threshold_pct']),
      baseline: {
        for (final e in base.entries)
          e.key: ForwardStats.fromJson(Map<String, dynamic>.from(e.value as Map))
      },
      thresholds: _maps(j['thresholds']).map(ThresholdStudy.fromJson).toList(),
      historyTrimmed: _i(_map(j['history'])['dropped']),
      note: _s(j['note']),
    );
  }

  ForwardStats baselineAt(String horizon) =>
      baseline[horizon] ?? ForwardStats.unknown;

  /// The row matching the drawdown the index is actually in today.
  ThresholdStudy? get activeStudy {
    final t = activeThresholdPct;
    if (t == null) return null;
    for (final s in thresholds) {
      if (s.thresholdPct == t) return s;
    }
    return null;
  }
}

class DipBacktest {
  final String asOf;
  final List<String> horizons;
  final List<BenchmarkStudy> studies;
  final int minSignalsForReliable;

  const DipBacktest({
    required this.asOf,
    required this.horizons,
    required this.studies,
    this.minSignalsForReliable = 5,
  });

  factory DipBacktest.fromJson(Map<String, dynamic> j) => DipBacktest(
        asOf: _s(j['as_of']),
        horizons: _strings(j['horizons']),
        studies: _maps(j['studies']).map(BenchmarkStudy.fromJson).toList(),
        minSignalsForReliable: _i(j['min_signals_for_reliable'], 5),
      );

  static const empty = DipBacktest(asOf: '', horizons: [], studies: []);

  BenchmarkStudy? bySymbol(String symbol) {
    for (final s in studies) {
      if (s.symbol == symbol) return s;
    }
    return null;
  }
}


// ══════════════════════════════════════════
//  TODAY'S OPPORTUNITIES
// ══════════════════════════════════════════

/// One row in the master decision bar.
class OpportunityRow {
  /// buy / add / watch / avoid.
  final String action;
  final String label;
  final String emoji;

  /// fund or stock — decides which detail sheet a tap opens.
  final String kind;
  final String key;
  final String name;
  final String subtitle;
  final double? score;
  final double? price;
  final String priceLabel;

  /// e.g. "14.6% off high". Null when there is no drawdown to state.
  final String? metric;

  /// The one line of argument behind the row. A score with nothing behind it
  /// is not something anyone should act on in five seconds.
  final String? why;

  final bool lowConfidence;

  const OpportunityRow({
    required this.action,
    required this.label,
    required this.emoji,
    required this.kind,
    required this.key,
    required this.name,
    this.subtitle = '',
    this.score,
    this.price,
    this.priceLabel = '',
    this.metric,
    this.why,
    this.lowConfidence = false,
  });

  factory OpportunityRow.fromJson(Map<String, dynamic> j) => OpportunityRow(
        action: _s(j['action']),
        label: _s(j['label']),
        emoji: _s(j['emoji']),
        kind: _s(j['kind']),
        key: _s(j['key']),
        name: _s(j['name'], _s(j['key'])),
        subtitle: _s(j['subtitle']),
        score: _dn(j['score']),
        price: _dn(j['price']),
        priceLabel: _s(j['price_label']),
        metric: j['metric'] == null ? null : _s(j['metric']),
        why: j['why'] == null ? null : _s(j['why']),
        lowConfidence: j['low_confidence'] == true,
      );

  bool get isRisk => action == 'avoid';
  bool get isBuy => action == 'buy' || action == 'add';
}

/// The one-word read on the market shown at the left of the master bar.
class MarketSignal {
  final String signal;
  final String label;
  final String emoji;

  /// Exactly one sentence. Never a paragraph.
  final String summary;
  final double? broadOffHighPct;
  final double? smallcapOffHighPct;
  final double? midcapOffHighPct;

  const MarketSignal({
    required this.signal,
    required this.label,
    required this.emoji,
    required this.summary,
    this.broadOffHighPct,
    this.smallcapOffHighPct,
    this.midcapOffHighPct,
  });

  factory MarketSignal.fromJson(Map<String, dynamic> j) => MarketSignal(
        signal: _s(j['signal'], 'unknown'),
        label: _s(j['label'], 'Not available'),
        emoji: _s(j['emoji']),
        summary: _s(j['summary']),
        broadOffHighPct: _dn(j['broad_off_high_pct']),
        smallcapOffHighPct: _dn(j['smallcap_off_high_pct']),
        midcapOffHighPct: _dn(j['midcap_off_high_pct']),
      );

  static const unknown = MarketSignal(
    signal: 'unknown',
    label: 'Not available',
    emoji: '—',
    summary: 'Market levels are not available right now.',
  );
}

class OpportunityBoard {
  final String asOf;

  /// "actionable" or "quiet". Quiet is a normal answer, not an error: the
  /// measured backtest says most days offer nothing, and a bar that
  /// manufactures a BUY every morning is not merely useless but wrong.
  final String status;
  final String? headline;
  final String? detail;
  final MarketSignal market;
  final List<OpportunityRow> rows;
  final int buyCount;
  final int riskCount;

  const OpportunityBoard({
    required this.asOf,
    required this.status,
    required this.market,
    required this.rows,
    this.headline,
    this.detail,
    this.buyCount = 0,
    this.riskCount = 0,
  });

  factory OpportunityBoard.fromJson(Map<String, dynamic> j) =>
      OpportunityBoard(
        asOf: _s(j['as_of']),
        status: _s(j['status'], 'quiet'),
        headline: j['headline'] == null ? null : _s(j['headline']),
        detail: j['detail'] == null ? null : _s(j['detail']),
        market: j['market'] is Map
            ? MarketSignal.fromJson(_map(j['market']))
            : MarketSignal.unknown,
        rows: _maps(j['rows']).map(OpportunityRow.fromJson).toList(),
        buyCount: _i(j['buy_count']),
        riskCount: _i(j['risk_count']),
      );

  static const empty = OpportunityBoard(
    asOf: '',
    status: 'quiet',
    market: MarketSignal.unknown,
    rows: [],
  );

  bool get isQuiet => status != 'actionable';
}
