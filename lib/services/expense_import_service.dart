import 'dart:io';
import 'package:csv/csv.dart';
import 'package:file_picker/file_picker.dart';
import 'package:logger/logger.dart';
import '../data/models/expense_config.dart';
import '../data/models/expense_schema.dart';

/// Parses an expense workbook — either a CSV or a Google Sheets HTML export
/// (`<table class="waffle">`). One sheet stacks up to five tables (the
/// local-currency salary ledger, Account A, Account B, investment tracker,
/// stock log); each is optional and its columns vary year to year, so sections
/// are found by header signature and columns mapped by header NAME (not
/// position). Extra header names for a particular workbook come from
/// [ExpenseConfig.headerAliases].
class ExpenseImportService {
  final _log = Logger(printer: PrettyPrinter(methodCount: 0));

  // ── Pickers ────────────────────────────────────────────────────

  /// Pick a single CSV/HTML file, parse it, return the structured map.
  Future<Map<String, dynamic>?> pickAndParse({int? fallbackYear}) async {
    try {
      final result = await FilePicker.pickFiles(
        dialogTitle: 'Import Expense Sheet (CSV or HTML)',
        type: FileType.custom,
        allowedExtensions: ['csv', 'html', 'htm'],
      );
      if (result == null || result.files.single.path == null) return null;
      final path = result.files.single.path!;
      final content = await File(path).readAsString();
      final year = _yearFrom(_baseName(path)) ?? fallbackYear;
      return parseContent(content, isHtml: _isHtml(path), fallbackYear: year);
    } catch (e, st) {
      _log.e('Expense import failed: $e\n$st');
      return null;
    }
  }

  /// Pick a folder and parse every CSV/HTML file in it, keyed by the year found
  /// in each filename (e.g. 2024.html → 2024). Returns {year: parsedMap}.
  Future<Map<int, Map<String, dynamic>>> pickFolderAndParseAll() async {
    final out = <int, Map<String, dynamic>>{};
    try {
      final dir = await FilePicker.getDirectoryPath(
          dialogTitle: 'Select the folder with your yearly expense sheets');
      if (dir == null) return out;
      final files = Directory(dir)
          .listSync()
          .whereType<File>()
          .where((f) => _isHtml(f.path) || f.path.toLowerCase().endsWith('.csv'))
          .toList();
      for (final f in files) {
        final year = _yearFrom(_baseName(f.path));
        if (year == null) continue; // only files named with a year
        try {
          final content = await f.readAsString();
          final parsed = parseContent(content,
              isHtml: _isHtml(f.path), fallbackYear: year);
          // Skip sheets with no data at all.
          if (_hasAnyData(parsed)) out[year] = parsed;
        } catch (e) {
          _log.w('Skipped ${f.path}: $e');
        }
      }
    } catch (e, st) {
      _log.e('Folder import failed: $e\n$st');
    }
    return out;
  }

  bool _isHtml(String path) {
    final p = path.toLowerCase();
    return p.endsWith('.html') || p.endsWith('.htm');
  }

  String _baseName(String path) =>
      path.replaceAll('\\', '/').split('/').last;

  // ── Content → grid → structured map ─────────────────────────────

  Map<String, dynamic> parseContent(String content,
      {required bool isHtml, int? fallbackYear}) {
    final grid = isHtml ? _htmlToGrid(content) : _csvToGrid(content);
    return parseGrid(grid, fallbackYear: fallbackYear);
  }

  /// Back-compat entry used by tests: accepts a decoded CSV grid (dynamic cells).
  Map<String, dynamic> parseRows(List<List<dynamic>> rows, {int? fallbackYear}) {
    final grid = rows
        .map((r) => r.map((c) => c?.toString() ?? '').toList())
        .toList();
    return parseGrid(grid, fallbackYear: fallbackYear);
  }

  List<List<String>> _csvToGrid(String content) {
    final rows = csv.decode(content);
    return rows.map((r) => r.map((c) => c.toString()).toList()).toList();
  }

