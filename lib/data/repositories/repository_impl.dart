import 'package:logger/logger.dart';
import '../../domain/repositories/repositories.dart';
import '../../data/models/portfolio_models.dart';
import '../../services/api_service.dart';

final _log = Logger(printer: PrettyPrinter(methodCount: 0));

// ══════════════════════════════════════════
//  PORTFOLIO REPOSITORY
// ══════════════════════════════════════════

class PortfolioRepositoryImpl implements PortfolioRepository {
  final ApiService _api;
  PortfolioRepositoryImpl(this._api);

  @override
  Future<PortfolioData> getPortfolio({bool syncKite = false}) async {
    try {
      final data = await _api.getPortfolio();
      return PortfolioData.fromJson(data);
    } catch (e) {
      _log.e('getPortfolio failed', error: e);
      return PortfolioData.empty();
    }
  }

  @override
  Future<PortfolioData> getLivePrices() async {
    try {
      final data = await _api.getLivePrices();
      return PortfolioData.fromJson(data);
    } catch (e) {
      _log.e('getLivePrices failed', error: e);
      return PortfolioData.empty();
    }
  }

  @override
  Future<void> addStock(String symbol, int shares, {double avgCost = 0}) async {
    await _api.addStock(symbol, shares);
  }

  @override
  Future<void> removeStock(String symbol) async {
    await _api.dio.delete('/portfolio/$symbol');
  }
}

// ══════════════════════════════════════════
//  MUTUAL FUND REPOSITORY
// ══════════════════════════════════════════

class MFRepositoryImpl implements MFRepository {
  final ApiService _api;
  MFRepositoryImpl(this._api);

  @override
  Future<MFPortfolioData> getMFPortfolio() async {
    try {
      final data = await _api.getMFPortfolio();
      return MFPortfolioData.fromJson(data);
    } catch (e) {
      _log.e('getMFPortfolio failed', error: e);
      return MFPortfolioData.empty();
    }
  }

  @override
  Future<void> addFund(String schemeName, {String category = 'Mutual Fund', String schemeCode = ''}) async {
    await _api.addMFFund({'scheme_name': schemeName, 'category': category, 'scheme_code': schemeCode});
  }

  @override
  Future<void> deleteFund(String schemeName) async {
    await _api.deleteMFFund({'scheme_name': schemeName});
  }

  @override
  Future<void> addTransaction(String schemeName, MFTransaction txn) async {
    await _api.addMFTransaction({
      'scheme_name': schemeName,
      'date': txn.date, 'invested': txn.invested,
      'redeemed': txn.redeemed, 'units': txn.units, 'nav': txn.nav,
    });
  }

  @override
  Future<void> editTransaction(String schemeName, int index, MFTransaction txn) async {
    await _api.updateMFTransaction({
      'scheme_name': schemeName, 'index': index,
      'date': txn.date, 'invested': txn.invested,
      'redeemed': txn.redeemed, 'units': txn.units, 'nav': txn.nav,
    });
  }

  @override
  Future<void> deleteTransaction(String schemeName, int index) async {
    await _api.deleteMFTransaction({'scheme_name': schemeName, 'index': index});
  }

  @override
  Future<void> refreshNav() async => await _api.refreshMFNav();

  @override
  Future<Map<String, dynamic>> analyzeMFPortfolio() async => await _api.analyzeMFPortfolio();

  @override
  Future<List<Map<String, dynamic>>> searchFund(String query) async {
    final data = await _api.searchMFFund(query);
    return List<Map<String, dynamic>>.from(data['results'] ?? []);
  }
}

// ══════════════════════════════════════════
//  ANALYSIS REPOSITORY
// ══════════════════════════════════════════

class AnalysisRepositoryImpl implements AnalysisRepository {
  final ApiService _api;
  AnalysisRepositoryImpl(this._api);

  @override
  Future<Map<String, dynamic>> getDeepAnalysis(String symbol) async =>
      await _api.getDeepAnalysis(symbol);

  @override
  Future<Map<String, dynamic>> getDeepSignals() async =>
      await _api.getDeepSignals();

  @override
  Future<void> startDeepSignals() async => await _api.startDeepSignals();

  @override
  Future<Map<String, dynamic>> getAdvisor() async => await _api.getAdvisor();

  @override
  Future<void> startAdvisor() async => await _api.startAdvisor();

  @override
  Future<String> chat(String message, List<ChatMessage> history) async {
    final historyMaps = history.map((m) => {'role': m.role, 'content': m.content}).toList();
    final data = await _api.chat(message, historyMaps);
    return data['reply'] ?? 'No response.';
  }
}

// ══════════════════════════════════════════
//  MARKET REPOSITORY
// ══════════════════════════════════════════

class MarketRepositoryImpl implements MarketRepository {
  final ApiService _api;
  MarketRepositoryImpl(this._api);

