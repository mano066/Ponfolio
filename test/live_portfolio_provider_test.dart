import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:aiei_wealth/providers/providers.dart';

/// The dashboard used to read a one-shot portfolio fetch, so its prices only
/// moved when the user pressed refresh. `livePortfolioProvider` lays the
/// 5-second live poll over that fetch; these pin down when a tick is trusted.

class _NotGuest extends IsGuestNotifier {
  @override
  bool build() => false;
}

Map<String, dynamic> _book(double value, {int holdings = 1}) => {
      'total_portfolio_value': value,
      'data_source': 'kite',
      'holdings': [
        for (var i = 0; i < holdings; i++) {'symbol': 'S$i', 'total_value': value},
      ],
    };

void main() {
  late StreamController<Map<String, dynamic>> live;

  ProviderContainer container({Map<String, dynamic>? base}) {
    live = StreamController<Map<String, dynamic>>();
    final c = ProviderContainer(overrides: [
      isGuestProvider.overrideWith(_NotGuest.new),
      portfolioProvider.overrideWith((ref) async => base ?? _book(100)),
      livePriceProvider.overrideWith((ref) => live.stream),
    ]);
    addTearDown(() {
      live.close();
      c.dispose();
    });
    return c;
  }

  Future<void> settle(ProviderContainer c) async {
    await c.read(portfolioProvider.future);
    await Future<void>.delayed(Duration.zero);
  }

  test('shows the base fetch until a live tick arrives', () async {
    final c = container();
    c.listen(livePortfolioProvider, (_, _) {});
    await settle(c);
    expect(c.read(livePortfolioProvider).value?['total_portfolio_value'], 100);
  });

  test('a live tick replaces the numbers without a loading state', () async {
    final c = container();
    c.listen(livePortfolioProvider, (_, _) {});
    await settle(c);
    live.add(_book(123.5));
    await Future<void>.delayed(Duration.zero);
    final v = c.read(livePortfolioProvider);
    expect(v.isLoading, isFalse);
    expect(v.value?['total_portfolio_value'], 123.5);
    expect(v.value?['live'], isTrue);
  });

  test('a tick describing a different holdings list is ignored', () async {
    final c = container();
    c.listen(livePortfolioProvider, (_, _) {});
    await settle(c);
    live.add(_book(999, holdings: 2));
    await Future<void>.delayed(Duration.zero);
    expect(c.read(livePortfolioProvider).value?['total_portfolio_value'], 100);
  });

  test('an empty tick (guest or failed poll) changes nothing', () async {
    final c = container();
    c.listen(livePortfolioProvider, (_, _) {});
    await settle(c);
    live.add(<String, dynamic>{});
    await Future<void>.delayed(Duration.zero);
    expect(c.read(livePortfolioProvider).value?['total_portfolio_value'], 100);
  });
}
