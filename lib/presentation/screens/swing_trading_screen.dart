import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../core/extensions.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_text_styles.dart';
import '../../providers/providers.dart';
import '../widgets/animated_page_wrapper.dart';
import '../widgets/common.dart';
import '../widgets/dense_ui.dart';
import 'swing_signals.dart';

/// Swing Trading — a data-dense "swing trade command center". Every setup shows
/// the exact reason, the buy zone, the stop, the targets, the risk:reward and
/// the invalidation — so the desk answers: what to trade, why it's valid, where
/// to buy, where the stop is, where to sell, and when to avoid or exit.
class SwingTradingScreen extends ConsumerStatefulWidget {
  const SwingTradingScreen({super.key});
  @override
  ConsumerState<SwingTradingScreen> createState() => _SwingTradingScreenState();
}

class _SwingTradingScreenState extends ConsumerState<SwingTradingScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabCtrl;
  String? _selectedSymbol; // for swing analysis sub-tab
  bool _kiteConnecting = false;

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 5, vsync: this);
  }

  @override
  void dispose() {
    _tabCtrl.dispose();
    super.dispose();
  }

  void _connectZerodha() async {
    setState(() => _kiteConnecting = true);
    try {
      final api = ref.read(apiServiceProvider);
      final data = await api.getKiteLoginUrl();
      if (data['already_connected'] == true) {
        ref.invalidate(kiteStatusProvider);
        setState(() => _kiteConnecting = false);
        return;
      }
      final url = data['login_url'] as String?;
      if (url != null && url.isNotEmpty) {
        await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
        int attempts = 0;
        Timer.periodic(const Duration(seconds: 2), (timer) async {
          attempts++;
          if (attempts > 60) {
            timer.cancel();
            if (mounted) setState(() => _kiteConnecting = false);
            return;
          }
          try {
            final check = await api.kiteCheck();
            if (check['connected'] == true) {
              timer.cancel();
              ref.invalidate(kiteStatusProvider);
              ref.invalidate(portfolioProvider);
              if (mounted) setState(() => _kiteConnecting = false);
            }
          } catch (_) {}
        });
      } else {
        setState(() => _kiteConnecting = false);
      }
    } catch (_) {
      setState(() => _kiteConnecting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final kiteAsync = ref.watch(kiteStatusProvider);
    final kiteConnected = kiteAsync.maybeWhen(
      data: (d) => d['connected'] == true,
      orElse: () => false,
    );

    return Column(children: [
      _ZerodhaConnectionBanner(
        c: c,
        kiteConnected: kiteConnected,
        kiteConnecting: _kiteConnecting,
        onConnect: _connectZerodha,
      ),
      Container(
        decoration: BoxDecoration(
          color: c.bg1,
          border: Border(bottom: BorderSide(color: c.bd)),
        ),
        child: Row(children: [
          Expanded(
            child: TabBar(
              controller: _tabCtrl,
              labelColor: c.accent,
              unselectedLabelColor: c.t3,
              indicatorColor: c.accent,
              indicatorWeight: 2,
              labelStyle: AppTextStyles.label(c.accent).copyWith(fontSize: 12),
              tabs: const [
                Tab(icon: Icon(LucideIcons.layoutDashboard, size: 16), text: 'Dashboard'),
                Tab(icon: Icon(LucideIcons.calendarClock, size: 16), text: '14-Day Desk'),
                Tab(icon: Icon(LucideIcons.target, size: 16), text: "Today's Focus List"),
                Tab(icon: Icon(LucideIcons.barChart3, size: 16), text: 'Swing Analysis'),
                Tab(icon: Icon(LucideIcons.wallet, size: 16), text: 'Paper Trading'),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: HeaderButton(
              icon: Icon(LucideIcons.trash2, size: 13, color: c.dn),
              text: 'Clear',
              onTap: () => _confirmResetAllSwingData(context, ref),
            ),
          ),
        ]),
      ),
      Expanded(
        child: TabBarView(
          controller: _tabCtrl,
          children: [
            _DashboardTab(
              onStockTap: (sym) {
                setState(() => _selectedSymbol = sym);
                _tabCtrl.animateTo(3);
              },
            ),
            _SwingDeskTab(
              onStockTap: (sym) {
                setState(() => _selectedSymbol = sym);
                _tabCtrl.animateTo(3);
              },
            ),
            _DailyPicksTab(
              kiteConnected: kiteConnected,
              onStockTap: (sym) {
                setState(() => _selectedSymbol = sym);
                _tabCtrl.animateTo(3);
              },
            ),
            _SwingAnalysisTab(
                symbol: _selectedSymbol,
                onSymbolChanged: (s) => setState(() => _selectedSymbol = s)),
            const _PaperTradingTab(),
          ],
        ),
      ),
    ]);
  }
}

/// Confirmation dialog + execution for the "Reset All Swing Data" action.
/// Clears saved daily picks/history, the 14-Day Desk, pending/open/closed
/// paper trades, equity history, and the in-memory scan cache for THIS user
/// only, then reinitializes a clean paper account. Never touches the real
/// portfolio, mutual funds, watchlist, or login data.
Future<void> _confirmResetAllSwingData(BuildContext context, WidgetRef ref) async {
  final c = context.colors;
  final ctrl = TextEditingController(text: '1000000');
  const clearedItems = [
    'Saved daily picks and daily-pick history',
    '14-Day Desk (active stocks and history)',
    'Pending, open, and closed paper trades',
    'Paper equity history',
    'In-memory swing scan cache',
  ];
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Reset All Swing Data'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('This permanently clears, for this account only:',
              style: AppTextStyles.bodySmall(c.t1).copyWith(fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          ...clearedItems.map((t) => Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('•  ', style: AppTextStyles.bodySmall(c.t2)),
                  Expanded(child: Text(t, style: AppTextStyles.bodySmall(c.t2))),
                ]),
              )),
          const SizedBox(height: 10),
          Text(
            'Your real portfolio, mutual funds, watchlist, and login are not affected.',
            style: AppTextStyles.captionXs(c.t3),
          ),
          const SizedBox(height: 14),
          TextField(
            controller: ctrl,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              labelText: 'New starting paper capital',
              prefixText: '₹ ',
              border: OutlineInputBorder(),
              isDense: true,
            ),
          ),
        ],
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: c.dn),
          onPressed: () => Navigator.pop(ctx, true),
          child: const Text('Reset Everything'),
        ),
      ],
    ),
  );
  if (confirmed != true) return;
  final capital = double.tryParse(ctrl.text.replaceAll(',', '').trim());

  try {
    final api = ref.read(apiServiceProvider);
    await api.resetAllSwingData(capital: (capital != null && capital > 0) ? capital : null);
    ref.invalidate(swingPicksProvider);
    ref.invalidate(swingDeskProvider);
    ref.invalidate(swingPaperStatusProvider);
    ref.invalidate(swingDeskFocusProvider);
    ref.invalidate(swingDailyPickHistoryProvider);
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('All Swing Trading data has been reset.')));
    }
  } catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Reset failed: $e')));
    }
  }
}

// ── Zerodha Connection Banner Widget ──
class _ZerodhaConnectionBanner extends StatelessWidget {
  final AppColorScheme c;
  final bool kiteConnected;
  final bool kiteConnecting;
  final VoidCallback onConnect;

  const _ZerodhaConnectionBanner({
    required this.c,
    required this.kiteConnected,
    required this.kiteConnecting,
    required this.onConnect,
  });

  @override
  Widget build(BuildContext context) {
    if (kiteConnected) {
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        decoration: BoxDecoration(
          color: c.upBg,
          border: Border(bottom: BorderSide(color: c.up.withValues(alpha: 0.2))),
        ),
        child: Row(children: [
          Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(shape: BoxShape.circle, color: c.up),
          ),
          const SizedBox(width: 8),
          Text('ZERODHA KITE CONNECTED', style: AppTextStyles.labelXs(c.up)),
          const SizedBox(width: 8),
          Text('· Real-time data active for swing analysis',
              style: AppTextStyles.captionXs(c.up.withValues(alpha: 0.75))),
          const Spacer(),
          Icon(LucideIcons.zap, size: 12, color: c.up.withValues(alpha: 0.7)),
        ]),
      );
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: c.goldBg,
        border: Border(bottom: BorderSide(color: c.gold.withValues(alpha: 0.25))),
      ),
      child: Row(children: [
        Icon(LucideIcons.alertTriangle, size: 14, color: c.gold),
        const SizedBox(width: 10),
        Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('ZERODHA KITE NOT CONNECTED', style: AppTextStyles.labelXs(c.gold)),
          const SizedBox(height: 2),
          Text(
              'Swing data comes from Zerodha Kite — a connected Kite session is required to scan and analyze.',
              style: AppTextStyles.captionXs(c.t3)),
        ])),
        const SizedBox(width: 12),
        HeaderButton(
          icon: const Icon(LucideIcons.power, size: 13, color: Colors.white),
          text: kiteConnecting ? 'Connecting…' : 'Connect Zerodha',
          solidColor: c.accent,
          loading: kiteConnecting,
          onTap: onConnect,
        ),
      ]),
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  TAB 0: DASHBOARD — the simple, plain-language "stock prediction
//  dashboard": today's picks (left), 14-day tracking (right), and full
//  pick history (bottom). No jargon, no charts — big text and short labels.
//  Reuses the exact same data/providers as the 14-Day Desk and Today's
//  Focus List tabs; this is a friendlier front door, not a new data source.
// ══════════════════════════════════════════════════════════════

bool _isNseMarketOpenNowIst() {
  final istNow = DateTime.now().toUtc().add(const Duration(hours: 5, minutes: 30));
  if (istNow.weekday == DateTime.saturday || istNow.weekday == DateTime.sunday) {
    return false;
  }
  final minutesSinceMidnight = istNow.hour * 60 + istNow.minute;
  return minutesSinceMidnight >= (9 * 60 + 15) && minutesSinceMidnight <= (15 * 60 + 30);
}

class _MarketClosedBanner extends StatelessWidget {
  const _MarketClosedBanner();
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: c.bg3,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: c.bd),
      ),
      child: Row(children: [
        Icon(LucideIcons.moon, size: 12, color: c.t3),
        const SizedBox(width: 6),
        Expanded(
          child: Text(
            "Markets are closed — showing the latest scan from open hours "
            '(NSE: Mon–Fri, 9:15am–3:30pm IST).',
            style: AppTextStyles.captionXs(c.t3),
          ),
        ),
      ]),
    );
  }
}

/// A labeled stat with an info tooltip explaining the plain-language meaning.
class _StatChip extends StatelessWidget {
  final String label;
  final String value;
  final Color valueColor;
  final String tooltip;
  const _StatChip({
    required this.label,
    required this.value,
    required this.valueColor,
    required this.tooltip,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Tooltip(
      message: tooltip,
      waitDuration: const Duration(milliseconds: 300),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(color: c.bg3, borderRadius: BorderRadius.circular(8)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
          Row(mainAxisSize: MainAxisSize.min, children: [
            Text(label, style: AppTextStyles.captionXs(c.t3)),
            const SizedBox(width: 3),
            Icon(LucideIcons.info, size: 10, color: c.t4),
          ]),
          Text(value, style: AppTextStyles.label(valueColor).copyWith(fontWeight: FontWeight.w700)),
        ]),
      ),
    );
  }
}

class _DashboardTab extends ConsumerWidget {
  final void Function(String symbol) onStockTap;
  const _DashboardTab({required this.onStockTap});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListView(padding: const EdgeInsets.only(top: 12), children: [
      AnimatedListItem(
        index: 0,
        child: LayoutBuilder(builder: (context, constraints) {
          final left = _ConsiderToBuyPanel(onStockTap: onStockTap);
          final right = _FocusDashboardPanelV2(onStockTap: onStockTap);
          if (constraints.maxWidth <= 860) {
            return Column(children: [left, const SizedBox(height: 12), right]);
          }
          return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(flex: 5, child: left),
            const SizedBox(width: 12),
            Expanded(flex: 6, child: right),
          ]);
        }),
      ),
      const SizedBox(height: 12),
      AnimatedListItem(index: 1, child: const _DailyPickHistoryPanel()),
      const SizedBox(height: 24),
    ]);
  }
}

// ── Left panel: "Today: Consider to Buy" ──
class _ConsiderToBuyPanel extends ConsumerWidget {
  final void Function(String symbol) onStockTap;
  const _ConsiderToBuyPanel({required this.onStockTap});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final asyncPicks = ref.watch(swingPicksProvider);
    final marketOpen = _isNseMarketOpenNowIst();
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: c.up.withValues(alpha: 0.35), width: 1.5),
      ),
      child: DenseCard(
        clip: true,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          denseTableHeader(
            context,
            icon: LucideIcons.trendingUp,
            accent: c.up,
            title: 'Today: Consider to Buy',
            subtitle: "Our top 5 picks most likely to gain 5% or more — "
                'ranked strongest to weakest',
          ),
          const Padding(
            padding: EdgeInsets.fromLTRB(12, 0, 12, 8),
            child: _PredictionDisclaimerBanner(),
          ),
          asyncPicks.when(
            loading: () => const Padding(
              padding: EdgeInsets.symmetric(vertical: 40),
              child: DensePulseLoader(label: "Finding today's best opportunities…"),
            ),
            error: (e, _) => Padding(
              padding: const EdgeInsets.all(16),
              child: ErrorRetry(
                title: "Could not load today's picks",
                detail: '$e',
                compact: true,
                onRetry: () => ref.invalidate(swingPicksProvider),
              ),
            ),
            data: (data) {
              final picks = List<Map<String, dynamic>>.from(data['picks'] ?? const []);
              final scanning = data['scanning'] == true;
              if (picks.isEmpty && scanning) {
                return const Padding(
                  padding: EdgeInsets.symmetric(vertical: 40),
                  child: DensePulseLoader(label: 'Scanning the market for opportunities…'),
                );
              }
              if (picks.isEmpty) {
                return Padding(
                  padding: const EdgeInsets.all(16),
                  child: DenseEmptyCard(
                    icon: marketOpen ? LucideIcons.searchX : LucideIcons.moon,
                    title: marketOpen ? 'No strong setups today' : 'Markets are closed',
                    sub: marketOpen
                        ? "No stock cleared today's 5%+ predicted-gain bar. Check back tomorrow."
                        : "NSE trades Mon–Fri, 9:15am–3:30pm IST. Check back when markets reopen.",
                  ),
                );
              }
              // Only READY_TO_BUY / NEAR_BUY_ZONE may show as a fresh buy
              // opportunity here (isFreshBuyOpportunity). A pick with no
              // actionable_status at all (older saved data) is treated as
              // still fresh for back-compat.
              final fresh = picks.where((p) {
                final raw = p['actionable_status']?.toString();
                return raw == null || isFreshBuyOpportunity(actionableStatusFrom(raw));
              }).toList();
              final waiting = picks
                  .where((p) => actionableStatusFrom(p['actionable_status']?.toString()) ==
                      ActionableStatus.waitForEntry)
                  .toList();
              final excluded = picks.where((p) {
                final s = actionableStatusFrom(p['actionable_status']?.toString());
                return s == ActionableStatus.missedEntry ||
                    s == ActionableStatus.targetAlreadyReached ||
                    s == ActionableStatus.invalid ||
                    s == ActionableStatus.dataStale;
              }).toList();
              return Column(children: [
                if (!marketOpen)
                  const Padding(
                    padding: EdgeInsets.fromLTRB(12, 0, 12, 8),
                    child: _MarketClosedBanner(),
                  ),
                if (fresh.isEmpty)
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: DenseEmptyCard(
                      icon: LucideIcons.searchX,
                      title: 'Nothing actionable right now',
                      sub: waiting.isNotEmpty
                          ? "Today's setups moved before we could show them — "
                              'see "Waiting for Entry" below.'
                          : "Today's setups already played out (missed or target "
                              'reached) — check back tomorrow.',
                    ),
                  )
                else
                  ...fresh.take(5).toList().asMap().entries.map((e) => _ConsiderToBuyCard(
                        rank: e.key + 1,
                        pick: e.value,
                        onTap: () => onStockTap(e.value['symbol']?.toString() ?? ''),
                      )),
                if (waiting.isNotEmpty)
                  _WaitingForEntrySection(picks: waiting, onTap: onStockTap),
                if (excluded.isNotEmpty)
                  _ExcludedSetupsSection(picks: excluded, onTap: onStockTap),
              ]);
            },
          ),
          const SizedBox(height: 8),
        ]),
      ),
    );
  }
}

