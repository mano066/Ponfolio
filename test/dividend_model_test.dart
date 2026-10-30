import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/providers/dividend_provider.dart';

/// Verifies the client-side dividend model against the exact payload shape the
/// backend emits, plus the degraded shapes it can emit (missing keys, nulls,
/// string-keyed month maps from JSON).
void main() {
  // A trimmed but structurally faithful copy of /api/portfolio/dividend-analysis.
  Map<String, dynamic> payload() => {
        'as_of': '2026-08-05',
        'goal': {
          'annual': 120000.0,
          'monthly': 10000.0,
          'achieved_pct': 43.8,
          'gap_annual': 67470.0,
          'gap_monthly': 5622.5,
          'on_track': false,
          'years_to_goal': 4,
          'goal_year': 2030,
          'assumed_dividend_growth_pct': 9.5,
          'assumed_new_money_yield_pct': 4.2,
          'monthly_investment': 11000.0,
          'sip_needed_3y': 24000.0,
          'sip_needed_5y': 13000.0,
          'sip_needed_10y': 5000.0,
        },
        'income': {
          'annual_gross': 52530.0,
          'monthly_gross': 4377.5,
          'annual_net': 36771.0,
          'monthly_net': 3064.25,
          'tax_slab_pct': 30.0,
          'from_stocks': 52530.0,
          'from_funds': 0.0,
          'reinvested_in_funds': 6000.0,
          'blended_yield': 4.21,
          'yield_on_cost': 4.55,
          'total_value': 1247500.0,
          'income_bearing_value': 747500.0,
          'income_bearing_pct': 59.9,
          'payer_count': 2,
          'non_payer_count': 1,
          'non_payers': ['ITCHOTELS'],
        },
        'corpus_ladder': [
          {'yield_pct': 3.0, 'corpus_required': 4000000.0, 'realism': 'achievable'},
          {'yield_pct': 6.0, 'corpus_required': 2000000.0,
           'realism': 'deep-value / PSU concentration'},
        ],
        'projection': [
          {'year': 2027, 'offset': 1, 'annual_income': 57520.0,
           'monthly_income': 4793.3, 'corpus': 1479300.0, 'goal_pct': 47.9,
           'goal_reached': false},
          {'year': 2030, 'offset': 4, 'annual_income': 124000.0,
           'monthly_income': 10333.3, 'corpus': 2200000.0, 'goal_pct': 103.3,
           'goal_reached': true},
        ],
        'stocks': [
          {
            'symbol': 'COALINDIA', 'sector': 'Energy', 'mcap_class': 'Large Cap',
            'shares': 100.0, 'price': 400.0, 'avg_cost': 350.0,
            'value': 40000.0, 'dps': 26.5, 'dps_source': 'history_last_fy',
            'annual_income': 2650.0, 'monthly_income': 220.8,
            'yield_pct': 6.6, 'yield_on_cost': 7.57, 'payout_ratio': 70.0,
            'growth_cagr': 10.6, 'years_paid': 8, 'tier': 'anchor',
            'tier_label': 'Income anchor', 'reason': 'keep as an income anchor',
            'tds_applicable': false,
            'payout_months': {'2': 5.5, '8': 21.0},
          },
          {
            'symbol': 'ITCHOTELS', 'sector': 'Hotels', 'shares': 100.0,
            'price': 200.0, 'avg_cost': 180.0, 'value': 20000.0, 'dps': 0.0,
            'dps_source': 'none', 'annual_income': 0.0, 'monthly_income': 0.0,
            'yield_pct': 0.0, 'yield_on_cost': 0.0, 'payout_ratio': 0.0,
            'growth_cagr': 0.0, 'years_paid': 0, 'tier': 'none',
            'tier_label': 'Non-payer', 'reason': 'No dividend',
            'tds_applicable': false, 'payout_months': {},
          },
        ],
        'funds': [
          {
            'scheme_name': 'PPFAS Flexi Cap Growth', 'category': 'Flexi Cap',
            'plan': 'Growth', 'distributes': false, 'value': 500000.0,
            'invested': 400000.0, 'lookthrough_yield': 1.2,
            'lookthrough_income': 6000.0, 'cash_income': 0.0,
            'monthly_income': 0.0, 'note': 'Growth plan',
          },
        ],
        'by_sector': [
          {'sector': 'Energy', 'income': 2650.0, 'pct': 5.0},
          {'sector': 'FMCG', 'income': 1754.5, 'pct': 3.3},
        ],
        'anchors': [],
        'growers': [],
        'traps': [],
        'calendar': [
          for (var m = 1; m <= 12; m++)
            {'month': m, 'amount': m == 8 ? 2772.0 : m == 2 ? 726.0 : 0.0}
        ],
        'alerts': [
          {'level': 'warning', 'msg': '67% of income comes from COALINDIA'},
        ],
        'disclosure': {
          'dps_basis': 'Higher of trailing 12 months and last completed fiscal year',
        },
      };

  group('DividendBook parsing', () {
    late DividendBook book;

    setUp(() => book = DividendBook.fromJson(payload()));

    test('goal block round-trips', () {
      expect(book.goal.annual, 120000);
      expect(book.goal.monthly, 10000);
      expect(book.goal.achievedPct, 43.8);
      expect(book.goal.onTrack, isFalse);
      expect(book.goal.yearsToGoal, 4);
      expect(book.goal.goalYear, 2030);
      expect(book.goal.sipNeeded3y, 24000);
    });

    test('income block round-trips', () {
      expect(book.income.annualGross, 52530);
      expect(book.income.monthlyNet, 3064.25);
      expect(book.income.blendedYield, 4.21);
      expect(book.income.payerCount, 2);
      expect(book.income.nonPayers, ['ITCHOTELS']);
      expect(book.income.reinvestedInFunds, 6000);
    });

    test('stocks parse with tier enum and month map', () {
      expect(book.stocks, hasLength(2));
      final coal = book.stocks.first;
      expect(coal.symbol, 'COALINDIA');
      expect(coal.tier, DividendTier.anchor);
      expect(coal.mcapClass, 'Large Cap');
      expect(coal.shares, 100);
      expect(coal.avgCost, 350);
      expect(coal.value, 40000);
      expect(coal.annualIncome, 2650);
      expect(coal.yieldOnCost, 7.57);
      // JSON object keys arrive as strings and must become ints.
      expect(coal.payoutMonths, {2: 5.5, 8: 21.0});
    });

    test('dps source is rendered in words', () {
      expect(book.stocks.first.dpsSourceLabel, 'Last full FY');
      expect(book.stocks.last.dpsSourceLabel, 'No data');
    });

    test('unknown tier string degrades to none', () {
      final p = payload();
      (p['stocks'] as List)[0]['tier'] = 'something_new';
      expect(DividendBook.fromJson(p).stocks.first.tier, DividendTier.none);
    });

    test('funds parse with plan flag', () {
      expect(book.funds, hasLength(1));
      expect(book.funds.first.distributes, isFalse);
      expect(book.funds.first.lookthroughIncome, 6000);
      expect(book.funds.first.cashIncome, 0);
    });

    test('calendar lands in Jan..Dec order', () {
      expect(book.calendar, hasLength(12));
      expect(book.calendar[7], 2772.0); // August
      expect(book.calendar[1], 726.0); // February
      expect(book.calendar[0], 0.0);
    });

    test('peak month is the largest payout month', () {
      expect(book.peakMonth, 8);
    });

    test('out-of-range calendar months are ignored, not crashed on', () {
      final p = payload();
      p['calendar'] = [
        {'month': 0, 'amount': 999.0},
        {'month': 13, 'amount': 999.0},
        {'month': 5, 'amount': 100.0},
      ];
      final b = DividendBook.fromJson(p);
      expect(b.calendar, hasLength(12));
      expect(b.calendar[4], 100.0);
      expect(b.calendar.reduce((a, x) => a + x), 100.0);
    });

    test('alerts and disclosure carry through', () {
      expect(book.alerts, hasLength(1));
      expect(book.alerts.first['level'], 'warning');
      expect(book.dpsBasis, contains('trailing 12 months'));
    });

    test('hasData is true when holdings exist', () {
      expect(book.hasData, isTrue);
    });
  });

  group('Degraded payloads', () {
    test('completely empty object parses to a zero book', () {
      final book = DividendBook.fromJson({});
      expect(book.income.annualGross, 0);
      expect(book.goal.annual, 0);
      expect(book.stocks, isEmpty);
      expect(book.funds, isEmpty);
      expect(book.calendar, hasLength(12));
      expect(book.calendar.every((v) => v == 0), isTrue);
      expect(book.peakMonth, isNull);
      expect(book.hasData, isFalse);
    });

    test('null values inside blocks do not throw', () {
      final book = DividendBook.fromJson({
        'goal': {'annual': null, 'years_to_goal': null, 'on_track': null},
        'income': {'annual_gross': null, 'non_payers': null},
        'stocks': [
          {'symbol': null, 'shares': null, 'payout_months': null, 'tier': null}
        ],
      });
      expect(book.goal.annual, 0);
      expect(book.goal.yearsToGoal, isNull);
      expect(book.goal.onTrack, isFalse);
      expect(book.income.nonPayers, isEmpty);
      expect(book.stocks.first.symbol, '');
      expect(book.stocks.first.payoutMonths, isEmpty);
    });

    test('string numbers are not silently misread as values', () {
      final book = DividendBook.fromJson({
        'income': {'annual_gross': '52530'},
      });
      // A string where a number belongs becomes 0 rather than a wrong figure.
      expect(book.income.annualGross, 0);
    });

    test('numeric month keys also parse', () {
      final book = DividendBook.fromJson({
        'stocks': [
          {'symbol': 'X', 'payout_months': {8: 21.0}}
        ],
      });
      expect(book.stocks.first.payoutMonths, {8: 21.0});
    });

    test('empty static book is well formed', () {
      expect(DividendBook.empty.calendar, hasLength(12));
      expect(DividendBook.empty.hasData, isFalse);
      expect(DividendBook.empty.peakMonth, isNull);
    });
  });

  group('Tier mapping', () {
    test('every backend tier string maps to a distinct enum', () {
      expect(tierFromString('anchor'), DividendTier.anchor);
      expect(tierFromString('grower'), DividendTier.grower);
      expect(tierFromString('modest'), DividendTier.modest);
      expect(tierFromString('trap'), DividendTier.trap);
      expect(tierFromString('none'), DividendTier.none);
      expect(tierFromString(null), DividendTier.none);
    });
  });

  group('DividendGoalDraft', () {
    test('copyWith preserves the untouched field', () {
      const d = DividendGoalDraft(goalAnnual: 120000, monthlyInvestment: 5000);
      expect(d.copyWith(goalAnnual: 240000).monthlyInvestment, 5000);
      expect(d.copyWith(monthlyInvestment: 1000).goalAnnual, 120000);
    });

    test('isEmpty only when nothing has been set', () {
      expect(const DividendGoalDraft().isEmpty, isTrue);
      expect(const DividendGoalDraft(goalAnnual: 1).isEmpty, isFalse);
      expect(const DividendGoalDraft(monthlyInvestment: 1).isEmpty, isFalse);
    });
  });
}
