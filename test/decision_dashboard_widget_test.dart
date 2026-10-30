import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:aiei_wealth/core/theme/app_theme.dart';
import 'package:aiei_wealth/data/models/deploy_models.dart';
import 'package:aiei_wealth/data/models/dip_models.dart';
import 'package:aiei_wealth/presentation/widgets/deploy/market_tape_strip.dart';
import 'package:aiei_wealth/presentation/widgets/deploy/opportunity_cards.dart';
import 'package:aiei_wealth/presentation/widgets/deploy/todays_opportunities_bar.dart';
import 'package:aiei_wealth/providers/deploy_provider.dart';

/// Widget tests for the decision-first dashboard.
///
/// The most valuable ones here are the LAYOUT tests. A RenderFlex assertion
/// only fires at paint time, so `dart analyze` is blind to it and a card can
/// look perfectly correct in source while throwing on every frame — which is
/// exactly what happened: the stock card's score block sat as a non-flex child
/// of a Row, was therefore measured with unbounded width, and contained a
/// Flexible. Pumping each card and asserting no exception is the only thing
/// that catches that.
Future<void> _pump(
  WidgetTester tester,
  Widget child, {
  OpportunityBoard? board,
  FundDipBoard? funds,
  StockDipBoard? stocks,
  MarketTape? tape,
  bool stocksFail = false,
  bool fundsFail = false,
  double width = 1500,
}) async {
  tester.view.physicalSize = Size(width, 2400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);

  await tester.pumpWidget(
    ProviderScope(
      // All three decision providers are ALWAYS overridden, never just the
      // one under test. dashboardRefreshingProvider (which drives the Update
      // button's spinner) watches all three, so leaving one un-overridden
      // sends a real network call from a widget test and fails at teardown
      // with a pending future.
      overrides: [
        opportunitiesProvider.overrideWith(
            (ref) => Stream.value(board ?? OpportunityBoard.empty)),
        if (fundsFail)
          fundDipsProvider.overrideWith(
              (ref) => Stream.error(Exception('backend down')))
        else
          fundDipsProvider.overrideWith(
              (ref) => Stream.value(funds ?? FundDipBoard.empty)),
        if (stocksFail)
          stockDipsProvider.overrideWith(
              (ref) => Stream.error(Exception('backend down')))
        else
          stockDipsProvider.overrideWith(
              (ref) => Stream.value(stocks ?? StockDipBoard.empty)),
        marketTapeProvider
            .overrideWith((ref) => Stream.value(tape ?? MarketTape.empty)),
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
  await tester.pump();
}

// ── fixtures ──────────────────────────────────────────────────────────────

OpportunityBoard _board({
  String status = 'actionable',
  List<Map<String, dynamic>> rows = const [],
  String signal = 'correction',
}) =>
    OpportunityBoard.fromJson({
      'as_of': '2026-09-04T12:31:00',
      'status': status,
      'headline': status == 'quiet' ? 'No strong dip today' : null,
      'detail': status == 'quiet'
          ? 'Nothing currently meets the strategy threshold.'
          : null,
      'market': {
        'signal': signal,
        'label': signal == 'correction' ? 'Correction' : 'High risk',
        'emoji': signal == 'correction' ? '🟠' : '🔴',
        'summary': 'Large caps are 9% off their highs while midcaps are '
            'at their highs.',
        'broad_off_high_pct': 9.0,
      },
      'rows': rows,
      'buy_count': rows.where((r) => r['action'] == 'buy' || r['action'] == 'add').length,
      'risk_count': rows.where((r) => r['action'] == 'avoid').length,
    });

Map<String, dynamic> _row({
  String action = 'add',
  String label = 'ADD',
  String kind = 'fund',
  String name = 'HDFC Silver ETF FoF',
  double? score = 87.4,
  String? why = 'Silver (ETF) is 36.8% off its high',
}) =>
    {
      'action': action,
      'label': label,
      'emoji': action == 'avoid' ? '🔴' : '🟢',
      'kind': kind,
      'key': name,
      'name': name,
      'subtitle': 'Silver',
      'score': score,
      'price': 38.0,
      'price_label': 'NAV',
      'metric': '36.8% off high',
      'why': why,
      'low_confidence': false,
    };

FundDipBoard _funds({double score = 87.4, String action = 'add'}) =>
    FundDipBoard.fromJson({
      'as_of': '2026-09-04',
      'funds': [
        {
          'scheme_name': 'HDFC Silver ETF FoF Growth Direct Plan',
          'category': 'Silver',
          'nav': 38.0,
          'benchmark': 'SILVERBEES.NS',
          'benchmark_label': 'Silver (ETF)',
          'benchmark_drawdown_pct': 36.8,
          'peak_nav': 61.4,
          'score': score,
          'confidence': 75.0,
          'low_confidence': false,
          'action': action,
          'action_label': 'Consider adding',
          'action_emoji': '🟢',
          'deep_fall_risk': true,
          'reasons': [
            'Silver (ETF) is 36.8% off its high',
            'Too few past episodes at this depth to rely on',
            'NAV is 21.0% below your average',
          ],
          'factors': {
            'benchmark_dip': 74.2,
            'backtest_support': null,
            'own_drawdown': 100.0,
            'below_avg_nav': 100.0,
          },
          'purchase': {'buys': 3, 'weighted_avg_nav': 48.12},
          'position': {'label': 'Below everything you have ever paid'},
          'zones': [],
          'next_trigger': {'label': 'Good buy zone', 'nav_at_or_below': 55.25},
        }
      ],
    });

StockDipBoard _stocks({bool blocked = false}) => StockDipBoard.fromJson({
      'as_of': '2026-09-04',
      'stocks': [
        {
          'symbol': 'ITC.NS',
          'name': 'ITC Limited',
          'price': 263.0,
          'avg_cost': 400.0,
          'drawdown_pct': 35.4,
          'benchmark_label': 'FMCG',
          'benchmark_drawdown_pct': 19.5,
          'score': 65.1,
          'confidence': 100.0,
          'low_confidence': false,
          'factors': {
            'drawdown': 87.0,
            'valuation': 40.0,
            'fundamental': 60.0,
            'growth': 0.0,
            'news': 25.0,
          },
          'reason_for_fall': {
            'reason': blocked ? 'deterioration' : 'market_wide',
            'label': blocked
                ? 'Fundamentals deteriorating'
                : 'Falling with its market',
            'emoji': blocked ? '🔴' : '🟢',
            'why': 'because of reasons',
            'excess_drawdown_pp': 15.9,
            'deterioration_flags':
                blocked ? ['Earnings shrinking (-16.0%)'] : <String>[],
            'news': {'checked': 3, 'severe_headlines': <String>[]},
          },
          'averaging_blocked': blocked,
          'corporate_action_suspected': false,
          'action': blocked ? 'do_not_average' : 'consider',
          'action_label':
              blocked ? 'Do not average down' : 'Consider accumulating',
          'action_emoji': blocked ? '🔴' : '🟢',
          'health': blocked ? 'deteriorating' : 'stable',
          'health_label': blocked ? 'Deteriorating' : 'Stable',
          'valuation': 'fair',
          'valuation_label': 'Fair',
          'news_sentiment': 'neutral',
          'news_label': 'Neutral',
          'main_risk': blocked ? 'Earnings shrinking (-16.0%)' : null,
          'reasons': ['35.4% below its 52-week high'],
        }
      ],
      'blocked_count': blocked ? 1 : 0,
      'corporate_action_count': 0,
      'valuation_note': 'No feed carries historical index P/E.',
    });

MarketTape _tape({String status = 'overheated', double off = 0.4}) =>
    MarketTape.fromJson({
      'as_of': '2026-09-04',
      'indices': [
        {
          'symbol': 'NIFTYSMLCAP250.NS',
          'label': 'SMALLCAP 250',
          'group': 'size',
          'status': 'ok',
          'last': 18515.0,
          'day_chg_pct': 0.38,
          'off_high_pct': off,
          'above_low_pct': 30.1,
          'market_status': status,
        }
      ],
      'groups': [
        {'key': 'size', 'label': 'Midcap & smallcap', 'symbols': ['NIFTYSMLCAP250.NS']}
      ],
      'breadth': {'up': 1, 'down': 0, 'available': 1, 'total': 1},
      'market_mood': 'near-high',
      'summary': 'Nifty 50 is 9.0% below its 1-year high.',
    });

void main() {
  // ══════════════════════════════════════════════════════════════
  //  LAYOUT — the class of bug analyze cannot see
  // ══════════════════════════════════════════════════════════════

  group('layout', () {
    testWidgets('the stock section paints without a render exception',
        (tester) async {
      // The regression: the score block was a non-flex child of a Row, so it
      // was measured with unbounded width while containing a Flexible.
      await _pump(tester, const StockOpportunitySection(),
          stocks: _stocks(), width: 1500);
      expect(tester.takeException(), isNull);
    });

    testWidgets('the stock section paints when the holding is blocked',
        (tester) async {
      await _pump(tester, const StockOpportunitySection(),
          stocks: _stocks(blocked: true), width: 1500);
      expect(tester.takeException(), isNull);
    });

    testWidgets('the fund section paints without a render exception',
        (tester) async {
      await _pump(tester, const FundOpportunitySection(),
          funds: _funds(), width: 1500);
      expect(tester.takeException(), isNull);
    });

    testWidgets('the master bar paints without a render exception',
        (tester) async {
      await _pump(tester, const TodaysOpportunitiesBar(),
          board: _board(rows: [_row(), _row(action: 'avoid', label: 'AVOID')]),
          width: 1500);
      expect(tester.takeException(), isNull);
    });

    testWidgets('the market tape paints without a render exception',
        (tester) async {
      await _pump(tester, const MarketTapeStrip(), tape: _tape(), width: 1500);
      expect(tester.takeException(), isNull);
    });

    // Split rather than pumped twice in one test: Riverpod refuses to change
    // WHICH providers a scope overrides between pumps, so a second _pump with
    // a different fixture throws before any layout is exercised.
    testWidgets('the master bar survives a cramped window', (tester) async {
      // Below 900px the market read stacks above the cards instead of
      // sitting beside them.
      await _pump(tester, const TodaysOpportunitiesBar(),
          board: _board(rows: [_row()]), width: 700);
      expect(tester.takeException(), isNull);
    });

    testWidgets('the fund section survives a cramped window', (tester) async {
      await _pump(tester, const FundOpportunitySection(),
          funds: _funds(), width: 700);
      expect(tester.takeException(), isNull);
    });

    testWidgets('the stock section survives a cramped window', (tester) async {
      await _pump(tester, const StockOpportunitySection(),
          stocks: _stocks(blocked: true), width: 700);
      expect(tester.takeException(), isNull);
    });
  });

  // ══════════════════════════════════════════════════════════════
  //  TODAY'S OPPORTUNITIES
  // ══════════════════════════════════════════════════════════════

  group("today's opportunities", () {
    testWidgets('a quiet day says so rather than inventing a buy',
        (tester) async {
      // The behaviour the widget lives or dies by: the measured backtest says
      // most days offer nothing, so a manufactured BUY would be wrong.
      await _pump(tester, const TodaysOpportunitiesBar(),
          board: _board(status: 'quiet'));
      expect(find.text('No strong dip today'), findsOneWidget);
    });

    testWidgets('the market read is one word and one sentence', (tester) async {
      await _pump(tester, const TodaysOpportunitiesBar(),
          board: _board(rows: [_row()]));
      expect(find.text('CORRECTION'), findsOneWidget);
      expect(find.textContaining('Large caps are 9% off'), findsOneWidget);
    });

    testWidgets('every card carries its why, not just a score', (tester) async {
      await _pump(tester, const TodaysOpportunitiesBar(),
          board: _board(rows: [_row()]));
      expect(find.text('87'), findsOneWidget);
      expect(find.textContaining('36.8% off its high'), findsWidgets);
    });

    testWidgets('a risk row is labelled and counted', (tester) async {
      await _pump(tester, const TodaysOpportunitiesBar(),
          board: _board(rows: [
            _row(),
            _row(action: 'avoid', label: 'AVOID', kind: 'stock', name: 'ITC'),
          ]));
      expect(find.text('AVOID'), findsOneWidget);
      expect(find.text('1 to avoid'), findsOneWidget);
    });
  });

  // ══════════════════════════════════════════════════════════════
  //  MARKET TAPE — the inverted palette
  // ══════════════════════════════════════════════════════════════

  group('market tape', () {
    testWidgets('an index at its high reads OVERHEATED', (tester) async {
      await _pump(tester, const MarketTapeStrip(),
          tape: _tape(status: 'overheated', off: 0.4));
      expect(find.text('OVERHEATED'), findsOneWidget);
    });

    testWidgets('a real correction reads ATTRACTIVE, not as a loss',
        (tester) async {
      // Red must mean risk. A 20% correction is the thing this dashboard
      // exists to find and must never be painted like a loss.
      await _pump(tester, const MarketTapeStrip(),
          tape: _tape(status: 'attractive', off: 20.0));
      expect(find.text('ATTRACTIVE'), findsOneWidget);
      expect(find.text('OVERHEATED'), findsNothing);
    });

    testWidgets('an extreme fall reads HIGH RISK', (tester) async {
      await _pump(tester, const MarketTapeStrip(),
          tape: _tape(status: 'high_risk', off: 36.8));
      expect(find.text('HIGH RISK'), findsOneWidget);
    });
  });

  // ══════════════════════════════════════════════════════════════
  //  CARDS
  // ══════════════════════════════════════════════════════════════

  group('fund cards', () {
    testWidgets('a category tile shows the normalised name, not the raw one',
        (tester) async {
      // The raw source field is "Fund of Funds" / "Mutual Fund", which tells
      // the reader nothing about whether smallcaps are cheaper than large.
      await _pump(tester, const FundOpportunitySection(), funds: _funds());
      expect(find.text('SILVER'), findsOneWidget);
      expect(find.text('FUND OF FUNDS'), findsNothing);
    });

    testWidgets('the score is shown large with its reasons', (tester) async {
      await _pump(tester, const FundOpportunitySection(), funds: _funds());
      expect(find.text('87'), findsWidgets);
      expect(find.textContaining('Too few past episodes'), findsOneWidget);
    });

    testWidgets('a deep fall is flagged beside the action, not instead of it',
        (tester) async {
      await _pump(tester, const FundOpportunitySection(), funds: _funds());
      expect(find.text('CONSIDER ADDING'), findsWidgets);
      expect(find.text('deep fall'), findsOneWidget);
    });

    testWidgets('an unscored fund shows a dash, never a zero', (tester) async {
      final board = FundDipBoard.fromJson({
        'as_of': '',
        'funds': [
          {
            'scheme_name': 'X Fund',
            'category': 'Other',
            'nav': 10.0,
            'score': null,
            'action': 'watch',
            'action_label': 'Watch',
            'reasons': <String>[],
            'purchase': {'buys': 0},
            'position': {'label': 'No purchase history'},
            'zones': [],
          }
        ],
      });
      await _pump(tester, const FundOpportunitySection(), funds: board);
      expect(find.text('0'), findsNothing);
      expect(find.text('—'), findsWidgets);
    });
  });

  group('stock cards', () {
    testWidgets('the fall reason is on the card, not hidden in a detail view',
        (tester) async {
      await _pump(tester, const StockOpportunitySection(), stocks: _stocks());
      expect(find.text('FALL REASON'), findsOneWidget);
      expect(find.text('TEMPORARY · MARKET-WIDE'), findsOneWidget);
    });

    testWidgets('a blocked holding strikes its score and says do not average',
        (tester) async {
      await _pump(tester, const StockOpportunitySection(),
          stocks: _stocks(blocked: true));
      expect(find.text('DO NOT AVERAGE'), findsOneWidget);
      expect(find.text('STRUCTURAL · FUNDAMENTALS WEAK'), findsOneWidget);
      // The score stays visible — hiding it would look like missing data.
      expect(find.text('65'), findsOneWidget);
    });

    testWidgets('the three status chips are always present', (tester) async {
      await _pump(tester, const StockOpportunitySection(), stocks: _stocks());
      expect(find.text('FUNDAMENTALS'), findsOneWidget);
      expect(find.text('VALUATION'), findsOneWidget);
      expect(find.text('NEWS'), findsOneWidget);
    });

    testWidgets('the main risk is shown when there is one', (tester) async {
      await _pump(tester, const StockOpportunitySection(),
          stocks: _stocks(blocked: true));
      expect(find.textContaining('Main risk:'), findsOneWidget);
    });
  });

  // ══════════════════════════════════════════════════════════════
  //  FAILURE IS NOT EMPTINESS
  // ══════════════════════════════════════════════════════════════

  group('a failed fetch never reads as an empty portfolio', () {
    /// Seen on the running app: the backend was restarted mid-load, the
    /// provider swallowed the error and returned an empty board, and a user
    /// holding nineteen stocks was told "No stocks to analyse yet — add
    /// equity holdings". "The request failed" and "you own nothing" are
    /// different facts and must not share a screen.
    testWidgets('a dropped stock request offers a retry, not "add holdings"',
        (tester) async {
      await _pump(tester, const StockOpportunitySection(), stocksFail: true);
      await tester.pumpAndSettle();
      expect(find.textContaining('Could not load'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);
      expect(find.textContaining('Add equity holdings'), findsNothing);
    });

    testWidgets('a dropped fund request offers a retry', (tester) async {
      await _pump(tester, const FundOpportunitySection(), fundsFail: true);
      await tester.pumpAndSettle();
      expect(find.textContaining('Could not load'), findsOneWidget);
      expect(find.textContaining('Add mutual funds'), findsNothing);
    });

    testWidgets('a genuinely empty portfolio still says so', (tester) async {
      await _pump(tester, const StockOpportunitySection(),
          stocks: StockDipBoard.empty);
      expect(find.text('No stocks to analyse yet'), findsOneWidget);
      expect(find.text('Retry'), findsNothing);
    });
  });

  // ══════════════════════════════════════════════════════════════
  //  REFRESH — automatic and manual
  // ══════════════════════════════════════════════════════════════

  group('refresh', () {
    test('an automatic tick does not force, a manual press does', () {
      // The distinction the server cares about: the hourly tick is happy with
      // the server cache, but someone pressing Update wants the current number
      // and must bypass the TTL.
      final container = ProviderContainer();
      addTearDown(container.dispose);

      expect(container.read(deployRefreshProvider).manual, isFalse);

      container.read(deployRefreshProvider.notifier).refresh();
      expect(container.read(deployRefreshProvider).generation, 1);
      expect(container.read(deployRefreshProvider).manual, isFalse,
          reason: 'a write-triggered refetch should not bypass the cache');

      container.read(deployRefreshProvider.notifier).manualRefresh();
      expect(container.read(deployRefreshProvider).generation, 2);
      expect(container.read(deployRefreshProvider).manual, isTrue);
    });

    test('the dashboard clock is one hour', () {
      // One constant drives the tape and all three decision surfaces, so they
      // cannot drift apart and show two different moments as one.
      expect(kDashboardRefresh, const Duration(hours: 1));
    });

    testWidgets('the bar shows an Update button and the cadence',
        (tester) async {
      await _pump(tester, const TodaysOpportunitiesBar(),
          board: _board(rows: [_row()]));
      await tester.pumpAndSettle();
      expect(find.text('Update'), findsOneWidget);
      // The stamp must say it is hourly, or "Updated 12:58" reads as live.
      expect(find.textContaining('hourly'), findsOneWidget);
    });

    testWidgets('pressing Update bumps the refresh request', (tester) async {
      await _pump(tester, const TodaysOpportunitiesBar(),
          board: _board(rows: [_row()]));
      await tester.pumpAndSettle();
      final container = ProviderScope.containerOf(
          tester.element(find.byType(TodaysOpportunitiesBar)));
      expect(container.read(deployRefreshProvider).manual, isFalse);

      await tester.tap(find.text('Update'));
      await tester.pump();
      expect(container.read(deployRefreshProvider).manual, isTrue);
    });
  });
}
