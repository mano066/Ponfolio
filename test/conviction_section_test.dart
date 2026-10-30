import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:aiei_wealth/core/theme/app_theme.dart';
import 'package:aiei_wealth/data/models/conviction_models.dart';
import 'package:aiei_wealth/presentation/widgets/conviction_section.dart';
import 'package:aiei_wealth/providers/conviction_provider.dart';

/// The conviction board: every holding judged on the business, the written
/// thesis and the position size — never on price or average cost.

Map<String, dynamic> _boardJson() => {
      'as_of': '2026-10-07T10:00:00',
      'settings': {'max_position_pct': 10, 'min_position_pct': 2},
      'results_season': {
        'label': 'Jul–Sep 2026 results',
        'in_season': true,
        'days_until': 0,
      },
      'summary': {
        'borrowed_conviction': 1,
        'under_exit_line': 1,
        'add_allowed': 1,
        'review_due': 0,
      },
      'trigger_metrics': {'revenue_growth_pct': 'Sales growth %'},
      'trigger_ops': ['<', '<=', '>', '>='],
      'holdings': [
        {
          'symbol': 'TINY.NS',
          'key': 'TINY',
          'name': 'Tiny Ltd',
          'weight_pct': 0.6,
          'size_band': 'exit_or_grow',
          'size_label': 'Too small — exit it or grow it',
          'health': {'score': null, 'grade': 'unknown', 'checks': []},
          'thesis': null,
          'thesis_state': 'missing',
          'thesis_label': 'No thesis — borrowed conviction?',
          'borrowed_conviction': true,
          'add_gate': {
            'allowed': false,
            'blockers': ['No complete thesis — answer the three questions first'],
          },
          'last_result': 'unknown',
          'action': 'exit_or_grow',
          'action_label': 'Under 1% — exit it or grow it',
        },
        {
          'symbol': 'HDFCBANK.NS',
          'key': 'HDFCBANK',
          'name': 'HDFC Bank',
          'weight_pct': 8.2,
          'size_band': 'ok',
          'size_label': 'Sized right',
          'health': {
            'score': 78.0,
            'grade': 'strong',
            'grade_label': 'Strong',
            'coverage': 100,
            'financial': true,
            'checks': [
              {
                'key': 'roe', 'label': 'Return on equity', 'group': 'quality',
                'value': 16.5, 'unit': '%', 'score': 100, 'status': 'good',
                'rule': 'Good above 15%',
              },
            ],
          },
          'thesis': {
            'what_it_does': 'Lends to households and companies.',
            'growth_reason': 'Deposit franchise, branch expansion.',
            'expected_eps_growth_pct': 15,
            'sell_triggers': [
              {'text': 'Profit shrinks', 'metric': 'earnings_growth_pct',
                'op': '<', 'value': 0},
            ],
          },
          'thesis_state': 'ok',
          'thesis_label': 'Thesis written',
          'borrowed_conviction': false,
          'add_gate': {'allowed': true, 'blockers': []},
          'quarters': [
            {'quarter': '2026Q3', 'result': 'met', 'manual': false},
          ],
          'last_result': 'met',
          'missed_streak': 0,
          'action': 'add_allowed',
          'action_label': 'Adding allowed',
        },
      ],
      'watchlist': [
        {
          'symbol': 'TITAN.NS',
          'key': 'TITAN',
          'name': 'Titan',
          'stage': 'waiting',
          'stage_label': "Watching — don't buy yet",
          'thesis_state': 'missing',
          'days_watched': 6,
          'ready_after': '2026-11-15',
          'health': {'score': 70.0, 'grade': 'good', 'grade_label': 'Good'},
        },
      ],
    };

