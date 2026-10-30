/// Conviction & position-size discipline, as served by `/api/conviction/board`.
///
/// The dip panels answer "has this fallen?". This board answers the questions
/// that come first: is it a good business, why do I own it, what would make me
/// sell, is it sized sensibly, and did the last quarterly result meet what I
/// expected? Nothing here is driven by the share price or the average cost.
library;

double? _d(dynamic v) => v is num ? v.toDouble() : null;
String _s(dynamic v) => v == null ? '' : '$v';
List<Map<String, dynamic>> _maps(dynamic v) => v is List
    ? [for (final e in v) if (e is Map) Map<String, dynamic>.from(e)]
    : const [];

class HealthCheck {
  final String key, label, group, unit, status, rule;
  final double? value, score;
  const HealthCheck({
    required this.key,
    required this.label,
    required this.group,
    required this.unit,
    required this.status,
    required this.rule,
    this.value,
    this.score,
  });

  factory HealthCheck.fromJson(Map<String, dynamic> j) => HealthCheck(
        key: _s(j['key']),
        label: _s(j['label']),
        group: _s(j['group']),
        unit: _s(j['unit']),
        status: j['status'] is String ? j['status'] as String : 'unknown',
        rule: _s(j['rule']),
        value: _d(j['value']),
        score: _d(j['score']),
      );

  String get valueText {
    final v = value;
    if (v == null) return '—';
    return switch (unit) {
      '%' => '${v.toStringAsFixed(1)}%',
      'x' => '${v.toStringAsFixed(2)}x',
      'Cr' => '₹${v.toStringAsFixed(0)} Cr',
      _ => v.toStringAsFixed(2),
    };
  }
}

class BusinessHealth {
  final double? score;
  final String grade, gradeLabel;
  final double coverage;
  final bool lowCoverage, financial;
  final List<HealthCheck> checks;
  const BusinessHealth({
    this.score,
    this.grade = 'unknown',
    this.gradeLabel = 'Not enough data',
    this.coverage = 0,
    this.lowCoverage = true,
    this.financial = false,
    this.checks = const [],
  });

  factory BusinessHealth.fromJson(Map<String, dynamic>? j) {
    if (j == null) return const BusinessHealth();
    return BusinessHealth(
      score: _d(j['score']),
      grade: _s(j['grade']).isEmpty ? 'unknown' : _s(j['grade']),
      gradeLabel: _s(j['grade_label']),
      coverage: _d(j['coverage']) ?? 0,
      lowCoverage: j['low_coverage'] == true,
      financial: j['financial'] == true,
      checks: [for (final c in _maps(j['checks'])) HealthCheck.fromJson(c)],
    );
  }
}

class SellTrigger {
  final String text;
  final String? metric, op;
  final double? value, current;
  const SellTrigger({this.text = '', this.metric, this.op, this.value, this.current});

  factory SellTrigger.fromJson(Map<String, dynamic> j) => SellTrigger(
        text: _s(j['text']),
        metric: j['metric'] as String?,
        op: j['op'] as String?,
        value: _d(j['value']),
        current: _d(j['current']),
      );

  bool get automatic => metric != null && op != null && value != null;

  Map<String, dynamic> toJson() => {
        'text': text,
        if (automatic) ...{'metric': metric, 'op': op, 'value': value},
      };
}

class Thesis {
  final String whatItDoes, growthReason, source;
  final double? expectedEpsGrowthPct, expectedSalesGrowthPct;
  final List<SellTrigger> sellTriggers;
  final String? nextReview, writtenAt, updatedAt;
  const Thesis({
    this.whatItDoes = '',
    this.growthReason = '',
    this.source = '',
    this.expectedEpsGrowthPct,
    this.expectedSalesGrowthPct,
    this.sellTriggers = const [],
    this.nextReview,
    this.writtenAt,
    this.updatedAt,
  });

