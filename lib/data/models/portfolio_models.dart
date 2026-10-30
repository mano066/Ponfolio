import 'package:freezed_annotation/freezed_annotation.dart';

part 'portfolio_models.freezed.dart';
part 'portfolio_models.g.dart';

// ══════════════════════════════════════════
//  STOCK HOLDING
// ══════════════════════════════════════════

@freezed
abstract class StockHolding with _$StockHolding {
  const factory StockHolding({
    required String symbol,
    @Default('') String name,
    @Default('Other') String sector,
    @Default(0) int shares,
    @JsonKey(name: 'avg_cost') @Default(0) double avgCost,
    @JsonKey(name: 'current_price') @Default(0) double currentPrice,
    @Default(0) double invested,
    @Default(0) double pnl,
    @JsonKey(name: 'net_chg') @Default(0) double netChg,
    @JsonKey(name: 'day_chg') @Default(0) double dayChg,
    @JsonKey(name: 'total_value') @Default(0) double totalValue,
    @Default('INR') String currency,
    @Default('') String? error,
    // Enriched by providers
    @Default('HOLD') String signal,
  }) = _StockHolding;

  factory StockHolding.fromJson(Map<String, dynamic> json) =>
      _$StockHoldingFromJson(json);
}

// ══════════════════════════════════════════
//  PORTFOLIO DATA
// ══════════════════════════════════════════

@freezed
abstract class PortfolioData with _$PortfolioData {
  const factory PortfolioData({
    @Default('success') String status,
    @Default('INR') String currency,
    @JsonKey(name: 'data_source') @Default('yfinance') String dataSource,
    @JsonKey(name: 'kite_connected') @Default(false) bool kiteConnected,
    @JsonKey(name: 'total_portfolio_value') @Default(0) double totalPortfolioValue,
    @JsonKey(name: 'total_invested') @Default(0) double totalInvested,
    @JsonKey(name: 'total_pnl') @Default(0) double totalPnl,
    @JsonKey(name: 'total_pnl_pct') @Default(0) double totalPnlPct,
    @Default([]) List<StockHolding> holdings,
  }) = _PortfolioData;

  factory PortfolioData.fromJson(Map<String, dynamic> json) =>
      _$PortfolioDataFromJson(json);

  factory PortfolioData.empty() => const PortfolioData();
}

// ══════════════════════════════════════════
//  MUTUAL FUND TRANSACTION
// ══════════════════════════════════════════

@freezed
abstract class MFTransaction with _$MFTransaction {
  const factory MFTransaction({
    required String date,
    @Default(0) double invested,
    @Default(0) double redeemed,
    @Default(0) double units,
    @Default(0) double nav,
  }) = _MFTransaction;

  factory MFTransaction.fromJson(Map<String, dynamic> json) =>
      _$MFTransactionFromJson(json);
}

// ══════════════════════════════════════════
//  MUTUAL FUND HOLDING
// ══════════════════════════════════════════

@freezed
abstract class MFFund with _$MFFund {
  const factory MFFund({
    @JsonKey(name: 'scheme_name') @Default('') String schemeName,
    @Default('Mutual Fund') String category,
    @Default('') String folio,
    @Default(0) double invested,
    @JsonKey(name: 'current_value') @Default(0) double currentValue,
    @Default(0) double units,
    @Default(0) double nav,
    @JsonKey(name: 'avg_nav') @Default(0) double avgNav,
    @JsonKey(name: 'return_pct') @Default(0) double returnPct,
    @Default(0) double xirr,
    @Default([]) List<MFTransaction> transactions,
  }) = _MFFund;

  factory MFFund.fromJson(Map<String, dynamic> json) =>
      _$MFFundFromJson(json);
}

// ══════════════════════════════════════════
//  MF PORTFOLIO DATA
// ══════════════════════════════════════════

@freezed
abstract class MFPortfolioData with _$MFPortfolioData {
  const factory MFPortfolioData({
    @Default([]) List<MFFund> funds,
    @JsonKey(name: 'total_invested') @Default(0) double totalInvested,
    @JsonKey(name: 'total_current') @Default(0) double totalCurrent,
    @JsonKey(name: 'total_pnl') @Default(0) double totalPnl,
    @JsonKey(name: 'total_pnl_pct') @Default(0) double totalPnlPct,
    @JsonKey(name: 'total_xirr') @Default(0) double totalXirr,
  }) = _MFPortfolioData;

  factory MFPortfolioData.fromJson(Map<String, dynamic> json) =>
      _$MFPortfolioDataFromJson(json);

  factory MFPortfolioData.empty() => const MFPortfolioData();
}

// ══════════════════════════════════════════
//  NIFTY 50
// ══════════════════════════════════════════

@freezed
abstract class NiftyData with _$NiftyData {
  const factory NiftyData({
    @Default('NIFTY 50') String symbol,
    @Default(0) double current,
    @JsonKey(name: 'change_pct') @Default(0) double changePct,
    String? error,
  }) = _NiftyData;

  factory NiftyData.fromJson(Map<String, dynamic> json) =>
      _$NiftyDataFromJson(json);
}

// ══════════════════════════════════════════
//  KITE STATUS
// ══════════════════════════════════════════

@freezed
abstract class KiteStatus with _$KiteStatus {
  const factory KiteStatus({
    @Default(false) bool connected,
    @Default(false) bool configured,
    @JsonKey(name: 'mcp_available') @Default(false) bool mcpAvailable,
    @JsonKey(name: 'user_name') String? userName,
    @JsonKey(name: 'user_id') String? userId,
    String? broker,
    @JsonKey(name: 'last_error') String? lastError,
  }) = _KiteStatus;

