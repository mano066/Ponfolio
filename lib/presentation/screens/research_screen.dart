import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/research_library.dart';
import 'package:aiei_wealth/presentation/widgets/animated_page_wrapper.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/services/api_service.dart';
import 'package:aiei_wealth/services/research_store.dart';

/// Research library — the bundled stock, ETF and mutual-fund reports, plus any
/// the user adds. Owner-only reports appear only when the build bundles them. Built-in reports open from an offline
/// copy bundled with the app; each can also be opened on claude.ai or saved to
/// disk. Added reports are either a file copied into the app or a link.
class ResearchScreen extends StatefulWidget {
  final ResearchStore? store;

  /// Where Google Drive sync goes; defaults to the app backend.
  final ResearchRemote? remote;
  const ResearchScreen({super.key, this.store, this.remote});

  @override
  State<ResearchScreen> createState() => _ResearchScreenState();
}

class _ResearchScreenState extends State<ResearchScreen> {
  late final ResearchStore _store = widget.store ?? ResearchStore();
  late final ResearchRemote _remote = widget.remote ?? BackendResearchRemote(ApiService().dio);
  ResearchKind? _kind;
  List<ResearchDoc> _mine = [];
  List<ResearchDoc> _builtIns = loadedResearchLibrary ?? researchLibrary;
  bool _syncing = false;
  String? _syncStatus;
  bool _syncOk = true;

  static const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  static String _date(DateTime d) => '${d.day} ${_months[d.month - 1]} ${d.year}';

  @override
  void initState() {
    super.initState();
    _reload().then((_) => _sync());
    loadResearchLibrary().then((docs) {
      if (mounted) setState(() => _builtIns = docs);
    });
  }

  /// Merges this device's library with Google Drive. Runs on open and after
  /// every add or remove; the button runs it on demand.
  Future<void> _sync({bool manual = false}) async {
    if (_syncing) return;
    setState(() => _syncing = true);
    String status;
    var ok = true;
    try {
      final r = await _store.sync(_remote);
      if (!r.signedIn) {
        status = 'Sign in with Google (sidebar) to sync your added reports to Drive';
        ok = false;
      } else {
        final t = TimeOfDay.now();
        final hhmm = '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
        final moved = [
          if (r.downloaded > 0) '${r.downloaded} from Drive',
          if (r.uploaded > 0) '${r.uploaded} uploaded',
        ];
        status = 'Synced with Google Drive at $hhmm · ${r.total} added report${r.total == 1 ? '' : 's'}'
            '${moved.isEmpty ? '' : ' · ${moved.join(', ')}'}';
      }
    } catch (e) {
      status = "Couldn't reach Google Drive. Is the app backend running? Your reports are safe on this PC.";
      ok = false;
    }
    await _reload();
    if (!mounted) return;
    setState(() {
      _syncing = false;
      _syncStatus = status;
      _syncOk = ok;
    });
    if (manual) _toast(status);
  }

  Future<void> _reload() async {
    final mine = await _store.loadUserDocs();
    if (mounted) setState(() => _mine = mine);
  }

  List<ResearchDoc> get _all => [..._mine, ..._builtIns];

  IconData _icon(ResearchKind k) => switch (k) {
        ResearchKind.etf => LucideIcons.layers,
        ResearchKind.mutualFunds => LucideIcons.briefcase,
        ResearchKind.portfolio => LucideIcons.pieChart,
        ResearchKind.rebalancing => LucideIcons.scale,
        ResearchKind.stocks => LucideIcons.trendingUp,
      };

  void _toast(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _launch(Uri uri) async {
    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok) _toast('Couldn\'t open ${uri.scheme == 'file' ? 'the file' : 'the browser'}. Location: $uri');
  }

  /// Opens the offline copy when there is one, otherwise the online link.
  Future<void> _open(ResearchDoc d) async {
    try {
      final f = await _store.localFile(d);
      if (f != null) return await _launch(Uri.file(f.path));
      if (d.url != null) return await _launch(Uri.parse(d.url!));
      _toast('This report\'s file is missing. Remove it and add it again.');
    } catch (e) {
      _toast('Couldn\'t open the report: $e');
    }
  }

