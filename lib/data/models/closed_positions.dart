/// Realised P&L on shares already sold, as returned by
/// `/api/portfolio/closed-positions`.
///
/// The backend keeps three kinds of number apart and so does this model, right
/// down to the field names: buy/sell/quantity are **measured** from the
/// tradebook, `chargesEstimated` and everything derived from it is
/// **estimated** from the statutory rate card, and `taxIndicative` is an
/// arithmetic illustration rather than a tax computation. A field that the
/// backend could not fill stays null — never zero.
library;

double? closedNumber(dynamic value) {
  final n = value is num ? value.toDouble() : double.tryParse('$value');
  return n != null && n.isFinite ? n : null;
}

int closedInt(dynamic value) =>
    value is num ? value.toInt() : int.tryParse('$value') ?? 0;

String? closedText(dynamic value) {
  final s = value?.toString().trim();
  return s == null || s.isEmpty || s == 'null' ? null : s;
}

/// One FIFO round trip: a buy lot matched against the sell that closed it.
class ClosedLot {
  final String symbol;
  final double qty;
  final String? buyDate, sellDate;
  final double? buyPrice, sellPrice, buyValue, sellValue;
  final double? grossPnl, grossPnlPct, chargesEstimated, netPnlEstimated;
  final int daysHeld;

  /// 'short' or 'long' on the 12-month listed-equity rule.
  final String term;

  const ClosedLot({
    required this.symbol,
    required this.qty,
    required this.daysHeld,
    required this.term,
    this.buyDate,
    this.sellDate,
    this.buyPrice,
    this.sellPrice,
    this.buyValue,
    this.sellValue,
    this.grossPnl,
    this.grossPnlPct,
    this.chargesEstimated,
    this.netPnlEstimated,
  });

  factory ClosedLot.fromJson(Map<String, dynamic> j) => ClosedLot(
    symbol: closedText(j['symbol']) ?? '—',
    qty: closedNumber(j['qty']) ?? 0,
    daysHeld: closedInt(j['days_held']),
    term: closedText(j['term']) ?? 'short',
    buyDate: closedText(j['buy_date']),
    sellDate: closedText(j['sell_date']),
    buyPrice: closedNumber(j['buy_price']),
    sellPrice: closedNumber(j['sell_price']),
    buyValue: closedNumber(j['buy_value']),
    sellValue: closedNumber(j['sell_value']),
    grossPnl: closedNumber(j['gross_pnl']),
    grossPnlPct: closedNumber(j['gross_pnl_pct']),
    chargesEstimated: closedNumber(j['charges_estimated']),
    netPnlEstimated: closedNumber(j['net_pnl_estimated']),
  );

  bool get isLongTerm => term == 'long';
}

/// Every closed lot for one company, plus that company's rollup.
class ClosedSymbol {
  final String symbol;
  final int trades;
  final double qtyClosed;
  final double? buyValue, sellValue, grossPnl;
  final double? chargesEstimated, dpChargesEstimated;
  final double? netPnlEstimated, netPnlPctEstimated;
  final double unmatchedSellQty, stillOpenQty;
  final String? firstBuy, lastSell;
  final List<ClosedLot> lots;

  /// What the broker's own P&L statement says this position realised, when a
  /// statement covers it. Measured, not reconstructed — preferred over
  /// [grossPnl] for display, while both stay visible for comparison.
  final double? realizedBroker;

  /// 'broker_statement' or 'ledger_fifo'.
  final String realizedSource;

  /// Whether the FIFO reconstruction and the broker agree (null if no
  /// statement covers this symbol). False means the ledger is missing trades.
  final bool? realizedAgrees;

  /// 'broker_statement' when Console itemised the DP charge for this symbol.
  final String dpChargesSource;

  /// TDS traced to this position from the funds ledger, and how it got here:
  /// 'date_matched' (one position traded that day), 'apportioned' (several
  /// did, split by sell value) or 'none'.
  final double tdsAttributed;
  final String tdsSource;

  /// Net after charges AND the TDS withheld on this position. Null until a
  /// ledger is imported, because TDS appears in no other export.
  final double? netAfterTds, netAfterTdsPct;

