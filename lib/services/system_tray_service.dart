import 'dart:io';
import 'package:flutter/material.dart';
import 'package:tray_manager/tray_manager.dart';
import 'package:local_notifier/local_notifier.dart';
import 'package:window_manager/window_manager.dart';

/// System tray integration for Ponfolio.
/// Provides:
///  - Tray icon with context menu (Show/Refresh/Quit)
///  - Native Windows notifications for AI analysis completion
class SystemTrayService with TrayListener {
  static final SystemTrayService _instance = SystemTrayService._internal();
  factory SystemTrayService() => _instance;
  SystemTrayService._internal();

  bool _initialized = false;
  VoidCallback? onRefreshRequested;

  /// Initialize system tray with icon and context menu.
  Future<void> init() async {
    if (_initialized) return;
    _initialized = true;

    try {
      // Initialize local notifications
      await localNotifier.setup(appName: 'Ponfolio');

      // Resolve tray icon path from the executable's directory
      // In dev mode: windows/runner/resources/app_icon.ico (relative)
      // In installed mode: {app}\data\flutter_assets\... or find the exe's own icon
      String iconPath;
      if (Platform.isWindows) {
        final exeDir = File(Platform.resolvedExecutable).parent.path;
        // Try the installed location first (exe directory itself)
        final installedIcon = '$exeDir\\app_icon.ico';
        final devIcon = 'windows\\runner\\resources\\app_icon.ico';
        if (File(installedIcon).existsSync()) {
          iconPath = installedIcon;
        } else if (File(devIcon).existsSync()) {
          iconPath = devIcon;
        } else {
          // Fallback: use the exe itself as icon source
          iconPath = Platform.resolvedExecutable;
        }
      } else {
        iconPath = 'assets/icon.png';
      }

      // Set up system tray
      await trayManager.setIcon(iconPath);
      await trayManager.setToolTip('Ponfolio');
      await _buildMenu();
      trayManager.addListener(this);
    } catch (_) {
      // Silently fail — tray is optional
    }
  }

  Future<void> _buildMenu() async {
    final menu = Menu(items: [
      MenuItem(key: 'show', label: 'Show Terminal'),
      MenuItem.separator(),
      MenuItem(key: 'refresh', label: 'Refresh Portfolio'),
      MenuItem.separator(),
      MenuItem(key: 'quit', label: 'Quit'),
    ]);
    await trayManager.setContextMenu(menu);
  }

  @override
  void onTrayIconMouseDown() async {
    await windowManager.show();
    await windowManager.focus();
  }

  @override
  void onTrayIconRightMouseDown() async {
    await trayManager.popUpContextMenu();
  }

  @override
  void onTrayMenuItemClick(MenuItem menuItem) async {
    switch (menuItem.key) {
      case 'show':
        await windowManager.show();
        await windowManager.focus();
      case 'refresh':
        onRefreshRequested?.call();
      case 'quit':
        await windowManager.destroy();
    }
  }

  /// Show a native Windows notification.
  Future<void> showNotification({
    required String title,
    String? body,
  }) async {
    try {
      final notification = LocalNotification(
        title: title,
        body: body ?? '',
      );
      await notification.show();
    } catch (_) {}
  }

  /// Dispose tray resources.
  Future<void> dispose() async {
    trayManager.removeListener(this);
    await trayManager.destroy();
  }
}
