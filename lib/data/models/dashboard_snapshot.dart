import 'dart:convert';
import 'expense_config.dart';
import 'expense_schema.dart';
import 'expense_analytics.dart';

/// Read-only dashboard calculations. Unknown inputs stay unknown.
double? dashboardNumber(dynamic value) {
  final n = value is num ? value.toDouble() : double.tryParse('$value');
  return n != null && n.isFinite ? n : null;
}

List<Map<String, dynamic>> dashboardRows(dynamic value) => value is List
    ? value.whereType<Map>().map((v) => Map<String, dynamic>.from(v)).toList()
    : [];

bool dashboardFresh(Map<String, dynamic>? data, DateTime now) {
  if (data == null || data['offline'] == true || data['stale'] == true) {
    return false;
  }
  final stamp = DateTime.tryParse('${data['last_updated'] ?? ''}');
  if (stamp == null) return false;
  final age = now.toUtc().difference(stamp.toUtc());
  return !age.isNegative && age <= const Duration(minutes: 15);
}

String dashboardCategory(String raw) {
  final cat = raw.toLowerCase();
  if (cat.contains('international') ||
      cat.contains('global') ||
      cat.contains('nasdaq') ||
      cat.contains('foreign')) {
    return 'International';
  }
  if (cat.contains('silver')) return 'Silver';
  if (cat.contains('gold')) return 'Gold';
  if (cat.contains('debt') ||
      cat.contains('liquid') ||
      cat.contains('bond') ||
      cat.contains('gilt') ||
      cat.contains('money market')) {
    return 'Debt';
  }
  if (cat.contains('large') && cat.contains('mid')) return 'Mixed equity';
  if (cat.contains('small')) return 'Small Cap';
  if (cat.contains('mid')) return 'Mid Cap';
  if (cat.contains('large') || cat.contains('bluechip')) return 'Large Cap';
  if (cat.contains('flexi') || cat.contains('multi')) return 'Flexi Cap';
  if (cat.contains('hybrid') || cat.contains('balanced')) return 'Hybrid';
  return 'Unclassified';
}

class DashboardSnapshot {
  final Map<String, dynamic>? equity, funds;
  final Map<String, double> other, targets;
  DashboardSnapshot({
    this.equity,
    this.funds,
    this.other = const {},
    this.targets = const {},
  });
  List<Map<String, dynamic>> get holdings => dashboardRows(equity?['holdings']);
  List<Map<String, dynamic>> get fundRows => dashboardRows(funds?['funds']);

  double? _sum(Map<String, dynamic>? data, String key, String field) {
    if (data == null || data[key] is! List) return null;
    double total = 0;
    for (final row in dashboardRows(data[key])) {
      final value = dashboardNumber(row[field]);
      if (value == null) return null;
      total += value;
    }
    return total;
  }

  double? get equityValue => _sum(equity, 'holdings', 'total_value');
  double? get fundValue => _sum(funds, 'funds', 'current_value');
  double? get invested {
    final a = _sum(equity, 'holdings', 'invested');
    final b = _sum(funds, 'funds', 'invested');
    return a == null || b == null ? null : a + b;
  }

  double? get investmentValue => equityValue == null || fundValue == null
      ? null
      : equityValue! + fundValue!;
  double? get value => investmentValue == null
      ? null
      : investmentValue! +
            other.values
                .where((v) => v.isFinite && v >= 0)
                .fold(0.0, (a, b) => a + b);
  double? get pnl => invested == null || investmentValue == null
      ? null
      : investmentValue! - invested!;
  double? get absoluteReturn =>
      invested == null || invested! <= 0 || pnl == null
      ? null
      : pnl! / invested! * 100;
  double? get equityDayChange => _sum(equity, 'holdings', 'day_change_value');
  double? get monthInvested {
    final a = dashboardNumber(equity?['month_investment']);
    final b = dashboardNumber(funds?['month_investment']);
    return a == null || b == null ? null : a + b;
  }

  bool get validTargets =>
      targets.isNotEmpty &&
      targets.values.every((v) => v.isFinite && v >= 0 && v <= 100) &&
      (targets.values.fold(0.0, (a, b) => a + b) - 100).abs() < .01;

  Map<String, double> get categoryValues {
    final out = <String, double>{};
    void add(String key, double? v) {
      if (v != null) out[key] = (out[key] ?? 0) + v;
    }

    for (final h in holdings) {
      // A stock name/sector is not evidence of its market-cap category.
      add(
        dashboardCategory('${h['market_cap_category'] ?? ''}'),
        dashboardNumber(h['total_value']),
      );
    }
    for (final f in fundRows) {
      add(
        dashboardCategory('${f['category'] ?? ''}'),
        dashboardNumber(f['current_value']),
      );
    }
    other.forEach((k, v) {
      if (v.isFinite && v >= 0) add(k, v);
    });
    return out;
  }

  double? weight(double? amount) =>
      value == null || value! <= 0 || amount == null
      ? null
      : amount / value! * 100;
  double? drift(String category) =>
      !validTargets ||
          !targets.containsKey(category) ||
          value == null ||
          value! <= 0
      ? null
      : weight(categoryValues[category] ?? 0)! - targets[category]!;
}

/// Existing expense sheets remain in their source currency; never silently
/// combine local-currency cashflows with INR investments.
class DashboardExpense {
  final MonthlyReport? report, previous;
  final String currency;
  final List<CategoryLine> topCategories;
  final double? incomingTransfers, budget;
  DashboardExpense({
    this.report,
    this.previous,
    String? currency,
    this.topCategories = const [],
    this.incomingTransfers,
    this.budget,
  }) : currency = currency ?? ExpenseConfig.current.localCurrency;

  factory DashboardExpense.fromYear(
    Map<String, dynamic>? source,
    DateTime now, {
    Map<String, dynamic>? previousYear,
  }) {
    if (source == null) return DashboardExpense();
    final data = jsonDecode(jsonEncode(source)) as Map<String, dynamic>;
    ExpenseSchema.recompute(data); // clone: viewing never writes user data.
    final month = ExpenseSchema.months[now.month - 1];
    final report = ExpenseAnalytics.monthlyReport(data, now.year, month);
    MonthlyReport? previous;
    if (now.month > 1) {
      previous = ExpenseAnalytics.monthlyReport(
        data,
        now.year,
        ExpenseSchema.months[now.month - 2],
      );
    } else if (previousYear != null) {
      final old = jsonDecode(jsonEncode(previousYear)) as Map<String, dynamic>;
      ExpenseSchema.recompute(old);
      previous = ExpenseAnalytics.monthlyReport(old, now.year - 1, 'dec');
    }
    final sec = data['local'] as Map? ?? {};
    final transfers = {'transfer', ...ExpenseSchema.extraTransferKeys(sec)};
    final hasIncoming = report.row.containsKey('incoming_transfer') ||
        ExpenseSchema.extraDefs(sec).any((d) => d['kind'] == 'incoming_transfer');
    final incoming = hasIncoming ? dashboardNumber(report.row['incoming_transfer_total']) : null;
    return DashboardExpense(
      report: report,
      previous: previous,
      currency: '${sec['currency'] ?? ExpenseConfig.current.localCurrency}',
      incomingTransfers: incoming,
      budget: dashboardNumber(sec['monthly_budget']),
      topCategories: report.categories
          .where((c) => !transfers.contains(c.key) && c.amount > 0)
          .take(3)
          .toList(),
    );
  }
}
