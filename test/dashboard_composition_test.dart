import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:aiei_wealth/core/theme/app_theme.dart';
import 'package:aiei_wealth/data/models/deploy_models.dart';
import 'package:aiei_wealth/data/models/dip_models.dart';
import 'package:aiei_wealth/presentation/screens/dashboard_screen.dart';
import 'package:aiei_wealth/presentation/widgets/deploy/market_tape_strip.dart';
import 'package:aiei_wealth/presentation/widgets/deploy/opportunity_cards.dart';
import 'package:aiei_wealth/presentation/widgets/deploy/todays_opportunities_bar.dart';
import 'package:aiei_wealth/providers/allocation_provider.dart';
import 'package:aiei_wealth/providers/deploy_provider.dart';
import 'package:aiei_wealth/providers/expense_provider.dart';
import 'package:aiei_wealth/data/models/conviction_models.dart';
import 'package:aiei_wealth/providers/conviction_provider.dart';
import 'package:aiei_wealth/providers/providers.dart';

/// The dashboard carries two halves that were previously separate releases:
/// v1.4.3's decision widgets (opportunities, tape, funds, stocks) and the
/// four standing-position sections added in v1.4.4. These tests assert both
/// halves render TOGETHER, in decision-first order, and that composing them
/// does not overflow — the failure mode of stacking two dashboards is a
/// RenderFlex assertion at paint time, which analysis cannot see.

class _NotGuest extends IsGuestNotifier {
  @override
  bool build() => false;
}

class _Guest extends IsGuestNotifier {
  @override
  bool build() => true;
}

class _FakeOtherAssets extends OtherAssetsNotifier {
  @override
  Map<String, double> build() => const {'Gold': 50000};
}

class _FakeExpenses extends ExpenseStore {
  @override
  ExpenseState build() => const ExpenseState(lastSavedIso: '2026-09-07T10:00:00Z');
}

Future<void> _pump(WidgetTester tester, {bool guest = false, double width = 1500}) async {
  tester.view.physicalSize = Size(width, 2000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);

  await tester.pumpWidget(ProviderScope(
    overrides: [
      isGuestProvider.overrideWith(guest ? _Guest.new : _NotGuest.new),
      otherAssetsProvider.overrideWith(_FakeOtherAssets.new),
      expenseStoreProvider.overrideWith(_FakeExpenses.new),
      targetAllocationProvider.overrideWithValue(
        const {'Large Cap': 50.0, 'Small Cap': 20.0, 'Gold': 30.0},
      ),
      livePriceProvider.overrideWith((ref) => const Stream.empty()),
      convictionBoardProvider.overrideWith((ref) async => ConvictionBoard.empty),
      portfolioProvider.overrideWith((ref) async => {
            'last_updated': DateTime.now().toUtc().toIso8601String(),
            'holdings': [
              {'symbol': 'TEST', 'name': 'Test fixture only', 'invested': 1000,
                'total_value': 1200, 'current_price': 120, 'avg_cost': 100},
            ],
          }),
      mfPortfolioProvider.overrideWith((ref) async => {
            'last_updated': DateTime.now().toUtc().toIso8601String(),
            'funds': [
              {'scheme_name': 'Test fixture fund', 'category': 'Small Cap',
                'invested': 500, 'current_value': 600},
            ],
          }),
      portfolioXirrProvider.overrideWith((ref) async => const {
            'combined': {'xirr': 12.5, 'covered_pct': 100},
          }),
      kiteStatusProvider.overrideWith(
          (ref) => Stream.value(const {'connection_state': 'connected'})),
      // All four decision providers are always overridden: leaving one live
      // sends a real request from a widget test and fails at teardown.
      marketTapeProvider.overrideWith((ref) => Stream.value(MarketTape.empty)),
      opportunitiesProvider
          .overrideWith((ref) => Stream.value(OpportunityBoard.empty)),
      fundDipsProvider.overrideWith((ref) => Stream.value(FundDipBoard.empty)),
      stockDipsProvider.overrideWith((ref) => Stream.value(StockDipBoard.empty)),
    ],
    child: MaterialApp(
      theme: AppTheme.light(),
      home: const Scaffold(body: DashboardScreen()),
    ),
  ));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 600));
}

void main() {
  testWidgets('signed in, both dashboard halves are present', (tester) async {
    await _pump(tester);

    // v1.4.3's decision widgets, not the overview's own thinner readings.
    expect(find.byType(TodaysOpportunitiesBar), findsOneWidget);
    expect(find.byType(MarketTapeStrip), findsOneWidget);
    expect(find.byType(FundOpportunitySection), findsOneWidget);
    expect(find.byType(StockOpportunitySection), findsOneWidget);
    // The slots replace, never duplicate: the built-in headings are gone.
    expect(find.text('MARKET PULSE'), findsNothing);
    expect(find.text('MUTUAL FUND OPPORTUNITIES'), findsNothing);
    expect(find.text('EQUITY OPPORTUNITIES'), findsNothing);

    // The four sections asked for on top of the v1.4.3 layout.
    for (final title in [
      'TODAY’S ACTION BAR',
      'PORTFOLIO SUMMARY',
      'ALLOCATION HEALTH',
      'EXPENSE & SAVINGS SNAPSHOT',
    ]) {
      await tester.scrollUntilVisible(find.text(title), 400,
          scrollable: find.byType(Scrollable).first);
      expect(find.text(title), findsOneWidget, reason: '$title must be on the dashboard');
    }
  });

  testWidgets('decisions rank above the standing position', (tester) async {
    await _pump(tester);
    double y(Finder f) => tester.getTopLeft(f).dy;

    // The action bar answers "what needs me today", so it stays on top, and
    // nothing that merely describes the portfolio outranks the opportunities.
    expect(y(find.text('TODAY’S ACTION BAR')),
        lessThan(y(find.byType(TodaysOpportunitiesBar))));
    expect(y(find.byType(TodaysOpportunitiesBar)),
        lessThan(y(find.byType(MarketTapeStrip))));
    expect(y(find.byType(MarketTapeStrip)),
        lessThan(y(find.byType(FundOpportunitySection))));
    expect(y(find.byType(FundOpportunitySection)),
        lessThan(y(find.byType(StockOpportunitySection))));
  });

  for (final width in [375.0, 768.0, 1500.0]) {
    testWidgets('composed dashboard scrolls clean at $width', (tester) async {
      await _pump(tester, width: width);
      for (var i = 0; i < 20; i++) {
        await tester.drag(find.byType(Scrollable).first, const Offset(0, -450));
        await tester.pump();
        expect(tester.takeException(), isNull);
      }
      expect(find.text('CONNECTION & DATA HEALTH'), findsOneWidget);
    });
  }

  testWidgets('a guest keeps the public tape and loses holdings widgets',
      (tester) async {
    await _pump(tester, guest: true);
    expect(find.byType(MarketTapeStrip), findsOneWidget);
    expect(find.byType(TodaysOpportunitiesBar), findsNothing);
    expect(find.byType(FundOpportunitySection), findsNothing);
    expect(find.byType(StockOpportunitySection), findsNothing);
    expect(find.text('Sign in to review your finances'), findsOneWidget);
  });
}
