/// Schema + formulas for the editable Expense dashboard.
///
/// Defines every column of every section 1:1 with the source spreadsheet, which
/// cells are user inputs vs auto-computed, the blank per-year scaffold (12 month
/// rows so nothing is skipped), and the recompute pass that fills all derived
/// columns (totals, balances, month-to-month opening chains).
///
/// Sections of a year map: `local` (salary and living costs in the local
/// currency), `account_a` (home-currency account that receives transfers from
/// the local ledger), `account_b` (second home-currency account: dividends,
/// interest), `investments` and `stocks`. Display names come from
/// [ExpenseConfig].
library;

import 'expense_config.dart';

enum ECellKind { text, input, calc, opening }

class ECol {
  final String label;
  final String key;
  final double width;
  final ECellKind kind;
  const ECol(this.label, this.key, {this.width = 92, this.kind = ECellKind.input});
}

class ExpenseSchema {
  ExpenseSchema._();

  static const months = [
    'jan', 'feb', 'mar', 'apr', 'may', 'jun',
    'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
  ];

  /// Stock columns of the trade log. Empty unless the local expense config
  /// lists them (`scrips`).
  static List<String> get scrips => ExpenseConfig.current.scrips;

  static String monthTitle(String m) =>
      m.isEmpty ? '' : m[0].toUpperCase() + m.substring(1);

  /// Excel-style column letter for a 0-based column index (0→A, 26→AA).
  static String colLetter(int i) {
    var n = i + 1;
    final buf = <String>[];
    while (n > 0) {
      final r = (n - 1) % 26;
      buf.add(String.fromCharCode(65 + r));
      n = (n - 1) ~/ 26;
    }
    return buf.reversed.join();
  }

  // ── Column layouts (frozen first column handled separately by the grid) ──

  static String _f(String key, String fallback) => ExpenseConfig.current.field(key, fallback);

  static List<ECol> get local => <ECol>[
    ECol('Opening', 'opening', kind: ECellKind.opening, width: 96),
    ECol('Salary', 'salary'),
    ECol('Bonus', 'bonus'),
    ECol('Reimburse', 'reimburse'),
    ECol('Interest', 'interest'),
    ECol('Total Income', 'total_income', kind: ECellKind.calc, width: 100),
    ECol('Total Opening', 'total_opening', kind: ECellKind.calc, width: 104),
    ECol('Rent', 'rent'),
    ECol('Food', 'food'),
    ECol('Mobile', 'mobile'),
    ECol('Tour', 'tour'),
    ECol('CC', 'cc'),
    ECol('Travel', 'travel'),
    ECol('Shopping', 'shopping'),
    ECol('Transfer', 'transfer'),
    ECol('Home', 'home'),
    ECol('Ent', 'ent'),
    ECol('Health', 'health'),
    ECol('Total Expense', 'total_expense', kind: ECellKind.calc, width: 104),
    ECol('Actual Exp', 'actual_expense', kind: ECellKind.calc, width: 100),
    ECol('Balance', 'balance', kind: ECellKind.calc, width: 100),
  ];

  /// Local-ledger columns for [data], including any dynamically-added extra fields:
  /// income extras appear just before Total Income, expense/transfer extras
  /// just before Total Expense — so new categories are editable in the grid.
  static List<ECol> localCols(Map data) {
    final sec = data['local'] is Map ? data['local'] as Map : const {};
    final defs = extraDefs(sec);
    if (defs.isEmpty) return local;
    List<ECol> extrasOf(bool income) => [
          for (final d in defs)
            if ((_kind(d) == 'income') == income)
              ECol('${d['label'] ?? d['key']}', '${d['key']}', width: 96),
        ];
    final incomeExtra = extrasOf(true);
    final spendExtra = extrasOf(false);
    final out = <ECol>[];
    for (final col in local) {
      if (col.key == 'total_income') out.addAll(incomeExtra);
      if (col.key == 'total_expense') out.addAll(spendExtra);
      out.add(col);
    }
    return out;
  }

  static List<ECol> get accountA => <ECol>[
    ECol('Transfer Date', 'transfer_date', kind: ECellKind.text, width: 104),
    ECol(_f('local_amount', 'Local Amount'), 'local_amount', width: 104),
    ECol('INR Received', 'inr_received', width: 104),
    ECol('GST', 'gst'),
    ECol('Interest', 'interest'),
    ECol('Opening', 'opening', kind: ECellKind.opening, width: 100),
    ECol('After GST/Int', 'after', kind: ECellKind.calc, width: 104),
    ECol('Bank Charges', 'bank_charges', width: 104),
    ECol('Self Transfer', 'self_transfer', width: 104),
    ECol('Gold', 'gold'),
    ECol('Credit Card', 'creditcard', width: 100),
    ECol('Food', 'food'),
    ECol(_f('transfer_b', 'Transfer→${ExpenseConfig.current.short('account_b')}'), 'transfer_b', width: 108),
    ECol('Medical', 'medical'),
    ECol('Family', 'family'),
    ECol('Mutual', 'mutual'),
    ECol('Loan Give', 'loan_give'),
    ECol('Total Spend', 'total_spend', kind: ECellKind.calc, width: 100),
    ECol('Balance', 'balance', kind: ECellKind.calc, width: 100),
  ];

