import 'dart:async';
import 'dart:convert';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/expense_import_service.dart';
import '../services/drive_sync_service.dart';
import '../data/models/expense_config.dart';
import '../data/models/expense_schema.dart';
import '../data/models/expense_history.dart';
import 'providers.dart';

/// Currently-selected expense year (the year switcher on the Expenses screen).
class SelectedExpenseYearNotifier extends Notifier<int> {
  @override
  int build() => 2026;
  void set(int year) => state = year;
}

final selectedExpenseYearProvider =
    NotifierProvider<SelectedExpenseYearNotifier, int>(
        SelectedExpenseYearNotifier.new);

/// Currently-selected month for the Monthly Expense Overview (a month key like
/// 'jan'). Kept in a provider so it survives page/tab switches.
class SelectedExpenseMonthNotifier extends Notifier<String> {
  @override
  String build() => 'jan';
  void set(String monthKey) => state = monthKey;
}

final selectedExpenseMonthProvider =
    NotifierProvider<SelectedExpenseMonthNotifier, String>(
        SelectedExpenseMonthNotifier.new);

/// Store of expense sheets, keyed by year, backed by local storage. Years
/// listed in the local expense config (`seed_years`) are seeded once from
/// bundled `assets/private/expense_<year>.html` sheets when the build has them;
/// a public build has none and starts empty. All data is then editable and
/// persisted, and future years can be added blank.
class ExpenseStore extends Notifier<ExpenseState> {
  static Map<int, String> get _seedAssets => {
        for (final y in ExpenseConfig.current.seedYears) y: ExpenseConfig.seedAsset(y),
      };
  // v6: re-seed so bundled sheets carry source provenance (row/column/cell
  // references) and auto-detected extra categories.
  static const _seedFlag = 'expense_seeded_v6';

  @override
  ExpenseState build() {
    final storage = ref.read(localStorageProvider);
    final byYear = <int, Map<String, dynamic>>{};
    for (final y in storage.getExpenseYears()) {
      final d = storage.getExpenseYear(y);
      if (d != null) {
        ExpenseSchema.recompute(d);
        byYear[y] = d;
      }
    }
    // Seed the bundled historical sheets once, off the build path.
    Future(() => _seedFromAssets());
    return ExpenseState(
      byYear: byYear,
      importing: false,
      syncStatus: storage.getExpenseSyncStatus(),
      lastSavedIso: storage.getExpenseLastSaved(),
      lastUploadedIso: storage.getExpenseLastUploaded(),
    );
  }

  /// Parse the bundled HTML sheets and load any year not already present.
  Future<void> _seedFromAssets() async {
    final storage = ref.read(localStorageProvider);
    if (storage.getSetting<bool>(_seedFlag) == true) return;
    final next = Map<int, Map<String, dynamic>>.from(state.byYear);
    var added = false;
    // Runs once (gated by _seedFlag): the bundled sheets are the source of
    // truth for their years, so load them authoritatively. Future years the user
    // has added are keyed separately and left untouched.
    for (final e in _seedAssets.entries) {
      try {
        final content = await rootBundle.loadString(e.value);
        final parsed = expenseImportService
            .parseContent(content, isHtml: true, fallbackYear: e.key);
        parsed['year'] = e.key;
        parsed['imported_at'] = 'bundled';
        await storage.saveExpenseYear(e.key, parsed);
        next[e.key] = parsed;
        added = true;
      } catch (_) {/* skip a missing/unreadable asset */}
    }
    await storage.setSetting(_seedFlag, true);
    if (added) state = state.copyWith(byYear: next);
  }

  /// Years to offer: the seeded trio, any saved year, and always one blank slot
  /// beyond the latest so a future year can be started.
  List<int> get years {
    final s = {2024, 2025, 2026, ...state.byYear.keys};
    final list = s.toList()..sort();
    return list;
  }

  Map<String, dynamic> viewFor(int year) =>
      state.byYear[year] ?? ExpenseSchema.blankYear(year);

  bool hasData(int year) => state.byYear.containsKey(year);

  Map<String, dynamic> _clone(Map<String, dynamic> m) =>
      jsonDecode(jsonEncode(m)) as Map<String, dynamic>;

