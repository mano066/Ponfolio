import 'dart:async';
import 'package:aiei_wealth/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../core/constants.dart';
import '../../core/extensions.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_dimensions.dart';
import '../../core/theme/app_text_styles.dart';
import '../../providers/providers.dart';
import 'dashboard_screen.dart';
import 'equities_screen.dart';
import 'analytics_screen.dart';
import 'ai_triggers_screen.dart';
import 'strategies_screen.dart';
import 'reports_screen.dart';
import 'research_screen.dart';
import 'settings_screen.dart';
import 'mutual_funds_screen.dart';
import 'deep_analysis_screen.dart';
import 'mf_screener_screen.dart';
import 'sip_simulator_screen.dart';
import 'allocation_screen.dart';
import '../widgets/ai_chatbot.dart';
import 'swing_trading_screen.dart';
import 'expenses_screen.dart';
import '../widgets/stock_picker.dart';
import '../../services/export_service.dart';

/// ─── Stitch Design Tokens (AppShell) ───
/// surface:            #081425  (bg1 — sidebar bg)
/// surface-container:  #152031  (bg2 — header bg)
/// surface-container-low: #111c2d (active nav bg)
/// surface-container-high: #1F2A3C (hover bg)
/// outline-variant:    #1E293B  (borders)
/// primary-container:  #4D8EFF  (active accent)
/// Glow: box-shadow 0 0 12px [Color]33 (20%)

