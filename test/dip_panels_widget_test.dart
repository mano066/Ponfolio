import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:aiei_wealth/core/theme/app_theme.dart';
import 'package:aiei_wealth/data/models/dip_models.dart';
import 'package:aiei_wealth/presentation/widgets/deploy/dip_backtest_card.dart';
import 'package:aiei_wealth/presentation/widgets/deploy/fund_dip_card.dart';
import 'package:aiei_wealth/presentation/widgets/deploy/stock_dip_card.dart';
import 'package:aiei_wealth/providers/deploy_provider.dart';
import 'package:aiei_wealth/providers/providers.dart';

/// Widget tests for the dip panels.
///
/// These pin the renderings where a mistake would actively mislead someone
/// about their own money: a blocked holding must never read as a buy, a fall
/// that a corporate action explains must never read as a verdict, and a
/// threshold that lost to the baseline must say so on screen rather than
/// showing a flattering absolute return on its own.
/// Takes the boards directly rather than a `List<Override>`: Riverpod's
/// `Override` is a sealed, non-exported type, so a test cannot name it — which
/// is why the other widget tests in this suite build their override lists
/// inline too.
Future<void> _pump(
  WidgetTester tester,
  Widget child, {
  StockDipBoard? stocks,
  FundDipBoard? funds,
  DipBacktest? backtest,
  double width = 1500,
}) async {
  tester.view.physicalSize = Size(width, 2400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);

  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        if (stocks != null)
          stockDipsProvider.overrideWith((ref) => Stream.value(stocks)),
        if (funds != null) fundDipsProvider.overrideWith((ref) => Stream.value(funds)),
        if (backtest != null)
          dipBacktestProvider.overrideWith((ref) async => backtest),
      ],
      child: MaterialApp(
        theme: AppTheme.dark(),
        home: Scaffold(
          body:
              SingleChildScrollView(child: SizedBox(width: width, child: child)),
        ),
      ),
    ),
  );
  await tester.pump();
}

// ── fixtures ──────────────────────────────────────────────────────────────

Map<String, dynamic> _stock({
  String symbol = 'WIPRO.NS',
  String name = 'Wipro',
  double? price = 175.7,
  double? drawdown = 33.2,
  double? benchDd = 21.2,
  double? excess = 12.0,
  double? score = 72.0,
  double confidence = 100,
  String reason = 'company_soft',
  String action = 'consider',
  bool blocked = false,
  bool corporateAction = false,
  List<String> flags = const [],
  List<String> severeHeadlines = const [],
}) =>
    {
      'symbol': symbol,
      'name': name,
      'price': price,
      'avg_cost': 200.0,
      'drawdown_pct': drawdown,
      'benchmark_label': 'IT',
      'benchmark_drawdown_pct': benchDd,
      'score': score,
      'confidence': confidence,
      'low_confidence': confidence < 45,
      'factors': const {'drawdown': 71.4, 'valuation': 40.0},
      'reason_for_fall': {
        'reason': reason,
        'label': switch (reason) {
          'market_wide' => 'Falling with its market',
          'deterioration' => 'Fundamentals deteriorating',
          'corporate_action' => 'Corporate action — figures not like-for-like',
          'unknown' => 'Not enough information',
          _ => 'Company-specific, no damage visible',
        },
        'emoji': '•',
        'why': 'because of reasons',
        'excess_drawdown_pp': excess,
        'deterioration_flags': flags,
        'news': {'checked': 3, 'severe_headlines': severeHeadlines},
      },
      'averaging_blocked': blocked,
      'corporate_action_suspected': corporateAction,
      'action': action,
      'action_label': switch (action) {
        'do_not_average' => 'Do not average down',
        'accumulate' => 'Strong accumulation candidate',
        'consider' => 'Consider accumulating',
        _ => 'Watch / small buy only',
      },
      'action_emoji': '•',
    };