class _ConsiderToBuyCard extends StatelessWidget {
  final int rank;
  final Map<String, dynamic> pick;
  final VoidCallback onTap;
  const _ConsiderToBuyCard({required this.rank, required this.pick, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final symbol = pick['symbol']?.toString() ?? '';
    final name = pick['name']?.toString() ?? symbol.replaceAll('.NS', '');
    final price = (pick['price'] as num?)?.toDouble();
    final signalPrice = (pick['current_price_at_signal'] as num?)?.toDouble() ?? price;
    final livePrice = (pick['live_price'] as num?)?.toDouble();
    final signalTs = pick['signal_timestamp']?.toString();
    final status = actionableStatusFrom(pick['actionable_status']?.toString());
    final predictedGain = (pick['predicted_gain_pct'] as num?)?.toDouble();
    final confidence = (pick['prediction_confidence'] as num?)?.toInt() ??
        (pick['score'] as num?)?.toInt();
    final entryLow = (pick['buy_zone_low'] as num?)?.toDouble() ??
        (pick['entry_range_low'] as num?)?.toDouble();
    final entryHigh = (pick['buy_zone_high'] as num?)?.toDouble() ??
        (pick['entry_range_high'] as num?)?.toDouble();
    final target = (pick['predicted_target_price'] as num?)?.toDouble();
    final stop = (pick['stop_loss'] as num?)?.toDouble();
    final riskLevel = pick['risk_level']?.toString() ?? 'Medium';
    final riskColor = riskLevel == 'Low' ? c.up : riskLevel == 'High' ? c.dn : c.gold;
    final confidenceLabel = confidence == null
        ? '—'
        : confidence >= 80
            ? 'High'
            : confidence >= 60
                ? 'Medium'
                : 'Low';

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        margin: const EdgeInsets.fromLTRB(12, 0, 12, 10),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: c.bg2,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: c.bd),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Container(
              width: 28,
              height: 28,
              alignment: Alignment.center,
              decoration: BoxDecoration(color: c.up.withValues(alpha: 0.15), shape: BoxShape.circle),
              child: Text('#$rank',
                  style: AppTextStyles.labelXs(c.up).copyWith(fontWeight: FontWeight.w800)),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(name, style: AppTextStyles.heading3(c.t1)),
                Text(symbol.replaceAll('.NS', ''), style: AppTextStyles.captionXs(c.t3)),
              ]),
            ),
            ActionableStatusBadge(status: status),
          ]),
          const SizedBox(height: 10),
          Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Text(livePrice != null ? '₹${livePrice.toStringAsFixed(2)}' : '—',
                style: AppTextStyles.stat2xl(c.t1)),
            const SizedBox(width: 8),
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text('live price', style: AppTextStyles.captionXs(c.t3)),
            ),
          ]),
          const SizedBox(height: 2),
          Text(
            'Signal price ₹${signalPrice?.toStringAsFixed(2) ?? '—'}'
            '${signalTs != null ? ' at ${signalTs.replaceFirst('T', ' ').substring(0, signalTs.length > 16 ? 16 : signalTs.length)}' : ''}',
            style: AppTextStyles.captionXs(c.t3),
          ),
          const SizedBox(height: 10),
          Wrap(spacing: 10, runSpacing: 8, children: [
            _StatChip(
              label: 'Predicted Gain',
              value: predictedGain != null ? '+${predictedGain.toStringAsFixed(1)}%' : '—',
              valueColor: c.up,
              tooltip: 'Our estimate of how much this stock could rise. '
                  'This is not a guarantee.',
            ),
            _StatChip(
              label: 'Confidence',
              value: '$confidenceLabel${confidence != null ? ' ($confidence/100)' : ''}',
              valueColor: c.t1,
              tooltip: "How strongly our system's technical scoring supports "
                  'this pick, from 0 (weak) to 100 (strong).',
            ),
            _StatChip(
              label: 'Entry Range',
              value: entryLow != null && entryHigh != null
                  ? '₹${entryLow.toStringAsFixed(2)}–₹${entryHigh.toStringAsFixed(2)}'
                  : '—',
              valueColor: c.t1,
              tooltip: 'The price band where buying is considered reasonable — '
                  "close to today's signal price.",
            ),
            _StatChip(
              label: 'Target',
              value: target != null ? '₹${target.toStringAsFixed(2)} (est.)' : '—',
              valueColor: c.up,
              tooltip: 'An estimated price where the position could be reviewed '
                  'for profit. Not a guaranteed exit — this strategy actually '
                  'holds up to 20 trading sessions with no fixed profit target.',
            ),
            _StatChip(
              label: 'Stop-Loss',
              value: stop != null ? '₹${stop.toStringAsFixed(2)}' : '—',
              valueColor: c.dn,
              tooltip: 'The price at which the position is exited to limit losses.',
            ),
            Tooltip(
              message: 'How much this trade could swing against you before the '
                  'stop-loss triggers. Low / Medium / High.',
              waitDuration: const Duration(milliseconds: 300),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: riskColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: riskColor.withValues(alpha: 0.3)),
                ),
                child: Text('Risk: $riskLevel', style: AppTextStyles.labelXs(riskColor)),
              ),
            ),
          ]),
        ]),
      ),
    );
  }
}

/// Stocks whose current price is below the buy zone — waiting for entry, not
/// a fresh buy opportunity yet. Kept visible for transparency, never mixed
/// into "Consider to Buy".
class _WaitingForEntrySection extends StatelessWidget {
  final List<Map<String, dynamic>> picks;
  final void Function(String symbol) onTap;
  const _WaitingForEntrySection({required this.picks, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 10),
      child: Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: c.bg2,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: c.blue.withValues(alpha: 0.3)),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(LucideIcons.clock, size: 13, color: c.blue),
            const SizedBox(width: 6),
            Text('Waiting for Entry (${picks.length})',
                style: AppTextStyles.label(c.blue)),
          ]),
          const SizedBox(height: 6),
          ...picks.map((p) {
            final symbol = p['symbol']?.toString() ?? '';
            final low = (p['buy_zone_low'] as num?)?.toDouble();
            final high = (p['buy_zone_high'] as num?)?.toDouble();
            final signalPrice = (p['current_price_at_signal'] as num?)?.toDouble();
            return InkWell(
              onTap: () => onTap(symbol),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(children: [
                  Expanded(
                    child: Text(symbol.replaceAll('.NS', ''), style: AppTextStyles.bodySmall(c.t1)),
                  ),
                  Text(
                    'now ₹${signalPrice?.toStringAsFixed(2) ?? '—'} · zone '
                    '₹${low?.toStringAsFixed(2) ?? '—'}–₹${high?.toStringAsFixed(2) ?? '—'}',
                    style: AppTextStyles.captionXs(c.t3),
                  ),
                ]),
              ),
            );
          }),
        ]),
      ),
    );
  }
}

/// Missed / target-already-reached / invalid setups — shown collapsed for
/// transparency only. Never a buy recommendation.
class _ExcludedSetupsSection extends StatefulWidget {
  final List<Map<String, dynamic>> picks;
  final void Function(String symbol) onTap;
  const _ExcludedSetupsSection({required this.picks, required this.onTap});
  @override
  State<_ExcludedSetupsSection> createState() => _ExcludedSetupsSectionState();
}

class _ExcludedSetupsSectionState extends State<_ExcludedSetupsSection> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
      child: Container(
        decoration: BoxDecoration(
          color: c.bg2,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: c.bd),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          InkWell(
            onTap: () => setState(() => _open = !_open),
            child: Padding(
              padding: const EdgeInsets.all(10),
              child: Row(children: [
                Icon(_open ? LucideIcons.chevronUp : LucideIcons.chevronDown,
                    size: 13, color: c.t3),
                const SizedBox(width: 6),
                Text('Excluded today (${widget.picks.length}) — do not chase',
                    style: AppTextStyles.label(c.t3)),
              ]),
            ),
          ),
          if (_open)
            Padding(
              padding: const EdgeInsets.fromLTRB(10, 0, 10, 10),
              child: Column(children: widget.picks.map((p) {
                final symbol = p['symbol']?.toString() ?? '';
                final status = actionableStatusFrom(p['actionable_status']?.toString());
                return InkWell(
                  onTap: () => widget.onTap(symbol),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Row(children: [
                      Expanded(
                        child: Text(symbol.replaceAll('.NS', ''), style: AppTextStyles.bodySmall(c.t1)),
                      ),
                      ActionableStatusBadge(status: status),
                    ]),
                  ),
                );
              }).toList()),
            ),
        ]),
      ),
    );
  }
}

// ── Right panel: "14-Day Focus Dashboard" ──
enum _FocusFilter { active, winners, losers, completed }

class _FilterChip extends StatelessWidget {
  final String label;
  final int count;
  final bool selected;
  final Color? color;
  final VoidCallback onTap;
  const _FilterChip({
    required this.label,
    required this.count,
    required this.selected,
    required this.onTap,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final chipColor = color ?? c.accent;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: selected ? chipColor.withValues(alpha: 0.15) : c.bg3,
          border: Border.all(color: selected ? chipColor.withValues(alpha: 0.5) : c.bd),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text('$label ($count)',
            style: AppTextStyles.labelXs(selected ? chipColor : c.t2)),
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  final String status;
  const _StatusBadge({required this.status});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final (label, color) = switch (status) {
      'BUY' => ('Ready to Buy', c.up),
      'HOLD' => ('Holding', c.blue),
      'WAIT' => ('Watching', c.t3),
      'AVOID' => ('Avoid', c.gold),
      'EXIT' => ('Exit Now', c.dn),
      'EXPIRED' => ('Completed', c.t3),
      _ => (status, c.t3),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(6)),
      child: Text(label, style: AppTextStyles.labelXs(color)),
    );
  }
}

class _HitTag extends StatelessWidget {
  final String label;
  final Color color;
  const _HitTag({required this.label, required this.color});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: color.withValues(alpha: 0.4)),
        ),
        child: Text(label,
            style: AppTextStyles.captionXs(color).copyWith(fontWeight: FontWeight.w700)),
      );
}

class _FocusRow extends StatelessWidget {
  final Map<String, dynamic> stock;
  final bool alt;
  final void Function(String symbol) onTap;
  const _FocusRow({required this.stock, required this.alt, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final symbol = stock['symbol']?.toString() ?? '';
    final name = stock['name']?.toString() ?? symbol.replaceAll('.NS', '');
    final pnl = (stock['price_change_pct'] as num?)?.toDouble();
    final trackingDay = (stock['tracking_day'] as num?)?.toInt();
    final status = stock['tracking_status']?.toString() ?? 'WAIT';
    final entryPrice = (stock['original_price'] as num?)?.toDouble() ??
        (stock['original_entry'] as num?)?.toDouble();
    final currentPrice = (stock['current_price'] as num?)?.toDouble();
    final stop = (stock['original_stop_loss'] as num?)?.toDouble();
    final stopHit = currentPrice != null && stop != null && currentPrice <= stop;
    final predictedGainPct = (stock['predicted_gain_pct'] as num?)?.toDouble();
    final targetPrice = predictedGainPct != null && entryPrice != null
        ? entryPrice * (1 + predictedGainPct / 100)
        : null;
    final targetHit = currentPrice != null && targetPrice != null && currentPrice >= targetPrice;
    final pnlColor = pnl == null
        ? c.t3
        : pnl > 0
            ? c.up
            : pnl < 0
                ? c.dn
                : c.t3;

    return InkWell(
      onTap: () => onTap(symbol),
      child: Container(
        color: alt ? c.rowAlt : null,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(
                child: Text('$name (${symbol.replaceAll('.NS', '')})',
                    style: AppTextStyles.label(c.t1))),
            _StatusBadge(status: status),
          ]),
          const SizedBox(height: 4),
          Wrap(spacing: 14, runSpacing: 4, children: [
            if (trackingDay != null)
              Text('Day $trackingDay of 14', style: AppTextStyles.captionXs(c.t3)),
            if (stock['selected_date'] != null)
              Text('Picked ${stock['selected_date']}', style: AppTextStyles.captionXs(c.t3)),
            Text('Entry ₹${entryPrice?.toStringAsFixed(2) ?? '—'}',
                style: AppTextStyles.captionXs(c.t3)),
            Text('Now ₹${currentPrice?.toStringAsFixed(2) ?? '—'}',
                style: AppTextStyles.captionXs(c.t2)),
            Text(pnl != null ? '${pnl >= 0 ? '+' : ''}${pnl.toStringAsFixed(1)}%' : '—',
                style: AppTextStyles.labelXs(pnlColor).copyWith(fontWeight: FontWeight.w700)),
            if (stopHit) _HitTag(label: 'STOP-LOSS HIT', color: c.dn),
            if (targetHit) _HitTag(label: 'TARGET HIT', color: c.up),
          ]),
        ]),
      ),
    );
  }
}

class _FocusDashboardPanelV2 extends ConsumerStatefulWidget {
  final void Function(String symbol) onStockTap;
  const _FocusDashboardPanelV2({required this.onStockTap});
  @override
  ConsumerState<_FocusDashboardPanelV2> createState() => _FocusDashboardPanelV2State();
}

class _FocusDashboardPanelV2State extends ConsumerState<_FocusDashboardPanelV2> {
  _FocusFilter _filter = _FocusFilter.active;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final asyncDesk = ref.watch(swingDeskProvider);
    return DenseCard(
      clip: true,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        denseTableHeader(
          context,
          icon: LucideIcons.listChecks,
          accent: c.accent,
          title: '14-Day Focus Dashboard',
          subtitle: "Stocks we're tracking for up to 14 trading days, "
              'sorted by actual profit',
        ),
        asyncDesk.when(
          loading: () => const Padding(
            padding: EdgeInsets.symmetric(vertical: 40),
            child: DensePulseLoader(label: 'Loading tracked stocks…'),
          ),
          error: (e, _) => Padding(
            padding: const EdgeInsets.all(16),
            child: ErrorRetry(
              title: 'Could not load the dashboard',
              detail: '$e',
              compact: true,
              onRetry: () => ref.invalidate(swingDeskProvider),
            ),
          ),
          data: (desk) {
            if (desk['error'] != null) {
              return Padding(
                padding: const EdgeInsets.all(16),
                child: ErrorRetry(
                  title: 'Dashboard unavailable',
                  detail: desk['error'].toString(),
                  compact: true,
                  onRetry: () => ref.invalidate(swingDeskProvider),
                ),
              );
            }
            final batches = List<Map<String, dynamic>>.from(desk['batches'] ?? const []);
            final historyRaw = List<Map<String, dynamic>>.from(desk['history'] ?? const []);
            final allTracked = <Map<String, dynamic>>[
              for (final b in batches) ...List<Map<String, dynamic>>.from(b['stocks'] ?? const []),
            ];
            final merged = SwingDeskLogic.focusDashboardWithHistory(allTracked, historyRaw);

            if (merged.isEmpty) {
              return const Padding(
                padding: EdgeInsets.all(16),
                child: DenseEmptyCard(
                  icon: LucideIcons.calendarClock,
                  title: 'Nothing tracked yet',
                  sub: 'Stocks from "Today: Consider to Buy" are added here '
                      'automatically and tracked for 14 trading days.',
                ),
              );
            }

            bool isWinner(Map<String, dynamic> s) {
              final p = s['price_change_pct'] as num?;
              return p != null && p > 0;
            }

            bool isLoser(Map<String, dynamic> s) {
              final p = s['price_change_pct'] as num?;
              return p != null && p < 0;
            }

            final activeCount = merged.where((s) => s['completed'] != true).length;
            final winnersCount = merged.where(isWinner).length;
            final losersCount = merged.where(isLoser).length;
            final completedCount = merged.where((s) => s['completed'] == true).length;

            final filtered = switch (_filter) {
              _FocusFilter.active => merged.where((s) => s['completed'] != true).toList(),
              _FocusFilter.winners => merged.where(isWinner).toList(),
              _FocusFilter.losers => merged.where(isLoser).toList(),
              _FocusFilter.completed => merged.where((s) => s['completed'] == true).toList(),
            };

            return Column(children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
                child: Wrap(spacing: 8, runSpacing: 8, children: [
                  _FilterChip(
                    label: 'Active',
                    count: activeCount,
                    selected: _filter == _FocusFilter.active,
                    onTap: () => setState(() => _filter = _FocusFilter.active),
                  ),
                  _FilterChip(
                    label: 'Winners',
                    count: winnersCount,
                    color: c.up,
                    selected: _filter == _FocusFilter.winners,
                    onTap: () => setState(() => _filter = _FocusFilter.winners),
                  ),
                  _FilterChip(
                    label: 'Losers',
                    count: losersCount,
                    color: c.dn,
                    selected: _filter == _FocusFilter.losers,
                    onTap: () => setState(() => _filter = _FocusFilter.losers),
                  ),
                  _FilterChip(
                    label: 'Completed',
                    count: completedCount,
                    selected: _filter == _FocusFilter.completed,
                    onTap: () => setState(() => _filter = _FocusFilter.completed),
                  ),
                ]),
              ),
              if (filtered.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 24),
                  child: Text('No stocks in this view.', style: AppTextStyles.bodySmall(c.t3)),
                )
              else
                ...filtered.asMap().entries.map((e) => _FocusRow(
                      stock: e.value,
                      alt: e.key.isOdd,
                      onTap: widget.onStockTap,
                    )),
            ]);
          },
        ),
        const SizedBox(height: 8),
      ]),
    );
  }
}

// ── Bottom section: "Daily Pick History" ──
class _DailyPickHistoryPanel extends ConsumerStatefulWidget {
  const _DailyPickHistoryPanel();
  @override
  ConsumerState<_DailyPickHistoryPanel> createState() => _DailyPickHistoryPanelState();
}