  const ClosedSymbol({
    required this.symbol,
    required this.trades,
    required this.qtyClosed,
    required this.lots,
    this.buyValue,
    this.sellValue,
    this.grossPnl,
    this.chargesEstimated,
    this.dpChargesEstimated,
    this.netPnlEstimated,
    this.netPnlPctEstimated,
    this.unmatchedSellQty = 0,
    this.stillOpenQty = 0,
    this.firstBuy,
    this.lastSell,
    this.realizedBroker,
    this.realizedSource = 'ledger_fifo',
    this.realizedAgrees,
    this.dpChargesSource = 'estimated',
    this.tdsAttributed = 0,
    this.tdsSource = 'none',
    this.netAfterTds,
    this.netAfterTdsPct,
  });

  factory ClosedSymbol.fromJson(Map<String, dynamic> j) => ClosedSymbol(
    symbol: closedText(j['symbol']) ?? '—',
    trades: closedInt(j['trades']),
    qtyClosed: closedNumber(j['qty_closed']) ?? 0,
    buyValue: closedNumber(j['buy_value']),
    sellValue: closedNumber(j['sell_value']),
    grossPnl: closedNumber(j['gross_pnl']),
    chargesEstimated: closedNumber(j['charges_estimated']),
    dpChargesEstimated: closedNumber(j['dp_charges_estimated']),
    netPnlEstimated: closedNumber(j['net_pnl_estimated']),
    netPnlPctEstimated: closedNumber(j['net_pnl_pct_estimated']),
    unmatchedSellQty: closedNumber(j['unmatched_sell_qty']) ?? 0,
    stillOpenQty: closedNumber(j['still_open_qty']) ?? 0,
    firstBuy: closedText(j['first_buy']),
    lastSell: closedText(j['last_sell']),
    lots: [
      for (final l in (j['lots'] as List? ?? const []))
        if (l is Map) ClosedLot.fromJson(Map<String, dynamic>.from(l)),
    ],
    realizedBroker: closedNumber(j['realized_broker']),
    realizedSource: closedText(j['realized_source']) ?? 'ledger_fifo',
    realizedAgrees: j['realized_agrees'] is bool
        ? j['realized_agrees'] as bool
        : null,
    dpChargesSource: closedText(j['dp_charges_source']) ?? 'estimated',
    tdsAttributed: closedNumber(j['tds_attributed']) ?? 0,
    tdsSource: closedText(j['tds_source']) ?? 'none',
    netAfterTds: closedNumber(j['net_after_tds']),
    netAfterTdsPct: closedNumber(j['net_after_tds_pct']),
  );

  /// The net to show: after TDS when a ledger is in, else after charges only.
  double? get net => netAfterTds ?? netPnlEstimated;
  double? get netPct => netAfterTdsPct ?? netPnlPctEstimated;

  /// The realised figure to show: the broker's when it exists, else FIFO.
  double? get realized => realizedBroker ?? grossPnl;
  bool get isMeasured => realizedSource == 'broker_statement';

  /// Weighted average prices, for a row that summarises many lots.
  double? get avgBuyPrice =>
      qtyClosed > 0 && buyValue != null ? buyValue! / qtyClosed : null;
  double? get avgSellPrice =>
      qtyClosed > 0 && sellValue != null ? sellValue! / qtyClosed : null;
}

/// One charge head from the broker's statement — brokerage, STT, GST...
class ChargeHead {
  final String head;
  final double amount;
  const ChargeHead(this.head, this.amount);
}

/// One imported P&L period.
class StatementPeriod {
  final String period;
  final String? from, to;
  final double? realizedPnl, chargesActual;
  final int symbolsClosed;
  const StatementPeriod({
    required this.period,
    this.from,
    this.to,
    this.realizedPnl,
    this.chargesActual,
    this.symbolsClosed = 0,
  });

  factory StatementPeriod.fromJson(Map<String, dynamic> j) => StatementPeriod(
    period: closedText(j['period']) ?? '—',
    from: closedText(j['from']),
    to: closedText(j['to']),
    realizedPnl: closedNumber(j['realized_pnl']),
    chargesActual: closedNumber(j['charges_actual']),
    symbolsClosed: closedInt(j['symbols_closed']),
  );

  /// 'Oct 2025 – Sep 2026' style label, falling back to the raw key.
  String get label => from == null || to == null ? period : '$from → $to';
}