  List<List<String>> _htmlToGrid(String html) {
    final table = RegExp(r'<table[^>]*>([\s\S]*?)</table>', caseSensitive: false)
            .firstMatch(html)
            ?.group(1) ??
        html;
    final grid = <List<String>>[];
    for (final tr in RegExp(r'<tr[^>]*>([\s\S]*?)</tr>', caseSensitive: false)
        .allMatches(table)) {
      final cells = <String>[];
      for (final td in RegExp(r'<td[^>]*>([\s\S]*?)</td>', caseSensitive: false)
          .allMatches(tr.group(1)!)) {
        var t = td.group(1)!.replaceAll(RegExp(r'<[^>]+>'), '');
        cells.add(_unescape(t).trim());
      }
      if (cells.isNotEmpty) grid.add(cells);
    }
    return grid;
  }

  String _unescape(String s) => s
      .replaceAll('&amp;', '&')
      .replaceAll('&lt;', '<')
      .replaceAll('&gt;', '>')
      .replaceAll('&quot;', '"')
      .replaceAll('&#39;', "'")
      .replaceAll('&nbsp;', ' ');

  // ── Number / text helpers ──────────────────────────────────────

  static double num_(String s) {
    var t = s.trim();
    if (t.isEmpty || t == '-') return 0;
    t = t.replaceAll(',', '').replaceAll('₹', '').replaceAll(RegExp(r'[^\d.\-]'), '');
    if (t.isEmpty || t == '-' || t == '.') return 0;
    return double.tryParse(t) ?? 0;
  }

  static String _cell(List<String> row, int i) => i >= 0 && i < row.length ? row[i] : '';

  static const _monthOrder = [
    'jan', 'feb', 'mar', 'apr', 'may', 'jun',
    'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
  ];

  static String _month(String raw) {
    final low = raw.toLowerCase().trim();
    if (low.isEmpty) return '';
    final dm = RegExp(r'^(\d{1,2})\s*/\s*\d{1,2}\s*/\s*\d{2,4}$').firstMatch(low);
    if (dm != null) {
      final m = int.tryParse(dm.group(1)!) ?? 0;
      return (m >= 1 && m <= 12) ? _monthOrder[m - 1] : '';
    }
    for (final m in _monthOrder) {
      if (low.contains(m)) return m;
    }
    return '';
  }

  static int? _yearFrom(String raw) {
    final m = RegExp(r'(20\d{2})').firstMatch(raw);
    return m == null ? null : int.tryParse(m.group(1)!);
  }

  static String _norm(String s) =>
      s.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');

  /// Build normalized-header-label → column indices (all occurrences).
  static Map<String, List<int>> _headerIndex(List<String> header) {
    final m = <String, List<int>>{};
    for (var i = 0; i < header.length; i++) {
      final k = _norm(header[i]);
      if (k.isEmpty) continue;
      (m[k] ??= []).add(i);
    }
    return m;
  }

  /// Value for the first header matching any of [labels]. [last] picks the last
  /// occurrence (used to disambiguate duplicate labels like stock "Balance").
  static double _val(List<String> row, Map<String, List<int>> hi,
      List<String> labels, {bool last = false}) {
    for (final l in labels) {
      final idxs = hi[_norm(l)];
      if (idxs != null && idxs.isNotEmpty) {
        return num_(_cell(row, last ? idxs.last : idxs.first));
      }
    }
    return 0;
  }

  /// Column index for the first header matching any of [labels], or -1.
  static int _colOf(Map<String, List<int>> hi, List<String> labels,
      {bool last = false}) {
    for (final l in labels) {
      final idxs = hi[_norm(l)];
      if (idxs != null && idxs.isNotEmpty) return last ? idxs.last : idxs.first;
    }
    return -1;
  }

