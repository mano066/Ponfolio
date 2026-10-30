/// The research documents bundled with the app. Each public built-in report is
/// a claude.ai artifact that also ships inside the app as an offline copy
/// (`assets/research/`), so it opens without a network or a claude.ai login and
/// can be downloaded. Owner-only reports live in the git-ignored
/// `assets/private/` folder and are listed only when the build bundles them
/// (see [loadResearchLibrary]). Reports the user adds live in [ResearchStore].
library;

import 'package:flutter/services.dart';

enum ResearchKind {
  etf('ETFs'),
  mutualFunds('Mutual funds'),
  portfolio('My portfolio'),
  rebalancing('Rebalancing'),
  stocks('Stocks & swing trading');

  final String label;
  const ResearchKind(this.label);

  static ResearchKind byName(String? name) =>
      ResearchKind.values.firstWhere((k) => k.name == name, orElse: () => ResearchKind.stocks);
}

class ResearchDoc {
  /// Stable key; built-ins use their asset slug, user entries a timestamp id.
  final String id;
  final String title;
  final String summary;
  final ResearchKind kind;
  final DateTime updated;

  /// Online copy on claude.ai, if there is one.
  final String? url;

  /// Bundled offline page, e.g. `assets/research/india-etf-atlas.html`.
  final String? asset;

  /// Files the bundled page links to, relative to its folder (e.g. `docs/x.pdf`).
  final List<String> extraAssets;

  /// For a report the user added from disk: the app's own copy of that file.
  final String? filePath;

  final bool builtIn;

  const ResearchDoc({
    required this.id,
    required this.title,
    required this.summary,
    required this.kind,
    required this.updated,
    this.url,
    this.asset,
    this.extraAssets = const [],
    this.filePath,
    this.builtIn = true,
  });

  /// Whether a local copy exists that can be opened offline or downloaded.
  bool get hasLocalCopy => asset != null || filePath != null;

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'summary': summary,
        'kind': kind.name,
        'updated': updated.toIso8601String(),
        if (url != null) 'url': url,
        if (filePath != null) 'file_path': filePath,
      };

  /// Name of this report's file on Google Drive (flat app folder), if it has one.
  String? get driveFileName =>
      filePath == null ? null : 'research_file_$id.${filePath!.split('.').last.toLowerCase()}';

  /// The Drive copy of the index carries the Drive file name, never a local path.
  Map<String, dynamic> toSyncJson() => {
        ...toJson()..remove('file_path'),
        if (driveFileName != null) 'drive_file': driveFileName,
      };

  ResearchDoc withFilePath(String? path) => ResearchDoc(
        id: id,
        title: title,
        summary: summary,
        kind: kind,
        updated: updated,
        url: url,
        filePath: path,
        builtIn: false,
      );

  factory ResearchDoc.fromJson(Map<String, dynamic> j) => ResearchDoc(
        id: j['id'] as String,
        title: j['title'] as String? ?? 'Untitled report',
        summary: j['summary'] as String? ?? '',
        kind: ResearchKind.byName(j['kind'] as String?),
        updated: DateTime.tryParse(j['updated'] as String? ?? '') ?? DateTime.now(),
        url: j['url'] as String?,
        filePath: j['file_path'] as String?,
        builtIn: false,
      );
}

const _dir = 'assets/research';

