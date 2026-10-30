import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

import 'package:aiei_wealth/data/research_library.dart';

/// Keeps the reports the user adds, and turns any report into a real file on
/// disk so it can be opened offline or saved somewhere else.
///
/// Layout under the app-support folder:
///   research/library.json      the user's own entries, plus ids they removed
///   research/files/            copies of files the user added
///   research/bundled/          built-in reports unpacked from the app assets
class ResearchStore {
  /// Resolves the root folder. Injectable so tests can use a temp directory.
  final Future<Directory> Function() _root;
  final AssetBundle _bundle;

  ResearchStore({Future<Directory> Function()? root, AssetBundle? bundle})
      : _root = root ?? _defaultRoot,
        _bundle = bundle ?? rootBundle;

  static Future<Directory> _defaultRoot() async =>
      Directory('${(await getApplicationSupportDirectory()).path}${Platform.pathSeparator}research');

  static const allowedExtensions = ['html', 'htm', 'pdf'];

  Future<Directory> _sub(String name) async {
    final d = Directory('${(await _root()).path}${Platform.pathSeparator}$name');
    if (!await d.exists()) await d.create(recursive: true);
    return d;
  }

  Future<File> _indexFile() async {
    final root = await _root();
    if (!await root.exists()) await root.create(recursive: true);
    return File('${root.path}${Platform.pathSeparator}library.json');
  }

  /// Reads the index: the user's entries plus the ids they removed (kept so a
  /// sync can't bring a removed report back from Drive). Accepts the original
  /// plain-list format too. A missing or unreadable index is an empty library
  /// rather than an error, so one bad file can't hide the built-ins.
  Future<({List<ResearchDoc> docs, Set<String> removed})> _loadIndex() async {
    final f = await _indexFile();
    if (!await f.exists()) return (docs: <ResearchDoc>[], removed: <String>{});
    try {
      final raw = jsonDecode(await f.readAsString());
      final list = raw is List ? raw : (raw as Map)['docs'] as List? ?? const [];
      final removed = raw is Map ? {...((raw['removed'] as List?) ?? const []).map((e) => '$e')} : <String>{};
      final docs = list.whereType<Map>().map((m) => ResearchDoc.fromJson(Map<String, dynamic>.from(m))).toList();
      docs.sort((a, b) => b.updated.compareTo(a.updated));
      return (docs: docs, removed: removed);
    } catch (_) {
      return (docs: <ResearchDoc>[], removed: <String>{});
    }
  }

  /// The user's own entries, newest first.
  Future<List<ResearchDoc>> loadUserDocs() async => (await _loadIndex()).docs;

  Future<void> _save(List<ResearchDoc> docs, [Set<String>? removed]) async {
    final f = await _indexFile();
    removed ??= (await _loadIndex()).removed;
    await f.writeAsString(const JsonEncoder.withIndent('  ').convert({
      'docs': docs.map((d) => d.toJson()).toList(),
      'removed': removed.toList()..sort(),
    }));
  }

  String _newId() => 'user-${DateTime.now().microsecondsSinceEpoch}';

  /// Adds a report from a file on disk. The file is copied into the app, so the
  /// report keeps working if the original is moved or deleted.
  Future<ResearchDoc> addFile({
    required String sourcePath,
    required String title,
    required ResearchKind kind,
    String summary = '',
    String? url,
  }) async {
    final src = File(sourcePath);
    if (!await src.exists()) throw FileSystemException('File not found', sourcePath);
    final ext = sourcePath.split('.').last.toLowerCase();
    if (!allowedExtensions.contains(ext)) {
      throw ArgumentError('Only HTML and PDF reports can be added (got .$ext).');
    }
    final id = _newId();
    final dest = File('${(await _sub('files')).path}${Platform.pathSeparator}$id.$ext');
    await src.copy(dest.path);
    final doc = ResearchDoc(
      id: id,
      title: title.trim().isEmpty ? _stem(sourcePath) : title.trim(),
      summary: summary.trim(),
      kind: kind,
      updated: DateTime.now(),
      url: _cleanUrl(url),
      filePath: dest.path,
      builtIn: false,
    );
    await _save([doc, ...await loadUserDocs()]);
    return doc;
  }

