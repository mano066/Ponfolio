import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/api_service.dart';
import 'providers.dart';

// ══════════════════════════════════════════
//  RISK PROFILE PRESETS
// ══════════════════════════════════════════

enum RiskProfile { conservative, moderate, aggressive }

/// Target allocation percentages per risk profile.
const Map<RiskProfile, Map<String, double>> riskProfileTargets = {
  RiskProfile.conservative: {
    'Large Cap': 55,
    'Mid Cap': 15,
    'Small Cap': 5,
    'Flexi Cap': 5,
    'International': 5,
    'Debt': 10,
    'Gold': 5,
  },
  RiskProfile.moderate: {
    'Large Cap': 45,
    'Mid Cap': 20,
    'Small Cap': 10,
    'Flexi Cap': 10,
    'International': 5,
    'Debt': 5,
    'Gold': 5,
  },
  RiskProfile.aggressive: {
    'Large Cap': 30,
    'Mid Cap': 25,
    'Small Cap': 20,
    'Flexi Cap': 10,
    'International': 5,
    'Debt': 5,
    'Gold': 5,
  },
};

// ══════════════════════════════════════════
//  OTHER ASSETS (manual entries)
// ══════════════════════════════════════════

/// Manages manually-entered asset values (Gold, Cash, International, REITs, Debt).
class OtherAssetsNotifier extends Notifier<Map<String, double>> {
  @override
  Map<String, double> build() {
    final storage = ref.read(localStorageProvider);
    return storage.getOtherAssets();
  }

  void update(String category, double value) {
    final updated = Map<String, double>.from(state);
    if (value <= 0) {
      updated.remove(category);
    } else {
      updated[category] = value;
    }
    state = updated;
    ref.read(localStorageProvider).saveOtherAssets(updated);
  }

  void setAll(Map<String, double> assets) {
    state = Map<String, double>.from(assets);
    ref.read(localStorageProvider).saveOtherAssets(state);
  }
}

final otherAssetsProvider =
    NotifierProvider<OtherAssetsNotifier, Map<String, double>>(
  OtherAssetsNotifier.new,
);

// ══════════════════════════════════════════
//  RISK PROFILE SELECTOR
// ══════════════════════════════════════════

class RiskProfileNotifier extends Notifier<RiskProfile> {
  @override
  RiskProfile build() {
    final storage = ref.read(localStorageProvider);
    final saved = storage.getRiskProfile();
    return RiskProfile.values.firstWhere(
      (r) => r.name == saved,
      orElse: () => RiskProfile.moderate,
    );
  }

  void set(RiskProfile profile) {
    state = profile;
    ref.read(localStorageProvider).saveRiskProfile(profile.name);
  }
}

final riskProfileProvider =
    NotifierProvider<RiskProfileNotifier, RiskProfile>(
  RiskProfileNotifier.new,
);

// ══════════════════════════════════════════
//  CUSTOM TARGETS (user-editable overrides)
// ══════════════════════════════════════════

class CustomTargetsNotifier extends Notifier<Map<String, double>> {
  @override
  Map<String, double> build() {
    final storage = ref.read(localStorageProvider);
    return storage.getCustomTargets() ?? {};
  }

  void update(String category, double value) {
    final updated = Map<String, double>.from(state);
    updated[category] = value.clamp(0, 100);
    state = updated;
    ref.read(localStorageProvider).saveCustomTargets(updated);
  }

  void reset() {
    state = {};
    ref.read(localStorageProvider).saveCustomTargets({});
  }
}

final customTargetsProvider =
    NotifierProvider<CustomTargetsNotifier, Map<String, double>>(
  CustomTargetsNotifier.new,
);

// ══════════════════════════════════════════
//  TARGET ALLOCATION (profile + custom overrides)
// ══════════════════════════════════════════

final targetAllocationProvider = Provider<Map<String, double>>((ref) {
  final profile = ref.watch(riskProfileProvider);
  final defaults = Map<String, double>.from(riskProfileTargets[profile]!);
  final customOverrides = ref.watch(customTargetsProvider);
  // Merge custom overrides on top of defaults
  defaults.addAll(customOverrides);
  return defaults;
});

// ══════════════════════════════════════════
//  ENRICHED DATA MODELS
// ══════════════════════════════════════════