class _DailyPickHistoryPanelState extends ConsumerState<_DailyPickHistoryPanel> {
  String _dateFilter = '';
  String _symbolFilter = '';

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final async = ref.watch(swingDailyPickHistoryProvider);
    return DenseCard(
      clip: true,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        denseTableHeader(
          context,
          icon: LucideIcons.history,
          accent: c.t2,
          title: 'Daily Pick History',
          subtitle: "Every day's picks, with how they actually performed",
          trailing: HeaderButton(
            icon: Icon(LucideIcons.trash2, size: 13, color: c.dn),
            text: 'Clear',
            onTap: () => _confirmResetAllSwingData(context, ref),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
          child: Row(children: [
            Expanded(
              child: TextField(
                style: AppTextStyles.bodySmall(c.t1),
                decoration: InputDecoration(
                  isDense: true,
                  hintText: 'Filter by date (YYYY-MM-DD)',
                  hintStyle: AppTextStyles.bodySmall(c.t4),
                  prefixIcon: Icon(LucideIcons.calendar, size: 14, color: c.t3),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                ),
                onChanged: (v) => setState(() => _dateFilter = v.trim()),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: TextField(
                style: AppTextStyles.bodySmall(c.t1),
                decoration: InputDecoration(
                  isDense: true,
                  hintText: 'Filter by symbol',
                  hintStyle: AppTextStyles.bodySmall(c.t4),
                  prefixIcon: Icon(LucideIcons.search, size: 14, color: c.t3),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                ),
                onChanged: (v) => setState(() => _symbolFilter = v.trim().toUpperCase()),
              ),
            ),
          ]),
        ),
        async.when(
          loading: () => const Padding(
            padding: EdgeInsets.symmetric(vertical: 40),
            child: DensePulseLoader(label: 'Loading history…'),
          ),
          error: (e, _) => Padding(
            padding: const EdgeInsets.all(16),
            child: ErrorRetry(
              title: 'Could not load history',
              detail: '$e',
              compact: true,
              onRetry: () => ref.invalidate(swingDailyPickHistoryProvider),
            ),
          ),
          data: (data) {
            final dates = List<Map<String, dynamic>>.from(data['dates'] ?? const []);
            var filteredDates = dates;
            if (_dateFilter.isNotEmpty) {
              filteredDates = filteredDates
                  .where((d) => (d['date']?.toString() ?? '').contains(_dateFilter))
                  .toList();
            }
            if (_symbolFilter.isNotEmpty) {
              filteredDates = filteredDates
                  .map((d) => {
                        'date': d['date'],
                        'picks': List<Map<String, dynamic>>.from(d['picks'] ?? const [])
                            .where((p) =>
                                (p['symbol']?.toString() ?? '').toUpperCase().contains(_symbolFilter))
                            .toList(),
                      })
                  .where((d) => (d['picks'] as List).isNotEmpty)
                  .toList();
            }
            if (filteredDates.isEmpty) {
              return const Padding(
                padding: EdgeInsets.all(16),
                child: DenseEmptyCard(
                  icon: LucideIcons.calendarX,
                  title: 'No pick history yet',
                  sub: "Once the system selects daily picks, they'll show up "
                      'here grouped by date.',
                ),
              );
            }
            return Column(
              children: filteredDates
                  .map((d) => _DateHistoryTile(
                        date: d['date'].toString(),
                        picks: List<Map<String, dynamic>>.from(d['picks']),
                      ))
                  .toList(),
            );
          },
        ),
        const SizedBox(height: 8),
      ]),
    );
  }
}

class _DateHistoryTile extends StatelessWidget {
  final String date;
  final List<Map<String, dynamic>> picks;
  const _DateHistoryTile({required this.date, required this.picks});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final trackedCount = picks.where((p) => p['tracked'] == true).length;
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        tilePadding: const EdgeInsets.symmetric(horizontal: 12),
        leading: Icon(LucideIcons.calendarDays, size: 15, color: c.t3),
        title: Text(date, style: AppTextStyles.label(c.t1)),
        subtitle:
            Text('${picks.length} picks · $trackedCount tracked', style: AppTextStyles.captionXs(c.t3)),
        children: picks.map((p) => _HistoryPickRow(pick: p)).toList(),
      ),
    );
  }
}

class _HistoryPickRow extends StatelessWidget {
  final Map<String, dynamic> pick;
  const _HistoryPickRow({required this.pick});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final symbol = pick['symbol']?.toString() ?? '';
    final predictedGain = (pick['predicted_gain_pct'] as num?)?.toDouble();
    final actual = (pick['actual_profit_pct'] as num?)?.toDouble();
    final finalResult = (pick['final_result_pct'] as num?)?.toDouble();
    final tracked = pick['tracked'] == true;
    final daySnaps = Map<String, dynamic>.from(pick['day_snapshots'] ?? const {});
    final elsewhere = pick['tracked_elsewhere_date']?.toString();
    final trackingDay = (pick['tracking_day'] as num?)?.toInt();
    final isLive = pick['live_price'] != null;
    Color pnlColor(double? v) => v == null
        ? c.t3
        : v > 0
            ? c.up
            : v < 0
                ? c.dn
                : c.t3;

    Widget dayCol(String label, String key) {
      final snap = daySnaps[key] as Map?;
      final pct = (snap?['profit_pct'] as num?)?.toDouble();
      return Column(children: [
        Text(label, style: AppTextStyles.captionXs(c.t4)),
        Text(pct != null ? '${pct >= 0 ? '+' : ''}${pct.toStringAsFixed(1)}%' : '—',
            style: AppTextStyles.monoXs(pnlColor(pct))),
      ]);
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(symbol.replaceAll('.NS', ''), style: AppTextStyles.label(c.t1))),
          if (!tracked)
            Text(
                elsewhere != null && elsewhere.isNotEmpty
                    ? 'Already tracked from $elsewhere'
                    : 'Not tracked',
                style: AppTextStyles.captionXs(c.t4))
          else
            Text(
                actual != null
                    ? '${actual >= 0 ? '+' : ''}${actual.toStringAsFixed(1)}%'
                        '${isLive ? ' live' : ' so far'}'
                    : 'Tracking…',
                style: AppTextStyles.labelXs(pnlColor(actual))),
        ]),
        const SizedBox(height: 2),
        Text(
            'Predicted +${predictedGain?.toStringAsFixed(1) ?? '—'}%'
            '${tracked && trackingDay != null ? ' · day $trackingDay of 14' : ''}',
            style: AppTextStyles.captionXs(c.t3)),
        if (tracked) ...[
          const SizedBox(height: 6),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            dayCol('Day 1', '1'),
            dayCol('Day 3', '3'),
            dayCol('Day 7', '7'),
            dayCol('Day 14', '14'),
          ]),
          if (finalResult != null)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                  'Final 14-day result: ${finalResult >= 0 ? '+' : ''}${finalResult.toStringAsFixed(1)}%',
                  style: AppTextStyles.labelXs(pnlColor(finalResult)).copyWith(fontWeight: FontWeight.w700)),
            ),
        ],
        const Divider(height: 16),
      ]),
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  TAB 1: 14-DAY SWING DESK — AI-selected, user-executed watchlist
//
//  Today's Picks are ideas; this desk is the system-selected watchlist
//  (best few per scan day, tracked 14 trading days); paper trades are
//  the user's choice from here. Nothing auto-buys unless the user arms
//  a specific stock and it then turns READY.
// ══════════════════════════════════════════════════════════════

String _deskRs(dynamic v) {
  final d = v is num ? v.toDouble() : null;
  if (d == null) return '—';
  return '₹${d.toStringAsFixed(d >= 1000 ? 0 : 2)}';
}

int? _deskInt(dynamic v) => v is num ? v.round() : null;

class _SwingDeskTab extends ConsumerWidget {
  final void Function(String symbol) onStockTap;
  const _SwingDeskTab({required this.onStockTap});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncDesk = ref.watch(swingDeskProvider);

    return asyncDesk.when(
      loading: () => const DensePulseLoader(label: 'Loading the 14-day desk…'),
      error: (e, _) => ErrorRetry(
        title: 'Failed to load the swing desk',
        detail: '$e',
        icon: LucideIcons.alertTriangle,
        compact: true,
        onRetry: () => ref.invalidate(swingDeskProvider),
      ),
      data: (desk) {
        if (desk['error'] != null) {
          return ErrorRetry(
            title: 'Swing desk unavailable',
            detail: desk['error'].toString(),
            icon: LucideIcons.alertTriangle,
            compact: true,
            onRetry: () => ref.invalidate(swingDeskProvider),
          );
        }
        final batches =
            List<Map<String, dynamic>>.from(desk['batches'] ?? const []);
        final history =
            List<Map<String, dynamic>>.from(desk['history'] ?? const []);
        final summary =
            Map<String, dynamic>.from(desk['summary'] as Map? ?? const {});

        // Top 5 focus across ALL day-batches (batches are newest-first, so
        // a symbol picked on two days keeps its freshest setup). The
        // day-wise batch cards below stay untouched.
        final allTracked = <Map<String, dynamic>>[
          for (final b in batches)
            ...List<Map<String, dynamic>>.from(b['stocks'] ?? const []),
        ];
        final topFocus = SwingDeskLogic.topFocus(allTracked);

        var idx = 0;
        return ListView(padding: const EdgeInsets.only(top: 12), children: [
          AnimatedListItem(
            index: idx++,
            child: _DeskSummaryCard(desk: desk, summary: summary),
          ),
          // Today's Focus (left, fresh entry candidates — server-driven with
          // live prices, exit-first priority; falls back to client-side
          // Top-Focus ranking if the endpoint fails) side by side with the
          // Focus Dashboard (right, every tracked stock sorted by actual
          // profit %). Stacks vertically below the 860px breakpoint. Day-wise
          // picks stay full-width at the bottom, untouched.
          AnimatedListItem(
            index: idx++,
            child: Padding(
              padding: const EdgeInsets.only(top: 12),
              child: LayoutBuilder(builder: (context, constraints) {
                final todaysFocus = Consumer(builder: (context, ref, _) {
                  final asyncFocus = ref.watch(swingDeskFocusProvider);
                  return asyncFocus.when(
                    data: (f) =>
                        _FocusNowCard(focus: f, onStockTap: onStockTap),
                    loading: () => const SizedBox.shrink(),
                    error: (_, _) => topFocus.isEmpty
                        ? const SizedBox.shrink()
                        : _TopFocusCard(
                            stocks: topFocus,
                            totalTracked: allTracked.length,
                            onStockTap: onStockTap,
                          ),
                  );
                });
                final focusDashboard = _FocusDashboardCard(
                  stocks: SwingDeskLogic.focusDashboard(allTracked),
                  onStockTap: onStockTap,
                );
                if (constraints.maxWidth <= 860) {
                  return Column(children: [
                    todaysFocus,
                    const SizedBox(height: 12),
                    focusDashboard,
                  ]);
                }
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: todaysFocus),
                    const SizedBox(width: 12),
                    Expanded(child: focusDashboard),
                  ],
                );
              }),
            ),
          ),
          if (batches.isEmpty)
            AnimatedListItem(
              index: idx++,
              child: const Padding(
                padding: EdgeInsets.only(top: 12),
                child: DenseEmptyCard(
                  icon: LucideIcons.calendarClock,
                  title: 'No stocks selected yet',
                  sub: 'Run Today\'s Picks, then tap "Auto-select from Today\'s '
                      'Picks" — the system keeps only the best few (max 5/day) '
                      'and tracks them here for 14 trading days.',
                ),
              ),
            )
          else
            ...batches.map((b) {
              final w = AnimatedListItem(
                index: idx++,
                child: _DeskBatchCard(batch: b, onStockTap: onStockTap),
              );
              return Padding(padding: const EdgeInsets.only(top: 12), child: w);
            }),
          if (history.isNotEmpty) ...[
            const SizedBox(height: 12),
            AnimatedListItem(index: idx++, child: _DeskHistoryCard(history: history)),
          ],
          const SizedBox(height: 24),
        ]);
      },
    );
  }
}

class _DeskSummaryCard extends ConsumerStatefulWidget {
  final Map<String, dynamic> desk;
  final Map<String, dynamic> summary;
  const _DeskSummaryCard({required this.desk, required this.summary});
  @override
  ConsumerState<_DeskSummaryCard> createState() => _DeskSummaryCardState();
}

class _DeskSummaryCardState extends ConsumerState<_DeskSummaryCard> {
  bool _busy = false;

  Future<void> _autoSelect() async {
    setState(() => _busy = true);
    try {
      final api = ref.read(apiServiceProvider);
      final res = await api.swingDeskAutoSelect();
      if (!mounted) return;
      final n = _deskInt(res['selected_count']) ?? 0;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(n > 0
            ? 'Selected $n stock(s) into the 14-Day Desk'
            : 'No picks passed the selection quality gate today'),
      ));
      ref.invalidate(swingDeskProvider);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Auto-select failed: $e')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final desk = widget.desk;
    final summary = widget.summary;
    final ready = _deskInt(desk['ready_count']) ?? 0;
    final active = _deskInt(desk['active_count']) ?? 0;

    Widget line(IconData icon, Color col, String label, String? text) {
      if (text == null || text.isEmpty) return const SizedBox.shrink();
      return Padding(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(icon, size: 13, color: col),
          const SizedBox(width: 8),
          SizedBox(width: 78, child: Text(label, style: AppTextStyles.labelXs(col))),
          Expanded(child: Text(text, style: AppTextStyles.bodySmall(c.t2))),
        ]),
      );
    }

    return DenseCard(
      clip: true,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        denseTableHeader(
          context,
          icon: LucideIcons.calendarClock,
          accent: c.accent,
          title: '14-Day Swing Desk',
          subtitle: '${desk['desk_date'] ?? ''} · $active tracked · $ready ready · '
              'system-selected watchlist — you choose what to paper trade',
          trailing: Row(mainAxisSize: MainAxisSize.min, children: [
            if (_busy)
              SizedBox(
                  width: 12,
                  height: 12,
                  child: CircularProgressIndicator(strokeWidth: 2, color: c.accent))
            else
              HeaderButton(
                icon: const Icon(LucideIcons.sparkles, size: 13, color: Colors.white),
                text: 'Auto-select',
                solidColor: c.accent,
                onTap: _autoSelect,
              ),
            const SizedBox(width: 8),
            HeaderButton(
              icon: Icon(LucideIcons.refreshCw, size: 13, color: c.accent),
              text: 'Re-analyze',
              onTap: () => ref.read(swingDeskKeyProvider.notifier).refresh(),
            ),
            const SizedBox(width: 8),
            HeaderButton(
              icon: Icon(LucideIcons.trash2, size: 13, color: c.dn),
              text: 'Clear',
              onTap: () => _confirmResetAllSwingData(context, ref),
            ),
          ]),
        ),
        const SizedBox(height: 8),
        line(LucideIcons.target, c.accent, 'TODAY',
            summary['best_action_today']?.toString()),
        line(LucideIcons.workflow, c.blue, 'FLOW',
            summary['how_it_works']?.toString()),
        line(LucideIcons.alertTriangle, c.gold, 'RISK',
            summary['risk_warning']?.toString()),
        const SizedBox(height: 4),
      ]),
    );
  }
}

/// "Top 5 Focus" — the best fresh-entry candidates ranked across every
/// tracked day-batch, so the user watches 5 instead of everything. Purely a
/// ranked view: the same stocks stay in their day-wise batch cards below.
// ── Focus Now: server-ranked entry ladder — 3 positions per stock ──
// Each stock shows P1 (the setup trigger), P2 (EMA20 pullback) and P3 (deep
// support) with its own trigger/zone/SL/T1-T3, plain-language condition, hit
// flags and live P/L from the trigger price. Live prices refresh every 5s.
class _FocusNowCard extends StatelessWidget {
  final Map<String, dynamic> focus;
  final void Function(String symbol) onStockTap;
  const _FocusNowCard({required this.focus, required this.onStockTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final stocks = List<Map<String, dynamic>>.from(
        (focus['stocks'] as List? ?? const []).map((e) => Map<String, dynamic>.from(e as Map)));
    if (stocks.isEmpty) return const SizedBox.shrink();
    final live = _deskInt(focus['live_prices']) ?? 0;
    final total = _deskInt(focus['total_symbols']) ?? 0;
    final source = focus['price_source']?.toString() ?? '';
    final updated = focus['updated_at']?.toString() ?? '';
    final hhmmss = updated.length >= 19 ? updated.substring(11, 19) : '';

    return DenseCard(
      clip: true,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        denseTableHeader(
          context,
          icon: LucideIcons.crosshair,
          accent: c.accent,
          title: 'Focus — Entry Ladder',
          subtitle: 'P1 setup trigger · P2 EMA20 pullback · P3 deep support — '
              '$live/$total live ($source · ${hhmmss.isNotEmpty ? hhmmss : '—'} · 5s)',
        ),
        ...stocks.asMap().entries.map((e) => _FocusStockSection(
              stock: e.value,
              alt: e.key.isOdd,
              onTap: () => onStockTap(e.value['symbol']?.toString() ?? ''),
            )),
      ]),
    );
  }
}

(String, Color) _focusVerdictMeta(BuildContext context, String v) {
  final c = context.colors;
  return switch (v) {
    'SELL_EXIT' => ('SELL / EXIT', c.dn),
    'HOLD' => ('HOLD', c.accent),
    'ENTER_NOW' => ('ENTER NOW', c.up),
    'MISSED_P1' => ('MISSED P1', c.gold),
    'NO_ENTRY' => ('NO ENTRY', c.t3),
    _ => ('WAIT', c.t3),
  };
}

(String, Color) _positionStateMeta(BuildContext context, String s) {
  final c = context.colors;
  return switch (s) {
    'FILLED' => ('FILLED', c.accent),
    'BUYABLE' => ('BUY NOW', c.up),
    'IN_ZONE' => ('AT TRIGGER', c.up),
    'SL_HIT' => ('SL HIT', c.dn),
    'T1_DONE' || 'T2_DONE' || 'T3_DONE' => ('TARGET DONE', c.gold),
    'MISSED' => ('MISSED', c.gold),
    _ => ('WAITING', c.t3),
  };
}

