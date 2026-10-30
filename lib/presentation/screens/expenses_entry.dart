import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/data/models/expense_config.dart';
import 'package:aiei_wealth/data/models/expense_schema.dart';
import 'package:aiei_wealth/data/models/expense_history.dart';
import 'package:aiei_wealth/providers/expense_provider.dart';
import 'package:aiei_wealth/providers/providers.dart';
import 'package:aiei_wealth/services/expense_import_service.dart';
import 'package:aiei_wealth/services/drive_sync_service.dart';
import 'package:aiei_wealth/presentation/widgets/dense_ui.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/presentation/screens/expenses_common.dart';

/// ─── Raw Dataset Entry ───
/// The single-source-of-truth editor. Enter/edit raw values for every section,
/// add future years/months, new categories/fields, notes, soft-delete wrong
/// rows, then Save Draft / Final Save. Final Save validates, writes to the raw
/// dataset (Hive), appends the change-history log, snapshots a restorable
/// version, and backs up to Google Drive — after which the whole dashboard
/// re-renders from the latest data (all pages watch the same provider).

enum AccountKind {
  local('local', kLocal),
  accountA('account_a', kAccountA),
  accountB('account_b', kAccountB),
  investments('investments', kInv),
  stocks('stocks', kStk);

  final String key;
  final Color accent;
  const AccountKind(this.key, this.accent);

  /// Tab label; the three ledger sections are named by the expense config.
  String get label => switch (this) {
        AccountKind.investments => 'Investment',
        AccountKind.stocks => 'Stock',
        _ => ExpenseConfig.current.section(key),
      };
}

class RawDatasetEntryPage extends ConsumerStatefulWidget {
  const RawDatasetEntryPage({super.key});
  @override
  ConsumerState<RawDatasetEntryPage> createState() =>
      _RawDatasetEntryPageState();
}

class _RawDatasetEntryPageState extends ConsumerState<RawDatasetEntryPage> {
  AccountKind _account = AccountKind.local;

  /// Drive timestamp of the conflict we have already prompted about, so the
  /// dialog is raised once per conflict rather than on every rebuild.
  String? _promptedConflict;

  @override
  Widget build(BuildContext context) {
    final st = ref.watch(expenseStoreProvider);
    final notifier = ref.read(expenseStoreProvider.notifier);

    // A save uploads in the background; when that upload is held back because
    // Drive moved ahead of us, ask the user how to resolve it instead of
    // leaving the data un-synced with only a status pill to show for it.
    ref.listen(expenseStoreProvider, (prev, next) {
      final t = next.driveConflictTime;
      if (t == null) {
        _promptedConflict = null;
      } else if (t != _promptedConflict) {
        _promptedConflict = t;
        _showConflictDialog(notifier, t);
      }
    });
    final year = ref.watch(selectedExpenseYearProvider);
    final month = ref.watch(selectedExpenseMonthProvider);
    final data = notifier.viewFor(year);
    final validation = notifier.validateYear(year);

    return ListView(padding: EdgeInsets.zero, children: [
      _Toolbar(
        years: notifier.years,
        year: year,
        month: month,
        account: _account,
        state: st,
        onYear: (y) => ref.read(selectedExpenseYearProvider.notifier).set(y),
        onMonth: (m) => ref.read(selectedExpenseMonthProvider.notifier).set(m),
        onAccount: (a) => setState(() => _account = a),
        onAddYear: () => notifier.addFutureYear(),
        onImport: () => _import(notifier),
        onSaveDraft: () => _save(notifier, year, draft: true),
        onSaveFinal: () => _save(notifier, year, draft: false),
        onUpload: () => notifier.syncToDrive(),
        onConnectDrive: () => _connectDrive(notifier),
        onVersions: () => _showVersions(notifier),
        onConflict: () => _checkConflict(notifier),
      ),
      const SizedBox(height: 10),
      _ActionBar(account: _account, year: year, month: month, notifier: notifier),
      const SizedBox(height: 10),
      _grid(notifier, year, data),
      const SizedBox(height: 12),
      _BottomPanel(state: st, validation: validation, year: year),
      const SizedBox(height: 24),
    ]);
  }