  /// Create the next future year (max+1) as a blank editable sheet and select it.
  int addFutureYear() {
    final maxY = years.reduce((a, b) => a > b ? a : b);
    final y = maxY + 1;
    final data = ExpenseSchema.blankYear(y);
    _commit(y, data);
    ref.read(selectedExpenseYearProvider.notifier).set(y);
    return y;
  }

  /// Commit a freshly-imported/parsed sheet under its detected year and select
  /// it. Used by the "Import Excel" action on the Raw Dataset Entry page.
  int applyImported(Map<String, dynamic> parsed) {
    final y = (parsed['year'] as num?)?.toInt() ?? 0;
    if (y < 2000) return 0;
    _commit(y, _clone(parsed));
    ref.read(selectedExpenseYearProvider.notifier).set(y);
    return y;
  }

  void updateMonthCell(
      int year, String section, int rowIndex, String key, Object value) {
    final data = _clone(state.byYear[year] ?? ExpenseSchema.blankYear(year));
    final sec = Map<String, dynamic>.from(data[section] as Map);
    final rows = (sec['months'] as List)
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
    if (rowIndex < 0 || rowIndex >= rows.length) return;
    rows[rowIndex][key] = value;
    sec['months'] = rows;
    data[section] = sec;
    _commit(year, data);
  }

  void updateStockCell(int year, int rowIndex, String key, Object value) {
    final data = _clone(state.byYear[year] ?? ExpenseSchema.blankYear(year));
    final sec = Map<String, dynamic>.from(data['stocks'] as Map);
    final trades = (sec['trades'] as List)
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
    if (rowIndex < 0 || rowIndex >= trades.length) return;
    if (key.startsWith('scrip:')) {
      final name = key.substring(6);
      final scripsMap = trades[rowIndex]['scrips'] is Map
          ? Map<String, dynamic>.from(trades[rowIndex]['scrips'])
          : <String, dynamic>{};
      scripsMap[name] = value;
      trades[rowIndex]['scrips'] = scripsMap;
    } else {
      trades[rowIndex][key] = value;
    }
    sec['trades'] = trades;
    data['stocks'] = sec;
    _commit(year, data);
  }

  void addStockRow(int year) {
    final data = _clone(state.byYear[year] ?? ExpenseSchema.blankYear(year));
    final sec = Map<String, dynamic>.from(data['stocks'] as Map);
    final trades = (sec['trades'] as List)
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList()
      ..add(ExpenseSchema.blankStockTrade());
    sec['trades'] = trades;
    data['stocks'] = sec;
    _commit(year, data);
  }

  void deleteStockRow(int year, int rowIndex) {
    final data = _clone(state.byYear[year] ?? ExpenseSchema.blankYear(year));
    final sec = Map<String, dynamic>.from(data['stocks'] as Map);
    final trades = (sec['trades'] as List)
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
    if (rowIndex < 0 || rowIndex >= trades.length) return;
    trades.removeAt(rowIndex);
    sec['trades'] = trades;
    data['stocks'] = sec;
    _commit(year, data);
  }

  void _commit(int year, Map<String, dynamic> data) {
    ExpenseSchema.recompute(data);
    final next = Map<int, Map<String, dynamic>>.from(state.byYear)..[year] = data;
    // Bump version + stamp recalc time so the provider always notifies and the
    // whole dashboard (which watches this provider) rebuilds from fresh data.
    state = state.copyWith(
      byYear: next,
      version: state.version + 1,
      lastRecalcIso: _iso(),
      recalcFailed: false,
    );
    ref.read(localStorageProvider).saveExpenseYear(year, data);
  }

  /// Re-read every year from local storage (the persisted master raw dataset),
  /// re-run the calculation engine, and publish a fresh global state so every
  /// screen rebuilds. This is the "reload → parse → recalculate → notify" step
  /// of the save flow. Returns false if recalculation threw.
  bool reloadAndRecalculate() {
    try {
      final storage = ref.read(localStorageProvider);
      final rebuilt = <int, Map<String, dynamic>>{};
      for (final y in storage.getExpenseYears()) {
        final d = storage.getExpenseYear(y);
        if (d != null) {
          ExpenseSchema.recompute(d);
          rebuilt[y] = d;
        }
      }
      // Keep any in-memory years not yet indexed in storage (defensive).
      for (final e in state.byYear.entries) {
        rebuilt.putIfAbsent(e.key, () => e.value);
      }
      state = state.copyWith(
        byYear: rebuilt,
        version: state.version + 1,
        lastRecalcIso: _iso(),
        recalcFailed: false,
      );
      return true;
    } catch (_) {
      state = state.copyWith(recalcFailed: true);
      return false;
    }
  }

