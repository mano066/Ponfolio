/// Analytics layer for the Expense dashboard.
///
/// Pure functions that derive every KPI, monthly series, category breakdown,
/// account flow and data-quality signal from the stored expense data maps
/// (the same nested shape produced by [ExpenseSchema]/[ExpenseImportService]).
/// Nothing here mutates state — the UI reads these structures to render KPI
/// cards, charts, tables and the audit page without losing a single value.
library;

import 'expense_config.dart';
import 'expense_schema.dart';

double _g(Map m, String k) => (m[k] as num?)?.toDouble() ?? 0;

/// One month of the local salary ledger, already recomputed, plus a "filled" flag
/// so future/blank months still appear but can be styled/labelled distinctly.
class MonthPoint {
  final String month; // jan..dec
  final String label; // e.g. "Jan 2026"
  final Map<String, dynamic> row;
  final bool filled;
  const MonthPoint(this.month, this.label, this.row, this.filled);

  double get income => _g(row, 'total_income');
  double get expense => _g(row, 'total_expense');
  double get actual => _g(row, 'actual_expense');
  double get transfer => _g(row, 'transfer');
  double get balance => _g(row, 'balance');
  double get opening => _g(row, 'opening');
  double get savingsRate => income > 0 ? (income - actual) / income * 100 : 0;
}

/// KPI roll-up for one section/year.
class LocalKpis {
  final double opening, salary, bonus, reimburse, interest;
  final double income, totalExpense, actualExpense, transfer, closing;
  const LocalKpis({
    required this.opening,
    required this.salary,
    required this.bonus,
    required this.reimburse,
    required this.interest,
    required this.income,
    required this.totalExpense,
    required this.actualExpense,
    required this.transfer,
    required this.closing,
  });

  double get netSavings => income - actualExpense; // excludes transfer
  double get finalSavings => income - totalExpense; // includes transfer
  double get savingsRate => income > 0 ? netSavings / income * 100 : 0;
  double get expenseRatio => income > 0 ? actualExpense / income * 100 : 0;
  double get transferRatio => income > 0 ? transfer / income * 100 : 0;
}

/// Source reference for one imported value — links a dashboard number back to
/// the exact raw cell it came from (spec: sheet / section / row / column /
/// cell address / original value). Built from the provenance the parser
/// captures; degrades to a "computed"/"manual" note when no raw cell exists.
class ExpenseRef {
  final String sheet; // e.g. "2026"
  final String section; // e.g. "Local Monthly Expense"
  final int row; // 1-based sheet row (0 = derived, no single row)
  final String column; // source column name
  final String cellAddress; // e.g. "C4"
  final String originalValue; // raw cell text
  final double normalizedValue;
  final String currency;
  final String month; // "Jan 2026"
  final int year;
  final String accountType;
  final String note; // populated for derived/computed values
  const ExpenseRef({
    required this.sheet,
    required this.section,
    required this.row,
    required this.column,
    required this.cellAddress,
    required this.originalValue,
    required this.normalizedValue,
    required this.currency,
    required this.month,
    required this.year,
    required this.accountType,
    this.note = '',
  });

  bool get isDerived => row <= 0;

  /// Human-readable one-liner, e.g.
  /// "Sheet 2026, Local Monthly Expense, Row 4, Column Salary".
  String get label => isDerived
      ? (note.isNotEmpty ? note : 'Derived value (no single source cell)')
      : 'Sheet $sheet, $section, Row $row, Column $column';
}

/// One category row in the monthly breakdown, with every metric the spec asks
/// for: amount, share of total & actual expense, deltas vs previous month and
/// vs the category's monthly average, and a Normal/High/Low/N-A status.
class CategoryLine {
  final String key;
  final String label;
  final double amount;
  final double pctOfTotal; // of total expense (incl. transfer)
  final double pctOfActual; // of actual expense (ex. transfer)
  final double diffPrev; // this month − previous month
  final double diffAvg; // this month − average monthly for this category
  final String status; // Normal | High | Low | Not Available
  final ExpenseRef? ref;
  const CategoryLine({
    required this.key,
    required this.label,
    required this.amount,
    required this.pctOfTotal,
    required this.pctOfActual,
    required this.diffPrev,
    required this.diffAvg,
    required this.status,
    required this.ref,
  });
}