  Widget _grid(ExpenseStore notifier, int year, Map<String, dynamic> data) {
    switch (_account) {
      case AccountKind.local:
        return localGrid(notifier, year, data);
      case AccountKind.accountA:
        return accountAGrid(notifier, year, data);
      case AccountKind.accountB:
        return accountBGrid(notifier, year, data);
      case AccountKind.investments:
        return investGrid(notifier, year, data);
      case AccountKind.stocks:
        return stockGrid(notifier, year, data);
    }
  }

  Future<void> _save(ExpenseStore notifier, int year,
      {required bool draft}) async {
    final res = await notifier.saveRawEntryAndRefreshDashboard(year, draft: draft);
    if (!mounted) return;
    final c = context.colors;
    if (res.blocked) {
      _snack('Save blocked — ${res.issues.where((i) => i.isError).length} '
          'error(s) must be fixed first.', c.dn);
    } else if (res.recalcFailed) {
      _snack('Raw data was saved, but dashboard recalculation failed.', c.dn);
    } else {
      _snack(
          '${draft ? 'Draft saved' : 'Saved'} & dashboard refreshed · '
          '${res.changeCount} change(s)'
          '${res.issues.isNotEmpty ? ' · ${res.issues.length} warning(s)' : ''}',
          draft ? c.blue : c.up);
    }
  }

  Future<void> _import(ExpenseStore notifier) async {
    final parsed = await expenseImportService.pickAndParse();
    if (parsed == null) {
      if (mounted) _snack('Import cancelled or unreadable.', context.colors.gold);
      return;
    }
    final y = notifier.applyImported(parsed);
    if (mounted) {
      _snack(y > 0 ? 'Imported $y — review and Save to back up.' : 'Import failed.',
          y > 0 ? context.colors.up : context.colors.dn);
    }
  }

  Future<void> _connectDrive(ExpenseStore notifier) async {
    final url = await driveSyncService.googleAuthUrl();
    if (url == null) {
      if (mounted) {
        _snack('Could not start Google sign-in (backend down?).', context.colors.dn);
      }
      return;
    }
    await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    if (!mounted) return;
    _snack('Complete Google sign-in in your browser…', context.colors.blue);
    // Poll for login for ~30s, then sync.
    for (var i = 0; i < 15; i++) {
      await Future.delayed(const Duration(seconds: 2));
      final profile = await driveSyncService.authProfile();
      if (profile != null) {
        if (mounted) {
          _snack('Connected as ${profile['email']} — syncing…', context.colors.up);
        }
        await notifier.syncToDrive();
        return;
      }
    }
    if (mounted) {
      _snack('Sign-in not detected yet — use Sync when ready.', context.colors.gold);
    }
  }

  Future<void> _checkConflict(ExpenseStore notifier) async {
    final driveTime = await notifier.checkDriveConflict();
    if (!mounted) return;
    if (driveTime == null) {
      _snack('No conflict — local and Drive are in sync.', context.colors.up);
      return;
    }
    _promptedConflict = driveTime;
    _showConflictDialog(notifier, driveTime);
  }