class AppShell extends ConsumerWidget {
  const AppShell({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final activeTab = ref.watch(activeTabProvider);
    final compact = MediaQuery.sizeOf(context).width < 1000;

    final shortcuts = <ShortcutActivator, VoidCallback>{
      const SingleActivator(LogicalKeyboardKey.digit1, control: true): () => ref.read(activeTabProvider.notifier).setTab(AppTab.dashboard),
      const SingleActivator(LogicalKeyboardKey.digit2, control: true): () => ref.read(activeTabProvider.notifier).setTab(AppTab.equities),
      const SingleActivator(LogicalKeyboardKey.digit3, control: true): () => ref.read(activeTabProvider.notifier).setTab(AppTab.mutualFunds),
      const SingleActivator(LogicalKeyboardKey.digit4, control: true): () => ref.read(activeTabProvider.notifier).setTab(AppTab.analytics),
      const SingleActivator(LogicalKeyboardKey.digit5, control: true): () => ref.read(activeTabProvider.notifier).setTab(AppTab.aiSignals),
      const SingleActivator(LogicalKeyboardKey.digit6, control: true): () => ref.read(activeTabProvider.notifier).setTab(AppTab.deepAnalysis),
      const SingleActivator(LogicalKeyboardKey.digit7, control: true): () => ref.read(activeTabProvider.notifier).setTab(AppTab.swingTrading),
      const SingleActivator(LogicalKeyboardKey.digit8, control: true): () => ref.read(activeTabProvider.notifier).setTab(AppTab.reports),
      const SingleActivator(LogicalKeyboardKey.digit9, control: true): () => ref.read(activeTabProvider.notifier).setTab(AppTab.settings),
      const SingleActivator(LogicalKeyboardKey.digit0, control: true): () => ref.read(activeTabProvider.notifier).setTab(AppTab.expenses),
      const SingleActivator(LogicalKeyboardKey.keyT, control: true): () => ref.read(isDarkModeProvider.notifier).toggle(),
      const SingleActivator(LogicalKeyboardKey.f5): () { ref.invalidate(portfolioProvider); ref.invalidate(mfPortfolioProvider); },
      const SingleActivator(LogicalKeyboardKey.keyR, control: true): () { ref.invalidate(portfolioProvider); ref.invalidate(mfPortfolioProvider); },
      const SingleActivator(LogicalKeyboardKey.keyK, control: true): () {
        final syms = ref.read(portfolioProvider).whenOrNull(data: (d) =>
          List<Map<String, dynamic>>.from(d['holdings'] ?? [])
            .map((h) => h['symbol'].toString()).toList()) ?? [];
        StockPickerModal.show(context, portfolioSymbols: syms,
          onStockAdded: () => ref.invalidate(portfolioProvider));
      },
    };

    return CallbackShortcuts(
      bindings: shortcuts,
      child: Focus(
        autofocus: true,
        child: Scaffold(
          backgroundColor: c.bg0,
          body: Stack(
            children: [
              Row(
                children: [
                  if (!compact) _Sidebar(activeTab: activeTab),
                  Expanded(
                    child: Column(
                      children: [
                        if (compact)
                          SafeArea(bottom: false, child: Row(children: [
                            PopupMenuButton<AppTab>(
                              tooltip: 'Open navigation',
                              onSelected: (tab) => ref.read(activeTabProvider.notifier).setTab(tab),
                              itemBuilder: (_) => AppTab.values.where((tab) => tab != AppTab.welcome).map((tab) =>
                                PopupMenuItem(value: tab, child: Text(tab.label))).toList(),
                              icon: const Icon(Icons.menu),
                            ),
                            Expanded(child: Text(activeTab.label, style: AppTextStyles.heading3(c.t1))),
                            IconButton(tooltip: 'Toggle theme', icon: const Icon(Icons.brightness_6),
                              onPressed: () => ref.read(isDarkModeProvider.notifier).toggle()),
                          ]))
                        else _Header(activeTab: activeTab),
                        Expanded(
                          child: Container(
                            color: c.bg0,
                            padding: EdgeInsets.all(compact ? 12 : 20),
                            child: _TabBody(activeTab: activeTab),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              if (!compact) const AIChatBot(),
            ],
          ),
        ),
      ),
    );
  }
}

/// Keeps all navigable tabs alive using IndexedStack.
class _TabBody extends StatefulWidget {
  final AppTab activeTab;
  const _TabBody({required this.activeTab});

  @override
  State<_TabBody> createState() => _TabBodyState();
}

class _TabBodyState extends State<_TabBody> {
  final Set<AppTab> _visited = {};

  static const _tabs = [
    AppTab.dashboard, AppTab.equities, AppTab.analytics,
    AppTab.aiSignals, AppTab.strategies, AppTab.reports,
    AppTab.settings, AppTab.mutualFunds, AppTab.deepAnalysis,
    AppTab.mfScreener, AppTab.sipSimulator, AppTab.allocation,
    AppTab.swingTrading, AppTab.expenses, AppTab.research,
  ];

  @override
  Widget build(BuildContext context) {
    _visited.add(widget.activeTab);
    final idx = _tabs.indexOf(widget.activeTab).clamp(0, _tabs.length - 1);
    return IndexedStack(
      index: idx,
      children: _tabs.map((tab) => _visited.contains(tab)
        ? TickerMode(enabled: tab == widget.activeTab, child: _buildContent(tab))
        : const SizedBox.shrink()).toList(),
    );
  }

  static Widget _buildContent(AppTab tab) {
    switch (tab) {
      case AppTab.dashboard: return const DashboardScreen();
      case AppTab.equities: return const EquitiesScreen();
      case AppTab.analytics: return const AnalyticsScreen();
      case AppTab.aiSignals: return const AITriggersScreen();
      case AppTab.strategies: return const StrategiesScreen();
      case AppTab.reports: return const ReportsScreen();
      case AppTab.settings: return const SettingsScreen();
      case AppTab.mutualFunds: return const MutualFundsScreen();
      case AppTab.deepAnalysis: return const DeepAnalysisScreen();
      case AppTab.mfScreener: return const MFScreenerScreen();
      case AppTab.sipSimulator: return const SIPSimulatorScreen();
      case AppTab.allocation: return const AllocationScreen();
      case AppTab.swingTrading: return const SwingTradingScreen();
      case AppTab.expenses: return const ExpensesScreen();
      case AppTab.research: return const ResearchScreen();
      default: return _PlaceholderView(tab: tab);
    }
  }
}

class _PlaceholderView extends StatelessWidget {
  final AppTab tab;
  const _PlaceholderView({required this.tab});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
      Icon(LucideIcons.construction, size: 48, color: c.t4),
      const SizedBox(height: 16),
      Text(tab.label, style: AppTextStyles.heading2(c.t1)),
      const SizedBox(height: 8),
      Text('Coming soon — Phase 3 implementation', style: AppTextStyles.body(c.t3)),
    ]));
  }
}

// ══════════════════════════════════════════════════════════════
//  SIDEBAR — Stitch Design System
//  Solid bg1 (#081425), no gradients
//  Active: left blue bar + surface-container-low bg
//  Hover: surface-container-high + glow
// ══════════════════════════════════════════════════════════════

class _Sidebar extends ConsumerWidget {
  final AppTab activeTab;
  const _Sidebar({required this.activeTab});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;

    return Container(
      width: AppDimensions.sidebarWidth,
      decoration: BoxDecoration(
        // Stitch: solid surface background, NO gradient
        color: c.bg1,
        border: Border(right: BorderSide(color: c.bd, width: 1)),
      ),
      child: Column(
        children: [
          // ─── Logo ───
          _SidebarLogo(),

          Divider(color: c.bd, height: 1),

          // ─── Kite Status ───
          _KiteStatusWidget(),

          const SizedBox(height: 8),

          // ─── Navigation ───
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              children: [
                _NavGroup(label: 'MAIN', children: [
                  _NavItem(tab: AppTab.dashboard, icon: LucideIcons.layoutDashboard, activeTab: activeTab),
                  _NavItem(tab: AppTab.equities, icon: LucideIcons.trendingUp, activeTab: activeTab),
                  _NavItem(tab: AppTab.mutualFunds, icon: LucideIcons.briefcase, activeTab: activeTab),
                  _NavItem(tab: AppTab.allocation, icon: LucideIcons.pieChart, activeTab: activeTab),
                  _NavItem(tab: AppTab.expenses, icon: LucideIcons.receipt, activeTab: activeTab),
                  _NavItem(tab: AppTab.mfScreener, icon: LucideIcons.microscope, activeTab: activeTab),
                  _NavItem(tab: AppTab.sipSimulator, icon: LucideIcons.calculator, activeTab: activeTab),
                ]),
                const SizedBox(height: 12),
                _NavGroup(label: 'INTELLIGENCE', children: [
                  _NavItem(tab: AppTab.analytics, icon: LucideIcons.barChart2, activeTab: activeTab),
                  _NavItem(tab: AppTab.aiSignals, icon: LucideIcons.zap, activeTab: activeTab),
                  _NavItem(tab: AppTab.strategies, icon: LucideIcons.layers, activeTab: activeTab),
                  _NavItem(tab: AppTab.deepAnalysis, icon: LucideIcons.target, activeTab: activeTab),
                  _NavItem(tab: AppTab.swingTrading, icon: LucideIcons.barChart3, activeTab: activeTab),
                  _NavItem(tab: AppTab.reports, icon: LucideIcons.fileText, activeTab: activeTab),
                  _NavItem(tab: AppTab.research, icon: LucideIcons.bookOpen, activeTab: activeTab),
                ]),
                const SizedBox(height: 12),
                _NavGroup(label: 'SYSTEM', children: [
                  _NavItem(tab: AppTab.settings, icon: LucideIcons.settings, activeTab: activeTab),
                ]),
              ],
            ),
          ),

          _UserProfileSection(),
          _KiteActionsSection(),
          _NiftyTicker(),
          const SizedBox(height: 4),
        ],
      ),
    );
  }
}

/// Stitch-style logo with blue glow icon
class _SidebarLogo extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      height: AppDimensions.headerHeight,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      alignment: Alignment.centerLeft,
      child: Row(
        children: [
          // Solid blue icon with glow — Stitch reference
          Container(
            width: 30, height: 30,
            decoration: BoxDecoration(
              color: c.blue.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: c.blue.withValues(alpha: 0.25)),
              boxShadow: [
                BoxShadow(
                  color: c.blue.withValues(alpha: 0.20),
                  blurRadius: 12,
                ),
              ],
            ),
            child: Center(
              child: _BrandMark(color: c.blue, size: 18),
            ),
          ),
          const SizedBox(width: 10),
          Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Ponfolio',
                style: AppTextStyles.sidebarBrand(c.blue).copyWith(
                  letterSpacing: -0.3,
                )),
              Text('Terminal v${AppConstants.version}',
                style: AppTextStyles.captionXs(c.t3).copyWith(
                  letterSpacing: 0.3,
                  fontSize: 9,
                )),
            ],
          ),
        ],
      ),
    );
  }
}

/// Ponfolio uptrend logo mark — matches the product site's favicon
/// (rising line + node). Painted so it inherits the brand color and scales crisply.
class _BrandMark extends StatelessWidget {
  final Color color;
  final double size;
  const _BrandMark({required this.color, required this.size});
  @override
  Widget build(BuildContext context) =>
      CustomPaint(size: Size.square(size), painter: _BrandMarkPainter(color));
}

class _BrandMarkPainter extends CustomPainter {
  final Color color;
  _BrandMarkPainter(this.color);
  @override
  void paint(Canvas canvas, Size size) {
    final s = size.width / 32.0; // artwork defined on a 32×32 grid
    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.8 * s
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final path = Path()
      ..moveTo(6 * s, 21 * s)
      ..lineTo(12 * s, 15 * s)
      ..lineTo(16 * s, 19 * s)
      ..lineTo(26 * s, 8 * s);
    canvas.drawPath(path, stroke);
    canvas.drawCircle(Offset(26 * s, 8 * s), 2.4 * s, Paint()..color = color);
  }

