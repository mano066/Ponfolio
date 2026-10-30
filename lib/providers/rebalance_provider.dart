import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/local_storage_service.dart';
import 'allocation_provider.dart';
import 'providers.dart';

/// How often the book is opened for review. The band still decides whether
/// anything is actually traded when it is.
enum RebalanceCadence { semiannual, annual }

extension RebalanceCadenceMeta on RebalanceCadence {
  String get wire => switch (this) {
        RebalanceCadence.semiannual => 'semiannual',
        RebalanceCadence.annual => 'annual',
      };

  String get label => switch (this) {
        RebalanceCadence.semiannual => 'EVERY 6M',
        RebalanceCadence.annual => 'EVERY 1Y',
      };

  static RebalanceCadence fromWire(String? wire) =>
      wire == 'annual' ? RebalanceCadence.annual : RebalanceCadence.semiannual;
}

/// Whether gains are priced as a resident or an NRI (TDS withheld at
/// source). Defaults to resident; the user's choice is remembered.
class RebalanceResidencyNotifier extends Notifier<String> {
  @override
  String build() =>
      ref.read(localStorageProvider).getSetting<String>(
          LocalStorageService.keyRebalanceResidency) ??
      'resident';

  void set(String value) {
    state = value;
    ref.read(localStorageProvider)
        .setSetting(LocalStorageService.keyRebalanceResidency, value);
  }
}

final rebalanceResidencyProvider =
    NotifierProvider<RebalanceResidencyNotifier, String>(
  RebalanceResidencyNotifier.new,
);

/// The saved rebalance policy: both bands, the trigger switches, the custom
/// thresholds and the selection.
///
/// Held server-side rather than in local storage because the engine has to
/// build the plan from exactly the same numbers the screen is showing. Two
/// copies of a policy is two policies.
class RebalanceSettingsNotifier
    extends AsyncNotifier<Map<String, dynamic>> {
  @override
  Future<Map<String, dynamic>> build() =>
      ref.read(apiServiceProvider).getRebalanceSettings();

  /// Save a partial change and adopt the policy the backend echoes back.
  ///
  /// The echo matters: the backend swaps crossed sliders and rescales targets
  /// that do not sum to 100, so the value it stored is not always the value
  /// that was sent, and the screen must show what was actually stored.
  Future<void> save({
    Map<String, double>? taxRates,
    Map<String, double>? assetLimits,
    bool? longTermOnly,
    double? minWeightPct,
    double? maxWeightPct,
    double? deviationPct,
    String? cadence,
    List<String>? triggers,
    double? boomGainPct,
    double? crashDropPct,
    double? gainTriggerPct,
    double? lossTriggerPct,
    double? volTriggerPct,
    Map<String, double>? categoryTargets,
    String? mode,
    String? strategy,
    List<String>? selectedCategories,
    List<String>? selectedAssets,
    bool clearSelectedCategories = false,
    bool clearSelectedAssets = false,
    bool clearGainTrigger = false,
    bool clearLossTrigger = false,
  }) async {
    final saved = await ref.read(apiServiceProvider).saveRebalanceSettings(
          taxRates: taxRates,
          assetLimits: assetLimits,
          longTermOnly: longTermOnly,
          minWeightPct: minWeightPct,
          maxWeightPct: maxWeightPct,
          deviationPct: deviationPct,
          cadence: cadence,
          triggers: triggers,
          boomGainPct: boomGainPct,
          crashDropPct: crashDropPct,
          gainTriggerPct: gainTriggerPct,
          lossTriggerPct: lossTriggerPct,
          volTriggerPct: volTriggerPct,
          categoryTargets: categoryTargets,
          mode: mode,
          strategy: strategy,
          selectedCategories: selectedCategories,
          selectedAssets: selectedAssets,
          clearSelectedCategories: clearSelectedCategories,
          clearSelectedAssets: clearSelectedAssets,
          clearGainTrigger: clearGainTrigger,
          clearLossTrigger: clearLossTrigger,
        );
    state = AsyncData(saved);
  }

  /// Add or remove one trigger, leaving the others as they are.
  Future<void> toggleTrigger(String name) async {
    final current = List<String>.from(
        (state.value?['triggers'] as List?)?.cast<String>() ?? const []);
    if (current.contains(name)) {
      current.remove(name);
    } else {
      current.add(name);
    }
    await save(triggers: current);
  }

  /// Tick or untick one category.
  ///
  /// A null selection means "everything", so the first untick has to be
  /// expanded into the full list minus that one — otherwise unticking Gold
  /// would read as selecting only Gold.
  Future<void> toggleCategory(String name, List<String> all) async {
    final selected = (state.value?['selected_categories'] as List?)
            ?.cast<String>() ??
        all;
    final next = List<String>.from(selected);
    if (next.contains(name)) {
      next.remove(name);
    } else {
      next.add(name);
    }
    if (next.length == all.length) {
      // Back to everything: store it as "no narrowing" so a category added
      // later is included by default instead of silently left out.
      await save(clearSelectedCategories: true);
      return;
    }
    await save(selectedCategories: next);
  }

  /// Tick or untick one holding within the currently selected categories.
  Future<void> toggleAsset(String key, List<String> allKeys) async {
    final selected =
        (state.value?['selected_assets'] as List?)?.cast<String>() ??
            allKeys;
    final next = List<String>.from(selected);
    if (next.contains(key)) {
      next.remove(key);
    } else {
      next.add(key);
    }
    if (next.length >= allKeys.length) {
      await save(clearSelectedAssets: true);
      return;
    }
    await save(selectedAssets: next);
  }

  Future<void> selectAllAssets() => save(clearSelectedAssets: true);

  /// Pick one of the backtested presets. S10 is the default.
  Future<void> setStrategy(String id) => save(strategy: id);
}