class _FocusStockSection extends StatelessWidget {
  final Map<String, dynamic> stock;
  final bool alt;
  final VoidCallback onTap;
  const _FocusStockSection(
      {required this.stock, required this.alt, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final (verdictLabel, verdictColor) =
        _focusVerdictMeta(context, stock['verdict']?.toString() ?? 'WAIT');
    final positions = List<Map<String, dynamic>>.from(
        (stock['positions'] as List? ?? const []).map((e) => Map<String, dynamic>.from(e as Map)));
    final isLive = stock['live'] == true;
    final rank = _deskInt(stock['rank']) ?? 0;

    return InkWell(
      onTap: onTap,
      child: Container(
        color: alt ? c.rowAlt : null,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          // ── Stock header: rank, name, verdict, LIVE price ──
          Row(children: [
            Container(
              width: 20,
              height: 18,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: c.accent.withValues(alpha: 0.12),
                border: Border.all(color: c.accent.withValues(alpha: 0.30)),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text('$rank',
                  style: AppTextStyles.monoXs(c.accent)
                      .copyWith(fontWeight: FontWeight.w700)),
            ),
            const SizedBox(width: 6),
            Text(stock['name']?.toString() ?? '',
                style: AppTextStyles.label(c.t1)),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: verdictColor.withValues(alpha: 0.12),
                border: Border.all(color: verdictColor.withValues(alpha: 0.35)),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(verdictLabel,
                  style: AppTextStyles.monoXs(verdictColor)
                      .copyWith(fontWeight: FontWeight.w700)),
            ),
            const Spacer(),
            Container(
              width: 6,
              height: 6,
              decoration: BoxDecoration(
                  shape: BoxShape.circle, color: isLive ? c.up : c.t3),
            ),
            const SizedBox(width: 4),
            Text('LIVE ${_deskRs(stock['ltp'])}',
                style: AppTextStyles.monoXs(c.t1)
                    .copyWith(fontWeight: FontWeight.w700)),
          ]),
          const SizedBox(height: 2),
          Text(stock['verdict_text']?.toString() ?? '',
              style: AppTextStyles.captionXs(verdictColor)),
          if (positions.isNotEmpty) ...[
            const SizedBox(height: 6),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: _PositionTable(positions: positions),
            ),
          ],
        ]),
      ),
    );
  }
}

class _PositionTable extends StatelessWidget {
  final List<Map<String, dynamic>> positions;
  const _PositionTable({required this.positions});

  static const _headers = [
    'Position', 'Trigger', 'Buy zone', 'Stop loss',
    'Target1', 'T2', 'T3', 'Condition', 'P/L (live)',
  ];
  static const _widths = <double>[92, 76, 118, 84, 76, 76, 76, 250, 120];

  Widget _cell(int col, Widget child) => SizedBox(
        width: _widths[col],
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 3),
          child: child,
        ),
      );

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        for (var i = 0; i < _headers.length; i++)
          _cell(i, Text(_headers[i], style: AppTextStyles.captionXs(c.t3))),
      ]),
      ...positions.map((p) {
        final state = p['state']?.toString() ?? 'WAITING';
        final (stateLabel, stateColor) = _positionStateMeta(context, state);
        final hits = Map<String, dynamic>.from(p['hits'] as Map? ?? const {});
        final plAbs = (p['pl_abs'] as num?)?.toDouble();
        final plPct = (p['pl_pct'] as num?)?.toDouble();
        final dist = (p['distance_to_trigger_pct'] as num?)?.toDouble();

        Widget target(String key, dynamic v) => Row(mainAxisSize: MainAxisSize.min, children: [
              Text(_deskRs(v), style: AppTextStyles.monoXs(c.up)),
              if (hits[key] == true)
                Padding(
                  padding: const EdgeInsets.only(left: 2),
                  child: Icon(LucideIcons.check, size: 10, color: c.up),
                ),
            ]);

        return Container(
          decoration: BoxDecoration(
            color: stateColor.withValues(alpha: state == 'WAITING' ? 0.0 : 0.05),
            border: Border(top: BorderSide(color: c.rowAlt, width: 1)),
          ),
          child: Row(children: [
            _cell(0, Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(p['position']?.toString() ?? '',
                  style: AppTextStyles.monoXs(c.t1)
                      .copyWith(fontWeight: FontWeight.w700)),
              Text(stateLabel,
                  style: AppTextStyles.monoXs(stateColor)
                      .copyWith(fontWeight: FontWeight.w700)),
            ])),
            _cell(1, Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(_deskRs(p['trigger']), style: AppTextStyles.monoXs(c.t1)),
              if (dist != null && state == 'WAITING')
                Text('${dist >= 0 ? '+' : ''}${dist.toStringAsFixed(1)}%',
                    style: AppTextStyles.captionXs(c.t3)),
            ])),
            _cell(2, Text('${_deskRs(p['buy_zone_low'])}–${_deskRs(p['buy_zone_high'])}',
                style: AppTextStyles.monoXs(c.t2))),
            _cell(3, Row(mainAxisSize: MainAxisSize.min, children: [
              Text(_deskRs(p['stop_loss']), style: AppTextStyles.monoXs(c.dn)),
              if (hits['sl'] == true)
                Padding(
                  padding: const EdgeInsets.only(left: 3),
                  child: Text('HIT',
                      style: AppTextStyles.monoXs(c.dn)
                          .copyWith(fontWeight: FontWeight.w700)),
                ),
            ])),
            _cell(4, target('t1', p['target1'])),
            _cell(5, target('t2', p['target2'])),
            _cell(6, target('t3', p['target3'])),
            _cell(7, Text(p['condition']?.toString() ?? '',
                style: AppTextStyles.captionXs(c.t2))),
            _cell(8, plAbs == null
                ? Text('—', style: AppTextStyles.monoXs(c.t3))
                : Text(
                    '${plAbs >= 0 ? '+' : ''}₹${plAbs.toStringAsFixed(2)} '
                    '(${plPct != null && plPct >= 0 ? '+' : ''}${plPct?.toStringAsFixed(2) ?? ''}%)',
                    style: AppTextStyles.monoXs(plAbs >= 0 ? c.up : c.dn)
                        .copyWith(fontWeight: FontWeight.w700))),
          ]),
        );
      }),
    ]);
  }
}

class _TopFocusCard extends StatelessWidget {
  final List<Map<String, dynamic>> stocks;
  final int totalTracked;
  final void Function(String symbol) onStockTap;
  const _TopFocusCard(
      {required this.stocks,
      required this.totalTracked,
      required this.onStockTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final buys = stocks
        .where((s) =>
            deskActionFrom(s['tracking_status']?.toString()) == DeskAction.buy)
        .length;
    return DenseCard(
      clip: true,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        denseTableHeader(
          context,
          icon: LucideIcons.star,
          accent: c.accent,
          title: 'Top ${stocks.length} Focus',
          subtitle:
              'Best entry candidates ranked across all $totalTracked tracked pick(s) — '
              '$buys BUY · ${stocks.length - buys} WAIT · '
              'ranked by action, score, setup drift & R:R · day-wise batches unchanged below',
        ),
        ...stocks.asMap().entries.map((e) => _DeskStockCard(
              stock: e.value,
              alt: e.key.isOdd,
              rank: e.key + 1,
              onAnalyze: onStockTap,
            )),
      ]),
    );
  }
}

/// A small "predictions, not guaranteed returns" banner — shown wherever
/// prediction_confidence / predicted_gain_pct are displayed, so the numbers
/// are never mistaken for a validated forecast or investment advice.
class _PredictionDisclaimerBanner extends StatelessWidget {
  const _PredictionDisclaimerBanner();

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: c.goldBg,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: c.gold.withValues(alpha: 0.25)),
      ),
      child: Row(children: [
        Icon(LucideIcons.info, size: 12, color: c.gold),
        const SizedBox(width: 6),
        Expanded(
          child: Text(
            'Predictions are model estimates based on technical scoring, '
            'not guaranteed returns. Past performance does not '
            'guarantee future results.',
            style: AppTextStyles.captionXs(c.gold),
          ),
        ),
      ]),
    );
  }
}

/// "Focus Dashboard" — every actively-tracked stock (any status), sorted by
/// ACTUAL profit % since selection, highest to lowest. Unlike Top Focus
/// (fresh entry candidates only), this is the performance view: entered,
/// held, avoided, exited — everything stays visible here for the full
/// 14-day tracking window.
class _FocusDashboardCard extends StatelessWidget {
  final List<Map<String, dynamic>> stocks;
  final void Function(String symbol) onStockTap;
  const _FocusDashboardCard({required this.stocks, required this.onStockTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    if (stocks.isEmpty) return const SizedBox.shrink();
    return DenseCard(
      clip: true,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        denseTableHeader(
          context,
          icon: LucideIcons.trophy,
          accent: c.accent,
          title: 'Focus Dashboard',
          subtitle:
              '${stocks.length} tracked stock(s) sorted by actual profit/loss, '
              'highest to lowest',
        ),
        const Padding(
          padding: EdgeInsets.fromLTRB(12, 8, 12, 4),
          child: _PredictionDisclaimerBanner(),
        ),
        ...stocks.asMap().entries.map((e) => _DeskStockCard(
              stock: e.value,
              alt: e.key.isOdd,
              rank: e.key + 1,
              onAnalyze: onStockTap,
            )),
      ]),
    );
  }
}

/// One "YYYY-MM-DD Picks" batch, its stocks listed underneath.
class _DeskBatchCard extends StatelessWidget {
  final Map<String, dynamic> batch;
  final void Function(String symbol) onStockTap;
  const _DeskBatchCard({required this.batch, required this.onStockTap});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final stocks = List<Map<String, dynamic>>.from(batch['stocks'] ?? const []);
    return DenseCard(
      clip: true,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        denseTableHeader(
          context,
          icon: LucideIcons.layers,
          accent: c.gold,
          title: batch['batch_label']?.toString() ?? 'Selected Picks',
          subtitle: '${stocks.length} system-selected stock(s) · tracked 14 trading days',
        ),
        ...stocks.asMap().entries.map((e) => _DeskStockCard(
              stock: e.value,
              alt: e.key.isOdd,
              onAnalyze: onStockTap,
            )),
      ]),
    );
  }
}

class _DeskStockCard extends ConsumerStatefulWidget {
  final Map<String, dynamic> stock;
  final bool alt;
  final void Function(String symbol) onAnalyze;
  final int? rank; // set only inside the Top 5 Focus card
  const _DeskStockCard(
      {required this.stock,
      required this.alt,
      required this.onAnalyze,
      this.rank});
  @override
  ConsumerState<_DeskStockCard> createState() => _DeskStockCardState();
}

class _DeskStockCardState extends ConsumerState<_DeskStockCard> {
  bool _open = false;
  bool _busy = false;

  String get _symbol => widget.stock['symbol']?.toString() ?? '';

  Future<void> _run(Future<Map<String, dynamic>> Function() call, String ok) async {
    setState(() => _busy = true);
    try {
      final res = await call();
      if (!mounted) return;
      final err = res['error']?.toString();
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(err ?? ok),
      ));
      ref.invalidate(swingDeskProvider);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Action failed: $e')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final s = widget.stock;
    final api = ref.read(apiServiceProvider);
    final action = deskActionFrom(s['tracking_status']?.toString());
    final setupStatus = setupStatusFrom(s['setup_status']?.toString());
    final entered = s['entered'] == true;
    final armed = s['armed'] == true;
    final daysLeft = _deskInt(s['days_remaining']);
    final daysIn = _deskInt(s['days_in_tracking']);
    final origScore = _deskInt(s['original_score']) ?? 0;
    final curScore = _deskInt(s['current_score']) ?? origScore;
    final scoreChange = _deskInt(s['score_change']) ?? (curScore - origScore);
    final priceChange = (s['price_change_pct'] as num?)?.toDouble();
    final rr = s['risk_reward']?.toString();
    final confirms = List<String>.from(s['confirmation_signals'] ?? const []);
    final fails = List<String>.from(s['failure_signals'] ?? const []);

    return Container(
      color: widget.alt ? c.rowAlt : null,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // ── Title row ──
        Row(children: [
          if (widget.rank != null) ...[
            Container(
              width: 18,
              height: 18,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: c.accent.withValues(alpha: 0.12),
                border: Border.all(color: c.accent.withValues(alpha: 0.30)),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text('${widget.rank}',
                  style: AppTextStyles.monoXs(c.accent)
                      .copyWith(fontWeight: FontWeight.w700)),
            ),
            const SizedBox(width: 6),
          ],
          Text(_symbol.replaceAll('.NS', ''), style: AppTextStyles.label(c.t1)),
          const SizedBox(width: 8),
          DeskActionBadge(action: action),
          const SizedBox(width: 6),
          SetupStatusBadge(status: setupStatus),
          if (armed) ...[
            const SizedBox(width: 6),
            Icon(LucideIcons.zap, size: 12, color: c.gold),
          ],
          const Spacer(),
          if (daysLeft != null)
            Text('${daysLeft}d left', style: AppTextStyles.captionXs(c.t3)),
        ]),
        const SizedBox(height: 4),
        // ── Original vs current ──
        Wrap(spacing: 12, runSpacing: 2, children: [
          Text('Score $origScore→$curScore (${scoreChange >= 0 ? '+' : ''}$scoreChange)',
              style: AppTextStyles.monoXs(
                  scoreChange > 0 ? c.up : scoreChange < 0 ? c.dn : c.t3)),
          Text('${s['original_grade'] ?? ''}→${s['current_grade'] ?? s['original_grade'] ?? ''}',
              style: AppTextStyles.monoXs(c.t2)),
          Text('LTP ${_deskRs(s['current_price'])}', style: AppTextStyles.monoXs(c.t2)),
          if (priceChange != null)
            Text('${priceChange >= 0 ? '+' : ''}${priceChange.toStringAsFixed(1)}%',
                style: AppTextStyles.monoXs(priceChange >= 0 ? c.up : c.dn)),
          if (daysIn != null)
            Text('Day $daysIn', style: AppTextStyles.captionXs(c.t3)),
        ]),
        const SizedBox(height: 3),
        // ── Trade plan ──
        Wrap(spacing: 12, runSpacing: 2, children: [
          Text('Trigger ${_deskRs(s['original_entry'])}',
              style: AppTextStyles.monoXs(c.t2)),
          Text('Zone ${_deskRs(s['buy_zone_low'])}–${_deskRs(s['buy_zone_high'])}',
              style: AppTextStyles.monoXs(c.t3)),
          Text('SL ${_deskRs(s['original_stop_loss'])}',
              style: AppTextStyles.monoXs(c.dn)),
          Text('T1 ${_deskRs(s['original_target1'])} · T2 ${_deskRs(s['original_target2'])}',
              style: AppTextStyles.monoXs(c.up)),
          if (rr != null) Text('R:R $rr', style: AppTextStyles.monoXs(c.gold)),
          if (s['predicted_gain_pct'] != null)
            Text(
                'Predicted +${(s['predicted_gain_pct'] as num).toStringAsFixed(1)}% (unvalidated est.)',
                style: AppTextStyles.captionXs(c.t3)),
        ]),
        const SizedBox(height: 4),
        Text(s['reason_for_action']?.toString() ?? s['reason_selected']?.toString() ?? '',
            style: AppTextStyles.captionXs(c.t3)),
        if ((s['final_instruction']?.toString() ?? '').isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Row(children: [
              Icon(LucideIcons.arrowRight, size: 11, color: deskActionColor(context, action)),
              const SizedBox(width: 4),
              Expanded(
                child: Text(s['final_instruction'].toString(),
                    style: AppTextStyles.labelXs(deskActionColor(context, action))),
              ),
            ]),
          ),
        // ── Action buttons ──
        const SizedBox(height: 6),
        Row(children: [
          if (!entered)
            _DeskBtn(
              icon: LucideIcons.shoppingCart,
              label: 'Paper Buy',
              color: c.up,
              busy: _busy,
              onTap: () => _run(() => api.swingDeskPaperBuy(_symbol),
                  'Paper position opened for ${_symbol.replaceAll('.NS', '')}'),
            ),
          if (!entered) const SizedBox(width: 8),
          if (!entered)
            _DeskBtn(
              icon: armed ? LucideIcons.zapOff : LucideIcons.zap,
              label: armed ? 'Disarm' : 'Arm Auto-Buy',
              color: armed ? c.t3 : c.gold,
              busy: _busy,
              onTap: () => _run(
                  () => armed
                      ? api.swingDeskDisarmAutoBuy(_symbol)
                      : api.swingDeskArmAutoBuy(_symbol),
                  armed
                      ? 'Auto-buy disarmed'
                      : 'Armed — will paper-buy only if it turns READY'),
            ),
          if (entered)
            Text('Position open — manage in Paper Trading',
                style: AppTextStyles.captionXs(c.blue)),
          const Spacer(),
          IconButton(
            icon: Icon(LucideIcons.barChart3, size: 15, color: c.accent),
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 32, minHeight: 28),
            tooltip: 'Analyze',
            onPressed: () {
              if (_symbol.isNotEmpty) widget.onAnalyze(_symbol);
            },
          ),
          IconButton(
            icon: Icon(LucideIcons.x, size: 15, color: c.t3),
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 32, minHeight: 28),
            tooltip: 'Remove from desk',
            onPressed: _busy
                ? null
                : () => _run(() => api.swingDeskRemove(_symbol),
                    'Removed ${_symbol.replaceAll('.NS', '')} from the desk'),
          ),
          IconButton(
            icon: Icon(_open ? LucideIcons.chevronUp : LucideIcons.chevronDown,
                size: 15, color: c.t3),
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 32, minHeight: 28),
            tooltip: 'Details',
            onPressed: () => setState(() => _open = !_open),
          ),
        ]),
        if (_open) _DeskStockDetails(stock: s, confirms: confirms, fails: fails),
      ]),
    );
  }
}

/// Expanded per-stock analysis: recommendation summary, live indicators,
/// support/resistance, original vs current levels, and the re-analysis
/// timeline (Initial Pick Snapshot → Latest Re-analysis → history).
class _DeskStockDetails extends StatelessWidget {
  final Map<String, dynamic> stock;
  final List<String> confirms;
  final List<String> fails;
  const _DeskStockDetails(
      {required this.stock, required this.confirms, required this.fails});

  static String _num(dynamic v, [int dp = 1]) =>
      v is num ? v.toStringAsFixed(dp) : '—';

