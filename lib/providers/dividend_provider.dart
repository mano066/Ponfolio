import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/api_service.dart';
import 'providers.dart';
import 'allocation_provider.dart';

// ══════════════════════════════════════════
//  DIVIDEND TIERS
// ══════════════════════════════════════════

/// Quality tier assigned to each payer by the backend classifier.
enum DividendTier { anchor, grower, modest, trap, none }

DividendTier tierFromString(String? raw) {
  switch (raw) {
    case 'anchor':
      return DividendTier.anchor;
    case 'grower':
      return DividendTier.grower;
    case 'modest':
      return DividendTier.modest;
    case 'trap':
      return DividendTier.trap;
    default:
      return DividendTier.none;
  }
}

// ══════════════════════════════════════════
//  MODELS
// ══════════════════════════════════════════

class DividendStock {
  final String symbol;
  final String sector;
  final String mcapClass;
  final double shares;
  final double price;
  final double avgCost;
  final double value;
  final double dps;
  final String dpsSource;
  final double annualIncome;
  final double monthlyIncome;
  final double yieldPct;
  final double yieldOnCost;
  final double payoutRatio;
  final double growthCagr;
  final int yearsPaid;
  final DividendTier tier;
  final String tierLabel;
  final String reason;
  final bool tdsApplicable;
  final Map<int, double> payoutMonths;

  const DividendStock({
    required this.symbol,
    required this.sector,
    required this.mcapClass,
    required this.shares,
    required this.price,
    required this.avgCost,
    required this.value,
    required this.dps,
    required this.dpsSource,
    required this.annualIncome,
    required this.monthlyIncome,
    required this.yieldPct,
    required this.yieldOnCost,
    required this.payoutRatio,
    required this.growthCagr,
    required this.yearsPaid,
    required this.tier,
    required this.tierLabel,
    required this.reason,
    required this.tdsApplicable,
    required this.payoutMonths,
  });

  factory DividendStock.fromJson(Map<String, dynamic> j) => DividendStock(
        symbol: j['symbol']?.toString() ?? '',
        sector: j['sector']?.toString() ?? 'Other',
        mcapClass: j['mcap_class']?.toString() ?? 'Unknown',
        shares: _d(j['shares']),
        price: _d(j['price']),
        avgCost: _d(j['avg_cost']),
        value: _d(j['value']),
        dps: _d(j['dps']),
        dpsSource: j['dps_source']?.toString() ?? 'none',
        annualIncome: _d(j['annual_income']),
        monthlyIncome: _d(j['monthly_income']),
        yieldPct: _d(j['yield_pct']),
        yieldOnCost: _d(j['yield_on_cost']),
        payoutRatio: _d(j['payout_ratio']),
        growthCagr: _d(j['growth_cagr']),
        yearsPaid: _i(j['years_paid']),
        tier: tierFromString(j['tier']?.toString()),
        tierLabel: j['tier_label']?.toString() ?? '',
        reason: j['reason']?.toString() ?? '',
        tdsApplicable: j['tds_applicable'] == true,
        payoutMonths: _monthMap(j['payout_months']),
      );

  /// Where the DPS figure came from, in words — shown so a number the user
  /// can't reconcile with their broker statement is always explainable.
  String get dpsSourceLabel {
    switch (dpsSource) {
      case 'manual':
        return 'Your override';
      case 'history_ttm':
        return 'Trailing 12 months';
      case 'history_last_fy':
        return 'Last full FY';
      case 'provider_rate':
        return 'Declared rate';
      case 'provider_trailing':
        return 'Provider trailing';
      default:
        return 'No data';
    }
  }
}

class DividendFund {
  final String schemeName;
  final String category;
  final String plan;
  final bool distributes;
  final double value;
  final double invested;
  final double lookthroughYield;
  final double lookthroughIncome;
  final double cashIncome;
  final double monthlyIncome;
  final String note;

  const DividendFund({
    required this.schemeName,
    required this.category,
    required this.plan,
    required this.distributes,
    required this.value,
    required this.invested,
    required this.lookthroughYield,
    required this.lookthroughIncome,
    required this.cashIncome,
    required this.monthlyIncome,
    required this.note,
  });

