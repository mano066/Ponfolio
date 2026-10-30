import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:aiei_wealth/core/theme/app_theme.dart';
import 'package:aiei_wealth/data/research_library.dart';
import 'package:aiei_wealth/presentation/screens/research_screen.dart';
import 'package:aiei_wealth/services/research_store.dart';

/// The research library is where the user keeps reports they paid for in time,
/// so the tests pin what would lose them: a built-in without its offline copy,
/// an added file that does not survive its original being moved, a remove that
/// deletes the wrong thing, and a download that drops the PDFs a page links to.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory tmp;
  late ResearchStore store;

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('research_test_');
    store = ResearchStore(root: () async => Directory('${tmp.path}${Platform.pathSeparator}research'));
  });
  tearDown(() async {
    if (await tmp.exists()) await tmp.delete(recursive: true);
  });

  group('library contents', () {
    test('every public built-in has a claude.ai link and a bundled offline copy', () async {
      expect(researchLibrary, hasLength(8));
      expect(researchLibrary.map((d) => d.id).toSet().length, researchLibrary.length);
      for (final d in researchLibrary) {
        expect(Uri.parse(d.url!).host, 'claude.ai', reason: d.title);
        expect(d.asset, isNotNull, reason: d.title);
        final data = await rootBundle.load(d.asset!);
        expect(data.lengthInBytes, greaterThan(1000), reason: d.asset);
        for (final extra in d.extraAssets) {
          final base = d.asset!.substring(0, d.asset!.lastIndexOf('/') + 1);
          expect((await rootBundle.load('$base$extra')).lengthInBytes, greaterThan(1000), reason: extra);
        }
      }
    });

    test('private built-ins live in assets/private, have no online link and keep docs/ sibling-relative', () {
      expect(privateResearchLibrary.map((d) => d.id),
          ['portfolio-deep-dive', 'portfolio-deep-dive-static', 'rebalancing-strategy-lab', 'cross-sector-stock-screen']);
      for (final d in privateResearchLibrary) {
        expect(d.asset, startsWith('assets/private/'), reason: d.id);
        expect(d.asset!.split('/'), hasLength(3), reason: 'flat folder: asset dirs are not recursive');
        expect(d.url, isNull, reason: d.id);
        for (final f in requiredAssets(d).skip(1)) {
          expect(f, startsWith('assets/private/docs/'), reason: f);
        }
      }
      final ids = {...researchLibrary.map((d) => d.id), ...privateResearchLibrary.map((d) => d.id)};
      expect(ids, hasLength(12), reason: 'ids stay unique across public and private');
    });

    test('a private report is listed only when its page and every linked file are bundled', () {
      expect(researchLibraryFor({}).map((d) => d.id), researchLibrary.map((d) => d.id), reason: 'public clone');
      final all = {for (final d in privateResearchLibrary) ...requiredAssets(d)};
      expect(researchLibraryFor(all), hasLength(12));
      final rebal = privateResearchLibrary.firstWhere((d) => d.id == 'rebalancing-strategy-lab');
      final missingPdf = all.difference({requiredAssets(rebal).last});
      final shown = researchLibraryFor(missingPdf).map((d) => d.id);
      expect(shown, isNot(contains('rebalancing-strategy-lab')));
      expect(shown, contains('portfolio-deep-dive'));
    });

    test('loadResearchLibrary reads the asset manifest: empty private folder hides, bundled shows', () async {
      final empty = await loadResearchLibrary(bundle: _MapBundle({'assets/private/README.md': 'x'}));
      expect(empty.map((d) => d.id), researchLibrary.map((d) => d.id));
      final page = privateResearchLibrary.firstWhere((d) => d.id == 'cross-sector-stock-screen');
      final one = await loadResearchLibrary(bundle: _MapBundle({page.asset!: '<html></html>'}));
      expect(one, hasLength(researchLibrary.length + 1));
      expect(one.last.id, page.id);
      // The real bundle: whatever it holds, every listed private page must load.
      for (final d in await loadResearchLibrary()) {
        for (final f in requiredAssets(d)) {
          expect((await rootBundle.load(f)).lengthInBytes, greaterThan(0), reason: f);
        }
      }
    });
  });

  group('ResearchStore', () {
    test('an added file is copied in, so it survives the original being deleted', () async {
      final src = File('${tmp.path}${Platform.pathSeparator}my report.html')..writeAsStringSync('<h1>hi</h1>');
      final doc = await store.addFile(sourcePath: src.path, title: '', kind: ResearchKind.etf);
      expect(doc.title, 'my report', reason: 'title falls back to the file name');
      await src.delete();
      final f = await store.localFile(doc);
      expect(f, isNotNull);
      expect(await f!.readAsString(), '<h1>hi</h1>');
      expect((await store.loadUserDocs()).single.id, doc.id, reason: 'persisted to library.json');
    });

    test('rejects file types it cannot open, and links that are not web addresses', () async {
      final bad = File('${tmp.path}${Platform.pathSeparator}notes.docx')..writeAsStringSync('x');
      expect(() => store.addFile(sourcePath: bad.path, title: 't', kind: ResearchKind.etf), throwsArgumentError);
      expect(() => store.addLink(url: 'not a url', title: 't', kind: ResearchKind.etf), throwsArgumentError);
      expect(await store.loadUserDocs(), isEmpty);
    });

    test('remove deletes only that entry and its copied file', () async {
      final a = File('${tmp.path}${Platform.pathSeparator}a.pdf')..writeAsStringSync('%PDF a');
      final docA = await store.addFile(sourcePath: a.path, title: 'A', kind: ResearchKind.stocks);
      final docB = await store.addLink(url: 'https://claude.ai/artifact/abc', title: 'B', kind: ResearchKind.stocks);
      await store.remove(docA);
      expect(File(docA.filePath!).existsSync(), isFalse);
      expect(a.existsSync(), isTrue, reason: 'the user\'s original file is never touched');
      expect((await store.loadUserDocs()).map((d) => d.id), [docB.id]);
      await store.remove(researchLibrary.first);
      expect(researchLibrary, hasLength(8), reason: 'built-ins cannot be removed');
    });

    test('a built-in unpacks with its linked PDFs, and downloads as a complete folder', () async {
      // A synthetic bundle, so the test runs the same in a public clone that
      // has none of the private pages.
      final rebal = ResearchDoc(
        id: 'sample-lab',
        title: 'Sample lab',
        summary: '',
        kind: ResearchKind.rebalancing,
        updated: DateTime(2026, 1, 1),
        asset: 'assets/private/sample-lab.html',
        extraAssets: const ['docs/one.pdf', 'docs/two.pdf'],
      );
      final store = ResearchStore(
        root: () async => Directory('${tmp.path}${Platform.pathSeparator}research'),
        bundle: _MapBundle({
          'assets/private/sample-lab.html': '<a href="docs/one.pdf">1</a><a href="docs/two.pdf">2</a>',
          'assets/private/docs/one.pdf': '%PDF one',
          'assets/private/docs/two.pdf': '%PDF two',
        }),
      );
      final page = await store.localFile(rebal);
      expect(page!.existsSync(), isTrue);
      for (final rel in rebal.extraAssets) {
        expect(File('${page.parent.path}${Platform.pathSeparator}${rel.replaceAll('/', Platform.pathSeparator)}').existsSync(),
            isTrue, reason: rel);
      }
      final out = Directory('${tmp.path}${Platform.pathSeparator}out')..createSync();
      final saved = await store.export(rebal, out.path);
      expect(File('$saved${Platform.pathSeparator}sample-lab.html').existsSync(), isTrue);
      expect(Directory('$saved${Platform.pathSeparator}docs').listSync(), hasLength(rebal.extraAssets.length));
    });

    test('a link-only report has no local copy to download', () async {
      final doc = await store.addLink(url: 'https://example.com/r', title: 'R', kind: ResearchKind.etf);
      expect(doc.hasLocalCopy, isFalse);
      expect(await store.localFile(doc), isNull);
    });
  });

  group('Google Drive sync', () {
    ResearchStore storeAt(String name) =>
        ResearchStore(root: () async => Directory('${tmp.path}${Platform.pathSeparator}$name'));

    test('two PCs sharing one Drive end up with both sets of reports and files', () async {
      final drive = _FakeDrive();
      final pcA = storeAt('pcA'), pcB = storeAt('pcB');
      final src = File('${tmp.path}${Platform.pathSeparator}a.html')..writeAsStringSync('<p>from A</p>');
      await pcA.addFile(sourcePath: src.path, title: 'From A', kind: ResearchKind.etf);
      await Future<void>.delayed(const Duration(milliseconds: 2));
      await pcB.addLink(url: 'https://claude.ai/artifact/b', title: 'From B', kind: ResearchKind.stocks);

      final a1 = await pcA.sync(drive);
      expect(a1.uploaded, 1, reason: 'A pushes its file');
      final b1 = await pcB.sync(drive);
      expect(b1.downloaded, 1, reason: "B pulls A's report");
      await pcA.sync(drive);

      for (final pc in [pcA, pcB]) {
        final docs = await pc.loadUserDocs();
        expect(docs.map((d) => d.title).toSet(), {'From A', 'From B'});
        final fromA = docs.firstWhere((d) => d.title == 'From A');
        expect(await (await pc.localFile(fromA))!.readAsString(), '<p>from A</p>');
      }
      expect((await pcB.sync(drive)).uploaded, 0, reason: 'files already on Drive are not re-sent');
    });

    test('a report removed on one PC does not come back from Drive', () async {
      final drive = _FakeDrive();
      final pcA = storeAt('pcA'), pcB = storeAt('pcB');
      final doc = await pcA.addLink(url: 'https://claude.ai/artifact/x', title: 'Old', kind: ResearchKind.etf);
      await pcA.sync(drive);
      await pcB.sync(drive);
      expect(await pcB.loadUserDocs(), hasLength(1));

      await pcA.remove(doc);
      await pcA.sync(drive);
      await pcB.sync(drive);
      expect(await pcB.loadUserDocs(), isEmpty, reason: 'the removal reaches the other PC');
      await pcA.sync(drive);
      expect(await pcA.loadUserDocs(), isEmpty, reason: 'and nothing resurrects it');
    });

    test('signed out: sync changes nothing and says so', () async {
      await store.addLink(url: 'https://claude.ai/artifact/y', title: 'Y', kind: ResearchKind.etf);
      final r = await store.sync(_FakeDrive(signedIn: false));
      expect(r.signedIn, isFalse);
      expect(await store.loadUserDocs(), hasLength(1));
    });
  });

  group('ResearchScreen', () {
    // Read the asset manifest once on the real event loop; the screen then
    // picks up the cached list synchronously inside the fake clock.
    late List<ResearchDoc> builtIns;
    setUpAll(() async {
      builtIns = await loadResearchLibrary();
      expect(loadedResearchLibrary, same(builtIns));
    });

    // The screen only reads the user's entries; an in-memory store keeps the
    // widget tests inside the fake clock, where real file IO would never finish.
    Future<void> pump(WidgetTester tester, [List<ResearchDoc> mine = const []]) async {
      tester.view.physicalSize = const Size(1400, 4000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        theme: AppTheme.dark(),
        home: Scaffold(body: ResearchScreen(store: _MemStore(mine), remote: _SignedOutRemote())),
      ));
      await tester.pumpAndSettle();
    }

    testWidgets('lists every built-in report with Open, Online and Download', (tester) async {
      await pump(tester);
      for (final d in builtIns) {
        expect(find.text(d.title), findsOneWidget, reason: d.title);
      }
      expect(find.text('Open'), findsNWidgets(builtIns.length));
      expect(find.byTooltip('Open on claude.ai'), findsNWidgets(researchLibrary.length),
          reason: 'private reports have no online copy');
      expect(find.byTooltip('Download a copy'), findsNWidgets(builtIns.length));
      expect(find.byTooltip('Remove from library'), findsNothing, reason: 'built-ins cannot be removed');
      expect(find.text('Add report'), findsOneWidget);
      expect(find.text('Sync with Google Drive'), findsOneWidget);
      expect(find.textContaining('Sign in with Google'), findsOneWidget, reason: 'says why nothing synced');
    });

    testWidgets('an added link appears with Remove, and the filter still narrows', (tester) async {
      await pump(tester, [
        ResearchDoc(
            id: 'user-1',
            title: 'My own note',
            summary: '',
            kind: ResearchKind.rebalancing,
            updated: DateTime(2026, 9, 24),
            url: 'https://claude.ai/artifact/xyz',
            builtIn: false),
      ]);
      expect(find.text('My own note'), findsOneWidget);
      expect(find.byTooltip('Remove from library'), findsOneWidget);
      await tester.tap(find.textContaining('${ResearchKind.rebalancing.label} ('));
      await tester.pumpAndSettle();
      final n = builtIns.where((d) => d.kind == ResearchKind.rebalancing).length + 1;
      expect(find.text('Open'), findsNWidgets(n));
      expect(find.text(researchLibrary.first.title), findsNothing);
    });
  });
}

