import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:aiei_wealth/core/theme/app_theme.dart';
import 'package:aiei_wealth/data/models/deploy_models.dart';
import 'package:aiei_wealth/presentation/widgets/deploy/candidates_table.dart';
import 'package:aiei_wealth/presentation/widgets/deploy/sip_checklist_card.dart';

/// Widget tests for the deployment cards.
///
/// These pin the behaviours where a rendering mistake would actively mislead:
/// a dead index feed must never look like a flat market, an unchecked factor
/// must never look like a zero, and a skipped candidate must say why.
Future<void> _pump(WidgetTester tester, Widget child,
    {double width = 1400}) async {
  tester.view.physicalSize = Size(width, 1400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);

  await tester.pumpWidget(
    ProviderScope(
      child: MaterialApp(
        theme: AppTheme.dark(),
        home: Scaffold(
          body: SingleChildScrollView(child: SizedBox(width: width, child: child)),
        ),
      ),
    ),
  );
  await tester.pump();
}

DeployCandidate _candidate({
  String key = 'ICICI Tech Fund',
  double? score = 93.0,
  int confidence = 100,
  Map<String, dynamic>? factors,
  List<String> missing = const [],
  double? targetPct = 15.0,
}) =>
    DeployCandidate.fromJson({
      'kind': 'fund',
      'key': key,
      'name': key,
      'sector': 'Sectoral',
      'price': 145.0,
      'value': 36250.0,
      'avg_cost': 170.0,
      'target_pct': targetPct,
      'actual_pct': 9.1,
      'gap_pp': 5.9,
      'score': score,
      'confidence': confidence,
      'eligible': score != null && confidence >= 40,
      'why': const ['25.6% below its own NAV peak'],
      'missing_factors': missing,
      'factors': factors ??
          const {
            'own_drawdown': {
              'score': 100.0,
              'value': 25.6,
              'unit': '% below peak'
            },
            'index_dip': {
              'score': 100.0,
              'value': 22.0,
              'unit': '% below 1y high'
            },
            'below_avg_cost': {'score': 98.0, 'value': 14.7, 'unit': '%'},
            'underweight': {'score': 78.6, 'value': 5.9, 'unit': 'pp'},
          },
    });

DeployBoard _board({
  List<DeployCandidate>? candidates,
  Map<String, dynamic>? sipPlan,
}) =>
    DeployBoard(
      candidates: candidates ?? [_candidate()],
      sipPlan: SipPlanStatus.fromJson(sipPlan ?? const {}),
    );