  factory DividendFund.fromJson(Map<String, dynamic> j) => DividendFund(
        schemeName: j['scheme_name']?.toString() ?? '',
        category: j['category']?.toString() ?? 'Unknown',
        plan: j['plan']?.toString() ?? 'Growth',
        distributes: j['distributes'] == true,
        value: _d(j['value']),
        invested: _d(j['invested']),
        lookthroughYield: _d(j['lookthrough_yield']),
        lookthroughIncome: _d(j['lookthrough_income']),
        cashIncome: _d(j['cash_income']),
        monthlyIncome: _d(j['monthly_income']),
        note: j['note']?.toString() ?? '',
      );
}

class DividendGoal {
  final double annual;
  final double monthly;
  final double achievedPct;
  final double gapAnnual;
  final double gapMonthly;
  final bool onTrack;
  final int? yearsToGoal;
  final int? goalYear;
  final double assumedGrowthPct;
  final double assumedNewMoneyYieldPct;
  final double monthlyInvestment;
  final double sipNeeded3y;
  final double sipNeeded5y;
  final double sipNeeded10y;

  const DividendGoal({
    required this.annual,
    required this.monthly,
    required this.achievedPct,
    required this.gapAnnual,
    required this.gapMonthly,
    required this.onTrack,
    required this.yearsToGoal,
    required this.goalYear,
    required this.assumedGrowthPct,
    required this.assumedNewMoneyYieldPct,
    required this.monthlyInvestment,
    required this.sipNeeded3y,
    required this.sipNeeded5y,
    required this.sipNeeded10y,
  });

  factory DividendGoal.fromJson(Map<String, dynamic> j) => DividendGoal(
        annual: _d(j['annual']),
        monthly: _d(j['monthly']),
        achievedPct: _d(j['achieved_pct']),
        gapAnnual: _d(j['gap_annual']),
        gapMonthly: _d(j['gap_monthly']),
        onTrack: j['on_track'] == true,
        yearsToGoal: j['years_to_goal'] == null ? null : _i(j['years_to_goal']),
        goalYear: j['goal_year'] == null ? null : _i(j['goal_year']),
        assumedGrowthPct: _d(j['assumed_dividend_growth_pct']),
        assumedNewMoneyYieldPct: _d(j['assumed_new_money_yield_pct']),
        monthlyInvestment: _d(j['monthly_investment']),
        sipNeeded3y: _d(j['sip_needed_3y']),
        sipNeeded5y: _d(j['sip_needed_5y']),
        sipNeeded10y: _d(j['sip_needed_10y']),
      );

  static const empty = DividendGoal(
    annual: 120000, monthly: 10000, achievedPct: 0, gapAnnual: 120000,
    gapMonthly: 10000, onTrack: false, yearsToGoal: null, goalYear: null,
    assumedGrowthPct: 8, assumedNewMoneyYieldPct: 4, monthlyInvestment: 0,
    sipNeeded3y: 0, sipNeeded5y: 0, sipNeeded10y: 0,
  );
}

class DividendIncome {
  final double annualGross;
  final double monthlyGross;
  final double annualNet;
  final double monthlyNet;
  final double taxSlabPct;
  final double fromStocks;
  final double fromFunds;
  final double reinvestedInFunds;
  final double blendedYield;
  final double yieldOnCost;
  final double totalValue;
  final double incomeBearingValue;
  final double incomeBearingPct;
  final int payerCount;
  final int nonPayerCount;
  final List<String> nonPayers;

  const DividendIncome({
    required this.annualGross,
    required this.monthlyGross,
    required this.annualNet,
    required this.monthlyNet,
    required this.taxSlabPct,
    required this.fromStocks,
    required this.fromFunds,
    required this.reinvestedInFunds,
    required this.blendedYield,
    required this.yieldOnCost,
    required this.totalValue,
    required this.incomeBearingValue,
    required this.incomeBearingPct,
    required this.payerCount,
    required this.nonPayerCount,
    required this.nonPayers,
  });

  factory DividendIncome.fromJson(Map<String, dynamic> j) => DividendIncome(
        annualGross: _d(j['annual_gross']),
        monthlyGross: _d(j['monthly_gross']),
        annualNet: _d(j['annual_net']),
        monthlyNet: _d(j['monthly_net']),
        taxSlabPct: _d(j['tax_slab_pct']),
        fromStocks: _d(j['from_stocks']),
        fromFunds: _d(j['from_funds']),
        reinvestedInFunds: _d(j['reinvested_in_funds']),
        blendedYield: _d(j['blended_yield']),
        yieldOnCost: _d(j['yield_on_cost']),
        totalValue: _d(j['total_value']),
        incomeBearingValue: _d(j['income_bearing_value']),
        incomeBearingPct: _d(j['income_bearing_pct']),
        payerCount: _i(j['payer_count']),
        nonPayerCount: _i(j['non_payer_count']),
        nonPayers:
            (j['non_payers'] as List? ?? []).map((e) => e.toString()).toList(),
      );

