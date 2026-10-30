import 'dart:convert';
import 'package:hive/hive.dart';
import 'package:path_provider/path_provider.dart';
import 'package:logger/logger.dart';

/// Singleton local storage service backed by Hive.
///
/// Boxes:
///   - **cache**     — API response cache (portfolio, MF, nifty, etc.)
///   - **settings**  — User preferences (theme, window state, etc.)
///   - **secure**    — Sensitive data (API tokens, future Kite auth)
///
/// All values are stored as JSON strings so we don't need Hive adapters.
class LocalStorageService {
  static final LocalStorageService _instance = LocalStorageService._internal();
  factory LocalStorageService() => _instance;
  LocalStorageService._internal();

  static const String _cacheBoxName = 'aiei_cache';
  static const String _settingsBoxName = 'aiei_settings';
  static const String _secureBoxName = 'aiei_secure';

  final _log = Logger(printer: PrettyPrinter(methodCount: 0));

  late Box _cacheBox;
  late Box _settingsBox;
  late Box _secureBox;

  bool _initialized = false;

  // ──────────────────────────────────────
  //  INITIALIZATION
  // ──────────────────────────────────────

  /// Must be called once in main() before runApp().
  Future<void> init() async {
    if (_initialized) return;

    final appDir = await getApplicationSupportDirectory();
    Hive.init('${appDir.path}/hive');

    _cacheBox = await Hive.openBox(_cacheBoxName);
    _settingsBox = await Hive.openBox(_settingsBoxName);
    _secureBox = await Hive.openBox(_secureBoxName);

    _initialized = true;
    _log.i('[Storage] Hive initialized at ${appDir.path}/hive '
        '(cache: ${_cacheBox.length}, settings: ${_settingsBox.length}, '
        'secure: ${_secureBox.length} keys)');
  }

  // ──────────────────────────────────────
  //  CACHE BOX — API response caching
  // ──────────────────────────────────────

  // --- Cache Keys ---
  static const String keyPortfolio = 'portfolio';
  static const String keyMFPortfolio = 'mf_portfolio';
  static const String keyNifty = 'nifty';
  static const String keyKiteStatus = 'kite_status';
  static const String keyAnalytics = 'analytics';
  static const String keyDeepSignals = 'deep_signals';
  static const String keyAdvisor = 'advisor';
  static const String keyWealthReport = 'wealth_report';

  /// Store a JSON-serializable map in the cache box.
  Future<void> cacheJson(String key, Map<String, dynamic> data) async {
    try {
      await _cacheBox.put(key, jsonEncode(data));
      await _cacheBox.put('${key}_ts', DateTime.now().millisecondsSinceEpoch);
    } catch (e) {
      _log.w('[Storage] cacheJson($key) failed: $e');
    }
  }

  /// Retrieve a cached JSON map.  Returns null if not found.
  Map<String, dynamic>? getCachedJson(String key) {
    try {
      final raw = _cacheBox.get(key) as String?;
      if (raw == null) return null;
      return jsonDecode(raw) as Map<String, dynamic>;
    } catch (e) {
      _log.w('[Storage] getCachedJson($key) failed: $e');
      return null;
    }
  }

  /// Check if a cache entry is still fresh.
  bool isCacheFresh(String key, {Duration maxAge = const Duration(minutes: 5)}) {
    final ts = _cacheBox.get('${key}_ts') as int?;
    if (ts == null) return false;
    return DateTime.now().millisecondsSinceEpoch - ts < maxAge.inMilliseconds;
  }

  /// Store a JSON-serializable list in the cache box.
  Future<void> cacheList(String key, List<dynamic> data) async {
    try {
      await _cacheBox.put(key, jsonEncode(data));
      await _cacheBox.put('${key}_ts', DateTime.now().millisecondsSinceEpoch);
    } catch (e) {
      _log.w('[Storage] cacheList($key) failed: $e');
    }
  }

  /// Retrieve a cached JSON list.  Returns null if not found.
  List<dynamic>? getCachedList(String key) {
    try {
      final raw = _cacheBox.get(key) as String?;
      if (raw == null) return null;
      return jsonDecode(raw) as List<dynamic>;
    } catch (e) {
      _log.w('[Storage] getCachedList($key) failed: $e');
      return null;
    }
  }

  /// Remove a cache entry.
  Future<void> clearCache(String key) async {
    await _cacheBox.delete(key);
    await _cacheBox.delete('${key}_ts');
  }

  /// Wipe all cached data.
  Future<void> clearAllCache() async {
    await _cacheBox.clear();
    _log.i('[Storage] All cache cleared');
  }