  static String _inds(Map m) =>
      'RSI ${_num(m['rsi'], 0)} · MACD ${m['macd_signal'] ?? '—'} · '
      'ADX ${_num(m['adx'], 0)} · Vol ${_num(m['volume_ratio'], 2)}× · '
      '${m['trend'] ?? '—'} · EMA20 ${_deskRs(m['ema20'])} / EMA50 ${_deskRs(m['ema50'])}';

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final s = stock;
    final origInd = Map<String, dynamic>.from(s['original_indicators'] ?? const {});
    final curInd = Map<String, dynamic>.from(s['current_indicators'] ?? const {});
    final supports = (s['supports'] as List?)?.join(', ') ?? '';
    final resistances = (s['resistances'] as List?)?.join(', ') ?? '';
    final history =
        List<Map<String, dynamic>>.from(s['reanalysis_history'] ?? const []);
    final initial = Map<String, dynamic>.from(s['initial_snapshot'] ?? const {});
    final whatChanged = s['what_changed']?.toString() ?? '';

    Widget label(String t) => Padding(
          padding: const EdgeInsets.only(top: 8, bottom: 2),
          child: Text(t.toUpperCase(), style: AppTextStyles.labelXs(c.t2)),
        );
    Widget kv(String k, String v, {Color? col}) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 1),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            SizedBox(width: 96, child: Text(k, style: AppTextStyles.captionXs(c.t3))),
            Expanded(child: Text(v, style: AppTextStyles.monoXs(col ?? c.t2))),
          ]),
        );

    String snap(Map m) {
      final d = m['analyzed_at']?.toString();
      final day = (d != null && d.length >= 10) ? d.substring(0, 10) : (d ?? '');
      final rec = m['recommendation']?.toString() ?? '—';
      final delta = m['score_delta'];
      final deltaStr = delta is num
          ? ' (${delta >= 0 ? '+' : ''}$delta)'
          : '';
      return '$day · $rec · score ${m['score'] ?? '—'}$deltaStr · ${_deskRs(m['price'])}';
    }

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const SizedBox(height: 4),
      if (confirms.isNotEmpty)
        Wrap(spacing: 4, runSpacing: 4, children: [
          for (final x in confirms) SignalTagChip(tag: SignalTag(x, true)),
        ]),
      if (fails.isNotEmpty) ...[
        const SizedBox(height: 4),
        Wrap(spacing: 4, runSpacing: 4, children: [
          for (final x in fails)
            SignalTagChip(tag: SignalTag(x, true), danger: true),
        ]),
      ],

      // ── Recommendation summary ──
      label('Recommendation'),
      kv('Now', s['current_recommendation']?.toString() ?? s['tracking_status']?.toString() ?? '—'),
      kv('At pick', s['original_recommendation']?.toString() ?? 'WAIT'),
      kv('Setup', s['setup_status']?.toString() ?? 'same'),
      if (whatChanged.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Text(whatChanged, style: AppTextStyles.captionXs(c.t3)),
        ),

      // ── Live technicals ──
      label('Live technicals'),
      Text(_inds(curInd), style: AppTextStyles.monoXs(c.t2)),
      if (origInd.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 2),
          child: Text('At pick: ${_inds(origInd)}',
              style: AppTextStyles.captionXs(c.t4)),
        ),
      if (supports.isNotEmpty) kv('Support', supports, col: c.up),
      if (resistances.isNotEmpty) kv('Resistance', resistances, col: c.dn),

      // ── Original vs current levels ──
      label('Levels — pick → now'),
      kv('Entry', '${_deskRs(s['original_entry'])} → ${_deskRs(s['current_entry'])}'),
      kv('Stop', '${_deskRs(s['original_stop_loss'])} → ${_deskRs(s['current_stop_loss'])}', col: c.dn),
      kv('Target 1', '${_deskRs(s['original_target1'])} → ${_deskRs(s['current_target1'])}', col: c.up),
      kv('Target 2', '${_deskRs(s['original_target2'])} → ${_deskRs(s['current_target2'])}', col: c.up),
      kv('R:R', '${s['original_risk_reward'] ?? '—'} → ${s['risk_reward'] ?? '—'}', col: c.gold),

      // ── Timeline ──
      label('Initial pick snapshot'),
      if (initial.isNotEmpty)
        Text(snap(initial), style: AppTextStyles.monoXs(c.t2))
      else
        Text('—', style: AppTextStyles.captionXs(c.t4)),
      label('Re-analysis history (${history.length})'),
      if (history.isEmpty)
        Text('No re-analysis yet — run Re-analyze to snapshot progress.',
            style: AppTextStyles.captionXs(c.t4))
      else
        ...history.reversed.map((h) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 1),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Icon(LucideIcons.dot, size: 12, color: c.t3),
                Expanded(child: Text(snap(h), style: AppTextStyles.monoXs(c.t2))),
              ]),
            )),

      const SizedBox(height: 6),
      Text('Selected: ${s['reason_selected'] ?? '—'}',
          style: AppTextStyles.captionXs(c.t4)),
      if (s['invalidation_condition'] != null)
        Text('Invalid if: ${s['invalidation_condition']}',
            style: AppTextStyles.captionXs(c.t4)),
    ]);
  }
}

/// Compact bordered action button used inside desk stock cards.
class _DeskBtn extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final bool busy;
  final VoidCallback onTap;
  const _DeskBtn({
    required this.icon,
    required this.label,
    required this.color,
    required this.busy,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: busy ? null : onTap,
      borderRadius: BorderRadius.circular(5),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.10),
          border: Border.all(color: color.withValues(alpha: 0.35)),
          borderRadius: BorderRadius.circular(5),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 12, color: color),
          const SizedBox(width: 5),
          Text(label, style: AppTextStyles.labelXs(color)),
        ]),
      ),
    );
  }
}

class _DeskHistoryCard extends StatelessWidget {
  final List<Map<String, dynamic>> history;
  const _DeskHistoryCard({required this.history});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return DenseCard(
      clip: true,
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(horizontal: 12),
          leading: Icon(LucideIcons.history, size: 15, color: c.t3),
          title: Text('Removed / Expired (${history.length})',
              style: AppTextStyles.label(c.t2)),
          subtitle: Text('Left the desk by the 14-day lifecycle rules or your removal',
              style: AppTextStyles.captionXs(c.t4)),
          children: history.map((h) {
            return Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                SizedBox(
                  width: 96,
                  child: Text(h['symbol']?.toString().replaceAll('.NS', '') ?? '',
                      style: AppTextStyles.label(c.t3)),
                ),
                SizedBox(
                  width: 78,
                  child: Text(h['removed_date']?.toString() ?? '',
                      style: AppTextStyles.captionXs(c.t4)),
                ),
                Expanded(
                  child: Text(h['removal_reason']?.toString() ?? '',
                      style: AppTextStyles.captionXs(c.t3)),
                ),
              ]),
            );
          }).toList(),
        ),
      ),
    );
  }
}


class _DailyPicksTab extends ConsumerWidget {
  final void Function(String symbol) onStockTap;
  final bool kiteConnected;
  const _DailyPicksTab({required this.onStockTap, required this.kiteConnected});

  static const _cols = [
    DenseCol('INSTRUMENT', 3, numeric: false),
    DenseCol('ACTION', 2, numeric: false),
    DenseCol('LTP', 2),
    DenseCol('BUY ZONE', 3),
    DenseCol('STOP', 2),
    DenseCol('EXIT', 3),
    DenseCol('MAX ENTRY', 1),
    DenseCol('SCORE', 2),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final asyncPicks = ref.watch(swingPicksProvider);

    return asyncPicks.when(
      loading: () => const DensePulseLoader(label: 'Loading swing picks…'),
      error: (e, _) => ErrorRetry(
        title: 'Failed to load picks',
        detail: '$e',
        icon: LucideIcons.alertTriangle,
        compact: true,
        onRetry: () => ref.read(swingPicksKeyProvider.notifier).refresh(),
      ),
      data: (data) {
        final picks = List<Map<String, dynamic>>.from(data['picks'] ?? []);
        final scanning = data['scanning'] == true;
        final cooldown = (data['cooldown'] as num?)?.toInt();
        final awaiting = data['awaiting_user'] == true;
        // Name of the selected scan universe, for copy that used to hard-code
        // "Nifty Total Market". Falls back to a neutral phrase while loading.
        final universeLabel = ref.watch(swingUniverseProvider).maybeWhen(
              data: (u) {
                final sel = u['selected']?.toString();
                final opts = List<Map<String, dynamic>>.from(u['options'] ?? const []);
                for (final o in opts) {
                  if (o['key'] == sel) return o['label']?.toString() ?? 'this universe';
                }
                return 'this universe';
              },
              orElse: () => 'this universe',
            );

        if (picks.isEmpty && scanning) {
          return _ScanProgressCard(
            progress: (data['progress'] as num?)?.toInt() ?? 0,
            total: (data['total'] as num?)?.toInt() ?? 0,
            currentStock: data['current_stock'] as String? ?? '',
          );
        }

        // Idle / empty state. Scanning no longer requires Kite — data falls back
        // to Yahoo Finance — so always offer a Scan button here.
        if (picks.isEmpty) {
          return ListView(padding: const EdgeInsets.only(top: 12), children: [
            const _EngineToggle(),
            const SizedBox(height: 10),
            const _UniverseToggle(),
            const SizedBox(height: 10),
            AnimatedListItem(
              index: 0,
              child: DenseEmptyCard(
                icon: awaiting ? LucideIcons.target : LucideIcons.search,
                // Name the universe actually selected — this copy used to hard-code
                // "Nifty Total Market" regardless of the picker above.
                title: awaiting ? 'Ready to scan $universeLabel' : 'No swing setups found',
                sub: awaiting
                    ? "Run the scanner to find today's best swing setups across "
                        'the $universeLabel universe.'
                    : 'The scanner found no qualifying setups in $universeLabel.',
              ),
            ),
            if (!kiteConnected) ...[
              const SizedBox(height: 10),
              const AnimatedListItem(index: 1, child: _DataSourceNote()),
            ],
            const SizedBox(height: 12),
            AnimatedListItem(
              index: 2,
              child: Center(
                child: HeaderButton(
                  icon: const Icon(LucideIcons.refreshCw, size: 13, color: Colors.white),
                  text: cooldown != null
                      ? 'Scan Again (${cooldown}s)'
                      : (awaiting ? 'Scan Now' : 'Scan Again'),
                  solidColor: c.accent,
                  onTap: cooldown != null
                      ? null
                      : () => ref.read(swingPicksKeyProvider.notifier).refresh(),
                ),
              ),
            ),
          ]);
        }

        final universe = (data['universe_size'] as num?)?.toInt() ??
            (data['total'] as num?)?.toInt() ??
            500;
        final src = picks[0]['data_source']?.toString() ?? 'Yahoo Finance';

        // Signal legend / count summary across all picks. Prefer the backend's
        // hybrid action when present; fall back to the client-derived plan.
        SwingAction actionOf(Map<String, dynamic> p) =>
            _backendAction(p) ?? SwingSignals.of(p).plan.action;
        final buyCount =
            picks.where((p) => actionOf(p) == SwingAction.buy).length;
        final watchCount =
            picks.where((p) => actionOf(p) == SwingAction.watch).length;

        final engine = ref.watch(swingEngineProvider);
        return ListView(padding: const EdgeInsets.only(top: 12), children: [
          const _EngineToggle(),
          const SizedBox(height: 10),
          const _UniverseToggle(),
          const SizedBox(height: 10),
          AnimatedListItem(
            index: 0,
            child: DenseCard(
              clip: true,
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                denseTableHeader(
                  context,
                  icon: LucideIcons.target,
                  accent: c.accent,
                  title: "Today's Focus List · ${engine == 'v5' ? 'v5 · ensemble (beta)' : engine == 'v4.1' ? 'v4.1 · low-vol rank' : 'v4'}",
                  subtitle:
                      'Top ${picks.length} picks whose heuristic predicted gain clears 5%, '
                      'ranked by confidence then expected gain · tracked 14 trading days on the '
                      'Focus Dashboard · no take-profit target, hold up to 20 sessions · '
                      'stop 2.5×ATR on daily close · skip if it opens >4% above signal close · '
                      'Scanned $universe NSE stocks · $buyCount buy · $watchCount watch · $src',
                  trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                    if (scanning) ...[
                      SizedBox(
                          width: 12,
                          height: 12,
                          child: CircularProgressIndicator(strokeWidth: 2, color: c.accent)),
                      const SizedBox(width: 6),
                      Text('SCANNING', style: AppTextStyles.labelXs(c.accent)),
                      const SizedBox(width: 12),
                    ],
                    HeaderButton(
                      icon: Icon(LucideIcons.rotateCcw, size: 13, color: c.accent),
                      text: 'Hard Rescan',
                      onTap: () async {
                        final ok = await showDialog<bool>(
                          context: context,
                          builder: (dctx) => AlertDialog(
                            title: const Text('Hard rescan today?'),
                            content: const Text(
                                "This replaces today's saved picks with a fresh "
                                'scan. Existing 14-Day Desk stocks are not affected.'),
                            actions: [
                              TextButton(
                                  onPressed: () => Navigator.pop(dctx, false),
                                  child: const Text('Cancel')),
                              TextButton(
                                  onPressed: () => Navigator.pop(dctx, true),
                                  child: const Text('Rescan')),
                            ],
                          ),
                        );
                        if (ok == true) {
                          ref.read(swingHardResetKeyProvider.notifier).refresh();
                        }
                      },
                    ),
                  ]),
                ),
                const Padding(
                  padding: EdgeInsets.fromLTRB(12, 0, 12, 8),
                  child: _PredictionDisclaimerBanner(),
                ),
                denseColumnHeader(context, _cols),
                ...picks.asMap().entries.map((e) => _PickTile(
                      pick: e.value,
                      alt: e.key.isOdd,
                      cols: _cols,
                      onAnalyze: onStockTap,
                    )),
              ]),
            ),
          ),
          const SizedBox(height: 12),
          const AnimatedListItem(index: 1, child: _ScannerLegendCard()),
          const SizedBox(height: 24),
        ]);
      },
    );
  }
}

/// A two-line scanner row: dense levels on top, exact reason + indicator/signal
/// chips + Analyze action below. Everything derives from [SwingSignals].
class _PickTile extends StatelessWidget {
  final Map<String, dynamic> pick;
  final bool alt;
  final List<DenseCol> cols;
  final void Function(String) onAnalyze;
  const _PickTile(
      {required this.pick, required this.alt, required this.cols, required this.onAnalyze});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final sig = SwingSignals.of(pick);
    final plan = sig.plan;
    final symbol = pick['symbol']?.toString() ?? '';
    final name = pick['name']?.toString() ?? symbol;
    final trend = pick['trend']?.toString() ?? '';
    final price = (pick['price'] as num?)?.toDouble();

    final setupSub = <String>[
      if ((pick['setup_type']?.toString() ?? pick['setup']?.toString() ?? '')
          .isNotEmpty)
        (pick['setup_type'] ?? pick['setup']).toString(),
      if (trend.isNotEmpty) 'Trend $trend',
    ].join(' · ');

    // Hybrid backend fields take precedence; client-derived plan is fallback.
    final action = _backendAction(pick) ?? plan.action;
    final bzLow = (pick['buy_zone_low'] as num?)?.toDouble() ?? plan.buyLow;
    final bzHigh = (pick['buy_zone_high'] as num?)?.toDouble() ?? plan.buyHigh;
    final ltp = (pick['current_price'] as num?)?.toDouble() ?? price;

    final buyZone = action == SwingAction.avoid
        ? '—'
        : (bzLow != null && bzHigh != null)
            ? '${_px(bzLow)}–${_px(bzHigh)}'
            : _px(plan.entry);

    final stopStr = plan.stop != null
        ? '${_px(plan.stop)} (${pick['risk_pct'] ?? '?'}%)'
        : '—';

    final selectionScore = (pick['selection_score'] as num?)?.toInt();
    final confidence = pick['confidence']?.toString() ?? sig.confidence;

    final line1 = <Widget>[
      DInstrument(symbol: name, sub: setupSub, up: trend != 'Down'),
      Align(
        alignment: Alignment.centerLeft,
        child: SwingActionBadge(action: action),
      ),
      denseNum(context, _px(ltp), c.t1, bold: true),
      denseNum(context, buyZone, c.blue),
      denseNum(context, stopStr, c.dn),
      // v4: no take-profit — show the exit rule (or legacy targets if present).
      Column(crossAxisAlignment: CrossAxisAlignment.end, mainAxisSize: MainAxisSize.min, children: [
        denseNum(context,
            plan.target1 != null ? '${_px(plan.target1)} (+${pick['reward_pct'] ?? '?'}%)' : 'Day 20',
            c.up),
        const SizedBox(height: 1),
        Text(plan.target2 != null ? 'T2 ${_px(plan.target2)}' : 'time exit',
            style: AppTextStyles.captionXs(c.t3), textAlign: TextAlign.right),
      ]),
      // Max entry price (v4 gap guard) in place of the retired R:R column.
      denseNum(
          context,
          pick['max_entry_price'] != null
              ? '≤${_px(pick['max_entry_price'])}'
              : pick['risk_reward']?.toString() ?? plan.riskReward ?? '—',
          c.gold),
      // Score + confidence — hybrid selection score when present.
      Column(crossAxisAlignment: CrossAxisAlignment.end, mainAxisSize: MainAxisSize.min, children: [
        denseNum(context, '${selectionScore ?? sig.score}',
            swingScoreColor(context, selectionScore ?? sig.score),
            bold: true),
        Text(confidence, style: AppTextStyles.captionXs(c.t3), textAlign: TextAlign.right),
      ]),
    ];