  void _showConflictDialog(ExpenseStore notifier, String driveTime) {
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) {
        final c = ctx.colors;
        return AlertDialog(
          backgroundColor: c.bg2,
          title: Text('Drive has a newer version',
              style: AppTextStyles.heading3(c.t1)),
          content: Text(
              'Google Drive was modified at $driveTime, after your last upload, '
              'so it may hold entries this machine has never seen. Your upload '
              'was held back rather than overwrite them.\n\n'
              'Keep Drive is the safe choice — Keep Local discards whatever is '
              'only on Drive.',
              style: AppTextStyles.bodySmall(c.t2)),
          actions: [
            TextButton(
                onPressed: () {
                  Navigator.pop(ctx);
                  // Deliberate overwrite of the newer Drive master.
                  notifier.syncToDrive(force: true);
                  _snack('Keeping local — re-uploading.', c.blue);
                },
                child: const Text('Keep Local')),
            TextButton(
                onPressed: () async {
                  Navigator.pop(ctx);
                  final ok =
                      await notifier.restoreDriveVersion(ExpenseConfig.current.masterFileName);
                  if (mounted) {
                    _snack(ok ? 'Restored Drive version.' : 'Restore failed.',
                        ok ? c.up : c.dn);
                  }
                },
                child: const Text('Keep Drive')),
            TextButton(
                onPressed: () {
                  Navigator.pop(ctx);
                  // Save-both: the upload writes a new timestamped backup
                  // alongside the master, so the Drive copy stays recoverable
                  // from Version history even though the master is replaced.
                  notifier.syncToDrive(force: true);
                  _snack('Saved both — new timestamped backup created.', c.gold);
                },
                child: Text('Save Both', style: TextStyle(color: c.gold))),
          ],
        );
      },
    );
  }

  Future<void> _showVersions(ExpenseStore notifier) async {
    final storage = ref.read(localStorageProvider);
    final local = storage.getExpenseVersionIndex();
    final drive = await driveSyncService.listVersions();
    if (!mounted) return;
    showDialog<void>(
      context: context,
      builder: (ctx) {
        final c = ctx.colors;
        return AlertDialog(
          backgroundColor: c.bg2,
          title: Text('Version History', style: AppTextStyles.heading3(c.t1)),
          content: SizedBox(
            width: 460,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('LOCAL SNAPSHOTS', style: AppTextStyles.labelXs(c.t3)),
                const SizedBox(height: 6),
                if (local.isEmpty)
                  Text('None yet.', style: AppTextStyles.bodySmall(c.t3)),
                ...local.take(8).map((v) => _VersionRow(
                      label: '${v['label'] ?? v['versionId']}',
                      sub: '${v['ts'] ?? ''}',
                      onRestore: () {
                        Navigator.pop(ctx);
                        notifier.restoreLocalVersion('${v['versionId']}');
                        _snack('Restored ${v['versionId']}.', c.up);
                      },
                    )),
                const SizedBox(height: 12),
                Text('GOOGLE DRIVE BACKUPS', style: AppTextStyles.labelXs(c.t3)),
                const SizedBox(height: 6),
                if (drive.isEmpty)
                  Text('None (not signed in or no backups).',
                      style: AppTextStyles.bodySmall(c.t3)),
                ...drive.take(10).map((v) => _VersionRow(
                      label: v.name,
                      sub: v.modifiedTime,
                      onRestore: () async {
                        Navigator.pop(ctx);
                        final ok = await notifier.restoreDriveVersion(v.name);
                        if (mounted) {
                          _snack(ok ? 'Restored ${v.name}.' : 'Restore failed.',
                              ok ? c.up : c.dn);
                        }
                      },
                    )),
              ],
            ),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx), child: const Text('Close')),
          ],
        );
      },
    );
  }

  void _snack(String msg, Color color) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: color.withValues(alpha: 0.9),
      behavior: SnackBarBehavior.floating,
      duration: const Duration(seconds: 3),
    ));
  }
}

class _VersionRow extends StatelessWidget {
  final String label, sub;
  final VoidCallback onRestore;
  const _VersionRow(
      {required this.label, required this.sub, required this.onRestore});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label,
                  style: AppTextStyles.bodySmall(c.t1), maxLines: 1,
                  overflow: TextOverflow.ellipsis),
              Text(sub, style: AppTextStyles.captionXs(c.t3)),
            ],
          ),
        ),
        TextButton(onPressed: onRestore, child: const Text('Restore')),
      ]),
    );
  }
}