  Future<void> _download(ResearchDoc d) async {
    try {
      final f = await _store.localFile(d);
      if (f == null) return _toast('This report is a link only, so there is no file to download.');
      String? dest;
      if (d.extraAssets.isEmpty) {
        final name = ResearchStore.suggestedName(d, f);
        final ext = name.split('.').last;
        dest = await FilePicker.saveFile(
          dialogTitle: 'Save a copy of "${d.title}"',
          fileName: name,
          type: FileType.custom,
          allowedExtensions: [ext],
        );
        if (dest != null && !dest.toLowerCase().endsWith('.$ext')) dest = '$dest.$ext';
      } else {
        dest = await FilePicker.getDirectoryPath(dialogTitle: 'Choose a folder for "${d.title}" and its PDFs');
      }
      if (dest == null) return;
      final saved = await _store.export(d, dest);
      _toast('Saved to $saved');
    } catch (e) {
      _toast('Couldn\'t save the report: $e');
    }
  }

  Future<void> _remove(ResearchDoc d) async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Remove this report?'),
        content: Text('"${d.title}" will be removed from the library'
            '${d.filePath != null ? ', along with the app\'s copy of its file. The original file on your PC is not touched' : ''}.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Remove')),
        ],
      ),
    );
    if (yes != true) return;
    await _store.remove(d);
    await _reload();
    _toast('Removed "${d.title}"');
    _sync();
  }

  Future<void> _add() async {
    final added = await showDialog<ResearchDoc>(
      context: context,
      builder: (_) => _AddReportDialog(store: _store),
    );
    if (added == null) return;
    await _reload();
    setState(() => _kind = null);
    _toast('Added "${added.title}"');
    _sync();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final all = _all;
    final kinds = ResearchKind.values.where((k) => all.any((d) => d.kind == k)).toList();
    final shown = kinds.where((k) => _kind == null || _kind == k).toList();
    var i = 0;

    Widget chip(String label, bool on, VoidCallback tap) => Padding(
          padding: const EdgeInsets.only(right: 6),
          child: ChoiceChip(
            label: Text(label, style: AppTextStyles.label(on ? c.t1 : c.t2)),
            selected: on,
            onSelected: (_) => tap(),
            showCheckmark: false,
            selectedColor: c.blueBg,
            backgroundColor: c.bg2,
            side: BorderSide(color: on ? c.blue : c.bd),
          ),
        );

    return ListView(padding: EdgeInsets.zero, children: [
      AnimatedListItem(
        index: i++,
        child: DenseCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            denseTableHeader(context,
                icon: LucideIcons.bookOpen,
                accent: c.blue,
                title: 'Research library',
                subtitle: '${all.length} reports on Indian stocks, ETFs and mutual funds · open offline, online or download',
                trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                  OutlinedButton.icon(
                    onPressed: _syncing ? null : () => _sync(manual: true),
                    icon: _syncing
                        ? const SizedBox(width: 13, height: 13, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(LucideIcons.cloud, size: 14),
                    label: Text(_syncing ? 'Syncing…' : 'Sync with Google Drive'),
                  ),
                  const SizedBox(width: 8),
                  FilledButton.icon(
                    onPressed: _add,
                    icon: const Icon(LucideIcons.upload, size: 14),
                    label: const Text('Add report'),
                  ),
                ])),
            if (_syncStatus != null)
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 0, 14, 10),
                child: Row(children: [
                  Icon(_syncOk ? LucideIcons.cloudCheck : LucideIcons.cloudOff,
                      size: 13, color: _syncOk ? c.up : c.t3),
                  const SizedBox(width: 6),
                  Expanded(child: Text(_syncStatus!, style: AppTextStyles.captionXs(_syncOk ? c.t2 : c.t3))),
                ]),
              ),
            Container(height: 1, color: c.bd),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
              child: Wrap(runSpacing: 6, children: [
                chip('All (${all.length})', _kind == null, () => setState(() => _kind = null)),
                for (final k in kinds)
                  chip('${k.label} (${all.where((d) => d.kind == k).length})', _kind == k,
                      () => setState(() => _kind = k)),
              ]),
            ),
          ]),
        ),
      ),
      const SizedBox(height: 12),
      for (final k in shown) ...[
        AnimatedListItem(
          index: i++,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(4, 4, 4, 8),
            child: Row(children: [
              Icon(_icon(k), size: 13, color: c.t3),
              const SizedBox(width: 6),
              Text(k.label.toUpperCase(), style: AppTextStyles.labelXs(c.t3)),
            ]),
          ),
        ),
        for (final d in all.where((d) => d.kind == k))
          AnimatedListItem(
            index: i++,
            child: Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _DocCard(
                doc: d,
                date: _date(d.updated),
                onOpen: () => _open(d),
                onOnline: d.url != null && d.hasLocalCopy ? () => _launch(Uri.parse(d.url!)) : null,
                onDownload: d.hasLocalCopy ? () => _download(d) : null,
                onRemove: d.builtIn ? null : () => _remove(d),
              ),
            ),
          ),
        const SizedBox(height: 8),
      ],
      Padding(
        padding: const EdgeInsets.fromLTRB(4, 4, 4, 24),
        child: Text(
          'Open uses the copy stored in the app, so it works offline and without a claude.ai login. '
          'Online opens the claude.ai version, which is private to your account. '
          'Reports you add sync to your Google Drive app folder, so they appear on any PC you sign in on; '
          'the built-in reports ship with the app and need no sync. '
          'Figures in each report are as of its own date.',
          style: AppTextStyles.captionXs(c.t3),
        ),
      ),
    ]);
  }
}