  static Thesis? fromJson(dynamic raw) {
    if (raw is! Map) return null;
    final j = Map<String, dynamic>.from(raw);
    return Thesis(
      whatItDoes: _s(j['what_it_does']),
      growthReason: _s(j['growth_reason']),
      source: _s(j['source']),
      expectedEpsGrowthPct: _d(j['expected_eps_growth_pct']),
      expectedSalesGrowthPct: _d(j['expected_sales_growth_pct']),
      sellTriggers: [
        for (final t in _maps(j['sell_triggers'])) SellTrigger.fromJson(t)
      ],
      nextReview: j['next_review'] as String?,
      writtenAt: j['written_at'] as String?,
      updatedAt: j['updated_at'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'what_it_does': whatItDoes,
        'growth_reason': growthReason,
        'source': source,
        'expected_eps_growth_pct': expectedEpsGrowthPct,
        'expected_sales_growth_pct': expectedSalesGrowthPct,
        'sell_triggers': [for (final t in sellTriggers) t.toJson()],
        'next_review': nextReview,
      };
}

class QuarterResult {
  final String quarter, result;
  final bool manual;
  final String? note;
  const QuarterResult(
      {required this.quarter, required this.result, this.manual = false, this.note});

  factory QuarterResult.fromJson(Map<String, dynamic> j) => QuarterResult(
        quarter: _s(j['quarter']),
        result: _s(j['result']).isEmpty ? 'unknown' : _s(j['result']),
        manual: j['manual'] == true,
        note: j['note'] as String?,
      );
}

class ConvictionRow {
  final String symbol, key, name, instrument;
  final double? weightPct, value;
  final String sizeBand, sizeLabel;
  final BusinessHealth health;
  final Thesis? thesis;
  final String thesisState, thesisLabel;
  final bool borrowedConviction, reviewDue, addAllowed;
  final List<QuarterResult> quarters;
  final String lastResult, lastResultLabel;
  final int missedStreak;
  final List<SellTrigger> firedTriggers;
  final List<String> trendFlags, addBlockers;
  final String action, actionLabel;
  final String? nextReview;

  const ConvictionRow({
    required this.symbol,
    required this.key,
    required this.name,
    this.instrument = 'stock',
    this.weightPct,
    this.value,
    this.sizeBand = 'unknown',
    this.sizeLabel = '',
    this.health = const BusinessHealth(),
    this.thesis,
    this.thesisState = 'missing',
    this.thesisLabel = '',
    this.borrowedConviction = true,
    this.reviewDue = false,
    this.addAllowed = false,
    this.quarters = const [],
    this.lastResult = 'unknown',
    this.lastResultLabel = '',
    this.missedStreak = 0,
    this.firedTriggers = const [],
    this.trendFlags = const [],
    this.addBlockers = const [],
    this.action = 'hold',
    this.actionLabel = '',
    this.nextReview,
  });

  factory ConvictionRow.fromJson(Map<String, dynamic> j) {
    final gate = j['add_gate'] is Map
        ? Map<String, dynamic>.from(j['add_gate'])
        : const <String, dynamic>{};
    return ConvictionRow(
      symbol: _s(j['symbol']),
      key: _s(j['key']),
      name: _s(j['name']),
      instrument: _s(j['instrument']).isEmpty ? 'stock' : _s(j['instrument']),
      weightPct: _d(j['weight_pct']),
      value: _d(j['value']),
      sizeBand: _s(j['size_band']),
      sizeLabel: _s(j['size_label']),
      health: BusinessHealth.fromJson(
          j['health'] is Map ? Map<String, dynamic>.from(j['health']) : null),
      thesis: Thesis.fromJson(j['thesis']),
      thesisState: _s(j['thesis_state']),
      thesisLabel: _s(j['thesis_label']),
      borrowedConviction: j['borrowed_conviction'] == true,
      reviewDue: j['review_due'] == true,
      addAllowed: gate['allowed'] == true,
      addBlockers: [for (final b in (gate['blockers'] as List? ?? const [])) '$b'],
      quarters: [for (final q in _maps(j['quarters'])) QuarterResult.fromJson(q)],
      lastResult: _s(j['last_result']),
      lastResultLabel: _s(j['last_result_label']),
      missedStreak: (j['missed_streak'] as num?)?.toInt() ?? 0,
      firedTriggers: [
        for (final t in _maps(j['fired_triggers'])) SellTrigger.fromJson(t)
      ],
      trendFlags: [for (final f in (j['trend_flags'] as List? ?? const [])) '$f'],
      action: _s(j['action']),
      actionLabel: _s(j['action_label']),
      nextReview: j['next_review'] as String?,
    );
  }

  bool get isEtf => instrument == 'etf';
}

class WatchRow {
  final String symbol, key, name, stage, stageLabel, thesisState;
  final String? addedAt, readyAfter;
  final int? daysWatched;
  final BusinessHealth health;
  final Thesis? thesis;
  final double initialPositionPct;
  const WatchRow({
    required this.symbol,
    required this.key,
    required this.name,
    required this.stage,
    required this.stageLabel,
    required this.thesisState,
    this.addedAt,
    this.readyAfter,
    this.daysWatched,
    this.health = const BusinessHealth(),
    this.thesis,
    this.initialPositionPct = 1,
  });

  factory WatchRow.fromJson(Map<String, dynamic> j) => WatchRow(
        symbol: _s(j['symbol']),
        key: _s(j['key']),
        name: _s(j['name']),
        stage: _s(j['stage']),
        stageLabel: _s(j['stage_label']),
        thesisState: _s(j['thesis_state']),
        addedAt: j['added_at'] as String?,
        readyAfter: j['ready_after'] as String?,
        daysWatched: (j['days_watched'] as num?)?.toInt(),
        health: BusinessHealth.fromJson(
            j['health'] is Map ? Map<String, dynamic>.from(j['health']) : null),
        thesis: Thesis.fromJson(j['thesis']),
        initialPositionPct: _d(j['initial_position_pct']) ?? 1,
      );
}

class ConvictionBoard {
  final String? asOf;
  final Map<String, dynamic> settings, summary, resultsSeason;
  final List<ConvictionRow> holdings;
  final List<WatchRow> watchlist;
  final Map<String, String> triggerMetrics;
  final List<String> triggerOps;

  const ConvictionBoard({
    this.asOf,
    this.settings = const {},
    this.summary = const {},
    this.resultsSeason = const {},
    this.holdings = const [],
    this.watchlist = const [],
    this.triggerMetrics = const {},
    this.triggerOps = const ['<', '<=', '>', '>='],
  });

  static const empty = ConvictionBoard();

  factory ConvictionBoard.fromJson(Map<String, dynamic> j) {
    Map<String, dynamic> m(dynamic v) =>
        v is Map ? Map<String, dynamic>.from(v) : <String, dynamic>{};
    return ConvictionBoard(
      asOf: j['as_of'] as String?,
      settings: m(j['settings']),
      summary: m(j['summary']),
      resultsSeason: m(j['results_season']),
      holdings: [for (final r in _maps(j['holdings'])) ConvictionRow.fromJson(r)],
      watchlist: [for (final w in _maps(j['watchlist'])) WatchRow.fromJson(w)],
      triggerMetrics: {
        for (final e in m(j['trigger_metrics']).entries) e.key: '${e.value}'
      },
      triggerOps: [
        for (final o in (j['trigger_ops'] as List? ?? const ['<', '<=', '>', '>='])) '$o'
      ],
    );
  }

  bool get isEmpty => holdings.isEmpty && watchlist.isEmpty;
  int count(String key) => (summary[key] as num?)?.toInt() ?? 0;
  double setting(String key, double fallback) =>
      (settings[key] as num?)?.toDouble() ?? fallback;
}