    return Container(
      decoration: BoxDecoration(
        color: alt ? c.rowAlt : Colors.transparent,
        border: Border(bottom: BorderSide(color: c.bd.withValues(alpha: 0.6))),
      ),
      child: Column(children: [
        InkWell(
          onTap: () => onAnalyze(symbol),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            child: Row(children: [
              for (var i = 0; i < cols.length; i++)
                Expanded(flex: cols[i].flex, child: line1[i]),
            ]),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 0, 14, 10),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Icon(LucideIcons.info, size: 11, color: c.t3),
                  const SizedBox(width: 5),
                  Expanded(
                    child: Text(pick['reason_selected']?.toString() ?? plan.reason,
                        style: AppTextStyles.bodySmall(c.t2), maxLines: 2, overflow: TextOverflow.ellipsis),
                  ),
                ]),
                const SizedBox(height: 6),
                Wrap(spacing: 6, runSpacing: 5, children: [
                  if (pick['v3_momentum'] == true)
                    _miniStat(context, 'MOMENTUM', '✓', c.up),
                  if (pick['quality_pick'] == true)
                    _miniStat(context, 'QUALITY', '✓', c.up),
                  if (pick['recently_topped'] == true)
                    _miniStat(context, 'REPEAT', '⏳', c.gold),
                  _miniStat(context, 'RSI', '${pick['rsi'] ?? '—'}',
                      (pick['rsi'] as num?) != null && (pick['rsi'] as num) < 40 ? c.up : c.t2),
                  _miniStat(context, 'ADX', '${pick['adx'] ?? '—'}',
                      (pick['adx'] as num?) != null && (pick['adx'] as num) > 25 ? c.up : c.t2),
                  _miniStat(context, 'Vol', '${pick['volume_ratio'] ?? '—'}×',
                      pick['volume_spike'] == true ? c.gold : c.t2),
                  _miniStat(context, 'MACD', pick['macd_signal']?.toString() ?? '—',
                      pick['macd_signal'] == 'Bullish' ? c.up : c.dn),
                  if ((pick['pattern']?.toString() ?? 'None') != 'None')
                    _miniStat(context, 'Pattern', pick['pattern'].toString(), c.gold),
                  _signalCountChip(context, sig),
                ]),
                _HybridStrip(pick: pick),
              ]),
            ),
            const SizedBox(width: 12),
            HeaderButton(
              icon: Icon(LucideIcons.barChart3, size: 13, color: c.accent),
              text: 'Analyze',
              onTap: () => onAnalyze(symbol),
            ),
          ]),
        ),
      ]),
    );
  }
}

/// Small "LABEL value" chip for the indicator strip.
Widget _miniStat(BuildContext context, String label, String value, Color color) {
  final c = context.colors;
  return Container(
    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
    decoration: BoxDecoration(
      color: c.bg3,
      border: Border.all(color: c.bd),
      borderRadius: BorderRadius.circular(4),
    ),
    child: Row(mainAxisSize: MainAxisSize.min, children: [
      Text('$label ', style: AppTextStyles.captionXs(c.t3)),
      Text(value, style: AppTextStyles.mono(color).copyWith(fontSize: 11, fontWeight: FontWeight.w600)),
    ]),
  );
}

/// "▲ 4/6 continuation" style chip summarising the strongest firing strategy.
Widget _signalCountChip(BuildContext context, SwingSignal sig) {
  final c = context.colors;
  // Pick the strategy with the most fired conditions (excluding avoid).
  SignalKind best = SignalKind.continuation;
  int bestN = -1;
  for (final k in [SignalKind.continuation, SignalKind.pullback, SignalKind.reversal]) {
    final n = sig.fired(k);
    if (n > bestN) {
      bestN = n;
      best = k;
    }
  }
  final avoidN = sig.fired(SignalKind.avoid);
  final label = avoidN >= 2 ? '$avoidN risk flags' : '$bestN/${sig.total(best)} ${best.title}';
  final col = avoidN >= 2 ? c.dn : c.up;
  return Container(
    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
    decoration: BoxDecoration(
      color: col.withValues(alpha: 0.10),
      border: Border.all(color: col.withValues(alpha: 0.25)),
      borderRadius: BorderRadius.circular(4),
    ),
    child: Row(mainAxisSize: MainAxisSize.min, children: [
      Icon(avoidN >= 2 ? LucideIcons.alertTriangle : LucideIcons.checkCircle2, size: 10, color: col),
      const SizedBox(width: 4),
      Text(label, style: AppTextStyles.captionXs(col).copyWith(fontWeight: FontWeight.w600)),
    ]),
  );
}

/// Maps the backend's hybrid `action` field (BUY / WATCH / AVOID) onto the
/// client-side enum; returns null for legacy payloads without the field.
SwingAction? _backendAction(Map<String, dynamic> pick) {
  switch (pick['action']?.toString()) {
    case 'BUY':
      return SwingAction.buy;
    case 'WATCH':
      return SwingAction.watch;
    case 'AVOID':
      return SwingAction.avoid;
  }
  return null;
}

Color _gradeColor(BuildContext context, String grade) {
  final c = context.colors;
  switch (grade) {
    case 'A+':
    case 'A':
      return c.up;
    case 'B':
      return c.gold;
    case 'C':
      return c.blue;
    default:
      return c.dn;
  }
}

List<String> _dataWarnings(Map<String, dynamic> pick) {
  return <String>[
    if (pick['stale_price_warning'] == true) 'Stale live quote',
    if (pick['ltp_mismatch_warning'] == true) 'Kite/Yahoo price mismatch',
    if (pick['volume_missing_warning'] == true) 'Volume data missing',
  ];
}

/// Hybrid-selector read-out: grade, Yahoo+Kite source badge, Yahoo scan score,
/// Kite confirmation score, probability forecast, data warnings and the
/// invalidation condition. Renders nothing for legacy (non-hybrid) payloads.
class _HybridStrip extends StatelessWidget {
  final Map<String, dynamic> pick;
  const _HybridStrip({required this.pick});

  Widget _badge(BuildContext context, String text, Color col, {IconData? icon}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: col.withValues(alpha: 0.12),
        border: Border.all(color: col.withValues(alpha: 0.35)),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        if (icon != null) ...[
          Icon(icon, size: 10, color: col),
          const SizedBox(width: 4),
        ],
        Text(text,
            style: AppTextStyles.captionXs(col).copyWith(fontWeight: FontWeight.w700)),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final grade = pick['grade']?.toString();
    if (grade == null) return const SizedBox.shrink();

    final gradeCol = _gradeColor(context, grade);
    final kiteLive = pick['kite_live_ok'] == true;
    final yScore = (pick['yahoo_scan_score'] as num?)?.toInt();
    final kScore = (pick['kite_confirmation_score'] as num?)?.toInt();
    final p5 = (pick['upside_probability_5d'] as num?)?.toDouble();
    final p10 = (pick['upside_probability_10d'] as num?)?.toDouble();
    final down = (pick['downside_risk_probability'] as num?)?.toDouble();
    final dq = (pick['data_quality_score'] as num?)?.toInt();
    final warnings = _dataWarnings(pick);
    final invalidation = pick['invalidation_condition']?.toString();

    String pct(double v) => '${(v * 100).round()}%';

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const SizedBox(height: 6),
      Wrap(spacing: 6, runSpacing: 5, children: [
        _badge(context, 'GRADE $grade', gradeCol, icon: LucideIcons.award),
        _badge(context, kiteLive ? 'YAHOO + KITE' : 'YAHOO', kiteLive ? c.accent : c.t3,
            icon: LucideIcons.database),
        if (yScore != null) _miniStat(context, 'Y-Scan', '$yScore', c.t2),
        if (kScore != null)
          _miniStat(context, 'Kite', '$kScore/10', kiteLive ? c.up : c.t3),
        if (p5 != null) _miniStat(context, 'P↑5d', pct(p5), c.up),
        if (p10 != null) _miniStat(context, 'P↑10d', pct(p10), c.up),
        if (down != null) _miniStat(context, 'P↓risk', pct(down), c.dn),
        if (dq != null) _miniStat(context, 'DQ', '$dq', dq >= 80 ? c.t2 : c.gold),
        for (final w in warnings)
          _badge(context, w, c.dn, icon: LucideIcons.alertTriangle),
      ]),
      if (invalidation != null && grade != 'Avoid') ...[
        const SizedBox(height: 6),
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(LucideIcons.xCircle, size: 11, color: c.dn),
          const SizedBox(width: 5),
          Expanded(
            child: Text('Invalid if: $invalidation',
                style: AppTextStyles.captionXs(c.t3),
                maxLines: 2,
                overflow: TextOverflow.ellipsis),
          ),
        ]),
      ],
    ]);
  }
}

/// A compact legend explaining the score bands and the action tags.
/// Engine selector. v4 is the default; v4.1 and v5 are candidates on isolated
/// paths (own cache, own storage variant, no desk or paper feed). Switching sets
/// the engine and re-runs the daily scan for it.
///
/// v4's sub-label used to read "Validated default". That claim was refuted:
/// research/V6_TRAINING_PLAN.md measured v4 at 1.58%/trade on TEST against a
/// random-picking bar of 1.95-2.00, below all three seeds at matched config. It
/// is still the default; it is not validated, and the UI should not say it is.
class _EngineToggle extends ConsumerWidget {
  const _EngineToggle();

  static const _notes = {
    'v4': 'v4 is the default and the most-used engine, but its stock selection '
        'did not beat random picking out of sample (research/V6_TRAINING_PLAN.md). '
        'Its risk profile — drawdown and Calmar — did beat every random seed.',
    'v4.1': "v4.1 is v4's scan re-ranked: it penalises high volatility "
        '(cross-sectional ATR%) and rewards closeness to the 52-week high. Both '
        'effects replicated at 6 of 6 folds on two universes '
        '(research/FEATURE_IC_REPLICATION.md). Not yet tested against a '
        'random-pick benchmark — candidate, not a promotion.',
    'v5': 'v5 is research/experimental (regime-adaptive ensemble). Its s1/s3 '
        'rules beat random per-trade but at materially worse drawdown.',
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final engine = ref.watch(swingEngineProvider);

    void select(String e) {
      if (e == engine) return;
      ref.read(swingEngineProvider.notifier).select(e);
      // Re-run the scan for the newly selected engine.
      ref.read(swingPicksKeyProvider.notifier).refresh();
    }

    // Three segments, so each stacks icon over label over sub-label rather than
    // laying them out side by side — the same shape _UniverseToggle uses, which
    // keeps all three readable at narrow window widths.
    Widget seg(String value, String label, String sub, IconData icon) {
      final on = engine == value;
      return Expanded(
        child: GestureDetector(
          onTap: () => select(value),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 160),
            padding: const EdgeInsets.symmetric(vertical: 9, horizontal: 8),
            decoration: BoxDecoration(
              color: on ? c.accent : c.bg2,
              borderRadius: BorderRadius.circular(9),
              border: Border.all(color: on ? c.accent : c.bd),
            ),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                Icon(icon, size: 13, color: on ? Colors.white : c.t3),
                const SizedBox(width: 6),
                Text(label, style: AppTextStyles.bodyBold(on ? Colors.white : c.t1)),
              ]),
              Text(sub,
                  textAlign: TextAlign.center,
                  style: AppTextStyles.labelXs(on ? Colors.white70 : c.t3)),
            ]),
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 2),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 6),
          child: Text('SWING ENGINE', style: AppTextStyles.labelXs(c.t3)),
        ),
        Row(children: [
          seg('v4', 'v4', 'Default', LucideIcons.shieldCheck),
          const SizedBox(width: 8),
          seg('v4.1', 'v4.1', 'Low-vol rank', LucideIcons.trendingUp),
          const SizedBox(width: 8),
          seg('v5', 'v5', 'Ensemble · beta', LucideIcons.flaskConical),
        ]),
        if (_notes[engine] != null)
          Padding(
            padding: const EdgeInsets.only(left: 4, top: 6),
            child: Text(_notes[engine]!, style: AppTextStyles.labelXs(c.t3)),
          ),
      ]),
    );
  }
}

/// Which index the scanner sweeps: Nifty 50 / Nifty 500 / Nifty Total Market.
/// Persisted per user on the backend, so it survives a restart and follows the
/// signed-in account. Switching only changes the NEXT scan — today's picks are
/// frozen once saved, so this offers a hard rescan instead of silently leaving
/// the new count unused.
class _UniverseToggle extends ConsumerWidget {
  const _UniverseToggle();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final async = ref.watch(swingUniverseProvider);

    return async.when(
      loading: () => const SizedBox.shrink(),
      error: (_, _) => const SizedBox.shrink(),
      data: (data) {
        final selected = data['selected']?.toString() ?? 'total';
        final options = List<Map<String, dynamic>>.from(data['options'] ?? const []);
        if (options.isEmpty) return const SizedBox.shrink();

        Future<void> select(String key) async {
          if (key == selected) return;
          final api = ref.read(apiServiceProvider);
          try {
            await api.setSwingUniverse(key);
          } catch (e) {
            if (!context.mounted) return;
            ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('Could not change universe: $e')));
            return;
          }
          ref.invalidate(swingUniverseProvider);
          if (!context.mounted) return;
          final label = options.firstWhere((o) => o['key'] == key,
              orElse: () => {'label': key})['label'];
          final rescan = await showDialog<bool>(
            context: context,
            builder: (dctx) => AlertDialog(
              title: Text('Scan $label now?'),
              content: Text(
                  "$label is saved as your scan universe. Today's picks were "
                  'already scanned on the old universe — rescan now to use the '
                  'new one, or keep today as-is and let it apply tomorrow.'),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(dctx, false),
                    child: const Text('Keep today')),
                FilledButton(
                    onPressed: () => Navigator.pop(dctx, true),
                    child: const Text('Rescan now')),
              ],
            ),
          );
          if (rescan == true) {
            ref.read(swingPicksKeyProvider.notifier).refresh();
          }
        }

        Widget seg(Map<String, dynamic> o) {
          final key = o['key']?.toString() ?? '';
          final on = key == selected;
          return Expanded(
            child: Tooltip(
              message: o['description']?.toString() ?? '',
              child: GestureDetector(
                onTap: () => select(key),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 160),
                  padding: const EdgeInsets.symmetric(vertical: 9, horizontal: 10),
                  decoration: BoxDecoration(
                    color: on ? c.accent : c.bg2,
                    borderRadius: BorderRadius.circular(9),
                    border: Border.all(color: on ? c.accent : c.bd),
                  ),
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Text(o['label']?.toString() ?? key,
                        textAlign: TextAlign.center,
                        style: AppTextStyles.bodyBold(on ? Colors.white : c.t1)),
                    Text('${o['size'] ?? '—'} stocks',
                        style:
                            AppTextStyles.labelXs(on ? Colors.white70 : c.t3)),
                  ]),
                ),
              ),
            ),
          );
        }

        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 2),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Padding(
              padding: const EdgeInsets.only(left: 4, bottom: 6),
              child: Text('SCAN UNIVERSE', style: AppTextStyles.labelXs(c.t3)),
            ),
            Row(children: [
              for (var i = 0; i < options.length; i++) ...[
                if (i > 0) const SizedBox(width: 8),
                seg(options[i]),
              ],
            ]),
            if (data['note'] != null)
              Padding(
                padding: const EdgeInsets.only(left: 4, top: 6),
                child: Text(data['note'].toString(),
                    style: AppTextStyles.labelXs(c.t3)),
              ),
          ]),
        );
      },
    );
  }
}

class _ScannerLegendCard extends StatelessWidget {
  const _ScannerLegendCard();
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(context,
            icon: LucideIcons.bookOpen, accent: c.t3, title: 'How to read the desk'),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
          child: Wrap(spacing: 14, runSpacing: 8, children: [
            _legend(context, c.up, 'Score 80–100 · Strong setup'),
            _legend(context, c.gold, 'Score 65–79 · Good setup'),
            _legend(context, c.blue, 'Score 50–64 · Watchlist only'),
            _legend(context, c.dn, 'Score < 50 · Avoid'),
            _legend(context, c.up, 'BUY = price in buy zone now'),
            _legend(context, c.gold, 'WATCH = wait for the trigger'),
            _legend(context, c.dn, 'AVOID = setup fails the checks'),
            _legend(context, c.up, 'Grade A+/A = Yahoo scan + Kite live confirmation agree'),
            _legend(context, c.blue, 'P↑/P↓ = probability estimates, not guarantees'),
          ]),
        ),
      ]),
    );
  }

  Widget _legend(BuildContext context, Color col, String text) {
    final c = context.colors;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Container(width: 8, height: 8, decoration: BoxDecoration(color: col, borderRadius: BorderRadius.circular(2))),
      const SizedBox(width: 6),
      Text(text, style: AppTextStyles.captionXs(c.t2)),
    ]);
  }
}

/// Small note shown when Kite isn't connected: the desk still scans using Yahoo
/// Finance (delayed); Kite is only needed for real-time LTP.
class _DataSourceNote extends StatelessWidget {
  const _DataSourceNote();
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
          decoration: BoxDecoration(
            color: c.blueBg,
            border: Border.all(color: c.blue.withValues(alpha: 0.25)),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Row(children: [
            Icon(LucideIcons.info, size: 13, color: c.blue),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'Kite not connected — the scan will use Yahoo Finance (end-of-day / delayed). Connect Zerodha for real-time prices.',
                style: AppTextStyles.captionXs(c.t2),
              ),
            ),
          ]),
        ),
      ),
    );
  }
}

