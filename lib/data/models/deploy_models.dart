/// Models for the capital-deployment dashboard.
///
/// Pure Dart — no Riverpod, no Flutter. That keeps them unit-testable without a
/// `ProviderContainer` or a widget pump.
///
/// The one rule these carry over from the backend: **a null number means
/// UNKNOWN, and unknown is never parsed into 0.** An index whose feed is down
/// and an index sitting at its high must not render identically, and a factor
/// the engine could not judge must not look like a factor that scored zero. So
/// every optional figure here is a nullable `double?`, and [_d] is used only
/// where a real default is genuinely correct.
library;

// ── parse helpers ─────────────────────────────────────────────────────────

/// Nullable number: preserves "unknown".
double? _dn(dynamic v) {
  if (v == null) return null;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString());
}

/// Number with a default, for fields where absence really does mean zero.
double _d(dynamic v, [double fallback = 0]) => _dn(v) ?? fallback;

int _i(dynamic v, [int fallback = 0]) {
  if (v == null) return fallback;
  if (v is num) return v.toInt();
  return int.tryParse(v.toString()) ?? fallback;
}

String _s(dynamic v, [String fallback = '']) => v?.toString() ?? fallback;

List<Map<String, dynamic>> _maps(dynamic v) => v is List
    ? v.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList()
    : const [];

// ══════════════════════════════════════════
//  MARKET TAPE
// ══════════════════════════════════════════

enum IndexGroup { broad, size, bank, sector, commodity, global }

IndexGroup indexGroupFrom(String? raw) => switch (raw) {
      'broad' => IndexGroup.broad,
      'size' => IndexGroup.size,
      'bank' => IndexGroup.bank,
      'sector' => IndexGroup.sector,
      'commodity' => IndexGroup.commodity,
      'global' => IndexGroup.global,
      _ => IndexGroup.broad,
    };

String indexGroupLabel(IndexGroup g) => switch (g) {
      IndexGroup.broad => 'BROAD MARKET',
      IndexGroup.size => 'MIDCAP & SMALLCAP',
      IndexGroup.bank => 'BANKS & FINANCIALS',
      IndexGroup.sector => 'SECTORS',
      IndexGroup.commodity => 'GOLD & SILVER',
      IndexGroup.global => 'GLOBAL',
    };

class IndexQuote {
  final String symbol;
  final String label;
  final IndexGroup group;

  /// False when the feed gave us nothing. Every figure below is then null.
  final bool ok;
  final double? last;

  /// Today's move in index points, signed. The percentage alone hides how big
  /// a 0.4% day is on an index that trades at 76,000.
  ///
  /// Null when the feed holds no adjacent prior session for this index — see
  /// [dayChgSpanDays]. Yahoo serves several NSE sector indices sparsely, and
  /// treating a bar from weeks ago as "yesterday" printed a multi-week move
  /// as a day move.
  final double? dayChg;
  final double? dayChgPct;

  /// Calendar days between the last two bars on record. Above ~4 there is no
  /// session comparison to make, which is why [dayChgPct] is then null.
  final int? dayChgSpanDays;
  final String? lastBarDate, prevBarDate;

  /// The feed is still quoting a live level but stopped serving daily bars,
  /// so every trailing figure on this row is older than it looks.
  final bool staleHistory;

  /// Move since the previous close ON RECORD, over whatever period that is.
  /// Equals [dayChgPct] when the bars are adjacent; on a frozen-history
  /// index it is the multi-week move, which is a real number as long as its
  /// period is stated beside it.
  final double? spanChgPct;

  /// How far below its 1-year high, as a POSITIVE magnitude (0 = at the high).
  final double? offHighPct;

  /// The index has too few closes to HAVE a high and a low, so every
  /// figure derived from that range is withheld rather than reported as zero.
  final bool historyUnavailable;
  final double? high52w;
  final double? low52w;

  /// How far ABOVE the 52-week low the index sits, as a positive percent.
  final double? aboveLowPct;
  final bool atHigh;

  /// True when the series was too short for a real 52-week window.
  final bool shortWindow;

