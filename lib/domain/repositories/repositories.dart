import '../../data/models/portfolio_models.dart';

/// Abstract portfolio data access.
/// Implementations may use API, Hive cache, or mock data.
abstract class PortfolioRepository {
  /// Fetch full portfolio (holdings + totals).
  Future<PortfolioData> getPortfolio({bool syncKite = false});

  /// Fetch live price updates only (lighter endpoint).
  Future<PortfolioData> getLivePrices();

  /// Add a stock to the portfolio.
  Future<void> addStock(String symbol, int shares, {double avgCost = 0});

  /// Remove a stock from the portfolio.
  Future<void> removeStock(String symbol);
}

/// Mutual Fund portfolio data access.
abstract class MFRepository {
  Future<MFPortfolioData> getMFPortfolio();
  Future<void> addFund(String schemeName, {String category = 'Mutual Fund', String schemeCode = ''});
  Future<void> deleteFund(String schemeName);
  Future<void> addTransaction(String schemeName, MFTransaction txn);
  Future<void> editTransaction(String schemeName, int index, MFTransaction txn);
  Future<void> deleteTransaction(String schemeName, int index);
  Future<void> refreshNav();
  Future<Map<String, dynamic>> analyzeMFPortfolio();
  Future<List<Map<String, dynamic>>> searchFund(String query);
}

/// AI analysis & advisor data access.
abstract class AnalysisRepository {
  Future<Map<String, dynamic>> getDeepAnalysis(String symbol);
  Future<Map<String, dynamic>> getDeepSignals();
  Future<void> startDeepSignals();
  Future<Map<String, dynamic>> getAdvisor();
  Future<void> startAdvisor();
  Future<String> chat(String message, List<ChatMessage> history);
}

/// Market data access.
abstract class MarketRepository {
  Future<NiftyData> getNifty50();
  Future<List<Map<String, dynamic>>> searchStock(String query);
  Future<Map<String, dynamic>> getStockNews(String symbol);
  Future<Map<String, dynamic>> getStockQuote(String symbol);
}

/// Kite Connect broker integration.
abstract class KiteRepository {
  Future<KiteStatus> getStatus();
  Future<String?> getLoginUrl();
  Future<void> logout();
  Future<void> syncPortfolio();
  Future<bool> checkConnection();
}

/// Authentication.
abstract class AuthRepository {
  Future<UserProfile> getProfile();
  Future<String> getGoogleAuthUrl();
  Future<void> logout();
}

/// App settings.
abstract class SettingsRepository {
  Future<AppSettings> getSettings();
  Future<void> updateSettings(AppSettings settings);
  Future<List<String>> getOllamaModels();
  Future<bool> testOllama();
}

/// SIP Simulator.
abstract class SIPRepository {
  Future<List<Map<String, dynamic>>> searchInstruments(String query);
  Future<Map<String, dynamic>> simulate({
    required List<Map<String, dynamic>> symbols,
    required String startDate,
    int sipDay = 1,
    double stepUpPct = 0,
    List<Map<String, dynamic>>? customEntries,
  });
}

/// Reports.
abstract class ReportsRepository {
  Future<Map<String, dynamic>> getWealthReport();
}

/// Analytics.
abstract class AnalyticsRepository {
  Future<AnalyticsData> getAnalytics();
}