  @override
  bool shouldRepaint(covariant _BrandMarkPainter old) => old.color != color;
}

class _NavGroup extends StatelessWidget {
  final String label;
  final List<Widget> children;
  const _NavGroup({required this.label, required this.children});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
          // Stitch: label-caps → 11px, 600, uppercase, 0.05em
          child: Text(label,
            style: AppTextStyles.captionXs(c.t4).copyWith(
              letterSpacing: 1.2,
              fontSize: 9,
              fontWeight: FontWeight.w600,
            )),
        ),
        ...children,
      ],
    );
  }
}

/// Nav item with Stitch active indicator + hover glow
class _NavItem extends ConsumerStatefulWidget {
  final AppTab tab;
  final IconData icon;
  final AppTab activeTab;
  const _NavItem({required this.tab, required this.icon, required this.activeTab});

  @override
  ConsumerState<_NavItem> createState() => _NavItemState();
}

class _NavItemState extends ConsumerState<_NavItem> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final isActive = widget.activeTab == widget.tab;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 1),
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        onEnter: (_) => setState(() => _hovered = true),
        onExit: (_) => setState(() => _hovered = false),
        child: GestureDetector(
          onTap: () => ref.read(activeTabProvider.notifier).setTab(widget.tab),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeOutCubic,
            padding: const EdgeInsets.symmetric(
              horizontal: AppDimensions.sidebarNavPaddingH,
              vertical: AppDimensions.sidebarNavPaddingV,
            ),
            decoration: BoxDecoration(
              // blueBg, not a hardcoded surface: the label is drawn in c.t1, so
              // a fixed dark fill turns the active tab into invisible dark-on-dark
              // text under the light theme.
              color: isActive
                  ? c.blueBg
                  : _hovered
                      ? c.bg3
                      : Colors.transparent,
              borderRadius: BorderRadius.circular(AppDimensions.radiusSm),
              // Stitch: hover glow effect
              boxShadow: _hovered && !isActive
                  ? [BoxShadow(color: c.blue.withValues(alpha: 0.08), blurRadius: 12)]
                  : [],
            ),
            child: Row(
              children: [
                // Stitch: 3px left border indicator for active state
                AnimatedContainer(
                  duration: const Duration(milliseconds: 300),
                  curve: Curves.easeOutCubic,
                  width: 3,
                  height: isActive ? 20 : 0,
                  margin: const EdgeInsets.only(right: 10),
                  decoration: BoxDecoration(
                  color: isActive ? c.blue : Colors.transparent,
                    borderRadius: BorderRadius.circular(2),
                    boxShadow: isActive
                        ? [BoxShadow(color: c.blue.withValues(alpha: 0.40), blurRadius: 6)]
                        : [],
                  ),
                ),
                // Icon
                AnimatedDefaultTextStyle(
                  duration: const Duration(milliseconds: 200),
                  style: TextStyle(color: isActive ? c.blue : _hovered ? c.t2 : c.t3),
                  child: Icon(
                    widget.icon, size: 18,
                    color: isActive ? c.blue : _hovered ? c.t2 : c.t3,
                  ),
                ),
                const SizedBox(width: 10),
                // Label
                Text(
                  widget.tab.label,
                  style: AppTextStyles.sidebarNav(
                    isActive ? c.t1 : _hovered ? c.t2 : c.t3,
                    active: isActive,
                  ),
                ),
                // Active glow dot
                if (isActive) ...[
                  const Spacer(),
                  Container(
                    width: 4, height: 4,
                    decoration: BoxDecoration(
                      color: c.blue,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(color: c.blue.withValues(alpha: 0.60), blurRadius: 4),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _KiteStatusWidget extends ConsumerStatefulWidget {
  @override
  ConsumerState<_KiteStatusWidget> createState() => _KiteStatusWidgetState();
}

class _KiteStatusWidgetState extends ConsumerState<_KiteStatusWidget> {
  /// The login poller, held so it can be stopped. As a bare local it outlived
  /// the sidebar that started it and kept calling the backend from a widget
  /// that no longer existed.
  Timer? _loginPoll;

  @override
  void dispose() {
    _loginPoll?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final kite = ref.watch(kiteStatusProvider);
    final kiteLoading = ref.watch(kiteLoadingProvider);

    return kite.when(
      data: (data) {
        final connected = data['connected'] == true;
        final configured = data['configured'] == true;

        if (data['connection_state'] == 'reconnecting') {
          return Padding(
            padding: const EdgeInsets.all(12),
            child: TextButton.icon(
              // Re-reading the status does not mend a session, and the
              // backend is already retrying on its own. Tapping asks it to
              // stop trying to restore a session that will not come back and
              // negotiate a clean one instead.
              onPressed: () async {
                try {
                  await ref.read(apiServiceProvider).reconnectKite();
                } catch (_) {
                  // The poll below reports the outcome either way.
                }
                ref.invalidate(kiteStatusProvider);
              },
              icon: Icon(Icons.sync, size: 16, color: c.gold),
              label: Text('Kite retrying', style: TextStyle(color: c.gold)),
            ),
          );
        }
        if (connected) {
          final userName = data['user_name'] ?? data['user_id'] ?? '';
          return _KiteBreathingGlow(
            color: c.up,
            child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              decoration: BoxDecoration(
                color: c.upBg,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: c.up.withValues(alpha: 0.2)),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  _PulsingDot(color: c.up),
                  const SizedBox(width: 6),
                  Text('Kite Live',
                    style: AppTextStyles.captionXs(c.up).copyWith(
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.5,
                    )),
                ]),
                if (userName.toString().isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(userName.toString(),
                    style: AppTextStyles.captionXs(c.t3),
                    overflow: TextOverflow.ellipsis),
                ],
              ]),
            ),
          );
        } else if (configured) {
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: MouseRegion(
              cursor: SystemMouseCursors.click,
              child: GestureDetector(
                onTap: kiteLoading ? null : _kiteLogin,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: c.blue.withValues(alpha: 0.3)),
                    // Stitch: solid color, no gradient
                    color: c.blue.withValues(alpha: 0.08),
                  ),
                  child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                    Icon(LucideIcons.power, size: 14, color: c.blue),
                    const SizedBox(width: 6),
                    Text(kiteLoading ? 'Connecting...' : 'Connect Zerodha',
                      style: AppTextStyles.captionXs(c.blue).copyWith(fontWeight: FontWeight.w700)),
                  ]),
                ),
              ),
            ),
          );
        } else {
          return Container(
            margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              color: c.bg3,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: c.bd),
            ),
            child: Row(children: [
              Container(width: 6, height: 6, decoration: BoxDecoration(shape: BoxShape.circle, color: c.t4)),
              const SizedBox(width: 6),
              Text('Kite Offline', style: AppTextStyles.captionXs(c.t4).copyWith(fontWeight: FontWeight.w600)),
            ]),
          );
        }
      },
      loading: () => const SizedBox.shrink(),
      error: (_, _) => const SizedBox.shrink(),
    );
  }

  void _kiteLogin() async {
    ref.read(kiteLoadingProvider.notifier).set(true);
    try {
      final api = ref.read(apiServiceProvider);
      final data = await api.getKiteLoginUrl();

      if (data['already_connected'] == true) {
        ref.invalidate(kiteStatusProvider);
        ref.invalidate(portfolioProvider);
        ref.read(kiteLoadingProvider.notifier).set(false);
        return;
      }

      final url = data['login_url'] as String?;
      if (url != null && url.isNotEmpty) {
        await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);

        // One poll at a time, and only one poller ever. Every tick costs an
        // MCP round trip AND a full holdings sync on the backend, so the old
        // fire-and-forget Timer.periodic did real damage: a tick that took
        // longer than two seconds overlapped the next one, a second press of
        // Connect started a second timer beside the first, and nothing
        // cancelled either when the sidebar went away. The logs show 120
        // checks from one login — enough to starve the backend, time out the
        // status poll, and paint the very "reconnecting" chip that sends
        // people to the logout button.
        _loginPoll?.cancel();
        _loginPoll = null;
        var attempts = 0;
        var busy = false;
        _loginPoll = Timer.periodic(const Duration(seconds: 2), (timer) async {
          if (busy) return;
          attempts++;
          if (attempts > 60) {
            timer.cancel();
            _loginPoll = null;
            ref.read(kiteLoadingProvider.notifier).set(false);
            return;
          }
          busy = true;
          try {
            // Cheap on the way in; the holdings are pulled once, on the
            // tick that actually finds a session.
            final check = await api.kiteCheck(syncHoldings: false);
            if (check['connected'] == true) {
              timer.cancel();
              _loginPoll = null;
              try {
                await api.kiteCheck();
              } catch (_) {
                // Connected either way; the sync can be retried from Sync.
              }
              ref.invalidate(kiteStatusProvider);
              refreshHoldings(ref);
              ref.read(kiteLoadingProvider.notifier).set(false);
            }
          } catch (_) {
            // A failed check is not a failed login; the next tick retries.
          } finally {
            busy = false;
          }
        });
      } else {
        ref.read(kiteLoadingProvider.notifier).set(false);
      }
    } catch (_) {
      ref.read(kiteLoadingProvider.notifier).set(false);
    }
  }
}