  factory KiteStatus.fromJson(Map<String, dynamic> json) =>
      _$KiteStatusFromJson(json);
}

// ══════════════════════════════════════════
//  ADVISOR VERDICT
// ══════════════════════════════════════════

@freezed
abstract class AdvisorVerdict with _$AdvisorVerdict {
  const factory AdvisorVerdict({
    @Default('HOLD') String verdict,
    @JsonKey(name: 'action_summary') @Default('') String actionSummary,
    @JsonKey(name: 'entry_range') String? entryRange,
    @JsonKey(name: 'target_price') String? targetPrice,
    @JsonKey(name: 'stop_loss') String? stopLoss,
    @JsonKey(name: 'sell_pct') String? sellPct,
    @JsonKey(name: 'time_horizon') @Default('Medium') String timeHorizon,
    @JsonKey(name: 'risk_level') @Default('Medium') String riskLevel,
    @Default(50) int confidence,
    @Default('') String reasoning,
    @JsonKey(name: 'current_price') double? currentPrice,
    @JsonKey(name: 'pnl_pct') double? pnlPct,
    double? rsi,
    @JsonKey(name: 'news_count') @Default(0) int newsCount,
  }) = _AdvisorVerdict;

  factory AdvisorVerdict.fromJson(Map<String, dynamic> json) =>
      _$AdvisorVerdictFromJson(json);
}

// ══════════════════════════════════════════
//  ANALYTICS DATA
// ══════════════════════════════════════════

@freezed
abstract class AnalyticsData with _$AnalyticsData {
  const factory AnalyticsData({
    @JsonKey(name: 'portfolio_beta') @Default(1.0) double portfolioBeta,
    @JsonKey(name: 'sharpe_ratio') @Default(0) double sharpeRatio,
    @JsonKey(name: 'projected_1y_return') @Default(0) double projected1yReturn,
    @JsonKey(name: 'nifty_1y_return') @Default(14.2) double nifty1yReturn,
    @JsonKey(name: 'volatility_index') @Default(0) double volatilityIndex,
    @JsonKey(name: 'diversification_score') @Default(0) int diversificationScore,
    @JsonKey(name: 'top_performer') @Default('N/A') String topPerformer,
    @JsonKey(name: 'worst_performer') @Default('N/A') String worstPerformer,
  }) = _AnalyticsData;

  factory AnalyticsData.fromJson(Map<String, dynamic> json) =>
      _$AnalyticsDataFromJson(json);
}

// ══════════════════════════════════════════
//  USER PROFILE
// ══════════════════════════════════════════

@freezed
abstract class UserProfile with _$UserProfile {
  const factory UserProfile({
    @Default('') String name,
    @Default('') String email,
    @Default('') String picture,
    @JsonKey(name: 'logged_in') @Default(false) bool loggedIn,
    @Default(false) bool authenticated,
  }) = _UserProfile;

  factory UserProfile.fromJson(Map<String, dynamic> json) =>
      _$UserProfileFromJson(json);

  factory UserProfile.guest() => const UserProfile(name: 'Guest');
}

// ══════════════════════════════════════════
//  APP SETTINGS
// ══════════════════════════════════════════

@freezed
abstract class AppSettings with _$AppSettings {
  const factory AppSettings({
    @JsonKey(name: 'ollama_url') @Default('http://localhost:11434') String ollamaUrl,
    @JsonKey(name: 'model_name') @Default('qwen3.6:35b') String modelName,
    @Default('dark') String theme,
    @JsonKey(name: 'auto_refresh_nav') @Default(true) bool autoRefreshNav,
    @JsonKey(name: 'nav_refresh_interval') @Default(300) int navRefreshInterval,
  }) = _AppSettings;

  factory AppSettings.fromJson(Map<String, dynamic> json) =>
      _$AppSettingsFromJson(json);
}

// ══════════════════════════════════════════
//  SIP SIMULATION RESULT
// ══════════════════════════════════════════

@freezed
abstract class SIPTimelinePoint with _$SIPTimelinePoint {
  const factory SIPTimelinePoint({
    required String date,
    @Default(0) double invested,
    @Default(0) double value,
    @Default(0) double pnl,
    @JsonKey(name: 'pnl_pct') @Default(0) double pnlPct,
  }) = _SIPTimelinePoint;

  factory SIPTimelinePoint.fromJson(Map<String, dynamic> json) =>
      _$SIPTimelinePointFromJson(json);
}

@freezed
abstract class SIPYearlySummary with _$SIPYearlySummary {
  const factory SIPYearlySummary({
    required String year,
    @Default(0) double invested,
    @Default(0) int months,
    @JsonKey(name: 'cumulative_units') @Default(0) double cumulativeUnits,
    @JsonKey(name: 'cumulative_invested') @Default(0) double cumulativeInvested,
    @Default(0) double nav,
    @Default(0) double value,
    @Default(0) double pnl,
    @JsonKey(name: 'return_pct') @Default(0) double returnPct,
  }) = _SIPYearlySummary;

  factory SIPYearlySummary.fromJson(Map<String, dynamic> json) =>
      _$SIPYearlySummaryFromJson(json);
}

// ══════════════════════════════════════════
//  CHAT MESSAGE
// ══════════════════════════════════════════

@freezed
abstract class ChatMessage with _$ChatMessage {
  const factory ChatMessage({
    required String role,   // 'user' or 'assistant'
    required String content,
    DateTime? timestamp,
  }) = _ChatMessage;

  factory ChatMessage.fromJson(Map<String, dynamic> json) =>
      _$ChatMessageFromJson(json);
}
