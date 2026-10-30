import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import '../../core/extensions.dart';
import '../../core/theme/app_text_styles.dart';

/// ─── Swing Signal Engine ───
/// Pure, testable logic that turns the backend's computed technicals (from
/// `/api/swing/daily-picks` and `/api/swing/analyze/{symbol}`) into a concrete
/// trading desk view: signal tags grouped by strategy, a component score
/// breakdown, and an actionable Buy/Watch/Avoid/Exit plan with exact price
/// levels, position sizing and invalidation conditions.
///
/// No new backend fields are required — everything here is derived from the
/// existing scan payload so the desk works with the current API.

/// Reference capital used for the 1%-risk position-size suggestion. Matches the
/// paper-trading account (₹10 lakh) so the two views stay consistent.
const double kSwingRefCapital = 1000000;
const double kSwingRiskPct = 0.01; // risk 1% of capital per trade

enum SwingAction { buy, watch, avoid, exit }

extension SwingActionX on SwingAction {
  String get label => switch (this) {
        SwingAction.buy => 'BUY',
        SwingAction.watch => 'WATCH',
        SwingAction.avoid => 'AVOID',
        SwingAction.exit => 'EXIT',
      };
}

enum SignalKind { continuation, pullback, reversal, avoid, exit }

extension SignalKindX on SignalKind {
  String get title => switch (this) {
        SignalKind.continuation => 'Bullish Continuation',
        SignalKind.pullback => 'Pullback Buy',
        SignalKind.reversal => 'Reversal Swing',
        SignalKind.avoid => 'Avoid / Weak',
        SignalKind.exit => 'Sell / Exit Rules',
      };
}

/// One checklist condition and whether it currently fires.
class SignalTag {
  final String label;
  final bool active;
  const SignalTag(this.label, this.active);
}

/// A single dimension of the swing score (0–100) with a short explanation.
class ScoreComponent {
  final String label;
  final int score;
  final String detail;
  const ScoreComponent(this.label, this.score, this.detail);
}

/// A concrete, level-based trade plan derived from the technicals.
class TradePlan {
  final SwingAction action;
  final double? entry;
  final bool entryDerived; // true when we fell back to LTP (no real trigger)
  final double? buyLow, buyHigh;
  final double? stop, target1, target2;
  final double? riskPerShare, rewardPerShare;
  final String? riskReward; // "1:2.0"
  final double? trailingAfterT1; // trail-to level once T1 prints
  final String holdDuration;
  final int? positionQty;
  final double? positionValue;
  final String? invalidIf;
  final String reason;
  final List<String> exitRules;
  const TradePlan({
    required this.action,
    this.entry,
    this.entryDerived = false,
    this.buyLow,
    this.buyHigh,
    this.stop,
    this.target1,
    this.target2,
    this.riskPerShare,
    this.rewardPerShare,
    this.riskReward,
    this.trailingAfterT1,
    required this.holdDuration,
    this.positionQty,
    this.positionValue,
    this.invalidIf,
    required this.reason,
    required this.exitRules,
  });
}

/// The full derived signal view for one stock.
class SwingSignal {
  final int score;
  final String scoreBucket; // Strong / Good / Watchlist / Avoid
  final String confidence; // High / Medium / Low
  final List<ScoreComponent> components;
  final Map<SignalKind, List<SignalTag>> tagsByKind;
  final TradePlan plan;
  const SwingSignal({
    required this.score,
    required this.scoreBucket,
    required this.confidence,
    required this.components,
    required this.tagsByKind,
    required this.plan,
  });

  /// Count of fired conditions for a strategy kind (for compact summaries).
  int fired(SignalKind k) =>
      (tagsByKind[k] ?? const []).where((t) => t.active).length;

  int total(SignalKind k) => (tagsByKind[k] ?? const []).length;
}

class SwingSignals {
  SwingSignals._();

  static double? _d(dynamic v) => v is num ? v.toDouble() : null;

  /// Parse a "1:2.0" risk:reward string into its numeric reward multiple.
  static double? parseRR(dynamic raw) {
    if (raw is num) return raw.toDouble();
    if (raw is String) {
      final parts = raw.split(':');
      final tail = parts.isNotEmpty ? parts.last.trim() : raw.trim();
      return double.tryParse(tail);
    }
    return null;
  }

  static bool _bullishPattern(String p) {
    final s = p.toLowerCase();
    return s.contains('bullish') ||
        s.contains('hammer') ||
        s.contains('morning');
  }

  static bool _bearishPattern(String p) => p.toLowerCase().contains('bearish');

  /// Nearest support strictly below [price] (highest such level).
  static double? _nearestSupport(List sup, double price) {
    final below = sup
        .map((e) => _d(e))
        .whereType<double>()
        .where((s) => s < price)
        .toList();
    if (below.isEmpty) return null;
    below.sort();
    return below.last;
  }

  /// Nearest resistance strictly above [price] (lowest such level).
  static double? _nearestResistance(List res, double price) {
    final above = res
        .map((e) => _d(e))
        .whereType<double>()
        .where((r) => r > price)
        .toList();
    if (above.isEmpty) return null;
    above.sort();
    return above.first;
  }

  static String bucketFor(int score) {
    if (score >= 80) return 'Strong Setup';
    if (score >= 65) return 'Good Setup';
    if (score >= 50) return 'Watchlist';
    return 'Avoid';
  }

  static String confidenceFor(int score) {
    if (score >= 80) return 'High';
    if (score >= 65) return 'Medium';
    return 'Low';
  }