/// What the imported Kite Console statements measure, as opposed to what this
/// app reconstructs from the tradebook.
///
/// [chargesActual] covers **every** trade in the period, including the buys of
/// positions still held, so it is the cost of trading over that window and not
/// the cost of the closed lots. [periodNet] is named accordingly and must
/// never be relabelled "net realised".
class ClosedStatement {
  final List<StatementPeriod> periods;
  final List<ChargeHead> chargesByHead;
  final String? coversFrom, coversTo, basis;
  final double? realizedPnl, chargesActual, otherCreditDebit, periodNet;
  final double? unrealizedPnl;
  final List<List<String>> overlappingPeriods;

  const ClosedStatement({
    this.periods = const [],
    this.chargesByHead = const [],
    this.coversFrom,
    this.coversTo,
    this.basis,
    this.realizedPnl,
    this.chargesActual,
    this.otherCreditDebit,
    this.periodNet,
    this.unrealizedPnl,
    this.overlappingPeriods = const [],
  });

  static ClosedStatement? fromJson(dynamic json) {
    if (json is! Map) return null;
    final j = Map<String, dynamic>.from(json);
    return ClosedStatement(
      periods: [
        for (final p in (j['periods'] as List? ?? const []))
          if (p is Map) StatementPeriod.fromJson(Map<String, dynamic>.from(p)),
      ],
      chargesByHead: [
        for (final c in (j['charges_by_head'] as List? ?? const []))
          if (c is Map && closedNumber(c['amount']) != null)
            ChargeHead(
              closedText(c['head']) ?? '—',
              closedNumber(c['amount'])!,
            ),
      ],
      coversFrom: closedText(j['covers_from']),
      coversTo: closedText(j['covers_to']),
      basis: closedText(j['basis']),
      realizedPnl: closedNumber(j['realized_pnl']),
      chargesActual: closedNumber(j['charges_actual']),
      otherCreditDebit: closedNumber(j['other_credit_debit']),
      periodNet: closedNumber(j['period_net']),
      unrealizedPnl: closedNumber(j['unrealized_pnl']),
      overlappingPeriods: [
        for (final pair in (j['overlapping_periods'] as List? ?? const []))
          if (pair is List) [for (final v in pair) '$v'],
      ],
    );
  }

  bool get hasOverlap => overlappingPeriods.isNotEmpty;

  /// Charge heads that actually cost something, largest first. A zero head
  /// (Clearing Charges, or IGST on an intra-state account) is real information
  /// but not worth a row.
  List<ChargeHead> get chargesRanked =>
      chargesByHead.where((c) => c.amount.abs() > 0.005).toList()
        ..sort((a, b) => b.amount.compareTo(a.amount));
}

/// One TDS line from the Console funds ledger.
class TdsEntry {
  final String particulars;
  final String? date;
  final double debit, credit;

  /// 'tds', 'tds_provisional_blocked' or 'tds_provisional_reversed'.
  final String kind;

  const TdsEntry({
    required this.particulars,
    required this.kind,
    this.date,
    this.debit = 0,
    this.credit = 0,
  });

  factory TdsEntry.fromJson(Map<String, dynamic> j) => TdsEntry(
    particulars: closedText(j['particulars']) ?? '—',
    kind: closedText(j['kind']) ?? 'tds',
    date: closedText(j['date']),
    debit: closedNumber(j['debit']) ?? 0,
    credit: closedNumber(j['credit']) ?? 0,
  );

  bool get isProvisional => kind.startsWith('tds_provisional');
  bool get isReversal => kind == 'tds_provisional_reversed';

  /// Money out is positive; a reversal is money back.
  double get net => debit - credit;
}

/// TDS, from the Console funds ledger — the only export that carries it.
///
/// [deducted] is the sole figure that is a cost. A provisional amount is
/// blocked against a pending liability and normally reversed within days, so
/// it is held separately and never added to a cost: a blocked/reversed pair
/// can be many times larger than the tax genuinely deducted, so summing them
/// would overstate the tax by an order of magnitude or more.
class ClosedTds {
  final double deducted;
  final double provisionalBlocked, provisionalReversed, provisionalOutstanding;
  final List<TdsEntry> entries;
  final String? coversFrom, coversTo, basis;
  final List<List<String>> overlappingPeriods;