  /// Local ledger: field key → the header labels it may appear under. Used
  /// both to extract values AND to record which source column each field came
  /// from (for the Monthly Overview source references). Category fields are the
  /// slice rent..health (transfer is kept separate from "actual expense").
  static const _localFields = <String, List<String>>{
    'opening': ['opening balance', 'opening'],
    'salary': ['salary'],
    'bonus': ['bonus'],
    'reimburse': ['reimburse'],
    'interest': ['interest'],
    'total_income': ['total income'],
    'total_opening': ['total opening balance', 'total opening'],
    'rent': ['rent'],
    'food': ['food'],
    'mobile': ['mobile'],
    'tour': ['tour'],
    'cc': ['cc'],
    'travel': ['travel'],
    'shopping': ['shopping'],
    'transfer': ['transfer'],
    'home': ['home'],
    'ent': ['ent'],
    'health': ['health'],
    'total_expense': ['total expense'],
    'actual_expense': [
      'actual expense( without transfer)',
      'actual expense without transfer',
      'actual expense',
    ],
    'balance': ['total balance', 'balance'],
  };

  /// Header names for [field] of [section]: the built-in [defaults] first,
  /// then any the local expense config adds for this workbook.
  static List<String> _h(String section, String field, List<String> defaults) {
    final extra = ExpenseConfig.current.aliases(section, field);
    return extra.isEmpty ? defaults : [...defaults, ...extra];
  }

  /// [_localFields] plus configured aliases.
  static Map<String, List<String>> get _localAliases => {
        for (final e in _localFields.entries) e.key: _h('local', e.key, e.value),
      };

  static bool _hasAny(List<String> header, List<String> needles) =>
      needles.any((n) => _joinHas(header, n));

  static String _str(List<String> row, Map<String, List<int>> hi, List<String> labels) {
    for (final l in labels) {
      final idxs = hi[_norm(l)];
      if (idxs != null && idxs.isNotEmpty) return _cell(row, idxs.first);
    }
    return '';
  }

  static bool _joinHas(List<String> header, String needle) =>
      header.map(_norm).join('|').contains(_norm(needle));

  static bool _rowBlank(List<String> row) => row.every((c) => c.trim().isEmpty);

  // ── Grid parser (header-name based, sections optional) ──────────

  Map<String, dynamic> parseGrid(List<List<String>> rows, {int? fallbackYear}) {
    int localHdr = -1, accountAHdr = -1, accountBHdr = -1, invHdr = -1, stockHdr = -1;
    for (var r = 0; r < rows.length; r++) {
      final row = rows[r];
      final first = _norm(_cell(row, 0));
      if (first == 'month') {
        if (_hasAny(row, _h('local', 'salary', const ['salary']))) {
          localHdr = r;
        } else if (_hasAny(row, _h('account_b', 'dividend', const ['dividend']))) {
          accountBHdr = r;
        } else {
          accountAHdr = r; // month-headed, not the salary ledger, no dividends
        }
      } else if (first == 'date') {
        final allocation = [
          ..._h('investments', 'silver', const ['silver']),
          ..._h('investments', 'para', const ['para']),
          ..._h('investments', 'nasdaq', _nasdaq),
          ..._h('investments', 'bank_balance', const ['bank balance']),
        ];
        if (_joinHas(row, 'mutual') && _hasAny(row, allocation)) {
          invHdr = r;
        } else if (_hasAny(row, _h('stocks', 'charges', _charges)) ||
            row.map(_norm).any(ExpenseSchema.scrips.map(_norm).toSet().contains)) {
          stockHdr = r;
        }
      }
    }

    int? detected;
    void noteYear(String s) => detected ??= _yearFrom(s);

    final heads = [localHdr, accountAHdr, accountBHdr, invHdr, stockHdr]
        .where((i) => i >= 0)
        .toList()
      ..sort();
    int endOf(int hdr) {
      for (final h in heads) {
        if (h > hdr) return h;
      }
      return rows.length;
    }

    final local = _parseLocal(rows, localHdr, endOf(localHdr), noteYear);
    final accountA = _parseAccountA(rows, accountAHdr, endOf(accountAHdr), noteYear);
    final accountB = _parseAccountB(rows, accountBHdr, endOf(accountBHdr), noteYear);
    final inv = _parseInvestments(rows, invHdr, endOf(invHdr));
    final stocks = _parseStocks(rows, stockHdr, endOf(stockHdr), noteYear);

    final year = detected ?? fallbackYear ?? 0;
    // Stamp the sheet name onto captured provenance now that the year is known.
    final tSource = local['source'];
    if (tSource is Map) tSource['sheet'] = '$year';

    final result = {
      'year': year,
      'local': local,
      'account_a': accountA,
      'account_b': accountB,
      'investments': inv,
      'stocks': stocks,
      'imported_at': null,
    };
    ExpenseSchema.recompute(result);
    return result;
  }