/// Everything the Monthly Expense Overview renders for one selected month.
class MonthlyReport {
  final int year;
  final String monthKey; // "jan"
  final String monthLabel; // "Jan 2026"
  final bool filled; // has any income/expense data
  final bool future; // no data at all (future / not filled)

  // 15 KPI values (spec order).
  final double openingBalance;
  final double salary;
  final double bonus;
  final double reimburse;
  final double interest;
  final double totalIncome;
  final double totalOpening; // opening + income
  final double totalExpense; // incl. transfer
  final double actualExpense; // ex. transfer
  final double transfer;
  final double closingBalance;
  final double netSavings; // income − actual
  final double savingsRate; // %
  final double expenseRatio; // %
  final double transferRatio; // %

  final List<CategoryLine> categories;
  final List<String> insights;
  final Map<String, dynamic> row; // the normalized month row
  const MonthlyReport({
    required this.year,
    required this.monthKey,
    required this.monthLabel,
    required this.filled,
    required this.future,
    required this.openingBalance,
    required this.salary,
    required this.bonus,
    required this.reimburse,
    required this.interest,
    required this.totalIncome,
    required this.totalOpening,
    required this.totalExpense,
    required this.actualExpense,
    required this.transfer,
    required this.closingBalance,
    required this.netSavings,
    required this.savingsRate,
    required this.expenseRatio,
    required this.transferRatio,
    required this.categories,
    required this.insights,
    required this.row,
  });

  bool get hasInterest => interest != 0;
}

/// A single data-quality finding surfaced on the audit page.
class AuditIssue {
  final String severity; // 'error' | 'warn' | 'info'
  final String section;
  final String message;
  const AuditIssue(this.severity, this.section, this.message);
}

class ExpenseAnalytics {
  ExpenseAnalytics._();

  /// The fixed local-ledger spend categories. Transfer is intentionally NOT here —
  /// it's tracked separately so "actual expense" can exclude it — but the
  /// Monthly Overview lists it as its own category line via [categoriesFor].
  static const localCategories = <String, String>{
    'rent': 'Rent',
    'food': 'Food',
    'mobile': 'Mobile',
    'tour': 'Tour',
    'cc': 'Credit Card',
    'travel': 'Travel',
    'shopping': 'Shopping',
    'home': 'Home',
    'ent': 'Entertainment',
    'health': 'Health',
  };

  /// Category field → label for [d], including any EXTRA categories detected in
  /// the raw sheet, so future categories appear with no code change. Ordering:
  /// fixed categories, then Transfer, then extras (spec lists Transfer inline).
  static Map<String, String> categoriesFor(Map<String, dynamic> d,
      {bool includeTransfer = true}) {
    final out = <String, String>{...localCategories};
    if (includeTransfer) out['transfer'] = 'Transfer';
    for (final k in ExpenseSchema.extraCategoryKeys(section(d, 'local'))) {
      final label = _extraLabel(d, k);
      out[k] = label;
    }
    return out;
  }

  static String _extraLabel(Map<String, dynamic> d, String key) {
    final defs = section(d, 'local')['extra_categories'];
    if (defs is List) {
      for (final e in defs) {
        if (e is Map && e['key'] == key && e['label'] is String) {
          return e['label'] as String;
        }
      }
    }
    return key.startsWith('x_') ? key.substring(2) : key;
  }

  static String monthLabel(String monthKey, int year, {bool short = false}) {
    final t = ExpenseSchema.monthTitle(monthKey);
    if (t.isEmpty) return '';
    return short ? '${t.substring(0, t.length.clamp(0, 3))} ${year % 100}'
                 : '$t $year';
  }

