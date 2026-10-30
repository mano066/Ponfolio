/// Change-history + validation models for the Raw Dataset Entry pipeline.
///
/// [ExpenseChange] is one entry in the dashboard history log (add/edit/delete/
/// import/upload) with full provenance. [ExpenseValidation] validates a year's
/// dataset before save, splitting findings into blocking errors and warnings.
library;

import 'expense_config.dart';
import 'expense_schema.dart';
import 'expense_analytics.dart';

/// One row of the dashboard change-history log.
class ExpenseChange {
  final String changeId;
  final String timestamp; // "2026-07-04 20:30"
  final String action; // add | edit | delete | import | upload
  final String sourceSheet;
  final String sourceSection;
  final int year;
  final String month; // "Jul 2026" ('' if not month-scoped)
  final int sourceRow; // 1-based; 0 if n/a
  final String sourceColumn;
  final String sourceCellAddress;
  final Object? oldValue;
  final Object? newValue;
  final String currency;
  final String note;
  final String saveStatus; // draft | saved
  final String driveUploadStatus; // success | pending | failed | disabled

  const ExpenseChange({
    required this.changeId,
    required this.timestamp,
    required this.action,
    required this.sourceSheet,
    required this.sourceSection,
    required this.year,
    required this.month,
    required this.sourceRow,
    required this.sourceColumn,
    required this.sourceCellAddress,
    required this.oldValue,
    required this.newValue,
    required this.currency,
    required this.note,
    required this.saveStatus,
    required this.driveUploadStatus,
  });

  Map<String, dynamic> toJson() => {
        'changeId': changeId,
        'timestamp': timestamp,
        'action': action,
        'sourceSheet': sourceSheet,
        'sourceSection': sourceSection,
        'year': year,
        'month': month,
        'sourceRow': sourceRow,
        'sourceColumn': sourceColumn,
        'sourceCellAddress': sourceCellAddress,
        'oldValue': oldValue,
        'newValue': newValue,
        'currency': currency,
        'note': note,
        'saveStatus': saveStatus,
        'driveUploadStatus': driveUploadStatus,
      };

  factory ExpenseChange.fromJson(Map<String, dynamic> j) => ExpenseChange(
        changeId: '${j['changeId'] ?? ''}',
        timestamp: '${j['timestamp'] ?? ''}',
        action: '${j['action'] ?? ''}',
        sourceSheet: '${j['sourceSheet'] ?? ''}',
        sourceSection: '${j['sourceSection'] ?? ''}',
        year: (j['year'] as num?)?.toInt() ?? 0,
        month: '${j['month'] ?? ''}',
        sourceRow: (j['sourceRow'] as num?)?.toInt() ?? 0,
        sourceColumn: '${j['sourceColumn'] ?? ''}',
        sourceCellAddress: '${j['sourceCellAddress'] ?? ''}',
        oldValue: j['oldValue'],
        newValue: j['newValue'],
        currency: '${j['currency'] ?? ''}',
        note: '${j['note'] ?? ''}',
        saveStatus: '${j['saveStatus'] ?? 'saved'}',
        driveUploadStatus: '${j['driveUploadStatus'] ?? 'pending'}',
      );
}

/// A single validation finding.
class ValidationIssue {
  final String severity; // 'error' (blocks save) | 'warning' (allow save)
  final String section;
  final String message;
  const ValidationIssue(this.severity, this.section, this.message);
  bool get isError => severity == 'error';
}

/// Pure dataset validation for the Save pipeline.
class ExpenseValidation {
  ExpenseValidation._();

  static double _g(Map m, String k) => (m[k] as num?)?.toDouble() ?? 0;