class OverlapHolding {
  final String stock;
  final double totalValue;
  final double exposurePct;
  final int sourceCount;
  final List<Map<String, dynamic>> sources; // [{source: "Fund A", value: 1000}, ...]

  const OverlapHolding({
    required this.stock,
    required this.totalValue,
    required this.exposurePct,
    required this.sourceCount,
    required this.sources,
  });

  factory OverlapHolding.fromJson(Map<String, dynamic> json) => OverlapHolding(
        stock: json['stock'] ?? '',
        totalValue: (json['total_value'] ?? 0).toDouble(),
        exposurePct: (json['exposure_pct'] ?? 0).toDouble(),
        sourceCount: (json['source_count'] ?? 0).toInt(),
        sources: List<Map<String, dynamic>>.from(json['sources'] ?? []),
      );
}

class ConcentrationRisk {
  final double top5Pct;
  final double top10Pct;
  final double topSectorPct;
  final String topSectorName;
  final double singleStockPct;
  final String singleStockName;
  final List<Map<String, dynamic>> alerts;

  const ConcentrationRisk({
    required this.top5Pct,
    required this.top10Pct,
    required this.topSectorPct,
    required this.topSectorName,
    required this.singleStockPct,
    required this.singleStockName,
    required this.alerts,
  });

  factory ConcentrationRisk.fromJson(Map<String, dynamic> json) => ConcentrationRisk(
        top5Pct: (json['top5_pct'] ?? 0).toDouble(),
        top10Pct: (json['top10_pct'] ?? 0).toDouble(),
        topSectorPct: (json['top_sector_pct'] ?? 0).toDouble(),
        topSectorName: json['top_sector_name'] ?? 'N/A',
        singleStockPct: (json['single_stock_pct'] ?? 0).toDouble(),
        singleStockName: json['single_stock_name'] ?? 'N/A',
        alerts: List<Map<String, dynamic>>.from(json['alerts'] ?? []),
      );

  static const empty = ConcentrationRisk(
    top5Pct: 0, top10Pct: 0, topSectorPct: 0, topSectorName: 'N/A',
    singleStockPct: 0, singleStockName: 'N/A', alerts: [],
  );
}

class EnrichedStock {
  final String symbol;
  final String sector;
  final String industry;
  final String mcapClass;
  final double currentPrice;
  final int shares;
  final double avgCost;
  final double invested;
  final double currentValue;
  final double pnl;
  final double pnlPct;
  final int riskScore;

  const EnrichedStock({
    required this.symbol, required this.sector, required this.industry,
    required this.mcapClass, required this.currentPrice, required this.shares,
    required this.avgCost, required this.invested, required this.currentValue,
    required this.pnl, required this.pnlPct, required this.riskScore,
  });

  factory EnrichedStock.fromJson(Map<String, dynamic> json) => EnrichedStock(
        symbol: json['symbol'] ?? '',
        sector: json['sector'] ?? 'Other',
        industry: json['industry'] ?? 'Other',
        mcapClass: json['mcap_class'] ?? 'Mid Cap',
        currentPrice: (json['current_price'] ?? 0).toDouble(),
        shares: (json['shares'] ?? 0).toInt(),
        avgCost: (json['avg_cost'] ?? 0).toDouble(),
        invested: (json['invested'] ?? 0).toDouble(),
        currentValue: (json['current_value'] ?? 0).toDouble(),
        pnl: (json['pnl'] ?? 0).toDouble(),
        pnlPct: (json['pnl_pct'] ?? 0).toDouble(),
        riskScore: (json['risk_score'] ?? 3).toInt(),
      );
}

class EnrichedFund {
  final String schemeName;
  final String category;
  final double invested;
  final double currentValue;
  final double pnl;
  final double returnPct;
  final double xirr;
  final double lcPct;
  final double mcPct;
  final double scPct;
  final String topSector;
  final String style;
  final double overlapScore;
  final int topHoldingsCount;
  final int riskScore;

  const EnrichedFund({
    required this.schemeName, required this.category, required this.invested,
    required this.currentValue, required this.pnl, required this.returnPct,
    required this.xirr, required this.lcPct, required this.mcPct,
    required this.scPct, required this.topSector, required this.style,
    required this.overlapScore, required this.topHoldingsCount, required this.riskScore,
  });

