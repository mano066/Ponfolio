import 'package:flutter/material.dart';

/// Design system color tokens — exact match to globals.css
/// Both dark and light themes are defined here.
class AppColors {
  AppColors._();

  // ══════════════════════════════════════════
  //  DARK THEME (default)
  // ══════════════════════════════════════════
  // Ponfolio brand (matches the product site) — navy dark, teal
  // primary + sky-blue secondary, standard green/red for gains/losses.
  static const darkBg0 = Color(0xFF0B0F17);  // page / scaffold
  static const darkBg1 = Color(0xFF0E1420);  // subtle surface
  static const darkBg2 = Color(0xFF121A29);  // cards
  static const darkBg3 = Color(0xFF1B2536);  // subtle fill / chips
  static const darkBgH = Color(0xFF26324A);  // highest
  static const darkBd = Color(0xFF1F2A3A);   // hairline border
  static const darkBd2 = Color(0xFF33415A);  // stronger border
  static const darkT1 = Color(0xFFE6EBF2);   // primary text
  static const darkT2 = Color(0xFFC4CAD4);   // secondary text
  static const darkT3 = Color(0xFF95A1B3);   // muted text
  static const darkT4 = Color(0xFF6B7688);   // dim text
  static const darkUp = Color(0xFF22C55E);   // gains green
  static const darkUpBg = Color(0x1A22C55E);
  static const darkUpGlow = Color(0x3322C55E);
  static const darkDn = Color(0xFFEF4444);
  static const darkDnBg = Color(0x1AEF4444);
  static const darkDnGlow = Color(0x33EF4444);
  static const darkBlue = Color(0xFF2DD4BF);  // PRIMARY brand = teal
  static const darkBlueBg = Color(0x1A2DD4BF);
  static const darkAccent = Color(0xFF38BDF8); // secondary sky-blue
  static const darkAccentBg = Color(0x1A38BDF8);
  static const darkGold = Color(0xFFF5B642);  // tertiary amber
  static const darkGoldBg = Color(0x1AF5B642);
  static const darkGlass = Color(0xB3121A29); // 70%
  static const darkGlassBorder = Color(0x14FFFFFF); // 8%
  static const darkRowAlt = Color(0x05FFFFFF); // 2%
  static const darkRowBorder = Color(0x0AFFFFFF); // 4%
  static const darkCyan = Color(0xFF22D3EE);  // info accent
  static const darkCyanBg = Color(0x1A22D3EE);

  // ══════════════════════════════════════════
  //  LIGHT THEME
  // ══════════════════════════════════════════
  // Ponfolio brand (light) — soft page, white cards, deeper teal/sky so the
  // brand stays readable on white; standard green/red for gains/losses.
  static const lightBg0 = Color(0xFFF7F9FC);  // page / scaffold (soft grey)
  static const lightBg1 = Color(0xFFFFFFFF);  // subtle surface
  static const lightBg2 = Color(0xFFFFFFFF);  // cards
  static const lightBg3 = Color(0xFFF1F5F9);  // subtle fill / chips
  static const lightBgH = Color(0xFFE7EDF5);  // highest
  static const lightBd = Color(0xFFE3E9F0);   // hairline border
  static const lightBd2 = Color(0xFFD3DBE6);  // stronger border
  static const lightT1 = Color(0xFF0F172A);   // primary text (near-black slate)
  static const lightT2 = Color(0xFF404757);   // secondary text
  static const lightT3 = Color(0xFF64748B);   // muted text
  static const lightT4 = Color(0xFFA6AEBC);   // dim text
  static const lightUp = Color(0xFF16A34A);   // gains green (readable on white)
  static const lightUpBg = Color(0xFFE7F6EC);
  static const lightUpGlow = Color(0x2616A34A);
  static const lightDn = Color(0xFFDC2626);
  static const lightDnBg = Color(0xFFFDECEC);
  static const lightDnGlow = Color(0x26DC2626);
  static const lightBlue = Color(0xFF0D9488);  // PRIMARY brand = teal (600)
  static const lightBlueBg = Color(0xFFDCF5F1);
  static const lightAccent = Color(0xFF0284C7); // secondary sky-blue (600)
  static const lightAccentBg = Color(0xFFE0F2FE);
  static const lightGold = Color(0xFFEA9A15);
  static const lightGoldBg = Color(0xFFFCF1DE);
  static const lightGlass = Color(0xF2FFFFFF); // 95%
  static const lightGlassBorder = Color(0x0F000000); // 6%
  static const lightRowAlt = Color(0x05000000); // 2%
  static const lightRowBorder = Color(0x0A000000); // 4%
  static const lightCyan = Color(0xFF0891B2);  // info accent (light)
  static const lightCyanBg = Color(0xFFE0F5FA);

  // ══════════════════════════════════════════
  //  SHARED / SEMANTIC COLORS
  // ══════════════════════════════════════════
  static const gradientPrimaryStart = Color(0xFF2DD4BF); // teal → sky (brand)
  static const gradientPrimaryEnd = Color(0xFF38BDF8);
  static const gradientUpStart = Color(0xFF00E676);
  static const gradientUpEnd = Color(0xFF00C853);
  static const gradientDnStart = Color(0xFFFF5252);
  static const gradientDnEnd = Color(0xFFD50000);
  static const kiteGreen = Color(0xFF00E676);
  static const indigoStart = Color(0xFF6366F1);
  static const indigoEnd = Color(0xFF8B5CF6);
  static const purpleStart = Color(0xFF8B5CF6);
  static const purpleEnd = Color(0xFFA855F7);
}

