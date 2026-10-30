import 'dart:ui';
import 'dart:io';
import 'package:flutter/material.dart';
import 'services/backend_launcher.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:window_manager/window_manager.dart';
import 'core/theme/app_theme.dart';
import 'data/models/expense_config.dart';
import 'providers/providers.dart';
import 'services/local_storage_service.dart';
import 'services/system_tray_service.dart';
import 'presentation/screens/app_shell.dart';
import 'presentation/screens/welcome_screen.dart';
import 'presentation/screens/system_check_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // ── Hive Local Storage Setup ──
  final storage = LocalStorageService();
  await storage.init();
  await storage.markCleanStart();

  // Optional per-install expense settings (git-ignored; defaults if absent).
  await ExpenseConfig.load();

  // ── Auto-start Backend Server (non-blocking) ──
  // Fire-and-forget: the backend boots in the background.
  // The SystemCheckScreen will wait for it to become available.
  BackendLauncher.start();

  // ── Window Manager Setup ──
  await windowManager.ensureInitialized();

  // Restore saved window state, or use defaults
  final savedWindow = storage.getWindowState();
  
  // Validate that saved position is actually on-screen
  final bool hasSavedPosition = savedWindow != null && _isPositionOnScreen(savedWindow);

  final windowOptions = WindowOptions(
    size: hasSavedPosition
        ? Size(savedWindow.width, savedWindow.height)
        : const Size(1440, 900),
    minimumSize: const Size(375, 600),
    center: !hasSavedPosition,
    title: 'Ponfolio',
    backgroundColor: const Color(0xFFF4F6FA),
    titleBarStyle: TitleBarStyle.normal,
  );

  await windowManager.waitUntilReadyToShow(windowOptions, () async {
    // Restore position only if it's a valid on-screen location
    if (hasSavedPosition) {
      await windowManager.setPosition(Offset(savedWindow.x, savedWindow.y));
      if (savedWindow.isMaximized) {
        await windowManager.maximize();
      }
    }
    await windowManager.show();
    await windowManager.focus();
  });

  // ── System Tray Setup ──
  await SystemTrayService().init();

  // ── Global error handler for crash recovery ──
  FlutterError.onError = (details) {
    FlutterError.presentError(details);
    storage.markCrash(details.exceptionAsString());
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    storage.markCrash('$error\n$stack');
    return true;
  };

  // ── Restore theme from storage ── (default: light, Groww/INDmoney style)
  final savedTheme = storage.getThemeMode();
  final initialIsDark = savedTheme == 'dark';

  runApp(
    ProviderScope(
      overrides: [
        // Seed the theme provider with the persisted value
        isDarkModeProvider.overrideWith(() => IsDarkModeNotifier(initialIsDark)),
        // Make storage available to all providers
        localStorageProvider.overrideWithValue(storage),
      ],
      child: const AieiWealthApp(),
    ),
  );
}

/// Validate that a saved window position is actually visible on screen.
/// Returns false for positions like (-32000, -32000) which Windows uses for hidden windows.
bool _isPositionOnScreen(WindowState state) {
  // Reject obviously off-screen coordinates
  if (state.x < -500 || state.y < -500) return false;
  if (state.x > 10000 || state.y > 10000) return false;
  if (state.width < 200 || state.height < 200) return false;
  return true;
}

class AieiWealthApp extends ConsumerStatefulWidget {
  const AieiWealthApp({super.key});

  @override
  ConsumerState<AieiWealthApp> createState() => _AieiWealthAppState();
}

class _AieiWealthAppState extends ConsumerState<AieiWealthApp>
    with WindowListener {
  @override
  void initState() {
    super.initState();
    windowManager.addListener(this);
    windowManager.setPreventClose(true);

    // Show crash recovery notification if previous session crashed
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final crash = ref.read(localStorageProvider).getLastCrash();
      if (crash != null && mounted) {
        _showCrashRecoveryBanner(crash);
      }
    });
  }

  @override
  void dispose() {
    windowManager.removeListener(this);
    super.dispose();
  }

  /// Intercept window close — save state and confirm
  @override
  void onWindowClose() async {
    final isPreventClose = await windowManager.isPreventClose();
    if (!isPreventClose) return;

    // Save final window state
    await _saveWindowState();

    // Stop backend server
    BackendLauncher.stop();

    // Close Hive boxes cleanly
    await ref.read(localStorageProvider).dispose();

    // Destroy the window
    await windowManager.destroy();
  }

  void _showCrashRecoveryBanner(Map<String, dynamic> crash) {
    if (!mounted) return;
    final time = crash['time'] ?? '';
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      backgroundColor: const Color(0xCC1A1E2E),
      behavior: SnackBarBehavior.floating,
      margin: const EdgeInsets.only(bottom: 60, left: 80, right: 80),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      duration: const Duration(seconds: 8),
      content: Row(children: [
        const Icon(Icons.warning_amber_rounded, size: 18, color: Color(0xFFFFD740)),
        const SizedBox(width: 12),
        Expanded(child: Text(
          'Previous session crashed at $time. Your data has been preserved.',
          style: const TextStyle(color: Colors.white70, fontSize: 12),
        )),
      ]),
      action: SnackBarAction(label: 'Dismiss', textColor: const Color(0xFF448AFF),
        onPressed: () {}),
    ));
  }

  // ── Persist window state on move/resize ──

  Future<void> _saveWindowState() async {
    final storage = ref.read(localStorageProvider);
    try {
      final pos = await windowManager.getPosition();
      final size = await windowManager.getSize();
      final maximized = await windowManager.isMaximized();
      await storage.saveWindowState(
        x: pos.dx,
        y: pos.dy,
        width: size.width,
        height: size.height,
        isMaximized: maximized,
      );
    } catch (_) {}
  }

  @override
  void onWindowMoved() => _saveWindowState();

  @override
  void onWindowResized() => _saveWindowState();

  @override
  void onWindowMaximize() => _saveWindowState();

  @override
  void onWindowUnmaximize() => _saveWindowState();

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkModeProvider);

    // Persist theme changes to Hive
    ref.listen<bool>(isDarkModeProvider, (_, isDark) {
      ref.read(localStorageProvider).setThemeMode(isDark ? 'dark' : 'light');
    });

    return MaterialApp(
      title: 'Ponfolio',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: isDark ? ThemeMode.dark : ThemeMode.light,
      home: const _HomeRouter(),
    );
  }
}

/// Routes: Welcome → System Check → AppShell
/// Welcome shows on EVERY launch — user picks Google or Guest each time.
enum AppPhase { welcome, systemCheck, dashboard }

/// Global app phase notifier — resettable from anywhere (e.g. logout).
class AppPhaseNotifier extends Notifier<AppPhase> {
  @override
  AppPhase build() => AppPhase.welcome;
  void set(AppPhase phase) => state = phase;
}

final appPhaseProvider = NotifierProvider<AppPhaseNotifier, AppPhase>(AppPhaseNotifier.new);

class _HomeRouter extends ConsumerWidget {
  const _HomeRouter();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final phase = ref.watch(appPhaseProvider);

    switch (phase) {
      case AppPhase.welcome:
        return WelcomeScreen(
          onLogin: () => ref.read(appPhaseProvider.notifier).set(AppPhase.systemCheck),
          onSkip: () => ref.read(appPhaseProvider.notifier).set(AppPhase.systemCheck),
        );
      case AppPhase.systemCheck:
        return SystemCheckScreen(
          onContinue: () => ref.read(appPhaseProvider.notifier).set(AppPhase.dashboard),
        );
      case AppPhase.dashboard:
        return const AppShell();
    }
  }
}