  const ClosedTds({
    this.deducted = 0,
    this.provisionalBlocked = 0,
    this.provisionalReversed = 0,
    this.provisionalOutstanding = 0,
    this.entries = const [],
    this.coversFrom,
    this.coversTo,
    this.basis,
    this.overlappingPeriods = const [],
  });

  static ClosedTds? fromJson(dynamic json) {
    if (json is! Map) return null;
    final j = Map<String, dynamic>.from(json);
    return ClosedTds(
      deducted: closedNumber(j['deducted']) ?? 0,
      provisionalBlocked: closedNumber(j['provisional_blocked']) ?? 0,
      provisionalReversed: closedNumber(j['provisional_reversed']) ?? 0,
      provisionalOutstanding: closedNumber(j['provisional_outstanding']) ?? 0,
      entries: [
        for (final e in (j['entries'] as List? ?? const []))
          if (e is Map) TdsEntry.fromJson(Map<String, dynamic>.from(e)),
      ],
      coversFrom: closedText(j['covers_from']),
      coversTo: closedText(j['covers_to']),
      basis: closedText(j['basis']),
      overlappingPeriods: [
        for (final pair in (j['overlapping_periods'] as List? ?? const []))
          if (pair is List) [for (final v in pair) '$v'],
      ],
    );
  }

  bool get hasOverlap => overlappingPeriods.isNotEmpty;

  /// True when something is still withheld and not yet reversed.
  bool get hasOutstanding => provisionalOutstanding.abs() > 0.005;

  /// Was any provisional amount seen at all?
  bool get hasProvisional =>
      provisionalBlocked.abs() > 0.005 || provisionalReversed.abs() > 0.005;
}

/// FIFO reconstruction against the broker's own numbers.
class ClosedReconciliation {
  final double? ledgerFifoGross, brokerRealized;
  final double? chargesEstimated, chargesActual, chargesEstimateError;
  final bool? grossAgrees;
  final String? note;

  const ClosedReconciliation({
    this.ledgerFifoGross,
    this.brokerRealized,
    this.chargesEstimated,
    this.chargesActual,
    this.chargesEstimateError,
    this.grossAgrees,
    this.note,
  });

  static ClosedReconciliation? fromJson(dynamic json) {
    if (json is! Map) return null;
    final j = Map<String, dynamic>.from(json);
    return ClosedReconciliation(
      ledgerFifoGross: closedNumber(j['ledger_fifo_gross']),
      brokerRealized: closedNumber(j['broker_realized']),
      chargesEstimated: closedNumber(j['charges_estimated']),
      chargesActual: closedNumber(j['charges_actual']),
      chargesEstimateError: closedNumber(j['charges_estimate_error']),
      grossAgrees: j['gross_agrees'] is bool ? j['gross_agrees'] as bool : null,
      note: closedText(j['note']),
    );
  }
}

/// The whole realised book.
class ClosedBook {
  final List<ClosedSymbol> symbols;
  final int symbolsClosed, trades, wins, losses;
  final double? buyValue, sellValue, grossPnl, chargesEstimated;
  final double? netPnlEstimated, netPnlPctEstimated;
  final double? shortTermNet, longTermNet, winRatePct;
  final double unmatchedSellQty;
  final double? taxIndicative, ltcgExemptionApplied;
  final String? asOf, chargesNote, taxBasis;

  /// Book totals for TDS, once a ledger is imported.
  final double? tdsAttributedTotal, netAfterTdsTotal;

  /// Present once a Kite Console P&L statement has been imported. While null,
  /// every charge figure on this book is a rate-card estimate.
  final ClosedStatement? statement;
  final ClosedReconciliation? reconciliation;

  /// Present once a Console funds ledger has been imported. TDS appears in no
  /// other export, so while this is null the cost figures omit it entirely.
  final ClosedTds? tds;