  // ── Section row extraction ──────────────────────────────────────

  static List<Map<String, dynamic>> _rows(Map<String, dynamic> d, String key) {
    final sec = key == 'invest' ? d['investments'] : d[key];
    if (sec is! Map) return [];
    final ms = sec['months'];
    return ms is List
        ? ms.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList()
        : [];
  }

  static List<Map<String, dynamic>> trades(Map<String, dynamic> d) {
    final sec = d['stocks'];
    if (sec is! Map) return [];
    final ts = sec['trades'];
    return ts is List
        ? ts.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList()
        : [];
  }

  static Map<String, dynamic> section(Map<String, dynamic> d, String key) {
    final sec = key == 'invest' ? d['investments'] : d[key];
    return sec is Map ? Map<String, dynamic>.from(sec) : {};
  }

  /// Local-ledger months aligned to Jan..Dec, marking any absent/blank month as
  /// unfilled so nothing is dropped and future months still render.
  static List<MonthPoint> localPoints(Map<String, dynamic> d, int year) {
    final byKey = {for (final r in _rows(d, 'local')) '${r['month']}': r};
    return [
      for (final m in ExpenseSchema.months)
        MonthPoint(
          m,
          monthLabel(m, year),
          byKey[m] ?? {'month': m},
          byKey.containsKey(m) && _g(byKey[m]!, 'total_income') +
                  _g(byKey[m]!, 'total_expense') !=
              0,
        ),
    ];
  }

  static List<Map<String, dynamic>> localRows(Map<String, dynamic> d) =>
      _rows(d, 'local');
  static List<Map<String, dynamic>> accountARows(Map<String, dynamic> d) =>
      _rows(d, 'account_a');
  static List<Map<String, dynamic>> accountBRows(Map<String, dynamic> d) =>
      _rows(d, 'account_b');
  static List<Map<String, dynamic>> investRows(Map<String, dynamic> d) =>
      _rows(d, 'invest');

  static double _sum(List<Map<String, dynamic>> rows, String key) =>
      rows.fold(0.0, (a, r) => a + _g(r, key));

  static double lastNonZero(List<Map<String, dynamic>> rows, String key) {
    for (var i = rows.length - 1; i >= 0; i--) {
      final v = _g(rows[i], key);
      if (v != 0) return v;
    }
    return 0;
  }

  static double firstOpening(List<Map<String, dynamic>> rows) =>
      rows.isEmpty ? 0 : _g(rows.first, 'opening');

  // ── KPI roll-ups ────────────────────────────────────────────────

  static LocalKpis localKpis(Map<String, dynamic> d) {
    final r = _rows(d, 'local');
    return LocalKpis(
      opening: firstOpening(r),
      salary: _sum(r, 'salary'),
      bonus: _sum(r, 'bonus'),
      reimburse: _sum(r, 'reimburse'),
      interest: _sum(r, 'interest'),
      income: _sum(r, 'total_income'),
      totalExpense: _sum(r, 'total_expense'),
      actualExpense: _sum(r, 'actual_expense'),
      transfer: _sum(r, 'transfer'),
      closing: lastNonZero(r, 'balance'),
    );
  }

  /// Category totals for the year (descending), excluding transfer. Includes
  /// any extra categories detected in the raw sheet.
  static List<MapEntry<String, double>> categoryTotals(Map<String, dynamic> d) {
    final r = _rows(d, 'local');
    final out = <String, double>{};
    categoriesFor(d, includeTransfer: false).forEach((k, label) {
      final v = _sum(r, k);
      if (v != 0) out[label] = v;
    });
    final list = out.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    return list;
  }

  // ── Period / filled-month info (future-month aware) ─────────────