  /// Derive the full swing view. [confidenceOverride] lets the analyze screen
  /// pass the LLM's confidence when available.
  static SwingSignal of(Map<String, dynamic> s, {String? confidenceOverride}) {
    final price = _d(s['price']) ?? 0;
    // Prefer the backend hybrid selection score when present; fall back to the
    // classic scan score for legacy payloads.
    final score = (_d(s['selection_score']) ?? _d(s['score']) ?? 0).round();
    final rsi = _d(s['rsi']);
    final stochRsi = _d(s['stoch_rsi']);
    final macdHist = _d(s['macd_hist']) ?? 0;
    final macdBull = (s['macd_signal']?.toString() ?? '') == 'Bullish';
    final adx = _d(s['adx']);
    final volRatio = _d(s['volume_ratio']);
    final volSpike = s['volume_spike'] == true;
    final pattern = s['pattern']?.toString() ?? 'None';
    final bbPos = s['bb_position']?.toString() ?? '';
    final ema20 = _d(s['ema20']);
    final ema50 = _d(s['ema50']);
    final trend = s['trend']?.toString() ?? 'Sideways';
    final supports = s['supports'] is List ? s['supports'] as List : const [];
    final resistances =
        s['resistances'] is List ? s['resistances'] as List : const [];
    final rawEntry = _d(s['entry']);
    final stop = _d(s['stop_loss']);
    final t1 = _d(s['target1']);
    final t2 = _d(s['target2']);
    final rr = s['risk_reward'];
    final rrVal = parseRR(rr);
    final setup = s['setup']?.toString() ?? '';
    final setupL = setup.toLowerCase();

    final entryDerived = rawEntry == null;
    final entry = rawEntry ?? (price > 0 ? price : null);
    final nSup = _nearestSupport(supports, price);
    final nRes = _nearestResistance(resistances, price);
    final nearSupport = nSup != null && price > 0 && (price - nSup) / price < 0.03;

    // ── Component scores (0–100) ──
    int trendScore;
    if (trend == 'Up') {
      trendScore = 70 +
          (adx == null
              ? 0
              : adx >= 30
                  ? 25
                  : adx >= 25
                      ? 18
                      : adx >= 20
                          ? 10
                          : 0);
    } else if (trend == 'Down') {
      trendScore = (adx != null && adx >= 25) ? 10 : 18;
    } else {
      trendScore = 45;
    }
    trendScore = trendScore.clamp(0, 100);

    int momentum = 50;
    if (rsi != null) {
      if (rsi >= 45 && rsi <= 60) {
        momentum = 80;
      } else if (rsi >= 40 && rsi < 45) {
        momentum = 70;
      } else if (rsi > 60 && rsi <= 68) {
        momentum = 60;
      } else if (rsi >= 35 && rsi < 40) {
        momentum = 55;
      } else if (rsi >= 30 && rsi < 35) {
        momentum = 45;
      } else if (rsi > 70) {
        momentum = 30;
      } else {
        momentum = 35; // < 30, deeply oversold / possibly broken
      }
    }
    if (macdBull && macdHist > 0) {
      momentum += 15;
    } else if (!macdBull && macdHist < 0) {
      momentum -= 20;
    }
    if (stochRsi != null) {
      if (stochRsi < 20) {
        momentum += 5;
      } else if (stochRsi > 80) {
        momentum -= 10;
      }
    }
    momentum = momentum.clamp(0, 100);

    int volume;
    if (volRatio == null) {
      volume = 50;
    } else if (volRatio >= 2) {
      volume = 95;
    } else if (volRatio >= 1.5) {
      volume = 85;
    } else if (volRatio >= 1.2) {
      volume = 68;
    } else if (volRatio >= 1.0) {
      volume = 50;
    } else if (volRatio >= 0.8) {
      volume = 38;
    } else {
      volume = 25;
    }

    int patternScore = _bullishPattern(pattern)
        ? 85
        : _bearishPattern(pattern)
            ? 15
            : pattern.toLowerCase().contains('doji')
                ? 45
                : 50;

    int rrScore;
    if (rrVal == null) {
      rrScore = 0;
    } else if (rrVal >= 3) {
      rrScore = 95;
    } else if (rrVal >= 2.5) {
      rrScore = 88;
    } else if (rrVal >= 2) {
      rrScore = 80;
    } else if (rrVal >= 1.5) {
      rrScore = 62;
    } else if (rrVal >= 1) {
      rrScore = 40;
    } else {
      rrScore = 22;
    }

    int srScore = 50;
    if (nearSupport) srScore += 25;
    if (nRes != null && price > 0) {
      final headroom = (nRes - price) / price;
      if (headroom >= 0.04) {
        srScore += 15;
      } else if (headroom < 0.015) {
        srScore -= 20; // ceiling right overhead
      }
    }
    if (supports.isEmpty) srScore -= 15;
    srScore = srScore.clamp(0, 100);

    final components = <ScoreComponent>[
      ScoreComponent('Trend', trendScore,
          '$trend${adx != null ? ' · ADX ${adx.toStringAsFixed(0)}' : ''}'),
      ScoreComponent('Momentum', momentum,
          'RSI ${rsi?.toStringAsFixed(0) ?? '—'} · MACD ${macdBull ? 'Bull' : 'Bear'}'),
      ScoreComponent('Volume', volume,
          '${volRatio?.toStringAsFixed(2) ?? '—'}× avg${volSpike ? ' · spike' : ''}'),
      ScoreComponent('Pattern', patternScore, pattern),
      ScoreComponent('Risk:Reward', rrScore, rr?.toString() ?? '—'),
      ScoreComponent(
          'Support/Res',
          srScore,
          nearSupport
              ? 'near support'
              : nRes != null
                  ? 'room to ₹${nRes.toStringAsFixed(0)}'
                  : 'open'),
    ];

    // ── Signal tags by strategy ──
    final nearEma = ema20 != null &&
            price > 0 &&
            (price - ema20).abs() / price < 0.02 ||
        (ema50 != null && price > 0 && (price - ema50).abs() / price < 0.02);

    final tags = <SignalKind, List<SignalTag>>{
      SignalKind.continuation: [
        SignalTag('Price > EMA20 > EMA50', trend == 'Up'),
        SignalTag('EMA20 above EMA50',
            ema20 != null && ema50 != null && ema20 > ema50),
        SignalTag('ADX ≥ 25 (strong trend)', adx != null && adx >= 25),
        SignalTag('MACD histogram bullish', macdBull && macdHist > 0),
        SignalTag('Volume ≥ 1.5× average', volRatio != null && volRatio >= 1.5),
        SignalTag('At/above upper band (breakout)', bbPos == 'Upper'),
      ],
      SignalKind.pullback: [
        SignalTag('Price pulling back to EMA20/50', nearEma),
        SignalTag('RSI 40–55 (turning up)',
            rsi != null && rsi >= 40 && rsi <= 55),
        SignalTag('Bounce off support', nearSupport),
        SignalTag('Bullish reversal candle', _bullishPattern(pattern)),
        SignalTag('Volume expansion on bounce', volSpike),
      ],
      SignalKind.reversal: [
        SignalTag('RSI recovering from < 40', rsi != null && rsi < 40),
        SignalTag('Stochastic RSI oversold (< 20)',
            stochRsi != null && stochRsi < 20),
        SignalTag('Price near strong support', nearSupport),
        SignalTag('Bullish candlestick pattern', _bullishPattern(pattern)),
        SignalTag('MACD histogram improving', macdHist > 0),
        SignalTag('Risk:Reward ≥ 1:2', rrVal != null && rrVal >= 2),
      ],
      SignalKind.avoid: [
        SignalTag('Price below EMA20 & EMA50', trend == 'Down'),
        SignalTag('Weak trend (ADX < 20)', adx != null && adx < 20),
        SignalTag('RSI overbought > 75, no breakout',
            rsi != null && rsi > 75 && bbPos != 'Upper'),
        SignalTag('Volume below average', volRatio != null && volRatio < 1.0),
        SignalTag('Risk:Reward < 1:1.5', rrVal != null && rrVal < 1.5),
        SignalTag(
            'Entry too close to resistance',
            nRes != null &&
                entry != null &&
                entry > 0 &&
                (nRes - entry) / entry < 0.015),
        SignalTag('No clear support below', supports.isEmpty),
      ],
    };

    // ── Action decision ──
    final avoidFired = tags[SignalKind.avoid]!.where((t) => t.active).length;
    final hardAvoid = trend == 'Down' ||
        (rrVal != null && rrVal < 1.2) ||
        supports.isEmpty ||
        (rsi != null && rsi > 78 && bbPos != 'Upper');

    // Buy zone around the entry trigger. Prefer the backend hybrid zone when
    // present so this view matches the scanner row exactly.
    double? buyLow = _d(s['buy_zone_low']);
    double? buyHigh = _d(s['buy_zone_high']);
    if ((buyLow == null || buyHigh == null) && entry != null) {
      if (setupL.contains('breakout') ||
          setupL.contains('squeeze') ||
          setupL.contains('crossover') ||
          setupL.contains('continuation')) {
        // Break-and-go: buy from the trigger up to ~1.2% above it.
        buyLow = entry;
        buyHigh = entry * 1.012;
      } else {
        // Bounce/reversal: buy a band around the level.
        buyLow = entry * 0.995;
        buyHigh = entry * 1.008;
      }
    }

    // Prefer the backend hybrid action (BUY / WATCH / AVOID) when present.
    final backendAction = switch (s['action']?.toString()) {
      'BUY' => SwingAction.buy,
      'WATCH' => SwingAction.watch,
      'AVOID' => SwingAction.avoid,
      _ => null,
    };
    SwingAction action;
    if (backendAction != null) {
      action = backendAction;
    } else if (hardAvoid || avoidFired >= 3 || score < 50) {
      action = SwingAction.avoid;
    } else if (score >= 55 &&
        buyLow != null &&
        buyHigh != null &&
        price >= buyLow &&
        price <= buyHigh) {
      action = SwingAction.buy; // already inside the buy zone
    } else {
      action = SwingAction.watch; // wait for the trigger
    }

    // Position sizing on 1% capital risk.
    final riskPerShare =
        (entry != null && stop != null) ? (entry - stop) : null;
    final rewardPerShare =
        (entry != null && t1 != null) ? (t1 - entry) : null;
    int? qty;
    double? posValue;
    if (riskPerShare != null && riskPerShare > 0 && entry != null) {
      qty = (kSwingRefCapital * kSwingRiskPct / riskPerShare).floor();
      if (qty < 0) qty = 0;
      posValue = qty * entry;
    }

    // Human-readable reason — prefer the backend hybrid rationale when present.
    final backendReason = (s['reason_selected'] as String?);
    final reason = (backendReason != null && backendReason.isNotEmpty)
        ? backendReason
        : _reason(
            action: action,
            setup: setup,
            setupL: setupL,
            entry: entry,
            entryDerived: entryDerived,
            nRes: nRes,
            nSup: nSup,
            rsi: rsi,
            macdBull: macdBull,
            volRatio: volRatio,
            pattern: pattern,
            trend: trend,
            adx: adx,
          );

    final exitRules = <String>[
      if (t1 != null) 'T1 ₹${_f(t1)} → book ~half, trail the rest',
      if (t2 != null) 'T2 ₹${_f(t2)} → book remaining',
      if (stop != null) 'Stop ₹${_f(stop)} hit → exit full position',
      if (ema20 != null) 'Daily close below EMA20 (₹${_f(ema20)}) → exit',
      'MACD turns bearish or RSI momentum fades → tighten stop',
      'Failed breakout back below trigger / volume spike on red candle → exit',
    ];

    final plan = TradePlan(
      action: action,
      entry: entry,
      entryDerived: entryDerived,
      buyLow: buyLow,
      buyHigh: buyHigh,
      stop: stop,
      target1: t1,
      target2: t2,
      riskPerShare: riskPerShare,
      rewardPerShare: rewardPerShare,
      riskReward: rr?.toString(),
      trailingAfterT1: entry, // trail to breakeven once T1 prints
      holdDuration: '3–10 trading days',
      positionQty: qty,
      positionValue: posValue,
      invalidIf: (s['invalidation_condition'] as String?) ??
          (stop != null
              ? 'Daily close below ₹${_f(stop)}'
              : (entry != null ? 'Loss of ₹${_f(entry)} trigger' : null)),
      reason: reason,
      exitRules: exitRules,
    );

    return SwingSignal(
      score: score,
      scoreBucket: bucketFor(score),
      confidence: confidenceOverride?.isNotEmpty == true
          ? confidenceOverride!
          : (s['confidence']?.toString() ?? confidenceFor(score)),
      components: components,
      tagsByKind: tags,
      plan: plan,
    );
  }