  static const empty = DividendIncome(
    annualGross: 0, monthlyGross: 0, annualNet: 0, monthlyNet: 0,
    taxSlabPct: 30, fromStocks: 0, fromFunds: 0, reinvestedInFunds: 0,
    blendedYield: 0, yieldOnCost: 0, totalValue: 0, incomeBearingValue: 0,
    incomeBearingPct: 0, payerCount: 0, nonPayerCount: 0, nonPayers: [],
  );
}

class CorpusRung {
  final double yieldPct;
  final double corpusRequired;
  final String realism;

  const CorpusRung({
    required this.yieldPct,
    required this.corpusRequired,
    required this.realism,
  });

  factory CorpusRung.fromJson(Map<String, dynamic> j) => CorpusRung(
        yieldPct: _d(j['yield_pct']),
        corpusRequired: _d(j['corpus_required']),
        realism: j['realism']?.toString() ?? '',
      );
}

class ProjectionYear {
  final int year;
  final int offset;
  final double annualIncome;
  final double monthlyIncome;
  final double corpus;
  final double goalPct;
  final bool goalReached;

  const ProjectionYear({
    required this.year,
    required this.offset,
    required this.annualIncome,
    required this.monthlyIncome,
    required this.corpus,
    required this.goalPct,
    required this.goalReached,
  });

  factory ProjectionYear.fromJson(Map<String, dynamic> j) => ProjectionYear(
        year: _i(j['year']),
        offset: _i(j['offset']),
        annualIncome: _d(j['annual_income']),
        monthlyIncome: _d(j['monthly_income']),
        corpus: _d(j['corpus']),
        goalPct: _d(j['goal_pct']),
        goalReached: j['goal_reached'] == true,
      );
}

class SectorIncome {
  final String sector;
  final double income;
  final double pct;

  const SectorIncome(
      {required this.sector, required this.income, required this.pct});

  factory SectorIncome.fromJson(Map<String, dynamic> j) => SectorIncome(
        sector: j['sector']?.toString() ?? 'Other',
        income: _d(j['income']),
        pct: _d(j['pct']),
      );
}

class DividendBook {
  final String asOf;
  final DividendGoal goal;
  final DividendIncome income;
  final List<CorpusRung> corpusLadder;
  final List<ProjectionYear> projection;
  final List<DividendStock> stocks;
  final List<DividendFund> funds;
  final List<SectorIncome> bySector;
  final List<DividendStock> anchors;
  final List<DividendStock> growers;
  final List<DividendStock> traps;
  final List<double> calendar; // 12 entries, Jan..Dec
  final List<Map<String, dynamic>> alerts;
  final String dpsBasis;

  const DividendBook({
    required this.asOf,
    required this.goal,
    required this.income,
    required this.corpusLadder,
    required this.projection,
    required this.stocks,
    required this.funds,
    required this.bySector,
    required this.anchors,
    required this.growers,
    required this.traps,
    required this.calendar,
    required this.alerts,
    required this.dpsBasis,
  });

