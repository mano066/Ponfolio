import 'package:dio/dio.dart';
import 'package:logger/logger.dart';
import '../core/constants.dart';
import '../data/models/expense_config.dart';

/// Talks to the backend's Google Drive + auth endpoints for the expense
/// dataset. The backend owns the OAuth tokens (drive.appdata scope); this
/// service only sends the serialized dataset up and pulls versions back.
///
/// Everything degrades gracefully: when the user is not signed in, [backup]
/// still saves locally on the backend and reports `driveStatus: pending`.
class DriveSyncService {
  static final DriveSyncService _instance = DriveSyncService._internal();
  factory DriveSyncService() => _instance;
  DriveSyncService._internal();

  final _log = Logger(printer: PrettyPrinter(methodCount: 0));

  final Dio _dio = Dio(BaseOptions(
    baseUrl: AppConstants.apiBase,
    connectTimeout: const Duration(seconds: 6),
    receiveTimeout: const Duration(seconds: 30),
    headers: {'Content-Type': 'application/json'},
  ));

  // ── Auth / status ───────────────────────────────────────────────

  /// Current Google profile, or null when not signed in / backend down.
  Future<Map<String, dynamic>?> authProfile() async {
    try {
      final r = await _dio.get('/auth/profile');
      final data = r.data;
      if (data is Map && data['email'] != null) {
        return Map<String, dynamic>.from(data);
      }
    } catch (_) {}
    return null;
  }

  /// Get the Google OAuth URL (backend starts a local callback server).
  Future<String?> googleAuthUrl() async {
    try {
      final r = await _dio.get('/auth/google/url');
      return (r.data is Map) ? r.data['url'] as String? : null;
    } catch (e) {
      _log.w('[Drive] auth url failed: $e');
      return null;
    }
  }

  Future<bool> driveLoggedIn() async {
    try {
      final r = await _dio.get('/drive/status');
      return r.data is Map && r.data['logged_in'] == true;
    } catch (_) {
      return false;
    }
  }

  // ── Backup / sync ────────────────────────────────────────────────

  /// Save + upload the dataset. Returns the backend result, or a synthetic
  /// pending/failed result when the backend is unreachable (offline).
  Future<DriveBackupResult> backup({
    required Map<String, dynamic> master,
    required String masterName,
    String? backupName,
    List<Map<String, dynamic>>? history,
    String historyName = 'dashboard_history_log.json',
  }) async {
    try {
      final r = await _dio.post('/expense/backup', data: {
        'master': master,
        'master_name': masterName,
        'backup_name': ?backupName,
        'history': ?history,
        'history_name': historyName,
      });
      final d = r.data is Map ? Map<String, dynamic>.from(r.data) : {};
      return DriveBackupResult(
        saved: d['saved'] == true,
        authenticated: d['authenticated'] == true,
        driveStatus: '${d['driveStatus'] ?? 'pending'}',
        uploads: (d['uploads'] is Map)
            ? Map<String, dynamic>.from(d['uploads'])
            : {},
      );
    } catch (e) {
      _log.w('[Drive] backup failed (offline?): $e');
      // Backend unreachable → treat as offline: local Hive already holds the
      // data; mark upload pending so the badge shows "sync pending".
      return const DriveBackupResult(
        saved: false,
        authenticated: false,
        driveStatus: 'pending',
        uploads: {},
        offline: true,
      );
    }
  }

  /// List dataset versions available on Drive (newest first).
  Future<List<DriveVersion>> listVersions() async {
    try {
      final r = await _dio.get('/expense/versions');
      final data = r.data;
      if (data is Map && data['versions'] is List) {
        return [
          for (final v in (data['versions'] as List))
            if (v is Map)
              DriveVersion(
                name: '${v['name'] ?? ''}',
                modifiedTime: '${v['modifiedTime'] ?? ''}',
                size: '${v['size'] ?? ''}',
              ),
        ];
      }
    } catch (e) {
      _log.w('[Drive] listVersions failed: $e');
    }
    return [];
  }

  /// Fetch a specific version's dataset JSON from Drive.
  Future<Map<String, dynamic>?> getVersion(String name) async {
    try {
      final r = await _dio.get('/expense/version',
          queryParameters: {'name': name});
      if (r.data is Map && r.data['master'] is Map) {
        return Map<String, dynamic>.from(r.data['master']);
      }
    } catch (e) {
      _log.w('[Drive] getVersion($name) failed: $e');
    }
    return null;
  }

  /// Drive modifiedTime for the master file, for conflict detection.
  Future<String?> masterModifiedTime({String? name}) async {
    name ??= ExpenseConfig.current.masterFileName;
    try {
      final r = await _dio.get('/expense/drive-meta',
          queryParameters: {'name': name});
      if (r.data is Map && r.data['meta'] is Map) {
        return '${(r.data['meta'] as Map)['modifiedTime'] ?? ''}';
      }
    } catch (_) {}
    return null;
  }
}

class DriveBackupResult {
  final bool saved;
  final bool authenticated;
  final String driveStatus; // success | pending | failed | disabled
  final Map<String, dynamic> uploads;
  final bool offline;
  const DriveBackupResult({
    required this.saved,
    required this.authenticated,
    required this.driveStatus,
    required this.uploads,
    this.offline = false,
  });
}

class DriveVersion {
  final String name;
  final String modifiedTime;
  final String size;
  const DriveVersion({
    required this.name,
    required this.modifiedTime,
    required this.size,
  });
}

final driveSyncService = DriveSyncService();