  factory EnrichedFund.fromJson(Map<String, dynamic> json) => EnrichedFund(
        schemeName: json['scheme_name'] ?? '',
        category: json['category'] ?? 'Unknown',
        invested: (json['invested'] ?? 0).toDouble(),
        currentValue: (json['current_value'] ?? 0).toDouble(),
        pnl: (json['pnl'] ?? 0).toDouble(),
        returnPct: (json['return_pct'] ?? 0).toDouble(),
        xirr: (json['xirr'] ?? 0).toDouble(),
        lcPct: (json['lc_pct'] ?? 0).toDouble(),
        mcPct: (json['mc_pct'] ?? 0).toDouble(),
        scPct: (json['sc_pct'] ?? 0).toDouble(),
        topSector: json['top_sector'] ?? 'N/A',
        style: json['style'] ?? 'Blend',
        overlapScore: (json['overlap_score'] ?? 0).toDouble(),
        topHoldingsCount: (json['top_holdings_count'] ?? 0).toInt(),
        riskScore: (json['risk_score'] ?? 3).toInt(),
      );
}

class SectorDetail {
  final String sector;
  final double currentPct;
  final double targetPct;
  final double delta;
  final String status;
  final String riskRating;
  final double value;

  const SectorDetail({
    required this.sector, required this.currentPct, required this.targetPct,
    required this.delta, required this.status, required this.riskRating,
    required this.value,
  });

  factory SectorDetail.fromJson(Map<String, dynamic> json) => SectorDetail(
        sector: json['sector'] ?? '',
        currentPct: (json['current_pct'] ?? 0).toDouble(),
        targetPct: (json['target_pct'] ?? 0).toDouble(),
        delta: (json['delta'] ?? 0).toDouble(),
        status: json['status'] ?? 'Neutral',
        riskRating: json['risk_rating'] ?? 'Medium',
        value: (json['value'] ?? 0).toDouble(),
      );
}

class TopHolding {
  final String stock;
  final double value;
  final double pct;
  final int sourceCount;

  const TopHolding({
    required this.stock, required this.value, required this.pct, required this.sourceCount,
  });

  factory TopHolding.fromJson(Map<String, dynamic> json) => TopHolding(
        stock: json['stock'] ?? '',
        value: (json['value'] ?? 0).toDouble(),
        pct: (json['pct'] ?? 0).toDouble(),
        sourceCount: (json['source_count'] ?? 0).toInt(),
      );
}

// ══════════════════════════════════════════
//  EXPOSURE ANALYSIS DATA
// ══════════════════════════════════════════

class ExposureAnalysis {
  final double totalValue;
  final double totalStockValue;
  final double totalMfValue;
  final int uniqueHoldings;

  // True market-cap exposure
  final Map<String, double> mcapExposure;
  final Map<String, double> mcapValues;

  // True sector exposure
  final Map<String, double> sectorExposure;
  final List<SectorDetail> sectorDetails;

  // Overlap
  final double overlapPct;
  final double duplicatePct;
  final double hiddenConcentrationPct;
  final List<OverlapHolding> overlapHoldings;

  // Concentration risk
  final ConcentrationRisk concentration;

  // Enriched
  final List<EnrichedStock> enrichedStocks;
  final List<EnrichedFund> enrichedFunds;
  final List<TopHolding> topHoldings;

  // Sector drill-down holdings
  final Map<String, List<Map<String, dynamic>>> sectorHoldings;

  // Overlap source names for grid columns
  final List<String> overlapSourceNames;

  const ExposureAnalysis({
    required this.totalValue, required this.totalStockValue, required this.totalMfValue,
    required this.uniqueHoldings, required this.mcapExposure, required this.mcapValues,
    required this.sectorExposure, required this.sectorDetails, required this.overlapPct,
    required this.duplicatePct, required this.hiddenConcentrationPct,
    required this.overlapHoldings, required this.concentration,
    required this.enrichedStocks, required this.enrichedFunds, required this.topHoldings,
    required this.sectorHoldings, required this.overlapSourceNames,
  });

