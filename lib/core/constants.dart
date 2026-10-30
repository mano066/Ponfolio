/// API and app constants
class AppConstants {
  AppConstants._();

  static const String apiBase = 'http://localhost:8182/api';
  static const String appName = 'Ponfolio';
  static const String appTagline = 'Institutional AI-Powered Stock & Mutual Fund Terminal';
  static const String version = '1.4.8';

  // Polling intervals (milliseconds)
  static const int priceRefreshMs = 5000;    // Live prices every 5s
  static const int signalPollMs = 10000;     // AI signals every 10s
  static const int niftyPollMs = 30000;      // Nifty 50 every 30s
  static const int kitePollMs = 15000;       // Kite status every 15s
  static const int advisorPollMs = 4000;     // Advisor poll every 4s

  // API timeouts
  static const int connectTimeoutMs = 15000;
  static const int receiveTimeoutMs = 600000;  // 10 min — Kite portfolio sync can be slow
}

/// Tab identifiers matching the web app's tab system
/// MAIN: Dashboard, Equities, Mutual Funds, MF Screener, SIP Simulator
/// INTELLIGENCE: Analytics, AI Triggers, Strategies, Deep Analysis, Reports, Research
/// SYSTEM: Settings
enum AppTab {
  // ── MAIN ──
  dashboard('Dashboard'),
  equities('Equities'),
  mutualFunds('Mutual Funds'),
  allocation('Allocation'),
  expenses('Expenses'),
  mfScreener('MF Screener'),
  sipSimulator('SIP Simulator'),
  // ── INTELLIGENCE ──
  analytics('Analytics'),
  aiSignals('AI Triggers'),
  strategies('Strategies'),
  deepAnalysis('Deep Analysis'),
  swingTrading('Swing Trading'),
  reports('Reports'),
  research('Research'),
  // ── SYSTEM ──
  settings('Settings'),
  // ── SPECIAL ──
  welcome('Welcome');

  final String label;
  const AppTab(this.label);
}