/// User profile section at sidebar bottom — Stitch tokens
class _UserProfileSection extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final isGuest = ref.watch(isGuestProvider);
    final profile = ref.watch(profileProvider);

    if (isGuest) {
      return Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          border: Border(top: BorderSide(color: c.bd)),
          color: c.bg0.withValues(alpha: 0.5),
        ),
        child: Column(children: [
          Row(children: [
            Container(width: 28, height: 28, decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: c.bgH,
              border: Border.all(color: c.bd),
            ), child: Icon(LucideIcons.user, size: 14, color: c.t3)),
            const SizedBox(width: 8),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Guest Mode', style: AppTextStyles.captionXs(c.t1).copyWith(fontWeight: FontWeight.w700)),
              Text('Offline · No sync', style: AppTextStyles.captionXs(c.t4).copyWith(fontSize: 9)),
            ])),
          ]),
          const SizedBox(height: 8),
          _StitchButton(
            icon: LucideIcons.user,
            label: 'Sign in with Google',
            color: c.blue,
            onTap: () async {
              try {
                final api = ref.read(apiServiceProvider);
                final data = await api.getGoogleAuthUrl();
                final url = data['url'] as String?;
                if (url != null && url.isNotEmpty) {
                  await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
                  int attempts = 0;
                  Timer.periodic(const Duration(seconds: 2), (timer) async {
                    attempts++;
                    if (attempts > 60) { timer.cancel(); return; }
                    try {
                      final profile = await api.getProfile();
                      if (profile['logged_in'] == true || profile['authenticated'] == true) {
                        timer.cancel();
                        ref.invalidate(profileProvider);
                        ref.read(isGuestProvider.notifier).set(false);
                      }
                    } catch (_) {}
                  });
                }
              } catch (_) {}
            },
          ),
        ]),
      );
    }

    return profile.when(
      data: (p) {
        final name = p['name'] ?? '';
        final email = p['email'] ?? '';
        if (name.isEmpty && email.isEmpty) return const SizedBox.shrink();
        return Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            border: Border(top: BorderSide(color: c.bd)),
            color: c.bg0.withValues(alpha: 0.5),
          ),
          child: Column(children: [
            Row(children: [
              Container(width: 28, height: 28, decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: const Color(0xFF8B5CF6).withValues(alpha: 0.15),
                border: Border.all(color: const Color(0xFF8B5CF6).withValues(alpha: 0.25)),
              ), child: Center(child: Text(
                name.isNotEmpty ? name[0].toUpperCase() : 'U',
                style: const TextStyle(color: Color(0xFF8B5CF6), fontSize: 11, fontWeight: FontWeight.w700),
              ))),
              const SizedBox(width: 8),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(name, style: AppTextStyles.captionXs(c.t1).copyWith(fontWeight: FontWeight.w700), overflow: TextOverflow.ellipsis),
                if (email.isNotEmpty) Text(email, style: AppTextStyles.captionXs(c.t4).copyWith(fontSize: 9), overflow: TextOverflow.ellipsis),
              ])),
            ]),
            const SizedBox(height: 8),
            Row(children: [
              // Labelled "Sync" next to a portfolio, so it has to sync the
              // portfolio. It used to only upload a Drive backup, which is why
              // holdings appeared frozen: the one obvious refresh button never
              // asked Kite for anything, and re-logging in was the only path
              // that pulled holdings at all.
              Expanded(child: _sidebarAction(c, LucideIcons.cloud, 'Sync', c.t3, c.blue, () async {
                try { await ref.read(apiServiceProvider).kiteSync(); } catch (_) {}
                try { await ref.read(apiServiceProvider).driveSync('upload'); } catch (_) {}
                refreshHoldings(ref);
              })),
              Expanded(child: _sidebarAction(c, LucideIcons.logOut, 'Logout', c.t3, c.dn, () async {
                final confirm = await showDialog<bool>(
                  context: context,
                  builder: (ctx) => AlertDialog(
                    backgroundColor: c.bg2,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: c.bd)),
                    title: Row(children: [
                      Icon(LucideIcons.logOut, size: 20, color: c.dn),
                      const SizedBox(width: 10),
                      Text('Confirm Logout', style: AppTextStyles.heading3(c.t1)),
                    ]),
                    content: Text('Are you sure you want to logout?\nYou will be taken back to the welcome screen.', style: AppTextStyles.body(c.t2)),
                    actions: [
                      TextButton(
                        onPressed: () => Navigator.pop(ctx, false),
                        child: Text('Cancel', style: AppTextStyles.caption(c.t3)),
                      ),
                      ElevatedButton(
                        onPressed: () => Navigator.pop(ctx, true),
                        style: ElevatedButton.styleFrom(backgroundColor: c.dn, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8))),
                        child: Text('Logout', style: AppTextStyles.caption(Colors.white)),
                      ),
                    ],
                  ),
                );
                if (confirm == true) {
                  try { await ref.read(apiServiceProvider).logout(); } catch (_) {}
                  ref.invalidate(profileProvider);
                  ref.read(appPhaseProvider.notifier).set(AppPhase.welcome);
                }
              })),
            ]),
          ]),
        );
      },
      loading: () => const SizedBox.shrink(),
      error: (_, _) => const SizedBox.shrink(),
    );
  }

  Widget _sidebarAction(AppColorScheme c, IconData icon, String label, Color defaultColor, Color hoverColor, VoidCallback onTap) {
    return Material(
      color: Colors.transparent, borderRadius: BorderRadius.circular(4),
      child: InkWell(
        borderRadius: BorderRadius.circular(4), onTap: onTap,
        hoverColor: c.bg3,
        child: Padding(padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(icon, size: 12, color: defaultColor), const SizedBox(width: 4),
            Text(label, style: AppTextStyles.captionXs(defaultColor).copyWith(fontSize: 10)),
          ]),
        ),
      ),
    );
  }
}