  factory ExposureAnalysis.fromJson(Map<String, dynamic> json) {
    final overlap = json['overlap'] as Map<String, dynamic>? ?? {};
    return ExposureAnalysis(
      totalValue: (json['total_value'] ?? 0).toDouble(),
      totalStockValue: (json['total_stock_value'] ?? 0).toDouble(),
      totalMfValue: (json['total_mf_value'] ?? 0).toDouble(),
      uniqueHoldings: (json['unique_holdings'] ?? 0).toInt(),
      mcapExposure: _toDoubleMap(json['mcap_exposure']),
      mcapValues: _toDoubleMap(json['mcap_values']),
      sectorExposure: _toDoubleMap(json['sector_exposure']),
      sectorDetails: (json['sector_details'] as List? ?? [])
          .map((e) => SectorDetail.fromJson(e as Map<String, dynamic>))
          .toList(),
      overlapPct: (overlap['overlap_pct'] ?? 0).toDouble(),
      duplicatePct: (overlap['duplicate_pct'] ?? 0).toDouble(),
      hiddenConcentrationPct: (overlap['hidden_concentration_pct'] ?? 0).toDouble(),
      overlapHoldings: (overlap['holdings'] as List? ?? [])
          .map((e) => OverlapHolding.fromJson(e as Map<String, dynamic>))
          .toList(),
      concentration: ConcentrationRisk.fromJson(
          json['concentration'] as Map<String, dynamic>? ?? {}),
      enrichedStocks: (json['enriched_stocks'] as List? ?? [])
          .map((e) => EnrichedStock.fromJson(e as Map<String, dynamic>))
          .toList(),
      enrichedFunds: (json['enriched_funds'] as List? ?? [])
          .map((e) => EnrichedFund.fromJson(e as Map<String, dynamic>))
          .toList(),
      topHoldings: (json['top_holdings'] as List? ?? [])
          .map((e) => TopHolding.fromJson(e as Map<String, dynamic>))
          .toList(),
      sectorHoldings: _parseSectorHoldings(json['sector_holdings']),
      overlapSourceNames: (json['overlap_source_names'] as List? ?? [])
          .map((e) => e.toString())
          .toList(),
    );
  }

  static const empty = ExposureAnalysis(
    totalValue: 0, totalStockValue: 0, totalMfValue: 0, uniqueHoldings: 0,
    mcapExposure: {}, mcapValues: {}, sectorExposure: {}, sectorDetails: [],
    overlapPct: 0, duplicatePct: 0, hiddenConcentrationPct: 0,
    overlapHoldings: [], concentration: ConcentrationRisk.empty,
    enrichedStocks: [], enrichedFunds: [], topHoldings: [],
    sectorHoldings: const {}, overlapSourceNames: const [],
  );
}

Map<String, double> _toDoubleMap(dynamic data) {
  if (data is Map) {
    return data.map((k, v) => MapEntry(k.toString(), (v ?? 0).toDouble()));
  }
  return {};
}

Map<String, List<Map<String, dynamic>>> _parseSectorHoldings(dynamic data) {
  if (data is! Map) return {};
  final result = <String, List<Map<String, dynamic>>>{};
  data.forEach((key, value) {
    if (value is List) {
      result[key.toString()] = value
          .map((e) => e is Map ? Map<String, dynamic>.from(e) : <String, dynamic>{})
          .toList();
    }
  });
  return result;
}

// ══════════════════════════════════════════
//  EXPOSURE ANALYSIS PROVIDER (async)
// ══════════════════════════════════════════

final exposureAnalysisProvider = FutureProvider.autoDispose<ExposureAnalysis>((ref) async {
  // Also depend on portfolio/mf changes to auto-refresh
  ref.watch(portfolioProvider);
  ref.watch(mfPortfolioProvider);
  try {
    final data = await ApiService().getExposureAnalysis();
    return ExposureAnalysis.fromJson(data);
  } catch (_) {
    return ExposureAnalysis.empty;
  }
});

// ══════════════════════════════════════════
//  ALLOCATION DATA MODEL
// ══════════════════════════════════════════

class AllocationData {
  // ── Portfolio summary ──
  final double totalPortfolioValue;
  final double totalInvested;
  final double totalPnl;
  final double totalPnlPct;

  // ── Category breakdown (values) ──
  final double equityValue;
  final double mfValue;
  final double goldValue;
  final double cashValue;
  final double debtValue;
  final double internationalValue;
  final double reitsValue;

  // ── Market-cap breakdown (values) ──
  final Map<String, double> marketCapValues;  // 'Large Cap' → ₹2,50,000
  final Map<String, double> marketCapPct;     // 'Large Cap' → 48.0