/// Scan-in-progress state — dense card with a slim progress bar.
class _ScanProgressCard extends StatelessWidget {
  final int progress;
  final int total;
  final String currentStock;
  const _ScanProgressCard({this.progress = 0, this.total = 0, this.currentStock = ''});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final pct = total > 0 ? (progress / total).clamp(0.0, 1.0) : 0.0;
    final pctText = total > 0 ? '${(pct * 100).toInt()}%' : '';

    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480),
        child: DenseCard(
          padding: const EdgeInsets.all(20),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(strokeWidth: 2, color: c.blue)),
            const SizedBox(height: 14),
            Text('Scanning stocks for swing setups', style: AppTextStyles.heading3(c.t1)),
            const SizedBox(height: 5),
            Text('RSI · MACD · Bollinger · candlestick patterns · volume',
                style: AppTextStyles.captionXs(c.t3), textAlign: TextAlign.center),
            const SizedBox(height: 18),
            ClipRRect(
              borderRadius: BorderRadius.circular(3),
              child: SizedBox(
                height: 6,
                child: Row(children: [
                  Expanded(
                      flex: (pct * 1000).round().clamp(0, 1000),
                      child: AnimatedContainer(
                          duration: const Duration(milliseconds: 400), color: c.blue)),
                  Expanded(
                      flex: (1000 - (pct * 1000).round()).clamp(0, 1000),
                      child: Container(color: c.bg3)),
                ]),
              ),
            ),
            const SizedBox(height: 10),
            Text(
              total > 0 ? '$progress / $total stocks · $pctText' : 'Starting scan…',
              style: AppTextStyles.mono(c.t2).copyWith(fontSize: 12),
            ),
            if (currentStock.isNotEmpty && currentStock != 'Done') ...[
              const SizedBox(height: 6),
              Text('Analyzing $currentStock', style: AppTextStyles.captionXs(c.t3)),
            ],
          ]),
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════
//  TAB 2: SWING ANALYSIS (individual stock)
// ═══════════════════════════════════════════════════════════════
class _SwingAnalysisTab extends ConsumerStatefulWidget {
  final String? symbol;
  final ValueChanged<String> onSymbolChanged;
  const _SwingAnalysisTab({this.symbol, required this.onSymbolChanged});
  @override
  ConsumerState<_SwingAnalysisTab> createState() => _SwingAnalysisTabState();
}

class _SwingAnalysisTabState extends ConsumerState<_SwingAnalysisTab> {
  Map<String, dynamic>? _analysis;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (widget.symbol != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _loadAnalysis(widget.symbol!));
    }
  }

  @override
  void didUpdateWidget(covariant _SwingAnalysisTab oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.symbol != null && widget.symbol != oldWidget.symbol) {
      _loadAnalysis(widget.symbol!);
    }
  }

  void _loadAnalysis(String symbol) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = ref.read(apiServiceProvider);
      final result = await api.getSwingAnalysis(symbol);
      if (result['error'] != null) {
        setState(() {
          _error = result['error'].toString();
          _loading = false;
        });
        return;
      }
      setState(() {
        _analysis = result;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = '$e';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;

    if (_analysis == null && !_loading && _error == null) {
      return Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: const DenseEmptyCard(
            icon: LucideIcons.barChart3,
            title: "Select a stock from Today's Picks",
            sub: 'Tap any pick row to see the full trade plan, signal breakdown and price levels',
          ),
        ),
      );
    }

    if (_loading) {
      return DensePulseLoader(label: 'Analyzing ${widget.symbol?.replaceAll(".NS", "")}…');
    }

    if (_error != null) {
      return ErrorRetry(
        title: 'Failed to load analysis',
        detail: _error,
        icon: LucideIcons.alertTriangle,
        compact: true,
        onRetry: () {
          if (widget.symbol != null) _loadAnalysis(widget.symbol!);
        },
      );
    }

    if (_analysis == null) {
      return Center(child: Text('No data available', style: AppTextStyles.body(c.t4)));
    }

    final a = _analysis!;
    final llm = a['llm_analysis'] is Map ? a['llm_analysis'] as Map<String, dynamic> : <String, dynamic>{};
    final sig = SwingSignals.of(a, confidenceOverride: llm['confidence']?.toString());
    final score = sig.score;

    return ListView(padding: const EdgeInsets.only(top: 12), children: [
      // ── Header card ──
      AnimatedListItem(
        index: 0,
        child: DenseCard(
          child: denseTableHeader(
            context,
            icon: LucideIcons.barChart3,
            accent: c.accent,
            title: '${a['name']} — Swing Analysis',
            subtitle: (a['setup_type'] ?? a['setup'])?.toString(),
            trailing: Row(mainAxisSize: MainAxisSize.min, children: [
              SwingActionBadge(action: sig.plan.action, large: true),
              const SizedBox(width: 12),
              SwingScoreReadout(score: score, bucket: sig.scoreBucket),
            ]),
          ),
        ),
      ),
      // Grade, Yahoo+Kite source badge, probability forecast, data warnings —
      // mirrors the scanner row so both views agree.
      if (a['grade'] != null) ...[
        const SizedBox(height: 12),
        AnimatedListItem(
          index: 1,
          child: DenseCard(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
              child: _HybridStrip(pick: a),
            ),
          ),
        ),
      ],
      const SizedBox(height: 12),

      // ── Derived Trade Plan (levels + sizing + invalidation) ──
      AnimatedListItem(index: 1, child: _TradePlanCard(sig: sig, analysis: a)),
      const SizedBox(height: 12),

      // ── Signal Strength breakdown ──
      AnimatedListItem(index: 2, child: _ScoreBreakdownCard(sig: sig)),
      const SizedBox(height: 12),

      // ── Signals by strategy ──
      AnimatedListItem(index: 3, child: _SignalsCard(sig: sig)),
      const SizedBox(height: 12),

      // ── AI Trade Plan (LLM) ──
      if (llm.isNotEmpty) ...[
        AnimatedListItem(index: 4, child: _LlmPlanCard(llm: llm)),
        const SizedBox(height: 12),
      ],

      // ── Technical Data Grid ──
      AnimatedListItem(index: 5, child: _LevelsGrid(a: a)),
      const SizedBox(height: 24),
    ]);
  }
}

/// The concrete, level-based trade plan card.
class _TradePlanCard extends StatelessWidget {
  final SwingSignal sig;
  final Map<String, dynamic> analysis;
  const _TradePlanCard({required this.sig, required this.analysis});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final p = sig.plan;
    final actionCol = swingActionColor(context, p.action);

    final cells = <_PlanCell>[
      _PlanCell('Entry Trigger', p.entry != null ? '₹${_px(p.entry)}${p.entryDerived ? ' (LTP)' : ''}' : '—', c.blue),
      _PlanCell('Buy Zone',
          (p.buyLow != null && p.buyHigh != null) ? '₹${_px(p.buyLow)} – ₹${_px(p.buyHigh)}' : '—', c.blue),
      _PlanCell('Stop Loss', p.stop != null ? '₹${_px(p.stop)}' : '—', c.dn),
      _PlanCell('Target 1', p.target1 != null ? '₹${_px(p.target1)}' : '—', c.up),
      _PlanCell('Target 2', p.target2 != null ? '₹${_px(p.target2)}' : '—', c.up),
      _PlanCell('Risk : Reward', p.riskReward ?? '—', c.gold),
      _PlanCell('Risk / share', p.riskPerShare != null ? '₹${_px(p.riskPerShare)}' : '—', c.dn),
      _PlanCell('Reward / share', p.rewardPerShare != null ? '₹${_px(p.rewardPerShare)}' : '—', c.up),
      _PlanCell('Trailing (after T1)', p.trailingAfterT1 != null ? 'to ₹${_px(p.trailingAfterT1)}' : '—', c.t1),
      _PlanCell('Hold Duration', p.holdDuration, c.t1),
      _PlanCell('Position (1% risk)',
          p.positionQty != null ? '${p.positionQty} sh · ${formatINR(p.positionValue ?? 0)}' : '—', c.t1),
      _PlanCell('Ref Capital', formatINR(kSwingRefCapital), c.t3),
    ];

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(context,
            icon: LucideIcons.clipboardList,
            accent: actionCol,
            title: 'Trade Plan',
            trailing: SwingActionBadge(action: p.action)),
        // Reason callout.
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 0, 14, 10),
          child: Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: actionCol.withValues(alpha: 0.06),
              border: Border.all(color: actionCol.withValues(alpha: 0.2)),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(swingActionIcon(p.action), size: 14, color: actionCol),
              const SizedBox(width: 8),
              Expanded(child: Text(p.reason, style: AppTextStyles.bodySmall(c.t1))),
            ]),
          ),
        ),
        // Levels grid — 2 cells per row.
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 0, 14, 4),
          child: Column(children: [
            for (var i = 0; i < cells.length; i += 2)
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(child: cells[i]),
                Container(width: 1, height: 30, color: c.bd),
                Expanded(child: i + 1 < cells.length ? cells[i + 1] : const SizedBox()),
              ]),
          ]),
        ),
        // Invalidation line.
        if (p.invalidIf != null)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
            decoration: BoxDecoration(
              color: c.dnBg,
              border: Border(top: BorderSide(color: c.bd)),
            ),
            child: Row(children: [
              Icon(LucideIcons.xCircle, size: 13, color: c.dn),
              const SizedBox(width: 8),
              Text('Invalid if: ', style: AppTextStyles.labelXs(c.dn)),
              Expanded(child: Text(p.invalidIf!, style: AppTextStyles.bodySmall(c.t2))),
            ]),
          ),
        // Exit rules.
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('EXIT / SELL RULES', style: AppTextStyles.labelXs(c.t3)),
            const SizedBox(height: 6),
            ...p.exitRules.map((r) => Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Icon(LucideIcons.logOut, size: 11, color: c.t3),
                    const SizedBox(width: 6),
                    Expanded(child: Text(r, style: AppTextStyles.captionXs(c.t2))),
                  ]),
                )),
          ]),
        ),
      ]),
    );
  }
}

class _PlanCell extends StatelessWidget {
  final String label, value;
  final Color color;
  const _PlanCell(this.label, this.value, this.color);
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
        Text(label, style: AppTextStyles.captionXs(c.t3)),
        const SizedBox(height: 3),
        Text(value, style: AppTextStyles.monoBold(color).copyWith(fontSize: 13), maxLines: 1, overflow: TextOverflow.ellipsis),
      ]),
    );
  }
}

/// Component score bars.
class _ScoreBreakdownCard extends StatelessWidget {
  final SwingSignal sig;
  const _ScoreBreakdownCard({required this.sig});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(context,
            icon: LucideIcons.gauge,
            accent: c.accent,
            title: 'Signal Strength',
            subtitle: sig.scoreBucket,
            trailing: SwingScoreReadout(score: sig.score, bucket: sig.scoreBucket)),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
          child: Column(
            children: sig.components
                .map((cmp) => SwingScoreBar(label: cmp.label, score: cmp.score, detail: cmp.detail))
                .toList(),
          ),
        ),
      ]),
    );
  }
}

/// Signal tags grouped by strategy.
class _SignalsCard extends StatelessWidget {
  final SwingSignal sig;
  const _SignalsCard({required this.sig});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    Widget section(SignalKind kind, IconData icon, Color accent, {bool danger = false}) {
      final tags = sig.tagsByKind[kind] ?? const [];
      if (tags.isEmpty) return const SizedBox();
      final fired = tags.where((t) => t.active).length;
      return Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(icon, size: 12, color: accent),
            const SizedBox(width: 6),
            Text(kind.title, style: AppTextStyles.label(c.t1).copyWith(fontSize: 11)),
            const SizedBox(width: 6),
            Text('$fired/${tags.length}', style: AppTextStyles.monoXs(accent)),
          ]),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 5,
            children: tags.map((t) => SignalTagChip(tag: t, danger: danger)).toList(),
          ),
        ]),
      );
    }

    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(context,
            icon: LucideIcons.listChecks, accent: c.accent, title: 'Signals Detected'),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 0, 14, 6),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            section(SignalKind.continuation, LucideIcons.trendingUp, c.up),
            section(SignalKind.pullback, LucideIcons.cornerDownRight, c.blue),
            section(SignalKind.reversal, LucideIcons.refreshCw, c.gold),
            section(SignalKind.avoid, LucideIcons.alertTriangle, c.dn, danger: true),
          ]),
        ),
      ]),
    );
  }
}

/// AI (LLM) trade plan card — unchanged behaviour, extracted for clarity.
class _LlmPlanCard extends StatelessWidget {
  final Map<String, dynamic> llm;
  const _LlmPlanCard({required this.llm});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return DenseCard(
      clip: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        denseTableHeader(context,
            icon: LucideIcons.brain,
            accent: c.accent,
            title: 'AI Trade Plan',
            trailing: llm['confidence'] != null
                ? AppBadge(
                    text: '${llm['confidence']} Confidence',
                    variant: llm['confidence'] == 'High' ? BadgeVariant.up : BadgeVariant.gold,
                    fontSize: 9)
                : null),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(
                llm['trade_plan']?.toString() ??
                    (llm['summary']?.toString() ??
                        'AI trade plan details are not available for this stock.'),
                style: AppTextStyles.bodySmall(c.t1)),
            if (llm['entry_trigger'] != null) ...[
              const SizedBox(height: 10),
              _llmRow(c, LucideIcons.crosshair, 'Entry', llm['entry_trigger'].toString(), c.blue),
            ],
            if (llm['exit_plan'] != null) ...[
              const SizedBox(height: 6),
              _llmRow(c, LucideIcons.logOut, 'Exit', llm['exit_plan'].toString(), c.up),
            ],
            if (llm['hold_duration'] != null) ...[
              const SizedBox(height: 6),
              _llmRow(c, LucideIcons.clock, 'Hold', llm['hold_duration'].toString(), c.t2),
            ],
            if (_llmKeyLevels(llm['key_levels']) != null) ...[
              const SizedBox(height: 6),
              _llmRow(c, LucideIcons.layers, 'Key Levels', _llmKeyLevels(llm['key_levels'])!, c.accent),
            ],
            if (llm['edge'] != null) ...[
              const SizedBox(height: 6),
              _llmRow(c, LucideIcons.zap, 'Edge', llm['edge'].toString(), c.gold),
            ],
            if (llm['risk_warning'] != null) ...[
              const SizedBox(height: 6),
              _llmRow(c, LucideIcons.alertTriangle, 'Risk', llm['risk_warning'].toString(), c.dn),
            ],
          ]),
        ),
      ]),
    );
  }
}

/// The price-levels / indicators / S-R / fibonacci grid.
class _LevelsGrid extends StatelessWidget {
  final Map<String, dynamic> a;
  const _LevelsGrid({required this.a});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Expanded(
          child: _kvCard(context, LucideIcons.crosshair, c.blue, 'Price Levels', [
        _kvRow(context, 'Entry', a['entry'] != null ? '₹${a['entry']}' : '—', c.blue),
        _kvRow(context, 'Max Entry', a['max_entry_price'] != null ? '≤₹${a['max_entry_price']} (skip gap-up)' : '—', c.gold),
        _kvRow(context, 'Stop Loss', a['stop_loss'] != null ? '₹${a['stop_loss']} (${a['risk_pct']}%, on close)' : '—', c.dn),
        _kvRow(
            context,
            'Exit',
            a['target1'] != null
                ? '₹${a['target1']} (+${a['reward_pct']}%)'
                : 'Day 20 time exit — no target (v4)',
            c.up),
      ])),
      const SizedBox(width: 12),
      Expanded(
          child: _kvCard(context, LucideIcons.activity, c.accent, 'Indicators', [
        _kvRow(context, 'RSI(14)', '${a['rsi'] ?? '—'}',
            (a['rsi'] as num?) != null && (a['rsi'] as num) < 40 ? c.up : c.t1),
        _kvRow(context, 'MACD', '${a['macd_signal'] ?? '—'} (${a['macd_hist'] ?? '—'})',
            a['macd_signal'] == 'Bullish' ? c.up : c.dn),
        _kvRow(context, 'EMA 20', a['ema20'] != null ? '₹${a['ema20']}' : '—', c.t1),
        _kvRow(context, 'EMA 50', a['ema50'] != null ? '₹${a['ema50']}' : '—', c.t1),
        _kvRow(context, 'ATR', a['atr'] != null ? '₹${a['atr']}' : '—', c.t1),
        _kvRow(context, 'Volume', '${a['volume_ratio'] ?? '—'}x avg',
            a['volume_spike'] == true ? c.gold : c.t1),
        _kvRow(context, 'Pattern', a['pattern']?.toString() ?? 'None', c.gold),
        _kvRow(context, 'BB Position', a['bb_position']?.toString() ?? '—', c.t1),
      ])),
      const SizedBox(width: 12),
      Expanded(
          child: Column(children: [
        _kvCard(context, LucideIcons.layers, c.up, 'Support / Resistance', [
          if (a['supports'] is List && (a['supports'] as List).isNotEmpty)
            ...List<Widget>.from((a['supports'] as List).map((s) => _kvRow(context, 'Support', '₹$s', c.up)))
          else
            _kvRow(context, 'Support', '—', c.t3),
          if (a['resistances'] is List && (a['resistances'] as List).isNotEmpty)
            ...List<Widget>.from((a['resistances'] as List).map((r) => _kvRow(context, 'Resistance', '₹$r', c.dn)))
          else
            _kvRow(context, 'Resistance', '—', c.t3),
        ]),
        const SizedBox(height: 12),
        if (a['fibonacci'] is Map && (a['fibonacci'] as Map).isNotEmpty)
          _kvCard(context, LucideIcons.gitBranch, c.accent, 'Fibonacci Levels',
              (a['fibonacci'] as Map<String, dynamic>).entries.map((e) => _kvRow(context, e.key, '₹${e.value}', c.accent)).toList()),
      ])),
    ]);
  }
}

