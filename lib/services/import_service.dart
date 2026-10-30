import 'dart:io';
import 'package:csv/csv.dart';
import 'package:file_picker/file_picker.dart';
import 'package:logger/logger.dart';
import 'package:aiei_wealth/services/api_service.dart';

class ImportService {
  final _log = Logger(printer: PrettyPrinter(methodCount: 0));

  Future<int> importPortfolioFromCsv() async {
    try {
      final result = await FilePicker.pickFiles(
        dialogTitle: 'Import Equity Portfolio',
        type: FileType.custom,
        allowedExtensions: ['csv'],
      );

      if (result == null || result.files.single.path == null) return 0;

      final fileContent = await File(result.files.single.path!).readAsString();
      final fields = csv.decode(fileContent);

      if (fields.isEmpty || fields.length == 1) return 0;

      // Assuming row 0 is header: Symbol, Name, Sector, Shares, Avg Cost, ...
      int imported = 0;
      final api = ApiService();

      for (int i = 1; i < fields.length; i++) {
        final row = fields[i];
        if (row.length < 5) continue;
        
        final symbol = row[0].toString();
        if (symbol.isEmpty) continue;

        // Try to parse numbers safely
        int shares = 0;
        double avgCost = 0.0;

        if (row[3] is num) {
          shares = (row[3] as num).toInt();
        } else {
          shares = int.tryParse(row[3].toString()) ?? 0;
        }

        if (row[4] is num) {
          avgCost = (row[4] as num).toDouble();
        } else {
          avgCost = double.tryParse(row[4].toString()) ?? 0.0;
        }

        if (shares > 0) {
          await api.addStock(symbol, shares, avgCost: avgCost); // Add or update the stock
          imported++;
        }
      }

      return imported;
    } catch (e) {
      _log.e('Failed to import CSV: $e');
      return 0;
    }
  }

  /// Select and upload a Zerodha Console tradebook export.
  ///
  /// A null result means the picker was cancelled. Errors are intentionally
  /// allowed through so the screen can give the user a useful recovery
  /// message instead of turning every failure into "0 rows imported".
  /// Console's tradebook, in either format it offers.
  ///
  /// The download button gives .xlsx by default, so restricting the picker to
  /// .csv meant the file the user actually had could not be selected. The
  /// backend dispatches on the bytes, not the extension.
  Future<Map<String, dynamic>?> importTradebookFromCsv() async {
    final result = await FilePicker.pickFiles(
      dialogTitle: 'Import Zerodha Tradebook (XLSX or CSV)',
      type: FileType.custom,
      allowedExtensions: ['xlsx', 'csv'],
    );
    if (result == null || result.files.single.path == null) return null;

    final picked = result.files.single;
    return ApiService().importTradebook(
      picked.path!,
      filename: picked.name,
    );
  }

  /// Console's funds ledger for one period — the only export with TDS on it.
  Future<Map<String, dynamic>?> importKiteLedger() async {
    final result = await FilePicker.pickFiles(
      dialogTitle: 'Import Kite Ledger (XLSX)',
      type: FileType.custom,
      allowedExtensions: ['xlsx'],
    );
    if (result == null || result.files.single.path == null) return null;

    final picked = result.files.single;
    return ApiService().importKiteLedger(picked.path!, filename: picked.name);
  }

  /// Console's P&L statement for one period — the measured realised P&L and
  /// the charges actually levied. XLSX only: Console's CSV P&L export drops
  /// the per-head charges block this reads.
  Future<Map<String, dynamic>?> importKitePnl() async {
    final result = await FilePicker.pickFiles(
      dialogTitle: 'Import Kite P&L Statement (XLSX)',
      type: FileType.custom,
      allowedExtensions: ['xlsx'],
    );
    if (result == null || result.files.single.path == null) return null;

    final picked = result.files.single;
    return ApiService().importKitePnl(picked.path!, filename: picked.name);
  }

  Future<int> importMfPortfolioFromCsv() async {
    try {
      final result = await FilePicker.pickFiles(
        dialogTitle: 'Import Mutual Fund Portfolio',
        type: FileType.custom,
        allowedExtensions: ['csv'],
      );

      if (result == null || result.files.single.path == null) return 0;

      final fileContent = await File(result.files.single.path!).readAsString();
      final fields = csv.decode(fileContent);

      if (fields.isEmpty || fields.length == 1) return 0;

      // Assuming row 0 is header: Fund Name, Category, Units, Avg NAV, ...
      int imported = 0;
      final api = ApiService();

      for (int i = 1; i < fields.length; i++) {
        final row = fields[i];
        if (row.length < 4) continue;
        
        final fundName = row[0].toString();
        if (fundName.isEmpty) continue;

        final category = row[1].toString();

        double units = 0.0;
        double avgNav = 0.0;

        if (row[2] is num) {
          units = (row[2] as num).toDouble();
        } else {
          units = double.tryParse(row[2].toString()) ?? 0.0;
        }

        if (row[3] is num) {
          avgNav = (row[3] as num).toDouble();
        } else {
          avgNav = double.tryParse(row[3].toString()) ?? 0.0;
        }

        if (units > 0) {
          await api.addMFFund({
            'fund_name': fundName,
            'category': category.isEmpty ? 'Equity' : category,
            'units': units,
            'avg_nav': avgNav,
          });
          imported++;
        }
      }

      return imported;
    } catch (e) {
      _log.e('Failed to import MF CSV: $e');
      return 0;
    }
  }
}

final importService = ImportService();