  static String _f(double v) => v.toStringAsFixed(v >= 1000 ? 0 : 2);

  static String _reason({
    required SwingAction action,
    required String setup,
    required String setupL,
    required double? entry,
    required bool entryDerived,
    required double? nRes,
    required double? nSup,
    required double? rsi,
    required bool macdBull,
    required double? volRatio,
    required String pattern,
    required String trend,
    required double? adx,
  }) {
    if (action == SwingAction.avoid) {
      final reasons = <String>[];
      if (trend == 'Down') reasons.add('price below EMA20/50 (downtrend)');
      if (adx != null && adx < 20) reasons.add('weak trend (ADX ${adx.toStringAsFixed(0)})');
      if (rsi != null && rsi > 75) reasons.add('overbought RSI ${rsi.toStringAsFixed(0)}');
      if (volRatio != null && volRatio < 1.0) reasons.add('below-average volume');
      final why = reasons.isEmpty ? 'poor risk/reward and no clear support' : reasons.join(', ');
      return 'Avoid for now — $why. Wait for a cleaner setup.';
    }

    final conf = <String>[];
    if (macdBull) conf.add('MACD bullish');
    if (rsi != null) conf.add('RSI ${rsi.toStringAsFixed(0)}');
    if (volRatio != null && volRatio >= 1.5) {
      conf.add('volume ${volRatio.toStringAsFixed(1)}× avg');
    }
    if (pattern != 'None' && _bullishPattern(pattern)) conf.add(pattern.split('(').first.trim());
    final confStr = conf.isEmpty ? '' : ' — confirmed by ${conf.join(', ')}';

    final e = entry != null ? '₹${_f(entry)}' : 'the trigger';
    if (setupL.contains('breakout') ||
        setupL.contains('squeeze') ||
        setupL.contains('crossover')) {
      final res = nRes != null ? ' above resistance ₹${_f(nRes)}' : '';
      return 'Buy only above $e$res on a volume-backed break$confStr.';
    }
    if (setupL.contains('bounce') ||
        setupL.contains('oversold') ||
        setupL.contains('hammer') ||
        setupL.contains('bullish') ||
        setupL.contains('morning')) {
      final sup = nSup != null ? ' near support ₹${_f(nSup)}' : '';
      return 'Buy on a bounce$sup around $e$confStr.';
    }
    return 'Buy above $e while price holds its trend$confStr.';
  }
}

