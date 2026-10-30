import 'package:flutter_test/flutter_test.dart';

import 'package:aiei_wealth/data/models/deploy_models.dart';

/// Parsing tests for the deployment models.
///
/// The load-bearing one: **null must survive as null.** The backend
/// deliberately distinguishes "we could not check this" from "this scored
/// zero", and that distinction is worthless if the Dart layer parses both into
/// 0.0 before anything renders.
void main() {
  group('IndexQuote', () {
    test('parses a live index', () {
      final q = IndexQuote.fromJson({
        'symbol': '^NSEI',
        'label': 'NIFTY 50',
        'group': 'broad',
        'status': 'ok',
        'last': 23914.65,
        'day_chg_pct': -1.2,
        'off_high_pct': 9.17,
        'high_52w': 26330.0,
        'at_high': false,
        'short_window': false,
      });

      expect(q.ok, isTrue);
      expect(q.label, 'NIFTY 50');
      expect(q.group, IndexGroup.broad);
      expect(q.last, 23914.65);
      expect(q.offHighPct, 9.17);
      expect(q.isDown, isTrue);
      expect(q.isUp, isFalse);
    });

    test('an unavailable index keeps NULL figures, never zero', () {
      final q = IndexQuote.fromJson({
        'symbol': '^BSESN',
        'label': 'SENSEX',
        'group': 'broad',
        'status': 'unavailable',
        'last': null,
        'day_chg_pct': null,
        'off_high_pct': null,
      });

      expect(q.ok, isFalse);
      expect(q.last, isNull);
      expect(q.dayChgPct, isNull);
      expect(q.offHighPct, isNull);
      // The whole point: it must not read as a flat market at its high.
      expect(q.isUp, isFalse);
      expect(q.isDown, isFalse);
    });

    test('unknown group falls back to broad', () {
      final q = IndexQuote.fromJson({'symbol': 'X', 'group': 'nonsense'});
      expect(q.group, IndexGroup.broad);
    });
  });

  group('MarketTape', () {
    final tape = MarketTape.fromJson({
      'as_of': '2026-09-03',
      'market_mood': 'falling',
      'summary': 'Nifty 50 is 9.2% below its 1-year high.',
      'breadth': {'up': 3, 'down': 9, 'available': 12},
      'indices': [
        {'symbol': '^NSEI', 'group': 'broad', 'status': 'ok', 'day_chg_pct': 1.0},
        {'symbol': '^CNXIT', 'group': 'sector', 'status': 'ok', 'day_chg_pct': -2.0},
        {'symbol': '^BSESN', 'group': 'broad', 'status': 'unavailable'},
      ],
    });

    test('parses breadth and mood', () {
      expect(tape.up, 3);
      expect(tape.down, 9);
      expect(tape.mood, 'falling');
      expect(tape.hasData, isTrue);
    });

    test('groups its indices', () {
      expect(tape.ofGroup(IndexGroup.broad).length, 2);
      expect(tape.ofGroup(IndexGroup.sector).length, 1);
      expect(tape.ofGroup(IndexGroup.commodity), isEmpty);
    });

    test('a tape with no live rows reports no data', () {
      final dead = MarketTape.fromJson({
        'indices': [
          {'symbol': '^NSEI', 'group': 'broad', 'status': 'unavailable'}
        ]
      });
      expect(dead.hasData, isFalse);
    });

    test('empty payload is safe', () {
      final empty = MarketTape.fromJson(const {});
      expect(empty.indices, isEmpty);
      expect(empty.hasData, isFalse);
      expect(MarketTape.empty.hasData, isFalse);
    });
  });

  group('DeployFactor', () {
    test('a known factor exposes score and magnitude', () {
      final f = DeployFactor.fromJson(
          {'score': 45.2, 'value': 12.4, 'unit': '% below peak'});
      expect(f.known, isTrue);
      expect(f.score, 45.2);
      expect(f.value, 12.4);
    });

    test('an unchecked factor is null, NOT zero', () {
      final f = DeployFactor.fromJson({'score': null, 'value': null});
      expect(f.known, isFalse);
      expect(f.score, isNull);
      expect(f.score, isNot(0.0));
    });

    test('a genuine zero score is still known', () {
      final f = DeployFactor.fromJson({'score': 0.0, 'value': 0.0});
      expect(f.known, isTrue);
      expect(f.score, 0.0);
    });

    test('missing json is an unknown factor', () {
      expect(DeployFactor.fromJson(null).known, isFalse);
    });
  });

  group('DeployCandidate', () {
    final cand = DeployCandidate.fromJson({
      'kind': 'fund',
      'key': 'ICICI Tech Fund',
      'name': 'ICICI Tech Fund',
      'sector': 'Sectoral',
      'price': 145.0,
      'value': 36250.0,
      'avg_cost': 170.0,
      'target_pct': 15.0,
      'actual_pct': 9.1,
      'gap_pp': 5.9,
      'at_or_over_target': false,
      'score': 93.38,
      'confidence': 100,
      'eligible': true,
      'benchmark_label': 'Nifty IT',
      'factors': {
        'own_drawdown': {'score': 100.0, 'value': 25.6, 'unit': '% below peak'},
        'index_dip': {'score': 100.0, 'value': 22.0, 'unit': '% below 1y high'},
        'below_avg_cost': {'score': 98.0, 'value': 14.7, 'unit': '%'},
        'underweight': {'score': 78.6, 'value': 5.9, 'unit': 'pp'},
      },
      'why': ['25.6% below its own NAV peak'],
      'missing_factors': <String>[],
      'rank': 1,
    });

    test('parses the full row', () {
      expect(cand.kind, HoldingKind.fund);
      expect(cand.score, 93.38);
      expect(cand.scored, isTrue);
      expect(cand.eligible, isTrue);
      expect(cand.rank, 1);
      expect(cand.benchmarkLabel, 'Nifty IT');
    });

    test('exposes factors by key', () {
      expect(cand.factor('own_drawdown').value, 25.6);
      expect(cand.factor('nonexistent').known, isFalse);
    });

    test('an unscorable candidate has a null score', () {
      final blank = DeployCandidate.fromJson({
        'kind': 'stock',
        'key': 'X.NS',
        'score': null,
        'confidence': 0,
        'missing_factors': ['own_drawdown', 'index_dip'],
      });
      expect(blank.score, isNull);
      expect(blank.scored, isFalse);
      expect(blank.eligible, isFalse);
      expect(blank.missingFactors.length, 2);
    });

    test('an unset target stays null so it is not read as on-target', () {
      final c = DeployCandidate.fromJson({'key': 'X', 'target_pct': null});
      expect(c.targetPct, isNull);
    });

    test('name falls back to key', () {
      expect(DeployCandidate.fromJson({'key': 'ABC'}).name, 'ABC');
    });
  });

  group('DeploySplit', () {
    test('a fund split reports units', () {
      final s = DeploySplit.fromJson({
        'kind': 'fund',
        'key': 'F',
        'label': 'F',
        'amount': 8000.0,
        'units': 55.172,
      });
      expect(s.unitsLabel, '55.172 units');
      expect(s.skipReason, isNull);
    });

    test('a stock split reports whole shares', () {
      final s = DeploySplit.fromJson({
        'kind': 'stock',
        'key': 'ITC.NS',
        'amount': 6336.0,
        'shares': 22,
      });
      expect(s.kind, HoldingKind.stock);
      expect(s.unitsLabel, '22 sh');
    });

    test('a skipped row carries its reason', () {
      final s = DeploySplit.fromJson({
        'kind': 'fund',
        'key': 'F',
        'amount': 0,
        'skip_reason': 'below_score_floor',
      });
      expect(s.amount, 0);
      expect(s.skipReason, 'below_score_floor');
    });
  });

  group('DeploySuggestion', () {
    test('parses allocations and leftovers', () {
      final s = DeploySuggestion.fromJson({
        'amount': 20000.0,
        'allocated': 19936.0,
        'unallocated': 64.0,
        'unallocated_reason': 'below_min_ticket',
        'allocations': [
          {'kind': 'fund', 'key': 'A', 'amount': 8000.0},
          {'kind': 'stock', 'key': 'B', 'amount': 6336.0, 'shares': 22},
        ],
        'skipped': [
          {'kind': 'fund', 'key': 'C', 'amount': 0, 'skip_reason': 'no_price'},
        ],
      });

      expect(s.hasSplits, isTrue);
      expect(s.splits.length, 2);
      expect(s.skipped.single.skipReason, 'no_price');
      expect(s.allocated + s.unallocated, 20000.0);
    });

    test('a too-small amount reports the ticket needed', () {
      final s = DeploySuggestion.fromJson({
        'amount': 300.0,
        'allocations': <dynamic>[],
        'unallocated': 300.0,
        'unallocated_reason': 'amount_below_min_ticket',
        'min_ticket_needed': 500.0,
      });
      expect(s.hasSplits, isFalse);
      expect(s.minTicketNeeded, 500.0);
    });
  });

  group('SipLeg', () {
    test('parses every status', () {
      const map = {
        'done': SipStatus.done,
        'partial': SipStatus.partial,
        'scheduled': SipStatus.scheduled,
        'due': SipStatus.due,
        'overdue': SipStatus.overdue,
        'inactive': SipStatus.inactive,
        'nonsense': SipStatus.unknown,
      };
      map.forEach((raw, expected) {
        expect(sipStatusFrom(raw), expected, reason: raw);
      });
    });

    test('round-trips through toJson', () {
      final leg = SipLeg.fromJson({
        'id': 'leg_1',
        'kind': 'fund',
        'key': 'A',
        'label': 'A',
        'amount': 10000.0,
        'due_day': 5,
        'active': true,
        'status': 'overdue',
        'deployed_this_month': 0.0,
        'shortfall': 10000.0,
        'days_overdue': 10,
      });

      expect(leg.status, SipStatus.overdue);
      expect(leg.daysOverdue, 10);

      final json = leg.toJson();
      expect(json['kind'], 'fund');
      expect(json['due_day'], 5);
      expect(json['amount'], 10000.0);
    });

    test('copyWith changes only what it is given', () {
      final leg = SipLeg.fromJson(
          {'kind': 'fund', 'key': 'A', 'amount': 1000.0, 'due_day': 5});
      final edited = leg.copyWith(amount: 2000);
      expect(edited.amount, 2000);
      expect(edited.dueDay, 5);
      expect(edited.key, 'A');
    });

    test('status labels are plain words', () {
      expect(sipStatusLabel(SipStatus.done), 'DONE');
      expect(sipStatusLabel(SipStatus.overdue), 'OVERDUE');
      expect(sipStatusLabel(SipStatus.scheduled), 'DUE');
    });
  });

  group('SipPlanStatus', () {
    final plan = SipPlanStatus.fromJson({
      'month': '2026-09',
      'budget_total': 20000.0,
      'deployed_total': 12000.0,
      'remaining': 8000.0,
      'done_count': 1,
      'total_count': 3,
      'legs': [
        {'kind': 'fund', 'key': 'A', 'status': 'done', 'active': true},
        {'kind': 'fund', 'key': 'B', 'status': 'overdue', 'active': true},
        {'kind': 'fund', 'key': 'C', 'status': 'partial', 'active': true},
      ],
    });

    test('parses totals', () {
      expect(plan.hasPlan, isTrue);
      expect(plan.doneCount, 1);
      expect(plan.remaining, 8000.0);
    });

    test('surfaces the legs still needing action', () {
      final keys = plan.needingAction.map((l) => l.key).toList();
      expect(keys, ['B', 'C']);
    });

    test('an empty plan is safe', () {
      final empty = SipPlanStatus.fromJson(const {});
      expect(empty.hasPlan, isFalse);
      expect(empty.needingAction, isEmpty);
    });
  });

  group('DeployBoard', () {
    test('parses a full board', () {
      final board = DeployBoard.fromJson({
        'as_of': '2026-09-03',
        'total_value': 400250.0,
        'market_mood': 'falling',
        'indices_summary': 'Nifty 50 is 9.2% below its 1-year high.',
        'candidates': [
          {'kind': 'fund', 'key': 'A', 'score': 93.0, 'rank': 1}
        ],
        'suggestion': {'amount': 20000.0, 'allocations': <dynamic>[]},
        'sip_plan': {'month': '2026-09', 'legs': <dynamic>[]},
        'targets': {'configured': true, 'sum_pct': 100.0, 'warning': null},
        'alerts': [
          {'level': 'warn', 'msg': '1 SIP line is overdue.'}
        ],
      });

      expect(board.hasData, isTrue);
      expect(board.totalValue, 400250.0);
      expect(board.candidates.single.score, 93.0);
      expect(board.targetsConfigured, isTrue);
      expect(board.alerts.single.level, 'warn');
      expect(board.marketMood, 'falling');
    });

    test('unconfigured targets surface a warning', () {
      final board = DeployBoard.fromJson({
        'targets': {
          'configured': false,
          'sum_pct': 60.0,
          'warning': 'Your targets add up to 60%, not 100%.'
        }
      });
      expect(board.targetsConfigured, isFalse);
      expect(board.targetsSumPct, 60.0);
      expect(board.targetsWarning, contains('60%'));
    });

    test('empty board is safe', () {
      expect(DeployBoard.fromJson(const {}).hasData, isFalse);
      expect(DeployBoard.empty.hasData, isFalse);
    });
  });

  group('DeployPlanConfig', () {
    test('parses saved config and suggestions', () {
      final cfg = DeployPlanConfig.fromJson({
        'sip_legs': [
          {'kind': 'fund', 'key': 'A', 'amount': 10000.0, 'due_day': 5}
        ],
        'targets': {'A': 25.0, 'ITC.NS': 5.0},
        'suggested_legs': [
          {'kind': 'fund', 'key': 'B', 'amount': 6000.0}
        ],
        'suggested_targets': {'A': 60.0},
        'monthly_budget': 30000.0,
        'holdings': {
          'funds': ['A', 'B'],
          'stocks': ['ITC.NS'],
        },
      });

      expect(cfg.isConfigured, isTrue);
      expect(cfg.legs.single.amount, 10000.0);
      expect(cfg.targets['A'], 25.0);
      expect(cfg.fundKeys, ['A', 'B']);
      expect(cfg.stockKeys, ['ITC.NS']);
      expect(cfg.suggestedLegs.single.key, 'B');
    });

    test('empty config is safe', () {
      final cfg = DeployPlanConfig.fromJson(const {});
      expect(cfg.isConfigured, isFalse);
      expect(cfg.fundKeys, isEmpty);
      expect(cfg.monthlyBudget, 30000);
    });
  });
}