/// Stitch-style ghost button for sidebar
class _StitchButton extends StatefulWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;
  const _StitchButton({required this.icon, required this.label, required this.color, required this.onTap});
  @override
  State<_StitchButton> createState() => _StitchButtonState();
}

class _StitchButtonState extends State<_StitchButton> {
  bool _h = false;
  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _h = true),
      onExit: (_) => setState(() => _h = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(vertical: 6),
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: _h ? widget.color.withValues(alpha: 0.12) : widget.color.withValues(alpha: 0.06),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: widget.color.withValues(alpha: _h ? 0.30 : 0.15)),
            boxShadow: _h ? [BoxShadow(color: widget.color.withValues(alpha: 0.20), blurRadius: 12)] : [],
          ),
          child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(widget.icon, size: 12, color: widget.color),
            const SizedBox(width: 6),
            Text(widget.label, style: AppTextStyles.captionXs(widget.color).copyWith(fontWeight: FontWeight.w700)),
          ]),
        ),
      ),
    );
  }
}

/// Kite sync/disconnect buttons
class _KiteActionsSection extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final kite = ref.watch(kiteStatusProvider);
    final connected = kite.whenOrNull(data: (d) => d['connected'] == true) ?? false;
    if (!connected) return const SizedBox.shrink();

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: c.bd)),
        color: c.bg0.withValues(alpha: 0.5),
      ),
      child: Column(children: [
        // Stitch: solid blue button, no gradient
        _StitchButton(
          icon: LucideIcons.refreshCw,
          label: 'Sync Portfolio',
          color: c.blue,
          onTap: () async {
            try {
              await ref.read(apiServiceProvider).kiteSync();
              refreshHoldings(ref);
            } catch (_) {}
          },
        ),
        const SizedBox(height: 4),
        Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () async {
              final confirm = await showDialog<bool>(
                context: context,
                builder: (ctx) => AlertDialog(
                  backgroundColor: c.bg2,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: c.bd)),
                  title: Row(children: [
                    Icon(LucideIcons.zap, size: 20, color: c.gold),
                    const SizedBox(width: 10),
                    Text('Disconnect Kite', style: AppTextStyles.heading3(c.t1)),
                  ]),
                  content: Text('Are you sure you want to disconnect Zerodha Kite?\nLive market data will stop until you reconnect.', style: AppTextStyles.body(c.t2)),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(ctx, false),
                      child: Text('Cancel', style: AppTextStyles.caption(c.t3)),
                    ),
                    ElevatedButton(
                      onPressed: () => Navigator.pop(ctx, true),
                      style: ElevatedButton.styleFrom(backgroundColor: c.dn, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8))),
                      child: Text('Disconnect', style: AppTextStyles.caption(Colors.white)),
                    ),
                  ],
                ),
              );
              if (confirm == true) {
                try {
                  await ref.read(apiServiceProvider).kiteLogout();
                  ref.invalidate(kiteStatusProvider);
                } catch (_) {}
              }
            },
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Text('Disconnect Kite', style: AppTextStyles.captionXs(c.t4).copyWith(fontSize: 10)),
            ),
          ),
        ),
      ]),
    );
  }
}

/// Nifty Ticker — Stitch surface token
class _NiftyTicker extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final nifty = ref.watch(niftyProvider);

    return nifty.when(
      data: (data) {
        final price = (data['current'] ?? data['price'] ?? 0).toDouble();
        if (price == 0) return const SizedBox.shrink();
        final changePct = (data['change_pct'] ?? 0).toDouble();
        final isUp = changePct >= 0;

        return Container(
          margin: const EdgeInsets.symmetric(horizontal: 12),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: c.bg2, // Stitch: surface-container
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: c.bd),
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Container(
                width: 5, height: 5,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: isUp ? c.up : c.dn,
                  boxShadow: [BoxShadow(color: (isUp ? c.up : c.dn).withValues(alpha: 0.40), blurRadius: 4)],
                ),
              ),
              const SizedBox(width: 6),
              Text('NIFTY 50', style: AppTextStyles.captionXs(c.t4).copyWith(letterSpacing: 0.8, fontWeight: FontWeight.w700)),
            ]),
            const SizedBox(height: 6),
            Text(price.toStringAsFixed(1), style: AppTextStyles.monoBold(c.t1).copyWith(fontSize: 16)),
            const SizedBox(height: 3),
            Row(children: [
              Icon(isUp ? LucideIcons.arrowUpRight : LucideIcons.arrowDownRight, size: 12, color: isUp ? c.up : c.dn),
              const SizedBox(width: 2),
              Text('${isUp ? '+' : ''}${changePct.toStringAsFixed(2)}% today',
                style: AppTextStyles.captionXs(isUp ? c.up : c.dn).copyWith(fontWeight: FontWeight.w700, fontSize: 10)),
            ]),
          ]),
        );
      },
      loading: () => const SizedBox.shrink(),
      error: (_, _) => const SizedBox.shrink(),
    );
  }
}

// ══════════════════════════════════════════════════════════════
//  HEADER — Stitch Design System
//  Solid surface-container bg (#152031)
//  Search box with focus glow
//  Buttons with outline-variant borders + hover glow
// ══════════════════════════════════════════════════════════════

