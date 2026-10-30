import 'package:flutter/material.dart';
import 'package:aiei_wealth/core/theme/app_colors.dart';

/// BuildContext extensions for quick access to theme colors and text styles.
extension ContextExtensions on BuildContext {
  /// Quick access to our custom color scheme
  AppColorScheme get colors => Theme.of(this).extension<AppColorScheme>()!;

  /// Check if dark mode
  bool get isDark => Theme.of(this).brightness == Brightness.dark;

  /// Screen size
  Size get screenSize => MediaQuery.sizeOf(this);
  double get screenWidth => screenSize.width;
  double get screenHeight => screenSize.height;

  /// P&L color helper
  Color pnlColor(double value) => value >= 0 ? colors.up : colors.dn;
  Color pnlBg(double value) => value >= 0 ? colors.upBg : colors.dnBg;
}

// ══════════════════════════════════════════
//  NUMBER FORMATTING (top-level functions)
//  Works on any num/int/double/dynamic
// ══════════════════════════════════════════

/// Format as Indian Rupees: ₹1,23,456
String formatINR(num value, {int decimals = 0}) {
  if (value == 0) return '₹0';
  final isNeg = value < 0;
  final abs = value.abs();
  final parts = abs.toStringAsFixed(decimals).split('.');
  String intPart = parts[0];
  String decPart = parts.length > 1 ? '.${parts[1]}' : '';

  if (intPart.length > 3) {
    final last3 = intPart.substring(intPart.length - 3);
    final rest = intPart.substring(0, intPart.length - 3);
    final reversed = rest.split('').reversed.toList();
    final formatted = StringBuffer();
    for (int i = 0; i < reversed.length; i++) {
      if (i > 0 && i % 2 == 0) formatted.write(',');
      formatted.write(reversed[i]);
    }
    intPart = '${formatted.toString().split('').reversed.join('')},$last3';
  }
  return '${isNeg ? '-' : ''}₹$intPart$decPart';
}

/// Format as signed INR: +₹1,23,456
String formatSignedINR(num value, {int decimals = 0}) {
  final sign = value >= 0 ? '+' : '';
  return '$sign${formatINR(value, decimals: decimals)}';
}

/// Format as percentage with sign: +12.34%
String formatPct(num value, {int decimals = 2}) {
  final sign = value >= 0 ? '+' : '';
  return '$sign${value.toStringAsFixed(decimals)}%';
}

/// Format an annualised return: `+12.3%`, `~+12.3%` when the backend had to
/// seed part of the position at avg cost, or `—` when no dated cashflows
/// exist for it. Never invents a number — a null XIRR renders as a dash so an
/// un-backed cell can't be mistaken for a real 0%.
String formatXirr(double? value, {bool exact = true, int decimals = 1}) {
  if (value == null) return '—';
  return '${exact ? '' : '~'}${formatPct(value, decimals: decimals)}';
}

/// Reads the `xirr` / `xirr_exact` pair off a holding map from the API.
/// The value is null when the backend had no dated cashflows for the row.
(double?, bool) xirrOf(Map<String, dynamic> row) {
  final raw = row['xirr'];
  return (raw is num ? raw.toDouble() : null, row['xirr_exact'] != false);
}

/// Compact format: 1.2L, 45.3K
String formatCompact(num value) {
  final abs = value.abs();
  if (abs >= 10000000) return '${(value / 10000000).toStringAsFixed(1)}Cr';
  if (abs >= 100000) return '${(value / 100000).toStringAsFixed(1)}L';
  if (abs >= 1000) return '${(value / 1000).toStringAsFixed(0)}K';
  return value.toStringAsFixed(0);
}

/// Convenience extension on num so existing code still works
extension NumFormatting on num {
  String toINR({int decimals = 0}) => formatINR(this, decimals: decimals);
  String toPct({int decimals = 2}) => formatPct(this, decimals: decimals);
  String toSignedINR({int decimals = 0}) => formatSignedINR(this, decimals: decimals);
  String toCompact() => formatCompact(this);
}

/// String helpers
extension StringX on String {
  /// Remove .NS or .BO suffix from stock symbols
  String get cleanSymbol => replaceAll(RegExp(r'\.(NS|BO)$', caseSensitive: false), '');
}