  // ── Trailing returns. Null whenever the series could not reach that far
  // back: a 3-month column filled from a 40-day series would be a 40-day
  // return wearing the wrong label.
  final double? chg1wPct;
  final double? chg1mPct;
  final double? chg3mPct;
  final double? chgYtdPct;

  /// Drawdown from the high of the FULL downloaded series (about ten years),
  /// which is not the same claim as an all-time high — [points] says how much
  /// history it actually covers.
  final double? offMaxHighPct;
  final double? highMax;

  final double? dma50;
  final double? dma100;
  final double? dma200;
  final double? vsDma50Pct;
  final double? vsDma100Pct;
  final double? vsDma200Pct;
  final double? rsi14;

  /// One of extended / fair / attractive / dip / deep_dip / unknown.
  final String marketStatus;

  /// Number of daily closes behind the long-window figures.
  final int points;

  /// Always false today: no feed in use carries historical index P/E or P/B,
  /// so there is nothing to compare a current multiple against. Kept as a
  /// field rather than dropped so the UI renders an explicit "not available"
  /// instead of quietly omitting a metric the dashboard promises.
  final bool valuationAvailable;

  const IndexQuote({
    required this.symbol,
    required this.label,
    required this.group,
    required this.ok,
    this.last,
    this.dayChg,
    this.dayChgPct,
    this.dayChgSpanDays,
    this.lastBarDate,
    this.prevBarDate,
    this.staleHistory = false,
    this.spanChgPct,
    this.offHighPct,
    this.historyUnavailable = false,
    this.high52w,
    this.low52w,
    this.aboveLowPct,
    this.atHigh = false,
    this.shortWindow = false,
    this.chg1wPct,
    this.chg1mPct,
    this.chg3mPct,
    this.chgYtdPct,
    this.offMaxHighPct,
    this.highMax,
    this.dma50,
    this.dma100,
    this.dma200,
    this.vsDma50Pct,
    this.vsDma100Pct,
    this.vsDma200Pct,
    this.rsi14,
    this.marketStatus = 'unknown',
    this.points = 0,
    this.valuationAvailable = false,
  });

  factory IndexQuote.fromJson(Map<String, dynamic> j) => IndexQuote(
        symbol: _s(j['symbol']),
        label: _s(j['label']),
        group: indexGroupFrom(j['group'] as String?),
        ok: j['status'] == 'ok',
        last: _dn(j['last']),
        dayChg: _dn(j['day_chg']),
        dayChgPct: _dn(j['day_chg_pct']),
        dayChgSpanDays: j['day_chg_span_days'] is num
            ? (j['day_chg_span_days'] as num).toInt()
            : null,
        lastBarDate: j['last_bar_date']?.toString(),
        prevBarDate: j['prev_bar_date']?.toString(),
        staleHistory: j['stale_history'] == true,
        spanChgPct: _dn(j['span_chg_pct']),
        offHighPct: _dn(j['off_high_pct']),
        historyUnavailable: j['history_unavailable'] == true,
        high52w: _dn(j['high_52w']),
        low52w: _dn(j['low_52w']),
        aboveLowPct: _dn(j['above_low_pct']),
        atHigh: j['at_high'] == true,
        shortWindow: j['short_window'] == true,
        chg1wPct: _dn(j['chg_1w_pct']),
        chg1mPct: _dn(j['chg_1m_pct']),
        chg3mPct: _dn(j['chg_3m_pct']),
        chgYtdPct: _dn(j['chg_ytd_pct']),
        offMaxHighPct: _dn(j['off_max_high_pct']),
        highMax: _dn(j['high_max']),
        dma50: _dn(j['dma_50']),
        dma100: _dn(j['dma_100']),
        dma200: _dn(j['dma_200']),
        vsDma50Pct: _dn(j['vs_dma_50_pct']),
        vsDma100Pct: _dn(j['vs_dma_100_pct']),
        vsDma200Pct: _dn(j['vs_dma_200_pct']),
        rsi14: _dn(j['rsi_14']),
        marketStatus: _s(j['market_status'], 'unknown'),
        points: _i(j['points']),
        valuationAvailable: j['valuation_status'] == 'ok',
      );

  bool get isUp => (dayChgPct ?? 0) > 0;
  bool get isDown => (dayChgPct ?? 0) < 0;