  Map<String, dynamic> _parseLocal(
      List<List<String>> rows, int hdr, int end, void Function(String) note) {
    if (hdr < 0) {
      return {
        'currency': ExpenseConfig.current.localCurrency,
        'months': [],
        'totals': {},
        'extra_categories': [],
      };
    }
    final header = rows[hdr];
    final hi = _headerIndex(header);

    // Resolve which source column each known field came from.
    final columns = <String, int>{};
    final labels = <String, String>{};
    final fields = _localAliases;
    fields.forEach((field, aliases) {
      final ci = _colOf(hi, aliases, last: field == 'balance');
      if (ci >= 0) {
        columns[field] = ci;
        labels[field] = header[ci].trim().isEmpty ? field : header[ci].trim();
      }
    });

    // Auto-detect EXTRA category columns: any non-blank header not already
    // claimed by a known field. This is what makes a future category the user
    // adds to the raw sheet flow through to totals/charts with no code change.
    final claimed = <String>{
      for (final aliases in fields.values)
        for (final l in aliases) _norm(l),
    };
    final extraDefs = <Map<String, dynamic>>[];
    for (var ci = 0; ci < header.length; ci++) {
      final raw = header[ci].trim();
      final nk = _norm(raw);
      if (nk.isEmpty || claimed.contains(nk)) continue;
      if (columns.values.contains(ci)) continue;
      final key = 'x_$nk';
      extraDefs.add({'key': key, 'label': raw});
      columns[key] = ci;
      labels[key] = raw;
      claimed.add(nk); // avoid duplicate columns with the same header
    }

    final months = <Map<String, dynamic>>[];
    final sourceRows = <String, dynamic>{};
    Map<String, dynamic> totals = {};
    for (var r = hdr + 1; r < end; r++) {
      final row = rows[r];
      final label = _cell(row, 0).trim();
      if (label.isEmpty) continue;
      note(label);
      final month = _month(label);
      final rec = <String, dynamic>{'month': month, 'label': label};
      // Known input fields (calc fields are re-derived by recompute).
      for (final f in [
        'opening', 'salary', 'bonus', 'reimburse', 'interest',
        'rent', 'food', 'mobile', 'tour', 'cc', 'travel', 'shopping',
        'transfer', 'home', 'ent', 'health',
      ]) {
        rec[f] = _val(row, hi, fields[f]!);
      }
      for (final d in extraDefs) {
        rec[d['key'] as String] = num_(_cell(row, columns[d['key']]!));
      }
      if (label.toUpperCase() == 'TOTAL') {
        totals = rec;
      } else if (month != '') {
        months.add(rec);
        sourceRows[month] = {'r': r, 'cells': List<String>.from(row)};
      }
    }
    return {
      'currency': ExpenseConfig.current.localCurrency,
      'months': months,
      'totals': totals,
      'extra_categories': extraDefs,
      'source': {
        'sheet': '', // filled in parseGrid once the year is known
        'section': '${ExpenseConfig.current.localLabel} Monthly Expense',
        'headerRow': hdr,
        'header': List<String>.from(header),
        'columns': columns,
        'labels': labels,
        'rows': sourceRows,
      },
    };
  }

