/// Local, per-install settings for the Expense dashboard.
///
/// The dashboard tracks one salary ledger in a local currency (section
/// `local`), two home-currency bank accounts (`account_a` receives the
/// transfers out of the local ledger, `account_b` holds other income such as
/// dividends), an investment tracker and a stock trade log. Everything that
/// names a real person's banks, places, sheets or stocks lives in an optional,
/// git-ignored `assets/private/expense_config.json`; without it the generic
/// defaults below apply. Recognised keys (all optional):
///
/// * `file_prefix` — stem of the master/backup file names (`<prefix>_master.json`).
/// * `local_currency`, `local_symbol` — currency code and money prefix of the
///   local ledger.
/// * `section_labels`, `section_short_labels` — display names for `local`,
///   `account_a`, `account_b`.
/// * `field_labels` — display name per column key (e.g. `local_amount`).
/// * `header_aliases` — `{section: {field: [extra sheet headers]}}`, tried
///   after the built-in header names when importing a sheet.
/// * `scrips` — stock columns of the trade log.
/// * `seed_years` — years to seed once from bundled
///   `assets/private/expense_<year>.html` sheets.
/// * `legacy_section_keys`, `legacy_field_keys`, `legacy_type` — old stored
///   key names, migrated to the current ones whenever a dataset is loaded.
library;

import 'dart:convert';

import 'package:flutter/services.dart';

class ExpenseConfig {
  final String filePrefix;
  final String localCurrency;
  final String localSymbol;
  final Map<String, String> sectionLabels;
  final Map<String, String> sectionShortLabels;
  final Map<String, String> fieldLabels;
  final Map<String, Map<String, List<String>>> headerAliases;
  final List<String> scrips;
  final List<int> seedYears;
  final Map<String, String> legacySectionKeys;
  final Map<String, String> legacyFieldKeys;
  final String? legacyType;

  const ExpenseConfig({
    this.filePrefix = 'expense',
    this.localCurrency = 'LCY',
    this.localSymbol = '',
    this.sectionLabels = const {},
    this.sectionShortLabels = const {},
    this.fieldLabels = const {},
    this.headerAliases = const {},
    this.scrips = const [],
    this.seedYears = const [],
    this.legacySectionKeys = const {},
    this.legacyFieldKeys = const {},
    this.legacyType,
  });

  /// Where the owner's optional config is bundled from.
  static const assetPath = 'assets/private/expense_config.json';

  /// Dataset `type` written into the master file.
  static const datasetType = 'expense_dataset';

  static const _defaultSectionLabels = {
    'local': 'Local',
    'account_a': 'Account A',
    'account_b': 'Account B',
    'investments': 'Investments',
    'stocks': 'Stocks',
  };

  /// The config in force. Defaults until [load] finds a local file.
  static ExpenseConfig current = const ExpenseConfig();