void main() {
  group('BuyMoreCandidatesTable', () {
    testWidgets('renders a scored candidate with its score', (tester) async {
      await _pump(tester, BuyMoreCandidatesTable(board: _board()));
      expect(find.text('ICICI Tech Fund'), findsOneWidget);
      expect(find.text('93'), findsOneWidget);
      expect(find.textContaining('conf 100%'), findsOneWidget);
    });

    testWidgets('an unscorable candidate says so instead of showing 0',
        (tester) async {
      final cand = _candidate(score: null, confidence: 0, factors: const {
        'own_drawdown': {'score': null, 'value': null, 'unit': ''},
        'index_dip': {'score': null, 'value': null, 'unit': ''},
        'below_avg_cost': {'score': null, 'value': null, 'unit': ''},
        'underweight': {'score': null, 'value': null, 'unit': ''},
      });
      await _pump(tester, BuyMoreCandidatesTable(board: _board(candidates: [cand])));

      expect(find.text('not enough data'), findsOneWidget);
      expect(find.text('0'), findsNothing);
    });

    testWidgets('a low-confidence candidate is flagged', (tester) async {
      final cand = _candidate(score: 100.0, confidence: 15);
      await _pump(tester, BuyMoreCandidatesTable(board: _board(candidates: [cand])));
      expect(find.textContaining('conf 15%'), findsOneWidget);
    });

    testWidgets('a holding with no target says "no target", not 0%',
        (tester) async {
      final cand = _candidate(targetPct: null);
      await _pump(tester, BuyMoreCandidatesTable(board: _board(candidates: [cand])));
      expect(find.textContaining('no target'), findsOneWidget);
    });

    testWidgets('tapping a row reveals the factor breakdown', (tester) async {
      await _pump(tester, BuyMoreCandidatesTable(board: _board()));

      expect(find.textContaining('How far it has fallen'), findsNothing);
      await tester.tap(find.text('ICICI Tech Fund'));
      await tester.pumpAndSettle();

      expect(find.textContaining('How far it has fallen from its own peak'),
          findsOneWidget);
      expect(find.textContaining('How far below your average cost'),
          findsOneWidget);
      expect(find.textContaining('fully informed'), findsOneWidget);
    });

    testWidgets('an unchecked factor reads "could not check", never a number',
        (tester) async {
      final cand = _candidate(
        missing: const ['underweight'],
        factors: const {
          'own_drawdown': {'score': 100.0, 'value': 25.6, 'unit': '% below peak'},
          'index_dip': {'score': 50.0, 'value': 8.0, 'unit': '%'},
          'below_avg_cost': {'score': 98.0, 'value': 14.7, 'unit': '%'},
          'underweight': {'score': null, 'value': null, 'unit': 'pp'},
        },
      );
      await _pump(tester, BuyMoreCandidatesTable(board: _board(candidates: [cand])));
      await tester.tap(find.text('ICICI Tech Fund'));
      await tester.pumpAndSettle();

      expect(find.text('could not check'), findsOneWidget);
      expect(find.textContaining('1 of 4 checks could not be made'),
          findsOneWidget);
    });

    testWidgets('empty portfolio shows an empty state', (tester) async {
      await _pump(tester,
          BuyMoreCandidatesTable(board: _board(candidates: const [])));
      expect(find.text('Nothing to rank yet'), findsOneWidget);
    });

    testWidgets('narrow layout drops to the compact column set',
        (tester) async {
      await _pump(tester, BuyMoreCandidatesTable(board: _board()), width: 780);
      // VS COST only exists in the wide spec.
      expect(find.text('VS COST'), findsNothing);
      expect(find.text('OFF PEAK'), findsOneWidget);
    });
  });

  group('SipChecklistCard', () {
    Map<String, dynamic> plan(List<Map<String, dynamic>> legs) => {
          'month': '2026-09',
          'budget_total': 20000.0,
          'deployed_total': 10000.0,
          'remaining': 10000.0,
          'done_count': 1,
          'total_count': legs.length,
          'legs': legs,
        };

    testWidgets('shows no-plan state when nothing is configured',
        (tester) async {
      await _pump(tester, SipChecklistCard(board: _board()));
      expect(find.text('Set up plan'), findsOneWidget);
      expect(find.textContaining('Set up your monthly plan'), findsOneWidget);
    });

    testWidgets('renders each status with the right badge', (tester) async {
      final board = _board(
        sipPlan: plan([
          {'kind': 'fund', 'key': 'A', 'label': 'Fund A', 'amount': 10000.0,
           'due_day': 5, 'active': true, 'status': 'done',
           'deployed_this_month': 10000.0},
          {'kind': 'fund', 'key': 'B', 'label': 'Fund B', 'amount': 5000.0,
           'due_day': 10, 'active': true, 'status': 'overdue',
           'deployed_this_month': 0.0},
          {'kind': 'fund', 'key': 'C', 'label': 'Fund C', 'amount': 5000.0,
           'due_day': 15, 'active': true, 'status': 'partial',
           'deployed_this_month': 2000.0},
        ]),
      );
      await _pump(tester, SipChecklistCard(board: board));

      expect(find.text('DONE'), findsOneWidget);
      expect(find.text('OVERDUE'), findsOneWidget);
      expect(find.text('PARTIAL'), findsOneWidget);
      expect(find.text('Fund A'), findsOneWidget);
    });

    testWidgets('due days render as ordinals', (tester) async {
      final board = _board(
        sipPlan: plan([
          {'kind': 'fund', 'key': 'A', 'label': 'Fund A', 'amount': 1000.0,
           'due_day': 1, 'active': true, 'status': 'scheduled'},
          {'kind': 'fund', 'key': 'B', 'label': 'Fund B', 'amount': 1000.0,
           'due_day': 22, 'active': true, 'status': 'scheduled'},
        ]),
      );
      await _pump(tester, SipChecklistCard(board: board));
      expect(find.text('1st'), findsOneWidget);
      expect(find.text('22nd'), findsOneWidget);
    });

    testWidgets('a done leg offers no Record button', (tester) async {
      final board = _board(
        sipPlan: plan([
          {'kind': 'fund', 'key': 'A', 'label': 'Fund A', 'amount': 10000.0,
           'due_day': 5, 'active': true, 'status': 'done',
           'deployed_this_month': 10000.0},
        ]),
      );
      await _pump(tester, SipChecklistCard(board: board));
      expect(find.text('Record'), findsNothing);
    });

    testWidgets('an overdue leg offers a Record button', (tester) async {
      final board = _board(
        sipPlan: plan([
          {'kind': 'fund', 'key': 'B', 'label': 'Fund B', 'amount': 5000.0,
           'due_day': 10, 'active': true, 'status': 'overdue',
           'deployed_this_month': 0.0, 'shortfall': 5000.0},
        ]),
      );
      await _pump(tester, SipChecklistCard(board: board));
      expect(find.text('Record'), findsOneWidget);
    });

    testWidgets('shows the month budget progress', (tester) async {
      final board = _board(
        sipPlan: plan([
          {'kind': 'fund', 'key': 'A', 'label': 'Fund A', 'amount': 10000.0,
           'due_day': 5, 'active': true, 'status': 'done'},
        ]),
      );
      await _pump(tester, SipChecklistCard(board: board));
      expect(find.textContaining('September 2026'), findsOneWidget);
      expect(find.textContaining('still to go'), findsOneWidget);
    });
  });
}