  // ──────────────────────────────────────
  //  SETTINGS BOX — user preferences
  // ──────────────────────────────────────

  // --- Settings Keys ---
  static const String keyThemeMode = 'theme_mode';      // 'dark' | 'light'
  static const String keyWindowX = 'window_x';
  static const String keyWindowY = 'window_y';
  static const String keyWindowW = 'window_w';
  static const String keyWindowH = 'window_h';
  static const String keyWindowMaximized = 'window_maximized';
  static const String keyLastTab = 'last_tab';
  static const String keySidebarCollapsed = 'sidebar_collapsed';
  static const String keyRebalanceResidency = 'rebalance_residency'; // 'resident' | 'nri'

  /// Read a setting value.
  T? getSetting<T>(String key) {
    try {
      return _settingsBox.get(key) as T?;
    } catch (e) {
      _log.w('[Storage] getSetting($key) failed: $e');
      return null;
    }
  }

  /// Write a setting value.
  Future<void> setSetting<T>(String key, T value) async {
    try {
      await _settingsBox.put(key, value);
    } catch (e) {
      _log.w('[Storage] setSetting($key) failed: $e');
    }
  }

  /// Get the saved theme preference.  Defaults to 'dark'.
  String getThemeMode() => getSetting<String>(keyThemeMode) ?? 'dark';

  /// Persist the current theme preference.
  Future<void> setThemeMode(String mode) => setSetting(keyThemeMode, mode);

  /// Convenience: read a boolean setting.
  bool? getBool(String key) => getSetting<bool>(key);

  /// Convenience: write a boolean setting.
  Future<void> setBool(String key, bool value) => setSetting(key, value);

  // ──────────────────────────────────────
  //  WINDOW STATE — save/restore position
  // ──────────────────────────────────────

  /// Save window bounds + maximized state.
  Future<void> saveWindowState({
    required double x,
    required double y,
    required double width,
    required double height,
    required bool isMaximized,
  }) async {
    await Future.wait([
      setSetting(keyWindowX, x),
      setSetting(keyWindowY, y),
      setSetting(keyWindowW, width),
      setSetting(keyWindowH, height),
      setSetting(keyWindowMaximized, isMaximized),
    ]);
  }

  /// Retrieve saved window state.  Returns null if never saved.
  WindowState? getWindowState() {
    final x = getSetting<double>(keyWindowX);
    final y = getSetting<double>(keyWindowY);
    final w = getSetting<double>(keyWindowW);
    final h = getSetting<double>(keyWindowH);
    final maximized = getSetting<bool>(keyWindowMaximized) ?? false;

    if (x == null || y == null || w == null || h == null) return null;
    return WindowState(x: x, y: y, width: w, height: h, isMaximized: maximized);
  }

  // ──────────────────────────────────────
  //  SECURE BOX — tokens & secrets
  // ──────────────────────────────────────

  // --- Secure Keys ---
  static const String keyKiteToken = 'kite_access_token';
  static const String keyKiteRefreshToken = 'kite_refresh_token';
  static const String keyGoogleToken = 'google_auth_token';

  /// Store a secret value.
  Future<void> setSecure(String key, String value) async {
    try {
      await _secureBox.put(key, value);
    } catch (e) {
      _log.w('[Storage] setSecure($key) failed: $e');
    }
  }

  /// Retrieve a secret value.
  String? getSecure(String key) {
    try {
      return _secureBox.get(key) as String?;
    } catch (e) {
      _log.w('[Storage] getSecure($key) failed: $e');
      return null;
    }
  }

  /// Delete a secret.
  Future<void> deleteSecure(String key) async {
    await _secureBox.delete(key);
  }

  /// Wipe all secrets.
  Future<void> clearAllSecure() async {
    await _secureBox.clear();
    _log.i('[Storage] All secure data cleared');
  }

  // ──────────────────────────────────────
  //  CRASH RECOVERY
  // ──────────────────────────────────────

  static const String keyCrashFlag = 'last_crash';

  /// Mark that the app started cleanly (call after successful init).
  Future<void> markCleanStart() async {
    await _settingsBox.delete(keyCrashFlag);
  }

  /// Mark that a crash occurred.
  Future<void> markCrash(String error) async {
    await _settingsBox.put(keyCrashFlag, {
      'error': error,
      'time': DateTime.now().toIso8601String(),
    });
  }

  /// Check if the previous session crashed.
  Map<String, dynamic>? getLastCrash() {
    final raw = _settingsBox.get(keyCrashFlag);
    if (raw == null) return null;
    return Map<String, dynamic>.from(raw as Map);
  }


  // ──────────────────────────────────────
  //  ALLOCATION DASHBOARD — other assets & targets
  // ──────────────────────────────────────

