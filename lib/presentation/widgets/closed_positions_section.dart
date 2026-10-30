import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../../core/extensions.dart';
import '../../core/theme/app_text_styles.dart';
import '../../data/models/closed_positions.dart';
import 'dense_ui.dart';

/// Closed positions: what the shares you have already sold actually made.
///
/// Layout-only, like the rest of the dense widgets — the screen fetches the
/// book and hands it over, so this renders in a test without a backend.
///
/// The labelling is the substance here. Buy, sell and gross P&L are measured
/// from the tradebook; charges are computed from the statutory rate card
/// because a tradebook has no contract-note figures; the tax line is an
/// illustration at statutory rates. Each of the three is named for what it is
/// on the face of the card, not in a footnote, so a net figure is never
/// mistaken for a settled one.
class ClosedPositionsSection extends StatefulWidget {
  final ClosedBook book;
  final bool loading;
  final Object? error;
  final VoidCallback? onRetry;

  const ClosedPositionsSection({
    super.key,
    required this.book,
    this.loading = false,
    this.error,
    this.onRetry,
  });

  @override
  State<ClosedPositionsSection> createState() =>
      _ClosedPositionsSectionState();
}

class _ClosedPositionsSectionState extends State<ClosedPositionsSection> {
  final Set<String> _open = {};

  static String _money(double? n) => n == null
      ? 'Unavailable'
      : NumberFormat.currency(locale: 'en_IN', symbol: '₹', decimalDigits: 0)
            .format(n);

  static String _signed(double? n) => n == null
      ? 'Unavailable'
      : '${n > 0 ? '+' : ''}${NumberFormat.currency(locale: 'en_IN', symbol: '₹', decimalDigits: 0).format(n)}';

  static String _pct(double? n) =>
      n == null ? '—' : '${n > 0 ? '+' : ''}${n.toStringAsFixed(2)}%';

  static String _price(double? n) =>
      n == null ? '—' : NumberFormat('#,##0.00', 'en_IN').format(n);

  static String _days(int d) => d >= 365
      ? '${(d / 365).toStringAsFixed(1)}y'
      : d >= 30
      ? '${(d / 30).round()}m'
      : '${d}d';

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final book = widget.book;

