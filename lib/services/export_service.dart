import 'dart:io';
import 'package:csv/csv.dart';
import 'package:file_picker/file_picker.dart';
import 'package:intl/intl.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;

class ExportService {
  final _currencyFormat = NumberFormat.currency(locale: 'en_IN', symbol: 'Rs.');
  final _pctFormat = NumberFormat.decimalPattern('en_US');

  double _toNum(dynamic val) {
    if (val == null) return 0;
    if (val is num) return val.toDouble();
    if (val is String) return double.tryParse(val) ?? 0;
    return 0;
  }

  String _fmt(dynamic val) => _currencyFormat.format(_toNum(val));
  String _pct(dynamic val) => '${_toNum(val).toStringAsFixed(2)}%';
  String _dateSuffix() => DateFormat('yyyy-MM-dd_HHmm').format(DateTime.now());
  String _csvEncode(List<List<dynamic>> rows) => Csv().encode(rows);

  // MF field helpers — backend uses scheme_name, nav, return_pct
  String _mfName(Map f) => (f['scheme_name'] ?? f['fund_name'] ?? '').toString();
  double _mfNav(Map f) => _toNum(f['nav'] ?? f['current_nav']);
  double _mfPnl(Map f) => _toNum(f['current_value']) - _toNum(f['invested']);
  double _mfPnlPct(Map f) => _toNum(f['return_pct'] ?? f['pnl_pct']);

  // P&L color
  PdfColor _plColor(double val) => val >= 0 ? PdfColors.green800 : PdfColors.red800;

  // ══════════════════════════════════════════
  //  CSV EXPORTS
  // ══════════════════════════════════════════

  Future<String?> exportPortfolioToCsv(List<dynamic> holdings) async {
    final String? outputFile = await FilePicker.saveFile(
      dialogTitle: 'Save Equity Portfolio as CSV',
      fileName: 'Ponfolio_Equity_Portfolio_${_dateSuffix()}.csv',
      type: FileType.custom,
      allowedExtensions: ['csv'],
    );
    if (outputFile == null) return null;

    List<List<dynamic>> rows = [];
    rows.add(['Symbol', 'Name', 'Sector', 'Shares', 'Avg Cost', 'Current Price', 'Invested', 'Current Value', 'P&L', 'P&L %']);
    for (var h in holdings) {
      if (h is! Map) continue;
      rows.add([
        h['symbol'] ?? '', h['name'] ?? '', h['sector'] ?? 'Other',
        h['shares'] ?? 0, h['avg_cost'] ?? 0.0, h['current_price'] ?? 0.0,
        h['invested'] ?? 0.0, h['total_value'] ?? 0.0, h['pnl'] ?? 0.0, h['net_chg'] ?? 0.0,
      ]);
    }
    final path = outputFile.endsWith('.csv') ? outputFile : '$outputFile.csv';
    await File(path).writeAsString(_csvEncode(rows));
    return path;
  }

  Future<String?> exportMfPortfolioToCsv(List<dynamic> funds) async {
    final String? outputFile = await FilePicker.saveFile(
      dialogTitle: 'Save Mutual Fund Portfolio as CSV',
      fileName: 'Ponfolio_MF_Portfolio_${_dateSuffix()}.csv',
      type: FileType.custom,
      allowedExtensions: ['csv'],
    );
    if (outputFile == null) return null;

    List<List<dynamic>> rows = [];
    rows.add(['Fund Name', 'Category', 'Units', 'Avg NAV', 'Current NAV', 'Invested', 'Current Value', 'P&L', 'Return %']);
    for (var f in funds) {
      if (f is! Map) continue;
      final pnl = _mfPnl(f);
      rows.add([
        _mfName(f), f['category'] ?? '', _toNum(f['units']).toStringAsFixed(3),
        _toNum(f['avg_nav']).toStringAsFixed(4), _mfNav(f).toStringAsFixed(4),
        _toNum(f['invested']), _toNum(f['current_value']),
        pnl.toStringAsFixed(2), _mfPnlPct(f).toStringAsFixed(2),
      ]);
    }
    final path = outputFile.endsWith('.csv') ? outputFile : '$outputFile.csv';
    await File(path).writeAsString(_csvEncode(rows));
    return path;
  }