StockDipBoard _stockBoard(List<Map<String, dynamic>> stocks) =>
    StockDipBoard.fromJson({
      'as_of': '2026-09-04',
      'stocks': stocks,
      'blocked_count': stocks.where((s) => s['averaging_blocked'] == true).length,
      'corporate_action_count':
          stocks.where((s) => s['corporate_action_suspected'] == true).length,
      'valuation_note': 'No feed carries historical index P/E.',
      'sector_pe_available': false,
    });

FundDipBoard _fundBoard({
  bool reached = false,
  double edge = 1.9,
  bool reliable = true,
  String? caution,
}) =>
    FundDipBoard.fromJson({
      'as_of': '2026-09-04',
      'funds': [
        {
          'scheme_name': 'Parag Parikh Flexi Cap',
          'category': 'Flexi Cap Fund',
          'nav': 90.5,
          'benchmark': '^CRSLDX',
          'benchmark_label': 'Nifty 500',
          'benchmark_drawdown_pct': 3.6,
          'peak_nav': 95.77,
          'peak_is_purchase_high': false,
          'purchase': {
            'buys': 8,
            'lowest_buy_nav': 86.51,
            'highest_buy_nav': 93.76,
            'weighted_avg_nav': 90.48,
            'high_low_ratio': 1.0837,
          },
          'position': {
            'label': 'Above your weighted average',
            'vs_avg_pct': 0.03,
            'caution': caution,
          },
          'zones': [
            {
              'zone': 'good',
              'label': 'Good buy zone',
              'depth_pct': 10.0,
              'nav_at_or_below': 86.2,
              'reached': reached,
              'distance_pct': 4.99,
              'evidence': {
                'tested': true,
                'reliable': reliable,
                'signals': reliable ? 12 : 2,
                'forward_mean_pct': 20.0,
                'edge_pp': edge,
                'note': reliable
                    ? (edge > 0
                        ? 'Beat buying on a random day by +6.7pp over 1y across 12 episodes.'
                        : 'Did NOT beat buying on a random day (-9.5pp over 1y, 12 episodes).')
                    : 'Only 2 separate episode(s) in 9.8 years — too few to rely on.',
              },
            },
          ],
          'next_trigger': {
            'label': 'Good buy zone',
            'nav_at_or_below': 86.2,
            'fall_needed_pct': 4.8,
          },
        }
      ],
    });

DipBacktest _backtest({double edge = -2.5, int signals = 20}) =>
    DipBacktest.fromJson({
      'as_of': '2026-09-04',
      'horizons': const ['3m', '6m', '1y', '3y', '5y'],
      'min_signals_for_reliable': 5,
      'studies': [
        {
          'symbol': '^NSEI',
          'label': 'NIFTY 50',
          'status': 'ok',
          'years': 9.8,
          'current_drawdown_pct': 9.2,
          'active_threshold_pct': 5.0,
          'best_threshold_pct': 10.0,
          'history': {'dropped': 0},
          'baseline': {
            '1y': {'n': 2212, 'mean_pct': 13.3, 'positive_rate_pct': 84.0}
          },
          'thresholds': [
            {
              'threshold_pct': 5.0,
              'signals': signals,
              'reliable': signals >= 5,
              'forward': {
                '1y': {'n': 19, 'mean_pct': 10.8, 'positive_rate_pct': 84.0}
              },
              'edge': {
                '1y': {'mean_pp': edge}
              },
            }
          ],
        }
      ],
    });

// ══════════════════════════════════════════════════════════════
//  STOCK PANEL
// ══════════════════════════════════════════════════════════════