  static const String keyOtherAssets = 'allocation_other_assets';
  static const String keyRiskProfile = 'allocation_risk_profile';
  static const String keyCustomTargets = 'allocation_custom_targets';

  /// Save manually-entered other assets (Gold, Cash, International, etc.)
  /// as a JSON map: { "Gold": 50000, "Cash": 100000, ... }
  Future<void> saveOtherAssets(Map<String, double> assets) async {
    try {
      await _settingsBox.put(keyOtherAssets, jsonEncode(assets));
    } catch (e) {
      _log.w('[Storage] saveOtherAssets failed: $e');
    }
  }

  /// Retrieve other assets.  Returns empty map if none saved.
  Map<String, double> getOtherAssets() {
    try {
      final raw = _settingsBox.get(keyOtherAssets) as String?;
      if (raw == null) return {};
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      return decoded.map((k, v) => MapEntry(k, (v as num).toDouble()));
    } catch (e) {
      _log.w('[Storage] getOtherAssets failed: $e');
      return {};
    }
  }

  /// Save risk profile preference: 'conservative', 'moderate', 'aggressive'
  Future<void> saveRiskProfile(String profile) =>
      setSetting(keyRiskProfile, profile);

  /// Get risk profile.  Defaults to 'moderate'.
  String getRiskProfile() =>
      getSetting<String>(keyRiskProfile) ?? 'moderate';

  /// Save custom target allocation percentages as JSON.
  Future<void> saveCustomTargets(Map<String, double> targets) async {
    try {
      await _settingsBox.put(keyCustomTargets, jsonEncode(targets));
    } catch (e) {
      _log.w('[Storage] saveCustomTargets failed: $e');
    }
  }

  /// Retrieve custom target allocation percentages.
  Map<String, double>? getCustomTargets() {
    try {
      final raw = _settingsBox.get(keyCustomTargets) as String?;
      if (raw == null) return null;
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      return decoded.map((k, v) => MapEntry(k, (v as num).toDouble()));
    } catch (e) {
      _log.w('[Storage] getCustomTargets failed: $e');
      return null;
    }
  }

  // ──────────────────────────────────────
  //  EXPENSE DASHBOARD — imported yearly sheets
  // ──────────────────────────────────────

  static const String _keyExpensePrefix = 'expense_year_';
  static const String keyExpenseYearsIndex = 'expense_years_index';

  /// Persist a parsed expense sheet for [year] and track it in the index.
  Future<void> saveExpenseYear(int year, Map<String, dynamic> data) async {
    try {
      await _settingsBox.put('$_keyExpensePrefix$year', jsonEncode(data));
      final years = getExpenseYears().toSet()..add(year);
      final sorted = years.toList()..sort();
      await _settingsBox.put(keyExpenseYearsIndex, sorted);
    } catch (e) {
      _log.w('[Storage] saveExpenseYear($year) failed: $e');
    }
  }

  /// Load the parsed expense sheet for [year], or null if not imported.
  Map<String, dynamic>? getExpenseYear(int year) {
    try {
      final raw = _settingsBox.get('$_keyExpensePrefix$year') as String?;
      if (raw == null) return null;
      return jsonDecode(raw) as Map<String, dynamic>;
    } catch (e) {
      _log.w('[Storage] getExpenseYear($year) failed: $e');
      return null;
    }
  }

  /// Years that have an imported sheet, ascending.
  List<int> getExpenseYears() {
    try {
      final raw = _settingsBox.get(keyExpenseYearsIndex);
      if (raw == null) return [];
      return List<int>.from((raw as List).map((e) => e is int ? e : int.parse('$e')));
    } catch (e) {
      _log.w('[Storage] getExpenseYears failed: $e');
      return [];
    }
  }

  /// Remove an imported year.
  Future<void> deleteExpenseYear(int year) async {
    await _settingsBox.delete('$_keyExpensePrefix$year');
    final years = getExpenseYears().where((y) => y != year).toList();
    await _settingsBox.put(keyExpenseYearsIndex, years);
  }

  // ──────────────────────────────────────
  //  EXPENSE — change history log
  // ──────────────────────────────────────

  static const String keyExpenseHistory = 'expense_history_log';

  /// Append change entries to the full-history log (kept for all years).
  Future<void> appendExpenseHistory(List<Map<String, dynamic>> entries) async {
    if (entries.isEmpty) return;
    try {
      final log = getExpenseHistory()..addAll(entries);
      await _settingsBox.put(keyExpenseHistory, jsonEncode(log));
    } catch (e) {
      _log.w('[Storage] appendExpenseHistory failed: $e');
    }
  }