/// Newest first within each kind; the screen groups by [ResearchKind].
final researchLibrary = <ResearchDoc>[
  ResearchDoc(
    id: 'india-etf-atlas',
    title: 'India ETF Atlas',
    summary:
        'All 351 NSE ETFs: a research engine that compares every relevant ETF for a goal, '
        'a plain-English index dictionary, factor guide, TER, AUM, tracking and liquidity, '
        'and the 2010–2026 annual return quilt.',
    kind: ResearchKind.etf,
    updated: DateTime(2026, 9, 24),
    url: 'https://claude.ai/artifact/5RDyfJEt7idAS5VL91xDpw',
    asset: '$_dir/india-etf-atlas.html',
  ),
  ResearchDoc(
    id: 'itbees-vs-it-stocks',
    title: 'ITBEES vs IT Stocks — Since Listing',
    summary:
        'ITBEES against its 10 Nifty IT holdings, 6 wider IT names and NIFTYBEES, Jun 2020 – Aug 2026. '
        'The ETF returned 15.2% a year against 21.2% for its median holding and lost to the plain Nifty.',
    kind: ResearchKind.etf,
    updated: DateTime(2026, 8, 7),
    url: 'https://claude.ai/artifact/6HvCN4HYk2ARishNy6FzpM',
    asset: '$_dir/itbees-vs-it-stocks.html',
  ),
  ResearchDoc(
    id: 'pharmabees-vs-pharma-stocks',
    title: 'PHARMABEES vs Pharma Stocks — Since Listing',
    summary:
        'PHARMABEES against its 16 pharma holdings, Jul 2021 – Aug 2026. The ETF returned 13.3% a year, '
        'above the median stock, with half the average stock\'s worst fall.',
    kind: ResearchKind.etf,
    updated: DateTime(2026, 8, 7),
    url: 'https://claude.ai/artifact/PUYq2UY2shMghJ8scvnV6M',
    asset: '$_dir/pharmabees-vs-pharma-stocks.html',
  ),
  ResearchDoc(
    id: 'what-this-research-tells-you',
    title: 'What This Research Actually Tells You To Do',
    summary:
        'Fixed ₹10,000-a-month SIP blends of 3–5 fund categories against chasing last year\'s winners, '
        '2013–2026. 1.8 million blends tested on measured NAV data.',
    kind: ResearchKind.mutualFunds,
    updated: DateTime(2026, 8, 7),
    url: 'https://claude.ai/artifact/CjLbxZu8BESTZUyMwYx1RG',
    asset: '$_dir/what-this-research-tells-you.html',
  ),
  ResearchDoc(
    id: 'fund-category-winners-2013-2026',
    title: 'Which Fund Category Won Each Year — 2013 to 2026',
    summary:
        'Twenty SEBI fund categories ranked in every calendar year on the median Direct-plan return, '
        'with the Nifty 50 alongside. No category wins twice in a row on any consistent basis.',
    kind: ResearchKind.mutualFunds,
    updated: DateTime(2026, 8, 7),
    url: 'https://claude.ai/artifact/XWrmQ7L378SRH1PHDziaVx',
    asset: '$_dir/fund-category-winners-2013-2026.html',
  ),
  ResearchDoc(
    id: 'cy2010-mutual-fund-rankings',
    title: 'CY2010 Indian Mutual Fund Rankings',
    summary:
        'Every fund category ranked on what it actually returned in 2010, computed from each fund\'s '
        'own NAV on 31 Dec 2009 and 31 Dec 2010.',
    kind: ResearchKind.mutualFunds,
    updated: DateTime(2026, 8, 7),
    url: 'https://claude.ai/artifact/CJd8grW8zbKpdNZkzMQpje',
    asset: '$_dir/cy2010-mutual-fund-rankings.html',
  ),
  ResearchDoc(
    id: 'train-data-profile',
    title: 'TRAIN data profile — NSE bias-free panel',
    summary: 'Profile of the survivorship-bias-free NSE stock panel used to train the swing model.',
    kind: ResearchKind.stocks,
    updated: DateTime(2026, 7, 29),
    url: 'https://claude.ai/artifact/Kj6HdyWkuynxbQFe97Z3Dy',
    asset: '$_dir/train-data-profile.html',
  ),
  ResearchDoc(
    id: 'v4-v5-rollout-plan',
    title: 'v4 → v5 Rollout Plan',
    summary:
        'NSE swing engine: v5 roughly halves max drawdown (−34% to −19%) at similar return, '
        'so it runs in shadow mode and must pass forward validation before replacing v4.',
    kind: ResearchKind.stocks,
    updated: DateTime(2026, 7, 25),
    url: 'https://claude.ai/artifact/EhvTPThGEnN1UCUDEMEfor',
    asset: '$_dir/v4-v5-rollout-plan.html',
  ),
];

const _privateDir = 'assets/private';