  /// Reads [assetPath]; a missing or malformed file keeps the defaults.
  static Future<ExpenseConfig> load({AssetBundle? bundle}) async {
    try {
      final raw = await (bundle ?? rootBundle).loadString(assetPath);
      current = ExpenseConfig.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (_) {
      current = const ExpenseConfig();
    }
    return current;
  }

  factory ExpenseConfig.fromJson(Map<String, dynamic> j) {
    Map<String, String> strMap(Object? v) => v is Map
        ? {for (final e in v.entries) if (e.value is String) '${e.key}': e.value as String}
        : const {};
    final aliases = <String, Map<String, List<String>>>{};
    final ha = j['header_aliases'];
    if (ha is Map) {
      for (final s in ha.entries) {
        if (s.value is! Map) continue;
        aliases['${s.key}'] = {
          for (final f in (s.value as Map).entries)
            if (f.value is List) '${f.key}': [for (final a in f.value as List) '$a'],
        };
      }
    }
    String str(String k, String dflt) {
      final v = j[k];
      return v is String && v.trim().isNotEmpty ? v.trim() : dflt;
    }

    return ExpenseConfig(
      filePrefix: str('file_prefix', 'expense'),
      localCurrency: str('local_currency', 'LCY'),
      localSymbol: j['local_symbol'] is String ? j['local_symbol'] as String : '',
      sectionLabels: strMap(j['section_labels']),
      sectionShortLabels: strMap(j['section_short_labels']),
      fieldLabels: strMap(j['field_labels']),
      headerAliases: aliases,
      scrips: j['scrips'] is List ? [for (final s in j['scrips'] as List) '$s'] : const [],
      seedYears: j['seed_years'] is List
          ? [for (final y in j['seed_years'] as List) if (y is num) y.toInt()]
          : const [],
      legacySectionKeys: strMap(j['legacy_section_keys']),
      legacyFieldKeys: strMap(j['legacy_field_keys']),
      legacyType: j['legacy_type'] is String ? j['legacy_type'] as String : null,
    );
  }

  // ── Names ──

  String get masterFileName => '${filePrefix}_master.json';
  String backupFileName(DateTime d) =>
      '${filePrefix}_backup_${d.year}_${_p2(d.month)}_${_p2(d.day)}.json';
  static String _p2(int n) => n.toString().padLeft(2, '0');

  /// Display name of a section (`local`, `account_a`, `account_b`).
  String section(String key) => sectionLabels[key] ?? _defaultSectionLabels[key] ?? key;

  /// Short display name of a section, for compact KPI captions.
  String short(String key) => sectionShortLabels[key] ?? section(key);

  String get localLabel => section('local');
  String get accountALabel => section('account_a');
  String get accountBLabel => section('account_b');

  /// Display label for a column [key], falling back to [fallback].
  String field(String key, String fallback) => fieldLabels[key] ?? fallback;

  /// Extra sheet header names for [field] of [section].
  List<String> aliases(String section, String field) =>
      headerAliases[section]?[field] ?? const [];

  /// Bundled sheet asset for a seed year.
  static String seedAsset(int year) => 'assets/private/expense_$year.html';

  // ── Money ──

  /// Formats a local-currency amount, e.g. `LCY 12,345` or `$12,345`.
  String money(double v) {
    final neg = v < 0;
    final s = _grp(v.abs().round());
    final body = localSymbol.isNotEmpty ? '$localSymbol$s' : '$localCurrency $s';
    return '${neg ? '-' : ''}$body';
  }

  static String _grp(int n) {
    final str = n.toString();
    final buf = StringBuffer();
    for (var i = 0; i < str.length; i++) {
      if (i > 0 && (str.length - i) % 3 == 0) buf.write(',');
      buf.write(str[i]);
    }
    return buf.toString();
  }

  // ── Migration of older stored key names ──

  /// Renames legacy section and field keys in a year map, in place. A new key
  /// that already exists wins over its legacy twin. Safe to run repeatedly.
  void migrateYear(Map d) {
    if (legacySectionKeys.isEmpty && legacyFieldKeys.isEmpty) return;
    legacySectionKeys.forEach((old, now) {
      if (d.containsKey(old)) {
        final v = d.remove(old);
        if (!d.containsKey(now)) d[now] = v;
      }
    });
    if (legacyFieldKeys.isEmpty) return;
    for (final sec in d.values) {
      if (sec is! Map) continue;
      for (final listKey in const ['months']) {
        final rows = sec[listKey];
        if (rows is List) {
          for (final r in rows) {
            if (r is Map) _renameKeys(r);
          }
        }
      }
      if (sec['totals'] is Map) _renameKeys(sec['totals'] as Map);
      final src = sec['source'];
      if (src is Map) {
        if (src['columns'] is Map) _renameKeys(src['columns'] as Map);
        if (src['labels'] is Map) _renameKeys(src['labels'] as Map);
      }
    }
  }

  /// Migrates every year of a full dataset (`{type, years: {...}}`).
  void migrateDataset(Map master) {
    if (legacyType != null && master['type'] == legacyType) master['type'] = datasetType;
    final years = master['years'];
    if (years is Map) {
      for (final y in years.values) {
        if (y is Map) migrateYear(y);
      }
    }
  }

  void _renameKeys(Map m) {
    legacyFieldKeys.forEach((old, now) {
      if (m.containsKey(old)) {
        final v = m.remove(old);
        if (!m.containsKey(now)) m[now] = v;
      }
    });
  }
}