// ══════════════════════════════════════════════════════════════════
//  TOOLBAR
// ══════════════════════════════════════════════════════════════════

class _Toolbar extends StatelessWidget {
  final List<int> years;
  final int year;
  final String month;
  final AccountKind account;
  final ExpenseState state;
  final ValueChanged<int> onYear;
  final ValueChanged<String> onMonth;
  final ValueChanged<AccountKind> onAccount;
  final VoidCallback onAddYear, onImport, onSaveDraft, onSaveFinal, onUpload;
  final VoidCallback onConnectDrive, onVersions, onConflict;
  const _Toolbar({
    required this.years,
    required this.year,
    required this.month,
    required this.account,
    required this.state,
    required this.onYear,
    required this.onMonth,
    required this.onAccount,
    required this.onAddYear,
    required this.onImport,
    required this.onSaveDraft,
    required this.onSaveFinal,
    required this.onUpload,
    required this.onConnectDrive,
    required this.onVersions,
    required this.onConflict,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return DenseCard(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(LucideIcons.filePlus2, size: 16, color: c.blue),
            const SizedBox(width: 8),
            Text('Raw Dataset Entry', style: AppTextStyles.heading3(c.t1)),
            const SizedBox(width: 8),
            Text('single source of truth · edits reflect everywhere',
                style: AppTextStyles.captionXs(c.t3)),
            const Spacer(),
            _SyncBadge(
              status: state.syncStatus,
              onConnect: onConnectDrive,
              onSync: onUpload,
              onVersions: onVersions,
              onConflict: onConflict,
            ),
          ]),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              _labeled(context, 'YEAR', Row(mainAxisSize: MainAxisSize.min, children: [
                for (final y in years) ...[
                  _pill(context, '$y', y == year, c.blue, () => onYear(y)),
                  const SizedBox(width: 4),
                ],
                _iconBtn(context, LucideIcons.calendarPlus, 'Add Year', onAddYear),
              ])),
              _labeled(context, 'MONTH', _MonthDropdown(month: month, onMonth: onMonth)),
              _labeled(context, 'ACCOUNT', Row(mainAxisSize: MainAxisSize.min, children: [
                for (final a in AccountKind.values) ...[
                  _pill(context, a.label, a == account, a.accent, () => onAccount(a)),
                  const SizedBox(width: 4),
                ],
              ])),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(spacing: 8, runSpacing: 8, children: [
            HeaderButton(
                icon: Icon(LucideIcons.fileInput, size: 14, color: c.t2),
                text: 'Import Excel',
                onTap: onImport),
            HeaderButton(
                icon: Icon(LucideIcons.save, size: 14, color: c.t2),
                text: 'Save Draft',
                onTap: onSaveDraft),
            HeaderButton(
                icon: const Icon(LucideIcons.checkCheck, size: 14, color: Colors.white),
                text: 'Final Save',
                primary: true,
                onTap: onSaveFinal),
            HeaderButton(
                icon: Icon(LucideIcons.uploadCloud, size: 14, color: c.blue),
                text: 'Upload to Drive',
                onTap: onUpload),
          ]),
        ],
      ),
    );
  }

  Widget _labeled(BuildContext context, String label, Widget child) {
    final c = context.colors;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Text(label, style: AppTextStyles.labelXs(c.t3)),
      const SizedBox(width: 6),
      child,
      const SizedBox(width: 6),
    ]);
  }

  Widget _pill(BuildContext context, String text, bool active, Color color,
      VoidCallback onTap) {
    final c = context.colors;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
          decoration: BoxDecoration(
            color: active ? color.withValues(alpha: 0.14) : c.bg3,
            borderRadius: BorderRadius.circular(7),
            border: Border.all(
                color: active ? color.withValues(alpha: 0.4) : c.bd),
          ),
          child: Text(text,
              style: AppTextStyles.monoBold(active ? color : c.t2)
                  .copyWith(fontSize: 11.5)),
        ),
      ),
    );
  }

  Widget _iconBtn(
      BuildContext context, IconData icon, String tip, VoidCallback onTap) {
    final c = context.colors;
    return Tooltip(
      message: tip,
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        child: GestureDetector(
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(
                color: c.bg3,
                borderRadius: BorderRadius.circular(7),
                border: Border.all(color: c.bd)),
            child: Icon(icon, size: 14, color: c.blue),
          ),
        ),
      ),
    );
  }
}