  /// Adds a report that lives only online, such as a claude.ai artifact link.
  Future<ResearchDoc> addLink({
    required String url,
    required String title,
    required ResearchKind kind,
    String summary = '',
  }) async {
    final clean = _cleanUrl(url);
    if (clean == null) throw ArgumentError('Enter a full web address starting with https://');
    final doc = ResearchDoc(
      id: _newId(),
      title: title.trim().isEmpty ? clean : title.trim(),
      summary: summary.trim(),
      kind: kind,
      updated: DateTime.now(),
      url: clean,
      builtIn: false,
    );
    await _save([doc, ...await loadUserDocs()]);
    return doc;
  }

  /// Removes a user entry and the app's copy of its file. Built-ins can't be removed.
  Future<void> remove(ResearchDoc doc) async {
    if (doc.builtIn) return;
    final idx = await _loadIndex();
    await _save(idx.docs.where((d) => d.id != doc.id).toList(), {...idx.removed, doc.id});
    if (doc.filePath != null) {
      final f = File(doc.filePath!);
      if (await f.exists()) await f.delete();
    }
  }

  /// Two-way sync with Google Drive through [remote]. Drive and this device are
  /// merged, never overwritten: reports on either side are kept, and a report
  /// removed on either side stays removed. Files are only moved when the other
  /// side lacks them.
  Future<ResearchSyncResult> sync(ResearchRemote remote) async {
    final pulled = await remote.pull();
    if (pulled == null) return const ResearchSyncResult.signedOut();
    final local = await _loadIndex();
    final removed = {...local.removed, ...pulled.removed};
    final byId = {for (final d in local.docs) d.id: d};
    var downloaded = 0;
    for (final r in pulled.docs) {
      // Ids become file names, so only accept the app's own id format.
      if (!RegExp(r'^user-\d+$').hasMatch(r.doc.id)) continue;
      if (removed.contains(r.doc.id) || byId.containsKey(r.doc.id)) continue;
      var doc = r.doc;
      if (r.driveFile != null && pulled.files.contains(r.driveFile)) {
        final ext = r.driveFile!.split('.').last;
        final dest = File('${(await _sub('files')).path}${Platform.pathSeparator}${doc.id}.$ext');
        await dest.writeAsBytes(await remote.fetchFile(r.driveFile!), flush: true);
        doc = doc.withFilePath(dest.path);
      }
      byId[doc.id] = doc;
      downloaded++;
    }
    for (final id in removed) {
      final gone = byId.remove(id);
      if (gone?.filePath != null) {
        final f = File(gone!.filePath!);
        if (await f.exists()) await f.delete();
      }
    }
    final merged = byId.values.toList()..sort((a, b) => b.updated.compareTo(a.updated));
    await _save(merged, removed);

    final toUpload = <String, List<int>>{};
    for (final d in merged) {
      final name = d.driveFileName;
      if (name == null || pulled.files.contains(name)) continue;
      final f = File(d.filePath!);
      if (await f.exists()) toUpload[name] = await f.readAsBytes();
    }
    await remote.push({
      'docs': merged.map((d) => d.toSyncJson()).toList(),
      'removed': removed.toList()..sort(),
    }, toUpload);
    return ResearchSyncResult(downloaded: downloaded, uploaded: toUpload.length, total: merged.length);
  }

  /// A file on disk for this report, unpacking a built-in from the app bundle
  /// (with any PDFs it links to) the first time. Null for a link-only report.
  Future<File?> localFile(ResearchDoc doc) async {
    if (doc.filePath != null) {
      final f = File(doc.filePath!);
      return await f.exists() ? f : null;
    }
    if (doc.asset == null) return null;
    final dir = await _sub('bundled');
    final base = doc.asset!.substring(0, doc.asset!.lastIndexOf('/') + 1);
    for (final rel in [doc.asset!.substring(base.length), ...doc.extraAssets]) {
      final out = File('${dir.path}${Platform.pathSeparator}${rel.replaceAll('/', Platform.pathSeparator)}');
      final data = await _bundle.load('$base$rel');
      final bytes = data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
      // Rewrite on every open: an app update may ship a newer copy of the report.
      if (!await out.parent.exists()) await out.parent.create(recursive: true);
      await out.writeAsBytes(bytes, flush: true);
    }
    return File('${dir.path}${Platform.pathSeparator}${doc.asset!.substring(base.length)}');
  }