  Map<String, dynamic> _parseAccountA(
      List<List<String>> rows, int hdr, int end, void Function(String) note) {
    if (hdr < 0) return {'currency': 'INR', 'months': [], 'totals': {}};
    final hi = _headerIndex(rows[hdr]);
    final months = <Map<String, dynamic>>[];
    for (var r = hdr + 1; r < end; r++) {
      final row = rows[r];
      if (_rowBlank(row)) continue;
      final label = _cell(row, 0).trim();
      note(label);
      final month = _month(label);
      if (month == '') continue; // skip totals / notes rows
      List<String> h(String field, List<String> d) => _h('account_a', field, d);
      months.add({
        'month': month,
        'label': label,
        'transfer_date': _str(row, hi, h('transfer_date', const ['transfer date'])),
        'local_amount': _val(row, hi, h('local_amount', const ['local amount'])),
        'inr_received': _val(row, hi, h('inr_received', const ['inr received'])),
        'gst': _val(row, hi, h('gst', const ['gst'])),
        'interest': _val(row, hi, h('interest', const ['interest'])),
        'opening': _val(row, hi, h('opening', const ['open balance', 'opening balance', 'opening'])),
        'bank_charges': _val(row, hi, h('bank_charges', const ['bank charges'])),
        'self_transfer': _val(row, hi, h('self_transfer', const ['self transfer'])),
        'gold': _val(row, hi, h('gold', const ['gold'])),
        'creditcard': _val(row, hi, h('creditcard', const ['creditcard', 'credit card'])),
        'food': _val(row, hi, h('food', const ['food'])),
        'transfer_b': _val(row, hi, h('transfer_b', const ['transfer to account b'])),
        'medical': _val(row, hi, h('medical', const ['medical'])),
        'family': _val(row, hi, h('family', const ['family'])),
        'mutual': _val(row, hi, h('mutual', const ['mutual', 'mutual/stock', 'stock/mutual'])),
        'loan_give': _val(row, hi, h('loan_give', const ['loan give'])),
      });
    }
    return {'currency': 'INR', 'months': months, 'totals': {}};
  }

  Map<String, dynamic> _parseAccountB(
      List<List<String>> rows, int hdr, int end, void Function(String) note) {
    if (hdr < 0) return {'currency': 'INR', 'months': [], 'totals': {}};
    final hi = _headerIndex(rows[hdr]);
    final months = <Map<String, dynamic>>[];
    for (var r = hdr + 1; r < end; r++) {
      final row = rows[r];
      if (_rowBlank(row)) continue;
      final label = _cell(row, 0).trim();
      note(label);
      final month = _month(label);
      if (month == '') continue;
      List<String> h(String field, List<String> d) => _h('account_b', field, d);
      months.add({
        'month': month,
        'label': label,
        'inr_received': _val(row, hi, h('inr_received', const ['inr received'])),
        'dividend': _val(row, hi, h('dividend', const ['dividend'])),
        'interest': _val(row, hi, h('interest', const ['interest'])),
        'opening': _val(row, hi, h('opening', const ['open balance', 'opening balance', 'opening'])),
        'bank_charges': _val(row, hi, h('bank_charges', const ['bank charges'])),
        'self_transfer': _val(row, hi, h('self_transfer', const ['self transfer'])),
        'gold': _val(row, hi, h('gold', const ['gold'])),
        'creditcard': _val(row, hi, h('creditcard', const ['creditcard', 'credit card'])),
        'food': _val(row, hi, h('food', const ['food'])),
        'transfer': _val(row, hi, h('transfer', const ['transfer'])),
        'medical': _val(row, hi, h('medical', const ['medical'])),
        'family': _val(row, hi, h('family', const ['family'])),
        'mutual': _val(row, hi, h('mutual', const ['mutual'])),
        'stock': _val(row, hi, h('stock', const ['stock'])),
        'loan_give': _val(row, hi, h('loan_give', const ['loan give'])),
      });
    }
    return {'currency': 'INR', 'months': months, 'totals': {}};
  }

