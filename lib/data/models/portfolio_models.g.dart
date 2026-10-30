// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'portfolio_models.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_StockHolding _$StockHoldingFromJson(Map<String, dynamic> json) =>
    _StockHolding(
      symbol: json['symbol'] as String,
      name: json['name'] as String? ?? '',
      sector: json['sector'] as String? ?? 'Other',
      shares: (json['shares'] as num?)?.toInt() ?? 0,
      avgCost: (json['avg_cost'] as num?)?.toDouble() ?? 0,
      currentPrice: (json['current_price'] as num?)?.toDouble() ?? 0,
      invested: (json['invested'] as num?)?.toDouble() ?? 0,
      pnl: (json['pnl'] as num?)?.toDouble() ?? 0,
      netChg: (json['net_chg'] as num?)?.toDouble() ?? 0,
      dayChg: (json['day_chg'] as num?)?.toDouble() ?? 0,
      totalValue: (json['total_value'] as num?)?.toDouble() ?? 0,
      currency: json['currency'] as String? ?? 'INR',
      error: json['error'] as String? ?? '',
      signal: json['signal'] as String? ?? 'HOLD',
    );

Map<String, dynamic> _$StockHoldingToJson(_StockHolding instance) =>
    <String, dynamic>{
      'symbol': instance.symbol,
      'name': instance.name,
      'sector': instance.sector,
      'shares': instance.shares,
      'avg_cost': instance.avgCost,
      'current_price': instance.currentPrice,
      'invested': instance.invested,
      'pnl': instance.pnl,
      'net_chg': instance.netChg,
      'day_chg': instance.dayChg,
      'total_value': instance.totalValue,
      'currency': instance.currency,
      'error': instance.error,
      'signal': instance.signal,
    };