  /// Whether today's move can be stated at all. False when the feed has no
  /// adjacent prior session, in which case the tile shows no percentage
  /// rather than a stale multi-week move dressed up as a day.
  bool get hasDayChange => dayChgPct != null;

  /// Rough span of the long-window history, for labelling `offMaxHighPct`
  /// honestly as "10-year high" rather than "all-time high".
  int get historyYears => (points / 252).round();

  /// Position relative to a moving average, or null when that DMA is unknown.
  bool? aboveDma(int window) {
    final v = switch (window) {
      50 => vsDma50Pct,
      100 => vsDma100Pct,
      200 => vsDma200Pct,
      _ => null,
    };
    return v == null ? null : v > 0;
  }

  /// Where the level sits in its 52-week band, 0 = on the low, 100 = on the
  /// high. Null whenever the band is unusable, so the bar can render "unknown"
  /// rather than silently pinning to the low.
  double? get rangePct {
    final l = low52w, h = high52w, v = last;
    if (!ok || l == null || h == null || v == null || h <= l) return null;
    return ((v - l) / (h - l) * 100).clamp(0, 100).toDouble();
  }
}

class MarketTape {
  final String asOf;
  final List<IndexQuote> indices;
  final int up;
  final int down;
  final int available;
  final String mood;
  final String summary;
  final bool stale;

  const MarketTape({
    required this.asOf,
    required this.indices,
    this.up = 0,
    this.down = 0,
    this.available = 0,
    this.mood = 'unknown',
    this.summary = '',
    this.stale = false,
  });

  static const empty = MarketTape(asOf: '', indices: []);

  factory MarketTape.fromJson(Map<String, dynamic> j) {
    final breadth = j['breadth'] is Map
        ? Map<String, dynamic>.from(j['breadth'])
        : const <String, dynamic>{};
    return MarketTape(
      asOf: _s(j['as_of']),
      indices: _maps(j['indices']).map(IndexQuote.fromJson).toList(),
      up: _i(breadth['up']),
      down: _i(breadth['down']),
      available: _i(breadth['available']),
      mood: _s(j['market_mood'], 'unknown'),
      summary: _s(j['summary']),
      stale: j['stale'] == true,
    );
  }

  bool get hasData => indices.any((i) => i.ok);

  List<IndexQuote> ofGroup(IndexGroup g) =>
      indices.where((i) => i.group == g).toList();
}

// ══════════════════════════════════════════
//  DEPLOY BOARD
// ══════════════════════════════════════════

enum HoldingKind { fund, stock }

HoldingKind kindFrom(String? raw) =>
    raw == 'stock' ? HoldingKind.stock : HoldingKind.fund;

String kindLabel(HoldingKind k) =>
    k == HoldingKind.fund ? 'Mutual fund' : 'Stock';

/// One factor's contribution to a candidate's score.
class DeployFactor {
  /// 0-100, or null when the engine could not judge this factor at all.
  final double? score;

  /// The real-world magnitude behind the score (e.g. 12.4 for "12.4% below").
  final double? value;
  final String unit;

  const DeployFactor({this.score, this.value, this.unit = ''});

  factory DeployFactor.fromJson(Map<String, dynamic>? j) => j == null
      ? const DeployFactor()
      : DeployFactor(
          score: _dn(j['score']), value: _dn(j['value']), unit: _s(j['unit']));

  bool get known => score != null;
}

class DeployCandidate {
  final HoldingKind kind;
  final String key;
  final String name;
  final String sector;
  final double? price;
  final double units;
  final double value;
  final double? avgCost;
  final String? benchmarkLabel;
  final double? targetPct;
  final double? actualPct;
  final double? gapPp;
  final bool atOrOverTarget;

  /// Null when nothing at all could be judged.
  final double? score;
  final int confidence;
  final bool eligible;
  final Map<String, DeployFactor> factors;
  final List<String> why;
  final List<String> missingFactors;
  final int rank;