  Map<String, dynamic> _parseInvestments(
      List<List<String>> rows, int hdr, int end) {
    if (hdr < 0) return {'currency': 'INR', 'months': [], 'totals': {}};
    final hi = _headerIndex(rows[hdr]);
    final months = <Map<String, dynamic>>[];
    for (var r = hdr + 1; r < end; r++) {
      final row = rows[r];
      final label = _cell(row, 0).trim();
      final month = _month(label);
      List<String> h(String field, List<String> d) => _h('investments', field, d);
      final rec = {
        'month': month,
        'label': label,
        'mutual': _val(row, hi, h('mutual', const ['mutual', 'stock/mutual', 'mutual/stock'])),
        'gold': _val(row, hi, h('gold', const ['gold'])),
        'silver': _val(row, hi, h('silver', const ['silver'])),
        'para': _val(row, hi, h('para', const ['para'])),
        'bank_balance': _val(row, hi, h('bank_balance', const ['bank balance'])),
        'nasdaq': _val(row, hi, h('nasdaq', _nasdaq)),
      };
      final sum = (rec['mutual'] as double) + (rec['gold'] as double) +
          (rec['silver'] as double) + (rec['para'] as double) +
          (rec['nasdaq'] as double);
      if (label.isEmpty) continue;
      if (month == '' && sum == 0) continue;
      months.add(rec); // includes month rows and a "2025"-style carry row
    }
    return {'currency': 'INR', 'months': months, 'totals': {}};
  }

  Map<String, dynamic> _parseStocks(
      List<List<String>> rows, int hdr, int end, void Function(String) note) {
    if (hdr < 0) {
      return {'currency': 'INR', 'trades': [], 'by_stock': {}, 'totals': {}};
    }
    final hi = _headerIndex(rows[hdr]);
    final trades = <Map<String, dynamic>>[];
    for (var r = hdr + 1; r < end; r++) {
      final row = rows[r];
      if (_rowBlank(row)) continue;
      final date = _cell(row, 0).trim();
      if (date.isEmpty) continue; // totals row
      note(date);
      final scrips = <String, dynamic>{};
      for (final s in ExpenseSchema.scrips) {
        final v = _val(row, hi, [s]);
        if (v != 0) scrips[s] = v;
      }
      trades.add({
        'date': date,
        'invested': _val(row, hi, _h('stocks', 'invested', const ['stock', 'invested'])),
        // Brokerage: the first matching charges header wins, so a sheet that
        // also carries a funding-adjustment column keeps it out of charges.
        'charges': _val(row, hi, _h('stocks', 'charges', _charges)),
        'scrips': scrips,
        'balance': _val(row, hi, _h('stocks', 'balance', const ['balance']), last: true),
      });
    }
    // Drop a trailing TOTALS row: some sheets stamp the sum row with a date, so
    // it looks like a trade. It's identifiable because its invested equals the
    // sum of every other trade AND it fills nearly every scrip column (a real
    // buy only touches a few).
    if (trades.length >= 3) {
      final last = trades.last;
      final lastInv = (last['invested'] as num?)?.toDouble() ?? 0;
      final restInv = trades
          .take(trades.length - 1)
          .fold<double>(0, (a, t) => a + ((t['invested'] as num?)?.toDouble() ?? 0));
      final scripCount = (last['scrips'] as Map).length;
      if (lastInv > 0 && (lastInv - restInv).abs() < 1 && scripCount >= 5) {
        trades.removeLast();
      }
    }
    return {'currency': 'INR', 'trades': trades, 'by_stock': {}, 'totals': {}};
  }

  static const _nasdaq = ['nasdaq', 'nasdaq-100', 'nasdaq100'];
  static const _charges = ['chargers', 'charges'];

  static bool _hasAnyData(Map<String, dynamic> d) {
    bool nonEmpty(dynamic sec, String key) =>
        sec is Map && sec[key] is List && (sec[key] as List).isNotEmpty;
    return nonEmpty(d['local'], 'months') ||
        nonEmpty(d['account_a'], 'months') ||
        nonEmpty(d['account_b'], 'months') ||
        nonEmpty(d['investments'], 'months') ||
        nonEmpty(d['stocks'], 'trades');
  }
}

final expenseImportService = ExpenseImportService();