  // ══════════════════════════════════════════════════════════════
  //  RAW DATASET ENTRY — dynamic fields, notes, soft-delete
  // ══════════════════════════════════════════════════════════════

  static String _norm(String s) =>
      s.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');

  /// Add a new local-ledger field (kind: 'expense' | 'income' | 'transfer'). It
  /// becomes an editable column and flows into the right total automatically.
  void addLocalField(int year, String label, {String kind = 'expense'}) {
    final clean = label.trim();
    if (clean.isEmpty) return;
    final data = _clone(state.byYear[year] ?? ExpenseSchema.blankYear(year));
    final sec = Map<String, dynamic>.from(data['local'] as Map);
    final defs = (sec['extra_categories'] is List)
        ? List<Map<String, dynamic>>.from(
            (sec['extra_categories'] as List).map((e) => Map<String, dynamic>.from(e as Map)))
        : <Map<String, dynamic>>[];
    final key = 'x_${_norm(clean)}';
    if (defs.any((d) => d['key'] == key)) return; // already exists
    defs.add({'key': key, 'label': clean, 'kind': kind});
    sec['extra_categories'] = defs;
    final rows = (sec['months'] as List)
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
    for (final r in rows) {
      r[key] ??= 0.0;
    }
    sec['months'] = rows;
    data['local'] = sec;
    _commit(year, data);
  }

  /// Add a new investment fund / index column (e.g. "Nifty 50", "S&P 500"). It
  /// becomes an editable column in the Investment Contributions grid and flows
  /// into the Total automatically.
  void addInvestField(int year, String label) {
    final clean = label.trim();
    if (clean.isEmpty) return;
    final data = _clone(state.byYear[year] ?? ExpenseSchema.blankYear(year));
    final sec = Map<String, dynamic>.from(data['investments'] as Map);
    final defs = (sec['extra_categories'] is List)
        ? List<Map<String, dynamic>>.from(
            (sec['extra_categories'] as List).map((e) => Map<String, dynamic>.from(e as Map)))
        : <Map<String, dynamic>>[];
    final key = 'x_${_norm(clean)}';
    if (defs.any((d) => d['key'] == key)) return; // already exists
    defs.add({'key': key, 'label': clean, 'kind': 'invest'});
    sec['extra_categories'] = defs;
    final rows = (sec['months'] as List)
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
    for (final r in rows) {
      r[key] ??= 0.0;
    }
    sec['months'] = rows;
    data['investments'] = sec;
    _commit(year, data);
  }

  /// Set a free-text note on a month row of any month-based section.
  void setMonthNote(int year, String section, int rowIndex, String note) =>
      updateMonthCell(year, section, rowIndex, 'note', note);

  /// Soft-delete / restore a stock trade (kept in raw, excluded from totals).
  void setStockDeleted(int year, int rowIndex, bool deleted) {
    final data = _clone(state.byYear[year] ?? ExpenseSchema.blankYear(year));
    final sec = Map<String, dynamic>.from(data['stocks'] as Map);
    final trades = (sec['trades'] as List)
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
    if (rowIndex < 0 || rowIndex >= trades.length) return;
    trades[rowIndex]['_deleted'] = deleted;
    sec['trades'] = trades;
    data['stocks'] = sec;
    _commit(year, data);
  }

  // ══════════════════════════════════════════════════════════════
  //  SAVE PIPELINE — validate → persist → history → version → Drive
  // ══════════════════════════════════════════════════════════════

  static String _iso() => DateTime.now().toIso8601String();
  static String _p2(int n) => n.toString().padLeft(2, '0');
  static String _stamp([DateTime? t]) {
    final d = t ?? DateTime.now();
    return '${d.year}-${_p2(d.month)}-${_p2(d.day)} ${_p2(d.hour)}:${_p2(d.minute)}';
  }

  static String _yyyymmdd([DateTime? t]) {
    final d = t ?? DateTime.now();
    return '${d.year}${_p2(d.month)}${_p2(d.day)}';
  }