  static List<ECol> get accountB => <ECol>[
    ECol('INR Received', 'inr_received', width: 104),
    ECol('Dividend', 'dividend'),
    ECol('Interest', 'interest'),
    ECol('Opening', 'opening', kind: ECellKind.opening, width: 100),
    ECol('After', 'after', kind: ECellKind.calc, width: 100),
    ECol('Bank Charges', 'bank_charges', width: 104),
    ECol('Self Transfer', 'self_transfer', width: 104),
    ECol('Gold', 'gold'),
    ECol('Credit Card', 'creditcard', width: 100),
    ECol('Food', 'food'),
    ECol('Transfer', 'transfer'),
    ECol('Medical', 'medical'),
    ECol('Family', 'family'),
    ECol('Mutual', 'mutual'),
    ECol('Stock', 'stock'),
    ECol('Loan Give', 'loan_give'),
    ECol('Total Spend', 'total_spend', kind: ECellKind.calc, width: 100),
    ECol('Balance', 'balance', kind: ECellKind.calc, width: 100),
  ];

  static List<ECol> get investments => <ECol>[
    ECol('Mutual', 'mutual'),
    ECol('Gold', 'gold'),
    ECol('Silver', 'silver'),
    ECol('Para', 'para'),
    ECol(_f('bank_balance', 'Bank Balance'), 'bank_balance', width: 104),
    ECol('NASDAQ-100', 'nasdaq', width: 100),
    ECol('Total', 'total', kind: ECellKind.calc, width: 100),
  ];

  /// Investment columns for [data], including any dynamically-added funds /
  /// indices. Extra columns are inserted just before the Total column so they
  /// are editable in the grid and flow into the Total automatically.
  static List<ECol> investCols(Map data) {
    final sec = data['investments'] is Map ? data['investments'] as Map : const {};
    final defs = extraDefs(sec);
    if (defs.isEmpty) return investments;
    final extras = [
      for (final d in defs)
        ECol('${d['label'] ?? d['key']}', '${d['key']}', width: 100),
    ];
    final out = <ECol>[];
    for (final col in investments) {
      if (col.key == 'total') out.addAll(extras);
      out.add(col);
    }
    return out;
  }

  /// Stock columns (after the frozen Date column). Scrip columns are generated.
  static List<ECol> stockCols() => [
        const ECol('Invested', 'invested'),
        const ECol('Charges', 'charges'),
        for (final s in scrips) ECol(s, 'scrip:$s', width: 84),
        const ECol('Total', 'total', kind: ECellKind.calc, width: 96),
        const ECol('Balance', 'balance', width: 96),
      ];

  // ── Number helper ──
  static double g(Map m, String k) => (m[k] as num?)?.toDouble() ?? 0;

  // ── Blank scaffold ──

  static Map<String, dynamic> blankYear(int year) {
    Map<String, dynamic> monthRow(String m) => {'month': m, 'label': monthTitle(m)};
    List<Map<String, dynamic>> twelve() =>
        months.map((m) => monthRow(m)).toList();
    final d = {
      'year': year,
      'local': {
        'currency': ExpenseConfig.current.localCurrency,
        'months': twelve(),
        'totals': {},
        'extra_categories': [],
      },
      'account_a': {'currency': 'INR', 'months': twelve(), 'totals': {}},
      'account_b': {'currency': 'INR', 'months': twelve(), 'totals': {}},
      'investments': {
        'currency': 'INR',
        'months': twelve(),
        'totals': {},
        'extra_categories': [],
      },
      'stocks': {'currency': 'INR', 'trades': <Map<String, dynamic>>[], 'by_stock': {}, 'totals': {}},
      'imported_at': null,
    };
    recompute(d);
    return d;
  }

  static Map<String, dynamic> blankStockTrade() => {
        'date': '',
        'invested': 0.0,
        'charges': 0.0,
        'scrips': <String, dynamic>{},
        'total': 0.0,
        'balance': 0.0,
      };

  // ── Recompute all derived columns in place ──