  /// The full change-history log (oldest first).
  List<Map<String, dynamic>> getExpenseHistory() {
    try {
      final raw = _settingsBox.get(keyExpenseHistory) as String?;
      if (raw == null) return [];
      return (jsonDecode(raw) as List)
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
    } catch (e) {
      _log.w('[Storage] getExpenseHistory failed: $e');
      return [];
    }
  }

  /// Next sequential change id for [date] (yyyyMMdd), e.g. CHG-20260704-001.
  int nextChangeSeq(String yyyymmdd) {
    final prefix = 'CHG-$yyyymmdd-';
    var max = 0;
    for (final e in getExpenseHistory()) {
      final id = '${e['changeId'] ?? ''}';
      if (id.startsWith(prefix)) {
        final n = int.tryParse(id.substring(prefix.length)) ?? 0;
        if (n > max) max = n;
      }
    }
    return max + 1;
  }

  // ──────────────────────────────────────
  //  EXPENSE — version snapshots (restore)
  // ──────────────────────────────────────

  static const String keyExpenseVersionsPrefix = 'expense_version_';
  static const String keyExpenseVersionsIndex = 'expense_versions_index';

  /// Store a full-dataset snapshot under [versionId] and index it.
  Future<void> saveExpenseVersion(
      String versionId, Map<String, dynamic> snapshot) async {
    try {
      await _settingsBox.put(
          '$keyExpenseVersionsPrefix$versionId', jsonEncode(snapshot));
      final idx = getExpenseVersionIndex();
      idx.insert(0, {
        'versionId': versionId,
        'ts': snapshot['ts'] ?? DateTime.now().toIso8601String(),
        'label': snapshot['label'] ?? versionId,
      });
      // Keep the most recent 50 snapshots locally.
      final trimmed = idx.take(50).toList();
      await _settingsBox.put(keyExpenseVersionsIndex, jsonEncode(trimmed));
    } catch (e) {
      _log.w('[Storage] saveExpenseVersion failed: $e');
    }
  }

  /// Version index (newest first): [{versionId, ts, label}].
  List<Map<String, dynamic>> getExpenseVersionIndex() {
    try {
      final raw = _settingsBox.get(keyExpenseVersionsIndex) as String?;
      if (raw == null) return [];
      return (jsonDecode(raw) as List)
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
    } catch (e) {
      return [];
    }
  }

  /// Load a stored snapshot by version id.
  Map<String, dynamic>? getExpenseVersion(String versionId) {
    try {
      final raw = _settingsBox.get('$keyExpenseVersionsPrefix$versionId') as String?;
      if (raw == null) return null;
      return jsonDecode(raw) as Map<String, dynamic>;
    } catch (e) {
      return null;
    }
  }

  // ──────────────────────────────────────
  //  EXPENSE — save / upload status
  // ──────────────────────────────────────

  static const String keyExpenseLastSaved = 'expense_last_saved';
  static const String keyExpenseLastUploaded = 'expense_last_uploaded';
  static const String keyExpenseSyncStatus = 'expense_sync_status';

  Future<void> setExpenseLastSaved(String iso) =>
      setSetting(keyExpenseLastSaved, iso);
  String? getExpenseLastSaved() => getSetting<String>(keyExpenseLastSaved);

  Future<void> setExpenseLastUploaded(String iso) =>
      setSetting(keyExpenseLastUploaded, iso);
  String? getExpenseLastUploaded() => getSetting<String>(keyExpenseLastUploaded);

  /// Sync status: 'success' | 'pending' | 'failed' | 'disabled' | 'conflict'
  /// ('conflict' = upload held back because Drive moved ahead of us).
  Future<void> setExpenseSyncStatus(String status) =>
      setSetting(keyExpenseSyncStatus, status);
  String getExpenseSyncStatus() =>
      getSetting<String>(keyExpenseSyncStatus) ?? 'disabled';

  // ──────────────────────────────────────
  //  CLEANUP
  // ──────────────────────────────────────

  /// Close all Hive boxes.  Call on app termination.
  Future<void> dispose() async {
    await _cacheBox.close();
    await _settingsBox.close();
    await _secureBox.close();
    _log.i('[Storage] All boxes closed');
  }
}

/// Simple data class for saved window position/size.
class WindowState {
  final double x, y, width, height;
  final bool isMaximized;

  const WindowState({
    required this.x,
    required this.y,
    required this.width,
    required this.height,
    this.isMaximized = false,
  });

  @override
  String toString() =>
      'WindowState(${width.toInt()}x${height.toInt()} at ${x.toInt()},${y.toInt()}'
      '${isMaximized ? " maximized" : ""})';
}