class _MonthDropdown extends StatelessWidget {
  final String month;
  final ValueChanged<String> onMonth;
  const _MonthDropdown({required this.month, required this.onMonth});
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      decoration: BoxDecoration(
        color: c.bg3,
        borderRadius: BorderRadius.circular(7),
        border: Border.all(color: c.bd),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: month,
          isDense: true,
          dropdownColor: c.bg2,
          style: AppTextStyles.monoBold(c.t2).copyWith(fontSize: 11.5),
          items: [
            for (final m in ExpenseSchema.months)
              DropdownMenuItem(value: m, child: Text(ExpenseSchema.monthTitle(m))),
          ],
          onChanged: (v) => v != null ? onMonth(v) : null,
        ),
      ),
    );
  }
}

class _SyncBadge extends StatelessWidget {
  final String status;
  final VoidCallback onConnect, onSync, onVersions, onConflict;
  const _SyncBadge({
    required this.status,
    required this.onConnect,
    required this.onSync,
    required this.onVersions,
    required this.onConflict,
  });
  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final (Color color, IconData icon, String label) = switch (status) {
      'success' => (c.up, LucideIcons.checkCircle2, 'Synced'),
      'pending' => (c.gold, LucideIcons.refreshCw, 'Sync pending'),
      'failed' => (c.dn, LucideIcons.cloudOff, 'Sync failed'),
      'conflict' => (c.dn, LucideIcons.alertTriangle, 'Drive conflict'),
      _ => (c.t3, LucideIcons.cloud, 'Drive off'),
    };
    return PopupMenuButton<String>(
      color: c.bg2,
      tooltip: 'Google Drive',
      onSelected: (v) {
        switch (v) {
          case 'connect':
            onConnect();
          case 'sync':
            onSync();
          case 'versions':
            onVersions();
          case 'conflict':
            onConflict();
        }
      },
      itemBuilder: (_) => [
        const PopupMenuItem(value: 'connect', child: Text('Connect Google Drive')),
        const PopupMenuItem(value: 'sync', child: Text('Sync / Upload now')),
        const PopupMenuItem(value: 'versions', child: Text('Version history…')),
        const PopupMenuItem(value: 'conflict', child: Text('Check for conflicts')),
      ],
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: 0.35)),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 13, color: color),
          const SizedBox(width: 5),
          Text(label, style: AppTextStyles.captionXs(color)),
          const SizedBox(width: 3),
          Icon(LucideIcons.chevronDown, size: 12, color: color),
        ]),
      ),
    );
  }
}

// ══════════════════════════════════════════════════════════════════
//  ACTION BAR (context-sensitive add buttons + notes)
// ══════════════════════════════════════════════════════════════════