  const ClosedBook({
    this.symbols = const [],
    this.symbolsClosed = 0,
    this.trades = 0,
    this.wins = 0,
    this.losses = 0,
    this.buyValue,
    this.sellValue,
    this.grossPnl,
    this.chargesEstimated,
    this.netPnlEstimated,
    this.netPnlPctEstimated,
    this.shortTermNet,
    this.longTermNet,
    this.winRatePct,
    this.unmatchedSellQty = 0,
    this.taxIndicative,
    this.ltcgExemptionApplied,
    this.asOf,
    this.chargesNote,
    this.taxBasis,
    this.statement,
    this.reconciliation,
    this.tds,
    this.tdsAttributedTotal,
    this.netAfterTdsTotal,
  });

  factory ClosedBook.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const ClosedBook();
    final t = json['totals'] is Map
        ? Map<String, dynamic>.from(json['totals'] as Map)
        : const <String, dynamic>{};
    final tax = json['tax_indicative'] is Map
        ? Map<String, dynamic>.from(json['tax_indicative'] as Map)
        : const <String, dynamic>{};
    final charges = json['charges_basis'] is Map
        ? Map<String, dynamic>.from(json['charges_basis'] as Map)
        : const <String, dynamic>{};
    return ClosedBook(
      symbols: [
        for (final s in (json['symbols'] as List? ?? const []))
          if (s is Map) ClosedSymbol.fromJson(Map<String, dynamic>.from(s)),
      ],
      symbolsClosed: closedInt(t['symbols_closed']),
      trades: closedInt(t['trades']),
      wins: closedInt(t['wins']),
      losses: closedInt(t['losses']),
      buyValue: closedNumber(t['buy_value']),
      sellValue: closedNumber(t['sell_value']),
      grossPnl: closedNumber(t['gross_pnl']),
      chargesEstimated: closedNumber(t['charges_estimated']),
      netPnlEstimated: closedNumber(t['net_pnl_estimated']),
      netPnlPctEstimated: closedNumber(t['net_pnl_pct_estimated']),
      shortTermNet: closedNumber(t['short_term_net']),
      longTermNet: closedNumber(t['long_term_net']),
      winRatePct: closedNumber(t['win_rate_pct']),
      unmatchedSellQty: closedNumber(t['unmatched_sell_qty']) ?? 0,
      taxIndicative: closedNumber(tax['tax']),
      ltcgExemptionApplied: closedNumber(tax['ltcg_exemption_applied']),
      asOf: closedText(json['as_of']),
      chargesNote: closedText(charges['note']),
      taxBasis: closedText(tax['basis']),
      statement: ClosedStatement.fromJson(json['statement']),
      reconciliation: ClosedReconciliation.fromJson(json['reconciliation']),
      tds: ClosedTds.fromJson(json['tds']),
      tdsAttributedTotal: closedNumber(t['tds_attributed']),
      netAfterTdsTotal: closedNumber(t['net_after_tds']),
    );
  }

  /// Book net to show: after TDS when a ledger is in, else after charges.
  double? get net => netAfterTdsTotal ?? netPnlEstimated;

  /// True once the broker's own statement backs these figures.
  bool get isMeasured => statement != null && statement!.periods.isNotEmpty;

  /// The realised total to headline: the broker's when a statement covers it.
  double? get realized => statement?.realizedPnl ?? grossPnl;

  /// Charges to headline, and whether they were billed or computed.
  double? get charges => statement?.chargesActual ?? chargesEstimated;
  bool get chargesAreMeasured => statement?.chargesActual != null;

  /// Charges plus TDS — the full measured cost of trading the period, when
  /// both exports are present. Kept as a separate getter because Console
  /// bills TDS on its own voucher and its charge block excludes it, so the
  /// two must never be silently merged into one "charges" number.
  double? get costWithTds {
    final base = charges;
    if (base == null) return null;
    return tds == null ? base : base + tds!.deducted;
  }

  bool get isEmpty => symbols.isEmpty;

  /// Symbols worst-first: a closed book is reviewed for what went wrong.
  List<ClosedSymbol> get ranked {
    final out = [...symbols];
    out.sort((a, b) => (a.net ?? 0).compareTo(b.net ?? 0));
    return out;
  }

  /// Every lot across every symbol, most recently closed first.
  List<ClosedLot> get recentLots {
    final out = [for (final s in symbols) ...s.lots];
    out.sort((a, b) => (b.sellDate ?? '').compareTo(a.sellDate ?? ''));
    return out;
  }
}