/// Theme-aware color set accessed via `Theme.of(context).extension<AppColorScheme>()`
@immutable
class AppColorScheme extends ThemeExtension<AppColorScheme> {
  final Color bg0, bg1, bg2, bg3, bgH;
  final Color bd, bd2;
  final Color t1, t2, t3, t4;
  final Color up, upBg, upGlow;
  final Color dn, dnBg, dnGlow;
  final Color blue, blueBg;
  final Color accent, accentBg;
  final Color gold, goldBg;
  final Color glass, glassBorder;
  final Color rowAlt, rowBorder;
  final Color cyan, cyanBg;

  const AppColorScheme({
    required this.bg0, required this.bg1, required this.bg2,
    required this.bg3, required this.bgH,
    required this.bd, required this.bd2,
    required this.t1, required this.t2, required this.t3, required this.t4,
    required this.up, required this.upBg, required this.upGlow,
    required this.dn, required this.dnBg, required this.dnGlow,
    required this.blue, required this.blueBg,
    required this.accent, required this.accentBg,
    required this.gold, required this.goldBg,
    required this.glass, required this.glassBorder,
    required this.rowAlt, required this.rowBorder,
    required this.cyan, required this.cyanBg,
  });

  static const dark = AppColorScheme(
    bg0: AppColors.darkBg0, bg1: AppColors.darkBg1, bg2: AppColors.darkBg2,
    bg3: AppColors.darkBg3, bgH: AppColors.darkBgH,
    bd: AppColors.darkBd, bd2: AppColors.darkBd2,
    t1: AppColors.darkT1, t2: AppColors.darkT2, t3: AppColors.darkT3, t4: AppColors.darkT4,
    up: AppColors.darkUp, upBg: AppColors.darkUpBg, upGlow: AppColors.darkUpGlow,
    dn: AppColors.darkDn, dnBg: AppColors.darkDnBg, dnGlow: AppColors.darkDnGlow,
    blue: AppColors.darkBlue, blueBg: AppColors.darkBlueBg,
    accent: AppColors.darkAccent, accentBg: AppColors.darkAccentBg,
    gold: AppColors.darkGold, goldBg: AppColors.darkGoldBg,
    glass: AppColors.darkGlass, glassBorder: AppColors.darkGlassBorder,
    rowAlt: AppColors.darkRowAlt, rowBorder: AppColors.darkRowBorder,
    cyan: AppColors.darkCyan, cyanBg: AppColors.darkCyanBg,
  );

  static const light = AppColorScheme(
    bg0: AppColors.lightBg0, bg1: AppColors.lightBg1, bg2: AppColors.lightBg2,
    bg3: AppColors.lightBg3, bgH: AppColors.lightBgH,
    bd: AppColors.lightBd, bd2: AppColors.lightBd2,
    t1: AppColors.lightT1, t2: AppColors.lightT2, t3: AppColors.lightT3, t4: AppColors.lightT4,
    up: AppColors.lightUp, upBg: AppColors.lightUpBg, upGlow: AppColors.lightUpGlow,
    dn: AppColors.lightDn, dnBg: AppColors.lightDnBg, dnGlow: AppColors.lightDnGlow,
    blue: AppColors.lightBlue, blueBg: AppColors.lightBlueBg,
    accent: AppColors.lightAccent, accentBg: AppColors.lightAccentBg,
    gold: AppColors.lightGold, goldBg: AppColors.lightGoldBg,
    glass: AppColors.lightGlass, glassBorder: AppColors.lightGlassBorder,
    rowAlt: AppColors.lightRowAlt, rowBorder: AppColors.lightRowBorder,
    cyan: AppColors.lightCyan, cyanBg: AppColors.lightCyanBg,
  );

  @override
  AppColorScheme copyWith() => this;

  @override
  ThemeExtension<AppColorScheme> lerp(covariant ThemeExtension<AppColorScheme>? other, double t) {
    if (other is! AppColorScheme) return this;
    return AppColorScheme(
      bg0: Color.lerp(bg0, other.bg0, t)!, bg1: Color.lerp(bg1, other.bg1, t)!,
      bg2: Color.lerp(bg2, other.bg2, t)!, bg3: Color.lerp(bg3, other.bg3, t)!,
      bgH: Color.lerp(bgH, other.bgH, t)!,
      bd: Color.lerp(bd, other.bd, t)!, bd2: Color.lerp(bd2, other.bd2, t)!,
      t1: Color.lerp(t1, other.t1, t)!, t2: Color.lerp(t2, other.t2, t)!,
      t3: Color.lerp(t3, other.t3, t)!, t4: Color.lerp(t4, other.t4, t)!,
      up: Color.lerp(up, other.up, t)!, upBg: Color.lerp(upBg, other.upBg, t)!,
      upGlow: Color.lerp(upGlow, other.upGlow, t)!,
      dn: Color.lerp(dn, other.dn, t)!, dnBg: Color.lerp(dnBg, other.dnBg, t)!,
      dnGlow: Color.lerp(dnGlow, other.dnGlow, t)!,
      blue: Color.lerp(blue, other.blue, t)!, blueBg: Color.lerp(blueBg, other.blueBg, t)!,
      accent: Color.lerp(accent, other.accent, t)!, accentBg: Color.lerp(accentBg, other.accentBg, t)!,
      gold: Color.lerp(gold, other.gold, t)!, goldBg: Color.lerp(goldBg, other.goldBg, t)!,
      glass: Color.lerp(glass, other.glass, t)!, glassBorder: Color.lerp(glassBorder, other.glassBorder, t)!,
      rowAlt: Color.lerp(rowAlt, other.rowAlt, t)!, rowBorder: Color.lerp(rowBorder, other.rowBorder, t)!,
      cyan: Color.lerp(cyan, other.cyan, t)!, cyanBg: Color.lerp(cyanBg, other.cyanBg, t)!,
    );
  }
}