class _ActionBar extends ConsumerWidget {
  final AccountKind account;
  final int year;
  final String month;
  final ExpenseStore notifier;
  const _ActionBar({
    required this.account,
    required this.year,
    required this.month,
    required this.notifier,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final children = <Widget>[];
    if (account == AccountKind.local) {
      children.addAll([
        _btn(context, LucideIcons.plus, 'Add Expense Category',
            () => _addField(context, 'expense')),
        _btn(context, LucideIcons.plus, 'Add Income Field',
            () => _addField(context, 'income')),
        _btn(context, LucideIcons.plus, 'Add Transfer Field',
            () => _addField(context, 'transfer')),
        _btn(context, LucideIcons.stickyNote, 'Note for ${ExpenseSchema.monthTitle(month)}',
            () => _editNote(context, ref)),
      ]);
    } else if (account == AccountKind.stocks) {
      children.add(_btn(context, LucideIcons.plus, 'Add Trade Row',
          () => notifier.addStockRow(year)));
      children.add(Text('Use the trash icon in the grid to soft-delete a row.',
          style: AppTextStyles.captionXs(c.t3)));
    } else if (account == AccountKind.investments) {
      children.add(_btn(context, LucideIcons.plus, 'Add Fund / Index',
          () => _addInvestField(context)));
      children.add(Text(
          '12 monthly rows are always present — enter values directly in the grid.',
          style: AppTextStyles.captionXs(c.t3)));
    } else {
      children.add(Text(
          '12 monthly rows are always present — enter values directly in the grid.',
          style: AppTextStyles.captionXs(c.t3)));
    }
    return DenseCard(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: children),
    );
  }

  Widget _btn(BuildContext context, IconData icon, String text, VoidCallback onTap) =>
      HeaderButton(
          icon: Icon(icon, size: 13, color: context.colors.blue),
          text: text,
          onTap: onTap);

  Future<void> _addField(BuildContext context, String kind) async {
    final label = await _promptText(context,
        title: 'Add ${kind[0].toUpperCase()}${kind.substring(1)} Field',
        hint: kind == 'income' ? 'e.g. Rental Income' : 'e.g. Insurance');
    if (label != null && label.trim().isNotEmpty) {
      notifier.addLocalField(year, label.trim(), kind: kind);
    }
  }

  Future<void> _addInvestField(BuildContext context) async {
    final label = await _promptText(context,
        title: 'Add Fund / Index',
        hint: 'e.g. Nifty 50, S&P 500');
    if (label != null && label.trim().isNotEmpty) {
      notifier.addInvestField(year, label.trim());
    }
  }

  Future<void> _editNote(BuildContext context, WidgetRef ref) async {
    final data = notifier.viewFor(year);
    final rows = (data['local'] is Map && (data['local'] as Map)['months'] is List)
        ? ((data['local'] as Map)['months'] as List)
        : const [];
    int idx = -1;
    for (var i = 0; i < rows.length; i++) {
      if ('${(rows[i] as Map)['month']}' == month) {
        idx = i;
        break;
      }
    }
    if (idx < 0) return;
    final existing = '${(rows[idx] as Map)['note'] ?? ''}';
    final note = await _promptText(context,
        title: 'Note — ${ExpenseSchema.monthTitle(month)} $year',
        hint: 'Comment for this month',
        initial: existing);
    if (note != null) {
      notifier.setMonthNote(year, 'local', idx, note.trim());
    }
  }

  Future<String?> _promptText(BuildContext context,
      {required String title, required String hint, String initial = ''}) {
    final ctrl = TextEditingController(text: initial);
    return showDialog<String>(
      context: context,
      builder: (ctx) {
        final c = ctx.colors;
        return AlertDialog(
          backgroundColor: c.bg2,
          title: Text(title, style: AppTextStyles.heading3(c.t1)),
          content: TextField(
            controller: ctrl,
            autofocus: true,
            style: AppTextStyles.bodySmall(c.t1),
            decoration: InputDecoration(
              hintText: hint,
              hintStyle: AppTextStyles.bodySmall(c.t3),
            ),
            onSubmitted: (v) => Navigator.pop(ctx, v),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
            TextButton(
                onPressed: () => Navigator.pop(ctx, ctrl.text),
                child: const Text('OK')),
          ],
        );
      },
    );
  }
}

// ══════════════════════════════════════════════════════════════════
//  BOTTOM PANEL (summary + validation + history + timestamps)
// ══════════════════════════════════════════════════════════════════