// ══════════════════════════════════════════════════════════════
//  SHARED SWING WIDGETS
// ══════════════════════════════════════════════════════════════

/// Color for a 0–100 swing score / component (green→gold→red bands).
Color swingScoreColor(BuildContext context, num score) {
  final c = context.colors;
  if (score >= 80) return c.up;
  if (score >= 65) return c.gold;
  if (score >= 50) return c.blue;
  return c.dn;
}

Color swingActionColor(BuildContext context, SwingAction a) {
  final c = context.colors;
  return switch (a) {
    SwingAction.buy => c.up,
    SwingAction.watch => c.gold,
    SwingAction.avoid => c.dn,
    SwingAction.exit => c.dn,
  };
}

IconData swingActionIcon(SwingAction a) => switch (a) {
      SwingAction.buy => LucideIcons.trendingUp,
      SwingAction.watch => LucideIcons.eye,
      SwingAction.avoid => LucideIcons.ban,
      SwingAction.exit => LucideIcons.logOut,
    };

/// Solid action pill (BUY / WATCH / AVOID / EXIT). Colour + icon + text so the
/// meaning never relies on colour alone.
class SwingActionBadge extends StatelessWidget {
  final SwingAction action;
  final String? note;
  final bool large;
  const SwingActionBadge({super.key, required this.action, this.note, this.large = false});

  @override
  Widget build(BuildContext context) {
    final col = swingActionColor(context, action);
    return Container(
      padding: EdgeInsets.symmetric(horizontal: large ? 10 : 7, vertical: large ? 5 : 3),
      decoration: BoxDecoration(
        color: col.withValues(alpha: 0.12),
        border: Border.all(color: col.withValues(alpha: 0.35)),
        borderRadius: BorderRadius.circular(5),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(swingActionIcon(action), size: large ? 14 : 11, color: col),
        const SizedBox(width: 5),
        Text(action.label,
            style: (large ? AppTextStyles.label(col) : AppTextStyles.labelXs(col))),
        if (note != null && note!.isNotEmpty) ...[
          const SizedBox(width: 6),
          Text(note!, style: AppTextStyles.captionXs(col.withValues(alpha: 0.85))),
        ],
      ]),
    );
  }
}

/// Compact labelled score bar (label · thin fill · value). Value shown as text
/// so the reading is not colour-only.
class SwingScoreBar extends StatelessWidget {
  final String label;
  final int score; // 0..100
  final String? detail;
  const SwingScoreBar({super.key, required this.label, required this.score, this.detail});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final col = swingScoreColor(context, score);
    final pct = (score / 100).clamp(0.0, 1.0);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(children: [
        SizedBox(
          width: 96,
          child: Text(label, style: AppTextStyles.captionXs(c.t2), maxLines: 1, overflow: TextOverflow.ellipsis),
        ),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(2),
            child: SizedBox(
              height: 6,
              child: Row(children: [
                Expanded(flex: (pct * 1000).round().clamp(0, 1000), child: Container(color: col)),
                Expanded(flex: (1000 - (pct * 1000).round()).clamp(0, 1000), child: Container(color: c.bg3)),
              ]),
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 34,
          child: Text('$score', textAlign: TextAlign.right, style: AppTextStyles.monoBold(col).copyWith(fontSize: 12)),
        ),
        if (detail != null) ...[
          const SizedBox(width: 8),
          SizedBox(
            width: 110,
            child: Text(detail!, style: AppTextStyles.captionXs(c.t3), maxLines: 1, overflow: TextOverflow.ellipsis),
          ),
        ],
      ]),
    );
  }
}

/// A single signal condition chip — green when the condition fires, muted grey
/// (with a dot) when it does not. Text carries the meaning, not just colour.
class SignalTagChip extends StatelessWidget {
  final SignalTag tag;
  final bool danger; // avoid-list chips turn red when active
  const SignalTagChip({super.key, required this.tag, this.danger = false});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final on = tag.active;
    final col = on ? (danger ? c.dn : c.up) : c.t4;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: on ? col.withValues(alpha: 0.10) : c.bg3,
        border: Border.all(color: on ? col.withValues(alpha: 0.28) : c.bd),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(
          on ? (danger ? LucideIcons.alertTriangle : LucideIcons.check) : LucideIcons.minus,
          size: 10,
          color: col,
        ),
        const SizedBox(width: 4),
        Text(tag.label,
            style: AppTextStyles.captionXs(on ? col : c.t3)
                .copyWith(fontWeight: on ? FontWeight.w600 : FontWeight.w400)),
      ]),
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  14-DAY SWING DESK — AI-selected, user-executed watchlist logic
//
//  Mirrors the backend desk contract: Today's Picks are ideas, the
//  14-Day Desk is the system-selected watchlist, paper trading is the
//  user's choice from the desk. Actions: READY / WAIT / HOLD / EXIT /
//  REMOVE / EXPIRED. These statics let the UI render/group offline and
//  keep the classification testable. All copy is probability-based —
//  never a profit guarantee.
// ══════════════════════════════════════════════════════════════