  Map<String, dynamic> _fullDataset() => {
        'app': 'aiei_wealth',
        'type': ExpenseConfig.datasetType,
        'savedAt': _iso(),
        'years': {
          for (final e in state.byYear.entries) '${e.key}': e.value,
        },
      };

  /// Validate the current year without saving.
  List<ValidationIssue> validateYear(int year) => ExpenseValidation.validate(
      state.byYear[year] ?? ExpenseSchema.blankYear(year), year);

  /// Save (draft or final). Final save is blocked by validation errors;
  /// warnings never block. On final save the dataset is versioned, the change
  /// history is appended, and a Drive backup is kicked off (best-effort).
  Future<SaveResult> saveDataset(int year,
      {bool draft = false, String note = ''}) async {
    final storage = ref.read(localStorageProvider);
    state = state.copyWith(saving: true);
    final data = _clone(state.byYear[year] ?? ExpenseSchema.blankYear(year));
    ExpenseSchema.recompute(data);

    final issues = ExpenseValidation.validate(data, year);
    if (!draft && ExpenseValidation.hasBlockingErrors(issues)) {
      state = state.copyWith(
        saving: false,
        validation: issues,
        saveSummary: 'Save blocked — fix ${issues.where((i) => i.isError).length} error(s).',
      );
      return SaveResult(ok: false, blocked: true, issues: issues);
    }

    // Diff vs the previously-saved copy of this year → change-history entries.
    final prev = state.byYear[year];
    final changes = _diffChanges(prev, data, year, note, draft ? 'draft' : 'saved');

    // (2/3) Save the new value into the master raw dataset + local storage,
    // recompute, and notify all pages.
    _commit(year, data);

    // (4) Append to the full change-history log.
    if (changes.isNotEmpty) {
      await storage.appendExpenseHistory(changes.map((c) => c.toJson()).toList());
    }

    // Snapshot a restorable version (this year's data).
    final snapId = 'V-${_yyyymmdd()}${_p2(DateTime.now().hour)}${_p2(DateTime.now().minute)}${_p2(DateTime.now().second)}';
    await storage.saveExpenseVersion(snapId, {
      'ts': _iso(),
      'label': '${draft ? 'Draft' : 'Save'} $year',
      'year': year,
      'data': data,
    });

    // (6-10) Re-read the latest master from storage, re-run the calculation
    // engine, publish fresh global state and notify every screen. If this
    // throws, the raw data is safe but the dashboard didn't recalc.
    final recalcOk = reloadAndRecalculate();

    final nowIso = _iso();
    await storage.setExpenseLastSaved(nowIso);
    state = state.copyWith(
      saving: false,
      validation: issues,
      lastSavedIso: nowIso,
      recalcFailed: !recalcOk,
      saveSummary: !recalcOk
          ? 'Raw data was saved, but dashboard recalculation failed.'
          : draft
              ? 'Draft saved & dashboard refreshed · ${changes.length} change(s)'
              : 'Saved & dashboard refreshed · ${changes.length} change(s)'
                  '${issues.isNotEmpty ? ' · ${issues.length} warning(s)' : ''}',
    );

    // (5) Final save → back up to Google Drive (fire-and-forget).
    if (!draft) {
      unawaited(_uploadToDrive());
    }
    return SaveResult(
        ok: recalcOk, changeCount: changes.length, issues: issues, recalcFailed: !recalcOk);
  }

  /// The full save-and-refresh flow requested by the dashboard spec:
  /// validate → update master raw dataset → save locally → history log →
  /// Drive sync → reload latest master → recalculate → update global state →
  /// notify all screens. Thin alias over [saveDataset] (which performs every
  /// step) so callers/read as the documented entry point.
  Future<SaveResult> saveRawEntryAndRefreshDashboard(int year,
          {bool draft = false, String note = ''}) =>
      saveDataset(year, draft: draft, note: note);