class _BottomPanel extends ConsumerWidget {
  final ExpenseState state;
  final List<ValidationIssue> validation;
  final int year;
  const _BottomPanel(
      {required this.state, required this.validation, required this.year});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.colors;
    final errors = validation.where((i) => i.isError).toList();
    final warnings = validation.where((i) => !i.isError).toList();
    final history = ref.read(localStorageProvider).getExpenseHistory().reversed.take(6).toList();

    String fmt(String? iso) {
      if (iso == null) return '—';
      final d = DateTime.tryParse(iso);
      if (d == null) return iso;
      String p(int n) => n.toString().padLeft(2, '0');
      return '${d.year}-${p(d.month)}-${p(d.day)} ${p(d.hour)}:${p(d.minute)}';
    }

    return DenseCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(LucideIcons.clipboardCheck, size: 15, color: c.accent),
            const SizedBox(width: 8),
            Text('Save Summary', style: AppTextStyles.heading3(c.t1)),
            const Spacer(),
            if (state.saving)
              SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(strokeWidth: 2, color: c.blue)),
          ]),
          const SizedBox(height: 8),
          Text(
              state.saveSummary.isEmpty
                  ? 'No save yet this session. Edit values, then Save Draft or Final Save.'
                  : state.saveSummary,
              style: AppTextStyles.bodySmall(c.t2)),
          const SizedBox(height: 6),
          Wrap(spacing: 16, runSpacing: 4, children: [
            _stamp(context, 'Last saved', fmt(state.lastSavedIso)),
            _stamp(context, 'Last recalculated', fmt(state.lastRecalcIso)),
            _stamp(context, 'Last uploaded', fmt(state.lastUploadedIso)),
            _stamp(context, 'Sync', state.syncStatus),
            _stamp(context, 'Version', state.versionId),
          ]),
          const Divider(height: 22),
          Text('VALIDATION — ${errors.length} error(s), ${warnings.length} warning(s)',
              style: AppTextStyles.labelXs(errors.isNotEmpty ? c.dn : c.t3)),
          const SizedBox(height: 6),
          if (validation.isEmpty)
            Text('All checks passed.', style: AppTextStyles.bodySmall(c.up))
          else
            ...validation.take(10).map((i) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Icon(i.isError ? LucideIcons.xCircle : LucideIcons.alertTriangle,
                        size: 13, color: i.isError ? c.dn : c.gold),
                    const SizedBox(width: 8),
                    Container(
                      margin: const EdgeInsets.only(right: 8),
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                      decoration: BoxDecoration(
                          color: (i.isError ? c.dn : c.gold).withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(4)),
                      child: Text(i.section,
                          style: AppTextStyles.captionXs(i.isError ? c.dn : c.gold)),
                    ),
                    Expanded(child: Text(i.message, style: AppTextStyles.bodySmall(c.t2))),
                  ]),
                )),
          const Divider(height: 22),
          Text('RECENT CHANGES', style: AppTextStyles.labelXs(c.t3)),
          const SizedBox(height: 6),
          if (history.isEmpty)
            Text('No changes logged yet.', style: AppTextStyles.bodySmall(c.t3))
          else
            ...history.map((h) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Text(
                    '${h['changeId']} · ${h['action']} · ${h['sourceSection']} · '
                    '${h['month'].toString().isEmpty ? '' : '${h['month']} · '}'
                    '${h['sourceColumn']}${h['sourceCellAddress'].toString().isEmpty ? '' : ' (${h['sourceCellAddress']})'} · '
                    '${h['oldValue']} → ${h['newValue']}',
                    style: AppTextStyles.captionXs(c.t3),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                )),
        ],
      ),
    );
  }

  Widget _stamp(BuildContext context, String label, String value) {
    final c = context.colors;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Text('$label: ', style: AppTextStyles.captionXs(c.t3)),
      Text(value, style: AppTextStyles.monoXs(c.t2)),
    ]);
  }
}
