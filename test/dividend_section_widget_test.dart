import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/core/theme/app_theme.dart';
import 'package:aiei_wealth/providers/dividend_provider.dart';
import 'package:aiei_wealth/presentation/widgets/dividend_section.dart';

/// Renders the dividend section against representative books to catch layout
/// assertion failures (unbounded constraints, overflow, bad Expanded nesting)
/// that static analysis cannot see.
void main() {
  DividendBook bookWith({
    int stockCount = 3,
    int fundCount = 1,
    bool withTrap = true,
    bool onTrack = false,
    int? yearsToGoal = 4,
    bool withCalendar = true,
    bool withAlerts = true,
  }) {
    return DividendBook.fromJson({
      'as_of': '2026-08-05',
      'goal': {
        'annual': 120000.0,
        'monthly': 10000.0,
        'achieved_pct': onTrack ? 118.0 : 43.8,
        'gap_annual': onTrack ? 0.0 : 67470.0,
        'gap_monthly': onTrack ? 0.0 : 5622.5,
        'on_track': onTrack,
        'years_to_goal': yearsToGoal,
        'goal_year': yearsToGoal == null ? null : 2026 + yearsToGoal,
        'assumed_dividend_growth_pct': 11.19,
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
        'reinvested_in_funds': 10500.0,
        'blended_yield': 4.21,
        'yield_on_cost': 4.55,
        'total_value': 1247500.0,
        'income_bearing_value': 747500.0,
        'income_bearing_pct': 59.9,
        'payer_count': stockCount,
        'non_payer_count': 1,
        'non_payers': ['ITCHOTELS'],
      },
      'corpus_ladder': [
        for (final y in [2.5, 3.0, 4.0, 6.0])
          {
            'yield_pct': y,
            'corpus_required': 120000 / (y / 100),
            'realism': y <= 4 ? 'achievable' : 'deep-value / PSU concentration',
          }
      ],
      'projection': [
        for (var i = 1; i <= 10; i++)
          {
            'year': 2026 + i,
            'offset': i,
            'annual_income': 52530.0 * (1 + 0.11 * i),
            'monthly_income': 52530.0 * (1 + 0.11 * i) / 12,
            'corpus': 1247500.0 * (1 + 0.08 * i),
            'goal_pct': 43.8 * (1 + 0.11 * i),
            'goal_reached': yearsToGoal != null && i >= yearsToGoal,
          }
      ],
      'stocks': [
        for (var i = 0; i < stockCount; i++)
          {
            'symbol': 'STOCK$i',
            'sector': ['Energy', 'FMCG', 'Banking'][i % 3],
            'mcap_class': 'Large Cap',
            'shares': 100.0 + i,
            'price': 400.0,
            'avg_cost': 380.0,
            'value': 40000.0,
            'dps': 26.5 - i,
            'dps_source': 'history_last_fy',
            'annual_income': 3000.0 - i * 500,
            'monthly_income': 250.0,
            'yield_pct': 6.4 - i,
            'yield_on_cost': 6.85 - i,
            'payout_ratio': withTrap && i == 0 ? 130.0 : 70.0,
            'growth_cagr': 10.6 - i * 4,
            'years_paid': 8,
            'tier': withTrap && i == 0
                ? 'trap'
                : ['anchor', 'grower', 'modest', 'none'][i % 4],
            'tier_label': withTrap && i == 0 ? 'Yield trap risk' : 'Income anchor',
            'reason': 'A reasonably long explanation of why this holding sits '
                'in the tier it does, long enough to wrap on a narrow screen.',
            'tds_applicable': i == 0,
            'payout_months': withCalendar ? {'2': 5.5, '8': 21.0} : {},
          }
      ],
      'funds': [
        for (var i = 0; i < fundCount; i++)
          {
            'scheme_name': 'A Rather Long Mutual Fund Scheme Name '
                'Direct Plan Growth Option $i',
            'category': 'Flexi Cap',
            'plan': i.isEven ? 'Growth' : 'IDCW',
            'distributes': i.isOdd,
            'value': 500000.0,
            'invested': 400000.0,
            'lookthrough_yield': 2.1,
            'lookthrough_income': 10500.0,
            'cash_income': i.isOdd ? 10500.0 : 0.0,
            'monthly_income': i.isOdd ? 875.0 : 0.0,
            'note': 'Growth plan',
          }
      ],
      'by_sector': [
        {'sector': 'Energy', 'income': 35000.0, 'pct': 66.6},
        {'sector': 'FMCG', 'income': 12530.0, 'pct': 23.9},
        {'sector': 'Banking', 'income': 5000.0, 'pct': 9.5},
      ],
      'anchors': [],
      'growers': [],
      'traps': withTrap
          ? [
              {'symbol': 'STOCK0', 'tier': 'trap', 'annual_income': 3000.0}
            ]
          : [],
      'calendar': [
        for (var m = 1; m <= 12; m++)
          {
            'month': m,
            'amount': withCalendar ? (m == 8 ? 2772.0 : m == 2 ? 726.0 : 0.0) : 0.0
          }
      ],
      'alerts': withAlerts
          ? [
              {'level': 'critical', 'msg': 'STOCK0 payout looks unfunded'},
              {'level': 'warning', 'msg': '66% of income is Energy'},
              {'level': 'info', 'msg': '₹10,500/yr is reinvested inside funds'},
            ]
          : [],
      'disclosure': {'dps_basis': 'Higher of trailing 12 months and last FY'},
    });
  }

  Future<void> pump(WidgetTester tester, DividendBook book,
      {Size size = const Size(1600, 1200)}) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          dividendBookProvider.overrideWith((ref) async => book),
        ],
        child: MaterialApp(
          theme: AppTheme.dark(),
          home: Scaffold(
            body: SingleChildScrollView(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: const DividendSection(),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  group('DividendSection renders', () {
    testWidgets('a full book without layout errors', (tester) async {
      await pump(tester, bookWith());
      expect(tester.takeException(), isNull);
      // Headline numbers reach the screen.
      expect(find.text('DIVIDEND INCOME · PER MONTH'), findsOneWidget);
      expect(find.text('The Ledger'), findsOneWidget);
      expect(find.textContaining('Path to'), findsOneWidget);
    });

    testWidgets('an empty book shows the empty state, not a crash',
        (tester) async {
      await pump(tester, DividendBook.empty);
      expect(tester.takeException(), isNull);
      expect(find.text('No holdings to measure'), findsOneWidget);
    });

    testWidgets('a book with no funds omits the fund table', (tester) async {
      await pump(tester, bookWith(fundCount: 0));
      expect(tester.takeException(), isNull);
      expect(find.text('Fund Income — Paid vs Reinvested'), findsNothing);
    });

    testWidgets('a book with no alerts omits the alert card', (tester) async {
      await pump(tester, bookWith(withAlerts: false));
      expect(tester.takeException(), isNull);
      expect(find.text('What Would Change the Plan'), findsNothing);
    });

    testWidgets('an empty payout calendar falls back to a note', (tester) async {
      await pump(tester, bookWith(withCalendar: false));
      expect(tester.takeException(), isNull);
      expect(find.textContaining('No ex-date history'), findsOneWidget);
    });

    testWidgets('an unreachable goal renders 10 yr+ rather than null',
        (tester) async {
      await pump(tester, bookWith(yearsToGoal: null));
      expect(tester.takeException(), isNull);
      expect(find.text('10 yr+'), findsOneWidget);
      expect(find.text('NOT REACHED IN 10 YEARS'), findsOneWidget);
    });

    testWidgets('a goal already met renders the covered state', (tester) async {
      await pump(tester, bookWith(onTrack: true));
      expect(tester.takeException(), isNull);
      expect(find.text('Goal covered'), findsOneWidget);
    });

    testWidgets('many holdings and long names still lay out', (tester) async {
      await pump(tester, bookWith(stockCount: 12, fundCount: 5));
      expect(tester.takeException(), isNull);
    });

    testWidgets('a narrow window does not throw overflow assertions',
        (tester) async {
      await pump(tester, bookWith(), size: const Size(1100, 1400));
      expect(tester.takeException(), isNull);
    });

    testWidgets('the narrowest real content width lays out', (tester) async {
      // 1024px minimum window less the shell's 220px sidebar.
      await pump(tester, bookWith(), size: const Size(780, 2200));
      expect(tester.takeException(), isNull);
    });
  });

  group('DividendSection interactions', () {
    testWidgets('the path-to-goal tabs each render', (tester) async {
      await pump(tester, bookWith());
      for (final label in ['Income path', 'SIP to close the gap', 'Corpus needed']) {
        await tester.tap(find.text(label));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull, reason: 'tab "$label" threw');
      }
      expect(find.textContaining('4.0% yield'), findsOneWidget);
    });

    testWidgets('tapping a ledger row expands its reasoning', (tester) async {
      await pump(tester, bookWith());
      expect(find.text('DPS FROM'), findsNothing);
      await tester.tap(find.text('STOCK0'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('DPS FROM'), findsOneWidget);
      expect(find.textContaining('TDS'), findsOneWidget);

      // Tapping again collapses it.
      await tester.tap(find.text('STOCK0'));
      await tester.pumpAndSettle();
      expect(find.text('DPS FROM'), findsNothing);
    });

    testWidgets('tier filter chips narrow the ledger', (tester) async {
      await pump(tester, bookWith(stockCount: 4));
      expect(find.text('STOCK0'), findsOneWidget);
      // "GROWERS" is also a header stat label, so target the chip specifically.
      await tester.tap(find.text('GROWERS').last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      // STOCK0 is the trap, so it drops out of the growers bucket.
      expect(find.text('STOCK0'), findsNothing);
    });

    testWidgets('an empty filter bucket shows a message, not a blank table',
        (tester) async {
      await pump(tester, bookWith(stockCount: 1, withTrap: false));
      await tester.tap(find.text('YIELD TRAPS'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Nothing in this bucket'), findsOneWidget);
    });

    testWidgets('the goal dialog opens and validates input', (tester) async {
      await pump(tester, bookWith());
      await tester.tap(find.text('Set Goal'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Dividend Income Goal'), findsOneWidget);

      // A non-numeric goal is rejected rather than silently saved.
      await tester.enterText(find.byType(TextField).first, 'abc');
      await tester.tap(find.text('Save Goal'));
      await tester.pumpAndSettle();
      expect(find.text('Enter a valid annual goal'), findsOneWidget);

      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(find.text('Dividend Income Goal'), findsNothing);
    });

    testWidgets('goal presets fill the field', (tester) async {
      await pump(tester, bookWith());
      await tester.tap(find.text('Set Goal'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('₹25,000/mo'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.textContaining('₹25,000 a month'), findsOneWidget);
    });
  });
}