  /// Month keys that have real activity (non-zero income or expense).
  static List<String> filledMonthKeys(Map<String, dynamic> d) {
    final byKey = {for (final r in localRows(d)) '${r['month']}': r};
    return [
      for (final m in ExpenseSchema.months)
        if (byKey[m] != null &&
            (_g(byKey[m]!, 'total_income') != 0 ||
                _g(byKey[m]!, 'total_expense') != 0))
          m,
    ];
  }

  /// Selected-period summary: filled/future counts, first/last filled month and
  /// a human period label ("Jan 2025 to Jul 2025").
  static Map<String, dynamic> periodInfo(Map<String, dynamic> d, int year) {
    final filled = filledMonthKeys(d);
    final first = filled.isNotEmpty ? filled.first : null;
    final last = filled.isNotEmpty ? filled.last : null;
    return {
      'filledCount': filled.length,
      'futureCount': ExpenseSchema.months.length - filled.length,
      'first': first,
      'last': last,
      'periodLabel': (first != null && last != null)
          ? '${monthLabel(first, year, short: true)} to ${monthLabel(last, year, short: true)}'
          : 'No filled months yet',
      'lastFilled': last != null ? monthLabel(last, year) : '—',
    };
  }

  /// Per-month source cells that feed an aggregate local-ledger [field] — powering the
  /// "View Source" trace on each Overview card. Only months present in the raw
  /// sheet are returned; empty when the year was hand-entered (no provenance).
  static List<Map<String, dynamic>> fieldSources(
      Map<String, dynamic> d, int year, String field) {
    final src = localSource(d);
    final cols = src['columns'];
    final rows = src['rows'];
    final labels = src['labels'];
    final out = <Map<String, dynamic>>[];
    if (cols is! Map || rows is! Map || cols[field] is! num) return out;
    final ci = (cols[field] as num).toInt();
    final colName =
        (labels is Map && labels[field] is String) ? labels[field] as String : field;
    for (final mk in ExpenseSchema.months) {
      final rr = rows[mk];
      if (rr is! Map || rr['cells'] is! List) continue;
      final cells = rr['cells'] as List;
      final rowNum = (rr['r'] as num? ?? -1).toInt() + 1;
      final orig = ci >= 0 && ci < cells.length ? '${cells[ci]}' : '';
      out.add({
        'month': monthLabel(mk, year),
        'column': colName,
        'cell': '${ExpenseSchema.colLetter(ci)}$rowNum',
        'original': orig,
      });
    }
    return out;
  }

  // ── Monthly overview: rows, references, report ──────────────────

  /// The local-ledger month record for [monthKey], or null if absent.
  static Map<String, dynamic>? localRow(Map<String, dynamic> d, String monthKey) {
    for (final r in _rows(d, 'local')) {
      if ('${r['month']}' == monthKey) return r;
    }
    return null;
  }

  /// The raw local-ledger source (provenance) map captured at import, or {}.
  static Map<String, dynamic> localSource(Map<String, dynamic> d) {
    final s = section(d, 'local')['source'];
    return s is Map ? Map<String, dynamic>.from(s) : {};
  }

  /// The exact raw sheet row for [monthKey] as {header:[...], cells:[...],
  /// row:<1-based>}, or null when there is no captured source (e.g. a
  /// hand-entered future year).
  static Map<String, dynamic>? rawLocalRow(
      Map<String, dynamic> d, String monthKey) {
    final src = localSource(d);
    final rows = src['rows'];
    final header = src['header'];
    if (rows is! Map || rows[monthKey] is! Map || header is! List) return null;
    final entry = Map<String, dynamic>.from(rows[monthKey] as Map);
    final cells = entry['cells'];
    return {
      'header': header.map((e) => '$e').toList(),
      'cells': cells is List ? cells.map((e) => '$e').toList() : <String>[],
      'row': (entry['r'] as num? ?? -1).toInt() + 1,
    };
  }

