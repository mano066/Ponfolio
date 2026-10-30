import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/data/models/expense_analytics.dart';
import 'package:aiei_wealth/data/models/expense_config.dart';
import 'package:aiei_wealth/data/models/expense_schema.dart';

/// The optional local expense config: generic defaults when it is absent, and
/// when present it renames files and labels and migrates older stored keys so
/// an existing dataset keeps loading. All names below are made up.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  tearDown(() => ExpenseConfig.current = const ExpenseConfig());

  test('defaults are generic', () {
    const c = ExpenseConfig();
    expect(c.masterFileName, 'expense_master.json');
    expect(c.backupFileName(DateTime(2026, 3, 7)), 'expense_backup_2026_03_07.json');
    expect(c.localLabel, 'Local');
    expect(c.accountALabel, 'Account A');
    expect(c.accountBLabel, 'Account B');
    expect(c.scrips, isEmpty);
    expect(c.seedYears, isEmpty);
    expect(c.money(1234567), 'LCY 1,234,567');
    expect(c.money(-50), '-LCY 50');
    expect(ExpenseSchema.blankYear(2030)['local']['currency'], 'LCY');
  });

  test('a missing config file keeps the defaults', () async {
    final c = await ExpenseConfig.load(bundle: _Bundle({}));
    expect(c.filePrefix, 'expense');
    expect(ExpenseConfig.current.localCurrency, 'LCY');
  });

  test('a config file overrides names, labels, money format and scrips', () async {
    final c = await ExpenseConfig.load(bundle: _Bundle({
      ExpenseConfig.assetPath: jsonEncode({
        'file_prefix': 'Home_budget',
        'local_currency': 'ABC',
        'local_symbol': 'A\$',
        'section_labels': {'local': 'Abroad', 'account_a': 'Bank One'},
        'section_short_labels': {'account_a': 'B1'},
        'field_labels': {'local_amount': 'ABC sent'},
        'scrips': ['AAA', 'BBB'],
        'seed_years': [2030],
      }),
    }));
    expect(identical(c, ExpenseConfig.current), true);
    expect(c.masterFileName, 'Home_budget_master.json');
    expect(c.backupFileName(DateTime(2031, 12, 1)), 'Home_budget_backup_2031_12_01.json');
    expect(c.money(9876), 'A\$9,876');
    expect(c.localLabel, 'Abroad');
    expect(c.short('account_a'), 'B1');
    expect(c.short('account_b'), 'Account B', reason: 'unset labels fall back');
    expect(ExpenseSchema.scrips, ['AAA', 'BBB']);
    expect(ExpenseSchema.accountA.firstWhere((col) => col.key == 'local_amount').label, 'ABC sent');
    expect(ExpenseConfig.seedAsset(2030), 'assets/private/expense_2030.html');
  });

  test('legacy stored keys are migrated on load, without touching newer keys', () {
    ExpenseConfig.current = ExpenseConfig.fromJson({
      'legacy_section_keys': {'old_ledger': 'local', 'old_bank': 'account_a'},
      'legacy_field_keys': {'old_amount': 'local_amount', 'old_bal': 'bank_balance'},
      'legacy_type': 'old_type',
    });
    final year = <String, dynamic>{
      'year': 2026,
      'old_ledger': {
        'currency': 'ABC',
        'months': [
          {'month': 'jan', 'opening': 100, 'salary': 1000, 'rent': 300},
        ],
        'totals': {},
        'source': {
          'columns': {'salary': 2},
          'labels': {'salary': 'Salary'},
        },
      },
      'old_bank': {
        'currency': 'INR',
        'months': [
          {'month': 'jan', 'old_amount': 500, 'inr_received': 1200, 'opening': 0},
        ],
        'totals': {},
      },
      'investments': {
        'currency': 'INR',
        'months': [
          {'month': 'jan', 'gold': 10, 'old_bal': 40},
        ],
        'totals': {},
      },
    };
    ExpenseSchema.recompute(year);
    expect(year.containsKey('old_ledger'), false);
    expect(year.containsKey('old_bank'), false);
    final r = ExpenseAnalytics.monthlyReport(year, 2026, 'jan');
    expect(r.totalIncome, 1000);
    expect(r.closingBalance, 800);
    final bank = (year['account_a']['months'] as List).first as Map;
    expect(bank['local_amount'], 500);
    expect(bank.containsKey('old_amount'), false);
    expect(bank['balance'], 1200);
    final inv = (year['investments']['months'] as List).first as Map;
    expect(inv['bank_balance'], 40);
    expect(inv['total'], 50);

    // A key already in the new name wins over its legacy twin.
    final both = <String, dynamic>{
      'local': {'months': [], 'marker': 'new'},
      'old_ledger': {'months': [], 'marker': 'old'},
    };
    ExpenseConfig.current.migrateYear(both);
    expect(both['local']['marker'], 'new');
    expect(both.containsKey('old_ledger'), false);

    // A whole downloaded dataset: every year, and the dataset type.
    final master = <String, dynamic>{
      'type': 'old_type',
      'years': {
        '2026': {'old_ledger': {'months': []}},
      },
    };
    ExpenseConfig.current.migrateDataset(master);
    expect(master['type'], ExpenseConfig.datasetType);
    expect((master['years'] as Map)['2026'].containsKey('local'), true);
  });

  test('without legacy keys nothing is renamed', () {
    final year = <String, dynamic>{'something_else': {'months': []}};
    const ExpenseConfig().migrateYear(year);
    expect(year.keys, ['something_else']);
  });
}

class _Bundle extends CachingAssetBundle {
  final Map<String, String> files;
  _Bundle(this.files);
  @override
  Future<ByteData> load(String key) async {
    final s = files[key];
    if (s == null) throw FlutterError('Unable to load asset: $key');
    return ByteData.sublistView(Uint8List.fromList(utf8.encode(s)));
  }
}
