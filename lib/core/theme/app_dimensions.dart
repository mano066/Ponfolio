/// Design system dimensions — exact match to globals.css tokens
class AppDimensions {
  AppDimensions._();

  // Layout
  static const double sidebarWidth = 220.0;
  static const double sidebarCollapsedWidth = 64.0;
  static const double headerHeight = 56.0;

  // Border radius
  static const double radius = 12.0;
  static const double radiusSm = 8.0;
  static const double radiusXs = 6.0;
  static const double radiusLg = 16.0;
  static const double radiusXl = 20.0;
  static const double radiusFull = 999.0;

  // Spacing (matches Tailwind-style usage)
  static const double space1 = 4.0;
  static const double space2 = 8.0;
  static const double space3 = 12.0;
  static const double space4 = 16.0;
  static const double space5 = 20.0;
  static const double space6 = 24.0;
  static const double space8 = 32.0;
  static const double space10 = 40.0;
  static const double space12 = 48.0;

  // Sidebar nav item
  static const double sidebarNavPaddingH = 14.0;
  static const double sidebarNavPaddingV = 9.0;
  static const double sidebarNavMargin = 8.0;
  static const double sidebarNavGap = 10.0;
  static const double sidebarNavIconSize = 20.0;
  static const double sidebarNavActiveBarWidth = 3.0;
  static const double sidebarNavActiveBarHeight = 20.0;

  // Header bar
  static const double headerPaddingH = 20.0;
  static const double headerGap = 12.0;

  // Section header
  static const double sectionHeaderPaddingH = 16.0;
  static const double sectionHeaderPaddingV = 12.0;
  static const double sectionHeaderIconSize = 28.0;
  static const double sectionHeaderGap = 10.0;

  // Stat card
  static const double statCardPaddingH = 20.0;
  static const double statCardPaddingV = 18.0;

  // Table
  static const double tableCellPaddingH = 14.0;
  static const double tableCellPaddingV = 11.0;
  static const double tableMinWidth = 1200.0;

  // Badge
  static const double badgePaddingH = 10.0;
  static const double badgePaddingV = 4.0;
  static const double badgeRadius = 20.0;

  // Chat
  static const double chatFabSize = 56.0;
  static const double chatWindowWidth = 420.0;
  static const double chatWindowHeight = 580.0;

  // Animation durations (ms)
  static const Duration animFast = Duration(milliseconds: 150);
  static const Duration animNormal = Duration(milliseconds: 300);
  static const Duration animSlow = Duration(milliseconds: 500);
  static const Duration animCounter = Duration(milliseconds: 800);
  static const Duration animPageEntrance = Duration(milliseconds: 450);
  static const Duration animStagger = Duration(milliseconds: 50);
  static const Duration animChartDraw = Duration(milliseconds: 1200);
}