  /// Build a source reference for local-ledger [field] in [monthKey]. Uses captured
  /// provenance when available; otherwise returns a "derived"/"manual" ref so
  /// every value still carries a traceable note.
  static ExpenseRef localRef(
      Map<String, dynamic> d, int year, String monthKey, String field,
      {double normalized = 0, String derivedNote = ''}) {
    final label = monthLabel(monthKey, year);
    final src = localSource(d);
    final columns = src['columns'];
    final labels = src['labels'];
    final rows = src['rows'];
    final sheet = '${src['sheet'] ?? year}';
    final sectionName = '${ExpenseConfig.current.localLabel} Monthly Expense';

    if (derivedNote.isEmpty &&
        columns is Map &&
        columns[field] is num &&
        rows is Map &&
        rows[monthKey] is Map) {
      final ci = (columns[field] as num).toInt();
      final entry = Map<String, dynamic>.from(rows[monthKey] as Map);
      final rowNum = (entry['r'] as num? ?? -1).toInt() + 1;
      final cells = entry['cells'];
      final original = (cells is List && ci >= 0 && ci < cells.length)
          ? '${cells[ci]}'
          : '';
      final colName = (labels is Map && labels[field] is String)
          ? labels[field] as String
          : field;
      return ExpenseRef(
        sheet: sheet,
        section: sectionName,
        row: rowNum,
        column: colName,
        cellAddress: '${ExpenseSchema.colLetter(ci)}$rowNum',
        originalValue: original,
        normalizedValue: normalized,
        currency: ExpenseConfig.current.localCurrency,
        month: label,
        year: year,
        accountType: '${ExpenseConfig.current.localLabel} Expense',
      );
    }

    return ExpenseRef(
      sheet: sheet,
      section: sectionName,
      row: 0,
      column: field,
      cellAddress: '',
      originalValue: '',
      normalizedValue: normalized,
      currency: ExpenseConfig.current.localCurrency,
      month: label,
      year: year,
      accountType: '${ExpenseConfig.current.localLabel} Expense',
      note: derivedNote.isNotEmpty
          ? derivedNote
          : 'Value entered manually (no imported source cell)',
    );
  }

  /// Full Monthly Expense Overview report for one month.
  static MonthlyReport monthlyReport(
      Map<String, dynamic> d, int year, String monthKey) {
    final rows = _rows(d, 'local');
    final byKey = {for (final r in rows) '${r['month']}': r};
    final row = byKey[monthKey] ?? <String, dynamic>{'month': monthKey};
    final label = monthLabel(monthKey, year);

    double gv(String k) => _g(row, k);
    final income = gv('total_income');
    final totalExp = gv('total_expense');
    final actual = gv('actual_expense');
    // transfer_total includes any extra transfer fields; falls back to the base
    // Transfer column for data recomputed before that field existed.
    final transfer = gv('transfer_total') != 0 ? gv('transfer_total') : gv('transfer');
    final opening = gv('opening');
    final closing = gv('balance');
    final filled = income != 0 || totalExp != 0;
    final future = !filled && gv('salary') == 0 && gv('opening') == 0;

    // Averages across months that actually have data (for deltas & status).
    final filledRows = rows
        .where((r) =>
            _g(r, 'total_income') != 0 || _g(r, 'total_expense') != 0)
        .toList();
    double avgOf(String k) => filledRows.isEmpty
        ? 0
        : filledRows.fold<double>(0, (a, r) => a + _g(r, k)) / filledRows.length;

    // Previous month (Jan..Dec order) for month-over-month deltas.
    final mi = ExpenseSchema.months.indexOf(monthKey);
    final prevRow = mi > 0 ? byKey[ExpenseSchema.months[mi - 1]] : null;

    final cats = <CategoryLine>[];
    categoriesFor(d).forEach((k, catLabel) {
      final amt = gv(k);
      final prev = prevRow != null ? _g(prevRow, k) : 0.0;
      final avg = avgOf(k);
      String status;
      if (!filled || amt == 0) {
        status = amt == 0 && filled ? 'Normal' : 'Not Available';
      } else if (avg <= 0) {
        status = 'Normal';
      } else if (amt >= avg * 1.25) {
        status = 'High';
      } else if (amt <= avg * 0.75) {
        status = 'Low';
      } else {
        status = 'Normal';
      }
      cats.add(CategoryLine(
        key: k,
        label: catLabel,
        amount: amt,
        pctOfTotal: totalExp > 0 ? amt / totalExp * 100 : 0,
        pctOfActual: actual > 0 ? amt / actual * 100 : 0,
        diffPrev: amt - prev,
        diffAvg: amt - avg,
        status: status,
        ref: localRef(d, year, monthKey, k, normalized: amt),
      ));
    });
    cats.sort((a, b) => b.amount.compareTo(a.amount));

    final netSavings = income - actual;
    final insights = _monthlyInsights(
      label: label,
      filled: filled,
      future: future,
      income: income,
      actual: actual,
      transfer: transfer,
      closing: closing,
      cats: cats,
      avgActual: avgOf('actual_expense'),
      prevActual: prevRow != null ? _g(prevRow, 'actual_expense') : null,
    );

    return MonthlyReport(
      year: year,
      monthKey: monthKey,
      monthLabel: label,
      filled: filled,
      future: future,
      openingBalance: opening,
      salary: gv('salary'),
      bonus: gv('bonus'),
      reimburse: gv('reimburse'),
      interest: gv('interest'),
      totalIncome: income,
      totalOpening: gv('total_opening'),
      totalExpense: totalExp,
      actualExpense: actual,
      transfer: transfer,
      closingBalance: closing,
      netSavings: netSavings,
      savingsRate: income > 0 ? netSavings / income * 100 : 0,
      expenseRatio: income > 0 ? actual / income * 100 : 0,
      transferRatio: income > 0 ? transfer / income * 100 : 0,
      categories: cats,
      insights: insights,
      row: row,
    );
  }

