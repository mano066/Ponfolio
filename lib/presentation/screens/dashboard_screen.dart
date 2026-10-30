import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/providers.dart';
import '../../providers/allocation_provider.dart';
import '../../providers/expense_provider.dart';
import '../../providers/deploy_provider.dart';
import '../../data/models/dashboard_snapshot.dart';
import '../../data/models/dip_models.dart';
import '../widgets/conviction_section.dart';
import '../widgets/dashboard_overview.dart';
import '../widgets/deploy/dip_detail_sheet.dart';
import '../widgets/deploy/market_tape_strip.dart';
import '../widgets/deploy/opportunity_cards.dart';
import '../widgets/deploy/todays_opportunities_bar.dart';

/// One overview of existing sources. Each section can fail independently.
///
/// The decision half of this screen is v1.4.3's: today's opportunities, the
/// market tape behind them, then where to add and where to buy — the same
/// widgets, so a tap still opens the same three-level detail sheet. Below
/// them sit the four sections that answer "where do I stand": the action
/// bar's alerts, portfolio summary, allocation health and the expense and
/// savings snapshot.
///
/// The opportunity widgets read their own providers, so they are built here
/// and handed down; [DashboardOverview] stays layout-only and testable
/// without a backend.
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final guest = ref.watch(isGuestProvider);
    final portfolio = guest
        ? const AsyncData<Map<String, dynamic>>({})
        : ref.watch(livePortfolioProvider);
    final funds = guest
        ? const AsyncData<Map<String, dynamic>>({})
        : ref.watch(mfPortfolioProvider);
    final now = DateTime.now();
    final expenses = guest ? null : ref.watch(expenseStoreProvider);
    final model = DashboardSnapshot(
      equity: portfolio.value,
      funds: funds.value,
      other: guest ? const {} : ref.watch(otherAssetsProvider),
      targets: guest ? const {} : ref.watch(targetAllocationProvider),
    );
    return DashboardOverview(
      snapshot: model,
      guest: guest,
      loading: portfolio.isLoading || funds.isLoading,
      failed: portfolio.hasError || funds.hasError,
      now: now,
      tape: ref.watch(marketTapeProvider),
      fundDips: guest ? const AsyncData(null) : ref.watch(fundDipsProvider),
      stockDips: guest ? const AsyncData(null) : ref.watch(stockDipsProvider),
      xirr: guest ? null : ref.watch(portfolioXirrProvider).value,
      closed: guest ? null : ref.watch(closedPositionsProvider).value,
      kite: ref.watch(kiteStatusProvider),
      expenses: DashboardExpense.fromYear(
        expenses?.byYear[now.year],
        now,
        previousYear: expenses?.byYear[now.year - 1],
      ),
      expenseUpdated: expenses?.lastSavedIso,
      expenseLoading: expenses?.importing ?? false,
      // The tape is public market data and works signed out, so a guest still
      // gets the one decision section that does not need their holdings. The
      // rest fall back to the overview's own sign-in notices.
      marketTape: const MarketTapeStrip(),
      opportunities: guest
          ? null
          : TodaysOpportunitiesBar(onOpen: (row) => _openRow(context, ref, row)),
      fundBoard: guest
          ? null
          : FundOpportunitySection(onOpen: (fund) => showFundDetail(context, fund)),
      conviction: guest ? null : const ConvictionSection(),
      stockBoard: guest
          ? null
          : StockOpportunitySection(
              onOpen: (stock) => showStockDetail(context, stock),
            ),
      onNavigate: (tab) => ref.read(activeTabProvider.notifier).setTab(tab),
      onRefresh: () {
        ref.invalidate(portfolioProvider);
        ref.invalidate(mfPortfolioProvider);
        ref.invalidate(portfolioXirrProvider);
        ref.invalidate(marketTapeProvider);
        ref.invalidate(kiteStatusProvider);
        ref.read(deployRefreshProvider.notifier).manualRefresh();
      },
    );
  }

  /// Opens the right detail sheet for a master-bar row.
  ///
  /// The bar carries only a kind and a key, so the full record is looked up
  /// from the section providers rather than duplicated onto the row. That
  /// keeps one source of truth per holding: a sheet opened from the bar and
  /// one opened from the card below it show the same object, and cannot drift
  /// apart when the two refresh at different times.
  void _openRow(BuildContext context, WidgetRef ref, OpportunityRow row) {
    if (row.kind == 'fund') {
      final funds = ref.read(fundDipsProvider).value?.funds ?? const <FundDip>[];
      for (final f in funds) {
        if (f.schemeName == row.key) {
          showFundDetail(context, f);
          return;
        }
      }
    } else {
      final stocks =
          ref.read(stockDipsProvider).value?.stocks ?? const <StockDip>[];
      for (final s in stocks) {
        if (s.symbol == row.key) {
          showStockDetail(context, s);
          return;
        }
      }
    }
  }
}