  /// Recompute all derived columns in place. Operates on the real nested maps
  /// (not copies) so results persist back into [d].
  static void recompute(Map<String, dynamic> d) {
    ExpenseConfig.current.migrateYear(d);
    if (d['local'] is Map) _recomputeLocal(d['local'] as Map);
    if (d['account_a'] is Map) _recomputeAccountA(d['account_a'] as Map);
    if (d['account_b'] is Map) _recomputeAccountB(d['account_b'] as Map);
    if (d['investments'] is Map) _recomputeInvestments(d['investments'] as Map);
    if (d['stocks'] is Map) _recomputeStocks(d['stocks'] as Map);
  }

  static List<Map<String, dynamic>> _rows(dynamic v) => v is List
      ? v.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList()
      : <Map<String, dynamic>>[];

  /// Extra field definitions ({key, label, kind}) added to the raw sheet
  /// beyond the fixed columns. kind ∈ expense | income | transfer.
  static List<Map> extraDefs(Map sec) {
    final defs = sec['extra_categories'];
    if (defs is! List) return const [];
    return [for (final d in defs) if (d is Map && d['key'] is String) d];
  }

  static String _kind(Map def) =>
      (def['kind'] as String?)?.toLowerCase() ?? 'expense';

  /// Extra keys that count as spend categories (expense + transfer). These flow
  /// into Total Expense and appear in the category breakdown — so a future
  /// category the user adds shows up everywhere with no code change.
  static List<String> extraCategoryKeys(Map sec) => [
        for (final d in extraDefs(sec))
          if (_kind(d) != 'income' && _kind(d) != 'incoming_transfer') d['key'] as String,
      ];

  /// Extra keys that count as income (added to Total Income).
  static List<String> extraIncomeKeys(Map sec) => [
        for (final d in extraDefs(sec))
          if (_kind(d) == 'income') d['key'] as String,
      ];

  /// Extra keys treated as transfers (part of Total Expense but excluded from
  /// Actual Expense, exactly like the built-in Transfer column).
  static List<String> extraTransferKeys(Map sec) => [
        for (final d in extraDefs(sec))
          if (_kind(d) == 'transfer') d['key'] as String,
      ];

  static void _recomputeLocal(Map sec) {
    final ms = _sorted(_rows(sec['months']));
    final incomeKeys = extraIncomeKeys(sec);
    final expenseKeys = extraCategoryKeys(sec); // expense + transfer extras
    final transferKeys = extraTransferKeys(sec);
    final incomingKeys = extraDefs(sec).where((d) => _kind(d) == 'incoming_transfer')
        .map((d) => d['key'] as String).toSet();
    double? prev;
    var chainLive = false;
    for (var i = 0; i < ms.length; i++) {
      final m = ms[i];
      final own = g(m, 'opening');
      final opening = _chainedOpening(i, own, prev, chainLive);
      m['opening'] = opening;
      var ti = g(m, 'salary') + g(m, 'bonus') + g(m, 'reimburse') + g(m, 'interest');
      for (final k in incomeKeys) {
        ti += g(m, k);
      }
      m['total_income'] = ti;
      m['total_opening'] = opening + ti;
      var te = g(m, 'rent') + g(m, 'food') + g(m, 'mobile') + g(m, 'tour') +
          g(m, 'cc') + g(m, 'travel') + g(m, 'shopping') + g(m, 'transfer') +
          g(m, 'home') + g(m, 'ent') + g(m, 'health');
      for (final k in expenseKeys) {
        te += g(m, k);
      }
      var transferTotal = g(m, 'transfer');
      for (final k in transferKeys) {
        transferTotal += g(m, k);
      }
      m['total_expense'] = te;
      m['transfer_total'] = transferTotal;
      m['actual_expense'] = te - transferTotal;
      var incoming = g(m, 'incoming_transfer');
      for (final key in incomingKeys.where((k) => k != 'incoming_transfer')) {
        incoming += g(m, key);
      }
      m['incoming_transfer_total'] = incoming;
      final bal = opening + ti - te + incoming;
      m['balance'] = bal;
      if (own != 0 || ti != 0 || te != 0 || incoming != 0) chainLive = true;
      prev = bal;
    }
    sec['months'] = ms;
    // Keep stored sheet totals in sync with the recomputed monthly sums so the
    // "sheet vs calculated" reconciliation warning does not fire on edits.
    if (sec['totals'] is Map) {
      final totals = sec['totals'] as Map;
      for (final k in totals.keys.toList()) {
        if (totals[k] is num) {
          totals[k] = ms.fold<double>(0.0, (a, m) => a + g(m, '$k'));
        }
      }
    }
  }