  const DeployCandidate({
    required this.kind,
    required this.key,
    required this.name,
    this.sector = '',
    this.price,
    this.units = 0,
    this.value = 0,
    this.avgCost,
    this.benchmarkLabel,
    this.targetPct,
    this.actualPct,
    this.gapPp,
    this.atOrOverTarget = false,
    this.score,
    this.confidence = 0,
    this.eligible = false,
    this.factors = const {},
    this.why = const [],
    this.missingFactors = const [],
    this.rank = 0,
  });

  factory DeployCandidate.fromJson(Map<String, dynamic> j) {
    final raw = j['factors'] is Map
        ? Map<String, dynamic>.from(j['factors'])
        : const <String, dynamic>{};
    return DeployCandidate(
      kind: kindFrom(j['kind'] as String?),
      key: _s(j['key']),
      name: _s(j['name'], _s(j['key'])),
      sector: _s(j['sector']),
      price: _dn(j['price']),
      units: _d(j['units']),
      value: _d(j['value']),
      avgCost: _dn(j['avg_cost']),
      benchmarkLabel: j['benchmark_label'] as String?,
      targetPct: _dn(j['target_pct']),
      actualPct: _dn(j['actual_pct']),
      gapPp: _dn(j['gap_pp']),
      atOrOverTarget: j['at_or_over_target'] == true,
      score: _dn(j['score']),
      confidence: _i(j['confidence']),
      eligible: j['eligible'] == true,
      factors: {
        for (final e in raw.entries)
          e.key: DeployFactor.fromJson(
              e.value is Map ? Map<String, dynamic>.from(e.value) : null)
      },
      why: (j['why'] as List?)?.map((e) => e.toString()).toList() ?? const [],
      missingFactors:
          (j['missing_factors'] as List?)?.map((e) => e.toString()).toList() ??
              const [],
      rank: _i(j['rank']),
    );
  }

  DeployFactor factor(String key) => factors[key] ?? const DeployFactor();
  bool get scored => score != null;
}

/// One line of a proposed split.
class DeploySplit {
  final HoldingKind kind;
  final String key;
  final String label;
  final double amount;
  final double? units;
  final int? shares;
  final double? price;
  final String reason;

  /// Set only on rows that received NOTHING, explaining why.
  final String? skipReason;

  const DeploySplit({
    required this.kind,
    required this.key,
    required this.label,
    required this.amount,
    this.units,
    this.shares,
    this.price,
    this.reason = '',
    this.skipReason,
  });

  factory DeploySplit.fromJson(Map<String, dynamic> j) => DeploySplit(
        kind: kindFrom(j['kind'] as String?),
        key: _s(j['key']),
        label: _s(j['label'], _s(j['name'])),
        amount: _d(j['amount']),
        units: _dn(j['units']),
        shares: j['shares'] == null ? null : _i(j['shares']),
        price: _dn(j['price']),
        reason: _s(j['reason']),
        skipReason: j['skip_reason'] as String?,
      );

  String get unitsLabel => kind == HoldingKind.stock
      ? '${shares ?? 0} sh'
      : '${(units ?? 0).toStringAsFixed(3)} units';
}

class DeploySuggestion {
  final double amount;
  final List<DeploySplit> splits;
  final List<DeploySplit> skipped;
  final double allocated;
  final double unallocated;
  final String? unallocatedReason;
  final double? minTicketNeeded;

  const DeploySuggestion({
    this.amount = 0,
    this.splits = const [],
    this.skipped = const [],
    this.allocated = 0,
    this.unallocated = 0,
    this.unallocatedReason,
    this.minTicketNeeded,
  });

  factory DeploySuggestion.fromJson(Map<String, dynamic> j) => DeploySuggestion(
        amount: _d(j['amount']),
        splits: _maps(j['allocations']).map(DeploySplit.fromJson).toList(),
        skipped: _maps(j['skipped']).map(DeploySplit.fromJson).toList(),
        allocated: _d(j['allocated']),
        unallocated: _d(j['unallocated']),
        unallocatedReason: j['unallocated_reason'] as String?,
        minTicketNeeded: _dn(j['min_ticket_needed']),
      );

  bool get hasSplits => splits.isNotEmpty;
}

// ══════════════════════════════════════════
//  SIP PLAN
// ══════════════════════════════════════════

enum SipStatus { done, partial, scheduled, due, overdue, unknown, inactive }

