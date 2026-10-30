import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:aiei_wealth/providers/providers.dart';
import 'package:aiei_wealth/services/api_service.dart';

/// Fake ApiService that reports whatever profile the test wants, and can fail
/// the first N calls to emulate the backend still booting.
class _FakeApi implements ApiService {
  _FakeApi(this.profile, {this.failFirst = 0});

  final Map<String, dynamic> profile;
  final int failFirst;
  int calls = 0;

  @override
  Future<Map<String, dynamic>> getProfile() async {
    calls++;
    if (calls <= failFirst) throw Exception('backend not up');
    return profile;
  }

  // IsGuestNotifier only ever calls getProfile(); the rest of the surface is
  // never touched, so forward it rather than stubbing ~80 methods.
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// Pump the microtask/timer queue until [check] passes or the budget runs out.
Future<void> _settleUntil(bool Function() check, {int maxTicks = 200}) async {
  for (var i = 0; i < maxTicks; i++) {
    if (check()) return;
    await Future<void>.delayed(Duration.zero);
  }
}

void main() {
  group('IsGuestNotifier rehydration', () {
    test('clears guest mode when the backend already has a session', () async {
      final container = ProviderContainer(overrides: [
        apiServiceProvider.overrideWithValue(
          _FakeApi({'logged_in': true, 'email': 'a@b.com'}),
        ),
      ]);
      addTearDown(container.dispose);

      // Starts guest — the backend has not been asked yet.
      expect(container.read(isGuestProvider), isTrue);

      await _settleUntil(() => container.read(isGuestProvider) == false);
      expect(container.read(isGuestProvider), isFalse,
          reason: 'a persisted backend session must lift guest mode');
    });

    test('recognises a session that only carries an email', () async {
      final container = ProviderContainer(overrides: [
        apiServiceProvider.overrideWithValue(_FakeApi({'email': 'a@b.com'})),
      ]);
      addTearDown(container.dispose);

      container.read(isGuestProvider);
      await _settleUntil(() => container.read(isGuestProvider) == false);
      expect(container.read(isGuestProvider), isFalse);
    });

    test('stays in guest mode when nobody is logged in', () async {
      final api = _FakeApi({'logged_in': false});
      final container = ProviderContainer(overrides: [
        apiServiceProvider.overrideWithValue(api),
      ]);
      addTearDown(container.dispose);

      container.read(isGuestProvider);
      await _settleUntil(() => api.calls > 0);
      await Future<void>.delayed(Duration.zero);

      expect(container.read(isGuestProvider), isTrue);
      expect(api.calls, 1, reason: 'a definitive "no session" must not be retried');
    });

    test('retries while the backend is still booting', () {
      fakeAsync((async) {
        final api = _FakeApi({'logged_in': true}, failFirst: 3);
        final container = ProviderContainer(overrides: [
          apiServiceProvider.overrideWithValue(api),
        ]);
        addTearDown(container.dispose);

        container.read(isGuestProvider);
        async.elapse(const Duration(seconds: 1));
        expect(container.read(isGuestProvider), isTrue,
            reason: 'still guest while the backend refuses connections');

        // 3 failures at 2s apart, then the 4th call succeeds.
        async.elapse(const Duration(seconds: 10));
        expect(api.calls, greaterThan(3));
        expect(container.read(isGuestProvider), isFalse,
            reason: 'guest mode must lift once the backend comes up');
      });
    });
  });
}