  // ── MF by category (values) ──
  final Map<String, List<Map<String, dynamic>>> mfByCategory;
  final Map<String, double> mfCategoryTotals;

  // ── Stock by sector (values) ──
  final Map<String, double> sectorValues;
  final List<Map<String, dynamic>> stockHoldings;
  final Map<String, List<Map<String, dynamic>>> stocksBySector;

  // ── Rebalancing ──
  final List<RebalanceItem> rebalanceItems;

  const AllocationData({
    required this.totalPortfolioValue,
    required this.totalInvested,
    required this.totalPnl,
    required this.totalPnlPct,
    required this.equityValue,
    required this.mfValue,
    required this.goldValue,
    required this.cashValue,
    required this.debtValue,
    required this.internationalValue,
    required this.reitsValue,
    required this.marketCapValues,
    required this.marketCapPct,
    required this.mfByCategory,
    required this.mfCategoryTotals,
    required this.sectorValues,
    required this.stockHoldings,
    required this.stocksBySector,
    required this.rebalanceItems,
  });
}

class RebalanceItem {
  final String category;
  final double currentPct;
  final double targetPct;
  final double deltaPct;
  final String action; // 'Buy', 'Sell', 'Hold'
  final double amount;  // ₹ amount to buy/sell

  const RebalanceItem({
    required this.category,
    required this.currentPct,
    required this.targetPct,
    required this.deltaPct,
    required this.action,
    required this.amount,
  });
}

// ══════════════════════════════════════════
//  MASTER ALLOCATION PROVIDER
// ══════════════════════════════════════════