  static void _recomputeAccountA(Map sec) {
    final ms = _sorted(_rows(sec['months']));
    double? prev;
    var chainLive = false;
    for (var i = 0; i < ms.length; i++) {
      final m = ms[i];
      final own = g(m, 'opening');
      final opening = _chainedOpening(i, own, prev, chainLive);
      m['opening'] = opening;
      final inflow = g(m, 'inr_received') + g(m, 'interest') + g(m, 'gst');
      final after = opening + g(m, 'inr_received') + g(m, 'interest') - g(m, 'gst');
      m['after'] = after;
      final spend = g(m, 'bank_charges') + g(m, 'self_transfer') + g(m, 'gold') +
          g(m, 'creditcard') + g(m, 'food') + g(m, 'transfer_b') +
          g(m, 'medical') + g(m, 'family') + g(m, 'mutual') + g(m, 'loan_give');
      m['total_spend'] = spend;
      final bal = after - spend;
      m['balance'] = bal;
      if (own != 0 || inflow != 0 || spend != 0) chainLive = true;
      prev = bal;
    }
    sec['months'] = ms;
  }

  static void _recomputeAccountB(Map sec) {
    final ms = _sorted(_rows(sec['months']));
    double? prev;
    var chainLive = false;
    for (var i = 0; i < ms.length; i++) {
      final m = ms[i];
      final own = g(m, 'opening');
      final opening = _chainedOpening(i, own, prev, chainLive);
      m['opening'] = opening;
      final inflow = g(m, 'inr_received') + g(m, 'dividend') + g(m, 'interest');
      final after = opening + inflow;
      m['after'] = after;
      final spend = g(m, 'bank_charges') + g(m, 'self_transfer') + g(m, 'gold') +
          g(m, 'creditcard') + g(m, 'food') + g(m, 'transfer') + g(m, 'medical') +
          g(m, 'family') + g(m, 'mutual') + g(m, 'stock') + g(m, 'loan_give');
      m['total_spend'] = spend;
      final bal = after - spend;
      m['balance'] = bal;
      if (own != 0 || inflow != 0 || spend != 0) chainLive = true;
      prev = bal;
    }
    sec['months'] = ms;
  }

  static void _recomputeInvestments(Map sec) {
    final ms = _rows(sec['months']);
    // Extra fund/index columns the user added flow into the Total.
    final extraKeys = [for (final d in extraDefs(sec)) d['key'] as String];
    for (final m in ms) {
      // "Mutual" is the hand-entered monthly total; Gold/Silver/Para/Bank/NASDAQ
      // are its allocation breakdown. Total = the allocation sum (matches the
      // source sheet's Total column) — do NOT add Mutual again (double count).
      var total = g(m, 'gold') + g(m, 'silver') + g(m, 'para') +
          g(m, 'bank_balance') + g(m, 'nasdaq');
      for (final k in extraKeys) {
        total += g(m, k);
      }
      m['total'] = total;
    }
    sec['months'] = ms;
  }

  static void _recomputeStocks(Map sec) {
    final trades = _rows(sec['trades']);
    final byStock = <String, double>{};
    for (final t in trades) {
      if (t['_deleted'] == true) {
        t['total'] = 0.0;
        continue; // soft-deleted rows kept in raw but excluded from totals
      }
      final scripsMap = t['scrips'] is Map
          ? Map<String, dynamic>.from(t['scrips'])
          : <String, dynamic>{};
      double total = 0;
      for (final s in scrips) {
        final v = (scripsMap[s] as num?)?.toDouble() ?? 0;
        total += v;
        if (v != 0) byStock[s] = (byStock[s] ?? 0) + v;
      }
      t['scrips'] = scripsMap;
      t['total'] = total;
    }
    sec['trades'] = trades;
    sec['by_stock'] = byStock;
  }

  /// Opening balance for month [i].
  ///
  /// Once the chain is "live" (a prior month had real data or an explicit
  /// opening), every later month chains from the previous month's balance —
  /// so editing an earlier month cascades all the way to the closing balance.
  /// Before the chain goes live (a leading run of empty months), an explicit
  /// own opening is preserved — this keeps imported sheets correct where the
  /// early months are blank and a mid-year opening is stated (e.g. Account B).
  static double _chainedOpening(int i, double own, double? prev, bool chainLive) {
    if (i == 0) return own;
    if (chainLive) return prev ?? 0;
    return own != 0 ? own : (prev ?? 0);
  }

  static List<Map<String, dynamic>> _sorted(List<Map<String, dynamic>> ms) {
    ms.sort((a, b) => months
        .indexOf((a['month'] ?? '').toString())
        .compareTo(months.indexOf((b['month'] ?? '').toString())));
    return ms;
  }
}