  /// Validate one year's dataset [d]. Returns all findings; the caller blocks
  /// save when any [ValidationIssue.isError] is present but allows save when
  /// only warnings exist.
  static List<ValidationIssue> validate(Map<String, dynamic> d, int year) {
    final issues = <ValidationIssue>[];

    // ── Year sanity ──
    if (year < 2000 || year > 2100) {
      issues.add(ValidationIssue('error', 'Year', 'Year $year is out of range.'));
    }

    final local = d['local'];
    final months = (local is Map && local['months'] is List)
        ? (local['months'] as List).whereType<Map>().toList()
        : <Map>[];

    // ── Month validity + duplicates + required fields ──
    final seen = <String>{};
    for (final m in months) {
      final mk = '${m['month']}';
      if (mk.isEmpty || !ExpenseSchema.months.contains(mk)) {
        issues.add(ValidationIssue('error', ExpenseConfig.current.localLabel,
            'Invalid month key "${m['month']}" (${m['label'] ?? ''}).'));
        continue;
      }
      if (!seen.add(mk)) {
        issues.add(ValidationIssue('error', ExpenseConfig.current.localLabel,
            'Duplicate month entry: ${ExpenseSchema.monthTitle(mk)}.'));
      }
      // Numeric field integrity (maps should hold numbers, not junk strings).
      for (final f in ['salary', 'bonus', 'reimburse', 'interest', 'transfer']) {
        final v = m[f];
        if (v != null && v is! num) {
          issues.add(ValidationIssue('error', ExpenseConfig.current.localLabel,
              '${ExpenseSchema.monthTitle(mk)} · $f is not numeric ("$v").'));
        }
      }
    }

    // ── Per-month calc + balance checks (values already recomputed) ──
    for (final m in months) {
      final mk = '${m['month']}';
      if (!ExpenseSchema.months.contains(mk)) continue;
      final label = ExpenseSchema.monthTitle(mk);
      final income = _g(m, 'total_income');
      final actual = _g(m, 'actual_expense');
      final transfer = _g(m, 'transfer_total') != 0
          ? _g(m, 'transfer_total')
          : _g(m, 'transfer');
      final bal = _g(m, 'balance');
      final filled = income != 0 || _g(m, 'total_expense') != 0;
      if (!filled) continue;
      if (bal < 0) {
        issues.add(ValidationIssue('warning', ExpenseConfig.current.localLabel,
            '$label: negative closing balance (${bal.round()}).'));
      }
      if (income > 0 && transfer > income) {
        issues.add(ValidationIssue('warning', ExpenseConfig.current.localLabel,
            '$label: transfer (${transfer.round()}) exceeds income.'));
      }
      if (income > 0 && actual > income) {
        issues.add(ValidationIssue('warning', ExpenseConfig.current.localLabel,
            '$label: actual expense (${actual.round()}) exceeds income.'));
      }
      if (income == 0 && _g(m, 'total_expense') != 0) {
        issues.add(ValidationIssue('warning', ExpenseConfig.current.localLabel,
            '$label: spending recorded with zero income.'));
      }
    }

    // ── TOTAL row reconciliation (sheet totals vs recomputed sums) ──
    if (local is Map && local['totals'] is Map) {
      final totals = local['totals'] as Map;
      double sum(String k) => months.fold(0.0, (a, m) => a + _g(m, k));
      for (final k in ['salary', 'total_expense']) {
        final sheet = _g(totals, k);
        final calc = sum(k);
        if (sheet != 0 && (sheet - calc).abs() > 1) {
          issues.add(ValidationIssue('warning', ExpenseConfig.current.localLabel,
              'TOTAL "$k": sheet ${sheet.round()} vs calculated ${calc.round()}.'));
        }
      }
    }

    // ── Bank account balance chain sanity (Account A/B) ──
    for (final key in ['account_a', 'account_b']) {
      final sec = d[key];
      final rows = (sec is Map && sec['months'] is List)
          ? (sec['months'] as List).whereType<Map>().toList()
          : <Map>[];
      for (final m in rows) {
        final after = _g(m, 'after');
        final spend = _g(m, 'total_spend');
        final bal = _g(m, 'balance');
        if ((after - spend - bal).abs() > 1 && (after != 0 || spend != 0)) {
          issues.add(ValidationIssue('warning', ExpenseConfig.current.section(key),
              '${ExpenseSchema.monthTitle('${m['month']}')}: balance does not reconcile.'));
        }
      }
    }

    // ── Currency present on each section ──
    for (final key in ['local', 'account_a', 'account_b', 'investments']) {
      final sec = d[key];
      if (sec is Map && sec['months'] is List && (sec['months'] as List).isNotEmpty) {
        final cur = '${sec['currency'] ?? ''}';
        if (cur.isEmpty) {
          issues.add(ValidationIssue('error', ExpenseConfig.current.section(key),
              'Currency is not set for this section.'));
        }
      }
    }

    return issues;
  }

  /// Convenience: are there any blocking errors?
  static bool hasBlockingErrors(List<ValidationIssue> issues) =>
      issues.any((i) => i.isError);
}

/// Reference metadata stored alongside each saved value (spec data model).
/// Built from an [ExpenseRef] plus save timestamps + version id.
Map<String, dynamic> buildSourceReference(
  ExpenseRef ref, {
  required String createdAt,
  required String updatedAt,
  required String versionId,
}) =>
    {
      'sourceSheet': ref.sheet,
      'sourceSection': ref.section,
      'sourceRow': ref.row,
      'sourceColumn': ref.column,
      'sourceCellAddress': ref.cellAddress,
      'originalValue': ref.originalValue,
      'normalizedValue': ref.normalizedValue,
      'currency': ref.currency,
      'month': ref.month,
      'year': ref.year,
      'accountType': ref.accountType,
      'createdAt': createdAt,
      'updatedAt': updatedAt,
      'versionId': versionId,
    };