/// Current recommendation for a tracked desk stock (wire: BUY/WAIT/HOLD/EXIT/
/// AVOID/EXPIRED). READY/REMOVE are accepted for back-compat with older data.
enum DeskAction { buy, wait, hold, exit, avoid, expired }

DeskAction deskActionFrom(String? s) => switch (s) {
      'BUY' => DeskAction.buy,
      'READY' => DeskAction.buy, // legacy wire value
      'WAIT' => DeskAction.wait,
      'HOLD' => DeskAction.hold,
      'EXIT' => DeskAction.exit,
      'AVOID' => DeskAction.avoid,
      'REMOVE' => DeskAction.avoid, // legacy wire value
      'EXPIRED' => DeskAction.expired,
      _ => DeskAction.wait,
    };

extension DeskActionX on DeskAction {
  String get wire => switch (this) {
        DeskAction.buy => 'BUY',
        DeskAction.wait => 'WAIT',
        DeskAction.hold => 'HOLD',
        DeskAction.exit => 'EXIT',
        DeskAction.avoid => 'AVOID',
        DeskAction.expired => 'EXPIRED',
      };

  String get label => switch (this) {
        DeskAction.buy => 'BUY',
        DeskAction.wait => 'WAIT',
        DeskAction.hold => 'HOLD',
        DeskAction.exit => 'EXIT',
        DeskAction.avoid => 'AVOID NEW ENTRY',
        DeskAction.expired => 'EXPIRED',
      };
}

/// How a tracked stock compares to its original selected setup.
enum SetupStatus { improved, same, weakened, invalid }

SetupStatus setupStatusFrom(String? s) => switch (s) {
      'improved' => SetupStatus.improved,
      'weakened' => SetupStatus.weakened,
      'invalid' => SetupStatus.invalid,
      _ => SetupStatus.same,
    };

/// Lifecycle thresholds — same names/defaults as the backend DESK_THRESHOLDS
/// (lowerCamelCase). Days are TRADING days (Mon–Fri; NSE holidays not excluded).
class DeskThresholds {
  final int maxTrackingDays;
  final int entryWaitDays;
  final int strongConfirmDay;
  final int minScoreKeep;
  final int scoreDropRemove;
  final int weakenedScoreDrop;
  final int improvedScoreGain;
  final double minRrKeep;
  final double readyMinVolumeRatio;
  final int readyMinDataQuality;
  final double strongMinRr;
  final double strongMinVolumeRatio;
  const DeskThresholds({
    this.maxTrackingDays = 14,
    this.entryWaitDays = 3,
    this.strongConfirmDay = 11,
    this.minScoreKeep = 45,
    this.scoreDropRemove = 20,
    this.weakenedScoreDrop = 8,
    this.improvedScoreGain = 5,
    this.minRrKeep = 1.2,
    this.readyMinVolumeRatio = 0.8,
    this.readyMinDataQuality = 40,
    this.strongMinRr = 2.0,
    this.strongMinVolumeRatio = 1.0,
  });
}

const kDeskThresholds = DeskThresholds();

class SwingDeskLogic {
  SwingDeskLogic._();

  static double? _d(dynamic v) => v is num ? v.toDouble() : null;
  static int _i(dynamic v) => v is num ? v.round() : 0;
  static DateTime? _date(dynamic s) =>
      s is DateTime ? s : DateTime.tryParse(s?.toString() ?? '');

  /// Weekdays strictly after [from], up to and including [to].
  /// Same day → 0. Friday → Monday → 1.
  static int tradingDaysBetween(DateTime from, DateTime to) {
    var d = DateTime(from.year, from.month, from.day);
    final end = DateTime(to.year, to.month, to.day);
    if (!end.isAfter(d)) return 0;
    var days = 0;
    while (d.isBefore(end)) {
      d = d.add(const Duration(days: 1));
      if (d.weekday <= DateTime.friday) days++;
    }
    return days;
  }

  static int daysInTracking(String selectedDate, DateTime today) {
    final d = _date(selectedDate);
    if (d == null) return 0;
    return tradingDaysBetween(d, today);
  }

  static int daysRemaining(String selectedDate, DateTime today,
      [DeskThresholds th = kDeskThresholds]) {
    final used = daysInTracking(selectedDate, today);
    return (th.maxTrackingDays - used).clamp(0, th.maxTrackingDays);
  }

  /// Setup drift vs the original selected pick.
  static SetupStatus setupStatusFor({
    required int originalScore,
    required int currentScore,
    bool invalid = false,
    DeskThresholds th = kDeskThresholds,
  }) {
    if (invalid) return SetupStatus.invalid;
    if (currentScore - originalScore >= th.improvedScoreGain) {
      return SetupStatus.improved;
    }
    if (originalScore - currentScore >= th.weakenedScoreDrop) {
      return SetupStatus.weakened;
    }
    return SetupStatus.same;
  }

  static double? _price(Map m) => _d(m['current_price']) ?? _d(m['price']);
  static int _score(Map m) => _i(m['selection_score'] ?? m['score']);
  static double _rr(Map m) {
    final v = _d(m['risk_reward_ratio']);
    if (v != null) return v;
    return SwingSignals.parseRR(m['risk_reward']) ?? 0.0;
  }

  /// Whether a tracked stock meets EVERY READY condition today (contract §6).
  static bool readyConditionsMet(
    Map<String, dynamic> record,
    Map<String, dynamic> snapshot,
    int days, {
    DeskThresholds th = kDeskThresholds,
  }) {
    final price = _price(snapshot);
    final entry = _d(record['original_entry']);
    final stop = _d(record['original_stop_loss']);
    if (price == null || entry == null) return false;
    final low = _d(record['buy_zone_low']) ?? entry * 0.98;
    final high = _d(record['buy_zone_high']) ?? entry * 1.02;
    final inZone = price >= low && price <= high;
    // Capped at max_entry_price/buy_zone_high — an uncapped "price >= entry"
    // would keep showing BUY forever once price gapped far past the entry.
    final ceiling = _d(record['max_entry_price']) ?? high;
    final triggered = price >= entry && price <= ceiling;
    if (!(inZone || triggered)) return false;
    final ema20 = _d(snapshot['ema20']) ?? 0;
    final ema50 = _d(snapshot['ema50']) ?? 0;
    final trendValid = (ema20 > 0 && price > ema20) ||
        (ema50 > 0 && price > ema50 && snapshot['trend']?.toString() == 'Up');
    if (!trendValid) return false;
    final rr = _rr(snapshot);
    final vol = _d(snapshot['volume_ratio']) ?? 0;
    final dq = _d(snapshot['data_quality_score']);
    if (vol < th.readyMinVolumeRatio) return false;
    if (rr < th.minRrKeep) return false;
    if (stop == null || stop <= 0) return false;
    if (dq != null && dq < th.readyMinDataQuality) return false;
    if (days >= th.strongConfirmDay) {
      final grade = snapshot['grade']?.toString() ?? '';
      final strong = rr >= th.strongMinRr &&
          vol >= th.strongMinVolumeRatio &&
          (grade == 'A+' || grade == 'A');
      if (!strong) return false;
    }
    return true;
  }