  /// Push the full dataset + a timestamped backup + the history log to Drive.
  ///
  /// Unless [force] is set, the Drive master is checked first: if it changed
  /// after our last upload, another client (or an older copy of this one) holds
  /// edits we do not have, and uploading would silently destroy them. In that
  /// case nothing is sent — the conflict is published on the state so the entry
  /// screen can ask the user to resolve it. [force] is how that dialog's
  /// "Keep Local" / "Save Both" choices then push anyway.
  Future<void> _uploadToDrive({bool force = false}) async {
    final storage = ref.read(localStorageProvider);
    if (!force) {
      final conflict = await checkDriveConflict();
      if (conflict != null) {
        await storage.setExpenseSyncStatus('conflict');
        state = state.copyWith(
          syncStatus: 'conflict',
          driveConflictTime: conflict,
          saveSummary: '${state.saveSummary} · Drive has newer data — '
              'upload held back',
        );
        return;
      }
    }
    await storage.setExpenseSyncStatus('pending');
    state = state.copyWith(syncStatus: 'pending');
    final now = DateTime.now();
    // One backup per day, overwritten by later saves that day. A per-minute
    // name left a new Drive file behind on every save; the backend also skips
    // the backup entirely when the master is unchanged and prunes to the
    // newest 30.
    final backupName = ExpenseConfig.current.backupFileName(now);
    final res = await driveSyncService.backup(
      master: _fullDataset(),
      masterName: ExpenseConfig.current.masterFileName,
      backupName: backupName,
      history: storage.getExpenseHistory(),
    );
    await storage.setExpenseSyncStatus(res.driveStatus);
    final uploadedIso = res.driveStatus == 'success' ? _iso() : null;
    if (uploadedIso != null) await storage.setExpenseLastUploaded(uploadedIso);
    state = state.copyWith(
      syncStatus: res.driveStatus,
      lastUploadedIso: uploadedIso ?? state.lastUploadedIso,
      clearDriveConflict: true,
      saveSummary: switch (res.driveStatus) {
        'success' => '${state.saveSummary} · uploaded to Drive',
        'pending' => '${state.saveSummary} · Drive sync pending (sign in / offline)',
        _ => '${state.saveSummary} · Drive upload failed',
      },
    );
  }

  /// Manually retry the Drive upload (e.g. after connecting or coming online).
  /// Pass [force] to overwrite a newer Drive master deliberately — only the
  /// conflict dialog's "Keep Local" / "Save Both" choices should do that.
  Future<void> syncToDrive({bool force = false}) =>
      _uploadToDrive(force: force);

  // ── History diffing ─────────────────────────────────────────────

  static const _calcSkip = {
    'total_income', 'total_opening', 'total_expense', 'actual_expense',
    'transfer_total', 'balance', 'after', 'total', 'total_spend', 'opening',
    'month', 'label', 'note', 'scrips', '_deleted',
  };

  List<ExpenseChange> _diffChanges(Map<String, dynamic>? prev,
      Map<String, dynamic> cur, int year, String note, String status) {
    final storage = ref.read(localStorageProvider);
    final changes = <ExpenseChange>[];
    final ymd = _yyyymmdd();
    var seq = storage.nextChangeSeq(ymd);
    final ts = _stamp();

    void emit({
      required String section,
      required String sectionLabel,
      required String monthKey,
      required String column,
      required int row,
      required String cell,
      required Object? oldV,
      required Object? newV,
      required String currency,
    }) {
      changes.add(ExpenseChange(
        changeId: 'CHG-$ymd-${seq.toString().padLeft(3, '0')}',
        timestamp: ts,
        action: (oldV == null || oldV == 0) && newV != null && newV != 0
            ? 'add'
            : 'edit',
        sourceSheet: '$year',
        sourceSection: sectionLabel,
        year: year,
        month: monthKey.isEmpty
            ? ''
            : '${ExpenseSchema.monthTitle(monthKey)} $year',
        sourceRow: row,
        sourceColumn: column,
        sourceCellAddress: cell,
        oldValue: oldV,
        newValue: newV,
        currency: currency,
        note: note,
        saveStatus: status,
        driveUploadStatus: 'pending',
      ));
      seq++;
    }

    // Month-based sections (local ledger / Account A / Account B / Investments).
    final cfg = ExpenseConfig.current;
    final sectionMeta = {
      'local': ['${cfg.localLabel} Monthly Expense', cfg.localCurrency],
      'account_a': [cfg.accountALabel, 'INR'],
      'account_b': [cfg.accountBLabel, 'INR'],
      'investments': ['Investment Tracker', 'INR'],
    };
    sectionMeta.forEach((key, meta) {
      final curRows = _monthRows(cur, key);
      final prevRows = prev != null ? _monthRows(prev, key) : <String, Map>{};
      final src = key == 'local'
          ? (cur['local'] is Map ? (cur['local'] as Map)['source'] : null)
          : null;
      curRows.forEach((mk, row) {
        final prevRow = prevRows[mk] ?? const {};
        for (final f in row.keys) {
          if (_calcSkip.contains(f)) continue;
          final nv = row[f];
          if (nv is! num) continue;
          final ov = prevRow[f];
          if ((ov as num?)?.toDouble() == nv.toDouble()) continue;
          String cell = '';
          int rowNum = 0;
          if (src is Map && src['columns'] is Map && src['rows'] is Map) {
            final ci = (src['columns'] as Map)[f];
            final rr = (src['rows'] as Map)[mk];
            if (ci is num && rr is Map && rr['r'] is num) {
              rowNum = (rr['r'] as num).toInt() + 1;
              cell = '${ExpenseSchema.colLetter(ci.toInt())}$rowNum';
            }
          }
          emit(
            section: key,
            sectionLabel: meta[0],
            monthKey: mk,
            column: f,
            row: rowNum,
            cell: cell,
            oldV: ov,
            newV: nv,
            currency: meta[1],
          );
        }
      });
    });

    // Stock trades (keyed by date + index).
    final curTrades = _trades(cur);
    final prevTrades = prev != null ? _trades(prev) : <Map>[];
    for (var i = 0; i < curTrades.length; i++) {
      final t = curTrades[i];
      final pt = i < prevTrades.length ? prevTrades[i] : const {};
      for (final f in ['invested', 'charges']) {
        final nv = (t[f] as num?)?.toDouble() ?? 0;
        final ov = (pt[f] as num?)?.toDouble() ?? 0;
        if (nv != ov) {
          emit(
            section: 'stocks',
            sectionLabel: 'Stock Trade Log',
            monthKey: '',
            column: f,
            row: i + 1,
            cell: '',
            oldV: ov,
            newV: nv,
            currency: 'INR',
          );
        }
      }
    }
    return changes;
  }