final rebalanceSettingsProvider =
    AsyncNotifierProvider<RebalanceSettingsNotifier, Map<String, dynamic>>(
  RebalanceSettingsNotifier.new,
);

/// The selectable presets (S1–S10, the master, Custom) and what each measured
/// in the 2011–2026 backtest. Fetched once — the list is static reference data,
/// not portfolio state.
final rebalanceStrategiesProvider =
    FutureProvider<Map<String, dynamic>>((ref) async {
  return ref.read(apiServiceProvider).getRebalanceStrategies();
});

/// Slider positions being dragged but not yet saved, so the plan can be
/// previewed at them. Null means "use whatever is saved".
class RebalanceBandPreview {
  final double? minPct;
  final double? maxPct;
  final double? deviationPct;

  const RebalanceBandPreview({this.minPct, this.maxPct, this.deviationPct});

  bool get isEmpty =>
      minPct == null && maxPct == null && deviationPct == null;
}

class RebalanceBandPreviewNotifier extends Notifier<RebalanceBandPreview> {
  @override
  RebalanceBandPreview build() => const RebalanceBandPreview();

  void setBand(double min, double max) =>
      state = RebalanceBandPreview(
          minPct: min, maxPct: max, deviationPct: state.deviationPct);

  void setDeviation(double value) => state = RebalanceBandPreview(
      minPct: state.minPct, maxPct: state.maxPct, deviationPct: value);

  void clear() => state = const RebalanceBandPreview();
}

final rebalanceBandPreviewProvider = NotifierProvider<
    RebalanceBandPreviewNotifier, RebalanceBandPreview>(
  RebalanceBandPreviewNotifier.new,
);

/// The plan itself. Kept as the raw payload rather than a typed model: the
/// engine owns the policy and every field it reports is already presentation-
/// ready, so a mirror class here would only be a second place to update when a
/// tax rate changes.
/// Every trade date, replayed. Kept out of [rebalancePlanProvider] on purpose:
/// the plan must stay fast, and this fetches a year of daily closes per
/// holding the first time it runs.
final rebalanceHistoryProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  ref.watch(portfolioProvider);
  return ref.read(apiServiceProvider).getRebalanceHistory();
});

/// Which page is on screen. Defaults to -1, read as "the most recent one",
/// so the section opens on today rather than on 10 March.
class RebalanceHistoryPageNotifier extends Notifier<int> {
  @override
  int build() => -1;
  void show(int index) => state = index;
  void latest() => state = -1;
}

final rebalanceHistoryPageProvider =
    NotifierProvider<RebalanceHistoryPageNotifier, int>(
        RebalanceHistoryPageNotifier.new);

/// New money waiting to be placed, in rupees.
///
/// Held here rather than inside the section so that changing it re-plans
/// through the same path as a slider: the contribution is an input to the
/// plan, not a decoration on top of one.
class RebalanceNewMoneyNotifier extends Notifier<double> {
  @override
  double build() => 0;
  void set(double v) => state = (v.isFinite && v > 0) ? v : 0;
  void clear() => state = 0;
}

final rebalanceNewMoneyProvider =
    NotifierProvider<RebalanceNewMoneyNotifier, double>(
        RebalanceNewMoneyNotifier.new);

final rebalancePlanProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final api = ref.read(apiServiceProvider);
  // Re-plan whenever the holdings behind it move, or the numbers on screen
  // would describe a portfolio the user no longer owns.
  ref.watch(portfolioProvider);
  ref.watch(mfPortfolioProvider);
  // The saved policy is an input to the plan, so a saved slider re-plans.
  final settings = await ref.watch(rebalanceSettingsProvider.future);
  final preview = ref.watch(rebalanceBandPreviewProvider);
  // Gold and debt the user tracks by hand live only on this device, so they
  // have to be sent up with the request.
  final manual = ref.watch(otherAssetsProvider);
  final newMoney = ref.watch(rebalanceNewMoneyProvider);

  return api.getRebalancePlan(
    cadence: settings['cadence']?.toString(),
    residency: ref.watch(rebalanceResidencyProvider),
    minWeightPct: preview.minPct,
    maxWeightPct: preview.maxPct,
    deviationPct: preview.deviationPct,
    manualGold: manual['Gold'] ?? 0,
    manualDebt: manual['Debt'] ?? 0,
    newMoney: newMoney,
  );
});