  /// Re-classify one tracked stock into a [DeskAction] (contract §5, §8).
  /// [record] is the persisted pick; [snapshot] is today's re-analysis data.
  static DeskAction classifyTracked(
    Map<String, dynamic> record,
    Map<String, dynamic>? snapshot,
    DateTime today, {
    DeskThresholds th = kDeskThresholds,
  }) {
    final days = daysInTracking(record['selected_date']?.toString() ?? '', today);
    final entered = record['entered'] == true;

    if (snapshot == null) {
      if (!entered && days >= th.maxTrackingDays) return DeskAction.expired;
      return deskActionFrom(record['tracking_status']?.toString());
    }

    final price = _price(snapshot);
    final score = _score(snapshot);
    final grade = snapshot['grade']?.toString() ?? '';
    final ema20 = _d(snapshot['ema20']) ?? 0;
    final ema50 = _d(snapshot['ema50']) ?? 0;
    final rr = _rr(snapshot);
    final origScore = _i(record['original_score']);
    final origStop = _d(record['original_stop_loss']) ?? 0;

    bool trendBroke = price != null &&
        ema20 > 0 &&
        ema50 > 0 &&
        price < ema20 &&
        price < ema50;

    if (entered) {
      if (price != null && origStop > 0 && price <= origStop) {
        return DeskAction.exit;
      }
      if (trendBroke) return DeskAction.exit;
      // Hard price stop aside, a held position shouldn't sit on HOLD once the
      // system's own re-scan says the thesis is gone: a sharp score collapse
      // or a flip to grade "Avoid" both mean the setup no longer holds.
      if (origScore - score >= th.scoreDropRemove) return DeskAction.exit;
      if (grade == 'Avoid') return DeskAction.exit;
      return DeskAction.hold;
    }

    if (days >= th.maxTrackingDays) return DeskAction.expired;

    // Invalidation keeps the stock on the desk, marked AVOID (avoid new entry).
    if (price != null && origStop > 0 && price <= origStop) {
      return DeskAction.avoid;
    }
    if (trendBroke) return DeskAction.avoid;
    if (rr > 0 && rr < th.minRrKeep) return DeskAction.avoid;
    if (score < th.minScoreKeep) return DeskAction.avoid;
    if (days > th.entryWaitDays && origScore - score >= th.scoreDropRemove) {
      return DeskAction.avoid;
    }
    if (grade == 'Avoid') return DeskAction.avoid;

    if (readyConditionsMet(record, snapshot, days, th: th)) {
      return DeskAction.buy;
    }
    return DeskAction.wait;
  }

  /// "Top 5 Focus" shortlist across ALL tracked day-batches — the desk can
  /// hold up to 5 picks/day × 14 days, which is too many to watch, so this
  /// ranks the fresh-entry candidates and keeps only the best [limit].
  ///
  /// Eligible: action BUY or WAIT, setup not invalidated, not already
  /// entered (open positions live in Paper Trading). Duplicated symbols keep
  /// their newest pick (input is expected newest-batch-first).
  /// Rank: BUY before WAIT → current score → setup drift (improved first)
  /// → R:R → more tracking days remaining.
  static List<Map<String, dynamic>> topFocus(
    List<Map<String, dynamic>> stocks, {
    int limit = 5,
  }) {
    final seen = <String>{};
    final pool = <Map<String, dynamic>>[];
    for (final s in stocks) {
      final action = deskActionFrom(s['tracking_status']?.toString());
      if (action != DeskAction.buy && action != DeskAction.wait) continue;
      if (setupStatusFrom(s['setup_status']?.toString()) ==
          SetupStatus.invalid) {
        continue;
      }
      if (s['entered'] == true) continue;
      final sym = s['symbol']?.toString() ?? '';
      if (sym.isEmpty || !seen.add(sym)) continue;
      pool.add(s);
    }
    int actionRank(Map<String, dynamic> s) =>
        deskActionFrom(s['tracking_status']?.toString()) == DeskAction.buy
            ? 0
            : 1;
    int statusRank(Map<String, dynamic> s) =>
        switch (setupStatusFrom(s['setup_status']?.toString())) {
          SetupStatus.improved => 0,
          SetupStatus.same => 1,
          SetupStatus.weakened => 2,
          SetupStatus.invalid => 3,
        };
    int score(Map<String, dynamic> s) =>
        _i(s['current_score'] ?? s['original_score']);
    pool.sort((a, b) {
      var d = actionRank(a) - actionRank(b);
      if (d != 0) return d;
      d = score(b) - score(a);
      if (d != 0) return d;
      d = statusRank(a) - statusRank(b);
      if (d != 0) return d;
      final rrd = _rr(b).compareTo(_rr(a));
      if (rrd != 0) return rrd;
      return _i(b['days_remaining']) - _i(a['days_remaining']);
    });
    return pool.take(limit).toList();
  }

  /// "Focus Dashboard" — every actively-tracked stock (any status except
  /// expired, which the backend already retires into `history`), sorted by
  /// ACTUAL profit % since selection (highest to lowest), highest first.
  /// Duplicated symbols keep their newest pick (input expected
  /// newest-batch-first, matching [topFocus]/[groupBySelectedDate]).
  ///
  /// This is the performance view: unlike [topFocus] (which only surfaces
  /// fresh entry candidates), everything stays here — entered/held, avoided,
  /// waiting, exited — so realized profit/loss is visible across the whole
  /// 14-day tracking window, not just for stocks still awaiting entry.
  static List<Map<String, dynamic>> focusDashboard(
    List<Map<String, dynamic>> stocks,
  ) {
    final seen = <String>{};
    final pool = <Map<String, dynamic>>[];
    for (final s in stocks) {
      if (deskActionFrom(s['tracking_status']?.toString()) ==
          DeskAction.expired) {
        continue;
      }
      final sym = s['symbol']?.toString() ?? '';
      if (sym.isEmpty || !seen.add(sym)) continue;
      pool.add(s);
    }
    double? profit(Map<String, dynamic> s) => _d(s['price_change_pct']);
    pool.sort((a, b) {
      final pa = profit(a);
      final pb = profit(b);
      if (pa == null && pb == null) return 0;
      if (pa == null) return 1; // no P/L yet sorts last
      if (pb == null) return -1;
      return pb.compareTo(pa);
    });
    return pool;
  }