  static List<String> _monthlyInsights({
    required String label,
    required bool filled,
    required bool future,
    required double income,
    required double actual,
    required double transfer,
    required double closing,
    required List<CategoryLine> cats,
    required double avgActual,
    required double? prevActual,
  }) {
    final out = <String>[];
    if (future) {
      out.add('$label has no data yet — future or not-yet-filled month.');
      return out;
    }
    if (!filled) {
      out.add('$label is blank — no income or expense recorded.');
    }
    final spent = cats.where((c) => c.amount > 0).toList();
    if (spent.isNotEmpty) {
      out.add('Highest spending category: ${spent.first.label} '
          '(${spent.first.amount.round()} ${ExpenseConfig.current.localCurrency}).');
      out.add('Lowest spending category: ${spent.last.label} '
          '(${spent.last.amount.round()} ${ExpenseConfig.current.localCurrency}).');
    } else {
      out.add('No category spending recorded this month.');
    }
    if (prevActual != null) {
      if (actual > prevActual) {
        out.add('Actual expense rose vs previous month '
            '(+${(actual - prevActual).round()} ${ExpenseConfig.current.localCurrency}).');
      } else if (actual < prevActual) {
        out.add('Actual expense fell vs previous month '
            '(${(actual - prevActual).round()} ${ExpenseConfig.current.localCurrency}).');
      } else {
        out.add('Actual expense unchanged vs previous month.');
      }
    }
    if (income > 0 && actual > income) {
      out.add('⚠ Actual expense exceeds income by '
          '${(actual - income).round()} ${ExpenseConfig.current.localCurrency} this month.');
    }
    if (income > 0 && transfer > income * 0.5) {
      out.add('⚠ Transfer is high — '
          '${(transfer / income * 100).round()}% of income.');
    }
    out.add(closing >= 0
        ? 'Closing balance is positive (${closing.round()} ${ExpenseConfig.current.localCurrency}).'
        : '⚠ Closing balance is negative (${closing.round()} ${ExpenseConfig.current.localCurrency}).');
    if (avgActual > 0 && actual > avgActual * 1.5) {
      out.add('⚠ Unusually high spending — '
          '${(actual / avgActual * 100).round()}% of the monthly average.');
    } else if (avgActual > 0 && actual > 0 && actual < avgActual * 0.5) {
      out.add('Spending is well below the monthly average.');
    }
    return out;
  }