/// Owner-only reports. Their pages sit in the git-ignored `assets/private/`
/// folder (PDFs in `assets/private/docs/`, so the pages' `docs/x.pdf` links
/// still resolve), and they have no public online copy. A public clone bundles
/// none of them, so each is shown only when its files are in the app bundle.
final privateResearchLibrary = <ResearchDoc>[
  ResearchDoc(
    id: 'portfolio-deep-dive',
    title: 'Portfolio Deep-Dive',
    summary: 'Holding-by-holding review of your own portfolio. Interactive version.',
    kind: ResearchKind.portfolio,
    updated: DateTime(2026, 8, 4),
    asset: '$_privateDir/portfolio-deep-dive.html',
  ),
  ResearchDoc(
    id: 'portfolio-deep-dive-static',
    title: 'Portfolio Deep-Dive (static)',
    summary: 'The same portfolio review as a static page, for reading or sharing.',
    kind: ResearchKind.portfolio,
    updated: DateTime(2026, 8, 4),
    asset: '$_privateDir/portfolio-deep-dive-static.html',
  ),
  ResearchDoc(
    id: 'rebalancing-strategy-lab',
    title: 'Rebalancing Strategy Lab',
    summary:
        'Sixteen rebalancing rules (S1–S10, M1–M6) on one ten-stock NSE basket, ₹10,000 a month, 2011–2026. '
        'Reinvesting dividends adds about 1.8 points a year; frequent trimming loses after tax. Includes the full PDF reports.',
    kind: ResearchKind.rebalancing,
    updated: DateTime(2026, 9, 16),
    asset: '$_privateDir/rebalancing-strategy-lab.html',
    extraAssets: [
      'docs/Rebalancing_All_16_Strategies_Parameter_Matrix.pdf',
      'docs/Masters_M1_M6_Ledger_vs_S10.pdf',
      'docs/Rebalancing_Ten_Strategies_Conditions_Explained.pdf',
      'docs/Rebalancing_Strategies_S1_S10_Backtest_2011_2026.pdf',
    ],
  ),
  ResearchDoc(
    id: 'cross-sector-stock-screen',
    title: 'Cross-Sector Stock Screen',
    summary:
        'About 40 Indian stocks across nine sectors screened on valuation and portfolio fit, '
        'sorted into buy now, buy on dip, watchlist and skip. Data as of 25 Aug 2026.',
    kind: ResearchKind.stocks,
    updated: DateTime(2026, 8, 25),
    asset: '$_privateDir/cross-sector-stock-screen.html',
  ),
];

/// Every file a built-in needs from the bundle: its page plus linked files.
List<String> requiredAssets(ResearchDoc d) {
  if (d.asset == null) return const [];
  final base = d.asset!.substring(0, d.asset!.lastIndexOf('/') + 1);
  return [d.asset!, for (final rel in d.extraAssets) '$base$rel'];
}

/// The built-ins to show, given the asset keys in the app bundle: every public
/// report, plus each private one whose page and linked files are all bundled.
List<ResearchDoc> researchLibraryFor(Set<String> bundled) => [
      ...researchLibrary,
      for (final d in privateResearchLibrary)
        if (requiredAssets(d).every(bundled.contains)) d,
    ];

Future<List<ResearchDoc>>? _available;
List<ResearchDoc>? _availableNow;

/// The result of [loadResearchLibrary] once it has completed, else null.
List<ResearchDoc>? get loadedResearchLibrary => _availableNow;

/// The built-ins this build can open, read once from the asset manifest and
/// cached. If the manifest cannot be read, only the public reports are listed.
Future<List<ResearchDoc>> loadResearchLibrary({AssetBundle? bundle}) {
  Future<List<ResearchDoc>> load() async {
    try {
      final manifest = await AssetManifest.loadFromAssetBundle(bundle ?? rootBundle);
      return researchLibraryFor(manifest.listAssets().toSet());
    } catch (_) {
      return List.of(researchLibrary);
    }
  }

  if (bundle != null) return load();
  return _available ??= load().then((docs) => _availableNow = docs);
}