  /// [focusDashboard] (active/tracking stocks) merged with retired history
  /// entries (expired 14-day picks that kept a full performance snapshot),
  /// each tagged `completed` so the UI can offer an Active/Completed filter.
  /// History entries without `actual_profit_pct` (e.g. a manual removal
  /// stub) are skipped — there's no comparable profit figure to rank them.
  static List<Map<String, dynamic>> focusDashboardWithHistory(
    List<Map<String, dynamic>> activeStocks,
    List<Map<String, dynamic>> historyEntries,
  ) {
    final active = focusDashboard(activeStocks)
        .map((s) => <String, dynamic>{...s, 'completed': false});
    final completed = historyEntries
        .where((h) => h['actual_profit_pct'] != null)
        .map((h) => <String, dynamic>{
              'symbol': h['symbol'],
              'name': h['name'],
              'selected_date': h['selected_date'],
              'original_price': h['original_price'],
              'current_price': h['final_price'],
              'price_change_pct': h['actual_profit_pct'],
              'tracking_day': 14,
              'tracking_status': 'EXPIRED',
              'prediction_confidence': h['prediction_confidence'],
              'predicted_gain_pct': h['predicted_gain_pct'],
              'day_snapshots': h['day_snapshots'] ?? const {},
              'completed': true,
            });
    final merged = [...active, ...completed];
    double? profit(Map<String, dynamic> s) => _d(s['price_change_pct']);
    merged.sort((a, b) {
      final pa = profit(a);
      final pb = profit(b);
      if (pa == null && pb == null) return 0;
      if (pa == null) return 1;
      if (pb == null) return -1;
      return pb.compareTo(pa);
    });
    return merged;
  }

  /// Group desk stocks by their batch label, newest selected date first
  /// (contract §4). Each entry: {batch_label, selected_date, stocks:[...]}.
  static List<Map<String, dynamic>> groupBySelectedDate(
      List<Map<String, dynamic>> stocks) {
    final groups = <String, Map<String, dynamic>>{};
    for (final s in stocks) {
      final label = s['day_batch_label']?.toString() ??
          '${s['selected_date']} Picks';
      final g = groups.putIfAbsent(
          label,
          () => {
                'batch_label': label,
                'selected_date': s['selected_date'],
                'stocks': <Map<String, dynamic>>[],
              });
      (g['stocks'] as List).add(s);
    }
    final list = groups.values.toList()
      ..sort((a, b) => (b['selected_date']?.toString() ?? '')
          .compareTo(a['selected_date']?.toString() ?? ''));
    return list;
  }
}

// ── Desk badges (colour + icon + text, never colour alone) ──

Color deskActionColor(BuildContext context, DeskAction a) {
  final c = context.colors;
  return switch (a) {
    DeskAction.buy => c.up,
    DeskAction.wait => c.gold,
    DeskAction.hold => c.blue,
    DeskAction.exit => c.dn,
    DeskAction.avoid => c.dn,
    DeskAction.expired => c.t3,
  };
}

IconData deskActionIcon(DeskAction a) => switch (a) {
      DeskAction.buy => LucideIcons.trendingUp,
      DeskAction.wait => LucideIcons.clock,
      DeskAction.hold => LucideIcons.shield,
      DeskAction.exit => LucideIcons.logOut,
      DeskAction.avoid => LucideIcons.ban,
      DeskAction.expired => LucideIcons.calendarX,
    };

/// Solid desk-action pill (BUY / WAIT / HOLD / EXIT / AVOID / EXPIRED),
/// styled like [SwingActionBadge].
class DeskActionBadge extends StatelessWidget {
  final DeskAction action;
  final String? note;
  final bool large;
  const DeskActionBadge(
      {super.key, required this.action, this.note, this.large = false});

  @override
  Widget build(BuildContext context) {
    final col = deskActionColor(context, action);
    return Container(
      padding: EdgeInsets.symmetric(
          horizontal: large ? 10 : 7, vertical: large ? 5 : 3),
      decoration: BoxDecoration(
        color: col.withValues(alpha: 0.12),
        border: Border.all(color: col.withValues(alpha: 0.35)),
        borderRadius: BorderRadius.circular(5),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(deskActionIcon(action), size: large ? 14 : 11, color: col),
        const SizedBox(width: 5),
        Text(action.label,
            style: large ? AppTextStyles.label(col) : AppTextStyles.labelXs(col)),
        if (note != null && note!.isNotEmpty) ...[
          const SizedBox(width: 6),
          Text(note!,
              style: AppTextStyles.captionXs(col.withValues(alpha: 0.85))),
        ],
      ]),
    );
  }
}