class _Header extends ConsumerWidget {
  final AppTab activeTab;
  const _Header({required this.activeTab});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final isDark = ref.watch(isDarkModeProvider);
    final advisor = ref.watch(advisorProvider);
    final lastUpdated = ref.watch(lastUpdatedProvider);
    final portfolio = ref.watch(livePortfolioProvider);
    final kiteConnected = portfolio.whenOrNull(data: (d) => d['kite_connected'] == true) ?? false;
    // Where the PRICES actually came from, which is not the same question as
    // whether a Kite session exists. This badge used to read "Live from
    // Zerodha" purely because kite_connected was true — while every price had
    // silently fallen back to Yahoo, because Kite's get_profile succeeds even
    // when get_ohlc and get_ltp do not. A badge that describes the connection
    // rather than the data tells the user their numbers are live when they are
    // not, which is worse than showing no badge at all.
    final priceSource =
        portfolio.whenOrNull(data: (d) => d['data_source']?.toString()) ?? '';
    final stalePriced = portfolio.whenOrNull(
          data: (d) => (d['stale_priced_count'] as num?)?.toInt() ?? 0,
        ) ??
        0;
    final hasSnapshot = stalePriced > 0;
    final kiteServing = priceSource == 'kite' && kiteConnected;
    late final String sourceLabel;
    late final Color sourceColor;
    if (kiteServing) {
      sourceLabel =
          hasSnapshot ? 'Zerodha live + snapshot' : 'Live from Zerodha';
      sourceColor = c.up;
    } else if (priceSource == 'kite') {
      sourceLabel = 'Last prices from Zerodha';
      sourceColor = c.gold;
    } else if (priceSource == 'mixed') {
      sourceLabel = kiteConnected
          ? 'Zerodha + Yahoo prices'
          : 'Yahoo + last Zerodha prices';
      sourceColor = c.gold;
    } else if (priceSource == 'yfinance') {
      sourceLabel = hasSnapshot
          ? 'Yahoo + Zerodha snapshot'
          : kiteConnected
              ? 'Zerodha connected · prices from Yahoo'
              : 'Data from Yahoo';
      sourceColor = c.blue;
    } else if (hasSnapshot) {
      sourceLabel = 'Using Zerodha snapshot';
      sourceColor = c.gold;
    } else {
      sourceLabel = kiteConnected
          ? 'Zerodha connected · prices unavailable'
          : 'Prices unavailable';
      sourceColor = c.t3;
    }

    portfolio.whenData((_) {
      final now = TimeOfDay.now();
      final h = now.hourOfPeriod == 0 ? 12 : now.hourOfPeriod;
      final m = now.minute.toString().padLeft(2, '0');
      final p = now.period == DayPeriod.am ? 'AM' : 'PM';
      final ts = '$h:$m $p';
      if (lastUpdated != ts) {
        Future.microtask(() => ref.read(lastUpdatedProvider.notifier).set(ts));
      }
    });

    return Container(
      height: AppDimensions.headerHeight,
      padding: const EdgeInsets.symmetric(horizontal: AppDimensions.headerPaddingH),
      decoration: BoxDecoration(
        // Stitch: solid surface-container, no gradient
        color: c.bg2,
        border: Border(bottom: BorderSide(color: c.bd, width: 1)),
      ),
      child: Row(
        children: [
          // Page title + data source
          Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Portfolio Overview', style: AppTextStyles.heading3(c.t1).copyWith(fontSize: 14)),
              Row(children: [
                Container(width: 5, height: 5, decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: sourceColor,
                  boxShadow: [BoxShadow(
                    color: sourceColor.withValues(alpha: 0.40),
                    blurRadius: 4,
                  )],
                )),
                const SizedBox(width: 5),
                Text(
                  sourceLabel,
                  style: AppTextStyles.captionXs(c.t3).copyWith(fontSize: 10),
                ),
                Text(' · ', style: AppTextStyles.captionXs(c.t4)),
                Text('Updated $lastUpdated', style: AppTextStyles.captionXs(c.t3).copyWith(fontSize: 10)),
              ]),
            ],
          ),
          const Spacer(),

          // Drive Sync Buttons
          _HeaderButton(
            icon: LucideIcons.uploadCloud, label: 'Backup',
            onTap: () => _handleBackup(context, ref, c),
          ),
          const SizedBox(width: 6),
          _HeaderButton(
            icon: LucideIcons.downloadCloud, label: 'Restore',
            onTap: () => _handleRestore(context, ref, c),
          ),
          const SizedBox(width: 6),

          // Search
          _HeaderButton(
            icon: LucideIcons.search, label: 'Search',
            onTap: () {
              final syms = portfolio.whenOrNull(data: (d) =>
                List<Map<String, dynamic>>.from(d['holdings'] ?? [])
                  .map((h) => h['symbol'].toString()).toList()) ?? [];
              StockPickerModal.show(context,
                portfolioSymbols: syms,
                onStockAdded: () => ref.invalidate(portfolioProvider));
            },
          ),
          const SizedBox(width: 6),