  Future<String?> exportCombinedCsv(List<dynamic> holdings, List<dynamic> funds) async {
    final String? outputFile = await FilePicker.saveFile(
      dialogTitle: 'Save Combined Portfolio as CSV',
      fileName: 'Ponfolio_Combined_Portfolio_${_dateSuffix()}.csv',
      type: FileType.custom,
      allowedExtensions: ['csv'],
    );
    if (outputFile == null) return null;

    List<List<dynamic>> rows = [];
    rows.add(['Type', 'Name/Symbol', 'Category/Sector', 'Qty/Units', 'Cost', 'Current', 'Invested', 'Value', 'P&L', 'P&L %']);
    for (var h in holdings) {
      if (h is! Map) continue;
      rows.add(['Equity', h['symbol'] ?? '', h['sector'] ?? '', h['shares'] ?? 0,
        h['avg_cost'] ?? 0, h['current_price'] ?? 0, h['invested'] ?? 0,
        h['total_value'] ?? 0, h['pnl'] ?? 0, h['net_chg'] ?? 0]);
    }
    for (var f in funds) {
      if (f is! Map) continue;
      rows.add(['Mutual Fund', _mfName(f), f['category'] ?? '',
        _toNum(f['units']).toStringAsFixed(3),
        _toNum(f['avg_nav']).toStringAsFixed(4), _mfNav(f).toStringAsFixed(4),
        _toNum(f['invested']), _toNum(f['current_value']),
        _mfPnl(f).toStringAsFixed(2), _mfPnlPct(f).toStringAsFixed(2)]);
    }
    final path = outputFile.endsWith('.csv') ? outputFile : '$outputFile.csv';
    await File(path).writeAsString(_csvEncode(rows));
    return path;
  }

  // ══════════════════════════════════════════
  //  PDF TABLE BUILDER WITH P&L COLORING
  // ══════════════════════════════════════════

  /// Builds a styled PDF table with color-coded P&L columns.
  /// [headers] = column names, [rows] = list of row data maps with 'cells' (List<String>) and 'pnl' (double).
  pw.Widget _coloredTable({
    required List<String> headers,
    required List<Map<String, dynamic>> rows,
    PdfColor headerColor = PdfColors.blue800,
    int pnlCol = -1,    // column index for P&L value
    int pnlPctCol = -1, // column index for P&L %
  }) {
    return pw.Table(
      border: pw.TableBorder.all(color: PdfColors.grey300, width: 0.5),
      columnWidths: {
        for (int i = 0; i < headers.length; i++)
          i: (i == 0 || i == 1) ? const pw.FlexColumnWidth(2) : const pw.FlexColumnWidth(1),
      },
      children: [
        // Header row
        pw.TableRow(
          decoration: pw.BoxDecoration(color: headerColor),
          children: headers.map((h) => pw.Padding(
            padding: const pw.EdgeInsets.all(4),
            child: pw.Text(h, style: pw.TextStyle(
              fontSize: 8, fontWeight: pw.FontWeight.bold, color: PdfColors.white,
            ), textAlign: (h == headers.first) ? pw.TextAlign.left : pw.TextAlign.right),
          )).toList(),
        ),
        // Data rows
        ...rows.asMap().entries.map((entry) {
          final idx = entry.key;
          final row = entry.value;
          final cells = row['cells'] as List<String>;
          final pnl = _toNum(row['pnl']);
          final bgColor = idx.isEven ? PdfColors.white : PdfColors.grey50;

          return pw.TableRow(
            decoration: pw.BoxDecoration(color: bgColor),
            children: List.generate(cells.length, (ci) {
              final isPlCol = (ci == pnlCol || ci == pnlPctCol);
              final color = isPlCol ? _plColor(pnl) : PdfColors.black;
              return pw.Padding(
                padding: const pw.EdgeInsets.all(4),
                child: pw.Text(cells[ci],
                  style: pw.TextStyle(
                    fontSize: 7,
                    color: color,
                    fontWeight: isPlCol ? pw.FontWeight.bold : pw.FontWeight.normal,
                  ),
                  textAlign: ci == 0 ? pw.TextAlign.left : pw.TextAlign.right,
                ),
              );
            }),
          );
        }),
      ],
    );
  }

  // ══════════════════════════════════════════
  //  PDF EXPORTS
  // ══════════════════════════════════════════