/// Improved / same / weakened / invalid chip for tracked picks.
class SetupStatusBadge extends StatelessWidget {
  final SetupStatus status;
  const SetupStatusBadge({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final (col, icon, label) = switch (status) {
      SetupStatus.improved => (c.up, LucideIcons.trendingUp, 'IMPROVED'),
      SetupStatus.same => (c.t3, LucideIcons.minus, 'SAME'),
      SetupStatus.weakened => (c.gold, LucideIcons.trendingDown, 'WEAKENED'),
      SetupStatus.invalid => (c.dn, LucideIcons.xCircle, 'INVALID'),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: col.withValues(alpha: 0.10),
        border: Border.all(color: col.withValues(alpha: 0.30)),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 10, color: col),
        const SizedBox(width: 4),
        Text(label, style: AppTextStyles.captionXs(col)),
      ]),
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  SIGNAL FRESHNESS — actionable_status (wire: backend validate_recommendation)
//
//  Every recommendation the backend publishes is validated against a FRESH
//  price before it's shown: a stale setup (price already gapped past the buy
//  zone, or a real target already reached) is never presented as a fresh
//  BUY. This is presentation-only logic — the backend is the single source
//  of truth for the status itself (see swing_trading.validate_recommendation
//  / determine_fill in the Python backend).
// ══════════════════════════════════════════════════════════════

enum ActionableStatus {
  readyToBuy,
  waitForEntry,
  nearBuyZone,
  missedEntry,
  targetAlreadyReached,
  invalid,
  pendingEntry,
  dataStale,
}

ActionableStatus actionableStatusFrom(String? s) => switch (s) {
      'READY_TO_BUY' => ActionableStatus.readyToBuy,
      'WAIT_FOR_ENTRY' => ActionableStatus.waitForEntry,
      'NEAR_BUY_ZONE' => ActionableStatus.nearBuyZone,
      'MISSED_ENTRY' => ActionableStatus.missedEntry,
      'TARGET_ALREADY_REACHED' => ActionableStatus.targetAlreadyReached,
      'INVALID' => ActionableStatus.invalid,
      'PENDING_ENTRY' => ActionableStatus.pendingEntry,
      'DATA_STALE' => ActionableStatus.dataStale,
      _ => ActionableStatus.waitForEntry,
    };

/// Only these may ever appear as a fresh "Today's Buy Opportunities" entry.
bool isFreshBuyOpportunity(ActionableStatus s) =>
    s == ActionableStatus.readyToBuy || s == ActionableStatus.nearBuyZone;

extension ActionableStatusX on ActionableStatus {
  /// Plain-language label — never says "BUY" once price is past the entry limit.
  String get label => switch (this) {
        ActionableStatus.readyToBuy => 'Ready — price inside buy zone',
        ActionableStatus.waitForEntry => 'Wait — price below buy zone',
        ActionableStatus.nearBuyZone => 'Near zone — do not chase',
        ActionableStatus.missedEntry => 'Missed — price moved above buy zone',
        ActionableStatus.targetAlreadyReached =>
          'Target/estimated move already reached',
        ActionableStatus.invalid => 'Setup invalid — skipped',
        ActionableStatus.pendingEntry => 'Pending — no paper position opened',
        ActionableStatus.dataStale => 'Price data stale — refresh',
      };

  String get shortLabel => switch (this) {
        ActionableStatus.readyToBuy => 'READY TO BUY',
        ActionableStatus.waitForEntry => 'WAIT FOR ENTRY',
        ActionableStatus.nearBuyZone => 'NEAR BUY ZONE',
        ActionableStatus.missedEntry => 'MISSED ENTRY',
        ActionableStatus.targetAlreadyReached => 'TARGET REACHED',
        ActionableStatus.invalid => 'INVALID',
        ActionableStatus.pendingEntry => 'PENDING',
        ActionableStatus.dataStale => 'DATA STALE',
      };

  /// Whether this status may ever be shown as a fresh buy recommendation.
  bool get isActionableBuy => isFreshBuyOpportunity(this);
}

Color actionableStatusColor(BuildContext context, ActionableStatus s) {
  final c = context.colors;
  return switch (s) {
    ActionableStatus.readyToBuy => c.up,
    ActionableStatus.nearBuyZone => c.gold,
    ActionableStatus.waitForEntry => c.blue,
    ActionableStatus.missedEntry => c.dn,
    ActionableStatus.targetAlreadyReached => c.t3,
    ActionableStatus.invalid => c.dn,
    ActionableStatus.pendingEntry => c.t3,
    ActionableStatus.dataStale => c.t3,
  };
}

IconData actionableStatusIcon(ActionableStatus s) => switch (s) {
      ActionableStatus.readyToBuy => LucideIcons.checkCircle2,
      ActionableStatus.nearBuyZone => LucideIcons.alertTriangle,
      ActionableStatus.waitForEntry => LucideIcons.clock,
      ActionableStatus.missedEntry => LucideIcons.ban,
      ActionableStatus.targetAlreadyReached => LucideIcons.flagOff,
      ActionableStatus.invalid => LucideIcons.xCircle,
      ActionableStatus.pendingEntry => LucideIcons.hourglass,
      ActionableStatus.dataStale => LucideIcons.wifiOff,
    };

/// "Filled at ₹X on DATE TIME" — the exact copy the UI requirements call for.
/// [filledAt] is expected in the backend's "YYYY-MM-DD HH:MM" format.
String formatFillLabel(double fillPrice, String? filledAt) {
  if (filledAt == null || filledAt.isEmpty) {
    return 'Filled at ₹${fillPrice.toStringAsFixed(2)}';
  }
  final parts = filledAt.split(' ');
  final date = parts.isNotEmpty ? parts[0] : filledAt;
  final time = parts.length > 1 ? parts[1] : '';
  return 'Filled at ₹${fillPrice.toStringAsFixed(2)} on $date $time'.trimRight();
}

/// Solid actionable-status pill, styled like [SwingActionBadge]/[DeskActionBadge].
class ActionableStatusBadge extends StatelessWidget {
  final ActionableStatus status;
  final bool large;
  const ActionableStatusBadge({super.key, required this.status, this.large = false});

  @override
  Widget build(BuildContext context) {
    final col = actionableStatusColor(context, status);
    return Container(
      padding: EdgeInsets.symmetric(horizontal: large ? 10 : 7, vertical: large ? 5 : 3),
      decoration: BoxDecoration(
        color: col.withValues(alpha: 0.12),
        border: Border.all(color: col.withValues(alpha: 0.35)),
        borderRadius: BorderRadius.circular(5),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(actionableStatusIcon(status), size: large ? 14 : 11, color: col),
        const SizedBox(width: 5),
        Text(status.shortLabel,
            style: large ? AppTextStyles.label(col) : AppTextStyles.labelXs(col)),
      ]),
    );
  }
}

/// A large score dial-ish readout: NN / 100 with the bucket underneath.
class SwingScoreReadout extends StatelessWidget {
  final int score;
  final String bucket;
  const SwingScoreReadout({super.key, required this.score, required this.bucket});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final col = swingScoreColor(context, score);
    return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.end, children: [
      Row(crossAxisAlignment: CrossAxisAlignment.baseline, textBaseline: TextBaseline.alphabetic, children: [
        Text('$score', style: AppTextStyles.monoBold(col).copyWith(fontSize: 22)),
        Text('/100', style: AppTextStyles.monoXs(c.t3)),
      ]),
      Text(bucket.toUpperCase(), style: AppTextStyles.labelXs(col)),
    ]);
  }
}