          // Export
          PopupMenuButton<String>(
            tooltip: 'Export / Import',
            offset: const Offset(0, 40),
            color: c.bg2,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: BorderSide(color: c.bd)),
            child: const IgnorePointer(child: _HeaderButton(icon: LucideIcons.download, label: 'Export')),
            onSelected: (val) => _handleExport(context, ref, val, c, portfolio),
            itemBuilder: (ctx) => [
              PopupMenuItem(value: 'Export Combined PDF', child: Text('📄 Export Combined Portfolio (PDF)', style: AppTextStyles.body(c.t1).copyWith(fontSize: 13))),
              PopupMenuItem(value: 'Export Combined CSV', child: Text('📊 Export Combined Portfolio (CSV)', style: AppTextStyles.body(c.t1).copyWith(fontSize: 13))),
              const PopupMenuDivider(),
              PopupMenuItem(value: 'Export Stocks PDF', child: Text('📄 Export Stocks (PDF)', style: AppTextStyles.body(c.t1).copyWith(fontSize: 13))),
              PopupMenuItem(value: 'Export Stocks CSV', child: Text('📊 Export Stocks (CSV)', style: AppTextStyles.body(c.t1).copyWith(fontSize: 13))),
              const PopupMenuDivider(),
              PopupMenuItem(value: 'Export MF PDF', child: Text('📄 Export Mutual Funds (PDF)', style: AppTextStyles.body(c.t1).copyWith(fontSize: 13))),
              PopupMenuItem(value: 'Export MF CSV', child: Text('📊 Export Mutual Funds (CSV)', style: AppTextStyles.body(c.t1).copyWith(fontSize: 13))),
              const PopupMenuDivider(),
              PopupMenuItem(value: 'Export Reports PDF', child: Text('📄 Export Wealth Report (PDF)', style: AppTextStyles.body(c.t1).copyWith(fontSize: 13))),
              const PopupMenuDivider(),
              PopupMenuItem(value: 'Import CSV', child: Text('📥 Import Portfolio (CSV)', style: AppTextStyles.body(c.blue).copyWith(fontSize: 13))),
            ],
          ),
          const SizedBox(width: 6),

          // AI Advisor — Stitch: solid button, no gradient
          _AIAdvisorButton(advisor: advisor, ref: ref),
          const SizedBox(width: 6),

          // Refresh
          _HeaderButton(
            icon: LucideIcons.refreshCw,
            onTap: () {
              ref.invalidate(portfolioProvider);
              ref.invalidate(mfPortfolioProvider);
            },
            isPrimary: true,
          ),

          // Divider
          Container(width: 1, height: 24, margin: const EdgeInsets.symmetric(horizontal: 8), color: c.bd),

          // Theme toggle
          _HeaderButton(
            icon: isDark ? LucideIcons.sun : LucideIcons.moon,
            onTap: () => ref.read(isDarkModeProvider.notifier).toggle(),
          ),
        ],
      ),
    );
  }

  // Backup handler
  void _handleBackup(BuildContext context, WidgetRef ref, AppColorScheme c) async {
    try {
      ScaffoldMessenger.of(context).clearSnackBars();
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Row(children: [
          SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)),
          const SizedBox(width: 12),
          const Text('Uploading to Google Drive...'),
        ]),
        backgroundColor: c.blue,
        duration: const Duration(seconds: 30),
      ));
      final result = await ref.read(apiServiceProvider).driveSync('upload');
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).clearSnackBars();
      final files = Map<String, dynamic>.from(result['files'] ?? {});
      final synced = files.entries.where((e) => e.value == true).map((e) => e.key).toList();
      final failed = files.entries.where((e) => e.value != true).map((e) => e.key).toList();
      final now = TimeOfDay.now();
      final timeStr = '${now.hourOfPeriod == 0 ? 12 : now.hourOfPeriod}:${now.minute.toString().padLeft(2, '0')} ${now.period == DayPeriod.am ? 'AM' : 'PM'}';
      showDialog(context: context, builder: (ctx) => AlertDialog(
        backgroundColor: c.bg2,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: c.bd)),
        title: Row(children: [
          Icon(LucideIcons.uploadCloud, color: c.up, size: 22),
          const SizedBox(width: 8),
          Text('Backup Complete', style: TextStyle(color: c.t1, fontSize: 16)),
        ]),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Synced at $timeStr', style: TextStyle(color: c.t3, fontSize: 12)),
          const SizedBox(height: 12),
          ...synced.map((f) => Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(children: [
              Icon(LucideIcons.checkCircle, color: c.up, size: 16),
              const SizedBox(width: 8),
              Text(f, style: TextStyle(color: c.t1, fontSize: 13)),
            ]),
          )),
          ...failed.map((f) => Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(children: [
              Icon(LucideIcons.xCircle, color: c.t3, size: 16),
              const SizedBox(width: 8),
              Text('$f (not found)', style: TextStyle(color: c.t3, fontSize: 13)),
            ]),
          )),
          const SizedBox(height: 8),
          Text('${synced.length} file${synced.length == 1 ? '' : 's'} backed up to Google Drive',
            style: TextStyle(color: c.up, fontSize: 12, fontWeight: FontWeight.w600)),
        ]),
        actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: Text('OK', style: TextStyle(color: c.blue)))],
      ));
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).clearSnackBars();
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Backup failed: $e'), backgroundColor: c.dn, duration: const Duration(seconds: 4)));
      }
    }
  }

  // Restore handler
  void _handleRestore(BuildContext context, WidgetRef ref, AppColorScheme c) async {
    try {
      ScaffoldMessenger.of(context).clearSnackBars();
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Row(children: [
          SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)),
          const SizedBox(width: 12),
          const Text('Restoring from Google Drive...'),
        ]),
        backgroundColor: c.blue,
        duration: const Duration(seconds: 30),
      ));
      final result = await ref.read(apiServiceProvider).driveSync('download');
      ref.invalidate(portfolioProvider);
      ref.invalidate(mfPortfolioProvider);
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).clearSnackBars();
      final files = Map<String, dynamic>.from(result['files'] ?? {});
      final synced = files.entries.where((e) => e.value == true).map((e) => e.key).toList();
      final failed = files.entries.where((e) => e.value != true).map((e) => e.key).toList();
      final now = TimeOfDay.now();
      final timeStr = '${now.hourOfPeriod == 0 ? 12 : now.hourOfPeriod}:${now.minute.toString().padLeft(2, '0')} ${now.period == DayPeriod.am ? 'AM' : 'PM'}';
      showDialog(context: context, builder: (ctx) => AlertDialog(
        backgroundColor: c.bg2,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: c.bd)),
        title: Row(children: [
          Icon(LucideIcons.downloadCloud, color: c.blue, size: 22),
          const SizedBox(width: 8),
          Text('Restore Complete', style: TextStyle(color: c.t1, fontSize: 16)),
        ]),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Restored at $timeStr', style: TextStyle(color: c.t3, fontSize: 12)),
          const SizedBox(height: 12),
          ...synced.map((f) => Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(children: [
              Icon(LucideIcons.checkCircle, color: c.up, size: 16),
              const SizedBox(width: 8),
              Text(f, style: TextStyle(color: c.t1, fontSize: 13)),
            ]),
          )),
          ...failed.map((f) => Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(children: [
              Icon(LucideIcons.xCircle, color: c.t3, size: 16),
              const SizedBox(width: 8),
              Text('$f (not on Drive)', style: TextStyle(color: c.t3, fontSize: 13)),
            ]),
          )),
          const SizedBox(height: 8),
          Text('${synced.length} file${synced.length == 1 ? '' : 's'} restored from Google Drive',
            style: TextStyle(color: c.blue, fontSize: 12, fontWeight: FontWeight.w600)),
        ]),
        actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: Text('OK', style: TextStyle(color: c.blue)))],
      ));
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).clearSnackBars();
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Restore failed: $e'), backgroundColor: c.dn, duration: const Duration(seconds: 4)));
      }
    }
  }

  // Export handler
  void _handleExport(BuildContext context, WidgetRef ref, String val, AppColorScheme c, AsyncValue<Map<String, dynamic>> portfolio) async {
    final holdings = portfolio.whenOrNull(data: (d) =>
      List<Map<String, dynamic>>.from(d['holdings'] ?? [])) ?? [];
    final mfData = ref.read(mfPortfolioProvider);
    final funds = mfData.whenOrNull(data: (d) =>
      List<Map<String, dynamic>>.from(d['funds'] ?? [])) ?? [];

    String? savedPath;
    try {
      switch (val) {
        case 'Export Stocks CSV': savedPath = await exportService.exportPortfolioToCsv(holdings); break;
        case 'Export Stocks PDF': savedPath = await exportService.exportStocksPdf(holdings); break;
        case 'Export MF CSV': savedPath = await exportService.exportMfPortfolioToCsv(funds); break;
        case 'Export MF PDF': savedPath = await exportService.exportMfPdf(funds); break;
        case 'Export Combined CSV': savedPath = await exportService.exportCombinedCsv(holdings, funds); break;
        case 'Export Combined PDF': savedPath = await exportService.exportCombinedPdf(holdings, funds); break;
        case 'Export Reports PDF':
          final report = await ref.read(apiServiceProvider).getWealthReport();
          savedPath = await exportService.exportWealthReportPdf(report);
          break;
        case 'Import CSV':
          final rows = await exportService.importCsv();
          if (rows != null && context.mounted) {
            ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text('Imported ${rows.length - 1} rows — processing...'),
              backgroundColor: c.blue,
            ));
          }
          return;
      }

      if (context.mounted) {
        if (savedPath != null) {
          final fileName = savedPath.split(RegExp(r'[/\\]')).last;
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text('✅ Saved: $fileName'),
            backgroundColor: c.up,
            duration: const Duration(seconds: 3),
          ));
        } else {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: const Text('Export cancelled'),
            backgroundColor: c.t3,
            duration: const Duration(seconds: 1),
          ));
        }
      }
    } catch (e, st) {
      debugPrint('❌ Export error: $e\n$st');
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Export failed: $e'),
          backgroundColor: c.dn,
        ));
      }
    }
  }
}