/// Computes the full allocation dataset by combining
/// portfolioProvider + mfPortfolioProvider + otherAssetsProvider.
final allocationProvider = Provider.autoDispose<AllocationData>((ref) {
  final portfolio = ref.watch(portfolioProvider);
  final mfPortfolio = ref.watch(mfPortfolioProvider);
  final otherAssets = ref.watch(otherAssetsProvider);
  final targets = ref.watch(targetAllocationProvider);

  // ── Extract equity data ──
  double eqInvested = 0, eqValue = 0;
  List<Map<String, dynamic>> holdings = [];
  portfolio.whenData((pData) {
    eqInvested = (pData['total_invested'] ?? 0).toDouble();
    eqValue = (pData['total_portfolio_value'] ?? 0).toDouble();
    holdings = List<Map<String, dynamic>>.from(pData['holdings'] ?? []);
  });

  // ── Extract MF data ──
  double mfInvested = 0, mfValue = 0;
  List<Map<String, dynamic>> funds = [];
  mfPortfolio.whenData((mfData) {
    mfInvested = (mfData['total_invested'] ?? 0).toDouble();
    mfValue = (mfData['total_current'] ?? 0).toDouble();
    funds = List<Map<String, dynamic>>.from(mfData['funds'] ?? []);
  });

  // ── Other assets ──
  final goldValue = otherAssets['Gold'] ?? 0.0;
  final cashValue = otherAssets['Cash'] ?? 0.0;
  final debtValue = otherAssets['Debt'] ?? 0.0;
  final internationalValue = otherAssets['International'] ?? 0.0;
  final reitsValue = otherAssets['REITs'] ?? 0.0;

  // ── Combined totals ──
  final totalInvested = eqInvested + mfInvested;
  final otherTotal = goldValue + cashValue + debtValue + internationalValue + reitsValue;
  final totalValue = eqValue + mfValue + otherTotal;
  final totalPnl = (eqValue + mfValue) - totalInvested;
  final totalPnlPct = totalInvested > 0 ? (totalPnl / totalInvested) * 100 : 0.0;

  // ── MF by category ──
  final mfByCategory = <String, List<Map<String, dynamic>>>{};
  final mfCategoryTotals = <String, double>{};
  for (final f in funds) {
    final cat = (f['category'] ?? 'Uncategorized').toString();
    mfByCategory.putIfAbsent(cat, () => []).add(f);
    final curVal = (f['current_value'] ?? 0).toDouble();
    mfCategoryTotals[cat] = (mfCategoryTotals[cat] ?? 0) + curVal;
  }

  // ── Market-cap allocation ──
  // Map MF categories to market-cap buckets
  final marketCapValues = <String, double>{
    'Large Cap': 0,
    'Mid Cap': 0,
    'Small Cap': 0,
    'Flexi Cap': 0,
    'International': internationalValue,
    'Debt': debtValue,
    'Gold': goldValue,
  };

  // Direct stocks → Large Cap by default
  marketCapValues['Large Cap'] = (marketCapValues['Large Cap'] ?? 0) + eqValue;

  for (final entry in mfCategoryTotals.entries) {
    final cat = entry.key.toLowerCase();
    if (cat.contains('large') || cat.contains('index') || cat.contains('bluechip')) {
      marketCapValues['Large Cap'] = (marketCapValues['Large Cap'] ?? 0) + entry.value;
    } else if (cat.contains('mid')) {
      marketCapValues['Mid Cap'] = (marketCapValues['Mid Cap'] ?? 0) + entry.value;
    } else if (cat.contains('small')) {
      marketCapValues['Small Cap'] = (marketCapValues['Small Cap'] ?? 0) + entry.value;
    } else if (cat.contains('flexi') || cat.contains('multi')) {
      marketCapValues['Flexi Cap'] = (marketCapValues['Flexi Cap'] ?? 0) + entry.value;
    } else if (cat.contains('international') || cat.contains('global') || cat.contains('foreign')) {
      marketCapValues['International'] = (marketCapValues['International'] ?? 0) + entry.value;
    } else if (cat.contains('debt') || cat.contains('liquid') || cat.contains('bond') || cat.contains('gilt') || cat.contains('money')) {
      marketCapValues['Debt'] = (marketCapValues['Debt'] ?? 0) + entry.value;
    } else if (cat.contains('gold') || cat.contains('commodity')) {
      marketCapValues['Gold'] = (marketCapValues['Gold'] ?? 0) + entry.value;
    } else {
      // Default uncategorized MF → Flexi Cap
      marketCapValues['Flexi Cap'] = (marketCapValues['Flexi Cap'] ?? 0) + entry.value;
    }
  }

  // Add cash to a separate bucket for percentage calculation
  final totalForPct = totalValue > 0 ? totalValue : 1;
  final marketCapPct = marketCapValues.map(
    (k, v) => MapEntry(k, (v / totalForPct) * 100),
  );

  // ── Stock by sector ──
  final sectorValues = <String, double>{};
  final stocksBySector = <String, List<Map<String, dynamic>>>{};
  for (final h in holdings) {
    final sector = (h['sector'] ?? h['industry'] ?? 'Other').toString();
    final val = (h['current_value'] ?? ((h['ltp'] ?? h['current_price'] ?? 0).toDouble() * (h['shares'] ?? 0))).toDouble();
    sectorValues[sector] = (sectorValues[sector] ?? 0) + val;
    stocksBySector.putIfAbsent(sector, () => []).add(h);
  }

  // ── Rebalancing ──
  final rebalanceItems = <RebalanceItem>[];
  for (final entry in targets.entries) {
    final currentPct = marketCapPct[entry.key] ?? 0.0;
    final targetPct = entry.value;
    final delta = currentPct - targetPct;
    String action;
    if (delta.abs() < 1) {
      action = 'Hold';
    } else if (delta > 0) {
      action = 'Reduce';
    } else {
      action = 'Add';
    }
    final amount = (delta.abs() / 100) * totalValue;
    rebalanceItems.add(RebalanceItem(
      category: entry.key,
      currentPct: currentPct,
      targetPct: targetPct,
      deltaPct: delta,
      action: action,
      amount: amount,
    ));
  }

  return AllocationData(
    totalPortfolioValue: totalValue,
    totalInvested: totalInvested,
    totalPnl: totalPnl,
    totalPnlPct: totalPnlPct,
    equityValue: eqValue,
    mfValue: mfValue,
    goldValue: goldValue,
    cashValue: cashValue,
    debtValue: debtValue,
    internationalValue: internationalValue,
    reitsValue: reitsValue,
    marketCapValues: marketCapValues,
    marketCapPct: marketCapPct,
    mfByCategory: mfByCategory,
    mfCategoryTotals: mfCategoryTotals,
    sectorValues: sectorValues,
    stockHoldings: holdings,
    stocksBySector: stocksBySector,
    rebalanceItems: rebalanceItems,
  );
});
