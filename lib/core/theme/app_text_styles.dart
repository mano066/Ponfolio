import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Typography system — Inter + JetBrains Mono matching the web app's
/// Inter (--font-inter) and Geist Mono (--font-geist-mono).
class AppTextStyles {
  AppTextStyles._();

  // ── Base font families ──
  static String get _inter => GoogleFonts.inter().fontFamily!;
  static String get _mono => GoogleFonts.jetBrainsMono().fontFamily!;

  // ── Heading styles ──
  static TextStyle heading1(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 28, fontWeight: FontWeight.w700,
    color: color, letterSpacing: -0.5, height: 1.3,
  );

  static TextStyle heading2(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 17, fontWeight: FontWeight.w700,
    color: color, height: 1.3,
  );

  static TextStyle heading3(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 15, fontWeight: FontWeight.w700,
    color: color, letterSpacing: -0.01, height: 1.3,
  );

  // ── Body styles ──
  static TextStyle body(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 13, fontWeight: FontWeight.w500,
    color: color, height: 1.5,
  );

  static TextStyle bodySmall(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 12, fontWeight: FontWeight.w500,
    color: color, height: 1.5,
  );

  static TextStyle bodyBold(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 13, fontWeight: FontWeight.w700,
    color: color, height: 1.5,
  );

  // ── Label / Caption styles (uppercase tracking) ──
  static TextStyle label(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 11, fontWeight: FontWeight.w700,
    color: color, letterSpacing: 0.04 * 11, // 0.04em
    height: 1.3,
  );

  static TextStyle labelXs(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 10, fontWeight: FontWeight.w700,
    color: color, letterSpacing: 0.08 * 10, // wider tracking
    height: 1.3,
  );

  static TextStyle caption(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 10, fontWeight: FontWeight.w600,
    color: color, height: 1.4,
  );

  static TextStyle captionXs(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 9, fontWeight: FontWeight.w500,
    color: color, height: 1.3,
  );

  // ── Stat / Number styles ──
  static TextStyle stat2xl(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 24, fontWeight: FontWeight.w700,
    color: color, height: 1.2,
  );

  static TextStyle statXl(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 20, fontWeight: FontWeight.w700,
    color: color, height: 1.2,
  );

  static TextStyle statLg(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 18, fontWeight: FontWeight.w700,
    color: color, height: 1.2,
  );

  // ── Mono / Table styles ──
  static TextStyle mono(Color color) => TextStyle(
    fontFamily: _mono, fontSize: 13, fontWeight: FontWeight.w500,
    color: color, height: 1.4,
  );

  static TextStyle monoBold(Color color) => TextStyle(
    fontFamily: _mono, fontSize: 13, fontWeight: FontWeight.w700,
    color: color, height: 1.4,
  );

  static TextStyle monoSmall(Color color) => TextStyle(
    fontFamily: _mono, fontSize: 12, fontWeight: FontWeight.w500,
    color: color, height: 1.4,
  );

  static TextStyle monoXs(Color color) => TextStyle(
    fontFamily: _mono, fontSize: 11, fontWeight: FontWeight.w500,
    color: color, height: 1.4,
  );

  // ── Sidebar nav ──
  static TextStyle sidebarNav(Color color, {bool active = false}) => TextStyle(
    fontFamily: _inter, fontSize: 13,
    fontWeight: active ? FontWeight.w600 : FontWeight.w500,
    color: color, height: 1.3,
  );

  static TextStyle sidebarBrand(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 15, fontWeight: FontWeight.w700,
    color: color, letterSpacing: -0.02, height: 1.2,
  );

  // ── Badge ──
  static TextStyle badge(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 11, fontWeight: FontWeight.w700,
    color: color, letterSpacing: 0.02 * 11, height: 1.2,
  );

  // ── Header button ──
  static TextStyle headerBtn(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 12, fontWeight: FontWeight.w500,
    color: color, height: 1.3,
  );

  // ── Section header ──
  static TextStyle sectionTitle(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 13, fontWeight: FontWeight.w700,
    color: color, letterSpacing: -0.01 * 13, height: 1.3,
  );

  static TextStyle sectionSubtitle(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 11, fontWeight: FontWeight.w400,
    color: color, height: 1.3,
  );

  // ── Table header ──
  static TextStyle tableHeader(Color color) => TextStyle(
    fontFamily: _inter, fontSize: 11, fontWeight: FontWeight.w700,
    color: color, letterSpacing: 0.04 * 11, height: 1.3,
  );
}