/// AI Advisor button — Stitch: solid blue, no gradient, with hover glow
class _AIAdvisorButton extends StatefulWidget {
  final AdvisorState advisor;
  final WidgetRef ref;
  const _AIAdvisorButton({required this.advisor, required this.ref});
  @override
  State<_AIAdvisorButton> createState() => _AIAdvisorButtonState();
}

class _AIAdvisorButtonState extends State<_AIAdvisorButton> {
  bool _h = false;
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final running = widget.advisor.running;
    return MouseRegion(
      cursor: running ? SystemMouseCursors.basic : SystemMouseCursors.click,
      onEnter: (_) => setState(() => _h = true),
      onExit: (_) => setState(() => _h = false),
      child: GestureDetector(
        onTap: running ? null : () async {
          try {
            await widget.ref.read(apiServiceProvider).startAdvisor();
            widget.ref.read(advisorProvider.notifier).setRunning(true);
          } catch (_) {}
        },
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(8),
            // Stitch: solid color, no gradient
            color: running ? c.bg3 : (_h ? c.blue : c.blue.withValues(alpha: 0.85)),
            border: running ? Border.all(color: c.blue.withValues(alpha: 0.3)) : null,
            boxShadow: _h && !running
                ? [BoxShadow(color: c.blue.withValues(alpha: 0.30), blurRadius: 12)]
                : [],
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            if (running) ...[
              SizedBox(width: 14, height: 14,
                child: CircularProgressIndicator(strokeWidth: 2, color: c.blue)),
              const SizedBox(width: 6),
              Text('AI Thinking...', style: AppTextStyles.captionXs(c.blue).copyWith(fontWeight: FontWeight.w700)),
            ] else ...[
              const Icon(LucideIcons.zap, size: 14, color: Colors.white),
              const SizedBox(width: 4),
              Text('Run AI Advisor', style: AppTextStyles.captionXs(Colors.white).copyWith(fontWeight: FontWeight.w700)),
            ],
          ]),
        ),
      ),
    );
  }
}

/// Header button — Stitch: outline-variant border + hover glow
class _HeaderButton extends StatefulWidget {
  final IconData icon;
  final String? label;
  final VoidCallback? onTap;
  final bool isPrimary;
  const _HeaderButton({required this.icon, this.label, this.onTap, this.isPrimary = false});

  @override
  State<_HeaderButton> createState() => _HeaderButtonState();
}

class _HeaderButtonState extends State<_HeaderButton> {
  bool _h = false;
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _h = true),
      onExit: (_) => setState(() => _h = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(8),
            color: widget.isPrimary
                ? (_h ? c.blue.withValues(alpha: 0.15) : c.blue.withValues(alpha: 0.08))
                : (_h ? c.bg3 : c.bg3.withValues(alpha: 0.5)),
            border: Border.all(
              color: widget.isPrimary
                  ? (_h ? c.blue.withValues(alpha: 0.40) : c.blue.withValues(alpha: 0.25))
                  : (_h ? c.bd2 : c.bd),
            ),
            // Stitch: hover glow
            boxShadow: _h
                ? [BoxShadow(
                    color: (widget.isPrimary ? c.blue : c.t3).withValues(alpha: 0.12),
                    blurRadius: 12)]
                : [],
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(widget.icon, size: 14, color: widget.isPrimary ? c.blue : (_h ? c.t2 : c.t3)),
            if (widget.label != null) ...[
              const SizedBox(width: 4),
              Text(widget.label!,
                style: AppTextStyles.captionXs(widget.isPrimary ? c.blue : (_h ? c.t2 : c.t3))
                  .copyWith(fontWeight: FontWeight.w600)),
            ],
          ]),
        ),
      ),
    );
  }
}

/// Breathing glow wrapper for Kite Live status
class _KiteBreathingGlow extends StatefulWidget {
  final Widget child;
  final Color color;
  const _KiteBreathingGlow({required this.child, required this.color});

  @override
  State<_KiteBreathingGlow> createState() => _KiteBreathingGlowState();
}

class _KiteBreathingGlowState extends State<_KiteBreathingGlow>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 2500))
      ..repeat(reverse: true);
    _anim = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(8),
          boxShadow: [
            BoxShadow(
              color: widget.color.withValues(alpha: 0.05 + _anim.value * 0.1),
              blurRadius: 8 + _anim.value * 8,
              spreadRadius: _anim.value * 1,
            ),
          ],
        ),
        child: widget.child,
      ),
    );
  }
}

/// Pulsing dot indicator for live status
class _PulsingDot extends StatefulWidget {
  final Color color;
  final double size;
  const _PulsingDot({required this.color}) : size = 6;

  @override
  State<_PulsingDot> createState() => _PulsingDotState();
}

class _PulsingDotState extends State<_PulsingDot>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1500))
      ..repeat(reverse: true);
    _anim = Tween<double>(begin: 0.6, end: 1.0).animate(
      CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => Container(
        width: widget.size,
        height: widget.size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: widget.color.withValues(alpha: _anim.value),
          boxShadow: [
            BoxShadow(
              color: widget.color.withValues(alpha: _anim.value * 0.4),
              blurRadius: 4 + _anim.value * 4,
            ),
          ],
        ),
      ),
    );
  }
}