  Map<String, Map> _monthRows(Map<String, dynamic> d, String key) {
    final sec = d[key];
    if (sec is! Map || sec['months'] is! List) return {};
    return {
      for (final r in (sec['months'] as List).whereType<Map>())
        '${r['month']}': r,
    };
  }

  List<Map> _trades(Map<String, dynamic> d) {
    final sec = d['stocks'];
    if (sec is! Map || sec['trades'] is! List) return [];
    return (sec['trades'] as List).whereType<Map>().toList();
  }

  // ── Restore ──────────────────────────────────────────────────────

  /// Restore a locally-snapshotted version (replaces that year).
  Future<void> restoreLocalVersion(String versionId) async {
    final storage = ref.read(localStorageProvider);
    final snap = storage.getExpenseVersion(versionId);
    if (snap == null || snap['data'] is! Map) return;
    final y = (snap['year'] as num?)?.toInt();
    if (y == null) return;
    _commit(y, _clone(Map<String, dynamic>.from(snap['data'] as Map)));
    state = state.copyWith(saveSummary: 'Restored version $versionId → $y');
  }

  /// Restore a full dataset downloaded from Google Drive (all years in it).
  Future<bool> restoreDriveVersion(String name) async {
    final master = await driveSyncService.getVersion(name);
    if (master == null || master['years'] is! Map) return false;
    ExpenseConfig.current.migrateDataset(master);
    final years = master['years'] as Map;
    final next = Map<int, Map<String, dynamic>>.from(state.byYear);
    final storage = ref.read(localStorageProvider);
    years.forEach((k, v) {
      final y = int.tryParse('$k');
      if (y != null && v is Map) {
        final data = _clone(Map<String, dynamic>.from(v));
        ExpenseSchema.recompute(data);
        next[y] = data;
        storage.saveExpenseYear(y, data);
      }
    });
    // Adopting Drive content as the new local base resolves any conflict: mark
    // "last uploaded" as now so the next save uploads cleanly instead of
    // re-prompting about a master the user has just deliberately chosen from.
    final nowIso = _iso();
    await storage.setExpenseLastUploaded(nowIso);
    await storage.setExpenseSyncStatus('success');
    state = state.copyWith(
      byYear: next,
      syncStatus: 'success',
      lastUploadedIso: nowIso,
      clearDriveConflict: true,
      saveSummary: 'Restored from Drive: $name',
    );
    return true;
  }