  Future<String?> exportStocksPdf(List<dynamic> holdings) async {
    final String? outputFile = await FilePicker.saveFile(
      dialogTitle: 'Save Equity Portfolio as PDF',
      fileName: 'Ponfolio_Equity_Portfolio_${_dateSuffix()}.pdf',
      type: FileType.custom,
      allowedExtensions: ['pdf'],
    );
    if (outputFile == null) return null;

    final pdf = pw.Document();
    final headers = ['Symbol', 'Name', 'Sector', 'Shares', 'Avg Cost', 'CMP', 'Invested', 'Value', 'P&L', 'P&L %'];
    final rows = holdings.whereType<Map>().map((h) {
      final pnl = _toNum(h['pnl']);
      return {
        'cells': [
          h['symbol']?.toString() ?? '', h['name']?.toString() ?? '', h['sector']?.toString() ?? '',
          '${h['shares'] ?? 0}', _fmt(h['avg_cost']), _fmt(h['current_price']),
          _fmt(h['invested']), _fmt(h['total_value']), _fmt(pnl), _pct(h['net_chg']),
        ],
        'pnl': pnl,
      };
    }).toList();

    pdf.addPage(pw.MultiPage(
      pageFormat: PdfPageFormat.a4.landscape,
      margin: const pw.EdgeInsets.all(28),
      build: (ctx) => [
        _pdfHeader('Equity Portfolio Report'),
        pw.SizedBox(height: 16),
        if (holdings.isEmpty)
          pw.Text('No equity holdings found.')
        else
          _coloredTable(headers: headers, rows: rows, pnlCol: 8, pnlPctCol: 9),
      ],
    ));
    final path = outputFile.endsWith('.pdf') ? outputFile : '$outputFile.pdf';
    await File(path).writeAsBytes(await pdf.save());
    return path;
  }

  Future<String?> exportMfPdf(List<dynamic> funds) async {
    final String? outputFile = await FilePicker.saveFile(
      dialogTitle: 'Save Mutual Fund Portfolio as PDF',
      fileName: 'Ponfolio_MF_Portfolio_${_dateSuffix()}.pdf',
      type: FileType.custom,
      allowedExtensions: ['pdf'],
    );
    if (outputFile == null) return null;

    final pdf = pw.Document();
    final headers = ['Fund Name', 'Category', 'Units', 'Avg NAV', 'NAV', 'Invested', 'Value', 'P&L', 'Return %'];
    final rows = funds.whereType<Map>().map((f) {
      final pnl = _mfPnl(f);
      return {
        'cells': [
          _mfName(f), f['category']?.toString() ?? '',
          _toNum(f['units']).toStringAsFixed(3),
          _fmt(f['avg_nav']), _fmt(_mfNav(f)),
          _fmt(f['invested']), _fmt(f['current_value']),
          _fmt(pnl), _pct(_mfPnlPct(f)),
        ],
        'pnl': pnl,
      };
    }).toList();

    pdf.addPage(pw.MultiPage(
      pageFormat: PdfPageFormat.a4.landscape,
      margin: const pw.EdgeInsets.all(28),
      build: (ctx) => [
        _pdfHeader('Mutual Fund Portfolio Report'),
        pw.SizedBox(height: 16),
        if (funds.isEmpty)
          pw.Text('No mutual fund holdings found.')
        else
          _coloredTable(headers: headers, rows: rows, headerColor: PdfColors.indigo800, pnlCol: 7, pnlPctCol: 8),
      ],
    ));
    final path = outputFile.endsWith('.pdf') ? outputFile : '$outputFile.pdf';
    await File(path).writeAsBytes(await pdf.save());
    return path;
  }