  @override
  Future<NiftyData> getNifty50() async {
    try {
      final data = await _api.getNifty50();
      return NiftyData.fromJson(data);
    } catch (e) {
      return const NiftyData();
    }
  }

  @override
  Future<List<Map<String, dynamic>>> searchStock(String query) async {
    final data = await _api.dio.get('/search', queryParameters: {'q': query});
    return List<Map<String, dynamic>>.from(data.data['results'] ?? []);
  }

  @override
  Future<Map<String, dynamic>> getStockNews(String symbol) async =>
      await _api.getStockNews(symbol);

  @override
  Future<Map<String, dynamic>> getStockQuote(String symbol) async =>
      await _api.dio.get('/stock/$symbol/quote').then((r) => r.data as Map<String, dynamic>);
}

// ══════════════════════════════════════════
//  KITE REPOSITORY
// ══════════════════════════════════════════

class KiteRepositoryImpl implements KiteRepository {
  final ApiService _api;
  KiteRepositoryImpl(this._api);

  @override
  Future<KiteStatus> getStatus() async {
    try {
      final data = await _api.getKiteStatus();
      return KiteStatus.fromJson(data);
    } catch (e) {
      return const KiteStatus();
    }
  }

  @override
  Future<String?> getLoginUrl() async {
    final data = await _api.getKiteLoginUrl();
    return data['login_url'] as String?;
  }

  @override
  Future<void> logout() async => await _api.kiteLogout();

  @override
  Future<void> syncPortfolio() async => await _api.kiteSync();

  @override
  Future<bool> checkConnection() async {
    final data = await _api.dio.post('/kite/check');
    return data.data['connected'] == true;
  }
}

// ══════════════════════════════════════════
//  AUTH REPOSITORY
// ══════════════════════════════════════════

class AuthRepositoryImpl implements AuthRepository {
  final ApiService _api;
  AuthRepositoryImpl(this._api);

  @override
  Future<UserProfile> getProfile() async {
    try {
      final data = await _api.getProfile();
      return UserProfile.fromJson(data);
    } catch (e) {
      return UserProfile.guest();
    }
  }

  @override
  Future<String> getGoogleAuthUrl() async {
    final data = await _api.getGoogleAuthUrl();
    return data['url'] ?? '';
  }

  @override
  Future<void> logout() async => await _api.logout();
}

// ══════════════════════════════════════════
//  SETTINGS REPOSITORY
// ══════════════════════════════════════════

class SettingsRepositoryImpl implements SettingsRepository {
  final ApiService _api;
  SettingsRepositoryImpl(this._api);

  @override
  Future<AppSettings> getSettings() async {
    try {
      final data = await _api.getSettings();
      return AppSettings.fromJson(data);
    } catch (e) {
      return const AppSettings();
    }
  }

  @override
  Future<void> updateSettings(AppSettings settings) async {
    await _api.updateSettings(settings.toJson());
  }

  @override
  Future<List<String>> getOllamaModels() async {
    final data = await _api.getOllamaModels();
    return List<String>.from(data['models'] ?? []);
  }

  @override
  Future<bool> testOllama() async {
    try {
      final data = await _api.testOllama();
      return data['success'] == true;
    } catch (_) {
      return false;
    }
  }
}

// ══════════════════════════════════════════
//  SIP REPOSITORY
// ══════════════════════════════════════════

class SIPRepositoryImpl implements SIPRepository {
  final ApiService _api;
  SIPRepositoryImpl(this._api);

  @override
  Future<List<Map<String, dynamic>>> searchInstruments(String query) async {
    final data = await _api.searchSIPInstruments(query);
    return List<Map<String, dynamic>>.from(data['results'] ?? []);
  }

  @override
  Future<Map<String, dynamic>> simulate({
    required List<Map<String, dynamic>> symbols,
    required String startDate,
    int sipDay = 1,
    double stepUpPct = 0,
    List<Map<String, dynamic>>? customEntries,
  }) async {
    return await _api.simulateSIP(
      symbols: symbols, startDate: startDate, sipDay: sipDay,
      stepUpPct: stepUpPct, customEntries: customEntries,
    );
  }
}

// ══════════════════════════════════════════
//  REPORTS REPOSITORY
// ══════════════════════════════════════════

class ReportsRepositoryImpl implements ReportsRepository {
  final ApiService _api;
  ReportsRepositoryImpl(this._api);

  @override
  Future<Map<String, dynamic>> getWealthReport() async =>
      await _api.getWealthReport();
}

// ══════════════════════════════════════════
//  ANALYTICS REPOSITORY
// ══════════════════════════════════════════

class AnalyticsRepositoryImpl implements AnalyticsRepository {
  final ApiService _api;
  AnalyticsRepositoryImpl(this._api);

  @override
  Future<AnalyticsData> getAnalytics() async {
    try {
      final data = await _api.getAnalytics();
      return AnalyticsData.fromJson(data);
    } catch (e) {
      return const AnalyticsData();
    }
  }
}