  /// Detect a Drive-vs-local conflict: Drive master is newer than our last
  /// upload. Returns the Drive modifiedTime when a conflict exists, else null.
  Future<String?> checkDriveConflict() async {
    final storage = ref.read(localStorageProvider);
    final driveTime = await driveSyncService.masterModifiedTime();
    if (driveTime == null || driveTime.isEmpty) return null;
    final lastUp = storage.getExpenseLastUploaded();
    if (lastUp == null) return driveTime; // never uploaded but Drive has data
    final dt = DateTime.tryParse(driveTime);
    final lu = DateTime.tryParse(lastUp);
    if (dt != null && lu != null && dt.isAfter(lu.add(const Duration(seconds: 2)))) {
      return driveTime;
    }
    return null;
  }

  Future<void> deleteYear(int year) async {
    await ref.read(localStorageProvider).deleteExpenseYear(year);
    final next = Map<int, Map<String, dynamic>>.from(state.byYear)..remove(year);
    state = state.copyWith(byYear: next);
  }
}

class ExpenseState {
  final Map<int, Map<String, dynamic>> byYear;
  final bool importing;
  final bool saving;
  final String syncStatus; // success | pending | failed | disabled | conflict
  final String? lastSavedIso;
  final String? lastUploadedIso;
  final String? lastRecalcIso;
  final String saveSummary;
  final List<ValidationIssue> validation;

  /// Drive `modifiedTime` of a master that is newer than our last upload. Set
  /// when an upload is held back to avoid clobbering someone else's edits;
  /// the entry screen watches this and raises the resolve dialog. Null = clear.
  final String? driveConflictTime;

  /// Monotonic revision of the calculated dashboard state. Bumped on every
  /// recompute/commit so (a) the provider always notifies listeners and (b) the
  /// UI can show a "data version" and key its widgets off it to force a rebuild.
  final int version;

  /// True when the last save persisted the raw data but recalculation threw.
  final bool recalcFailed;

  const ExpenseState({
    this.byYear = const {},
    this.importing = false,
    this.saving = false,
    this.syncStatus = 'disabled',
    this.lastSavedIso,
    this.lastUploadedIso,
    this.lastRecalcIso,
    this.saveSummary = '',
    this.validation = const [],
    this.version = 0,
    this.recalcFailed = false,
    this.driveConflictTime,
  });

  /// Human `V<n>` tag used as the current data-version id.
  String get versionId => 'V$version';

  ExpenseState copyWith({
    Map<int, Map<String, dynamic>>? byYear,
    bool? importing,
    bool? saving,
    String? syncStatus,
    String? lastSavedIso,
    String? lastUploadedIso,
    String? lastRecalcIso,
    String? saveSummary,
    List<ValidationIssue>? validation,
    int? version,
    bool? recalcFailed,
    String? driveConflictTime,
    // copyWith's `??` cannot express "set back to null", so clearing the
    // conflict (once resolved) needs its own flag.
    bool clearDriveConflict = false,
  }) =>
      ExpenseState(
        byYear: byYear ?? this.byYear,
        importing: importing ?? this.importing,
        saving: saving ?? this.saving,
        syncStatus: syncStatus ?? this.syncStatus,
        lastSavedIso: lastSavedIso ?? this.lastSavedIso,
        lastUploadedIso: lastUploadedIso ?? this.lastUploadedIso,
        lastRecalcIso: lastRecalcIso ?? this.lastRecalcIso,
        saveSummary: saveSummary ?? this.saveSummary,
        validation: validation ?? this.validation,
        version: version ?? this.version,
        recalcFailed: recalcFailed ?? this.recalcFailed,
        driveConflictTime: clearDriveConflict
            ? null
            : (driveConflictTime ?? this.driveConflictTime),
      );
}

/// Result of a save action.
class SaveResult {
  final bool ok;
  final bool blocked; // blocked by validation errors
  final bool recalcFailed; // saved but dashboard recompute threw
  final int changeCount;
  final List<ValidationIssue> issues;
  const SaveResult({
    required this.ok,
    this.blocked = false,
    this.recalcFailed = false,
    this.changeCount = 0,
    this.issues = const [],
  });
}

final expenseStoreProvider =
    NotifierProvider<ExpenseStore, ExpenseState>(ExpenseStore.new);