  // ── Account A / B flows ────────────────────────────────────────

  static double accountAClosing(Map<String, dynamic> d) =>
      lastNonZero(_rows(d, 'account_a'), 'balance');
  static double accountBClosing(Map<String, dynamic> d) =>
      lastNonZero(_rows(d, 'account_b'), 'balance');

  static double investedTotal(Map<String, dynamic> d) =>
      _sum(_rows(d, 'invest'), 'total');
  static double stockDeployed(Map<String, dynamic> d) => trades(d)
      .where((t) => t['_deleted'] != true)
      .fold(0.0, (a, t) => a + _g(t, 'invested'));

  /// Deployed amount per scrip across all trades (already recomputed).
  static Map<String, double> byScrip(Map<String, dynamic> d) {
    final sec = d['stocks'];
    final bs = sec is Map ? sec['by_stock'] : null;
    if (bs is! Map) return {};
    return {
      for (final e in bs.entries)
        '${e.key}': (e.value as num?)?.toDouble() ?? 0,
    };
  }

  /// Investment split by allocation (Gold/Silver/Para/Bank/NASDAQ). "Mutual" is
  /// the monthly total, so it's excluded here to avoid double-counting.
  static Map<String, double> investmentSplit(Map<String, dynamic> d) {
    final r = _rows(d, 'invest');
    final out = <String, double>{
      'Gold': _sum(r, 'gold'),
      'Silver': _sum(r, 'silver'),
      'Para': _sum(r, 'para'),
      ExpenseConfig.current.field('bank_balance', 'Bank Balance'): _sum(r, 'bank_balance'),
      'NASDAQ-100': _sum(r, 'nasdaq'),
    };
    // Dynamically-added funds / indices.
    final sec = d['investments'];
    if (sec is Map) {
      for (final def in ExpenseSchema.extraDefs(sec)) {
        final key = def['key'] as String;
        out['${def['label'] ?? key}'] = _sum(r, key);
      }
    }
    out.removeWhere((_, v) => v == 0);
    return out;
  }

  // ── Data-quality audit ──────────────────────────────────────────

  static List<AuditIssue> audit(Map<String, dynamic> d, int year) {
    final issues = <AuditIssue>[];
    final t = _rows(d, 'local');

    // Missing months (ledger present but not all 12).
    if (t.isNotEmpty) {
      final present = t.map((r) => '${r['month']}').toSet();
      final missing = ExpenseSchema.months
          .where((m) => !present.contains(m))
          .map(ExpenseSchema.monthTitle)
          .toList();
      if (missing.isNotEmpty) {
        issues.add(AuditIssue('info', ExpenseConfig.current.localLabel,
            'Months absent from sheet: ${missing.join(', ')}'));
      }
    }

    for (final r in t) {
      final label = ExpenseSchema.monthTitle('${r['month']}');
      final income = _g(r, 'total_income');
      final bal = _g(r, 'balance');
      final transfer = _g(r, 'transfer');
      final actual = _g(r, 'actual_expense');
      if (bal < 0) {
        issues.add(AuditIssue('warn', ExpenseConfig.current.localLabel, '$label: negative balance ${bal.round()}'));
      }
      if (income == 0 && _g(r, 'total_expense') != 0) {
        issues.add(AuditIssue('warn', ExpenseConfig.current.localLabel, '$label: zero income with spend'));
      }
      if (_g(r, 'salary') == 0 && income == 0 && _g(r, 'total_expense') == 0) {
        issues.add(AuditIssue('info', ExpenseConfig.current.localLabel, '$label: future / not filled'));
      }
      if (transfer > income && income > 0) {
        issues.add(AuditIssue('warn', ExpenseConfig.current.localLabel, '$label: transfer exceeds income'));
      }
      if (actual > income && income > 0) {
        issues.add(AuditIssue('warn', ExpenseConfig.current.localLabel, '$label: actual expense exceeds income'));
      }
    }

    // TOTAL row reconciliation against the recomputed monthly sums.
    final totals = section(d, 'local')['totals'];
    if (totals is Map && totals.isNotEmpty) {
      for (final k in ['salary', 'total_expense']) {
        final sheet = _g(totals, k);
        final calc = _sum(t, k);
        if (sheet != 0 && (sheet - calc).abs() > 1) {
          issues.add(AuditIssue('error', ExpenseConfig.current.localLabel,
              'TOTAL "$k" sheet=${sheet.round()} vs calc=${calc.round()}'));
        }
      }
    }

    // Currency mixing reminder (local currency vs INR accounts).
    if (t.isNotEmpty && (accountARows(d).isNotEmpty || accountBRows(d).isNotEmpty)) {
      issues.add(AuditIssue('info', 'Currency',
          '${ExpenseConfig.current.localLabel} is ${ExpenseConfig.current.localCurrency} and the bank accounts are INR — KPIs are kept per-currency, not summed.'));
    }

    if (issues.isEmpty) {
      issues.add(const AuditIssue('info', 'All', 'No data-quality issues detected.'));
    }
    return issues;
  }

