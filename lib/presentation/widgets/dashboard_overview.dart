import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import '../../core/extensions.dart';
import '../../core/constants.dart';
import '../../core/theme/app_text_styles.dart';
import '../../data/models/closed_positions.dart';
import '../../data/models/dashboard_snapshot.dart';
import '../../data/models/deploy_models.dart';
import '../../data/models/dip_models.dart';
import 'dense_ui.dart';

String _money(double? n, [String currency = 'INR']) => n == null || !n.isFinite
    ? 'Unavailable'
    : NumberFormat.currency(
        locale: currency == 'INR' ? 'en_IN' : 'en_US',
        symbol: currency == 'INR' ? '₹' : '$currency ',
        decimalDigits: 0,
      ).format(n);
String _pct(double? n) =>
    n == null || !n.isFinite ? 'Unavailable' : '${n.toStringAsFixed(2)}%';
String _stamp(String? value) {
  final date = DateTime.tryParse(value ?? '');
  return date == null
      ? 'Unknown'
      : '${DateFormat('dd MMM, HH:mm').format(date.toLocal())} local';
}

/// Layout-only view over typed, real-source data. Tests can exercise the whole
/// page at narrow widths without starting the backend or touching user records.
class DashboardOverview extends StatelessWidget {
  final DashboardSnapshot snapshot;
  final DashboardExpense expenses;
  final DateTime now;
  final bool guest, loading, failed, expenseLoading;
  final AsyncValue<MarketTape> tape;
  final AsyncValue<FundDipBoard?> fundDips;
  final AsyncValue<StockDipBoard?> stockDips;
  final AsyncValue<Map<String, dynamic>> kite;
  final Map<String, dynamic>? xirr;

  /// Realised P&L on sold shares. Null while it has not loaded; a book with
  /// no trades is a real answer ("nothing sold"), not a missing one.
  final ClosedBook? closed;
  final String? expenseUpdated;

  /// The v1.4.3 decision widgets, supplied by the screen because they read
  /// providers directly. Each one replaces this widget's own thinner reading
  /// of the same source, so the overview stays pumpable without a
  /// ProviderScope when they are absent.
  ///   [opportunities] — today's ranked answer, above everything else.
  ///   [marketTape]    — the index context that produced it.
  ///   [fundBoard]     — where to add, ranked by opportunity.
  ///   [stockBoard]    — where to buy, ranked by opportunity.
  ///   [conviction]    — why you own each one, and whether you may add more.
  final Widget? opportunities, marketTape, fundBoard, stockBoard, conviction;
  final void Function(AppTab) onNavigate;
  final VoidCallback onRefresh;
  const DashboardOverview({
    super.key,
    required this.snapshot,
    required this.expenses,
    required this.now,
    required this.tape,
    required this.fundDips,
    required this.stockDips,
    required this.kite,
    required this.onNavigate,
    required this.onRefresh,
    this.guest = false,
    this.loading = false,
    this.failed = false,
    this.expenseLoading = false,
    this.expenseUpdated,
    this.xirr,
    this.closed,
    this.opportunities,
    this.marketTape,
    this.fundBoard,
    this.stockBoard,
    this.conviction,
  });

