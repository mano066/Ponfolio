import 'package:flutter/material.dart';
import 'app_colors.dart';

/// All gradient definitions matching globals.css
class AppGradients {
  AppGradients._();

  // ── Primary (blue → purple) ──
  static const primary = LinearGradient(
    begin: Alignment.topLeft, end: Alignment.bottomRight,
    colors: [AppColors.gradientPrimaryStart, AppColors.gradientPrimaryEnd],
  );

  // ── P&L gradients ──
  static const up = LinearGradient(
    begin: Alignment.topLeft, end: Alignment.bottomRight,
    colors: [AppColors.gradientUpStart, AppColors.gradientUpEnd],
  );

  static const dn = LinearGradient(
    begin: Alignment.topLeft, end: Alignment.bottomRight,
    colors: [AppColors.gradientDnStart, AppColors.gradientDnEnd],
  );

  // ── Logo / brand ──
  static const brand = LinearGradient(
    begin: Alignment.topLeft, end: Alignment.bottomRight,
    colors: [Color(0xFF448AFF), Color(0xFF7C4DFF)],
  );

  // ── Indigo (chatbot, welcome) ──
  static const indigo = LinearGradient(
    begin: Alignment.topLeft, end: Alignment.bottomRight,
    colors: [AppColors.indigoStart, AppColors.indigoEnd],
  );

  static const indigoPurple = LinearGradient(
    begin: Alignment.topLeft, end: Alignment.bottomRight,
    colors: [AppColors.indigoStart, AppColors.indigoEnd, AppColors.purpleEnd],
  );

  // ── Button gradients ──
  static const blueIndigo = LinearGradient(
    colors: [Color(0xFF2563EB), Color(0xFF4F46E5)],
  );

  static const purpleIndigo = LinearGradient(
    colors: [Color(0xFF9333EA), Color(0xFF4F46E5)],
  );

  static const orangeAmber = LinearGradient(
    colors: [Color(0xFFEA580C), Color(0xFFD97706)],
  );

  static const yellowOrange = LinearGradient(
    colors: [Color(0xFFCA8A04), Color(0xFFEA580C)],
  );

  static const greenEmerald = LinearGradient(
    colors: [Color(0xFF16A34A), Color(0xFF059669)],
  );

  // ── Stat card top-bar gradients ──
  static const statBlue = LinearGradient(
    colors: [Color(0xFF448AFF), Color(0xFF7C4DFF)],
  );

  static const statUp = LinearGradient(
    colors: [Color(0xFF00E676), Color(0xFF00C853)],
  );

  static const statDn = LinearGradient(
    colors: [Color(0xFFFF5252), Color(0xFFD50000)],
  );

  static const statAccent = LinearGradient(
    colors: [Color(0xFF7C4DFF), Color(0xFF448AFF)],
  );

  static const statGold = LinearGradient(
    colors: [Color(0xFFFFD740), Color(0xFFFFAB00)],
  );

  // ── Sidebar / Header backgrounds ──
  static LinearGradient sidebarDark() => const LinearGradient(
    begin: Alignment.topCenter, end: Alignment.bottomCenter,
    colors: [Color(0xFF0B1018), Color(0xFF0D1420)],
  );

  static LinearGradient sidebarLight() => const LinearGradient(
    begin: Alignment.topCenter, end: Alignment.bottomCenter,
    colors: [Color(0xFFFFFFFF), Color(0xFFF3F5F8)],
  );

  static LinearGradient headerDark() => const LinearGradient(
    colors: [Color(0xF20B1018), Color(0xF210161F)],
  );

  static LinearGradient headerLight() => const LinearGradient(
    colors: [Color(0xF5FFFFFF), Color(0xF5F5F7FA)],
  );

  // ── Card backgrounds ──
  static LinearGradient cardDark() => const LinearGradient(
    begin: Alignment(-0.3, -1), end: Alignment(0.3, 1),
    colors: [Color(0xE610161F), Color(0x99171F2C)],
  );

  static LinearGradient cardLight() => const LinearGradient(
    begin: Alignment(-0.3, -1), end: Alignment(0.3, 1),
    colors: [Color(0xFFFFFFFF), Color(0xFFF5F7FA)],
  );

  // ── Welcome screen background ──
  static const welcomeBg = LinearGradient(
    begin: Alignment.topLeft, end: Alignment.bottomRight,
    colors: [Color(0xFF0A0E1A), Color(0xFF0F1729), Color(0xFF111B2E), Color(0xFF0A0E1A)],
    stops: [0.0, 0.3, 0.6, 1.0],
  );

  // ── Report header ──
  static const reportHeader = LinearGradient(
    begin: Alignment.topLeft, end: Alignment.bottomRight,
    colors: [Color(0xFF0A1020), Color(0xFF141D35), Color(0xFF0A1020)],
    stops: [0.0, 0.5, 1.0],
  );
}

/// Shadow definitions matching globals.css
class AppShadows {
  AppShadows._();

  static const sm = [BoxShadow(offset: Offset(0, 1), blurRadius: 3, color: Color(0x66000000))];
  static const smLight = [BoxShadow(offset: Offset(0, 1), blurRadius: 4, color: Color(0x14000000))];

  static const md = [BoxShadow(offset: Offset(0, 4), blurRadius: 12, color: Color(0x80000000))];
  static const mdLight = [BoxShadow(offset: Offset(0, 4), blurRadius: 16, color: Color(0x1A000000))];

  static const lg = [BoxShadow(offset: Offset(0, 8), blurRadius: 30, color: Color(0x99000000))];
  static const lgLight = [BoxShadow(offset: Offset(0, 8), blurRadius: 30, color: Color(0x1F000000))];

  static List<BoxShadow> glow(Color color, {double radius = 15}) => [
    BoxShadow(color: color.withValues(alpha: 0.4), blurRadius: radius),
  ];

  static List<BoxShadow> brandGlow({double radius = 15}) => [
    BoxShadow(color: const Color(0xFF448AFF).withValues(alpha: 0.4), blurRadius: radius),
  ];
}