class _DocCard extends StatelessWidget {
  final ResearchDoc doc;
  final String date;
  final VoidCallback onOpen;
  final VoidCallback? onOnline, onDownload, onRemove;
  const _DocCard({
    required this.doc,
    required this.date,
    required this.onOpen,
    this.onOnline,
    this.onDownload,
    this.onRemove,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final source = doc.builtIn
        ? (doc.extraAssets.isEmpty ? 'Offline copy' : 'Offline copy + ${doc.extraAssets.length} PDFs')
        : doc.filePath != null
            ? 'Added by you · ${doc.filePath!.split('.').last.toUpperCase()} file'
            : 'Added by you · link';
    Widget icon(IconData i, String tip, VoidCallback? on) => IconButton(
          tooltip: tip,
          onPressed: on,
          icon: Icon(i, size: 15),
          color: c.t2,
          visualDensity: VisualDensity.compact,
        );
    return DenseCard(
      clip: true,
      child: InkWell(
        onTap: onOpen,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(doc.title, style: AppTextStyles.bodyBold(c.t1)),
                if (doc.summary.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(doc.summary, style: AppTextStyles.bodySmall(c.t2)),
                ],
                const SizedBox(height: 6),
                Text('Updated $date · $source', style: AppTextStyles.captionXs(c.t3)),
              ]),
            ),
            const SizedBox(width: 10),
            Row(mainAxisSize: MainAxisSize.min, children: [
              OutlinedButton.icon(
                onPressed: onOpen,
                icon: const Icon(LucideIcons.externalLink, size: 13),
                label: const Text('Open'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: c.blue,
                  side: BorderSide(color: c.blue.withValues(alpha: 0.4)),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                ),
              ),
              const SizedBox(width: 4),
              if (onOnline != null) icon(LucideIcons.globe, 'Open on claude.ai', onOnline),
              if (onDownload != null) icon(LucideIcons.download, 'Download a copy', onDownload),
              if (onRemove != null) icon(LucideIcons.trash2, 'Remove from library', onRemove),
            ]),
          ]),
        ),
      ),
    );
  }
}

/// Add a report from a file on this PC, or as a web link.
class _AddReportDialog extends StatefulWidget {
  final ResearchStore store;
  const _AddReportDialog({required this.store});