  factory DividendBook.fromJson(Map<String, dynamic> j) {
    List<DividendStock> stocksAt(String key) =>
        (j[key] as List? ?? [])
            .map((e) => DividendStock.fromJson(Map<String, dynamic>.from(e)))
            .toList();

    final cal = List<double>.filled(12, 0);
    for (final entry in (j['calendar'] as List? ?? [])) {
      final m = _i((entry as Map)['month']);
      if (m >= 1 && m <= 12) cal[m - 1] = _d(entry['amount']);
    }

    return DividendBook(
      asOf: j['as_of']?.toString() ?? '',
      goal: DividendGoal.fromJson(
          Map<String, dynamic>.from(j['goal'] as Map? ?? {})),
      income: DividendIncome.fromJson(
          Map<String, dynamic>.from(j['income'] as Map? ?? {})),
      corpusLadder: (j['corpus_ladder'] as List? ?? [])
          .map((e) => CorpusRung.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
      projection: (j['projection'] as List? ?? [])
          .map((e) => ProjectionYear.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
      stocks: stocksAt('stocks'),
      funds: (j['funds'] as List? ?? [])
          .map((e) => DividendFund.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
      bySector: (j['by_sector'] as List? ?? [])
          .map((e) => SectorIncome.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
      anchors: stocksAt('anchors'),
      growers: stocksAt('growers'),
      traps: stocksAt('traps'),
      calendar: cal,
      alerts: (j['alerts'] as List? ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList(),
      dpsBasis:
          (j['disclosure'] as Map?)?['dps_basis']?.toString() ?? '',
    );
  }

  static const empty = DividendBook(
    asOf: '', goal: DividendGoal.empty, income: DividendIncome.empty,
    corpusLadder: [], projection: [], stocks: [], funds: [], bySector: [],
    anchors: [], growers: [], traps: [], calendar: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    alerts: [], dpsBasis: '',
  );

  bool get hasData => stocks.isNotEmpty || funds.isNotEmpty;

  /// Peak month of the payout calendar, or null when nothing is scheduled.
  int? get peakMonth {
    if (calendar.every((v) => v <= 0)) return null;
    var best = 0;
    for (var i = 1; i < calendar.length; i++) {
      if (calendar[i] > calendar[best]) best = i;
    }
    return best + 1;
  }
}

double _d(dynamic v) => v is num ? v.toDouble() : 0.0;
int _i(dynamic v) => v is num ? v.toInt() : 0;

/// Parses `{"8": 21.0}` (JSON object keys are always strings) into `{8: 21.0}`.
Map<int, double> _monthMap(dynamic v) {
  if (v is! Map) return {};
  final out = <int, double>{};
  v.forEach((k, value) {
    final month = k is num ? k.toInt() : int.tryParse(k.toString());
    if (month != null && month >= 1 && month <= 12) {
      out[month] = _d(value);
    }
  });
  return out;
}

// ══════════════════════════════════════════
//  GOAL DRAFT (local what-if, not yet saved)
// ══════════════════════════════════════════

/// Local, unsaved goal inputs.  Editing these re-fetches the book as a preview
/// so the user can see the effect before committing it to the backend.
class DividendGoalDraft {
  final double? goalAnnual;
  final double? monthlyInvestment;

  const DividendGoalDraft({this.goalAnnual, this.monthlyInvestment});

  DividendGoalDraft copyWith({double? goalAnnual, double? monthlyInvestment}) =>
      DividendGoalDraft(
        goalAnnual: goalAnnual ?? this.goalAnnual,
        monthlyInvestment: monthlyInvestment ?? this.monthlyInvestment,
      );

  bool get isEmpty => goalAnnual == null && monthlyInvestment == null;
}

class DividendGoalDraftNotifier extends Notifier<DividendGoalDraft> {
  @override
  DividendGoalDraft build() => const DividendGoalDraft();

  void setGoal(double annual) =>
      state = state.copyWith(goalAnnual: annual.clamp(0, 100000000));

  void setMonthlyInvestment(double monthly) =>
      state = state.copyWith(monthlyInvestment: monthly.clamp(0, 100000000));

  void clear() => state = const DividendGoalDraft();
}

final dividendGoalDraftProvider =
    NotifierProvider<DividendGoalDraftNotifier, DividendGoalDraft>(
  DividendGoalDraftNotifier.new,
);

// ══════════════════════════════════════════
//  DIVIDEND BOOK PROVIDER
// ══════════════════════════════════════════

/// Fetches the dividend book, folding in locally-tracked other assets so the
/// blended yield is measured against the whole portfolio, not just equities.
final dividendBookProvider =
    FutureProvider.autoDispose<DividendBook>((ref) async {
  // Re-fetch whenever holdings or the draft goal change.
  ref.watch(portfolioProvider);
  ref.watch(mfPortfolioProvider);
  final draft = ref.watch(dividendGoalDraftProvider);
  final otherAssets = ref.watch(otherAssetsProvider);
  final otherTotal = otherAssets.values.fold<double>(0, (a, b) => a + b);

  final data = await ApiService().getDividendAnalysis(
    goalAnnual: draft.goalAnnual,
    monthlyInvestment: draft.monthlyInvestment,
    otherAssetsValue: otherTotal,
  );
  return DividendBook.fromJson(data);
});

/// Persists the current draft so it survives a restart.
Future<void> saveDividendGoal(WidgetRef ref) async {
  final draft = ref.read(dividendGoalDraftProvider);
  if (draft.isEmpty) return;
  await ApiService().saveDividendGoal(
    goalAnnual: draft.goalAnnual,
    monthlyInvestment: draft.monthlyInvestment,
  );
  ref.invalidate(dividendBookProvider);
}