  Future<String?> exportCombinedPdf(List<dynamic> holdings, List<dynamic> funds) async {
    final String? outputFile = await FilePicker.saveFile(
      dialogTitle: 'Save Combined Portfolio as PDF',
      fileName: 'Ponfolio_Combined_Portfolio_${_dateSuffix()}.pdf',
      type: FileType.custom,
      allowedExtensions: ['pdf'],
    );
    if (outputFile == null) return null;

    final pdf = pw.Document();

    // Build equity rows
    final eqHeaders = ['Symbol', 'Name', 'Shares', 'Cost', 'CMP', 'Invested', 'Value', 'P&L', 'Chg%'];
    final eqRows = holdings.whereType<Map>().map((h) {
      final pnl = _toNum(h['pnl']);
      return {
        'cells': [
          h['symbol']?.toString() ?? '', h['name']?.toString() ?? '', '${h['shares'] ?? 0}',
          _fmt(h['avg_cost']), _fmt(h['current_price']),
          _fmt(h['invested']), _fmt(h['total_value']), _fmt(pnl), _pct(h['net_chg']),
        ],
        'pnl': pnl,
      };
    }).toList();

    // Build MF rows
    final mfHeaders = ['Fund Name', 'Category', 'Units', 'Avg NAV', 'NAV', 'Invested', 'Value', 'P&L', 'Return%'];
    final mfRows = funds.whereType<Map>().map((f) {
      final pnl = _mfPnl(f);
      return {
        'cells': [
          _mfName(f), f['category']?.toString() ?? '',
          _toNum(f['units']).toStringAsFixed(3),
          _fmt(f['avg_nav']), _fmt(_mfNav(f)),
          _fmt(f['invested']), _fmt(f['current_value']),
          _fmt(pnl), _pct(_mfPnlPct(f)),
        ],
        'pnl': pnl,
      };
    }).toList();

    pdf.addPage(pw.MultiPage(
      pageFormat: PdfPageFormat.a4.landscape,
      margin: const pw.EdgeInsets.all(28),
      build: (ctx) => [
        _pdfHeader('Combined Wealth Portfolio'),
        pw.SizedBox(height: 16),
        pw.Text('Equity Holdings', style: pw.TextStyle(fontSize: 14, fontWeight: pw.FontWeight.bold)),
        pw.Divider(),
        pw.SizedBox(height: 8),
        if (holdings.isEmpty) pw.Text('No equity holdings.')
        else _coloredTable(headers: eqHeaders, rows: eqRows, pnlCol: 7, pnlPctCol: 8),
        pw.SizedBox(height: 24),
        pw.Text('Mutual Fund Holdings', style: pw.TextStyle(fontSize: 14, fontWeight: pw.FontWeight.bold)),
        pw.Divider(),
        pw.SizedBox(height: 8),
        if (funds.isEmpty) pw.Text('No mutual fund holdings.')
        else _coloredTable(headers: mfHeaders, rows: mfRows, headerColor: PdfColors.indigo800, pnlCol: 7, pnlPctCol: 8),
      ],
    ));
    final path = outputFile.endsWith('.pdf') ? outputFile : '$outputFile.pdf';
    await File(path).writeAsBytes(await pdf.save());
    return path;
  }

  Future<String?> exportWealthReportPdf(Map<String, dynamic> report) async {
    final String? outputFile = await FilePicker.saveFile(
      dialogTitle: 'Save Wealth Report as PDF',
      fileName: 'Ponfolio_Wealth_Report_${_dateSuffix()}.pdf',
      type: FileType.custom,
      allowedExtensions: ['pdf'],
    );
    if (outputFile == null) return null;

    final pdf = pw.Document();
    final grand = report['grand_total'] as Map<String, dynamic>? ?? {};
    final sectors = List<Map<String, dynamic>>.from(report['sectors'] ?? []);
    final equity = report['equity'] as Map<String, dynamic>? ?? {};
    final mf = report['mutual_funds'] as Map<String, dynamic>? ?? {};
    final totalPnl = _toNum(grand['total_pnl']);

    pdf.addPage(pw.MultiPage(
      pageFormat: PdfPageFormat.a4,
      margin: const pw.EdgeInsets.all(32),
      build: (ctx) => [
        _pdfHeader('Wealth Report'),
        pw.SizedBox(height: 20),
        pw.Text('Grand Total', style: pw.TextStyle(fontSize: 16, fontWeight: pw.FontWeight.bold)),
        pw.Divider(),
        _row('Total Value:', _fmt(grand['total_value'])),
        _row('Total Invested:', _fmt(grand['total_invested'])),
        _coloredRow('Total P&L:', _fmt(totalPnl), totalPnl),
        _coloredRow('Total Return:', _pct(grand['total_pnl_pct']), totalPnl),
        pw.SizedBox(height: 30),
        pw.Row(crossAxisAlignment: pw.CrossAxisAlignment.start, children: [
          pw.Expanded(child: _breakdown('Equity Portfolio', equity)),
          pw.SizedBox(width: 20),
          pw.Expanded(child: _breakdown('Mutual Funds', mf)),
        ]),
        pw.SizedBox(height: 30),
        pw.Text('Sector Allocation', style: pw.TextStyle(fontSize: 16, fontWeight: pw.FontWeight.bold)),
        pw.Divider(),
        if (sectors.isNotEmpty)
          pw.TableHelper.fromTextArray(
            headerStyle: pw.TextStyle(fontWeight: pw.FontWeight.bold, color: PdfColors.white),
            headerDecoration: const pw.BoxDecoration(color: PdfColors.blue800),
            cellAlignment: pw.Alignment.centerRight,
            cellAlignments: {0: pw.Alignment.centerLeft},
            data: [
              ['Sector', 'Value', 'Weight'],
              ...sectors.map((s) => [
                s['sector']?.toString() ?? '',
                _fmt(s['value']),
                '${_toNum(s['weight']).toStringAsFixed(1)}%',
              ]),
            ],
          )
        else
          pw.Text('No sector data available.'),
      ],
    ));
    final path = outputFile.endsWith('.pdf') ? outputFile : '$outputFile.pdf';
    await File(path).writeAsBytes(await pdf.save());
    return path;
  }