  /// Copies a report to [destination]. For a report with linked files (the
  /// rebalancing PDFs) [destination] is a folder and the whole set is copied,
  /// so the links inside the page still work.
  Future<String> export(ResearchDoc doc, String destination) async {
    final src = await localFile(doc);
    if (src == null) throw StateError('This report has no local copy to download.');
    if (doc.extraAssets.isEmpty) {
      await src.copy(destination);
      return destination;
    }
    final folder = Directory('$destination${Platform.pathSeparator}${doc.id}');
    await folder.create(recursive: true);
    final name = src.uri.pathSegments.last;
    await src.copy('${folder.path}${Platform.pathSeparator}$name');
    for (final rel in doc.extraAssets) {
      final from = File('${src.parent.path}${Platform.pathSeparator}${rel.replaceAll('/', Platform.pathSeparator)}');
      final to = File('${folder.path}${Platform.pathSeparator}${rel.replaceAll('/', Platform.pathSeparator)}');
      await to.parent.create(recursive: true);
      await from.copy(to.path);
    }
    return folder.path;
  }

  /// Suggested file name when saving a copy, keeping the report's own extension.
  static String suggestedName(ResearchDoc doc, File local) {
    final ext = local.path.split('.').last;
    final slug = doc.title.replaceAll(RegExp(r'[^A-Za-z0-9]+'), '_').replaceAll(RegExp(r'^_|_$'), '');
    return '${slug.isEmpty ? doc.id : slug}.$ext';
  }

  static String _stem(String path) {
    final name = path.split(RegExp(r'[\\/]')).last;
    final dot = name.lastIndexOf('.');
    return dot > 0 ? name.substring(0, dot) : name;
  }

  static String? _cleanUrl(String? url) {
    final u = url?.trim() ?? '';
    if (u.isEmpty) return null;
    final parsed = Uri.tryParse(u);
    if (parsed == null || !(parsed.scheme == 'https' || parsed.scheme == 'http') || parsed.host.isEmpty) return null;
    return u;
  }
}

/// What Drive holds for the research library.
class RemoteLibrary {
  final List<({ResearchDoc doc, String? driveFile})> docs;
  final Set<String> removed;

  /// Names of report files already on Drive.
  final Set<String> files;
  const RemoteLibrary({required this.docs, required this.removed, required this.files});
}

/// Where [ResearchStore.sync] sends and fetches the library. Abstract so tests
/// can stand in for Google Drive.
abstract class ResearchRemote {
  /// Null when the user isn't signed in to Google.
  Future<RemoteLibrary?> pull();
  Future<List<int>> fetchFile(String name);
  Future<void> push(Map<String, dynamic> library, Map<String, List<int>> files);
}

class ResearchSyncResult {
  final bool signedIn;
  final int downloaded, uploaded, total;
  const ResearchSyncResult({required this.downloaded, required this.uploaded, required this.total})
      : signedIn = true;
  const ResearchSyncResult.signedOut()
      : signedIn = false,
        downloaded = 0,
        uploaded = 0,
        total = 0;
}

/// Google Drive via the app's backend (`/api/research/drive`), which uses the
/// same signed-in Google account and Drive app folder as the other backups.
class BackendResearchRemote implements ResearchRemote {
  final Dio dio;
  BackendResearchRemote(this.dio);

  @override
  Future<RemoteLibrary?> pull() async {
    final r = await dio.get('/research/drive');
    final data = Map<String, dynamic>.from(r.data as Map);
    if (data['authenticated'] != true) return null;
    final lib = Map<String, dynamic>.from((data['library'] as Map?) ?? const {});
    return RemoteLibrary(
      docs: [
        for (final m in (lib['docs'] as List? ?? const []).whereType<Map>())
          (doc: ResearchDoc.fromJson(Map<String, dynamic>.from(m)), driveFile: m['drive_file'] as String?),
      ],
      removed: {...(lib['removed'] as List? ?? const []).map((e) => '$e')},
      files: {...(data['files'] as List? ?? const []).map((e) => '$e')},
    );
  }

  @override
  Future<List<int>> fetchFile(String name) async {
    final r = await dio.get('/research/drive/file', queryParameters: {'name': name});
    return base64Decode((r.data as Map)['data'] as String);
  }

  @override
  Future<void> push(Map<String, dynamic> library, Map<String, List<int>> files) async {
    await dio.post('/research/drive', data: {
      'library': library,
      'files': files.map((k, v) => MapEntry(k, base64Encode(v))),
    });
  }
}
