import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/core/theme/app_theme.dart';
import 'package:aiei_wealth/providers/providers.dart';
import 'package:aiei_wealth/providers/allocation_provider.dart';
import 'package:aiei_wealth/providers/dividend_provider.dart';
import 'package:aiei_wealth/presentation/screens/allocation_screen.dart';

/// Exercises the tabbed allocation screen: every tab must render without a
/// layout assertion, at both a wide and a cramped window.
///
/// Storage-backed notifiers are subclassed rather than mocked so `build()`
/// never touches Hive in a test process.
class _FakeOtherAssets extends OtherAssetsNotifier {
  @override
  Map<String, double> build() => {'Gold': 120000, 'Cash': 80000};
}

class _FakeRiskProfile extends RiskProfileNotifier {
  @override
  RiskProfile build() => RiskProfile.moderate;
}

class _FakeCustomTargets extends CustomTargetsNotifier {
  @override
  Map<String, double> build() => {};
}

void main() {
  Map<String, dynamic> portfolioFixture() => {
        'total_portfolio_value': 754523.0,
        'total_invested': 700000.0,
        'total_pnl': 54523.0,
        'total_pnl_pct': 7.79,
        'holdings': [
          for (var i = 0; i < 4; i++)
            {
              'symbol': 'STOCK$i',
              'shares': 100,
              'avg_cost': 380.0,
              'ltp': 400.0,
              'current_value': 40000.0,
              'sector': ['Energy', 'FMCG', 'Banking', 'IT'][i],
            }
        ],
        'kite_connected': false,
        'data_source': 'yfinance',
      };

  Map<String, dynamic> mfFixture() => {
        'funds': [
          {
            'scheme_name': 'A Long Fund Scheme Name Direct Plan Growth',
            'category': 'Flexi Cap',
            'invested': 400000.0,
            'current_value': 500000.0,
            'return_pct': 25.0,
            'xirr': 14.2,
          },
        ],
        'total_invested': 400000.0,
        'total_current': 500000.0,
        'total_pnl': 100000.0,
        'total_pnl_pct': 25.0,
      };

  ExposureAnalysis exposureFixture() => ExposureAnalysis.fromJson({
        'total_value': 754523.0,
        'total_stock_value': 254523.0,
        'total_mf_value': 500000.0,
        'unique_holdings': 14,
        'mcap_exposure': {'Large Cap': 62.0, 'Mid Cap': 24.0, 'Small Cap': 14.0},
        'mcap_values': {
          'Large Cap': 467804.0,
          'Mid Cap': 181085.0,
          'Small Cap': 105633.0
        },
        'sector_exposure': {
          'Banking': 28.4,
          'IT': 18.2,
          'Energy': 15.6,
          'FMCG': 12.1,
          'Pharma': 9.3,
          'Auto': 8.0,
          'Metals': 5.2,
          'Telecom': 3.2
        },
        'sector_details': [
          for (final e in {
            'Banking': 28.4,
            'IT': 18.2,
            'Energy': 15.6,
            'FMCG': 12.1
          }.entries)
            {
              'sector': e.key,
              'current_pct': e.value,
              'target_pct': 20.0,
              'delta': e.value - 20.0,
              'status': e.value > 25 ? 'Overweight' : 'Neutral',
              'risk_rating': 'Medium',
              'value': 754523.0 * e.value / 100,
            }
        ],
        'overlap': {
          'overlap_pct': 34.2,
          'duplicate_pct': 21.4,
          'hidden_concentration_pct': 18.9,
          'holdings': [
            for (var i = 0; i < 5; i++)
              {
                'stock': 'STOCK$i',
                'total_value': 40000.0 - i * 2000,
                'exposure_pct': 5.3 - i * 0.4,
                'source_count': 2,
                'sources': [
                  {'source': 'Direct Stock', 'value': 20000.0},
                  {
                    'source': 'A Long Fund Scheme Name Direct Plan Growth',
                    'value': 20000.0
                  },
                ],
              }
          ],
        },
        'concentration': {
          'top5_pct': 46.2,
          'top10_pct': 68.1,
          'top_sector_pct': 28.4,
          'top_sector_name': 'Banking',
          'single_stock_pct': 9.4,
          'single_stock_name': 'STOCK0',
          'alerts': [
            {'level': 'warning', 'msg': 'Top 5 holdings concentration is high'},
            {'level': 'critical', 'msg': 'Single stock risk: STOCK0 at 9.4%'},
          ],
        },
        'enriched_stocks': [
          for (var i = 0; i < 4; i++)
            {
              'symbol': 'STOCK$i',
              'sector': ['Energy', 'FMCG', 'Banking', 'IT'][i],
              'industry': 'Other',
              'mcap_class': 'Large Cap',
              'current_price': 400.0,
              'shares': 100,
              'avg_cost': 380.0,
              'invested': 38000.0,
              'current_value': 40000.0,
              'pnl': 2000.0,
              'pnl_pct': 5.26,
              'risk_score': 2,
            }
        ],
        'enriched_funds': [
          {
            'scheme_name': 'A Long Fund Scheme Name Direct Plan Growth',
            'category': 'Flexi Cap',
            'invested': 400000.0,
            'current_value': 500000.0,
            'pnl': 100000.0,
            'return_pct': 25.0,
            'xirr': 14.2,
            'lc_pct': 62.0,
            'mc_pct': 24.0,
            'sc_pct': 14.0,
            'top_sector': 'Banking',
            'style': 'Growth',
            'overlap_score': 40.0,
            'top_holdings_count': 10,
            'risk_score': 3,
          }
        ],
        'top_holdings': [
          for (var i = 0; i < 8; i++)
            {
              'stock': 'STOCK$i',
              'value': 40000.0 - i * 2000,
              'pct': 5.3 - i * 0.4,
              'source_count': 2
            }
        ],
        'sector_holdings': {
          'Banking': [
            {'stock': 'STOCK2', 'value': 40000.0, 'pct': 5.3}
          ],
          'IT': [
            {'stock': 'STOCK3', 'value': 38000.0, 'pct': 5.0}
          ],
        },
        'overlap_source_names': [
          'Direct Stock',
          'A Long Fund Scheme Name Direct Plan Growth'
        ],
      });

  DividendBook dividendFixture() => DividendBook.fromJson({
        'goal': {
          'annual': 120000.0,
          'monthly': 10000.0,
          'achieved_pct': 5.1,
          'gap_annual': 113935.0,
          'gap_monthly': 9494.5,
          'on_track': false,
          'years_to_goal': null,
          'assumed_dividend_growth_pct': 11.19,
          'assumed_new_money_yield_pct': 4.0,
          'monthly_investment': 0.0,
          'sip_needed_5y': 15534.0,
        },
        'income': {
          'annual_gross': 6065.0,
          'monthly_gross': 505.4,
          'annual_net': 4245.0,
          'monthly_net': 353.8,
          'tax_slab_pct': 30.0,
          'from_stocks': 6065.0,
          'from_funds': 0.0,
          'reinvested_in_funds': 10500.0,
          'blended_yield': 0.8,
          'yield_on_cost': 0.87,
          'total_value': 754523.0,
          'income_bearing_value': 254523.0,
          'income_bearing_pct': 33.7,
          'payer_count': 3,
          'non_payer_count': 1,
          'non_payers': ['STOCK3'],
        },
        'corpus_ladder': [
          {'yield_pct': 4.0, 'corpus_required': 3000000.0, 'realism': 'achievable'}
        ],
        'projection': [
          for (var i = 1; i <= 10; i++)
            {
              'year': 2026 + i,
              'offset': i,
              'annual_income': 6065.0 * (1 + 0.11 * i),
              'monthly_income': 505.0 * (1 + 0.11 * i),
              'corpus': 754523.0 * (1 + 0.08 * i),
              'goal_pct': 5.1 * (1 + 0.11 * i),
              'goal_reached': false,
            }
        ],
        'stocks': [
          for (var i = 0; i < 3; i++)
            {
              'symbol': 'STOCK$i',
              'sector': ['Energy', 'FMCG', 'Banking'][i],
              'shares': 100.0,
              'price': 400.0,
              'avg_cost': 380.0,
              'value': 40000.0,
              'dps': 20.0 - i * 5,
              'dps_source': 'history_last_fy',
              'annual_income': 2000.0 - i * 500,
              'monthly_income': 166.0,
              'yield_pct': 5.0 - i,
              'yield_on_cost': 5.3 - i,
              'payout_ratio': 60.0,
              'growth_cagr': 12.0,
              'years_paid': 8,
              'tier': 'anchor',
              'tier_label': 'Income anchor',
              'reason': 'Solid payer',
              'tds_applicable': false,
              'payout_months': {'8': 20.0},
            }
        ],
        'funds': [],
        'by_sector': [
          {'sector': 'Energy', 'income': 2000.0, 'pct': 33.0}
        ],
        'anchors': [],
        'growers': [],
        'traps': [],
        'calendar': [
          for (var m = 1; m <= 12; m++)
            {'month': m, 'amount': m == 8 ? 6065.0 : 0.0}
        ],
        'alerts': [],
        'disclosure': {'dps_basis': 'Higher of TTM and last full FY'},
      });

  Future<void> pump(WidgetTester tester,
      {Size size = const Size(1700, 1300),
      ExposureAnalysis? exposure,
      bool exposureFails = false}) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          portfolioProvider.overrideWith((ref) async => portfolioFixture()),
          mfPortfolioProvider.overrideWith((ref) async => mfFixture()),
          exposureAnalysisProvider.overrideWith((ref) async {
            if (exposureFails) throw Exception('backend down');
            return exposure ?? exposureFixture();
          }),
          dividendBookProvider.overrideWith((ref) async => dividendFixture()),
          otherAssetsProvider.overrideWith(_FakeOtherAssets.new),
          riskProfileProvider.overrideWith(_FakeRiskProfile.new),
          customTargetsProvider.overrideWith(_FakeCustomTargets.new),
        ],
        child: MaterialApp(
          theme: AppTheme.dark(),
          home: const Scaffold(
            body: Padding(
              padding: EdgeInsets.all(16),
              child: AllocationScreen(),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  group('AllocationScreen structure', () {
    testWidgets('renders the persistent header and the tab strip',
        (tester) async {
      await pump(tester);
      expect(tester.takeException(), isNull);
      expect(find.text('PORTFOLIO VALUE'), findsOneWidget);
      expect(find.text('What Matters Right Now'), findsOneWidget);
      for (final tab in AllocTab.values) {
        expect(find.text(tab.label), findsWidgets, reason: '${tab.label} missing');
      }
    });

    testWidgets('opens on Overview', (tester) async {
      await pump(tester);
      expect(find.text('Asset Allocation — Current vs Target'), findsOneWidget);
    });

    testWidgets('Overview does not repeat what is already on the page',
        (tester) async {
      // Three sections used to state the same asset split: the category strip
      // above the tabs, a two-slice donut, and the Current vs Target table.
      // Only the table earns it — it carries the target and the gap as well.
      await pump(tester);
      expect(find.text('Portfolio Composition'), findsNothing);

      // OVERLAP and TOP 5 CONC are cards in "What Matters Right Now"; the KPI
      // strip below must not print the same figures a second time.
      expect(find.text('OVERLAP'), findsNothing);
      expect(find.text('TOP 5 CONC'), findsNothing);
      // TOP SECTOR is a card candidate too, so it went the same way. It may
      // still appear ONCE as a card when it ranks into the top four — the rule
      // is that no figure appears twice, not that it vanishes.
      expect(find.text('TOP SECTOR').evaluate().length, lessThanOrEqualTo(1));
      for (final kept in ['UNIQUE HOLDINGS', '#1 HOLDING', 'RISK ALERTS']) {
        expect(find.text(kept), findsOneWidget, reason: kept);
      }
    });

    testWidgets('every tab renders without a layout assertion', (tester) async {
      await pump(tester);
      for (final tab in AllocTab.values) {
        await tester.tap(find.text(tab.label).first);
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull,
            reason: 'tab "${tab.label}" threw during layout');
      }
    });

    testWidgets('each tab shows its own section, not the others',
        (tester) async {
      await pump(tester);

      await tester.tap(find.text('Exposure & Risk').first);
      await tester.pumpAndSettle();
      expect(find.text('Sector Exposure'), findsOneWidget);
      expect(find.text('Concentration Risk'), findsOneWidget);
      expect(find.text('Portfolio Composition'), findsNothing);

      await tester.tap(find.text('Overlap').first);
      await tester.pumpAndSettle();
      expect(find.text('Portfolio Overlap'), findsOneWidget);
      expect(find.text('Sector Exposure'), findsNothing);

      await tester.tap(find.text('Holdings').first);
      await tester.pumpAndSettle();
      expect(find.text('Mutual Fund Deep Analysis'), findsOneWidget);
      expect(find.text('Direct Stock Analysis & Rebalancing'), findsOneWidget);

      await tester.tap(find.text('Dividend Income').first);
      await tester.pumpAndSettle();
      expect(find.text('The Ledger'), findsOneWidget);
      expect(find.text('Mutual Fund Deep Analysis'), findsNothing);
    });

    testWidgets('a cramped window still lays out every tab', (tester) async {
      await pump(tester, size: const Size(1150, 1400));
      for (final tab in AllocTab.values) {
        await tester.tap(find.text(tab.label).first);
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull,
            reason: 'tab "${tab.label}" overflowed at 1150px');
      }
    });

    testWidgets('the narrowest real content width lays out every tab',
        (tester) async {
      // Minimum window is 1024px (main.dart) and the shell reserves a 220px
      // sidebar, so ~780px is the narrowest the screen can actually get.
      await pump(tester, size: const Size(780, 1500));
      expect(tester.takeException(), isNull, reason: 'header overflowed at 780px');
      for (final tab in AllocTab.values) {
        // At this width the tab strip scrolls, so the last tabs sit off-screen
        // and a bare tap() would miss them — leaving those tabs unmeasured.
        final chip = find.text(tab.label).first;
        await tester.ensureVisible(chip);
        await tester.pumpAndSettle();
        await tester.tap(chip);
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull,
            reason: 'tab "${tab.label}" overflowed at 780px');
      }
    });

    testWidgets('each tab states the question it answers', (tester) async {
      await pump(tester);
      for (final tab in AllocTab.values) {
        await tester.tap(find.text(tab.label).first);
        await tester.pumpAndSettle();
        expect(find.text(tab.purpose), findsOneWidget,
            reason: 'no purpose line for "${tab.label}"');
      }
    });
  });

  group('Section explainers', () {
    testWidgets('every tab explains its sections', (tester) async {
      await pump(tester);
      for (final tab in AllocTab.values) {
        await tester.tap(find.text(tab.label).first);
        await tester.pumpAndSettle();
        expect(find.text('How to read'), findsWidgets,
            reason: 'tab "${tab.label}" has no explainer');
      }
    });

    testWidgets('an explainer expands and collapses', (tester) async {
      await pump(tester);
      expect(find.text('Hide'), findsNothing);

      await tester.tap(find.text('How to read').first);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Hide'), findsOneWidget);

      await tester.tap(find.text('Hide'));
      await tester.pumpAndSettle();
      expect(find.text('Hide'), findsNothing);
    });

    testWidgets('expanding every explainer on a tab never overflows',
        (tester) async {
      // Tall viewport on purpose: with every section on screen at once the
      // outer ListView never unbuilds a card, so each explainer can be opened
      // without scrolling. Width stays at the 780px minimum — that is the axis
      // an explainer row can overflow on.
      await pump(tester, size: const Size(780, 6000));
      for (final tab in AllocTab.values) {
        final chip = find.text(tab.label).first;
        await tester.ensureVisible(chip);
        await tester.pumpAndSettle();
        await tester.tap(chip);
        await tester.pumpAndSettle();

        // Re-found every round: expanding one explainer moves the others.
        // Bounded rather than while-empty so a missed tap cannot spin forever.
        var opened = 0;
        for (var i = 0; i < 20; i++) {
          final toggles = find.text('How to read');
          if (toggles.evaluate().isEmpty) break;
          await tester.tap(toggles.first);
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull,
              reason: 'an explainer on "${tab.label}" overflowed at 780px');
          opened++;
        }
        expect(opened, greaterThan(0),
            reason: 'no explainer opened on "${tab.label}"');
        expect(find.text('How to read'), findsNothing,
            reason: 'explainers left unopened on "${tab.label}"');
      }
    });
  });

  group('Headline findings', () {
    testWidgets('surface the worst numbers with jump targets', (tester) async {
      await pump(tester);
      // Overlap of 34.2% and top-5 of 46.2% are both above their thresholds.
      expect(find.text('34.2%'), findsWidgets);
      expect(find.text('46.2%'), findsWidgets);
    });

    testWidgets('clicking a finding jumps to its section', (tester) async {
      await pump(tester);
      expect(find.text('Portfolio Overlap'), findsNothing);
      await tester.tap(find.text('FUND OVERLAP'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Portfolio Overlap'), findsOneWidget);
    });

    testWidgets('never shows more than four cards', (tester) async {
      await pump(tester);
      final labels = [
        'TOP 5 CONCENTRATION',
        'FUND OVERLAP',
        'TOP SECTOR',
        'LARGEST DRIFT',
        'DIVIDEND GOAL',
        'YIELD TRAP FLAGGED',
      ];
      final shown =
          labels.where((l) => find.text(l).evaluate().isNotEmpty).length;
      expect(shown, lessThanOrEqualTo(4));
      expect(shown, greaterThan(0));
    });
  });

  group('Degraded backend', () {
    testWidgets('exposure failure falls back without breaking the header',
        (tester) async {
      await pump(tester, exposureFails: true);
      expect(tester.takeException(), isNull);
      expect(find.textContaining('Advanced exposure analysis unavailable'),
          findsOneWidget);
      // The summary bar still renders.
      expect(find.text('PORTFOLIO VALUE'), findsOneWidget);
    });

    testWidgets('the dividend tab works even when exposure is down',
        (tester) async {
      await pump(tester, exposureFails: true);
      await tester.tap(find.text('Dividend Income').first);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('The Ledger'), findsOneWidget);
    });

    testWidgets('an empty exposure payload does not crash any tab',
        (tester) async {
      await pump(tester, exposure: ExposureAnalysis.empty);
      for (final tab in AllocTab.values) {
        await tester.tap(find.text(tab.label).first);
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull,
            reason: 'tab "${tab.label}" threw on empty exposure');
      }
    });
  });
}
