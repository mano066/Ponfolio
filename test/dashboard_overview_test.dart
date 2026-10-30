import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/core/constants.dart';
import 'package:aiei_wealth/core/theme/app_theme.dart';
import 'package:aiei_wealth/data/models/dashboard_snapshot.dart';
import 'package:aiei_wealth/data/models/deploy_models.dart';
import 'package:aiei_wealth/presentation/widgets/dashboard_overview.dart';

void main() {
  for (final loading in [false, true]) {
    testWidgets('populated narrow dashboard loading=$loading stays usable', (tester) async {
      tester.view.physicalSize = const Size(375, 850);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(body: DashboardOverview(
          now: DateTime.utc(2026, 9, 7, 12),
          loading: loading,
          snapshot: DashboardSnapshot(
            equity: {'last_updated': '2026-09-07T11:59:00Z', 'holdings': [
              {'symbol': 'TEST', 'name': 'Test fixture only', 'invested': 1000,
                'total_value': 1200, 'current_price': 120, 'avg_cost': 100}
            ]},
            funds: {'last_updated': '2026-09-07T11:59:00Z', 'funds': [
              {'scheme_name': 'Test fixture fund', 'category': 'Small Cap',
                'invested': 500, 'current_value': 600}
            ]},
            targets: {'Small Cap': 20, 'Large Cap': 80},
          ),
          expenses: DashboardExpense(),
          tape: const AsyncLoading(),
          fundDips: const AsyncData(null), stockDips: const AsyncData(null),
          kite: const AsyncData({'connection_state': 'authentication_required'}),
          onNavigate: (_) {}, onRefresh: () {},
        )),
      ));
      for (var i = 0; i < 20; i++) {
        await tester.drag(find.byType(ListView).first, const Offset(0, -500));
        await tester.pump();
        expect(tester.takeException(), isNull);
      }
      expect(find.text('CONNECTION & DATA HEALTH'), findsOneWidget);
    });
  }
  for (final width in [375.0, 768.0, 1440.0]) {
    for (final dark in [true, false]) {
      testWidgets('dashboard $width dark=$dark supports scroll, offline and navigation', (tester) async {
        tester.view.physicalSize = Size(width, 850);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        AppTab? selected;
        var refreshed = false;
        await tester.pumpWidget(MaterialApp(
          theme: dark ? AppTheme.dark() : AppTheme.light(),
          home: Scaffold(body: MediaQuery(
            data: MediaQueryData(size: Size(width,850), textScaler: const TextScaler.linear(1.5),
              disableAnimations: true),
            child: DashboardOverview(
              snapshot: DashboardSnapshot(), expenses: DashboardExpense(),
              now: DateTime(2026,9,7), failed: true,
              tape: const AsyncData(MarketTape.empty),
              fundDips: const AsyncData(null), stockDips: const AsyncData(null),
              kite: AsyncError(StateError('offline'), StackTrace.empty),
              onNavigate: (tab) => selected = tab, onRefresh: () => refreshed = true,
            ),
          )),
        ));
        await tester.pump();
        expect(find.text('TODAY’S ACTION BAR'), findsOneWidget);
        await tester.tap(find.text('Review').last);
        expect(selected, AppTab.settings);
        for (var i=0;i<17;i++) {
          await tester.drag(find.byType(ListView).first, const Offset(0,-650));
          await tester.pump();
          expect(tester.takeException(), isNull);
        }
        expect(find.text('CONNECTION & DATA HEALTH'), findsOneWidget);
        await tester.tap(find.text('Refresh dashboard'));
        expect(refreshed, isTrue);
        expect(find.text('Kite: Error — retry available'), findsOneWidget);
      });
    }
  }
}