  bool get _fresh =>
      dashboardFresh(snapshot.equity, now) &&
      dashboardFresh(snapshot.funds, now);
  void _go(AppTab tab) => onNavigate(tab);

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    // Decisions first, in v1.4.3's order — answer, context, where to add,
    // where to buy — then the standing position that the decisions act on.
    // Nothing that merely describes the portfolio sits above something to do.
    final items = <Widget>[
      _actions(context),
      ?opportunities,
      marketTape ?? _market(context),
      fundBoard ?? _funds(context),
      stockBoard ?? _stocks(context),
      // Directly under "where to buy": a dip is only worth acting on for a
      // holding you can say why you own.
      ?conviction,
      _summary(context),
      _allocation(context),
      _expenses(context),
      _health(context),
    ];
    return ListView.separated(
      key: const PageStorageKey('main-dashboard'),
      padding: const EdgeInsets.only(bottom: 88),
      itemCount: items.length,
      separatorBuilder: (_, _) => const SizedBox(height: 20),
      itemBuilder: (_, index) => DefaultTextStyle.merge(
        style: TextStyle(color: c.t1, fontSize: 14, height: 1.45),
        child: items[index],
      ),
    );
  }

  /// Section frame in the same idiom as the v1.4.3 opportunity sections above
  /// it: accent icon, short tracked title, one-line subtitle, and the content
  /// in its own card. The old frame wrapped every section in a second 20px
  /// bordered box, so these sections sat one indent deeper than the tape and
  /// opportunity cards and read as a different app.
  Widget _section(
    BuildContext context,
    String title,
    String sub,
    Widget child, {
    AppTab? route,
    IconData icon = LucideIcons.circleDot,
    Color? accent,
  }) {
    final c = context.colors;
    final tone = accent ?? c.blue;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(2, 0, 2, 10),
          child: Row(
            children: [
              Icon(icon, size: 15, color: tone),
              const SizedBox(width: 8),
              // One Expanded absorbs the slack so the trailing link keeps its
              // natural width and the title/subtitle ellipsize into what is
              // left. A Spacer here overflows a narrow card, because it claims
              // its share of the free space whether the texts used theirs or
              // not — the same trap documented on [denseTableHeader].
              Expanded(
                child: Row(
                  children: [
                    Flexible(
                      child: Text(
                        title,
                        style: AppTextStyles.bodyBold(
                          c.t1,
                        ).copyWith(fontSize: 13, letterSpacing: 0.5),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Flexible(
                      child: Text(
                        sub,
                        style: AppTextStyles.labelXs(c.t3),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ),
              if (route != null) ...[
                const SizedBox(width: 8),
                _link(context, 'View details', () => _go(route)),
              ],
            ],
          ),
        ),
        child,
      ],
    );
  }

  /// Compact text action, in place of Material's 48px-tall TextButton — the
  /// dense rows here are 34px, so a stock button set the row height.
  Widget _link(BuildContext context, String label, VoidCallback onTap) {
    final c = context.colors;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(4),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
        child: Row(
          children: [
            Text(
              label,
              style: AppTextStyles.bodyBold(c.blue).copyWith(fontSize: 11),
            ),
            const SizedBox(width: 2),
            Icon(LucideIcons.chevronRight, size: 12, color: c.blue),
          ],
        ),
      ),
    );
  }

  /// Status pill. [DSignalBadge] colours by trading verdict (BUY green, SELL
  /// red); these sections carry verdicts of their own — overweight, stale,
  /// over budget — where that mapping is wrong, so the tone is passed in.
  Widget _pill(BuildContext context, String text, Color tone) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
    decoration: BoxDecoration(
      color: tone.withValues(alpha: 0.10),
      border: Border.all(color: tone.withValues(alpha: 0.22)),
      borderRadius: BorderRadius.circular(4),
    ),
    child: Text(
      text,
      style: AppTextStyles.labelXs(tone),
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
    ),
  );

  /// KPI cells in the app's divider-separated grid, wrapped to the available
  /// width: two per row on a 375px window, four on a wide one.
  Widget _kpis(List<Kpi> cells, {String? note}) => LayoutBuilder(
    builder: (context, box) => KpiGrid(
      cells: cells,
      perRow: box.maxWidth < 430
          ? 2
          : box.maxWidth < 760
          ? 3
          : 4,
      note: note,
    ),
  );

  /// One-line caption for provenance — source, last-updated, coverage.
  Widget _foot(BuildContext context, List<String> lines) {
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.fromLTRB(2, 8, 2, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final line in lines)
            Padding(
              padding: const EdgeInsets.only(bottom: 2),
              child: Text(line, style: AppTextStyles.captionXs(c.t3)),
            ),
        ],
      ),
    );
  }

  Widget _grid(List<Widget> children, {double minWidth = 240}) => LayoutBuilder(
    builder: (context, box) {
      final count = (box.maxWidth / minWidth).floor().clamp(1, 4);
      final width = (box.maxWidth - (count - 1) * 12) / count;
      return Wrap(
        spacing: 12,
        runSpacing: 12,
        children: [
          for (final child in children) SizedBox(width: width, child: child),
        ],
      );
    },
  );

  Widget _notice(BuildContext context, String text, {bool risk = false}) {
    final c = context.colors;
    final tone = risk ? c.dn : c.t3;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 9),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: 0.07),
        border: Border.all(color: tone.withValues(alpha: 0.20)),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            risk ? LucideIcons.triangleAlert : LucideIcons.info,
            size: 12,
            color: tone,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              text,
              style: AppTextStyles.bodySmall(risk ? c.t1 : c.t2),
            ),
          ),
        ],
      ),
    );
  }

  Widget _skeleton(BuildContext context) => Semantics(
    label: 'Loading data',
    child: const DenseCard(
      child: SizedBox(height: 108, child: DensePulseLoader()),
    ),
  );

  Widget _actions(BuildContext context) {
    final alerts = <(String, String, AppTab)>[];
    if (guest) {
      alerts.add((
        'Sign in to review your finances',
        'Personal holdings stay hidden while signed out.',
        AppTab.settings,
      ));
    } else {
      if (!_fresh || failed) {
        alerts.add((
          'Review data freshness',
          'Some sources are stale, offline or have an unknown update time. Confidence: insufficient.',
          AppTab.settings,
        ));
      }
      if (snapshot.value != null && snapshot.value! > 0) {
        if ((snapshot.categoryValues['Unclassified'] ?? 0) > 0) {
          alerts.add((
            'Review asset classification',
            'Some holdings have no verified category. Allocation recommendations are incomplete.',
            AppTab.allocation,
          ));
        } else if (snapshot.validTargets) {
          final drifts =
              snapshot.targets.keys
                  .where((k) => (snapshot.drift(k) ?? 0).abs() >= 5)
                  .toList()
                ..sort(
                  (a, b) => snapshot
                      .drift(b)!
                      .abs()
                      .compareTo(snapshot.drift(a)!.abs()),
                );
          if (drifts.isNotEmpty) {
            final key = drifts.first, drift = snapshot.drift(drifts.first)!;
            alerts.add((
              '$key allocation needs review',
              '${drift.abs().toStringAsFixed(1)} percentage points ${drift > 0 ? 'above' : 'below'} target. Risk: allocation drift.',
              AppTab.allocation,
            ));
          }
        }
      }
      final expense = expenses.report;
      if (expense != null && expense.filled && expense.netSavings < 0) {
        alerts.add((
          'Monthly spending exceeds income',
          'Actual expenses exclude transfers. Risk: negative savings.',
          AppTab.expenses,
        ));
      }
      if (alerts.isEmpty && loading) {
        alerts.add((
          'Loading your overview',
          'Waiting for source records; no action can be assessed yet.',
          AppTab.dashboard,
        ));
      }
    }
    final state = alerts.isEmpty
        ? 'No Action'
        : alerts.any((a) => a.$1 == 'Monthly spending exceeds income')
        ? 'Action Needed'
        : 'Review';
    final c = context.colors;
    final tone = alerts.isEmpty
        ? c.up
        : state == 'Action Needed'
        ? c.dn
        : c.gold;
    final shown = alerts.take(3).toList();
    return _section(
      context,
      "TODAY’S ACTION BAR",
      'At most three priorities · review prompts, not trading instructions',
      DenseCard(
        clip: true,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // The verdict reads before any row does: one strip, tinted by the
            // worst thing found, so "nothing to do" is as legible as an alert.
            Container(
              width: double.infinity,
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
              color: tone.withValues(alpha: 0.06),
              child: Row(
                children: [
                  Icon(
                    alerts.isEmpty
                        ? LucideIcons.circleCheck
                        : LucideIcons.triangleAlert,
                    size: 14,
                    color: tone,
                  ),
                  const SizedBox(width: 8),
                  _pill(context, state, tone),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      alerts.isEmpty
                          ? 'No action required by the checks with available data.'
                          : '${shown.length} of ${alerts.length} shown',
                      style: AppTextStyles.captionXs(c.t3),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ),
            for (final alert in shown)
              Container(
                decoration: BoxDecoration(
                  border: Border(top: BorderSide(color: c.bd)),
                ),
                padding: const EdgeInsets.fromLTRB(14, 9, 10, 10),
                child: Row(
                  children: [
                    Container(
                      width: 3,
                      height: 30,
                      decoration: BoxDecoration(
                        color: tone,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            alert.$1,
                            style: AppTextStyles.bodyBold(
                              c.t1,
                            ).copyWith(fontSize: 12),
                          ),
                          const SizedBox(height: 2),
                          Text(alert.$2, style: AppTextStyles.captionXs(c.t3)),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    _link(context, 'Review', () => _go(alert.$3)),
                  ],
                ),
              ),
          ],
        ),
      ),
      icon: LucideIcons.listChecks,
      accent: tone,
    );
  }

  Widget _summary(BuildContext context) {
    final m = snapshot;
    final combined = xirr?['combined'] is Map ? xirr!['combined'] as Map : {};
    final rate = dashboardNumber(combined['xirr']);
    final coverage = dashboardNumber(combined['covered_pct']);
    final c = context.colors;
    Color tone(double? v) => v == null
        ? c.t3
        : v > 0
        ? c.up
        : v < 0
        ? c.dn
        : c.t1;
    return _section(
      context,
      'PORTFOLIO SUMMARY',
      'INR investments + recorded other assets',
      guest
          ? const DenseEmptyCard(
              icon: LucideIcons.logIn,
              title: 'Sign in to view your portfolio',
              sub: 'Holdings, cost basis and returns are tied to your account.',
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (loading && m.equity == null && m.funds == null)
                  _skeleton(context)
                else ...[
                  // Definitions used to hide in a tap-tooltip on each tile.
                  // They live in the kit's explainer now: the thresholds are
                  // one tap away for everyone instead of being discoverable
                  // only by prodding a number.
                  DenseCard(
                    child: SectionExplainer(
                      question: 'What am I worth, and what earned it?',
                      reading:
                          'Values are current; cost basis is what your ledger recorded.',
                      accent: c.blue,
                      borderTop: false,
                      rules: const [
                        'Unrealized gain/loss = current investment value − recorded invested amount. Not realized profit.',
                        'Absolute return is not annualized; XIRR is, and covers only dated cashflows.',
                        'XIRR never averages individual XIRRs — a partial coverage figure is stated, not hidden.',
                        'Other assets carry no cost basis, so they lift value but not invested.',
                        'Realized profit needs reconciled sale costs, fees and corporate actions; it is never inferred from holding gains.',
                        'Unavailable means a source did not return a number. It is never treated as zero.',
                      ],
                      action:
                          'Read value with the update times below it — a stale price makes every derived number stale.',
                    ),
                  ),
                  const SizedBox(height: 10),
                  _kpis(
                    [
                      Kpi(
                        'TOTAL VALUE',
                        _money(m.value),
                        'equity + funds + other',
                        m.value == null ? c.t3 : c.t1,
                      ),
                      Kpi(
                        'INVESTED',
                        _money(m.invested),
                        'recorded cost basis',
                        m.invested == null ? c.t3 : c.t1,
                      ),
                      Kpi(
                        'UNREALIZED P&L',
                        _money(m.pnl),
                        'not realized profit',
                        tone(m.pnl),
                      ),
                      Kpi(
                        'ABSOLUTE RETURN',
                        _pct(m.absoluteReturn),
                        'not annualized',
                        tone(m.absoluteReturn),
                      ),
                      Kpi(
                        'XIRR',
                        rate == null || coverage == null || coverage <= 0
                            ? 'Unavailable'
                            : _pct(rate),
                        coverage == null || coverage <= 0
                            ? 'no dated cashflows'
                            : 'covers ${_pct(coverage)} of book',
                        tone(rate),
                      ),
                      Kpi(
                        '1-DAY · EQUITY',
                        _money(m.equityDayChange),
                        'funds unavailable daily',
                        tone(m.equityDayChange),
                      ),
                      Kpi(
                        'EQUITY VALUE',
                        _money(m.equityValue),
                        'sum of holdings',
                        m.equityValue == null ? c.t3 : c.t1,
                      ),
                      Kpi(
                        'FUND VALUE',
                        _money(m.fundValue),
                        'units × latest NAV',
                        m.fundValue == null ? c.t3 : c.t1,
                      ),
                      Kpi(
                        'CASH',
                        _money(m.other['Cash']),
                        'manually recorded',
                        m.other['Cash'] == null ? c.t3 : c.t1,
                      ),
                      Kpi(
                        'BOUGHT THIS MONTH',
                        _money(m.monthInvested),
                        'gross dated purchases',
                        m.monthInvested == null ? c.t3 : c.t1,
                      ),
                      // Filled from the FIFO-matched closed book. It read
                      // 'Unavailable' for as long as nothing computed it;
                      // it still says so when no sale has been recorded,
                      // because zero sales is not zero profit.
                      Kpi(
                        'REALIZED PROFIT',
                        closed == null || closed!.trades == 0
                            ? 'Unavailable'
                            : _money(closed!.realized),
                        closed == null || closed!.trades == 0
                            ? 'no recorded sales'
                            : closed!.isMeasured
                            // Straight from the imported Kite P&L statement,
                            // so this tile is measured, not reconstructed.
                            ? 'Kite statement · ${closed!.trades} sales'
                            : '${closed!.trades} sales, ledger FIFO',
                        closed == null || closed!.trades == 0
                            ? c.t3
                            : tone(closed!.realized),
                      ),
                    ],
                    note:
                        'Update times are retrieval times; market prices and NAVs may be delayed.',
                  ),
                ],
                const SizedBox(height: 8),
                if (m.value == null && !loading)
                  _notice(
                    context,
                    'Valuation incomplete. Missing prices are not treated as zero.',
                  ),
                _foot(context, [
                  'Equities: ${m.equity?['data_source'] ?? 'Unavailable'} · Last updated: ${_stamp(m.equity?['last_updated']?.toString())}',
                  'Funds: ${m.funds?['data_source'] ?? 'Unavailable'} · Last updated: ${_stamp(m.funds?['last_updated']?.toString())}',
                ]),
              ],
            ),
      icon: LucideIcons.wallet,
      accent: c.blue,
    );
  }

  Widget _market(BuildContext context) {
    final data = tape.value;
    final quotes =
        data?.indices
            .where(
              (q) => q.group == IndexGroup.broad || q.group == IndexGroup.size,
            )
            .take(6)
            .toList() ??
        <IndexQuote>[];
    return _section(
      context,
      'MARKET PULSE',
      'Daily history from the existing index feed · Market as of: ${_stamp(data?.asOf)}',
      tape.isLoading
          ? _skeleton(context)
          : quotes.isEmpty
          ? _notice(
              context,
              'Market data unavailable. Refresh when the connection recovers.',
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (data?.stale == true)
                  _notice(
                    context,
                    'Stale market snapshot — use for context only.',
                  ),
                _grid([
                  for (final q in quotes)
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: context.colors.bg1,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            q.label,
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                          Text(
                    q.ok && q.last != null
                                ? NumberFormat(
                                    '#,##0.00',
                                    'en_IN',
                                  ).format(q.last ?? 0)
                                : 'Unavailable',
                            style: const TextStyle(
                              fontSize: 23,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          Text('Day: ${_pct(q.dayChgPct)}'),
                          Text('Below 52w high: ${_pct(q.offHighPct)}'),
                          Text('Above 52w low: ${_pct(q.aboveLowPct)}'),
                          Text(
                            q.offHighPct == null
                                ? 'Range unavailable'
                                : q.offHighPct! >= 20
                                ? 'High-risk fall'
                                : q.offHighPct! >= 10
                                ? 'Meaningful correction'
                                : q.offHighPct! >= 5
                                ? 'Mild dip'
                                : q.offHighPct! <= 2
                                ? 'Near high'
                                : 'Normal range',
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                          Text(
                            'Trend: ${q.aboveDma(200) == null
                                ? 'Unavailable'
                                : q.aboveDma(200)!
                                ? 'Above 200-day average'
                                : 'Below 200-day average'}',
                          ),
                          const Text('Recent-peak drawdown: unavailable'),
                        ],
                      ),
                    ),
                ]),
              ],
            ),
    );
  }

  Widget _holdingCard(
    BuildContext context,
    String title,
    List<String> lines,
    String action,
    String reason,
    AppTab tab,
  ) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: context.colors.bg1,
      borderRadius: BorderRadius.circular(8),
      border: Border.all(color: context.colors.bd),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
        ),
        const SizedBox(height: 8),
        for (final line in lines)
          Padding(padding: const EdgeInsets.only(bottom: 4), child: Text(line)),
        const Divider(),
        Text(action, style: const TextStyle(fontWeight: FontWeight.w700)),
        Text(reason),
        TextButton(
          onPressed: () => _go(tab),
          child: const Text('View details'),
        ),
      ],
    ),
  );

  Widget _funds(BuildContext context) {
    final m = snapshot;
    final dips = fundDips.value;
    final list = [...m.fundRows]
      ..sort(
        (a, b) => (dashboardNumber(b['current_value']) ?? -1).compareTo(
          dashboardNumber(a['current_value']) ?? -1,
        ),
      );
    return _section(
      context,
      'MUTUAL FUND OPPORTUNITIES',
      'Three largest existing funds · benchmark dips are review thresholds, not buy signals.',
      loading && m.funds == null
          ? _skeleton(context)
          : list.isEmpty
          ? _notice(
              context,
              guest
                  ? 'Sign in to view your funds.'
                  : 'No fund records available. Open Mutual Funds to add or sync holdings.',
            )
          : _grid([
              for (final f in list.take(3))
                Builder(
                  builder: (context) {
                    final name = '${f['scheme_name'] ?? 'Fund'}';
                    FundDip? dip;
                    for (final d in dips?.funds ?? <FundDip>[]) {
                      if (d.schemeName == name) dip = d;
                    }
                    final category = dashboardCategory(
                      '${f['category'] ?? ''}',
                    );
                    final drift = m.drift(category);
                    final complete =
                        _fresh &&
                        dashboardFresh({'last_updated': dips?.asOf}, now) &&
                        dip != null &&
                        !dip.lowConfidence &&
                        dip.benchmarkDrawdownPct != null &&
                        m.validTargets &&
                        category != 'Unclassified' &&
                        m.other.containsKey('Cash');
                    final action = !complete
                        ? 'Insufficient data'
                        : drift != null && drift >= 5
                        ? 'Avoid adding — allocation already high'
                        : 'Review opportunity';
                    final val = dashboardNumber(f['current_value']),
                        inv = dashboardNumber(f['invested']);
                    return _holdingCard(
                      context,
                      name,
                      [
                        'Category: ${f['category'] ?? 'Unclassified'}',
                        'Value: ${_money(val)} · Invested: ${_money(inv)}',
                        'Gain/loss: ${_money(val == null || inv == null ? null : val - inv)}',
                        'XIRR: ${_pct(dashboardNumber(f['xirr']))}',
                        'Portfolio weight: ${_pct(m.weight(val))}',
                        'Category target: ${_pct(m.targets[category])}',
                        'Benchmark: ${dip?.benchmarkLabel ?? 'Unavailable'}',
                        'Benchmark drawdown: ${_pct(dip?.benchmarkDrawdownPct)}',
                        'SIP: ${f['sip_status'] ?? 'Not recorded'}',
                        'NAV date: ${f['nav_date'] ?? 'Unavailable'} · ${f['nav_source'] ?? 'Saved holdings'}',
                        'Risk: ${dip?.deepFallRisk == true ? 'Deep fall — review carefully' : 'Review category and exposure'}',
                      ],
                      action,
                      !complete
                          ? 'Fresh data, verified allocation, cash and SIP/risk checks are required before considering additions.'
                          : 'Review benchmark trend, recent contributions and long-term performance before changing your plan.',
                      AppTab.mutualFunds,
                    );
                  },
                ),
            ], minWidth: 300),
      route: AppTab.mutualFunds,
    );
  }

  Widget _stocks(BuildContext context) {
    final m = snapshot;
    final list = [...m.holdings]
      ..sort(
        (a, b) => (dashboardNumber(b['total_value']) ?? -1).compareTo(
          dashboardNumber(a['total_value']) ?? -1,
        ),
      );
    return _section(
      context,
      'EQUITY OPPORTUNITIES',
      'Three largest positions · separate price falls from business deterioration.',
      loading && m.equity == null
          ? _skeleton(context)
          : list.isEmpty
          ? _notice(
              context,
              guest
                  ? 'Sign in to view your equities.'
                  : 'No equity records available. Open Equities to add or sync holdings.',
            )
          : _grid([
              for (final h in list.take(3))
                Builder(
                  builder: (context) {
                    StockDip? dip;
                    for (final d in stockDips.value?.stocks ?? <StockDip>[]) {
                      if (d.symbol == h['symbol']) dip = d;
                    }
                    final confidence = dip?.confidence;
                    final complete =
                        _fresh &&
                        dashboardFresh({'last_updated': stockDips.value?.asOf}, now) &&
                        dip != null &&
                        confidence != null &&
                        confidence >= 80 &&
                        dip.factors['fundamental'] != null;
                    final blocked =
                        dip?.averagingBlocked == true ||
                        dip?.corporateActionSuspected == true;
                    return _holdingCard(
                      context,
                      '${h['name'] ?? h['symbol']} · ${h['symbol']}',
                      [
                        'Price: ${_money(dashboardNumber(h['current_price']))} · Day: ${_pct(dashboardNumber(h['day_chg']))}',
                        'Your average: ${_money(dashboardNumber(h['avg_cost']))}',
                        'Return: ${_pct(dashboardNumber(h['net_chg']))} · Weight: ${_pct(m.weight(dashboardNumber(h['total_value'])))}',
                        'Below 52w high: ${_pct(dip?.drawdownPct)} · Above 52w low: unavailable',
                        'Opportunity score: ${complete ? '${dip.score?.toStringAsFixed(0) ?? 'Unavailable'}/100' : 'Insufficient data'}',
                        'Data coverage: ${_pct(confidence)} · not a success probability',
                        'Fall context: ${dip?.reasonForFall.label ?? 'Unavailable'}',
                        'News: ${dip?.newsLabel ?? 'Not checked'}',
                        'Risk: ${dip?.mainRisk ?? 'Liquidity, volatility and current news require review'}',
                      ],
                      !complete
                          ? 'Insufficient data'
                          : blocked
                          ? 'Avoid adding'
                          : 'Review opportunity',
                      !complete
                          ? 'Fresh price and sufficient fundamental evidence are required. A falling price alone is not a signal.'
                          : (dip.reasons.take(2).join(' · ')),
                      AppTab.equities,
                    );
                  },
                ),
            ], minWidth: 300),
      route: AppTab.equities,
    );
  }

  Widget _allocation(BuildContext context) {
    final m = snapshot, values = snapshot.categoryValues;
    final keys = {...m.targets.keys, ...values.keys, 'Cash'};
    final c = context.colors;
    // Ranked worst-first: the row that needs rebalancing should not be found
    // by reading an alphabetical list to the end.
    final ranked = keys.toList()
      ..sort(
        (a, b) => (m.drift(b)?.abs() ?? -1).compareTo(m.drift(a)?.abs() ?? -1),
      );
    final cols = const [
      DenseCol('CATEGORY', 5, numeric: false),
      DenseCol('CURRENT', 3),
      DenseCol('TARGET', 2),
      DenseCol('DRIFT', 2),
      DenseCol('STATUS', 4, numeric: false),
    ];
    final drifted = ranked
        .where((k) => (m.drift(k)?.abs() ?? 0) >= 5)
        .length;
    return _section(
      context,
      'ALLOCATION HEALTH',
      'Exposure versus saved targets',
      m.value == null || m.value! <= 0
          ? const DenseEmptyCard(
              icon: LucideIcons.chartPie,
              title: 'Allocation needs a complete valuation',
              sub: 'A non-empty portfolio value is required before exposure '
                  'can be compared with targets.',
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (!m.validTargets)
                  _notice(
                    context,
                    'Targets must total 100% before rebalancing can be assessed.',
                  ),
                if ((values['Unclassified'] ?? 0) > 0)
                  _notice(
                    context,
                    'Unclassified holdings prevent a complete market-cap comparison. No category is guessed.',
                  ),
                DenseTable(
                  icon: LucideIcons.chartPie,
                  accent: c.accent,
                  title: 'BY CATEGORY',
                  subtitle: drifted > 0
                      ? '$drifted of ${ranked.length} outside the ±5pp band'
                      : 'all categories within the ±5pp band',
                  trailing: _link(
                    context,
                    'Rebalance',
                    () => _go(AppTab.allocation),
                  ),
                  cols: cols,
                  rows: [
                    for (final key in ranked)
                      _allocationRow(context, key, values[key] ?? 0),
                  ],
                ),
              ],
            ),
      route: AppTab.allocation,
      icon: LucideIcons.chartPie,
      accent: c.accent,
    );
  }

  List<Widget> _allocationRow(BuildContext context, String key, double value) {
    final c = context.colors;
    final m = snapshot;
    final weight = m.weight(value) ?? 0;
    final drift = m.drift(key);
    final tone = drift == null
        ? c.t3
        : drift.abs() < 5
        ? c.up
        : drift > 0
        ? c.dn
        : c.gold;
    return [
      DInstrument(
        symbol: key,
        sub: _money(value),
        up: true,
        spine: tone,
        ellipsis: true,
      ),
      DWeightCell(pct: weight, color: tone),
      denseNum(context, _pct(m.targets[key]), c.t2),
      drift == null
          ? denseNum(context, '—', c.t3)
          : denseSignedNum(context, drift, tone, decimals: 1, suffix: ' pp'),
      Align(
        alignment: Alignment.centerLeft,
        child: _pill(
          context,
          drift == null
              ? 'No target'
              : drift.abs() < 5
              ? 'In band'
              : drift > 0
              ? 'Overweight'
              : 'Underweight',
          tone,
        ),
      ),
    ];
  }

  Widget _expenses(BuildContext context) {
    final r = expenses.report;
    final c = context.colors;
    final cur = expenses.currency;
    Color tone(double? v) => v == null
        ? c.t3
        : v > 0
        ? c.up
        : v < 0
        ? c.dn
        : c.t1;
    return _section(
      context,
      'EXPENSE & SAVINGS SNAPSHOT',
      '${DateFormat('MMMM yyyy').format(now)} · $cur',
      expenseLoading
          ? _skeleton(context)
          : r == null || !r.filled
          ? const DenseEmptyCard(
              icon: LucideIcons.receipt,
              title: 'No recorded cashflows this month',
              sub: 'Import or enter expenses to see savings. A blank month is '
                  'not zero spending.',
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _kpis(
                  [
                    Kpi(
                      'INCOME',
                      _money(r.totalIncome, cur),
                      'transfers excluded',
                      c.t1,
                    ),
                    Kpi(
                      'ACTUAL SPEND',
                      _money(r.actualExpense, cur),
                      'spending categories only',
                      c.t1,
                    ),
                    Kpi(
                      'SAVINGS',
                      _money(r.netSavings, cur),
                      'income − actual spend',
                      tone(r.netSavings),
                    ),
                    Kpi(
                      'SAVINGS RATE',
                      r.totalIncome > 0 ? _pct(r.savingsRate) : 'Unavailable',
                      r.totalIncome > 0
                          ? 'of positive income'
                          : 'no recorded income',
                      r.totalIncome > 0 ? tone(r.savingsRate) : c.t3,
                    ),
                    Kpi(
                      'TRANSFERS OUT',
                      _money(r.transfer, cur),
                      'moved, not consumed',
                      c.t2,
                    ),
                    Kpi(
                      'TRANSFERS IN',
                      _money(expenses.incomingTransfers, cur),
                      'own-account inflow',
                      c.t2,
                    ),
                    Kpi(
                      'OPENING',
                      _money(r.openingBalance, cur),
                      'carried in ledger',
                      c.t2,
                    ),
                    Kpi(
                      'CLOSING',
                      _money(r.closingBalance, cur),
                      'ledger, not a bank balance',
                      c.t1,
                    ),
                    Kpi(
                      'BUDGET VARIANCE',
                      expenses.budget == null
                          ? 'Not configured'
                          : _money(r.actualExpense - expenses.budget!, cur),
                      expenses.budget == null
                          ? 'set one in Expenses'
                          : 'positive = over budget',
                      expenses.budget == null
                          ? c.t3
                          : tone(expenses.budget! - r.actualExpense),
                    ),
                    Kpi(
                      'LAST MONTH SAVED',
                      expenses.previous?.filled == true
                          ? _money(expenses.previous!.netSavings, cur)
                          : 'Unavailable',
                      'prior calendar month',
                      expenses.previous?.filled == true
                          ? tone(expenses.previous!.netSavings)
                          : c.t3,
                    ),
                  ],
                  note:
                      'Saved expense ledger, kept separate from INR investments.',
                ),
                // Ten numbers say what happened; one bar says where the month
                // actually went. Savings is what is left after spend and
                // transfers, so it is drawn as the remainder, not as a claim.
                if (r.totalIncome > 0) ...[
                  const SizedBox(height: 10),
                  DenseCard(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(14, 11, 14, 12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Text(
                                'WHERE THE MONTH WENT',
                                style: AppTextStyles.labelXs(c.t3),
                              ),
                              const Spacer(),
                              Text(
                                '${_money(r.totalIncome, cur)} in',
                                style: AppTextStyles.monoXs(c.t2),
                              ),
                            ],
                          ),
                          const SizedBox(height: 9),
                          DStackedBar(
                            segments: [
                              (r.actualExpense, c.dn),
                              (r.transfer, c.gold),
                              (r.netSavings > 0 ? r.netSavings : 0.0, c.up),
                            ],
                            total: r.totalIncome,
                            height: 8,
                          ),
                          const SizedBox(height: 9),
                          Wrap(
                            spacing: 14,
                            runSpacing: 6,
                            children: [
                              _legend(
                                context,
                                c.dn,
                                'Spend',
                                _money(r.actualExpense, cur),
                              ),
                              _legend(
                                context,
                                c.gold,
                                'Transfers out',
                                _money(r.transfer, cur),
                              ),
                              _legend(
                                context,
                                c.up,
                                'Saved',
                                _money(r.netSavings, cur),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
                if (expenses.topCategories.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  DenseTable(
                    icon: LucideIcons.tags,
                    accent: c.gold,
                    title: 'TOP SPENDING',
                    subtitle: 'share of actual spend',
                    trailing: _link(
                      context,
                      'Open ledger',
                      () => _go(AppTab.expenses),
                    ),
                    cols: const [
                      DenseCol('CATEGORY', 5, numeric: false),
                      DenseCol('AMOUNT', 3),
                      DenseCol('SHARE', 3),
                    ],
                    rows: [
                      for (final v in expenses.topCategories)
                        [
                          DInstrument(
                            symbol: v.label,
                            sub: '',
                            up: true,
                            spine: c.gold,
                            ellipsis: true,
                          ),
                          denseNum(context, _money(v.amount, cur), c.t1),
                          DWeightCell(
                            pct: r.actualExpense > 0
                                ? (v.amount / r.actualExpense * 100).clamp(
                                    0.0,
                                    100.0,
                                  )
                                : 0,
                            color: c.gold,
                          ),
                        ],
                    ],
                  ),
                ],
                const SizedBox(height: 8),
                if (r.netSavings < 0)
                  _notice(
                    context,
                    'Actual spending exceeds income this month.',
                    risk: true,
                  ),
                if (expenses.previous?.filled == true &&
                    r.totalIncome > 0 &&
                    expenses.previous!.totalIncome > 0 &&
                    r.savingsRate < expenses.previous!.savingsRate)
                  _notice(
                    context,
                    'Savings rate decreased compared with last month.',
                  ),
                _foot(context, [
                  'Source: saved expense ledger · Last saved: ${_stamp(expenseUpdated)}',
                ]),
              ],
            ),
      route: AppTab.expenses,
      icon: LucideIcons.receipt,
      accent: context.colors.gold,
    );
  }

  /// Dot + label + value, for a stacked bar's segments.
  Widget _legend(BuildContext context, Color tone, String label, String value) {
    final c = context.colors;
    return Row(
      children: [
        Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(
            color: tone,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        const SizedBox(width: 6),
        Text(label, style: AppTextStyles.captionXs(c.t3)),
        const SizedBox(width: 5),
        Text(value, style: AppTextStyles.monoXs(c.t2)),
      ],
    );
  }

  Widget _health(BuildContext context) {
    final state = kite.value;
    final status = kite.hasError
        ? 'Error — retry available'
        : kite.isLoading && state == null
        ? 'Connecting'
        : state?['connection_state']?.toString().replaceAll('_', ' ') ??
              (state?['connected'] == true
                  ? 'Connected'
                  : state?['mcp_available'] == true
                  ? 'Authentication required'
                  : 'Disconnected');
    final c = context.colors;
    final connected =
        !kite.hasError &&
        (state?['connected'] == true ||
            state?['connection_state'] == 'connected');
    final equityOk = dashboardFresh(snapshot.equity, now);
    final fundOk = dashboardFresh(snapshot.funds, now);
    final ledgerOk = expenses.report?.filled == true;
    return _section(
      context,
      'CONNECTION & DATA HEALTH',
      'Connection health is separate from price freshness',
      DenseCard(
        clip: true,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // A dot per source: the question here is "can I trust the numbers
            // above", and that is answered by scanning a column of states, not
            // by reading five sentences.
            _healthRow(context, 'Kite: $status', connected
                ? c.up
                : kite.hasError
                ? c.dn
                : c.gold),
            _healthRow(
              context,
              'Equities: ${equityOk ? 'Recently retrieved' : 'Stale / unavailable'}',
              equityOk ? c.up : c.dn,
              top: true,
            ),
            _healthRow(
              context,
              'Mutual funds: ${fundOk ? 'Recently retrieved NAV snapshot' : 'Stale / unavailable'}',
              fundOk ? c.up : c.dn,
              top: true,
            ),
            _healthRow(
              context,
              'Expenses: ${ledgerOk ? 'Saved ledger available' : 'No current-month records'}',
              ledgerOk ? c.up : c.t3,
              top: true,
            ),
            Container(
              width: double.infinity,
              decoration: BoxDecoration(
                color: c.bg3,
                border: Border(top: BorderSide(color: c.bd)),
              ),
              padding: const EdgeInsets.fromLTRB(14, 9, 10, 9),
              // The caption and two controls do not share a line at 375px, so
              // the footer stacks instead of overflowing. Both controls stay
              // in a Wrap either way: 'Refresh dashboard' grows with the text
              // scale and must be free to drop to its own line.
              child: LayoutBuilder(
                builder: (context, box) {
                  final caption = Text(
                    'Last successful Kite check: ${_stamp(state?['last_success_at']?.toString())}',
                    style: AppTextStyles.captionXs(c.t3),
                  );
                  final controls = Wrap(
                    spacing: 4,
                    runSpacing: 6,
                    alignment: WrapAlignment.end,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      _link(
                        context,
                        'Connection settings',
                        () => _go(AppTab.settings),
                      ),
                      _refreshButton(context),
                    ],
                  );
                  if (box.maxWidth < 520) {
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [caption, const SizedBox(height: 8), controls],
                    );
                  }
                  return Row(
                    children: [
                      Expanded(child: caption),
                      const SizedBox(width: 8),
                      controls,
                    ],
                  );
                },
              ),
            ),
          ],
        ),
      ),
      icon: LucideIcons.activity,
      accent: connected ? c.up : c.gold,
    );
  }

  Widget _refreshButton(BuildContext context) {
    final c = context.colors;
    return InkWell(
      onTap: loading ? null : onRefresh,
      borderRadius: BorderRadius.circular(5),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: c.blue.withValues(alpha: loading ? 0.06 : 0.12),
          border: Border.all(color: c.blue.withValues(alpha: 0.28)),
          borderRadius: BorderRadius.circular(5),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              LucideIcons.refreshCw,
              size: 12,
              color: loading ? c.t3 : c.blue,
            ),
            const SizedBox(width: 6),
            Text(
              loading ? 'Refreshing…' : 'Refresh dashboard',
              style: AppTextStyles.bodyBold(
                loading ? c.t3 : c.blue,
              ).copyWith(fontSize: 11),
            ),
          ],
        ),
      ),
    );
  }

  Widget _healthRow(
    BuildContext context,
    String text,
    Color tone, {
    bool top = false,
  }) {
    final c = context.colors;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(14, 9, 14, 9),
      decoration: BoxDecoration(
        border: top ? Border(top: BorderSide(color: c.bd)) : null,
      ),
      child: Row(
        children: [
          Container(
            width: 7,
            height: 7,
            decoration: BoxDecoration(color: tone, shape: BoxShape.circle),
          ),
          const SizedBox(width: 9),
          Expanded(child: Text(text, style: AppTextStyles.bodySmall(c.t2))),
        ],
      ),
    );
  }
}