  // ══════════════════════════════════════════
  //  IMPORT CSV
  // ══════════════════════════════════════════

  Future<List<List<dynamic>>?> importCsv() async {
    FilePickerResult? result = await FilePicker.pickFiles(
      dialogTitle: 'Select CSV File to Import',
      type: FileType.custom,
      allowedExtensions: ['csv'],
      allowMultiple: false,
    );
    if (result == null || result.files.isEmpty) return null;
    final path = result.files.single.path;
    if (path == null) return null;

    final content = await File(path).readAsString();
    return Csv().decode(content);
  }

  // ══════════════════════════════════════════
  //  PDF HELPERS
  // ══════════════════════════════════════════

  pw.Widget _pdfHeader(String title) => pw.Row(
    mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
    children: [
      pw.Text('Ponfolio', style: pw.TextStyle(fontSize: 22, fontWeight: pw.FontWeight.bold, color: PdfColors.blue800)),
      pw.Column(crossAxisAlignment: pw.CrossAxisAlignment.end, children: [
        pw.Text(title, style: pw.TextStyle(fontSize: 16, color: PdfColors.grey700)),
        pw.Text('Generated: ${DateFormat('dd MMM yyyy, hh:mm a').format(DateTime.now())}',
          style: pw.TextStyle(fontSize: 9, color: PdfColors.grey500)),
      ]),
    ],
  );

  pw.Widget _row(String label, String value) => pw.Padding(
    padding: const pw.EdgeInsets.symmetric(vertical: 4),
    child: pw.Row(mainAxisAlignment: pw.MainAxisAlignment.spaceBetween, children: [
      pw.Text(label, style: const pw.TextStyle(color: PdfColors.grey700)),
      pw.Text(value, style: pw.TextStyle(fontWeight: pw.FontWeight.bold)),
    ]),
  );

  pw.Widget _coloredRow(String label, String value, double pnl) => pw.Padding(
    padding: const pw.EdgeInsets.symmetric(vertical: 4),
    child: pw.Row(mainAxisAlignment: pw.MainAxisAlignment.spaceBetween, children: [
      pw.Text(label, style: const pw.TextStyle(color: PdfColors.grey700)),
      pw.Text(value, style: pw.TextStyle(fontWeight: pw.FontWeight.bold, color: _plColor(pnl))),
    ]),
  );

  pw.Widget _breakdown(String title, Map<String, dynamic> data) {
    final pnl = _toNum(data['total_pnl']);
    return pw.Container(
      padding: const pw.EdgeInsets.all(12),
      decoration: pw.BoxDecoration(
        border: pw.Border.all(color: PdfColors.grey300),
        borderRadius: const pw.BorderRadius.all(pw.Radius.circular(8)),
      ),
      child: pw.Column(crossAxisAlignment: pw.CrossAxisAlignment.start, children: [
        pw.Text(title, style: pw.TextStyle(fontSize: 14, fontWeight: pw.FontWeight.bold)),
        pw.SizedBox(height: 10),
        _row('Value:', _fmt(data['total_value'])),
        _row('Invested:', _fmt(data['total_invested'])),
        _coloredRow('P&L:', _fmt(pnl), pnl),
      ]),
    );
  }
}

final exportService = ExportService();
