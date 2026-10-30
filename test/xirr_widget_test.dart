import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_theme.dart';
import 'package:aiei_wealth/data/models/closed_positions.dart';
import 'package:aiei_wealth/providers/providers.dart';
import 'package:aiei_wealth/presentation/screens/equities_screen.dart';

/// Covers the XIRR column and tiles added to the dashboard and equities views.
///
/// Two things are being pinned down. First, that a null XIRR renders as an
/// em-dash rather than a fabricated 0% — the backend returns null whenever no
/// dated trades back a position, and a 0% in that cell would read as a real
/// result. Second, that the extra column still fits: these tables are dense
/// Rows of Expanded cells, so an added column overflows silently at the app's
/// real minimum content width unless it is pumped there.
void main() {
  // The narrowest the app's content area actually gets. Wider windows have
  // slack; this is where a column too many first bites.
  const minContentWidth = 780.0;

  Map<String, dynamic> holding(String sym,
          {num? xirr, bool xirrExact = true, double value = 40000}) =>
      {
        'symbol': sym,
        'name': sym,
        'sector': 'Energy',
        'shares': 100,
        'avg_cost': 380.0,
        'current_price': 400.0,
        'ltp': 400.0,
        'invested': 38000.0,
        'total_value': value,
        'pnl': value - 38000.0,
        'net_chg': 5.26,
        'day_chg': 0.84,
        'xirr': xirr,
        'xirr_exact': xirrExact,
      };

  Map<String, dynamic> portfolioFixture({double? totalXirr}) => {
        'total_portfolio_value': 120000.0,
        'total_invested': 114000.0,
        'total_pnl': 6000.0,
        'total_pnl_pct': 5.26,
        'total_xirr': totalXirr,
        'xirr_covered_pct': totalXirr == null ? 0.0 : 66.7,
        'holdings': [
          holding('EXACTSTOCK', xirr: 18.4),
          holding('PARTIALSTOCK', xirr: 11.2, xirrExact: false),
          holding('NOHISTORYSTOCK'),
        ],
        'kite_connected': true,
        'data_source': 'kite',
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
        'total_xirr': 14.2,
      };

  Map<String, dynamic> xirrFixture({
    double? equity = 15.3,
    double? mf = 14.2,
    double? combined = 14.6,
  }) =>
      {
        'equity': {'xirr': equity, 'covered_pct': equity == null ? 0.0 : 66.7},
        'mutual_funds': {'xirr': mf, 'covered_pct': mf == null ? 0.0 : 100.0},
        'combined': {'xirr': combined, 'covered_pct': combined == null ? 0.0 : 84.0},
      };

  Future<void> pump(
    WidgetTester tester,
    Widget screen, {
    Size size = const Size(1700, 1300),
    double? totalXirr = 15.3,
    Map<String, dynamic>? xirr,
  }) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          livePriceProvider.overrideWith((ref) => const Stream.empty()),
          portfolioProvider
              .overrideWith((ref) async => portfolioFixture(totalXirr: totalXirr)),
          mfPortfolioProvider.overrideWith((ref) async => mfFixture()),
          portfolioXirrProvider.overrideWith((ref) async => xirr ?? xirrFixture()),
          niftyProvider.overrideWith(
              (ref) => Stream.value({'last_price': 24500.0, 'change_pct': 0.42})),
          aiSignalsProvider
              .overrideWith((ref) => Stream.value(<String, dynamic>{'signals': {}})),
          // The screen also renders the realised book below the holdings.
          // Left live, it fires a real request and the test fails at
          // teardown with a pending timer rather than on an assertion.
          closedPositionsProvider.overrideWith((ref) async => const ClosedBook()),
        ],
        child: MaterialApp(
          theme: AppTheme.dark(),
          home: Scaffold(
            body: Padding(padding: const EdgeInsets.all(16), child: screen),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  group('formatXirr', () {
    test('a null rate is a dash, never a zero', () {
      expect(formatXirr(null), '—');
      // 0% is a real answer for a flat position and must survive intact.
      expect(formatXirr(0), '+0.0%');
    });

    test('an inexact rate is marked with a tilde', () {
      expect(formatXirr(11.2, exact: false), '~+11.2%');
      expect(formatXirr(11.2), '+11.2%');
    });

    test('negative rates keep their sign', () {
      expect(formatXirr(-8.4), '-8.4%');
    });
  });

  group('xirrOf', () {
    test('reads the value and the exactness flag off a holding', () {
      expect(xirrOf({'xirr': 18.4, 'xirr_exact': true}), (18.4, true));
      expect(xirrOf({'xirr': 11.2, 'xirr_exact': false}), (11.2, false));
    });

    test('a missing or non-numeric xirr comes back null, not zero', () {
      expect(xirrOf({}).$1, isNull);
      expect(xirrOf({'xirr': null}).$1, isNull);
      expect(xirrOf({'xirr': 'n/a'}).$1, isNull);
    });

    test('defaults to exact when the backend omits the flag', () {
      expect(xirrOf({'xirr': 9.0}).$2, isTrue);
    });
  });

  // The 'DashboardScreen XIRR' group was removed when the dashboard became the
  // Deploy Desk. It asserted on a net-worth summary bar and a holdings table
  // that no longer exist there — those numbers now live only on the Equities and
  // Mutual Funds tabs, which the groups below still cover. The dash-not-zero
  // discipline it protected is retained by 'an empty ledger shows the dash and
  // says why' below, and by test/deploy_model_test.dart for the new screen.

  group('EquitiesScreen XIRR', () {
    testWidgets('adds an XIRR tile and column', (tester) async {
      await pump(tester, const EquitiesScreen());
      expect(tester.takeException(), isNull);
      expect(find.text('XIRR'), findsWidgets);
      expect(find.text('annualised · 67% of book'), findsOneWidget);
      // NET% stays, relabelled in the tile as absolute so the pair reads clearly.
      expect(find.text('NET%'), findsOneWidget);
      expect(find.text('absolute'), findsOneWidget);
    });

    testWidgets('an empty ledger shows the dash and says why', (tester) async {
      await pump(tester, const EquitiesScreen(), totalXirr: null);
      expect(tester.takeException(), isNull);
      expect(find.text('no trade history'), findsOneWidget);
    });

    testWidgets('fits at the minimum content width', (tester) async {
      await pump(tester, const EquitiesScreen(),
          size: const Size(minContentWidth, 1300));
      expect(tester.takeException(), isNull,
          reason: 'the XIRR column overflows the dense equity table');
    });
  });
}