void main() {
  group('StockDipCard', () {
    testWidgets('a blocked holding never renders as a buy', (tester) async {
      // The failure this whole panel exists to prevent: a holding 45% off its
      // high with a high score that must NOT be averaged into.
      await _pump(
        tester,
        const StockDipCard(),
        stocks: _stockBoard([
                _stock(
                  symbol: 'ITC.NS',
                  name: 'ITC',
                  drawdown: 35.4,
                  excess: 15.9,
                  score: 65,
                  reason: 'deterioration',
                  action: 'do_not_average',
                  blocked: true,
                  flags: const ['Earnings shrinking (-16.0%)'],
                ),
              ]),
      );
      await tester.pump();

      expect(find.text('DO NOT AVERAGE DOWN'), findsOneWidget);
      expect(find.textContaining('Earnings shrinking'), findsOneWidget);
      expect(find.text('1 BLOCKED'), findsOneWidget);
      // The score is shown but must not be the instruction.
      expect(find.text('65'), findsOneWidget);
    });

    testWidgets('a corporate action asks for a manual check, not a verdict',
        (tester) async {
      await _pump(
        tester,
        const StockDipCard(),
        stocks: _stockBoard([
                _stock(
                  symbol: 'VEDL.NS',
                  name: 'Vedanta',
                  drawdown: 66.0,
                  excess: 62.0,
                  score: 78,
                  reason: 'corporate_action',
                  action: 'watch',
                  corporateAction: true,
                ),
              ]),
      );
      await tester.pump();

      expect(find.text('CHECK BY HAND'), findsOneWidget);
      expect(find.text('DO NOT AVERAGE DOWN'), findsNothing);
      expect(find.text('STRONG ACCUMULATION CANDIDATE'), findsNothing);
    });

    testWidgets('a missing benchmark reads as unknown, not as zero excess',
        (tester) async {
      // Null excess must never render as "0.0pp", which would say the market
      // fully explains a fall nobody measured.
      await _pump(
        tester,
        const StockDipCard(),
        stocks: _stockBoard([
                _stock(excess: null, benchDd: null),
              ]),
      );
      await tester.pump();

      expect(find.text('no bench'), findsOneWidget);
      expect(find.textContaining('0.0pp'), findsNothing);
    });

    testWidgets('a holding with no price shows so and is not recommended',
        (tester) async {
      await _pump(
        tester,
        const StockDipCard(),
        stocks: _stockBoard([
                _stock(
                    price: null,
                    drawdown: null,
                    score: 83,
                    action: 'watch',
                    reason: 'unknown'),
              ]),
      );
      await tester.pump();

      expect(find.text('no price'), findsOneWidget);
      expect(find.text('STRONG ACCUMULATION CANDIDATE'), findsNothing);
    });

    testWidgets('the unavailable-valuation note is stated, not hidden',
        (tester) async {
      await _pump(
        tester,
        const StockDipCard(),
        stocks: _stockBoard([_stock()]),
      );
      await tester.pump();
      expect(find.textContaining('historical index P/E'), findsOneWidget);
    });

    testWidgets('an empty board says so rather than rendering zeros',
        (tester) async {
      await _pump(
        tester,
        const StockDipCard(),
        stocks: StockDipBoard.empty,
      );
      await tester.pump();
      expect(find.text('No stock analysis yet'), findsOneWidget);
    });
  });

  // ══════════════════════════════════════════════════════════════
  //  FUND PANEL
  // ══════════════════════════════════════════════════════════════

  group('FundDipCard', () {
    testWidgets('a zone that lost to the baseline says so on screen',
        (tester) async {
      // A zone must be allowed to argue against itself; hiding a negative edge
      // would turn the panel into an advocate.
      await _pump(
        tester,
        const FundDipCard(),
        funds: _fundBoard(edge: -9.5),
      );
      await tester.pump();
      expect(find.textContaining('Did NOT beat'), findsOneWidget);
    });

    testWidgets('thin evidence is labelled rather than presented as a reason',
        (tester) async {
      await _pump(
        tester,
        const FundDipCard(),
        funds: _fundBoard(reliable: false),
      );
      await tester.pump();
      expect(find.textContaining('too few to rely on'), findsOneWidget);
    });

    testWidgets('the purchase-price caution is shown verbatim', (tester) async {
      await _pump(
        tester,
        const FundDipCard(),
        funds: _fundBoard(
              caution: 'This compares today\'s NAV with what you paid before.'),
      );
      await tester.pump();
      expect(find.textContaining('what you paid before'), findsOneWidget);
    });

    testWidgets('the next trigger names a level and the fall needed',
        (tester) async {
      await _pump(
        tester,
        const FundDipCard(),
        funds: _fundBoard(),
      );
      await tester.pump();
      expect(find.textContaining('Next: Good buy zone at 86.20'), findsOneWidget);
    });

    testWidgets('reaching a zone is reflected in the header', (tester) async {
      await _pump(
        tester,
        const FundDipCard(),
        funds: _fundBoard(reached: true),
      );
      await tester.pump();
      expect(find.text('1 IN ZONE'), findsOneWidget);
    });
  });

  // ══════════════════════════════════════════════════════════════
  //  BACKTEST PANEL
  // ══════════════════════════════════════════════════════════════

  group('DipBacktestCard', () {
    testWidgets('the baseline is shown beside every forward return',
        (tester) async {
      // The single design rule of this card: a forward return with no null
      // beside it is not evidence.
      await _pump(
        tester,
        const DipBacktestCard(symbols: ['^NSEI']),
        backtest: _backtest(),
      );
      await tester.pump();

      expect(find.text('+10.8%'), findsOneWidget);   // the signal
      expect(find.text('+13.3%'), findsOneWidget);   // buying on any day
      expect(find.text('-2.5pp'), findsOneWidget);   // the edge
    });

    testWidgets('a negative edge reads as no better than any day',
        (tester) async {
      await _pump(
        tester,
        const DipBacktestCard(symbols: ['^NSEI']),
        backtest: _backtest(edge: -2.5),
      );
      await tester.pump();
      expect(find.text('No better than any day'), findsOneWidget);
      expect(find.text('Beat buying any day'), findsNothing);
    });

    testWidgets('a positive edge on enough episodes reads as a beat',
        (tester) async {
      await _pump(
        tester,
        const DipBacktestCard(symbols: ['^NSEI']),
        backtest: _backtest(edge: 1.9),
      );
      await tester.pump();
      expect(find.text('Beat buying any day'), findsOneWidget);
    });

    testWidgets('a threshold with too few episodes is refused, however good',
        (tester) async {
      // n=1 with a spectacular edge is the classic overfit. It must be shown
      // and simultaneously disqualified.
      await _pump(
        tester,
        const DipBacktestCard(symbols: ['^NSEI']),
        backtest: _backtest(edge: 40.2, signals: 1),
      );
      await tester.pump();

      expect(find.text('Too few episodes to rely on'), findsOneWidget);
      expect(find.text('Beat buying any day'), findsNothing);
    });

    testWidgets('the drawdown the index is in today is marked', (tester) async {
      await _pump(
        tester,
        const DipBacktestCard(symbols: ['^NSEI']),
        backtest: _backtest(),
      );
      await tester.pump();
      expect(find.textContaining('HERE NOW'), findsOneWidget);
    });
  });

  // ══════════════════════════════════════════════════════════════
  //  GUEST MODE
  // ══════════════════════════════════════════════════════════════

  group('guest mode', () {
    /// A guest session must not be shown an analysis of somebody's holdings
    /// just because the backend still has a portfolio loaded. The two
    /// portfolio-derived providers are gated exactly like deployBoardProvider;
    /// the backtest is not, because it is public market history.
    ///
    /// Written without a shared generic helper: Riverpod's `ProviderListenable`
    /// is not exported, the same reason `Override` cannot be named above.
    ProviderContainer _guestContainer() {
      final container = ProviderContainer(overrides: [
        isGuestProvider.overrideWith(() => _AlwaysGuest()),
      ]);
      addTearDown(container.dispose);
      return container;
    }

    /// Polls the emitted AsyncValue instead of awaiting `.future`.
    ///
    /// These became StreamProviders when the dashboard moved onto an hourly
    /// clock; awaiting `.future` on one hung for the full 30s test timeout.
    /// Written out twice rather than behind a generic helper because
    /// Riverpod's `ProviderListenable` is not exported, so the helper cannot
    /// name its own parameter type.
    Future<void> _settle(ProviderContainer c, bool Function() done) async {
      for (var i = 0; i < 60 && !done(); i++) {
        await Future<void>.delayed(const Duration(milliseconds: 5));
      }
    }

    test('stock dips are empty for a guest', () async {
      final c = _guestContainer();
      c.listen(stockDipsProvider, (_, __) {}, fireImmediately: true);
      await _settle(c, () => !c.read(stockDipsProvider).isLoading);
      final v = c.read(stockDipsProvider);
      expect(v.hasError, isFalse);
      expect(v.value!.isEmpty, isTrue);
    });

    test('fund dips are empty for a guest', () async {
      final c = _guestContainer();
      c.listen(fundDipsProvider, (_, __) {}, fireImmediately: true);
      await _settle(c, () => !c.read(fundDipsProvider).isLoading);
      final v = c.read(fundDipsProvider);
      expect(v.hasError, isFalse);
      expect(v.value!.isEmpty, isTrue);
    });
  });

  // ══════════════════════════════════════════════════════════════
  //  COLUMN LAYOUT
  // ══════════════════════════════════════════════════════════════

  group('column collision', () {
    /// Caught on the running dashboard at 1936px: DenseRow lays its cells out
    /// as bare Expanded flexes with no gap, so the right-aligned SCORE column
    /// butted straight into the left-aligned WHY column. The header read
    /// "SCOREWHY IT IS DOWN" and the cells ran together as
    /// "40% confNo price history for this holding."
    /// Measures the COLUMN HEADERS. That is what visibly collided, and it is
    /// the honest probe: the body cells happen to carry an emoji or an icon at
    /// the start of the reason text, which fakes a gap and would let a broken
    /// layout pass. Header labels sit flush against their column edges with
    /// nothing between them, so they collide the moment the spacer is gone.
    testWidgets('SCORE never touches WHY IT IS DOWN', (tester) async {
      await _pump(
        tester,
        const StockDipCard(),
        stocks: _stockBoard([_stock(score: 86, confidence: 40)]),
        width: 1936,
      );
      await tester.pump();

      final score = tester.getRect(find.text('SCORE'));
      final why = tester.getRect(find.text('WHY IT IS DOWN'));
      expect(why.left - score.right, greaterThan(8.0),
          reason: 'SCORE and WHY IT IS DOWN headers render flush together');
    });

    testWidgets('a right-aligned sub-label clears the reason text',
        (tester) async {
      // The other half of what was on screen: "40% confNo price history..."
      await _pump(
        tester,
        const StockDipCard(),
        stocks: _stockBoard([
          _stock(
              price: null,
              drawdown: null,
              score: 83,
              confidence: 40,
              reason: 'unknown',
              action: 'watch')
        ]),
        width: 1936,
      );
      await tester.pump();

      final conf = tester.getRect(find.text('40% conf'));
      final why = tester.getRect(find.text('Not enough information'));
      expect(why.left - conf.right, greaterThan(8.0));
    });

    testWidgets('EDGE never touches VERDICT', (tester) async {
      await _pump(
        tester,
        const DipBacktestCard(symbols: ['^NSEI']),
        backtest: _backtest(edge: -2.5),
        width: 1936,
      );
      await tester.pump();

      final edge = tester.getRect(find.text('EDGE'));
      final verdict = tester.getRect(find.text('VERDICT'));
      expect(verdict.left - edge.right, greaterThan(8.0),
          reason: 'EDGE and VERDICT headers render flush together');
    });
  });
}

/// Forces guest mode regardless of stored preferences.
class _AlwaysGuest extends IsGuestNotifier {
  @override
  bool build() => true;
}