class _MemStore extends ResearchStore {
  final List<ResearchDoc> docs;
  _MemStore(this.docs);
  @override
  Future<List<ResearchDoc>> loadUserDocs() => SynchronousFuture(docs);
}

/// Stands in for the backend when a screen test has no Google account.
class _SignedOutRemote implements ResearchRemote {
  @override
  Future<RemoteLibrary?> pull() => SynchronousFuture(null);
  @override
  Future<List<int>> fetchFile(String name) => throw UnimplementedError();
  @override
  Future<void> push(Map<String, dynamic> library, Map<String, List<int>> files) => throw UnimplementedError();
}

/// An in-memory Google Drive app folder, as the backend endpoints expose it.
class _FakeDrive implements ResearchRemote {
  final bool signedIn;
  Map<String, dynamic> index = {'docs': [], 'removed': []};
  final Map<String, List<int>> files = {};
  _FakeDrive({this.signedIn = true});

  @override
  Future<RemoteLibrary?> pull() async {
    if (!signedIn) return null;
    return RemoteLibrary(
      docs: [
        for (final m in (index['docs'] as List).cast<Map<String, dynamic>>())
          (doc: ResearchDoc.fromJson(m), driveFile: m['drive_file'] as String?),
      ],
      removed: {...(index['removed'] as List).map((e) => '$e')},
      files: files.keys.toSet(),
    );
  }

  @override
  Future<List<int>> fetchFile(String name) async => files[name]!;

  @override
  Future<void> push(Map<String, dynamic> library, Map<String, List<int>> upload) async {
    index = jsonDecode(jsonEncode(library)) as Map<String, dynamic>;
    files.addAll(upload);
    final removed = {...(index['removed'] as List).map((e) => '$e')};
    files.removeWhere((name, _) => removed.any((id) => name.startsWith('research_file_$id.')));
  }
}

/// An in-memory asset bundle with a generated asset manifest.
class _MapBundle extends CachingAssetBundle {
  final Map<String, String> files;
  _MapBundle(this.files);

  @override
  Future<ByteData> load(String key) async {
    if (key == 'AssetManifest.bin') {
      return const StandardMessageCodec().encodeMessage(<String, Object>{
        for (final k in files.keys) k: <Object>[<String, Object>{'asset': k}],
      })!;
    }
    final text = files[key];
    if (text == null) throw FlutterError('Unable to load asset: $key');
    return ByteData.sublistView(Uint8List.fromList(utf8.encode(text)));
  }
}