_PortfolioData _$PortfolioDataFromJson(Map<String, dynamic> json) =>
    _PortfolioData(
      status: json['status'] as String? ?? 'success',
      currency: json['currency'] as String? ?? 'INR',
      dataSource: json['data_source'] as String? ?? 'yfinance',
      kiteConnected: json['kite_connected'] as bool? ?? false,
      totalPortfolioValue:
          (json['total_portfolio_value'] as num?)?.toDouble() ?? 0,
      totalInvested: (json['total_invested'] as num?)?.toDouble() ?? 0,
      totalPnl: (json['total_pnl'] as num?)?.toDouble() ?? 0,
      totalPnlPct: (json['total_pnl_pct'] as num?)?.toDouble() ?? 0,
      holdings:
          (json['holdings'] as List<dynamic>?)
              ?.map((e) => StockHolding.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
    );

Map<String, dynamic> _$PortfolioDataToJson(_PortfolioData instance) =>
    <String, dynamic>{
      'status': instance.status,
      'currency': instance.currency,
      'data_source': instance.dataSource,
      'kite_connected': instance.kiteConnected,
      'total_portfolio_value': instance.totalPortfolioValue,
      'total_invested': instance.totalInvested,
      'total_pnl': instance.totalPnl,
      'total_pnl_pct': instance.totalPnlPct,
      'holdings': instance.holdings,
    };

_MFTransaction _$MFTransactionFromJson(Map<String, dynamic> json) =>
    _MFTransaction(
      date: json['date'] as String,
      invested: (json['invested'] as num?)?.toDouble() ?? 0,
      redeemed: (json['redeemed'] as num?)?.toDouble() ?? 0,
      units: (json['units'] as num?)?.toDouble() ?? 0,
      nav: (json['nav'] as num?)?.toDouble() ?? 0,
    );

Map<String, dynamic> _$MFTransactionToJson(_MFTransaction instance) =>
    <String, dynamic>{
      'date': instance.date,
      'invested': instance.invested,
      'redeemed': instance.redeemed,
      'units': instance.units,
      'nav': instance.nav,
    };

_MFFund _$MFFundFromJson(Map<String, dynamic> json) => _MFFund(
  schemeName: json['scheme_name'] as String? ?? '',
  category: json['category'] as String? ?? 'Mutual Fund',
  folio: json['folio'] as String? ?? '',
  invested: (json['invested'] as num?)?.toDouble() ?? 0,
  currentValue: (json['current_value'] as num?)?.toDouble() ?? 0,
  units: (json['units'] as num?)?.toDouble() ?? 0,
  nav: (json['nav'] as num?)?.toDouble() ?? 0,
  avgNav: (json['avg_nav'] as num?)?.toDouble() ?? 0,
  returnPct: (json['return_pct'] as num?)?.toDouble() ?? 0,
  xirr: (json['xirr'] as num?)?.toDouble() ?? 0,
  transactions:
      (json['transactions'] as List<dynamic>?)
          ?.map((e) => MFTransaction.fromJson(e as Map<String, dynamic>))
          .toList() ??
      const [],
);

Map<String, dynamic> _$MFFundToJson(_MFFund instance) => <String, dynamic>{
  'scheme_name': instance.schemeName,
  'category': instance.category,
  'folio': instance.folio,
  'invested': instance.invested,
  'current_value': instance.currentValue,
  'units': instance.units,
  'nav': instance.nav,
  'avg_nav': instance.avgNav,
  'return_pct': instance.returnPct,
  'xirr': instance.xirr,
  'transactions': instance.transactions,
};

_MFPortfolioData _$MFPortfolioDataFromJson(Map<String, dynamic> json) =>
    _MFPortfolioData(
      funds:
          (json['funds'] as List<dynamic>?)
              ?.map((e) => MFFund.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
      totalInvested: (json['total_invested'] as num?)?.toDouble() ?? 0,
      totalCurrent: (json['total_current'] as num?)?.toDouble() ?? 0,
      totalPnl: (json['total_pnl'] as num?)?.toDouble() ?? 0,
      totalPnlPct: (json['total_pnl_pct'] as num?)?.toDouble() ?? 0,
      totalXirr: (json['total_xirr'] as num?)?.toDouble() ?? 0,
    );

Map<String, dynamic> _$MFPortfolioDataToJson(_MFPortfolioData instance) =>
    <String, dynamic>{
      'funds': instance.funds,
      'total_invested': instance.totalInvested,
      'total_current': instance.totalCurrent,
      'total_pnl': instance.totalPnl,
      'total_pnl_pct': instance.totalPnlPct,
      'total_xirr': instance.totalXirr,
    };

_NiftyData _$NiftyDataFromJson(Map<String, dynamic> json) => _NiftyData(
  symbol: json['symbol'] as String? ?? 'NIFTY 50',
  current: (json['current'] as num?)?.toDouble() ?? 0,
  changePct: (json['change_pct'] as num?)?.toDouble() ?? 0,
  error: json['error'] as String?,
);

Map<String, dynamic> _$NiftyDataToJson(_NiftyData instance) =>
    <String, dynamic>{
      'symbol': instance.symbol,
      'current': instance.current,
      'change_pct': instance.changePct,
      'error': instance.error,
    };

_KiteStatus _$KiteStatusFromJson(Map<String, dynamic> json) => _KiteStatus(
  connected: json['connected'] as bool? ?? false,
  configured: json['configured'] as bool? ?? false,
  mcpAvailable: json['mcp_available'] as bool? ?? false,
  userName: json['user_name'] as String?,
  userId: json['user_id'] as String?,
  broker: json['broker'] as String?,
  lastError: json['last_error'] as String?,
);

Map<String, dynamic> _$KiteStatusToJson(_KiteStatus instance) =>
    <String, dynamic>{
      'connected': instance.connected,
      'configured': instance.configured,
      'mcp_available': instance.mcpAvailable,
      'user_name': instance.userName,
      'user_id': instance.userId,
      'broker': instance.broker,
      'last_error': instance.lastError,
    };

_AdvisorVerdict _$AdvisorVerdictFromJson(Map<String, dynamic> json) =>
    _AdvisorVerdict(
      verdict: json['verdict'] as String? ?? 'HOLD',
      actionSummary: json['action_summary'] as String? ?? '',
      entryRange: json['entry_range'] as String?,
      targetPrice: json['target_price'] as String?,
      stopLoss: json['stop_loss'] as String?,
      sellPct: json['sell_pct'] as String?,
      timeHorizon: json['time_horizon'] as String? ?? 'Medium',
      riskLevel: json['risk_level'] as String? ?? 'Medium',
      confidence: (json['confidence'] as num?)?.toInt() ?? 50,
      reasoning: json['reasoning'] as String? ?? '',
      currentPrice: (json['current_price'] as num?)?.toDouble(),
      pnlPct: (json['pnl_pct'] as num?)?.toDouble(),
      rsi: (json['rsi'] as num?)?.toDouble(),
      newsCount: (json['news_count'] as num?)?.toInt() ?? 0,
    );

Map<String, dynamic> _$AdvisorVerdictToJson(_AdvisorVerdict instance) =>
    <String, dynamic>{
      'verdict': instance.verdict,
      'action_summary': instance.actionSummary,
      'entry_range': instance.entryRange,
      'target_price': instance.targetPrice,
      'stop_loss': instance.stopLoss,
      'sell_pct': instance.sellPct,
      'time_horizon': instance.timeHorizon,
      'risk_level': instance.riskLevel,
      'confidence': instance.confidence,
      'reasoning': instance.reasoning,
      'current_price': instance.currentPrice,
      'pnl_pct': instance.pnlPct,
      'rsi': instance.rsi,
      'news_count': instance.newsCount,
    };

_AnalyticsData _$AnalyticsDataFromJson(Map<String, dynamic> json) =>
    _AnalyticsData(
      portfolioBeta: (json['portfolio_beta'] as num?)?.toDouble() ?? 1.0,
      sharpeRatio: (json['sharpe_ratio'] as num?)?.toDouble() ?? 0,
      projected1yReturn: (json['projected_1y_return'] as num?)?.toDouble() ?? 0,
      nifty1yReturn: (json['nifty_1y_return'] as num?)?.toDouble() ?? 14.2,
      volatilityIndex: (json['volatility_index'] as num?)?.toDouble() ?? 0,
      diversificationScore:
          (json['diversification_score'] as num?)?.toInt() ?? 0,
      topPerformer: json['top_performer'] as String? ?? 'N/A',
      worstPerformer: json['worst_performer'] as String? ?? 'N/A',
    );

Map<String, dynamic> _$AnalyticsDataToJson(_AnalyticsData instance) =>
    <String, dynamic>{
      'portfolio_beta': instance.portfolioBeta,
      'sharpe_ratio': instance.sharpeRatio,
      'projected_1y_return': instance.projected1yReturn,
      'nifty_1y_return': instance.nifty1yReturn,
      'volatility_index': instance.volatilityIndex,
      'diversification_score': instance.diversificationScore,
      'top_performer': instance.topPerformer,
      'worst_performer': instance.worstPerformer,
    };

_UserProfile _$UserProfileFromJson(Map<String, dynamic> json) => _UserProfile(
  name: json['name'] as String? ?? '',
  email: json['email'] as String? ?? '',
  picture: json['picture'] as String? ?? '',
  loggedIn: json['logged_in'] as bool? ?? false,
  authenticated: json['authenticated'] as bool? ?? false,
);

Map<String, dynamic> _$UserProfileToJson(_UserProfile instance) =>
    <String, dynamic>{
      'name': instance.name,
      'email': instance.email,
      'picture': instance.picture,
      'logged_in': instance.loggedIn,
      'authenticated': instance.authenticated,
    };

_AppSettings _$AppSettingsFromJson(Map<String, dynamic> json) => _AppSettings(
  ollamaUrl: json['ollama_url'] as String? ?? 'http://localhost:11434',
  modelName: json['model_name'] as String? ?? 'qwen3.6:35b',
  theme: json['theme'] as String? ?? 'dark',
  autoRefreshNav: json['auto_refresh_nav'] as bool? ?? true,
  navRefreshInterval: (json['nav_refresh_interval'] as num?)?.toInt() ?? 300,
);

Map<String, dynamic> _$AppSettingsToJson(_AppSettings instance) =>
    <String, dynamic>{
      'ollama_url': instance.ollamaUrl,
      'model_name': instance.modelName,
      'theme': instance.theme,
      'auto_refresh_nav': instance.autoRefreshNav,
      'nav_refresh_interval': instance.navRefreshInterval,
    };

_SIPTimelinePoint _$SIPTimelinePointFromJson(Map<String, dynamic> json) =>
    _SIPTimelinePoint(
      date: json['date'] as String,
      invested: (json['invested'] as num?)?.toDouble() ?? 0,
      value: (json['value'] as num?)?.toDouble() ?? 0,
      pnl: (json['pnl'] as num?)?.toDouble() ?? 0,
      pnlPct: (json['pnl_pct'] as num?)?.toDouble() ?? 0,
    );

Map<String, dynamic> _$SIPTimelinePointToJson(_SIPTimelinePoint instance) =>
    <String, dynamic>{
      'date': instance.date,
      'invested': instance.invested,
      'value': instance.value,
      'pnl': instance.pnl,
      'pnl_pct': instance.pnlPct,
    };

_SIPYearlySummary _$SIPYearlySummaryFromJson(Map<String, dynamic> json) =>
    _SIPYearlySummary(
      year: json['year'] as String,
      invested: (json['invested'] as num?)?.toDouble() ?? 0,
      months: (json['months'] as num?)?.toInt() ?? 0,
      cumulativeUnits: (json['cumulative_units'] as num?)?.toDouble() ?? 0,
      cumulativeInvested:
          (json['cumulative_invested'] as num?)?.toDouble() ?? 0,
      nav: (json['nav'] as num?)?.toDouble() ?? 0,
      value: (json['value'] as num?)?.toDouble() ?? 0,
      pnl: (json['pnl'] as num?)?.toDouble() ?? 0,
      returnPct: (json['return_pct'] as num?)?.toDouble() ?? 0,
    );

Map<String, dynamic> _$SIPYearlySummaryToJson(_SIPYearlySummary instance) =>
    <String, dynamic>{
      'year': instance.year,
      'invested': instance.invested,
      'months': instance.months,
      'cumulative_units': instance.cumulativeUnits,
      'cumulative_invested': instance.cumulativeInvested,
      'nav': instance.nav,
      'value': instance.value,
      'pnl': instance.pnl,
      'return_pct': instance.returnPct,
    };

_ChatMessage _$ChatMessageFromJson(Map<String, dynamic> json) => _ChatMessage(
  role: json['role'] as String,
  content: json['content'] as String,
  timestamp: json['timestamp'] == null
      ? null
      : DateTime.parse(json['timestamp'] as String),
);

Map<String, dynamic> _$ChatMessageToJson(_ChatMessage instance) =>
    <String, dynamic>{
      'role': instance.role,
      'content': instance.content,
      'timestamp': instance.timestamp?.toIso8601String(),
    };