SipStatus sipStatusFrom(String? raw) => switch (raw) {
      'done' => SipStatus.done,
      'partial' => SipStatus.partial,
      'scheduled' => SipStatus.scheduled,
      'due' => SipStatus.due,
      'overdue' => SipStatus.overdue,
      'inactive' => SipStatus.inactive,
      _ => SipStatus.unknown,
    };

String sipStatusLabel(SipStatus s) => switch (s) {
      SipStatus.done => 'DONE',
      SipStatus.partial => 'PARTIAL',
      SipStatus.scheduled => 'DUE',
      SipStatus.due => 'DUE NOW',
      SipStatus.overdue => 'OVERDUE',
      SipStatus.inactive => 'PAUSED',
      SipStatus.unknown => 'UNKNOWN',
    };

class SipLeg {
  final String? id;
  final HoldingKind kind;
  final String key;
  final String label;
  final double amount;
  final int dueDay;
  final bool active;
  final SipStatus status;
  final double deployedThisMonth;
  final double shortfall;
  final int? daysToDue;
  final int? daysOverdue;
  final bool missingHolding;

  const SipLeg({
    this.id,
    required this.kind,
    required this.key,
    required this.label,
    this.amount = 0,
    this.dueDay = 1,
    this.active = true,
    this.status = SipStatus.unknown,
    this.deployedThisMonth = 0,
    this.shortfall = 0,
    this.daysToDue,
    this.daysOverdue,
    this.missingHolding = false,
  });

  factory SipLeg.fromJson(Map<String, dynamic> j) => SipLeg(
        id: j['id'] as String?,
        kind: kindFrom(j['kind'] as String?),
        key: _s(j['key']),
        label: _s(j['label'], _s(j['key'])),
        amount: _d(j['amount']),
        dueDay: _i(j['due_day'], 1),
        active: j['active'] != false,
        status: sipStatusFrom(j['status'] as String?),
        deployedThisMonth: _d(j['deployed_this_month']),
        shortfall: _d(j['shortfall']),
        daysToDue: j['days_to_due'] == null ? null : _i(j['days_to_due']),
        daysOverdue: j['days_overdue'] == null ? null : _i(j['days_overdue']),
        missingHolding: j['missing_holding'] == true,
      );

  Map<String, dynamic> toJson() => {
        if (id != null) 'id': id,
        'kind': kind == HoldingKind.fund ? 'fund' : 'stock',
        'key': key,
        'amount': amount,
        'due_day': dueDay,
        'active': active,
      };

  SipLeg copyWith({double? amount, int? dueDay, bool? active}) => SipLeg(
        id: id,
        kind: kind,
        key: key,
        label: label,
        amount: amount ?? this.amount,
        dueDay: dueDay ?? this.dueDay,
        active: active ?? this.active,
        status: status,
        deployedThisMonth: deployedThisMonth,
        shortfall: shortfall,
        daysToDue: daysToDue,
        daysOverdue: daysOverdue,
        missingHolding: missingHolding,
      );
}

class SipPlanStatus {
  final String month;
  final List<SipLeg> legs;
  final double budgetTotal;
  final double deployedTotal;
  final double remaining;
  final int doneCount;
  final int totalCount;

  const SipPlanStatus({
    this.month = '',
    this.legs = const [],
    this.budgetTotal = 0,
    this.deployedTotal = 0,
    this.remaining = 0,
    this.doneCount = 0,
    this.totalCount = 0,
  });

  factory SipPlanStatus.fromJson(Map<String, dynamic> j) => SipPlanStatus(
        month: _s(j['month']),
        legs: _maps(j['legs']).map(SipLeg.fromJson).toList(),
        budgetTotal: _d(j['budget_total']),
        deployedTotal: _d(j['deployed_total']),
        remaining: _d(j['remaining']),
        doneCount: _i(j['done_count']),
        totalCount: _i(j['total_count']),
      );

  bool get hasPlan => legs.isNotEmpty;
  List<SipLeg> get needingAction => legs
      .where((l) =>
          l.active &&
          (l.status == SipStatus.overdue ||
              l.status == SipStatus.due ||
              l.status == SipStatus.partial))
      .toList();
}