Future<void> _pump(WidgetTester tester, ConvictionBoard board) async {
  tester.view.physicalSize = const Size(1400, 1800);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(ProviderScope(
    overrides: [
      convictionBoardProvider.overrideWith((ref) async => board),
    ],
    child: MaterialApp(
      theme: AppTheme.dark(),
      home: const Scaffold(
        body: SingleChildScrollView(child: ConvictionSection()),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  group('model', () {
    test('parses the board, rows, health, thesis and watchlist', () {
      final b = ConvictionBoard.fromJson(_boardJson());
      expect(b.holdings, hasLength(2));
      final hdfc = b.holdings[1];
      expect(hdfc.addAllowed, isTrue);
      expect(hdfc.health.financial, isTrue);
      expect(hdfc.health.checks.single.valueText, '16.5%');
      expect(hdfc.thesis!.sellTriggers.single.automatic, isTrue);
      expect(b.holdings.first.addBlockers, isNotEmpty);
      expect(b.watchlist.single.readyAfter, '2026-11-15');
      expect(b.count('borrowed_conviction'), 1);
    });

    test('a thesis round-trips to the API shape', () {
      const t = Thesis(
        whatItDoes: 'x',
        growthReason: 'y',
        expectedEpsGrowthPct: 12,
        sellTriggers: [
          SellTrigger(text: 'Manual only'),
          SellTrigger(text: 'Sales shrink', metric: 'revenue_growth_pct', op: '<', value: 0),
        ],
      );
      final j = t.toJson();
      expect((j['sell_triggers'] as List).first, {'text': 'Manual only'});
      expect((j['sell_triggers'] as List).last['metric'], 'revenue_growth_pct');
      final back = Thesis.fromJson(j)!;
      expect(back.sellTriggers.last.automatic, isTrue);
    });

    test('garbage degrades to empty, never throws', () {
      final b = ConvictionBoard.fromJson({'holdings': 'nope', 'summary': 3});
      expect(b.isEmpty, isTrue);
      expect(Thesis.fromJson('x'), isNull);
    });
  });

  group('section', () {
    testWidgets('shows every holding with its action, most urgent first',
        (tester) async {
      await _pump(tester, ConvictionBoard.fromJson(_boardJson()));
      expect(find.text('CONVICTION & POSITION SIZE'), findsOneWidget);
      expect(find.text('Under 1% — exit it or grow it'), findsOneWidget);
      expect(find.text('Adding allowed'), findsOneWidget);
      expect(find.text('78 Strong'), findsOneWidget);
      expect(find.textContaining('Results season now'), findsOneWidget);
      // The tiny, thesis-less holding is listed before the healthy one.
      final tiny = tester.getTopLeft(find.text('TINY')).dy;
      final hdfc = tester.getTopLeft(find.text('HDFCBANK')).dy;
      expect(tiny, lessThan(hdfc));
    });

    testWidgets('the watchlist says to wait, not to buy', (tester) async {
      await _pump(tester, ConvictionBoard.fromJson(_boardJson()));
      expect(find.text('TITAN'), findsOneWidget);
      expect(find.textContaining("don't buy yet"), findsOneWidget);
      expect(find.textContaining('2026-11-15'), findsOneWidget);
    });

    testWidgets('tapping a holding explains why it may or may not be added to',
        (tester) async {
      await _pump(tester, ConvictionBoard.fromJson(_boardJson()));
      await tester.tap(find.text('TINY'));
      await tester.pumpAndSettle();
      expect(find.text('MAY I ADD MORE?'), findsOneWidget);
      expect(find.textContaining('answer the three questions'), findsOneWidget);
      expect(find.text('Write thesis'), findsOneWidget);
    });

    testWidgets('the thesis editor asks the three questions', (tester) async {
      await _pump(tester, ConvictionBoard.fromJson(_boardJson()));
      await tester.tap(find.text('TINY'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Write thesis'));
      await tester.pumpAndSettle();
      expect(find.text('1. What does it sell, and who pays it?'), findsOneWidget);
      expect(find.text('2. Why can its profit grow for 5 years?'), findsOneWidget);
      expect(find.text('3. What business event would make you sell?'), findsOneWidget);
      expect(find.text('Save thesis'), findsOneWidget);
    });

    testWidgets('an empty board still renders and offers the watchlist',
        (tester) async {
      await _pump(tester, ConvictionBoard.empty);
      expect(find.text('Add equity holdings to judge them here.'), findsOneWidget);
      expect(find.text('Add idea'), findsOneWidget);
    });
  });
}