    if (widget.error != null) {
      return DenseCard(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 26),
        child: Column(
          children: [
            Icon(LucideIcons.triangleAlert, size: 22, color: c.dn),
            const SizedBox(height: 10),
            Text(
              'Could not load closed positions',
              style: AppTextStyles.heading3(c.t1),
            ),
            const SizedBox(height: 4),
            Text(
              'The realised book is computed from the saved trade ledger.',
              style: AppTextStyles.bodySmall(c.t3),
              textAlign: TextAlign.center,
            ),
            if (widget.onRetry != null) ...[
              const SizedBox(height: 12),
              _pillButton(context, 'Retry', LucideIcons.refreshCw,
                  widget.onRetry!),
            ],
          ],
        ),
      );
    }
    if (widget.loading && book.isEmpty) {
      return const DenseCard(
        child: SizedBox(height: 120, child: DensePulseLoader()),
      );
    }
    if (book.isEmpty) {
      return const DenseEmptyCard(
        icon: LucideIcons.archive,
        title: 'No closed positions yet',
        sub: 'When a holding is sold, its realised profit, the charges it '
            'cost and its holding period are matched FIFO and reported here. '
            'Import a Zerodha Console tradebook if past sales are missing.',
      );
    }

    final net = book.netPnlEstimated;
    final tone = net == null
        ? c.t3
        : net > 0
        ? c.up
        : net < 0
        ? c.dn
        : c.t1;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _header(context, tone),
        const SizedBox(height: 10),
        _kpis(context, tone),
        const SizedBox(height: 10),
        _table(context),
        if (book.statement != null || book.tds != null) ...[
          const SizedBox(height: 10),
          _statementPanel(context, book.statement, book.tds),
        ],
        if (book.tds?.hasOverlap ?? false) ...[
          const SizedBox(height: 8),
          _flag(
            context,
            'Two imported ledgers cover the same dates '
            '(${book.tds!.overlappingPeriods.map((p) => p.join(" & ")).join("; ")}). '
            'TDS is being counted twice — remove one of them.',
            c.dn,
          ),
        ],
        if (book.statement?.hasOverlap ?? false) ...[
          const SizedBox(height: 8),
          _flag(
            context,
            'Two imported statements cover the same dates '
            '(${book.statement!.overlappingPeriods.map((p) => p.join(" & ")).join("; ")}). '
            'Their totals are being added twice — remove one of them.',
            c.dn,
          ),
        ],
        if (book.unmatchedSellQty > 0) ...[
          const SizedBox(height: 8),
          _flag(
            context,
            '${book.unmatchedSellQty.toStringAsFixed(0)} sold shares have no '
            'matching buy in the ledger. Their profit is excluded rather than '
            'estimated — import the earlier tradebook to include them.',
            c.gold,
          ),
        ],
        const SizedBox(height: 8),
        _flag(
          context,
          book.chargesAreMeasured
              ? 'Realised P&L and charges are measured — taken from your Kite '
                    'P&L statement, not computed. Charges cover every trade in '
                    'the imported period, including buys of positions you still '
                    'hold, so period net is not the same as profit on these '
                    'closed lots. Per-position charge columns remain rate-card '
                    'estimates, since a statement does not split them by symbol. '
                    'The tax line is indicative and is not a tax computation.'
              : 'Buy, sell and gross P&L are measured from your tradebook. '
                    'Charges are estimated from the statutory delivery rate card '
                    '(STT, exchange, SEBI, stamp duty, GST, DP) because a '
                    'tradebook carries no contract-note amounts — import the '
                    'Kite P&L statement for the real figures. The tax line is '
                    'indicative at statutory rates and is not a tax computation.',
          c.t3,
        ),
      ],
    );
  }

  /// What the broker's own exports say, and how the reconstruction compares.
  ///
  /// The comparison is the point: FIFO from the tradebook and Console's
  /// realised figure are computed from different sources, so agreement is
  /// evidence the ledger is complete, and a gap localises the problem instead
  /// of leaving two plausible numbers on screen.
  ///
  /// [st] is the P&L statement and [tds] the funds ledger. They are separate
  /// exports covering possibly different periods, so each block states its own
  /// coverage rather than borrowing the other's.
  Widget _statementPanel(
    BuildContext context,
    ClosedStatement? st,
    ClosedTds? tds,
  ) {
    final c = context.colors;
    final rec = widget.book.reconciliation;
    final agrees = rec?.grossAgrees;
    final coverage = st?.coversFrom == null
        ? (tds?.coversFrom == null
              ? 'imported'
              : 'ledger ${tds!.coversFrom} → ${tds.coversTo}')
        : '${st!.coversFrom} → ${st.coversTo} · ${st.periods.length} period(s)';
    return DenseCard(
      clip: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          denseTableHeader(
            context,
            icon: LucideIcons.fileCheck,
            accent: agrees == false ? c.dn : c.up,
            title: 'BROKER STATEMENT',
            subtitle: coverage,
            trailing: _tag(
              context,
              agrees == null
                  ? 'NOT CHECKED'
                  : agrees
                  ? 'RECONCILED'
                  : 'MISMATCH',
              agrees == false ? c.dn : c.up,
            ),
          ),
          if (rec != null && st != null)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 11),
              decoration: BoxDecoration(
                border: Border(bottom: BorderSide(color: c.bd)),
              ),
              child: Column(
                children: [
                  _recRow(
                    context,
                    'Realised — your ledger, FIFO',
                    _signed(rec.ledgerFifoGross),
                    c.t2,
                  ),
                  _recRow(
                    context,
                    'Realised — broker statement',
                    _signed(rec.brokerRealized),
                    c.t1,
                  ),
                  _recRow(
                    context,
                    'Charges — rate-card estimate',
                    _money(rec.chargesEstimated),
                    c.t3,
                  ),
                  _recRow(
                    context,
                    'Charges — actually billed',
                    _money(rec.chargesActual),
                    c.t1,
                  ),
                  if (rec.chargesEstimateError != null)
                    _recRow(
                      context,
                      'Estimate was off by',
                      _signed(rec.chargesEstimateError),
                      rec.chargesEstimateError!.abs() < 1 ? c.up : c.gold,
                    ),
                ],
              ),
            ),
          // TDS comes from the funds ledger, a different export from the P&L
          // statement above, so it gets its own block with its own coverage.
          // Deducted and provisional are never added: one is a cost, the other
          // is money blocked and normally handed back within days.
          if (tds != null)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 11),
              decoration: BoxDecoration(
                border: Border(bottom: BorderSide(color: c.bd)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text('TDS', style: AppTextStyles.labelXs(c.t3)),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          tds.coversFrom == null
                              ? 'from the funds ledger'
                              : 'funds ledger · ${tds.coversFrom} → ${tds.coversTo}',
                          style: AppTextStyles.captionXs(c.t3),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  _recRow(
                    context,
                    'Actually deducted',
                    _money(tds.deducted),
                    tds.deducted > 0 ? c.dn : c.t2,
                  ),
                  if (tds.hasProvisional) ...[
                    _recRow(
                      context,
                      'Provisional — blocked',
                      _money(tds.provisionalBlocked),
                      c.t3,
                    ),
                    _recRow(
                      context,
                      'Provisional — reversed',
                      _money(tds.provisionalReversed),
                      c.t3,
                    ),
                    _recRow(
                      context,
                      tds.hasOutstanding
                          ? 'Still blocked, not yet reversed'
                          : 'Provisional net (blocked − reversed)',
                      _money(tds.provisionalOutstanding),
                      tds.hasOutstanding ? c.gold : c.up,
                    ),
                  ],
                  if (widget.book.costWithTds != null)
                    _recRow(
                      context,
                      'Charges + TDS',
                      _money(widget.book.costWithTds),
                      c.t1,
                    ),
                  if (tds.entries.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    for (final entry in tds.entries.take(8))
                      Padding(
                        padding: const EdgeInsets.only(bottom: 3),
                        child: Row(
                          children: [
                            SizedBox(
                              width: 74,
                              child: Text(
                                entry.date ?? '—',
                                style: AppTextStyles.monoXs(c.t3),
                              ),
                            ),
                            Expanded(
                              child: Text(
                                entry.particulars,
                                style: AppTextStyles.captionXs(c.t3),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              _signed(-entry.net),
                              style: AppTextStyles.monoXs(
                                entry.isReversal ? c.up : c.dn,
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ],
              ),
            ),
          if (st != null && st.chargesRanked.isNotEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'WHAT THE CHARGES WERE',
                    style: AppTextStyles.labelXs(c.t3),
                  ),
                  const SizedBox(height: 8),
                  for (final head in st.chargesRanked)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 5),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              head.head,
                              style: AppTextStyles.captionXs(c.t2),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          const SizedBox(width: 8),
                          SizedBox(
                            width: 92,
                            child: Text(
                              NumberFormat.currency(
                                locale: 'en_IN',
                                symbol: '₹',
                                decimalDigits: 2,
                              ).format(head.amount),
                              style: AppTextStyles.monoXs(c.t1),
                              textAlign: TextAlign.right,
                            ),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
          if (st != null && st.periods.length > 1)
            Container(
              width: double.infinity,
              color: c.bg3,
              padding: const EdgeInsets.fromLTRB(14, 9, 14, 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('PERIODS IMPORTED', style: AppTextStyles.labelXs(c.t3)),
                  const SizedBox(height: 6),
                  for (final period in st.periods)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 3),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              period.label,
                              style: AppTextStyles.monoXs(c.t2),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          Text(
                            _signed(period.realizedPnl),
                            style: AppTextStyles.monoXs(c.t2),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _recRow(
    BuildContext context,
    String label,
    String value,
    Color tone,
  ) => Padding(
    padding: const EdgeInsets.only(bottom: 4),
    child: Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: AppTextStyles.captionXs(context.colors.t3),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        const SizedBox(width: 8),
        Text(value, style: AppTextStyles.monoXs(tone)),
      ],
    ),
  );

  Widget _header(BuildContext context, Color tone) {
    final c = context.colors;
    final book = widget.book;
    return Padding(
      padding: const EdgeInsets.fromLTRB(2, 0, 2, 0),
      child: Row(
        children: [
          Icon(LucideIcons.archive, size: 15, color: tone),
          const SizedBox(width: 8),
          Expanded(
            child: Row(
              children: [
                Flexible(
                  child: Text(
                    'CLOSED POSITIONS — WHAT DID I MAKE?',
                    style: AppTextStyles.bodyBold(
                      c.t1,
                    ).copyWith(fontSize: 13, letterSpacing: 0.5),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 10),
                Flexible(
                  child: Text(
                    '${book.symbolsClosed} sold out · ${book.trades} round trips',
                    style: AppTextStyles.labelXs(c.t3),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
          if (widget.loading)
            SizedBox(
              width: 12,
              height: 12,
              child: CircularProgressIndicator(strokeWidth: 1.6, color: c.t3),
            ),
        ],
      ),
    );
  }

  Widget _kpis(BuildContext context, Color tone) {
    final c = context.colors;
    final b = widget.book;
    final st = b.statement;
    final measured = b.isMeasured;
    final realised = b.realized;
    Color pnlTone(double? v) => v == null
        ? c.t3
        : v >= 0
        ? c.up
        : c.dn;
    final cells = [
      // With a statement imported the headline becomes the broker's own
      // realised figure and the charges actually billed. Without one it stays
      // the FIFO reconstruction and the rate-card estimate, and says which.
      Kpi(
        measured ? 'REALISED (BROKER)' : 'NET REALISED',
        _signed(measured ? realised : b.netPnlEstimated),
        measured ? 'Kite P&L statement' : 'after est. charges',
        pnlTone(measured ? realised : b.netPnlEstimated),
      ),
      Kpi(
        measured ? 'PERIOD NET' : 'GROSS REALISED',
        _signed(measured ? st!.periodNet : b.grossPnl),
        measured ? 'realised − all charges' : 'measured from tradebook',
        pnlTone(measured ? st!.periodNet : b.grossPnl),
      ),
      Kpi(
        'CHARGES',
        _money(b.charges),
        b.chargesAreMeasured ? 'actually billed' : 'estimated, not billed',
        c.t2,
      ),
      Kpi(
        'RETURN ON COST',
        _pct(b.netPnlPctEstimated),
        'net, on ${_money(b.buyValue)} bought',
        tone,
      ),
      Kpi(
        'WIN RATE',
        b.winRatePct == null ? '—' : '${b.winRatePct!.toStringAsFixed(0)}%',
        '${b.wins} up · ${b.losses} down',
        c.t1,
      ),
      Kpi(
        'SHORT TERM',
        _signed(b.shortTermNet),
        'held under 12 months',
        b.shortTermNet == null
            ? c.t3
            : b.shortTermNet! >= 0
            ? c.up
            : c.dn,
      ),
      Kpi(
        'LONG TERM',
        _signed(b.longTermNet),
        'held over 12 months',
        b.longTermNet == null
            ? c.t3
            : b.longTermNet! >= 0
            ? c.up
            : c.dn,
      ),
      if (b.tds != null)
        Kpi(
          'TDS DEDUCTED',
          _money(b.tds!.deducted),
          b.tds!.hasOutstanding
              ? '+${_money(b.tds!.provisionalOutstanding)} still blocked'
              : 'Console funds ledger',
          b.tds!.deducted > 0 ? c.dn : c.t2,
        ),
      Kpi(
        'TAX (INDICATIVE)',
        _money(b.taxIndicative),
        b.ltcgExemptionApplied != null && b.ltcgExemptionApplied! > 0
            ? 'after ₹1.25L LTCG relief'
            : 'statutory rates only',
        c.t2,
      ),
    ];
    return LayoutBuilder(
      builder: (context, box) => KpiGrid(
        cells: cells,
        perRow: box.maxWidth < 430
            ? 2
            : box.maxWidth < 760
            ? 3
            : 4,
        note: 'Realised on sold shares only. Open holdings and their '
            'unrealised gain are above; the two are never added together.',
      ),
    );
  }

  Widget _table(BuildContext context) {
    final c = context.colors;
    // The TDS column appears only once a funds ledger is imported: without
    // one there is no TDS figure at all, and a column of dashes would imply
    // the tax was zero rather than unknown.
    final withTds = widget.book.tds != null;
    final cols = <DenseCol>[
      const DenseCol('SYMBOL', 5, numeric: false),
      const DenseCol('QTY', 2),
      const DenseCol('AVG BUY', 3),
      const DenseCol('AVG SELL', 3),
      const DenseCol('REALISED', 3),
      const DenseCol('CHARGES', 3),
      if (withTds) const DenseCol('TDS', 3),
      const DenseCol('NET', 3),
      const DenseCol('NET %', 2),
    ];
    final ranked = widget.book.ranked;
    return DenseCard(
      clip: true,
      child: Column(
        children: [
          denseTableHeader(
            context,
            icon: LucideIcons.receipt,
            accent: c.blue,
            title: 'BY POSITION',
            subtitle: 'worst first · tap a row for its lots',
          ),
          denseColumnHeader(context, cols),
          for (var i = 0; i < ranked.length; i++) ...[
            DenseRow(
              cols: cols,
              alt: i.isOdd,
              highlighted: _open.contains(ranked[i].symbol),
              onTap: () => setState(() {
                final sym = ranked[i].symbol;
                _open.contains(sym) ? _open.remove(sym) : _open.add(sym);
              }),
              cells: _symbolCells(context, ranked[i], withTds: withTds),
            ),
            if (_open.contains(ranked[i].symbol))
              _lots(context, ranked[i]),
          ],
          _footer(context, cols, withTds: withTds),
        ],
      ),
    );
  }

  List<Widget> _symbolCells(
    BuildContext context,
    ClosedSymbol s, {
    bool withTds = false,
  }) {
    final c = context.colors;
    final net = s.net ?? 0;
    final tone = net > 0
        ? c.up
        : net < 0
        ? c.dn
        : c.t2;
    // A row where the broker and the FIFO reconstruction disagree is the one
    // worth looking at: the ledger is missing trades for it. Nothing is
    // silently reconciled, so the row is marked instead.
    final mismatch = s.realizedAgrees == false;
    return [
      DInstrument(
        symbol: s.symbol,
        sub: mismatch
            ? 'ledger disagrees with broker'
            : s.lastSell == null
            ? '${s.trades} lots'
            : 'last sold ${s.lastSell}',
        up: net >= 0,
        spine: mismatch ? c.gold : tone,
        ellipsis: true,
      ),
      denseNum(context, s.qtyClosed.toStringAsFixed(0), c.t2),
      denseNum(context, _price(s.avgBuyPrice), c.t2),
      denseNum(context, _price(s.avgSellPrice), c.t2),
      denseNum(
        context,
        _signed(s.realized),
        mismatch ? c.gold : c.t2,
        bold: s.isMeasured,
      ),
      denseNum(context, _money(s.chargesEstimated), c.t3),
      // TDS traced to this position from the ledger's own dates. A dash means
      // nothing was withheld on it, not that the figure is unknown — the
      // column only exists when a ledger has been imported.
      if (withTds)
        denseNum(
          context,
          s.tdsAttributed > 0 ? _money(s.tdsAttributed) : '—',
          s.tdsAttributed > 0 ? c.dn : c.t3,
        ),
      denseNum(context, _signed(s.net), tone, bold: true),
      denseNum(context, _pct(s.netPct), tone),
    ];
  }

  /// The per-lot detail: every FIFO round trip that made up the row above.
  Widget _lots(BuildContext context, ClosedSymbol s) {
    final c = context.colors;
    final lots = [...s.lots]
      ..sort((a, b) => (b.sellDate ?? '').compareTo(a.sellDate ?? ''));
    return Container(
      width: double.infinity,
      color: c.bg3,
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                '${s.symbol} · ${lots.length} ROUND TRIPS',
                style: AppTextStyles.labelXs(c.t3),
              ),
              const Spacer(),
              if (s.stillOpenQty > 0)
                Text(
                  '${s.stillOpenQty.toStringAsFixed(0)} still held',
                  style: AppTextStyles.captionXs(c.t3),
                ),
            ],
          ),
          const SizedBox(height: 8),
          for (final lot in lots.take(30))
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                children: [
                  SizedBox(
                    width: 44,
                    child: Text(
                      lot.qty.toStringAsFixed(0),
                      style: AppTextStyles.monoXs(c.t2),
                    ),
                  ),
                  Expanded(
                    flex: 5,
                    child: Text(
                      '${lot.buyDate ?? '—'} @ ${_price(lot.buyPrice)}'
                      '  →  ${lot.sellDate ?? '—'} @ ${_price(lot.sellPrice)}',
                      style: AppTextStyles.monoXs(c.t2),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const SizedBox(width: 6),
                  SizedBox(
                    width: 42,
                    child: Text(
                      _days(lot.daysHeld),
                      style: AppTextStyles.monoXs(c.t3),
                      textAlign: TextAlign.right,
                    ),
                  ),
                  const SizedBox(width: 6),
                  SizedBox(
                    width: 46,
                    child: Align(
                      alignment: Alignment.centerRight,
                      child: _tag(
                        context,
                        lot.isLongTerm ? 'LT' : 'ST',
                        lot.isLongTerm ? c.blue : c.t3,
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    flex: 2,
                    child: Text(
                      _signed(lot.netPnlEstimated),
                      style: AppTextStyles.mono(
                        (lot.netPnlEstimated ?? 0) >= 0 ? c.up : c.dn,
                      ).copyWith(fontSize: 11),
                      textAlign: TextAlign.right,
                      maxLines: 1,
                    ),
                  ),
                ],
              ),
            ),
          if (lots.length > 30)
            Text(
              '${lots.length - 30} more round trips not listed',
              style: AppTextStyles.captionXs(c.t3),
            ),
        ],
      ),
    );
  }

  Widget _footer(
    BuildContext context,
    List<DenseCol> cols, {
    bool withTds = false,
  }) {
    final c = context.colors;
    final b = widget.book;
    final tone = (b.net ?? 0) >= 0 ? c.up : c.dn;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
      decoration: BoxDecoration(
        color: c.bg3,
        border: Border(top: BorderSide(color: c.bd)),
      ),
      child: Row(
        children: [
          Expanded(
            flex: cols[0].flex,
            child: denseFootLabel(context, 'TOTAL REALISED'),
          ),
          Expanded(flex: cols[1].flex, child: const SizedBox()),
          Expanded(flex: cols[2].flex, child: const SizedBox()),
          Expanded(
            flex: cols[3].flex,
            child: denseNum(context, _money(b.sellValue), c.t3),
          ),
          Expanded(
            flex: cols[4].flex,
            child: denseNum(context, _signed(b.realized), c.t2,
                bold: b.isMeasured),
          ),
          Expanded(
            flex: cols[5].flex,
            child: denseNum(context, _money(b.chargesEstimated), c.t3),
          ),
          if (withTds)
            Expanded(
              flex: cols[6].flex,
              child: denseNum(context, _money(b.tdsAttributedTotal), c.dn),
            ),
          Expanded(
            flex: cols[withTds ? 7 : 6].flex,
            child: denseNum(context, _signed(b.net), tone, bold: true),
          ),
          Expanded(
            flex: cols[withTds ? 8 : 7].flex,
            // The percentage is deliberately blank once TDS is in the total:
            // it was computed on cost before tax, and quietly reusing it
            // beside a TDS-inclusive net would misstate the return.
            child: denseNum(
              context,
              withTds ? '—' : _pct(b.netPnlPctEstimated),
              tone,
            ),
          ),
        ],
      ),
    );
  }

  Widget _tag(BuildContext context, String text, Color tone) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
    decoration: BoxDecoration(
      color: tone.withValues(alpha: 0.10),
      border: Border.all(color: tone.withValues(alpha: 0.22)),
      borderRadius: BorderRadius.circular(3),
    ),
    child: Text(text, style: AppTextStyles.labelXs(tone)),
  );

  Widget _flag(BuildContext context, String text, Color tone) => Container(
    width: double.infinity,
    padding: const EdgeInsets.fromLTRB(10, 8, 10, 9),
    decoration: BoxDecoration(
      color: tone.withValues(alpha: 0.07),
      border: Border.all(color: tone.withValues(alpha: 0.20)),
      borderRadius: BorderRadius.circular(6),
    ),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(LucideIcons.info, size: 12, color: tone),
        const SizedBox(width: 8),
        Expanded(
          child: Text(text, style: AppTextStyles.captionXs(context.colors.t3)),
        ),
      ],
    ),
  );

  Widget _pillButton(
    BuildContext context,
    String label,
    IconData icon,
    VoidCallback onTap,
  ) {
    final c = context.colors;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(5),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: c.blue.withValues(alpha: 0.12),
          border: Border.all(color: c.blue.withValues(alpha: 0.28)),
          borderRadius: BorderRadius.circular(5),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 12, color: c.blue),
            const SizedBox(width: 6),
            Text(
              label,
              style: AppTextStyles.bodyBold(c.blue).copyWith(fontSize: 11),
            ),
          ],
        ),
      ),
    );
  }
}