// Normalizes the LLM `key_levels` payload (String, List, or Map) to a
// single display string; returns null when there's nothing meaningful.
String? _llmKeyLevels(dynamic raw) {
  if (raw == null) return null;
  if (raw is String) {
    final t = raw.trim();
    return t.isEmpty ? null : t;
  }
  if (raw is List) {
    final parts = raw.where((e) => e != null).map((e) => e.toString().trim()).where((e) => e.isNotEmpty);
    return parts.isEmpty ? null : parts.join(', ');
  }
  if (raw is Map) {
    final parts = raw.entries
        .where((e) => e.value != null && e.value.toString().trim().isNotEmpty)
        .map((e) => '${e.key}: ${e.value}');
    return parts.isEmpty ? null : parts.join(', ');
  }
  final t = raw.toString().trim();
  return t.isEmpty ? null : t;
}

Widget _llmRow(AppColorScheme c, IconData icon, String label, String text, Color clr) {
  return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Icon(icon, size: 12, color: clr),
    const SizedBox(width: 6),
    Text('$label: ', style: AppTextStyles.captionXs(clr).copyWith(fontWeight: FontWeight.w700)),
    Expanded(child: Text(text, style: AppTextStyles.bodySmall(c.t2))),
  ]);
}

/// Small key/value dense card: header + right-aligned mono value rows.
Widget _kvCard(BuildContext context, IconData icon, Color accent, String title, List<Widget> rows) {
  return DenseCard(
    clip: true,
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      denseTableHeader(context, icon: icon, accent: accent, title: title),
      Padding(
        padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
        child: Column(children: rows),
      ),
    ]),
  );
}

Widget _kvRow(BuildContext context, String label, String value, Color clr) {
  final c = context.colors;
  return Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Row(children: [
      Text(label, style: AppTextStyles.captionXs(c.t3)),
      const Spacer(),
      denseNum(context, value, clr),
    ]),
  );
}

/// Price formatter shared by the desk — 1 decimal, "—" for null.
String _px(num? v) => v == null ? '—' : v.toStringAsFixed(1);

// ═══════════════════════════════════════════════════════════════
//  TAB 3: PAPER TRADING
// ═══════════════════════════════════════════════════════════════

/// Reset dialog — lets the user set the starting capital. Returns the chosen
/// amount, or null if cancelled.
Future<double?> _showResetCapitalDialog(BuildContext context, num current) {
  final c = context.colors;
  final ctrl = TextEditingController(text: current.toStringAsFixed(0));
  return showDialog<double>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Reset Paper Account'),
      content: Column(mainAxisSize: MainAxisSize.min, children: [
        Text(
          'Set your starting capital. This clears all positions and closed '
          'trades and frees every 14-Day Desk stock to be paper-tested again. '
          'Paper trading only — no real money.',
          style: AppTextStyles.bodySmall(c.t2),
        ),
        const SizedBox(height: 14),
        TextField(
          controller: ctrl,
          autofocus: true,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(
            labelText: 'Starting capital',
            prefixText: '₹ ',
            border: OutlineInputBorder(),
            isDense: true,
          ),
        ),
      ]),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
        FilledButton(
          onPressed: () {
            final v = double.tryParse(ctrl.text.replaceAll(',', '').trim());
            Navigator.pop(ctx, (v != null && v > 0) ? v : null);
          },
          child: const Text('Reset'),
        ),
      ],
    ),
  );
}

class _PaperTradingTab extends ConsumerWidget {
  const _PaperTradingTab();

  static const _posCols = [
    DenseCol('STOCK', 3, numeric: false),
    DenseCol('QTY', 1),
    DenseCol('ENTRY', 2),
    DenseCol('LTP', 2),
    DenseCol('STOP', 2),
    DenseCol('TARGET', 2),
    DenseCol('P&L', 3),
    DenseCol('STATUS', 2),
  ];

  static const _closedCols = [
    DenseCol('STOCK', 3, numeric: false),
    DenseCol('ENTRY', 2),
    DenseCol('EXIT', 2),
    DenseCol('QTY', 1),
    DenseCol('P&L', 3),
    DenseCol('REASON', 3, numeric: false),
    DenseCol('DATE', 2),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final asyncStatus = ref.watch(swingPaperStatusProvider);

    return asyncStatus.when(
      loading: () => const DensePulseLoader(label: 'Loading paper trades…'),
      error: (e, _) => ErrorRetry(
        title: 'Error loading paper trades',
        detail: '$e',
        compact: true,
        onRetry: () => ref.read(swingPaperKeyProvider.notifier).refresh(),
      ),
      data: (data) {
        final positions = List<Map<String, dynamic>>.from(data['positions'] ?? []);
        final closed = List<Map<String, dynamic>>.from(data['closed_trades'] ?? []);
        final pending = List<Map<String, dynamic>>.from(data['pending_entries'] ?? []);
        final missed = List<Map<String, dynamic>>.from(data['missed_entries'] ?? []);
        final equity = data['daily_equity'] is List
            ? List<Map<String, dynamic>>.from(data['daily_equity'])
            : <Map<String, dynamic>>[];
        final totalPnl = (data['total_pnl'] as num?)?.toDouble() ?? 0;
        final totalPnlPct = (data['total_pnl_pct'] as num?)?.toDouble() ?? 0;

        // Derived exposure + open risk (sum of (entry-stop)*qty for live positions).
        double exposure = 0, openRisk = 0;
        for (final p in positions) {
          final entry = (p['entry_price'] as num?)?.toDouble() ?? 0;
          final stop = (p['stop_loss'] as num?)?.toDouble() ?? 0;
          final qty = (p['quantity'] as num?)?.toDouble() ?? 0;
          exposure += entry * qty;
          final risk = (entry - stop) * qty;
          if (risk > 0) openRisk += risk;
        }

        return ListView(padding: const EdgeInsets.only(top: 12), children: [
          AnimatedListItem(
            index: 0,
            child: DenseCard(
              child: denseTableHeader(context,
                  icon: LucideIcons.wallet,
                  accent: c.accent,
                  title: 'Paper Trading — 30-Day Challenge',
                  subtitle: 'Day ${data['day_count'] ?? 0}/30',
                  trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                    HeaderButton(
                      icon: const Icon(LucideIcons.refreshCw, size: 13, color: Colors.white),
                      text: 'Auto-Check SL/TGT',
                      solidColor: c.accent,
                      onTap: () async {
                        await ref.read(apiServiceProvider).swingPaperAutoCheck();
                        ref.read(swingPaperKeyProvider.notifier).refresh();
                      },
                    ),
                    const SizedBox(width: 6),
                    HeaderButton(
                      icon: Icon(LucideIcons.rotateCcw, size: 13, color: c.dn),
                      text: 'Reset',
                      onTap: () async {
                        final cap = await _showResetCapitalDialog(
                            context, (data['initial_capital'] as num?) ?? 1000000);
                        if (cap == null) return;
                        await ref
                            .read(apiServiceProvider)
                            .swingPaperReset(capital: cap);
                        ref.read(swingPaperKeyProvider.notifier).refresh();
                        // Freed desk stocks become paper-testable again.
                        ref.invalidate(swingDeskProvider);
                      },
                    ),
                  ])),
            ),
          ),
          const SizedBox(height: 12),

          // ── KPI grid — capital, cash, equity, exposure, P&L, win rate, open risk, trades ──
          AnimatedListItem(
            index: 1,
            child: KpiGrid(perRow: 4, cells: [
              Kpi('CAPITAL', formatINR((data['initial_capital'] as num?) ?? 0), 'initial', c.t1),
              Kpi('CASH', formatINR((data['cash'] as num?) ?? 0), 'available', c.blue),
              Kpi('EQUITY', formatINR((data['total_equity'] as num?) ?? 0), 'cash + positions', c.t1),
              Kpi('EXPOSURE', formatINR(exposure), '${positions.length} positions', c.t1),
              Kpi('TOTAL P&L', formatSignedINR(totalPnl), formatPct(totalPnlPct, decimals: 1),
                  context.pnlColor(totalPnl)),
              Kpi('WIN RATE', '${data['win_rate'] ?? 0}%', 'W:${data['wins'] ?? 0} · L:${data['losses'] ?? 0}', c.gold),
              Kpi('OPEN RISK', formatINR(openRisk), 'if all stops hit', c.dn),
              Kpi('TRADES', '${data['total_trades'] ?? 0}', 'total closed', c.t1),
            ]),
          ),
          const SizedBox(height: 12),

          if (equity.length > 1) ...[
            AnimatedListItem(
              index: 2,
              child: DenseCard(
                clip: true,
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  denseTableHeader(context,
                      icon: LucideIcons.lineChart,
                      accent: context.pnlColor(totalPnl),
                      title: 'Equity Curve',
                      subtitle: '${equity.length} sessions',
                      trailing: densePnlTrailing(context, totalPnl, totalPnlPct)),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
                    child: SizedBox(
                        height: 120,
                        child: CustomPaint(
                          size: const Size(double.infinity, 120),
                          painter: _EquityCurvePainter(equity, c),
                        )),
                  ),
                ]),
              ),
            ),
            const SizedBox(height: 12),
          ],

          if (pending.isNotEmpty) ...[
            AnimatedListItem(
              index: 2,
              child: DenseCard(
                clip: true,
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  denseTableHeader(context,
                      icon: LucideIcons.hourglass,
                      accent: c.t3,
                      title: 'Pending Entries',
                      subtitle: '${pending.length} watching — no position opened yet'),
                  ...pending.map((p) {
                    final low = (p['buy_zone_low'] as num?)?.toDouble();
                    final high = (p['buy_zone_high'] as num?)?.toDouble();
                    final lastObs = (p['last_observed_price'] as num?)?.toDouble();
                    final status = actionableStatusFrom(
                        p['actionable_status']?.toString() ?? 'WAIT_FOR_ENTRY');
                    return Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      child: Row(children: [
                        Expanded(
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(p['name']?.toString() ?? p['symbol']?.toString() ?? '',
                                style: AppTextStyles.bodySmall(c.t1)),
                            Text(
                              'zone ₹${low?.toStringAsFixed(2) ?? '—'}–₹${high?.toStringAsFixed(2) ?? '—'}'
                              '${lastObs != null ? ' · last seen ₹${lastObs.toStringAsFixed(2)}' : ''}',
                              style: AppTextStyles.captionXs(c.t3),
                            ),
                          ]),
                        ),
                        ActionableStatusBadge(status: status),
                      ]),
                    );
                  }),
                ]),
              ),
            ),
            const SizedBox(height: 12),
          ],

          AnimatedListItem(
            index: 3,
            child: DenseCard(
              clip: true,
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                denseTableHeader(context,
                    icon: LucideIcons.activity,
                    accent: c.blue,
                    title: 'Active Positions',
                    subtitle: '${positions.length} open'),
                denseColumnHeader(context, _posCols),
                if (positions.isEmpty)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 26),
                    child: Center(
                        child: Text(
                            'No active positions — open one from the 14-Day Desk (Paper Buy)',
                            style: AppTextStyles.bodySmall(c.t4))),
                  )
                else
                  ...positions.asMap().entries.map((e) {
                    final pos = e.value;
                    final pnl = (pos['pnl'] as num?)?.toDouble() ?? 0;
                    final ltp = (pos['ltp'] as num?)?.toDouble();
                    final stop = (pos['stop_loss'] as num?)?.toDouble();
                    final tgt = (pos['target'] as num?)?.toDouble();
                    final statusColor =
                        pos['sl_hit'] == true ? c.dn : pos['tgt_hit'] == true ? c.up : c.t3;
                    // Distance to stop (and target, if a legacy one exists).
                    String statusSub = '';
                    if (ltp != null && stop != null && ltp > 0) {
                      final toStop = (ltp - stop) / ltp * 100;
                      statusSub = '▼${toStop.toStringAsFixed(1)}%';
                      if (tgt != null) {
                        final toTgt = (tgt - ltp) / ltp * 100;
                        statusSub += ' ▲${toTgt.toStringAsFixed(1)}%';
                      }
                    }
                    final actualFill = (pos['actual_fill_price'] as num?)?.toDouble();
                    final filledAt = pos['filled_at']?.toString();
                    final fillSub = actualFill != null
                        ? formatFillLabel(actualFill, filledAt)
                        : (pos['setup']?.toString() ?? '');
                    return DenseRow(
                      alt: e.key.isOdd,
                      cols: _posCols,
                      cells: [
                        DInstrument(symbol: pos['name']?.toString() ?? '', sub: fillSub, up: pnl >= 0),
                        denseNum(context, '${pos['quantity']}', c.t2),
                        denseNum(context, (pos['entry_price'] as num?)?.toStringAsFixed(1) ?? '—', c.t3),
                        denseNum(context, ltp?.toStringAsFixed(1) ?? '—', c.t1, bold: true),
                        denseNum(context, stop?.toStringAsFixed(1) ?? '—', c.dn),
                        denseNum(context, tgt?.toStringAsFixed(1) ?? 'Day 20', c.up),
                        denseNum(context, '${formatSignedINR(pnl)} (${pos['pnl_pct'] ?? '—'}%)', context.pnlColor(pnl)),
                        Column(crossAxisAlignment: CrossAxisAlignment.end, mainAxisSize: MainAxisSize.min, children: [
                          denseNum(context, pos['status']?.toString() ?? 'Active', statusColor),
                          if (statusSub.isNotEmpty)
                            Text(statusSub, style: AppTextStyles.captionXs(c.t3), textAlign: TextAlign.right),
                        ]),
                      ],
                    );
                  }),
              ]),
            ),
          ),
          const SizedBox(height: 12),

          if (closed.isNotEmpty)
            AnimatedListItem(
              index: 4,
              child: DenseCard(
                clip: true,
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  denseTableHeader(context,
                      icon: LucideIcons.history,
                      accent: c.gold,
                      title: 'Trade Journal',
                      subtitle: '${closed.length} trades'),
                  denseColumnHeader(context, _closedCols),
                  ...closed.reversed.take(15).toList().asMap().entries.map((e) {
                    final trade = e.value;
                    final pnl = (trade['pnl'] as num?)?.toDouble() ?? 0;
                    return DenseRow(
                      alt: e.key.isOdd,
                      cols: _closedCols,
                      cells: [
                        DInstrument(symbol: trade['name']?.toString() ?? '', sub: '', up: pnl >= 0),
                        denseNum(context, (trade['entry_price'] as num?)?.toStringAsFixed(1) ?? '—', c.t3),
                        denseNum(context, (trade['exit_price'] as num?)?.toStringAsFixed(1) ?? '—', c.t2),
                        denseNum(context, '${trade['quantity']}', c.t2),
                        denseNum(context, '${formatSignedINR(pnl)} (${trade['pnl_pct'] ?? '—'}%)', context.pnlColor(pnl)),
                        Text(trade['reason']?.toString() ?? '',
                            style: AppTextStyles.captionXs(c.t3), maxLines: 1, overflow: TextOverflow.ellipsis),
                        denseNum(context, trade['exit_date']?.toString().split(' ').first ?? '', c.t4),
                      ],
                    );
                  }),
                ]),
              ),
            ),

          if (missed.isNotEmpty) ...[
            const SizedBox(height: 12),
            AnimatedListItem(
              index: 5,
              child: DenseCard(
                clip: true,
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  denseTableHeader(context,
                      icon: LucideIcons.ban,
                      accent: c.dn,
                      title: 'Missed / Expired Setups',
                      subtitle: '${missed.length} — shown for transparency, never filled'),
                  ...missed.reversed.take(15).map((m) => Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
                        child: Row(children: [
                          Expanded(
                            child: Text(m['name']?.toString() ?? m['symbol']?.toString() ?? '',
                                style: AppTextStyles.bodySmall(c.t1)),
                          ),
                          Expanded(
                            flex: 2,
                            child: Text(m['removal_reason']?.toString() ?? '',
                                style: AppTextStyles.captionXs(c.t3),
                                maxLines: 1, overflow: TextOverflow.ellipsis),
                          ),
                        ]),
                      )),
                ]),
              ),
            ),
          ],
          const SizedBox(height: 24),
        ]);
      },
    );
  }
}

class _EquityCurvePainter extends CustomPainter {
  final List<Map<String, dynamic>> data;
  final AppColorScheme c;
  _EquityCurvePainter(this.data, this.c);

  @override
  void paint(Canvas canvas, Size size) {
    if (data.isEmpty) return;
    final values = data.map((d) => (d['equity'] as num?)?.toDouble() ?? 0).toList();
    final minV = values.reduce(math.min);
    final maxV = values.reduce(math.max);
    final range = maxV - minV;
    if (range == 0) return;

    final initial = values.first;
    final path = Path();
    final fillPath = Path();

    for (int i = 0; i < values.length; i++) {
      final x = i / (values.length - 1) * size.width;
      final y = size.height - ((values[i] - minV) / range * size.height);
      if (i == 0) {
        path.moveTo(x, y);
        fillPath.moveTo(x, y);
      } else {
        path.lineTo(x, y);
        fillPath.lineTo(x, y);
      }
    }

    final lastVal = values.last;
    final isProfit = lastVal >= initial;

    fillPath.lineTo(size.width, size.height);
    fillPath.lineTo(0, size.height);
    fillPath.close();
    canvas.drawPath(
        fillPath,
        Paint()
          ..shader = LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              (isProfit ? c.up : c.dn).withValues(alpha: 0.15),
              (isProfit ? c.up : c.dn).withValues(alpha: 0.02),
            ],
          ).createShader(Rect.fromLTWH(0, 0, size.width, size.height)));

    canvas.drawPath(
        path,
        Paint()
          ..color = isProfit ? c.up : c.dn
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => true;
}
