import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'app_colors.dart';

/// Builds MaterialApp ThemeData with custom extensions for both modes.
class AppTheme {
  AppTheme._();

  static ThemeData dark() => _build(Brightness.dark, AppColorScheme.dark);
  static ThemeData light() => _build(Brightness.light, AppColorScheme.light);

  static ThemeData _build(Brightness brightness, AppColorScheme colors) {
    final isDark = brightness == Brightness.dark;
    final baseTextTheme = GoogleFonts.interTextTheme(
      isDark ? ThemeData.dark().textTheme : ThemeData.light().textTheme,
    );

    return ThemeData(
      brightness: brightness,
      useMaterial3: true,
      scaffoldBackgroundColor: colors.bg0,
      colorScheme: ColorScheme(
        brightness: brightness,
        primary: colors.blue,
        onPrimary: Colors.white,
        secondary: colors.accent,
        onSecondary: Colors.white,
        surface: colors.bg1,
        onSurface: colors.t1,
        error: colors.dn,
        onError: Colors.white,
      ),
      textTheme: baseTextTheme.apply(
        bodyColor: colors.t1,
        displayColor: colors.t1,
      ),
      cardTheme: CardThemeData(
        color: colors.bg2,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: colors.bd, width: 1),
        ),
      ),
      dividerTheme: DividerThemeData(color: colors.bd, thickness: 1),
      scrollbarTheme: ScrollbarThemeData(
        thumbColor: WidgetStateProperty.all(colors.t4.withValues(alpha: 0.3)),
        trackColor: WidgetStateProperty.all(Colors.transparent),
        thickness: WidgetStateProperty.all(4),
        radius: const Radius.circular(4),
      ),
      tooltipTheme: TooltipThemeData(
        decoration: BoxDecoration(
          color: colors.bg2,
          border: Border.all(color: colors.bd),
          borderRadius: BorderRadius.circular(8),
        ),
        textStyle: TextStyle(color: colors.t1, fontSize: 12),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: colors.bg0,
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: colors.bd),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: colors.bd),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: colors.blue, width: 1.5),
        ),
        hintStyle: TextStyle(color: colors.t4, fontSize: 13),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: colors.blue,
          foregroundColor: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          textStyle: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
        ),
      ),
      extensions: [colors],
    );
  }
}