  /// Expanded audit metrics for the Data Audit page (spec: sheets/sections/
  /// rows/columns/blanks/zeros/future/new-categories/mismatches/duplicates/
  /// negative balances). Derived live from the latest data.
  static Map<String, int> auditMetrics(Map<String, dynamic> d) {
    final t = localRows(d);
    final filled = t
        .where((r) => _g(r, 'total_income') != 0 || _g(r, 'total_expense') != 0)
        .length;
    final extras = ExpenseSchema.extraDefs(section(d, 'local')).length;

    final seen = <String>{};
    var dup = 0;
    for (final r in t) {
      if (!seen.add('${r['month']}')) dup++;
    }
    var neg = 0;
    for (final r in t) {
      if (_g(r, 'balance') < 0) neg++;
    }
    var mismatch = 0;
    final totals = section(d, 'local')['totals'];
    if (totals is Map) {
      for (final k in ['salary', 'total_expense']) {
        final s = _g(totals, k);
        if (s != 0 && (s - _sum(t, k)).abs() > 1) mismatch++;
      }
    }
    var zero = 0, blank = 0;
    final inputKeys = <String>[
      ...categoriesFor(d).keys,
      'salary', 'bonus', 'reimburse', 'interest',
    ];
    for (final r in t) {
      final isFilled = _g(r, 'total_income') != 0 || _g(r, 'total_expense') != 0;
      for (final k in inputKeys) {
        if (_g(r, k) == 0) {
          if (isFilled) {
            zero++;
          } else {
            blank++;
          }
        }
      }
    }
    final cov = coverage(d);
    return {
      'sections': cov.values.where((v) => v > 0).length,
      'rows': cov.values.fold(0, (a, b) => a + b),
      'columns': ExpenseSchema.localCols(d).length,
      'blank': blank,
      'zero': zero,
      'future_months': ExpenseSchema.months.length - filled,
      'new_categories': extras,
      'mismatches': mismatch,
      'duplicate_months': dup,
      'negative_balances': neg,
    };
  }

  /// Row counts imported per section — feeds the audit "coverage" table.
  static Map<String, int> coverage(Map<String, dynamic> d) => {
        '${ExpenseConfig.current.localLabel} months': _rows(d, 'local').length,
        '${ExpenseConfig.current.accountALabel} months': _rows(d, 'account_a').length,
        '${ExpenseConfig.current.accountBLabel} months': _rows(d, 'account_b').length,
        'Investment rows': _rows(d, 'invest').length,
        'Stock trades': trades(d).length,
      };
}