// ══════════════════════════════════════════
//  BOARD + PLAN CONFIG
// ══════════════════════════════════════════

class DeployAlert {
  final String level;
  final String msg;
  const DeployAlert({required this.level, required this.msg});

  factory DeployAlert.fromJson(Map<String, dynamic> j) =>
      DeployAlert(level: _s(j['level'], 'info'), msg: _s(j['msg']));
}

class DeployBoard {
  final String asOf;
  final double totalValue;
  final List<DeployCandidate> candidates;
  final DeploySuggestion suggestion;
  final SipPlanStatus sipPlan;
  final List<DeployAlert> alerts;
  final bool targetsConfigured;
  final double targetsSumPct;
  final String? targetsWarning;
  final String marketMood;
  final String indicesSummary;

  const DeployBoard({
    this.asOf = '',
    this.totalValue = 0,
    this.candidates = const [],
    this.suggestion = const DeploySuggestion(),
    this.sipPlan = const SipPlanStatus(),
    this.alerts = const [],
    this.targetsConfigured = false,
    this.targetsSumPct = 0,
    this.targetsWarning,
    this.marketMood = 'unknown',
    this.indicesSummary = '',
  });

  static const empty = DeployBoard();

  factory DeployBoard.fromJson(Map<String, dynamic> j) {
    final targets = j['targets'] is Map
        ? Map<String, dynamic>.from(j['targets'])
        : const <String, dynamic>{};
    return DeployBoard(
      asOf: _s(j['as_of']),
      totalValue: _d(j['total_value']),
      candidates: _maps(j['candidates']).map(DeployCandidate.fromJson).toList(),
      suggestion: DeploySuggestion.fromJson(j['suggestion'] is Map
          ? Map<String, dynamic>.from(j['suggestion'])
          : const {}),
      sipPlan: SipPlanStatus.fromJson(j['sip_plan'] is Map
          ? Map<String, dynamic>.from(j['sip_plan'])
          : const {}),
      alerts: _maps(j['alerts']).map(DeployAlert.fromJson).toList(),
      targetsConfigured: targets['configured'] == true,
      targetsSumPct: _d(targets['sum_pct']),
      targetsWarning: targets['warning'] as String?,
      marketMood: _s(j['market_mood'], 'unknown'),
      indicesSummary: _s(j['indices_summary']),
    );
  }

  bool get hasData => candidates.isNotEmpty;

  /// Candidates worth showing as buy-more ideas, best first.
  List<DeployCandidate> get ranked => candidates;
}

class DeployPlanConfig {
  final List<SipLeg> legs;
  final Map<String, double> targets;
  final List<SipLeg> suggestedLegs;
  final Map<String, double> suggestedTargets;
  final List<String> fundKeys;
  final List<String> stockKeys;
  final double monthlyBudget;

  const DeployPlanConfig({
    this.legs = const [],
    this.targets = const {},
    this.suggestedLegs = const [],
    this.suggestedTargets = const {},
    this.fundKeys = const [],
    this.stockKeys = const [],
    this.monthlyBudget = 30000,
  });

  static const empty = DeployPlanConfig();

  factory DeployPlanConfig.fromJson(Map<String, dynamic> j) {
    Map<String, double> pcts(dynamic v) => v is Map
        ? {
            for (final e in v.entries)
              e.key.toString(): _d(e.value),
          }
        : <String, double>{};
    final holdings = j['holdings'] is Map
        ? Map<String, dynamic>.from(j['holdings'])
        : const <String, dynamic>{};
    List<String> keys(dynamic v) =>
        v is List ? v.map((e) => e.toString()).toList() : const <String>[];

    return DeployPlanConfig(
      legs: _maps(j['sip_legs']).map(SipLeg.fromJson).toList(),
      targets: pcts(j['targets']),
      suggestedLegs: _maps(j['suggested_legs']).map(SipLeg.fromJson).toList(),
      suggestedTargets: pcts(j['suggested_targets']),
      fundKeys: keys(holdings['funds']),
      stockKeys: keys(holdings['stocks']),
      monthlyBudget: _d(j['monthly_budget'], 30000),
    );
  }

  bool get isConfigured => legs.isNotEmpty || targets.isNotEmpty;
}