  @override
  State<_AddReportDialog> createState() => _AddReportDialogState();
}

class _AddReportDialogState extends State<_AddReportDialog> {
  bool _fromFile = true;
  String? _path;
  final _title = TextEditingController();
  final _summary = TextEditingController();
  final _url = TextEditingController();
  ResearchKind _kind = ResearchKind.stocks;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _title.dispose();
    _summary.dispose();
    _url.dispose();
    super.dispose();
  }

  Future<void> _pick() async {
    final r = await FilePicker.pickFiles(
      dialogTitle: 'Choose a report (HTML or PDF)',
      type: FileType.custom,
      allowedExtensions: ResearchStore.allowedExtensions,
    );
    final p = r?.files.single.path;
    if (p == null) return;
    setState(() {
      _path = p;
      _error = null;
      if (_title.text.trim().isEmpty) {
        final name = p.split(RegExp(r'[\\/]')).last;
        _title.text = name.contains('.') ? name.substring(0, name.lastIndexOf('.')) : name;
      }
    });
  }

  Future<void> _submit() async {
    setState(() => _error = null);
    if (_fromFile && _path == null) return setState(() => _error = 'Choose an HTML or PDF file first.');
    if (!_fromFile && _url.text.trim().isEmpty) return setState(() => _error = 'Paste the report\'s web address.');
    setState(() => _busy = true);
    try {
      final doc = _fromFile
          ? await widget.store.addFile(
              sourcePath: _path!, title: _title.text, kind: _kind, summary: _summary.text, url: _url.text)
          : await widget.store.addLink(url: _url.text, title: _title.text, kind: _kind, summary: _summary.text);
      if (mounted) Navigator.pop(context, doc);
    } catch (e) {
      setState(() {
        _busy = false;
        _error = e is ArgumentError ? '${e.message}' : '$e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return AlertDialog(
      title: const Text('Add a report'),
      content: SizedBox(
        width: 460,
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          SegmentedButton<bool>(
            segments: const [
              ButtonSegment(value: true, icon: Icon(LucideIcons.fileUp, size: 14), label: Text('File from this PC')),
              ButtonSegment(value: false, icon: Icon(LucideIcons.link, size: 14), label: Text('Web link')),
            ],
            selected: {_fromFile},
            onSelectionChanged: (s) => setState(() {
              _fromFile = s.first;
              _error = null;
            }),
          ),
          const SizedBox(height: 14),
          if (_fromFile)
            Row(children: [
              OutlinedButton.icon(
                onPressed: _busy ? null : _pick,
                icon: const Icon(LucideIcons.folderOpen, size: 14),
                label: const Text('Choose file…'),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  _path == null ? 'HTML or PDF' : _path!.split(RegExp(r'[\\/]')).last,
                  style: AppTextStyles.bodySmall(_path == null ? c.t3 : c.t1),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ]),
          const SizedBox(height: 10),
          TextField(
            key: const Key('add-url'),
            controller: _url,
            decoration: InputDecoration(
              labelText: _fromFile ? 'claude.ai link (optional)' : 'Web address',
              hintText: 'https://claude.ai/artifact/…',
            ),
          ),
          TextField(key: const Key('add-title'), controller: _title, decoration: const InputDecoration(labelText: 'Title')),
          TextField(
            controller: _summary,
            decoration: const InputDecoration(labelText: 'One-line summary (optional)'),
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<ResearchKind>(
            initialValue: _kind,
            decoration: const InputDecoration(labelText: 'Category'),
            items: [for (final k in ResearchKind.values) DropdownMenuItem(value: k, child: Text(k.label))],
            onChanged: (k) => setState(() => _kind = k ?? _kind),
          ),
          if (_error != null) ...[
            const SizedBox(height: 10),
            Text(_error!, style: AppTextStyles.bodySmall(c.dn)),
          ],
        ]),
      ),
      actions: [
        TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: _busy ? null : _submit, child: Text(_busy ? 'Adding…' : 'Add to library')),
      ],
    );
  }
}
