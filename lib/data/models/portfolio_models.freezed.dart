// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'portfolio_models.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// dart format off
T _$identity<T>(T value) => value;

/// @nodoc
mixin _$StockHolding {

 String get symbol; String get name; String get sector; int get shares;@JsonKey(name: 'avg_cost') double get avgCost;@JsonKey(name: 'current_price') double get currentPrice; double get invested; double get pnl;@JsonKey(name: 'net_chg') double get netChg;@JsonKey(name: 'day_chg') double get dayChg;@JsonKey(name: 'total_value') double get totalValue; String get currency; String? get error;// Enriched by providers
 String get signal;
/// Create a copy of StockHolding
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$StockHoldingCopyWith<StockHolding> get copyWith => _$StockHoldingCopyWithImpl<StockHolding>(this as StockHolding, _$identity);

  /// Serializes this StockHolding to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is StockHolding&&(identical(other.symbol, symbol) || other.symbol == symbol)&&(identical(other.name, name) || other.name == name)&&(identical(other.sector, sector) || other.sector == sector)&&(identical(other.shares, shares) || other.shares == shares)&&(identical(other.avgCost, avgCost) || other.avgCost == avgCost)&&(identical(other.currentPrice, currentPrice) || other.currentPrice == currentPrice)&&(identical(other.invested, invested) || other.invested == invested)&&(identical(other.pnl, pnl) || other.pnl == pnl)&&(identical(other.netChg, netChg) || other.netChg == netChg)&&(identical(other.dayChg, dayChg) || other.dayChg == dayChg)&&(identical(other.totalValue, totalValue) || other.totalValue == totalValue)&&(identical(other.currency, currency) || other.currency == currency)&&(identical(other.error, error) || other.error == error)&&(identical(other.signal, signal) || other.signal == signal));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,symbol,name,sector,shares,avgCost,currentPrice,invested,pnl,netChg,dayChg,totalValue,currency,error,signal);

@override
String toString() {
  return 'StockHolding(symbol: $symbol, name: $name, sector: $sector, shares: $shares, avgCost: $avgCost, currentPrice: $currentPrice, invested: $invested, pnl: $pnl, netChg: $netChg, dayChg: $dayChg, totalValue: $totalValue, currency: $currency, error: $error, signal: $signal)';
}


}

/// @nodoc
abstract mixin class $StockHoldingCopyWith<$Res>  {
  factory $StockHoldingCopyWith(StockHolding value, $Res Function(StockHolding) _then) = _$StockHoldingCopyWithImpl;
@useResult
$Res call({
 String symbol, String name, String sector, int shares,@JsonKey(name: 'avg_cost') double avgCost,@JsonKey(name: 'current_price') double currentPrice, double invested, double pnl,@JsonKey(name: 'net_chg') double netChg,@JsonKey(name: 'day_chg') double dayChg,@JsonKey(name: 'total_value') double totalValue, String currency, String? error, String signal
});




}
/// @nodoc
class _$StockHoldingCopyWithImpl<$Res>
    implements $StockHoldingCopyWith<$Res> {
  _$StockHoldingCopyWithImpl(this._self, this._then);

  final StockHolding _self;
  final $Res Function(StockHolding) _then;

/// Create a copy of StockHolding
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? symbol = null,Object? name = null,Object? sector = null,Object? shares = null,Object? avgCost = null,Object? currentPrice = null,Object? invested = null,Object? pnl = null,Object? netChg = null,Object? dayChg = null,Object? totalValue = null,Object? currency = null,Object? error = freezed,Object? signal = null,}) {
  return _then(_self.copyWith(
symbol: null == symbol ? _self.symbol : symbol // ignore: cast_nullable_to_non_nullable
as String,name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,sector: null == sector ? _self.sector : sector // ignore: cast_nullable_to_non_nullable
as String,shares: null == shares ? _self.shares : shares // ignore: cast_nullable_to_non_nullable
as int,avgCost: null == avgCost ? _self.avgCost : avgCost // ignore: cast_nullable_to_non_nullable
as double,currentPrice: null == currentPrice ? _self.currentPrice : currentPrice // ignore: cast_nullable_to_non_nullable
as double,invested: null == invested ? _self.invested : invested // ignore: cast_nullable_to_non_nullable
as double,pnl: null == pnl ? _self.pnl : pnl // ignore: cast_nullable_to_non_nullable
as double,netChg: null == netChg ? _self.netChg : netChg // ignore: cast_nullable_to_non_nullable
as double,dayChg: null == dayChg ? _self.dayChg : dayChg // ignore: cast_nullable_to_non_nullable
as double,totalValue: null == totalValue ? _self.totalValue : totalValue // ignore: cast_nullable_to_non_nullable
as double,currency: null == currency ? _self.currency : currency // ignore: cast_nullable_to_non_nullable
as String,error: freezed == error ? _self.error : error // ignore: cast_nullable_to_non_nullable
as String?,signal: null == signal ? _self.signal : signal // ignore: cast_nullable_to_non_nullable
as String,
  ));
}

}


/// Adds pattern-matching-related methods to [StockHolding].
extension StockHoldingPatterns on StockHolding {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _StockHolding value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _StockHolding() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _StockHolding value)  $default,){
final _that = this;
switch (_that) {
case _StockHolding():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _StockHolding value)?  $default,){
final _that = this;
switch (_that) {
case _StockHolding() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String symbol,  String name,  String sector,  int shares, @JsonKey(name: 'avg_cost')  double avgCost, @JsonKey(name: 'current_price')  double currentPrice,  double invested,  double pnl, @JsonKey(name: 'net_chg')  double netChg, @JsonKey(name: 'day_chg')  double dayChg, @JsonKey(name: 'total_value')  double totalValue,  String currency,  String? error,  String signal)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _StockHolding() when $default != null:
return $default(_that.symbol,_that.name,_that.sector,_that.shares,_that.avgCost,_that.currentPrice,_that.invested,_that.pnl,_that.netChg,_that.dayChg,_that.totalValue,_that.currency,_that.error,_that.signal);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String symbol,  String name,  String sector,  int shares, @JsonKey(name: 'avg_cost')  double avgCost, @JsonKey(name: 'current_price')  double currentPrice,  double invested,  double pnl, @JsonKey(name: 'net_chg')  double netChg, @JsonKey(name: 'day_chg')  double dayChg, @JsonKey(name: 'total_value')  double totalValue,  String currency,  String? error,  String signal)  $default,) {final _that = this;
switch (_that) {
case _StockHolding():
return $default(_that.symbol,_that.name,_that.sector,_that.shares,_that.avgCost,_that.currentPrice,_that.invested,_that.pnl,_that.netChg,_that.dayChg,_that.totalValue,_that.currency,_that.error,_that.signal);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String symbol,  String name,  String sector,  int shares, @JsonKey(name: 'avg_cost')  double avgCost, @JsonKey(name: 'current_price')  double currentPrice,  double invested,  double pnl, @JsonKey(name: 'net_chg')  double netChg, @JsonKey(name: 'day_chg')  double dayChg, @JsonKey(name: 'total_value')  double totalValue,  String currency,  String? error,  String signal)?  $default,) {final _that = this;
switch (_that) {
case _StockHolding() when $default != null:
return $default(_that.symbol,_that.name,_that.sector,_that.shares,_that.avgCost,_that.currentPrice,_that.invested,_that.pnl,_that.netChg,_that.dayChg,_that.totalValue,_that.currency,_that.error,_that.signal);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _StockHolding implements StockHolding {
  const _StockHolding({required this.symbol, this.name = '', this.sector = 'Other', this.shares = 0, @JsonKey(name: 'avg_cost') this.avgCost = 0, @JsonKey(name: 'current_price') this.currentPrice = 0, this.invested = 0, this.pnl = 0, @JsonKey(name: 'net_chg') this.netChg = 0, @JsonKey(name: 'day_chg') this.dayChg = 0, @JsonKey(name: 'total_value') this.totalValue = 0, this.currency = 'INR', this.error = '', this.signal = 'HOLD'});
  factory _StockHolding.fromJson(Map<String, dynamic> json) => _$StockHoldingFromJson(json);

@override final  String symbol;
@override@JsonKey() final  String name;
@override@JsonKey() final  String sector;
@override@JsonKey() final  int shares;
@override@JsonKey(name: 'avg_cost') final  double avgCost;
@override@JsonKey(name: 'current_price') final  double currentPrice;
@override@JsonKey() final  double invested;
@override@JsonKey() final  double pnl;
@override@JsonKey(name: 'net_chg') final  double netChg;
@override@JsonKey(name: 'day_chg') final  double dayChg;
@override@JsonKey(name: 'total_value') final  double totalValue;
@override@JsonKey() final  String currency;
@override@JsonKey() final  String? error;
// Enriched by providers
@override@JsonKey() final  String signal;

/// Create a copy of StockHolding
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$StockHoldingCopyWith<_StockHolding> get copyWith => __$StockHoldingCopyWithImpl<_StockHolding>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$StockHoldingToJson(this, );
}

@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _StockHolding&&(identical(other.symbol, symbol) || other.symbol == symbol)&&(identical(other.name, name) || other.name == name)&&(identical(other.sector, sector) || other.sector == sector)&&(identical(other.shares, shares) || other.shares == shares)&&(identical(other.avgCost, avgCost) || other.avgCost == avgCost)&&(identical(other.currentPrice, currentPrice) || other.currentPrice == currentPrice)&&(identical(other.invested, invested) || other.invested == invested)&&(identical(other.pnl, pnl) || other.pnl == pnl)&&(identical(other.netChg, netChg) || other.netChg == netChg)&&(identical(other.dayChg, dayChg) || other.dayChg == dayChg)&&(identical(other.totalValue, totalValue) || other.totalValue == totalValue)&&(identical(other.currency, currency) || other.currency == currency)&&(identical(other.error, error) || other.error == error)&&(identical(other.signal, signal) || other.signal == signal));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,symbol,name,sector,shares,avgCost,currentPrice,invested,pnl,netChg,dayChg,totalValue,currency,error,signal);

@override
String toString() {
  return 'StockHolding(symbol: $symbol, name: $name, sector: $sector, shares: $shares, avgCost: $avgCost, currentPrice: $currentPrice, invested: $invested, pnl: $pnl, netChg: $netChg, dayChg: $dayChg, totalValue: $totalValue, currency: $currency, error: $error, signal: $signal)';
}


}

/// @nodoc
abstract mixin class _$StockHoldingCopyWith<$Res> implements $StockHoldingCopyWith<$Res> {
  factory _$StockHoldingCopyWith(_StockHolding value, $Res Function(_StockHolding) _then) = __$StockHoldingCopyWithImpl;
@override @useResult
$Res call({
 String symbol, String name, String sector, int shares,@JsonKey(name: 'avg_cost') double avgCost,@JsonKey(name: 'current_price') double currentPrice, double invested, double pnl,@JsonKey(name: 'net_chg') double netChg,@JsonKey(name: 'day_chg') double dayChg,@JsonKey(name: 'total_value') double totalValue, String currency, String? error, String signal
});




}
/// @nodoc
class __$StockHoldingCopyWithImpl<$Res>
    implements _$StockHoldingCopyWith<$Res> {
  __$StockHoldingCopyWithImpl(this._self, this._then);

  final _StockHolding _self;
  final $Res Function(_StockHolding) _then;

/// Create a copy of StockHolding
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? symbol = null,Object? name = null,Object? sector = null,Object? shares = null,Object? avgCost = null,Object? currentPrice = null,Object? invested = null,Object? pnl = null,Object? netChg = null,Object? dayChg = null,Object? totalValue = null,Object? currency = null,Object? error = freezed,Object? signal = null,}) {
  return _then(_StockHolding(
symbol: null == symbol ? _self.symbol : symbol // ignore: cast_nullable_to_non_nullable
as String,name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,sector: null == sector ? _self.sector : sector // ignore: cast_nullable_to_non_nullable
as String,shares: null == shares ? _self.shares : shares // ignore: cast_nullable_to_non_nullable
as int,avgCost: null == avgCost ? _self.avgCost : avgCost // ignore: cast_nullable_to_non_nullable
as double,currentPrice: null == currentPrice ? _self.currentPrice : currentPrice // ignore: cast_nullable_to_non_nullable
as double,invested: null == invested ? _self.invested : invested // ignore: cast_nullable_to_non_nullable
as double,pnl: null == pnl ? _self.pnl : pnl // ignore: cast_nullable_to_non_nullable
as double,netChg: null == netChg ? _self.netChg : netChg // ignore: cast_nullable_to_non_nullable
as double,dayChg: null == dayChg ? _self.dayChg : dayChg // ignore: cast_nullable_to_non_nullable
as double,totalValue: null == totalValue ? _self.totalValue : totalValue // ignore: cast_nullable_to_non_nullable
as double,currency: null == currency ? _self.currency : currency // ignore: cast_nullable_to_non_nullable
as String,error: freezed == error ? _self.error : error // ignore: cast_nullable_to_non_nullable
as String?,signal: null == signal ? _self.signal : signal // ignore: cast_nullable_to_non_nullable
as String,
  ));
}


}


/// @nodoc
mixin _$PortfolioData {

 String get status; String get currency;@JsonKey(name: 'data_source') String get dataSource;@JsonKey(name: 'kite_connected') bool get kiteConnected;@JsonKey(name: 'total_portfolio_value') double get totalPortfolioValue;@JsonKey(name: 'total_invested') double get totalInvested;@JsonKey(name: 'total_pnl') double get totalPnl;@JsonKey(name: 'total_pnl_pct') double get totalPnlPct; List<StockHolding> get holdings;
/// Create a copy of PortfolioData
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$PortfolioDataCopyWith<PortfolioData> get copyWith => _$PortfolioDataCopyWithImpl<PortfolioData>(this as PortfolioData, _$identity);

  /// Serializes this PortfolioData to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is PortfolioData&&(identical(other.status, status) || other.status == status)&&(identical(other.currency, currency) || other.currency == currency)&&(identical(other.dataSource, dataSource) || other.dataSource == dataSource)&&(identical(other.kiteConnected, kiteConnected) || other.kiteConnected == kiteConnected)&&(identical(other.totalPortfolioValue, totalPortfolioValue) || other.totalPortfolioValue == totalPortfolioValue)&&(identical(other.totalInvested, totalInvested) || other.totalInvested == totalInvested)&&(identical(other.totalPnl, totalPnl) || other.totalPnl == totalPnl)&&(identical(other.totalPnlPct, totalPnlPct) || other.totalPnlPct == totalPnlPct)&&const DeepCollectionEquality().equals(other.holdings, holdings));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,status,currency,dataSource,kiteConnected,totalPortfolioValue,totalInvested,totalPnl,totalPnlPct,const DeepCollectionEquality().hash(holdings));

@override
String toString() {
  return 'PortfolioData(status: $status, currency: $currency, dataSource: $dataSource, kiteConnected: $kiteConnected, totalPortfolioValue: $totalPortfolioValue, totalInvested: $totalInvested, totalPnl: $totalPnl, totalPnlPct: $totalPnlPct, holdings: $holdings)';
}


}

/// @nodoc
abstract mixin class $PortfolioDataCopyWith<$Res>  {
  factory $PortfolioDataCopyWith(PortfolioData value, $Res Function(PortfolioData) _then) = _$PortfolioDataCopyWithImpl;
@useResult
$Res call({
 String status, String currency,@JsonKey(name: 'data_source') String dataSource,@JsonKey(name: 'kite_connected') bool kiteConnected,@JsonKey(name: 'total_portfolio_value') double totalPortfolioValue,@JsonKey(name: 'total_invested') double totalInvested,@JsonKey(name: 'total_pnl') double totalPnl,@JsonKey(name: 'total_pnl_pct') double totalPnlPct, List<StockHolding> holdings
});




}
/// @nodoc
class _$PortfolioDataCopyWithImpl<$Res>
    implements $PortfolioDataCopyWith<$Res> {
  _$PortfolioDataCopyWithImpl(this._self, this._then);

  final PortfolioData _self;
  final $Res Function(PortfolioData) _then;

/// Create a copy of PortfolioData
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? status = null,Object? currency = null,Object? dataSource = null,Object? kiteConnected = null,Object? totalPortfolioValue = null,Object? totalInvested = null,Object? totalPnl = null,Object? totalPnlPct = null,Object? holdings = null,}) {
  return _then(_self.copyWith(
status: null == status ? _self.status : status // ignore: cast_nullable_to_non_nullable
as String,currency: null == currency ? _self.currency : currency // ignore: cast_nullable_to_non_nullable
as String,dataSource: null == dataSource ? _self.dataSource : dataSource // ignore: cast_nullable_to_non_nullable
as String,kiteConnected: null == kiteConnected ? _self.kiteConnected : kiteConnected // ignore: cast_nullable_to_non_nullable
as bool,totalPortfolioValue: null == totalPortfolioValue ? _self.totalPortfolioValue : totalPortfolioValue // ignore: cast_nullable_to_non_nullable
as double,totalInvested: null == totalInvested ? _self.totalInvested : totalInvested // ignore: cast_nullable_to_non_nullable
as double,totalPnl: null == totalPnl ? _self.totalPnl : totalPnl // ignore: cast_nullable_to_non_nullable
as double,totalPnlPct: null == totalPnlPct ? _self.totalPnlPct : totalPnlPct // ignore: cast_nullable_to_non_nullable
as double,holdings: null == holdings ? _self.holdings : holdings // ignore: cast_nullable_to_non_nullable
as List<StockHolding>,
  ));
}

}


/// Adds pattern-matching-related methods to [PortfolioData].
extension PortfolioDataPatterns on PortfolioData {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _PortfolioData value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _PortfolioData() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _PortfolioData value)  $default,){
final _that = this;
switch (_that) {
case _PortfolioData():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _PortfolioData value)?  $default,){
final _that = this;
switch (_that) {
case _PortfolioData() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String status,  String currency, @JsonKey(name: 'data_source')  String dataSource, @JsonKey(name: 'kite_connected')  bool kiteConnected, @JsonKey(name: 'total_portfolio_value')  double totalPortfolioValue, @JsonKey(name: 'total_invested')  double totalInvested, @JsonKey(name: 'total_pnl')  double totalPnl, @JsonKey(name: 'total_pnl_pct')  double totalPnlPct,  List<StockHolding> holdings)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _PortfolioData() when $default != null:
return $default(_that.status,_that.currency,_that.dataSource,_that.kiteConnected,_that.totalPortfolioValue,_that.totalInvested,_that.totalPnl,_that.totalPnlPct,_that.holdings);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String status,  String currency, @JsonKey(name: 'data_source')  String dataSource, @JsonKey(name: 'kite_connected')  bool kiteConnected, @JsonKey(name: 'total_portfolio_value')  double totalPortfolioValue, @JsonKey(name: 'total_invested')  double totalInvested, @JsonKey(name: 'total_pnl')  double totalPnl, @JsonKey(name: 'total_pnl_pct')  double totalPnlPct,  List<StockHolding> holdings)  $default,) {final _that = this;
switch (_that) {
case _PortfolioData():
return $default(_that.status,_that.currency,_that.dataSource,_that.kiteConnected,_that.totalPortfolioValue,_that.totalInvested,_that.totalPnl,_that.totalPnlPct,_that.holdings);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String status,  String currency, @JsonKey(name: 'data_source')  String dataSource, @JsonKey(name: 'kite_connected')  bool kiteConnected, @JsonKey(name: 'total_portfolio_value')  double totalPortfolioValue, @JsonKey(name: 'total_invested')  double totalInvested, @JsonKey(name: 'total_pnl')  double totalPnl, @JsonKey(name: 'total_pnl_pct')  double totalPnlPct,  List<StockHolding> holdings)?  $default,) {final _that = this;
switch (_that) {
case _PortfolioData() when $default != null:
return $default(_that.status,_that.currency,_that.dataSource,_that.kiteConnected,_that.totalPortfolioValue,_that.totalInvested,_that.totalPnl,_that.totalPnlPct,_that.holdings);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _PortfolioData implements PortfolioData {
  const _PortfolioData({this.status = 'success', this.currency = 'INR', @JsonKey(name: 'data_source') this.dataSource = 'yfinance', @JsonKey(name: 'kite_connected') this.kiteConnected = false, @JsonKey(name: 'total_portfolio_value') this.totalPortfolioValue = 0, @JsonKey(name: 'total_invested') this.totalInvested = 0, @JsonKey(name: 'total_pnl') this.totalPnl = 0, @JsonKey(name: 'total_pnl_pct') this.totalPnlPct = 0, final  List<StockHolding> holdings = const []}): _holdings = holdings;
  factory _PortfolioData.fromJson(Map<String, dynamic> json) => _$PortfolioDataFromJson(json);

@override@JsonKey() final  String status;
@override@JsonKey() final  String currency;
@override@JsonKey(name: 'data_source') final  String dataSource;
@override@JsonKey(name: 'kite_connected') final  bool kiteConnected;
@override@JsonKey(name: 'total_portfolio_value') final  double totalPortfolioValue;
@override@JsonKey(name: 'total_invested') final  double totalInvested;
@override@JsonKey(name: 'total_pnl') final  double totalPnl;
@override@JsonKey(name: 'total_pnl_pct') final  double totalPnlPct;
 final  List<StockHolding> _holdings;
@override@JsonKey() List<StockHolding> get holdings {
  if (_holdings is EqualUnmodifiableListView) return _holdings;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_holdings);
}


/// Create a copy of PortfolioData
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$PortfolioDataCopyWith<_PortfolioData> get copyWith => __$PortfolioDataCopyWithImpl<_PortfolioData>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$PortfolioDataToJson(this, );
}

@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _PortfolioData&&(identical(other.status, status) || other.status == status)&&(identical(other.currency, currency) || other.currency == currency)&&(identical(other.dataSource, dataSource) || other.dataSource == dataSource)&&(identical(other.kiteConnected, kiteConnected) || other.kiteConnected == kiteConnected)&&(identical(other.totalPortfolioValue, totalPortfolioValue) || other.totalPortfolioValue == totalPortfolioValue)&&(identical(other.totalInvested, totalInvested) || other.totalInvested == totalInvested)&&(identical(other.totalPnl, totalPnl) || other.totalPnl == totalPnl)&&(identical(other.totalPnlPct, totalPnlPct) || other.totalPnlPct == totalPnlPct)&&const DeepCollectionEquality().equals(other._holdings, _holdings));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,status,currency,dataSource,kiteConnected,totalPortfolioValue,totalInvested,totalPnl,totalPnlPct,const DeepCollectionEquality().hash(_holdings));

@override
String toString() {
  return 'PortfolioData(status: $status, currency: $currency, dataSource: $dataSource, kiteConnected: $kiteConnected, totalPortfolioValue: $totalPortfolioValue, totalInvested: $totalInvested, totalPnl: $totalPnl, totalPnlPct: $totalPnlPct, holdings: $holdings)';
}


}

/// @nodoc
abstract mixin class _$PortfolioDataCopyWith<$Res> implements $PortfolioDataCopyWith<$Res> {
  factory _$PortfolioDataCopyWith(_PortfolioData value, $Res Function(_PortfolioData) _then) = __$PortfolioDataCopyWithImpl;
@override @useResult
$Res call({
 String status, String currency,@JsonKey(name: 'data_source') String dataSource,@JsonKey(name: 'kite_connected') bool kiteConnected,@JsonKey(name: 'total_portfolio_value') double totalPortfolioValue,@JsonKey(name: 'total_invested') double totalInvested,@JsonKey(name: 'total_pnl') double totalPnl,@JsonKey(name: 'total_pnl_pct') double totalPnlPct, List<StockHolding> holdings
});




}
/// @nodoc
class __$PortfolioDataCopyWithImpl<$Res>
    implements _$PortfolioDataCopyWith<$Res> {
  __$PortfolioDataCopyWithImpl(this._self, this._then);

  final _PortfolioData _self;
  final $Res Function(_PortfolioData) _then;

/// Create a copy of PortfolioData
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? status = null,Object? currency = null,Object? dataSource = null,Object? kiteConnected = null,Object? totalPortfolioValue = null,Object? totalInvested = null,Object? totalPnl = null,Object? totalPnlPct = null,Object? holdings = null,}) {
  return _then(_PortfolioData(
status: null == status ? _self.status : status // ignore: cast_nullable_to_non_nullable
as String,currency: null == currency ? _self.currency : currency // ignore: cast_nullable_to_non_nullable
as String,dataSource: null == dataSource ? _self.dataSource : dataSource // ignore: cast_nullable_to_non_nullable
as String,kiteConnected: null == kiteConnected ? _self.kiteConnected : kiteConnected // ignore: cast_nullable_to_non_nullable
as bool,totalPortfolioValue: null == totalPortfolioValue ? _self.totalPortfolioValue : totalPortfolioValue // ignore: cast_nullable_to_non_nullable
as double,totalInvested: null == totalInvested ? _self.totalInvested : totalInvested // ignore: cast_nullable_to_non_nullable
as double,totalPnl: null == totalPnl ? _self.totalPnl : totalPnl // ignore: cast_nullable_to_non_nullable
as double,totalPnlPct: null == totalPnlPct ? _self.totalPnlPct : totalPnlPct // ignore: cast_nullable_to_non_nullable
as double,holdings: null == holdings ? _self._holdings : holdings // ignore: cast_nullable_to_non_nullable
as List<StockHolding>,
  ));
}


}


/// @nodoc
mixin _$MFTransaction {

 String get date; double get invested; double get redeemed; double get units; double get nav;
/// Create a copy of MFTransaction
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$MFTransactionCopyWith<MFTransaction> get copyWith => _$MFTransactionCopyWithImpl<MFTransaction>(this as MFTransaction, _$identity);

  /// Serializes this MFTransaction to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is MFTransaction&&(identical(other.date, date) || other.date == date)&&(identical(other.invested, invested) || other.invested == invested)&&(identical(other.redeemed, redeemed) || other.redeemed == redeemed)&&(identical(other.units, units) || other.units == units)&&(identical(other.nav, nav) || other.nav == nav));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,date,invested,redeemed,units,nav);

@override
String toString() {
  return 'MFTransaction(date: $date, invested: $invested, redeemed: $redeemed, units: $units, nav: $nav)';
}


}

/// @nodoc
abstract mixin class $MFTransactionCopyWith<$Res>  {
  factory $MFTransactionCopyWith(MFTransaction value, $Res Function(MFTransaction) _then) = _$MFTransactionCopyWithImpl;
@useResult
$Res call({
 String date, double invested, double redeemed, double units, double nav
});




}
/// @nodoc
class _$MFTransactionCopyWithImpl<$Res>
    implements $MFTransactionCopyWith<$Res> {
  _$MFTransactionCopyWithImpl(this._self, this._then);

  final MFTransaction _self;
  final $Res Function(MFTransaction) _then;

/// Create a copy of MFTransaction
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? date = null,Object? invested = null,Object? redeemed = null,Object? units = null,Object? nav = null,}) {
  return _then(_self.copyWith(
date: null == date ? _self.date : date // ignore: cast_nullable_to_non_nullable
as String,invested: null == invested ? _self.invested : invested // ignore: cast_nullable_to_non_nullable
as double,redeemed: null == redeemed ? _self.redeemed : redeemed // ignore: cast_nullable_to_non_nullable
as double,units: null == units ? _self.units : units // ignore: cast_nullable_to_non_nullable
as double,nav: null == nav ? _self.nav : nav // ignore: cast_nullable_to_non_nullable
as double,
  ));
}

}


/// Adds pattern-matching-related methods to [MFTransaction].
extension MFTransactionPatterns on MFTransaction {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _MFTransaction value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _MFTransaction() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _MFTransaction value)  $default,){
final _that = this;
switch (_that) {
case _MFTransaction():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _MFTransaction value)?  $default,){
final _that = this;
switch (_that) {
case _MFTransaction() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String date,  double invested,  double redeemed,  double units,  double nav)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _MFTransaction() when $default != null:
return $default(_that.date,_that.invested,_that.redeemed,_that.units,_that.nav);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String date,  double invested,  double redeemed,  double units,  double nav)  $default,) {final _that = this;
switch (_that) {
case _MFTransaction():
return $default(_that.date,_that.invested,_that.redeemed,_that.units,_that.nav);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String date,  double invested,  double redeemed,  double units,  double nav)?  $default,) {final _that = this;
switch (_that) {
case _MFTransaction() when $default != null:
return $default(_that.date,_that.invested,_that.redeemed,_that.units,_that.nav);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _MFTransaction implements MFTransaction {
  const _MFTransaction({required this.date, this.invested = 0, this.redeemed = 0, this.units = 0, this.nav = 0});
  factory _MFTransaction.fromJson(Map<String, dynamic> json) => _$MFTransactionFromJson(json);

@override final  String date;
@override@JsonKey() final  double invested;
@override@JsonKey() final  double redeemed;
@override@JsonKey() final  double units;
@override@JsonKey() final  double nav;

/// Create a copy of MFTransaction
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$MFTransactionCopyWith<_MFTransaction> get copyWith => __$MFTransactionCopyWithImpl<_MFTransaction>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$MFTransactionToJson(this, );
}

@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _MFTransaction&&(identical(other.date, date) || other.date == date)&&(identical(other.invested, invested) || other.invested == invested)&&(identical(other.redeemed, redeemed) || other.redeemed == redeemed)&&(identical(other.units, units) || other.units == units)&&(identical(other.nav, nav) || other.nav == nav));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,date,invested,redeemed,units,nav);

@override
String toString() {
  return 'MFTransaction(date: $date, invested: $invested, redeemed: $redeemed, units: $units, nav: $nav)';
}


}

/// @nodoc
abstract mixin class _$MFTransactionCopyWith<$Res> implements $MFTransactionCopyWith<$Res> {
  factory _$MFTransactionCopyWith(_MFTransaction value, $Res Function(_MFTransaction) _then) = __$MFTransactionCopyWithImpl;
@override @useResult
$Res call({
 String date, double invested, double redeemed, double units, double nav
});




}
/// @nodoc
class __$MFTransactionCopyWithImpl<$Res>
    implements _$MFTransactionCopyWith<$Res> {
  __$MFTransactionCopyWithImpl(this._self, this._then);

  final _MFTransaction _self;
  final $Res Function(_MFTransaction) _then;

/// Create a copy of MFTransaction
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? date = null,Object? invested = null,Object? redeemed = null,Object? units = null,Object? nav = null,}) {
  return _then(_MFTransaction(
date: null == date ? _self.date : date // ignore: cast_nullable_to_non_nullable
as String,invested: null == invested ? _self.invested : invested // ignore: cast_nullable_to_non_nullable
as double,redeemed: null == redeemed ? _self.redeemed : redeemed // ignore: cast_nullable_to_non_nullable
as double,units: null == units ? _self.units : units // ignore: cast_nullable_to_non_nullable
as double,nav: null == nav ? _self.nav : nav // ignore: cast_nullable_to_non_nullable
as double,
  ));
}


}


/// @nodoc
mixin _$MFFund {

@JsonKey(name: 'scheme_name') String get schemeName; String get category; String get folio; double get invested;@JsonKey(name: 'current_value') double get currentValue; double get units; double get nav;@JsonKey(name: 'avg_nav') double get avgNav;@JsonKey(name: 'return_pct') double get returnPct; double get xirr; List<MFTransaction> get transactions;
/// Create a copy of MFFund
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$MFFundCopyWith<MFFund> get copyWith => _$MFFundCopyWithImpl<MFFund>(this as MFFund, _$identity);

  /// Serializes this MFFund to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is MFFund&&(identical(other.schemeName, schemeName) || other.schemeName == schemeName)&&(identical(other.category, category) || other.category == category)&&(identical(other.folio, folio) || other.folio == folio)&&(identical(other.invested, invested) || other.invested == invested)&&(identical(other.currentValue, currentValue) || other.currentValue == currentValue)&&(identical(other.units, units) || other.units == units)&&(identical(other.nav, nav) || other.nav == nav)&&(identical(other.avgNav, avgNav) || other.avgNav == avgNav)&&(identical(other.returnPct, returnPct) || other.returnPct == returnPct)&&(identical(other.xirr, xirr) || other.xirr == xirr)&&const DeepCollectionEquality().equals(other.transactions, transactions));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,schemeName,category,folio,invested,currentValue,units,nav,avgNav,returnPct,xirr,const DeepCollectionEquality().hash(transactions));

@override
String toString() {
  return 'MFFund(schemeName: $schemeName, category: $category, folio: $folio, invested: $invested, currentValue: $currentValue, units: $units, nav: $nav, avgNav: $avgNav, returnPct: $returnPct, xirr: $xirr, transactions: $transactions)';
}


}

/// @nodoc
abstract mixin class $MFFundCopyWith<$Res>  {
  factory $MFFundCopyWith(MFFund value, $Res Function(MFFund) _then) = _$MFFundCopyWithImpl;
@useResult
$Res call({
@JsonKey(name: 'scheme_name') String schemeName, String category, String folio, double invested,@JsonKey(name: 'current_value') double currentValue, double units, double nav,@JsonKey(name: 'avg_nav') double avgNav,@JsonKey(name: 'return_pct') double returnPct, double xirr, List<MFTransaction> transactions
});




}
/// @nodoc
class _$MFFundCopyWithImpl<$Res>
    implements $MFFundCopyWith<$Res> {
  _$MFFundCopyWithImpl(this._self, this._then);

  final MFFund _self;
  final $Res Function(MFFund) _then;

/// Create a copy of MFFund
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? schemeName = null,Object? category = null,Object? folio = null,Object? invested = null,Object? currentValue = null,Object? units = null,Object? nav = null,Object? avgNav = null,Object? returnPct = null,Object? xirr = null,Object? transactions = null,}) {
  return _then(_self.copyWith(
schemeName: null == schemeName ? _self.schemeName : schemeName // ignore: cast_nullable_to_non_nullable
as String,category: null == category ? _self.category : category // ignore: cast_nullable_to_non_nullable
as String,folio: null == folio ? _self.folio : folio // ignore: cast_nullable_to_non_nullable
as String,invested: null == invested ? _self.invested : invested // ignore: cast_nullable_to_non_nullable
as double,currentValue: null == currentValue ? _self.currentValue : currentValue // ignore: cast_nullable_to_non_nullable
as double,units: null == units ? _self.units : units // ignore: cast_nullable_to_non_nullable
as double,nav: null == nav ? _self.nav : nav // ignore: cast_nullable_to_non_nullable
as double,avgNav: null == avgNav ? _self.avgNav : avgNav // ignore: cast_nullable_to_non_nullable
as double,returnPct: null == returnPct ? _self.returnPct : returnPct // ignore: cast_nullable_to_non_nullable
as double,xirr: null == xirr ? _self.xirr : xirr // ignore: cast_nullable_to_non_nullable
as double,transactions: null == transactions ? _self.transactions : transactions // ignore: cast_nullable_to_non_nullable
as List<MFTransaction>,
  ));
}

}


/// Adds pattern-matching-related methods to [MFFund].
extension MFFundPatterns on MFFund {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _MFFund value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _MFFund() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _MFFund value)  $default,){
final _that = this;
switch (_that) {
case _MFFund():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _MFFund value)?  $default,){
final _that = this;
switch (_that) {
case _MFFund() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function(@JsonKey(name: 'scheme_name')  String schemeName,  String category,  String folio,  double invested, @JsonKey(name: 'current_value')  double currentValue,  double units,  double nav, @JsonKey(name: 'avg_nav')  double avgNav, @JsonKey(name: 'return_pct')  double returnPct,  double xirr,  List<MFTransaction> transactions)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _MFFund() when $default != null:
return $default(_that.schemeName,_that.category,_that.folio,_that.invested,_that.currentValue,_that.units,_that.nav,_that.avgNav,_that.returnPct,_that.xirr,_that.transactions);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function(@JsonKey(name: 'scheme_name')  String schemeName,  String category,  String folio,  double invested, @JsonKey(name: 'current_value')  double currentValue,  double units,  double nav, @JsonKey(name: 'avg_nav')  double avgNav, @JsonKey(name: 'return_pct')  double returnPct,  double xirr,  List<MFTransaction> transactions)  $default,) {final _that = this;
switch (_that) {
case _MFFund():
return $default(_that.schemeName,_that.category,_that.folio,_that.invested,_that.currentValue,_that.units,_that.nav,_that.avgNav,_that.returnPct,_that.xirr,_that.transactions);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function(@JsonKey(name: 'scheme_name')  String schemeName,  String category,  String folio,  double invested, @JsonKey(name: 'current_value')  double currentValue,  double units,  double nav, @JsonKey(name: 'avg_nav')  double avgNav, @JsonKey(name: 'return_pct')  double returnPct,  double xirr,  List<MFTransaction> transactions)?  $default,) {final _that = this;
switch (_that) {
case _MFFund() when $default != null:
return $default(_that.schemeName,_that.category,_that.folio,_that.invested,_that.currentValue,_that.units,_that.nav,_that.avgNav,_that.returnPct,_that.xirr,_that.transactions);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _MFFund implements MFFund {
  const _MFFund({@JsonKey(name: 'scheme_name') this.schemeName = '', this.category = 'Mutual Fund', this.folio = '', this.invested = 0, @JsonKey(name: 'current_value') this.currentValue = 0, this.units = 0, this.nav = 0, @JsonKey(name: 'avg_nav') this.avgNav = 0, @JsonKey(name: 'return_pct') this.returnPct = 0, this.xirr = 0, final  List<MFTransaction> transactions = const []}): _transactions = transactions;
  factory _MFFund.fromJson(Map<String, dynamic> json) => _$MFFundFromJson(json);

@override@JsonKey(name: 'scheme_name') final  String schemeName;
@override@JsonKey() final  String category;
@override@JsonKey() final  String folio;
@override@JsonKey() final  double invested;
@override@JsonKey(name: 'current_value') final  double currentValue;
@override@JsonKey() final  double units;
@override@JsonKey() final  double nav;
@override@JsonKey(name: 'avg_nav') final  double avgNav;
@override@JsonKey(name: 'return_pct') final  double returnPct;
@override@JsonKey() final  double xirr;
 final  List<MFTransaction> _transactions;
@override@JsonKey() List<MFTransaction> get transactions {
  if (_transactions is EqualUnmodifiableListView) return _transactions;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_transactions);
}


/// Create a copy of MFFund
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$MFFundCopyWith<_MFFund> get copyWith => __$MFFundCopyWithImpl<_MFFund>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$MFFundToJson(this, );
}

@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _MFFund&&(identical(other.schemeName, schemeName) || other.schemeName == schemeName)&&(identical(other.category, category) || other.category == category)&&(identical(other.folio, folio) || other.folio == folio)&&(identical(other.invested, invested) || other.invested == invested)&&(identical(other.currentValue, currentValue) || other.currentValue == currentValue)&&(identical(other.units, units) || other.units == units)&&(identical(other.nav, nav) || other.nav == nav)&&(identical(other.avgNav, avgNav) || other.avgNav == avgNav)&&(identical(other.returnPct, returnPct) || other.returnPct == returnPct)&&(identical(other.xirr, xirr) || other.xirr == xirr)&&const DeepCollectionEquality().equals(other._transactions, _transactions));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,schemeName,category,folio,invested,currentValue,units,nav,avgNav,returnPct,xirr,const DeepCollectionEquality().hash(_transactions));

@override
String toString() {
  return 'MFFund(schemeName: $schemeName, category: $category, folio: $folio, invested: $invested, currentValue: $currentValue, units: $units, nav: $nav, avgNav: $avgNav, returnPct: $returnPct, xirr: $xirr, transactions: $transactions)';
}


}

/// @nodoc
abstract mixin class _$MFFundCopyWith<$Res> implements $MFFundCopyWith<$Res> {
  factory _$MFFundCopyWith(_MFFund value, $Res Function(_MFFund) _then) = __$MFFundCopyWithImpl;
@override @useResult
$Res call({
@JsonKey(name: 'scheme_name') String schemeName, String category, String folio, double invested,@JsonKey(name: 'current_value') double currentValue, double units, double nav,@JsonKey(name: 'avg_nav') double avgNav,@JsonKey(name: 'return_pct') double returnPct, double xirr, List<MFTransaction> transactions
});




}
/// @nodoc
class __$MFFundCopyWithImpl<$Res>
    implements _$MFFundCopyWith<$Res> {
  __$MFFundCopyWithImpl(this._self, this._then);

  final _MFFund _self;
  final $Res Function(_MFFund) _then;

/// Create a copy of MFFund
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? schemeName = null,Object? category = null,Object? folio = null,Object? invested = null,Object? currentValue = null,Object? units = null,Object? nav = null,Object? avgNav = null,Object? returnPct = null,Object? xirr = null,Object? transactions = null,}) {
  return _then(_MFFund(
schemeName: null == schemeName ? _self.schemeName : schemeName // ignore: cast_nullable_to_non_nullable
as String,category: null == category ? _self.category : category // ignore: cast_nullable_to_non_nullable
as String,folio: null == folio ? _self.folio : folio // ignore: cast_nullable_to_non_nullable
as String,invested: null == invested ? _self.invested : invested // ignore: cast_nullable_to_non_nullable
as double,currentValue: null == currentValue ? _self.currentValue : currentValue // ignore: cast_nullable_to_non_nullable
as double,units: null == units ? _self.units : units // ignore: cast_nullable_to_non_nullable
as double,nav: null == nav ? _self.nav : nav // ignore: cast_nullable_to_non_nullable
as double,avgNav: null == avgNav ? _self.avgNav : avgNav // ignore: cast_nullable_to_non_nullable
as double,returnPct: null == returnPct ? _self.returnPct : returnPct // ignore: cast_nullable_to_non_nullable
as double,xirr: null == xirr ? _self.xirr : xirr // ignore: cast_nullable_to_non_nullable
as double,transactions: null == transactions ? _self._transactions : transactions // ignore: cast_nullable_to_non_nullable
as List<MFTransaction>,
  ));
}


}


/// @nodoc
mixin _$MFPortfolioData {

 List<MFFund> get funds;@JsonKey(name: 'total_invested') double get totalInvested;@JsonKey(name: 'total_current') double get totalCurrent;@JsonKey(name: 'total_pnl') double get totalPnl;@JsonKey(name: 'total_pnl_pct') double get totalPnlPct;@JsonKey(name: 'total_xirr') double get totalXirr;
/// Create a copy of MFPortfolioData
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$MFPortfolioDataCopyWith<MFPortfolioData> get copyWith => _$MFPortfolioDataCopyWithImpl<MFPortfolioData>(this as MFPortfolioData, _$identity);

  /// Serializes this MFPortfolioData to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is MFPortfolioData&&const DeepCollectionEquality().equals(other.funds, funds)&&(identical(other.totalInvested, totalInvested) || other.totalInvested == totalInvested)&&(identical(other.totalCurrent, totalCurrent) || other.totalCurrent == totalCurrent)&&(identical(other.totalPnl, totalPnl) || other.totalPnl == totalPnl)&&(identical(other.totalPnlPct, totalPnlPct) || other.totalPnlPct == totalPnlPct)&&(identical(other.totalXirr, totalXirr) || other.totalXirr == totalXirr));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,const DeepCollectionEquality().hash(funds),totalInvested,totalCurrent,totalPnl,totalPnlPct,totalXirr);

@override
String toString() {
  return 'MFPortfolioData(funds: $funds, totalInvested: $totalInvested, totalCurrent: $totalCurrent, totalPnl: $totalPnl, totalPnlPct: $totalPnlPct, totalXirr: $totalXirr)';
}


}

/// @nodoc
abstract mixin class $MFPortfolioDataCopyWith<$Res>  {
  factory $MFPortfolioDataCopyWith(MFPortfolioData value, $Res Function(MFPortfolioData) _then) = _$MFPortfolioDataCopyWithImpl;
@useResult
$Res call({
 List<MFFund> funds,@JsonKey(name: 'total_invested') double totalInvested,@JsonKey(name: 'total_current') double totalCurrent,@JsonKey(name: 'total_pnl') double totalPnl,@JsonKey(name: 'total_pnl_pct') double totalPnlPct,@JsonKey(name: 'total_xirr') double totalXirr
});




}
/// @nodoc
class _$MFPortfolioDataCopyWithImpl<$Res>
    implements $MFPortfolioDataCopyWith<$Res> {
  _$MFPortfolioDataCopyWithImpl(this._self, this._then);

  final MFPortfolioData _self;
  final $Res Function(MFPortfolioData) _then;

/// Create a copy of MFPortfolioData
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? funds = null,Object? totalInvested = null,Object? totalCurrent = null,Object? totalPnl = null,Object? totalPnlPct = null,Object? totalXirr = null,}) {
  return _then(_self.copyWith(
funds: null == funds ? _self.funds : funds // ignore: cast_nullable_to_non_nullable
as List<MFFund>,totalInvested: null == totalInvested ? _self.totalInvested : totalInvested // ignore: cast_nullable_to_non_nullable
as double,totalCurrent: null == totalCurrent ? _self.totalCurrent : totalCurrent // ignore: cast_nullable_to_non_nullable
as double,totalPnl: null == totalPnl ? _self.totalPnl : totalPnl // ignore: cast_nullable_to_non_nullable
as double,totalPnlPct: null == totalPnlPct ? _self.totalPnlPct : totalPnlPct // ignore: cast_nullable_to_non_nullable
as double,totalXirr: null == totalXirr ? _self.totalXirr : totalXirr // ignore: cast_nullable_to_non_nullable
as double,
  ));
}

}


/// Adds pattern-matching-related methods to [MFPortfolioData].
extension MFPortfolioDataPatterns on MFPortfolioData {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _MFPortfolioData value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _MFPortfolioData() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _MFPortfolioData value)  $default,){
final _that = this;
switch (_that) {
case _MFPortfolioData():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _MFPortfolioData value)?  $default,){
final _that = this;
switch (_that) {
case _MFPortfolioData() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( List<MFFund> funds, @JsonKey(name: 'total_invested')  double totalInvested, @JsonKey(name: 'total_current')  double totalCurrent, @JsonKey(name: 'total_pnl')  double totalPnl, @JsonKey(name: 'total_pnl_pct')  double totalPnlPct, @JsonKey(name: 'total_xirr')  double totalXirr)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _MFPortfolioData() when $default != null:
return $default(_that.funds,_that.totalInvested,_that.totalCurrent,_that.totalPnl,_that.totalPnlPct,_that.totalXirr);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( List<MFFund> funds, @JsonKey(name: 'total_invested')  double totalInvested, @JsonKey(name: 'total_current')  double totalCurrent, @JsonKey(name: 'total_pnl')  double totalPnl, @JsonKey(name: 'total_pnl_pct')  double totalPnlPct, @JsonKey(name: 'total_xirr')  double totalXirr)  $default,) {final _that = this;
switch (_that) {
case _MFPortfolioData():
return $default(_that.funds,_that.totalInvested,_that.totalCurrent,_that.totalPnl,_that.totalPnlPct,_that.totalXirr);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( List<MFFund> funds, @JsonKey(name: 'total_invested')  double totalInvested, @JsonKey(name: 'total_current')  double totalCurrent, @JsonKey(name: 'total_pnl')  double totalPnl, @JsonKey(name: 'total_pnl_pct')  double totalPnlPct, @JsonKey(name: 'total_xirr')  double totalXirr)?  $default,) {final _that = this;
switch (_that) {
case _MFPortfolioData() when $default != null:
return $default(_that.funds,_that.totalInvested,_that.totalCurrent,_that.totalPnl,_that.totalPnlPct,_that.totalXirr);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _MFPortfolioData implements MFPortfolioData {
  const _MFPortfolioData({final  List<MFFund> funds = const [], @JsonKey(name: 'total_invested') this.totalInvested = 0, @JsonKey(name: 'total_current') this.totalCurrent = 0, @JsonKey(name: 'total_pnl') this.totalPnl = 0, @JsonKey(name: 'total_pnl_pct') this.totalPnlPct = 0, @JsonKey(name: 'total_xirr') this.totalXirr = 0}): _funds = funds;
  factory _MFPortfolioData.fromJson(Map<String, dynamic> json) => _$MFPortfolioDataFromJson(json);

 final  List<MFFund> _funds;
@override@JsonKey() List<MFFund> get funds {
  if (_funds is EqualUnmodifiableListView) return _funds;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_funds);
}

@override@JsonKey(name: 'total_invested') final  double totalInvested;
@override@JsonKey(name: 'total_current') final  double totalCurrent;
@override@JsonKey(name: 'total_pnl') final  double totalPnl;
@override@JsonKey(name: 'total_pnl_pct') final  double totalPnlPct;
@override@JsonKey(name: 'total_xirr') final  double totalXirr;

/// Create a copy of MFPortfolioData
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$MFPortfolioDataCopyWith<_MFPortfolioData> get copyWith => __$MFPortfolioDataCopyWithImpl<_MFPortfolioData>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$MFPortfolioDataToJson(this, );
}

@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _MFPortfolioData&&const DeepCollectionEquality().equals(other._funds, _funds)&&(identical(other.totalInvested, totalInvested) || other.totalInvested == totalInvested)&&(identical(other.totalCurrent, totalCurrent) || other.totalCurrent == totalCurrent)&&(identical(other.totalPnl, totalPnl) || other.totalPnl == totalPnl)&&(identical(other.totalPnlPct, totalPnlPct) || other.totalPnlPct == totalPnlPct)&&(identical(other.totalXirr, totalXirr) || other.totalXirr == totalXirr));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,const DeepCollectionEquality().hash(_funds),totalInvested,totalCurrent,totalPnl,totalPnlPct,totalXirr);

@override
String toString() {
  return 'MFPortfolioData(funds: $funds, totalInvested: $totalInvested, totalCurrent: $totalCurrent, totalPnl: $totalPnl, totalPnlPct: $totalPnlPct, totalXirr: $totalXirr)';
}


}

/// @nodoc
abstract mixin class _$MFPortfolioDataCopyWith<$Res> implements $MFPortfolioDataCopyWith<$Res> {
  factory _$MFPortfolioDataCopyWith(_MFPortfolioData value, $Res Function(_MFPortfolioData) _then) = __$MFPortfolioDataCopyWithImpl;
@override @useResult
$Res call({
 List<MFFund> funds,@JsonKey(name: 'total_invested') double totalInvested,@JsonKey(name: 'total_current') double totalCurrent,@JsonKey(name: 'total_pnl') double totalPnl,@JsonKey(name: 'total_pnl_pct') double totalPnlPct,@JsonKey(name: 'total_xirr') double totalXirr
});




}
/// @nodoc
class __$MFPortfolioDataCopyWithImpl<$Res>
    implements _$MFPortfolioDataCopyWith<$Res> {
  __$MFPortfolioDataCopyWithImpl(this._self, this._then);

  final _MFPortfolioData _self;
  final $Res Function(_MFPortfolioData) _then;

/// Create a copy of MFPortfolioData
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? funds = null,Object? totalInvested = null,Object? totalCurrent = null,Object? totalPnl = null,Object? totalPnlPct = null,Object? totalXirr = null,}) {
  return _then(_MFPortfolioData(
funds: null == funds ? _self._funds : funds // ignore: cast_nullable_to_non_nullable
as List<MFFund>,totalInvested: null == totalInvested ? _self.totalInvested : totalInvested // ignore: cast_nullable_to_non_nullable
as double,totalCurrent: null == totalCurrent ? _self.totalCurrent : totalCurrent // ignore: cast_nullable_to_non_nullable
as double,totalPnl: null == totalPnl ? _self.totalPnl : totalPnl // ignore: cast_nullable_to_non_nullable
as double,totalPnlPct: null == totalPnlPct ? _self.totalPnlPct : totalPnlPct // ignore: cast_nullable_to_non_nullable
as double,totalXirr: null == totalXirr ? _self.totalXirr : totalXirr // ignore: cast_nullable_to_non_nullable
as double,
  ));
}


}


/// @nodoc
mixin _$NiftyData {

 String get symbol; double get current;@JsonKey(name: 'change_pct') double get changePct; String? get error;
/// Create a copy of NiftyData
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$NiftyDataCopyWith<NiftyData> get copyWith => _$NiftyDataCopyWithImpl<NiftyData>(this as NiftyData, _$identity);

  /// Serializes this NiftyData to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is NiftyData&&(identical(other.symbol, symbol) || other.symbol == symbol)&&(identical(other.current, current) || other.current == current)&&(identical(other.changePct, changePct) || other.changePct == changePct)&&(identical(other.error, error) || other.error == error));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,symbol,current,changePct,error);

@override
String toString() {
  return 'NiftyData(symbol: $symbol, current: $current, changePct: $changePct, error: $error)';
}


}

/// @nodoc
abstract mixin class $NiftyDataCopyWith<$Res>  {
  factory $NiftyDataCopyWith(NiftyData value, $Res Function(NiftyData) _then) = _$NiftyDataCopyWithImpl;
@useResult
$Res call({
 String symbol, double current,@JsonKey(name: 'change_pct') double changePct, String? error
});




}
/// @nodoc
class _$NiftyDataCopyWithImpl<$Res>
    implements $NiftyDataCopyWith<$Res> {
  _$NiftyDataCopyWithImpl(this._self, this._then);

  final NiftyData _self;
  final $Res Function(NiftyData) _then;

/// Create a copy of NiftyData
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? symbol = null,Object? current = null,Object? changePct = null,Object? error = freezed,}) {
  return _then(_self.copyWith(
symbol: null == symbol ? _self.symbol : symbol // ignore: cast_nullable_to_non_nullable
as String,current: null == current ? _self.current : current // ignore: cast_nullable_to_non_nullable
as double,changePct: null == changePct ? _self.changePct : changePct // ignore: cast_nullable_to_non_nullable
as double,error: freezed == error ? _self.error : error // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}

}


/// Adds pattern-matching-related methods to [NiftyData].
extension NiftyDataPatterns on NiftyData {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _NiftyData value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _NiftyData() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _NiftyData value)  $default,){
final _that = this;
switch (_that) {
case _NiftyData():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _NiftyData value)?  $default,){
final _that = this;
switch (_that) {
case _NiftyData() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String symbol,  double current, @JsonKey(name: 'change_pct')  double changePct,  String? error)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _NiftyData() when $default != null:
return $default(_that.symbol,_that.current,_that.changePct,_that.error);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String symbol,  double current, @JsonKey(name: 'change_pct')  double changePct,  String? error)  $default,) {final _that = this;
switch (_that) {
case _NiftyData():
return $default(_that.symbol,_that.current,_that.changePct,_that.error);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String symbol,  double current, @JsonKey(name: 'change_pct')  double changePct,  String? error)?  $default,) {final _that = this;
switch (_that) {
case _NiftyData() when $default != null:
return $default(_that.symbol,_that.current,_that.changePct,_that.error);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _NiftyData implements NiftyData {
  const _NiftyData({this.symbol = 'NIFTY 50', this.current = 0, @JsonKey(name: 'change_pct') this.changePct = 0, this.error});
  factory _NiftyData.fromJson(Map<String, dynamic> json) => _$NiftyDataFromJson(json);

@override@JsonKey() final  String symbol;
@override@JsonKey() final  double current;
@override@JsonKey(name: 'change_pct') final  double changePct;
@override final  String? error;

/// Create a copy of NiftyData
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$NiftyDataCopyWith<_NiftyData> get copyWith => __$NiftyDataCopyWithImpl<_NiftyData>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$NiftyDataToJson(this, );
}

@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _NiftyData&&(identical(other.symbol, symbol) || other.symbol == symbol)&&(identical(other.current, current) || other.current == current)&&(identical(other.changePct, changePct) || other.changePct == changePct)&&(identical(other.error, error) || other.error == error));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,symbol,current,changePct,error);

@override
String toString() {
  return 'NiftyData(symbol: $symbol, current: $current, changePct: $changePct, error: $error)';
}


}

/// @nodoc
abstract mixin class _$NiftyDataCopyWith<$Res> implements $NiftyDataCopyWith<$Res> {
  factory _$NiftyDataCopyWith(_NiftyData value, $Res Function(_NiftyData) _then) = __$NiftyDataCopyWithImpl;
@override @useResult
$Res call({
 String symbol, double current,@JsonKey(name: 'change_pct') double changePct, String? error
});




}
/// @nodoc
class __$NiftyDataCopyWithImpl<$Res>
    implements _$NiftyDataCopyWith<$Res> {
  __$NiftyDataCopyWithImpl(this._self, this._then);

  final _NiftyData _self;
  final $Res Function(_NiftyData) _then;

/// Create a copy of NiftyData
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? symbol = null,Object? current = null,Object? changePct = null,Object? error = freezed,}) {
  return _then(_NiftyData(
symbol: null == symbol ? _self.symbol : symbol // ignore: cast_nullable_to_non_nullable
as String,current: null == current ? _self.current : current // ignore: cast_nullable_to_non_nullable
as double,changePct: null == changePct ? _self.changePct : changePct // ignore: cast_nullable_to_non_nullable
as double,error: freezed == error ? _self.error : error // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}


}


/// @nodoc
mixin _$KiteStatus {

 bool get connected; bool get configured;@JsonKey(name: 'mcp_available') bool get mcpAvailable;@JsonKey(name: 'user_name') String? get userName;@JsonKey(name: 'user_id') String? get userId; String? get broker;@JsonKey(name: 'last_error') String? get lastError;
/// Create a copy of KiteStatus
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$KiteStatusCopyWith<KiteStatus> get copyWith => _$KiteStatusCopyWithImpl<KiteStatus>(this as KiteStatus, _$identity);

  /// Serializes this KiteStatus to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is KiteStatus&&(identical(other.connected, connected) || other.connected == connected)&&(identical(other.configured, configured) || other.configured == configured)&&(identical(other.mcpAvailable, mcpAvailable) || other.mcpAvailable == mcpAvailable)&&(identical(other.userName, userName) || other.userName == userName)&&(identical(other.userId, userId) || other.userId == userId)&&(identical(other.broker, broker) || other.broker == broker)&&(identical(other.lastError, lastError) || other.lastError == lastError));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,connected,configured,mcpAvailable,userName,userId,broker,lastError);

@override
String toString() {
  return 'KiteStatus(connected: $connected, configured: $configured, mcpAvailable: $mcpAvailable, userName: $userName, userId: $userId, broker: $broker, lastError: $lastError)';
}


}

/// @nodoc
abstract mixin class $KiteStatusCopyWith<$Res>  {
  factory $KiteStatusCopyWith(KiteStatus value, $Res Function(KiteStatus) _then) = _$KiteStatusCopyWithImpl;
@useResult
$Res call({
 bool connected, bool configured,@JsonKey(name: 'mcp_available') bool mcpAvailable,@JsonKey(name: 'user_name') String? userName,@JsonKey(name: 'user_id') String? userId, String? broker,@JsonKey(name: 'last_error') String? lastError
});




}
/// @nodoc
class _$KiteStatusCopyWithImpl<$Res>
    implements $KiteStatusCopyWith<$Res> {
  _$KiteStatusCopyWithImpl(this._self, this._then);

  final KiteStatus _self;
  final $Res Function(KiteStatus) _then;

/// Create a copy of KiteStatus
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? connected = null,Object? configured = null,Object? mcpAvailable = null,Object? userName = freezed,Object? userId = freezed,Object? broker = freezed,Object? lastError = freezed,}) {
  return _then(_self.copyWith(
connected: null == connected ? _self.connected : connected // ignore: cast_nullable_to_non_nullable
as bool,configured: null == configured ? _self.configured : configured // ignore: cast_nullable_to_non_nullable
as bool,mcpAvailable: null == mcpAvailable ? _self.mcpAvailable : mcpAvailable // ignore: cast_nullable_to_non_nullable
as bool,userName: freezed == userName ? _self.userName : userName // ignore: cast_nullable_to_non_nullable
as String?,userId: freezed == userId ? _self.userId : userId // ignore: cast_nullable_to_non_nullable
as String?,broker: freezed == broker ? _self.broker : broker // ignore: cast_nullable_to_non_nullable
as String?,lastError: freezed == lastError ? _self.lastError : lastError // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}

}


/// Adds pattern-matching-related methods to [KiteStatus].
extension KiteStatusPatterns on KiteStatus {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _KiteStatus value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _KiteStatus() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _KiteStatus value)  $default,){
final _that = this;
switch (_that) {
case _KiteStatus():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _KiteStatus value)?  $default,){
final _that = this;
switch (_that) {
case _KiteStatus() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( bool connected,  bool configured, @JsonKey(name: 'mcp_available')  bool mcpAvailable, @JsonKey(name: 'user_name')  String? userName, @JsonKey(name: 'user_id')  String? userId,  String? broker, @JsonKey(name: 'last_error')  String? lastError)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _KiteStatus() when $default != null:
return $default(_that.connected,_that.configured,_that.mcpAvailable,_that.userName,_that.userId,_that.broker,_that.lastError);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( bool connected,  bool configured, @JsonKey(name: 'mcp_available')  bool mcpAvailable, @JsonKey(name: 'user_name')  String? userName, @JsonKey(name: 'user_id')  String? userId,  String? broker, @JsonKey(name: 'last_error')  String? lastError)  $default,) {final _that = this;
switch (_that) {
case _KiteStatus():
return $default(_that.connected,_that.configured,_that.mcpAvailable,_that.userName,_that.userId,_that.broker,_that.lastError);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( bool connected,  bool configured, @JsonKey(name: 'mcp_available')  bool mcpAvailable, @JsonKey(name: 'user_name')  String? userName, @JsonKey(name: 'user_id')  String? userId,  String? broker, @JsonKey(name: 'last_error')  String? lastError)?  $default,) {final _that = this;
switch (_that) {
case _KiteStatus() when $default != null:
return $default(_that.connected,_that.configured,_that.mcpAvailable,_that.userName,_that.userId,_that.broker,_that.lastError);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _KiteStatus implements KiteStatus {
  const _KiteStatus({this.connected = false, this.configured = false, @JsonKey(name: 'mcp_available') this.mcpAvailable = false, @JsonKey(name: 'user_name') this.userName, @JsonKey(name: 'user_id') this.userId, this.broker, @JsonKey(name: 'last_error') this.lastError});
  factory _KiteStatus.fromJson(Map<String, dynamic> json) => _$KiteStatusFromJson(json);

@override@JsonKey() final  bool connected;
@override@JsonKey() final  bool configured;
@override@JsonKey(name: 'mcp_available') final  bool mcpAvailable;
@override@JsonKey(name: 'user_name') final  String? userName;
@override@JsonKey(name: 'user_id') final  String? userId;
@override final  String? broker;
@override@JsonKey(name: 'last_error') final  String? lastError;

/// Create a copy of KiteStatus
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$KiteStatusCopyWith<_KiteStatus> get copyWith => __$KiteStatusCopyWithImpl<_KiteStatus>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$KiteStatusToJson(this, );
}

@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _KiteStatus&&(identical(other.connected, connected) || other.connected == connected)&&(identical(other.configured, configured) || other.configured == configured)&&(identical(other.mcpAvailable, mcpAvailable) || other.mcpAvailable == mcpAvailable)&&(identical(other.userName, userName) || other.userName == userName)&&(identical(other.userId, userId) || other.userId == userId)&&(identical(other.broker, broker) || other.broker == broker)&&(identical(other.lastError, lastError) || other.lastError == lastError));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,connected,configured,mcpAvailable,userName,userId,broker,lastError);

@override
String toString() {
  return 'KiteStatus(connected: $connected, configured: $configured, mcpAvailable: $mcpAvailable, userName: $userName, userId: $userId, broker: $broker, lastError: $lastError)';
}


}

/// @nodoc
abstract mixin class _$KiteStatusCopyWith<$Res> implements $KiteStatusCopyWith<$Res> {
  factory _$KiteStatusCopyWith(_KiteStatus value, $Res Function(_KiteStatus) _then) = __$KiteStatusCopyWithImpl;
@override @useResult
$Res call({
 bool connected, bool configured,@JsonKey(name: 'mcp_available') bool mcpAvailable,@JsonKey(name: 'user_name') String? userName,@JsonKey(name: 'user_id') String? userId, String? broker,@JsonKey(name: 'last_error') String? lastError
});




}
/// @nodoc
class __$KiteStatusCopyWithImpl<$Res>
    implements _$KiteStatusCopyWith<$Res> {
  __$KiteStatusCopyWithImpl(this._self, this._then);

  final _KiteStatus _self;
  final $Res Function(_KiteStatus) _then;

/// Create a copy of KiteStatus
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? connected = null,Object? configured = null,Object? mcpAvailable = null,Object? userName = freezed,Object? userId = freezed,Object? broker = freezed,Object? lastError = freezed,}) {
  return _then(_KiteStatus(
connected: null == connected ? _self.connected : connected // ignore: cast_nullable_to_non_nullable
as bool,configured: null == configured ? _self.configured : configured // ignore: cast_nullable_to_non_nullable
as bool,mcpAvailable: null == mcpAvailable ? _self.mcpAvailable : mcpAvailable // ignore: cast_nullable_to_non_nullable
as bool,userName: freezed == userName ? _self.userName : userName // ignore: cast_nullable_to_non_nullable
as String?,userId: freezed == userId ? _self.userId : userId // ignore: cast_nullable_to_non_nullable
as String?,broker: freezed == broker ? _self.broker : broker // ignore: cast_nullable_to_non_nullable
as String?,lastError: freezed == lastError ? _self.lastError : lastError // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}


}


/// @nodoc
mixin _$AdvisorVerdict {

 String get verdict;@JsonKey(name: 'action_summary') String get actionSummary;@JsonKey(name: 'entry_range') String? get entryRange;@JsonKey(name: 'target_price') String? get targetPrice;@JsonKey(name: 'stop_loss') String? get stopLoss;@JsonKey(name: 'sell_pct') String? get sellPct;@JsonKey(name: 'time_horizon') String get timeHorizon;@JsonKey(name: 'risk_level') String get riskLevel; int get confidence; String get reasoning;@JsonKey(name: 'current_price') double? get currentPrice;@JsonKey(name: 'pnl_pct') double? get pnlPct; double? get rsi;@JsonKey(name: 'news_count') int get newsCount;
/// Create a copy of AdvisorVerdict
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$AdvisorVerdictCopyWith<AdvisorVerdict> get copyWith => _$AdvisorVerdictCopyWithImpl<AdvisorVerdict>(this as AdvisorVerdict, _$identity);

  /// Serializes this AdvisorVerdict to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is AdvisorVerdict&&(identical(other.verdict, verdict) || other.verdict == verdict)&&(identical(other.actionSummary, actionSummary) || other.actionSummary == actionSummary)&&(identical(other.entryRange, entryRange) || other.entryRange == entryRange)&&(identical(other.targetPrice, targetPrice) || other.targetPrice == targetPrice)&&(identical(other.stopLoss, stopLoss) || other.stopLoss == stopLoss)&&(identical(other.sellPct, sellPct) || other.sellPct == sellPct)&&(identical(other.timeHorizon, timeHorizon) || other.timeHorizon == timeHorizon)&&(identical(other.riskLevel, riskLevel) || other.riskLevel == riskLevel)&&(identical(other.confidence, confidence) || other.confidence == confidence)&&(identical(other.reasoning, reasoning) || other.reasoning == reasoning)&&(identical(other.currentPrice, currentPrice) || other.currentPrice == currentPrice)&&(identical(other.pnlPct, pnlPct) || other.pnlPct == pnlPct)&&(identical(other.rsi, rsi) || other.rsi == rsi)&&(identical(other.newsCount, newsCount) || other.newsCount == newsCount));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,verdict,actionSummary,entryRange,targetPrice,stopLoss,sellPct,timeHorizon,riskLevel,confidence,reasoning,currentPrice,pnlPct,rsi,newsCount);

@override
String toString() {
  return 'AdvisorVerdict(verdict: $verdict, actionSummary: $actionSummary, entryRange: $entryRange, targetPrice: $targetPrice, stopLoss: $stopLoss, sellPct: $sellPct, timeHorizon: $timeHorizon, riskLevel: $riskLevel, confidence: $confidence, reasoning: $reasoning, currentPrice: $currentPrice, pnlPct: $pnlPct, rsi: $rsi, newsCount: $newsCount)';
}


}

/// @nodoc
abstract mixin class $AdvisorVerdictCopyWith<$Res>  {
  factory $AdvisorVerdictCopyWith(AdvisorVerdict value, $Res Function(AdvisorVerdict) _then) = _$AdvisorVerdictCopyWithImpl;
@useResult
$Res call({
 String verdict,@JsonKey(name: 'action_summary') String actionSummary,@JsonKey(name: 'entry_range') String? entryRange,@JsonKey(name: 'target_price') String? targetPrice,@JsonKey(name: 'stop_loss') String? stopLoss,@JsonKey(name: 'sell_pct') String? sellPct,@JsonKey(name: 'time_horizon') String timeHorizon,@JsonKey(name: 'risk_level') String riskLevel, int confidence, String reasoning,@JsonKey(name: 'current_price') double? currentPrice,@JsonKey(name: 'pnl_pct') double? pnlPct, double? rsi,@JsonKey(name: 'news_count') int newsCount
});




}
/// @nodoc
class _$AdvisorVerdictCopyWithImpl<$Res>
    implements $AdvisorVerdictCopyWith<$Res> {
  _$AdvisorVerdictCopyWithImpl(this._self, this._then);

  final AdvisorVerdict _self;
  final $Res Function(AdvisorVerdict) _then;

/// Create a copy of AdvisorVerdict
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? verdict = null,Object? actionSummary = null,Object? entryRange = freezed,Object? targetPrice = freezed,Object? stopLoss = freezed,Object? sellPct = freezed,Object? timeHorizon = null,Object? riskLevel = null,Object? confidence = null,Object? reasoning = null,Object? currentPrice = freezed,Object? pnlPct = freezed,Object? rsi = freezed,Object? newsCount = null,}) {
  return _then(_self.copyWith(
verdict: null == verdict ? _self.verdict : verdict // ignore: cast_nullable_to_non_nullable
as String,actionSummary: null == actionSummary ? _self.actionSummary : actionSummary // ignore: cast_nullable_to_non_nullable
as String,entryRange: freezed == entryRange ? _self.entryRange : entryRange // ignore: cast_nullable_to_non_nullable
as String?,targetPrice: freezed == targetPrice ? _self.targetPrice : targetPrice // ignore: cast_nullable_to_non_nullable
as String?,stopLoss: freezed == stopLoss ? _self.stopLoss : stopLoss // ignore: cast_nullable_to_non_nullable
as String?,sellPct: freezed == sellPct ? _self.sellPct : sellPct // ignore: cast_nullable_to_non_nullable
as String?,timeHorizon: null == timeHorizon ? _self.timeHorizon : timeHorizon // ignore: cast_nullable_to_non_nullable
as String,riskLevel: null == riskLevel ? _self.riskLevel : riskLevel // ignore: cast_nullable_to_non_nullable
as String,confidence: null == confidence ? _self.confidence : confidence // ignore: cast_nullable_to_non_nullable
as int,reasoning: null == reasoning ? _self.reasoning : reasoning // ignore: cast_nullable_to_non_nullable
as String,currentPrice: freezed == currentPrice ? _self.currentPrice : currentPrice // ignore: cast_nullable_to_non_nullable
as double?,pnlPct: freezed == pnlPct ? _self.pnlPct : pnlPct // ignore: cast_nullable_to_non_nullable
as double?,rsi: freezed == rsi ? _self.rsi : rsi // ignore: cast_nullable_to_non_nullable
as double?,newsCount: null == newsCount ? _self.newsCount : newsCount // ignore: cast_nullable_to_non_nullable
as int,
  ));
}

}


/// Adds pattern-matching-related methods to [AdvisorVerdict].
extension AdvisorVerdictPatterns on AdvisorVerdict {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _AdvisorVerdict value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _AdvisorVerdict() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _AdvisorVerdict value)  $default,){
final _that = this;
switch (_that) {
case _AdvisorVerdict():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _AdvisorVerdict value)?  $default,){
final _that = this;
switch (_that) {
case _AdvisorVerdict() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String verdict, @JsonKey(name: 'action_summary')  String actionSummary, @JsonKey(name: 'entry_range')  String? entryRange, @JsonKey(name: 'target_price')  String? targetPrice, @JsonKey(name: 'stop_loss')  String? stopLoss, @JsonKey(name: 'sell_pct')  String? sellPct, @JsonKey(name: 'time_horizon')  String timeHorizon, @JsonKey(name: 'risk_level')  String riskLevel,  int confidence,  String reasoning, @JsonKey(name: 'current_price')  double? currentPrice, @JsonKey(name: 'pnl_pct')  double? pnlPct,  double? rsi, @JsonKey(name: 'news_count')  int newsCount)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _AdvisorVerdict() when $default != null:
return $default(_that.verdict,_that.actionSummary,_that.entryRange,_that.targetPrice,_that.stopLoss,_that.sellPct,_that.timeHorizon,_that.riskLevel,_that.confidence,_that.reasoning,_that.currentPrice,_that.pnlPct,_that.rsi,_that.newsCount);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String verdict, @JsonKey(name: 'action_summary')  String actionSummary, @JsonKey(name: 'entry_range')  String? entryRange, @JsonKey(name: 'target_price')  String? targetPrice, @JsonKey(name: 'stop_loss')  String? stopLoss, @JsonKey(name: 'sell_pct')  String? sellPct, @JsonKey(name: 'time_horizon')  String timeHorizon, @JsonKey(name: 'risk_level')  String riskLevel,  int confidence,  String reasoning, @JsonKey(name: 'current_price')  double? currentPrice, @JsonKey(name: 'pnl_pct')  double? pnlPct,  double? rsi, @JsonKey(name: 'news_count')  int newsCount)  $default,) {final _that = this;
switch (_that) {
case _AdvisorVerdict():
return $default(_that.verdict,_that.actionSummary,_that.entryRange,_that.targetPrice,_that.stopLoss,_that.sellPct,_that.timeHorizon,_that.riskLevel,_that.confidence,_that.reasoning,_that.currentPrice,_that.pnlPct,_that.rsi,_that.newsCount);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String verdict, @JsonKey(name: 'action_summary')  String actionSummary, @JsonKey(name: 'entry_range')  String? entryRange, @JsonKey(name: 'target_price')  String? targetPrice, @JsonKey(name: 'stop_loss')  String? stopLoss, @JsonKey(name: 'sell_pct')  String? sellPct, @JsonKey(name: 'time_horizon')  String timeHorizon, @JsonKey(name: 'risk_level')  String riskLevel,  int confidence,  String reasoning, @JsonKey(name: 'current_price')  double? currentPrice, @JsonKey(name: 'pnl_pct')  double? pnlPct,  double? rsi, @JsonKey(name: 'news_count')  int newsCount)?  $default,) {final _that = this;
switch (_that) {
case _AdvisorVerdict() when $default != null:
return $default(_that.verdict,_that.actionSummary,_that.entryRange,_that.targetPrice,_that.stopLoss,_that.sellPct,_that.timeHorizon,_that.riskLevel,_that.confidence,_that.reasoning,_that.currentPrice,_that.pnlPct,_that.rsi,_that.newsCount);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _AdvisorVerdict implements AdvisorVerdict {
  const _AdvisorVerdict({this.verdict = 'HOLD', @JsonKey(name: 'action_summary') this.actionSummary = '', @JsonKey(name: 'entry_range') this.entryRange, @JsonKey(name: 'target_price') this.targetPrice, @JsonKey(name: 'stop_loss') this.stopLoss, @JsonKey(name: 'sell_pct') this.sellPct, @JsonKey(name: 'time_horizon') this.timeHorizon = 'Medium', @JsonKey(name: 'risk_level') this.riskLevel = 'Medium', this.confidence = 50, this.reasoning = '', @JsonKey(name: 'current_price') this.currentPrice, @JsonKey(name: 'pnl_pct') this.pnlPct, this.rsi, @JsonKey(name: 'news_count') this.newsCount = 0});
  factory _AdvisorVerdict.fromJson(Map<String, dynamic> json) => _$AdvisorVerdictFromJson(json);

@override@JsonKey() final  String verdict;
@override@JsonKey(name: 'action_summary') final  String actionSummary;
@override@JsonKey(name: 'entry_range') final  String? entryRange;
@override@JsonKey(name: 'target_price') final  String? targetPrice;
@override@JsonKey(name: 'stop_loss') final  String? stopLoss;
@override@JsonKey(name: 'sell_pct') final  String? sellPct;
@override@JsonKey(name: 'time_horizon') final  String timeHorizon;
@override@JsonKey(name: 'risk_level') final  String riskLevel;
@override@JsonKey() final  int confidence;
@override@JsonKey() final  String reasoning;
@override@JsonKey(name: 'current_price') final  double? currentPrice;
@override@JsonKey(name: 'pnl_pct') final  double? pnlPct;
@override final  double? rsi;
@override@JsonKey(name: 'news_count') final  int newsCount;

/// Create a copy of AdvisorVerdict
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$AdvisorVerdictCopyWith<_AdvisorVerdict> get copyWith => __$AdvisorVerdictCopyWithImpl<_AdvisorVerdict>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$AdvisorVerdictToJson(this, );
}

@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _AdvisorVerdict&&(identical(other.verdict, verdict) || other.verdict == verdict)&&(identical(other.actionSummary, actionSummary) || other.actionSummary == actionSummary)&&(identical(other.entryRange, entryRange) || other.entryRange == entryRange)&&(identical(other.targetPrice, targetPrice) || other.targetPrice == targetPrice)&&(identical(other.stopLoss, stopLoss) || other.stopLoss == stopLoss)&&(identical(other.sellPct, sellPct) || other.sellPct == sellPct)&&(identical(other.timeHorizon, timeHorizon) || other.timeHorizon == timeHorizon)&&(identical(other.riskLevel, riskLevel) || other.riskLevel == riskLevel)&&(identical(other.confidence, confidence) || other.confidence == confidence)&&(identical(other.reasoning, reasoning) || other.reasoning == reasoning)&&(identical(other.currentPrice, currentPrice) || other.currentPrice == currentPrice)&&(identical(other.pnlPct, pnlPct) || other.pnlPct == pnlPct)&&(identical(other.rsi, rsi) || other.rsi == rsi)&&(identical(other.newsCount, newsCount) || other.newsCount == newsCount));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,verdict,actionSummary,entryRange,targetPrice,stopLoss,sellPct,timeHorizon,riskLevel,confidence,reasoning,currentPrice,pnlPct,rsi,newsCount);

@override
String toString() {
  return 'AdvisorVerdict(verdict: $verdict, actionSummary: $actionSummary, entryRange: $entryRange, targetPrice: $targetPrice, stopLoss: $stopLoss, sellPct: $sellPct, timeHorizon: $timeHorizon, riskLevel: $riskLevel, confidence: $confidence, reasoning: $reasoning, currentPrice: $currentPrice, pnlPct: $pnlPct, rsi: $rsi, newsCount: $newsCount)';
}


}

/// @nodoc
abstract mixin class _$AdvisorVerdictCopyWith<$Res> implements $AdvisorVerdictCopyWith<$Res> {
  factory _$AdvisorVerdictCopyWith(_AdvisorVerdict value, $Res Function(_AdvisorVerdict) _then) = __$AdvisorVerdictCopyWithImpl;
@override @useResult
$Res call({
 String verdict,@JsonKey(name: 'action_summary') String actionSummary,@JsonKey(name: 'entry_range') String? entryRange,@JsonKey(name: 'target_price') String? targetPrice,@JsonKey(name: 'stop_loss') String? stopLoss,@JsonKey(name: 'sell_pct') String? sellPct,@JsonKey(name: 'time_horizon') String timeHorizon,@JsonKey(name: 'risk_level') String riskLevel, int confidence, String reasoning,@JsonKey(name: 'current_price') double? currentPrice,@JsonKey(name: 'pnl_pct') double? pnlPct, double? rsi,@JsonKey(name: 'news_count') int newsCount
});




}
/// @nodoc
class __$AdvisorVerdictCopyWithImpl<$Res>
    implements _$AdvisorVerdictCopyWith<$Res> {
  __$AdvisorVerdictCopyWithImpl(this._self, this._then);

  final _AdvisorVerdict _self;
  final $Res Function(_AdvisorVerdict) _then;

/// Create a copy of AdvisorVerdict
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? verdict = null,Object? actionSummary = null,Object? entryRange = freezed,Object? targetPrice = freezed,Object? stopLoss = freezed,Object? sellPct = freezed,Object? timeHorizon = null,Object? riskLevel = null,Object? confidence = null,Object? reasoning = null,Object? currentPrice = freezed,Object? pnlPct = freezed,Object? rsi = freezed,Object? newsCount = null,}) {
  return _then(_AdvisorVerdict(
verdict: null == verdict ? _self.verdict : verdict // ignore: cast_nullable_to_non_nullable
as String,actionSummary: null == actionSummary ? _self.actionSummary : actionSummary // ignore: cast_nullable_to_non_nullable
as String,entryRange: freezed == entryRange ? _self.entryRange : entryRange // ignore: cast_nullable_to_non_nullable
as String?,targetPrice: freezed == targetPrice ? _self.targetPrice : targetPrice // ignore: cast_nullable_to_non_nullable
as String?,stopLoss: freezed == stopLoss ? _self.stopLoss : stopLoss // ignore: cast_nullable_to_non_nullable
as String?,sellPct: freezed == sellPct ? _self.sellPct : sellPct // ignore: cast_nullable_to_non_nullable
as String?,timeHorizon: null == timeHorizon ? _self.timeHorizon : timeHorizon // ignore: cast_nullable_to_non_nullable
as String,riskLevel: null == riskLevel ? _self.riskLevel : riskLevel // ignore: cast_nullable_to_non_nullable
as String,confidence: null == confidence ? _self.confidence : confidence // ignore: cast_nullable_to_non_nullable
as int,reasoning: null == reasoning ? _self.reasoning : reasoning // ignore: cast_nullable_to_non_nullable
as String,currentPrice: freezed == currentPrice ? _self.currentPrice : currentPrice // ignore: cast_nullable_to_non_nullable
as double?,pnlPct: freezed == pnlPct ? _self.pnlPct : pnlPct // ignore: cast_nullable_to_non_nullable
as double?,rsi: freezed == rsi ? _self.rsi : rsi // ignore: cast_nullable_to_non_nullable
as double?,newsCount: null == newsCount ? _self.newsCount : newsCount // ignore: cast_nullable_to_non_nullable
as int,
  ));
}


}


/// @nodoc
mixin _$AnalyticsData {

@JsonKey(name: 'portfolio_beta') double get portfolioBeta;@JsonKey(name: 'sharpe_ratio') double get sharpeRatio;@JsonKey(name: 'projected_1y_return') double get projected1yReturn;@JsonKey(name: 'nifty_1y_return') double get nifty1yReturn;@JsonKey(name: 'volatility_index') double get volatilityIndex;@JsonKey(name: 'diversification_score') int get diversificationScore;@JsonKey(name: 'top_performer') String get topPerformer;@JsonKey(name: 'worst_performer') String get worstPerformer;
/// Create a copy of AnalyticsData
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$AnalyticsDataCopyWith<AnalyticsData> get copyWith => _$AnalyticsDataCopyWithImpl<AnalyticsData>(this as AnalyticsData, _$identity);

  /// Serializes this AnalyticsData to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is AnalyticsData&&(identical(other.portfolioBeta, portfolioBeta) || other.portfolioBeta == portfolioBeta)&&(identical(other.sharpeRatio, sharpeRatio) || other.sharpeRatio == sharpeRatio)&&(identical(other.projected1yReturn, projected1yReturn) || other.projected1yReturn == projected1yReturn)&&(identical(other.nifty1yReturn, nifty1yReturn) || other.nifty1yReturn == nifty1yReturn)&&(identical(other.volatilityIndex, volatilityIndex) || other.volatilityIndex == volatilityIndex)&&(identical(other.diversificationScore, diversificationScore) || other.diversificationScore == diversificationScore)&&(identical(other.topPerformer, topPerformer) || other.topPerformer == topPerformer)&&(identical(other.worstPerformer, worstPerformer) || other.worstPerformer == worstPerformer));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,portfolioBeta,sharpeRatio,projected1yReturn,nifty1yReturn,volatilityIndex,diversificationScore,topPerformer,worstPerformer);

@override
String toString() {
  return 'AnalyticsData(portfolioBeta: $portfolioBeta, sharpeRatio: $sharpeRatio, projected1yReturn: $projected1yReturn, nifty1yReturn: $nifty1yReturn, volatilityIndex: $volatilityIndex, diversificationScore: $diversificationScore, topPerformer: $topPerformer, worstPerformer: $worstPerformer)';
}


}

/// @nodoc
abstract mixin class $AnalyticsDataCopyWith<$Res>  {
  factory $AnalyticsDataCopyWith(AnalyticsData value, $Res Function(AnalyticsData) _then) = _$AnalyticsDataCopyWithImpl;
@useResult
$Res call({
@JsonKey(name: 'portfolio_beta') double portfolioBeta,@JsonKey(name: 'sharpe_ratio') double sharpeRatio,@JsonKey(name: 'projected_1y_return') double projected1yReturn,@JsonKey(name: 'nifty_1y_return') double nifty1yReturn,@JsonKey(name: 'volatility_index') double volatilityIndex,@JsonKey(name: 'diversification_score') int diversificationScore,@JsonKey(name: 'top_performer') String topPerformer,@JsonKey(name: 'worst_performer') String worstPerformer
});




}
/// @nodoc
class _$AnalyticsDataCopyWithImpl<$Res>
    implements $AnalyticsDataCopyWith<$Res> {
  _$AnalyticsDataCopyWithImpl(this._self, this._then);

  final AnalyticsData _self;
  final $Res Function(AnalyticsData) _then;

/// Create a copy of AnalyticsData
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? portfolioBeta = null,Object? sharpeRatio = null,Object? projected1yReturn = null,Object? nifty1yReturn = null,Object? volatilityIndex = null,Object? diversificationScore = null,Object? topPerformer = null,Object? worstPerformer = null,}) {
  return _then(_self.copyWith(
portfolioBeta: null == portfolioBeta ? _self.portfolioBeta : portfolioBeta // ignore: cast_nullable_to_non_nullable
as double,sharpeRatio: null == sharpeRatio ? _self.sharpeRatio : sharpeRatio // ignore: cast_nullable_to_non_nullable
as double,projected1yReturn: null == projected1yReturn ? _self.projected1yReturn : projected1yReturn // ignore: cast_nullable_to_non_nullable
as double,nifty1yReturn: null == nifty1yReturn ? _self.nifty1yReturn : nifty1yReturn // ignore: cast_nullable_to_non_nullable
as double,volatilityIndex: null == volatilityIndex ? _self.volatilityIndex : volatilityIndex // ignore: cast_nullable_to_non_nullable
as double,diversificationScore: null == diversificationScore ? _self.diversificationScore : diversificationScore // ignore: cast_nullable_to_non_nullable
as int,topPerformer: null == topPerformer ? _self.topPerformer : topPerformer // ignore: cast_nullable_to_non_nullable
as String,worstPerformer: null == worstPerformer ? _self.worstPerformer : worstPerformer // ignore: cast_nullable_to_non_nullable
as String,
  ));
}

}


/// Adds pattern-matching-related methods to [AnalyticsData].
extension AnalyticsDataPatterns on AnalyticsData {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _AnalyticsData value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _AnalyticsData() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _AnalyticsData value)  $default,){
final _that = this;
switch (_that) {
case _AnalyticsData():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _AnalyticsData value)?  $default,){
final _that = this;
switch (_that) {
case _AnalyticsData() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function(@JsonKey(name: 'portfolio_beta')  double portfolioBeta, @JsonKey(name: 'sharpe_ratio')  double sharpeRatio, @JsonKey(name: 'projected_1y_return')  double projected1yReturn, @JsonKey(name: 'nifty_1y_return')  double nifty1yReturn, @JsonKey(name: 'volatility_index')  double volatilityIndex, @JsonKey(name: 'diversification_score')  int diversificationScore, @JsonKey(name: 'top_performer')  String topPerformer, @JsonKey(name: 'worst_performer')  String worstPerformer)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _AnalyticsData() when $default != null:
return $default(_that.portfolioBeta,_that.sharpeRatio,_that.projected1yReturn,_that.nifty1yReturn,_that.volatilityIndex,_that.diversificationScore,_that.topPerformer,_that.worstPerformer);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function(@JsonKey(name: 'portfolio_beta')  double portfolioBeta, @JsonKey(name: 'sharpe_ratio')  double sharpeRatio, @JsonKey(name: 'projected_1y_return')  double projected1yReturn, @JsonKey(name: 'nifty_1y_return')  double nifty1yReturn, @JsonKey(name: 'volatility_index')  double volatilityIndex, @JsonKey(name: 'diversification_score')  int diversificationScore, @JsonKey(name: 'top_performer')  String topPerformer, @JsonKey(name: 'worst_performer')  String worstPerformer)  $default,) {final _that = this;
switch (_that) {
case _AnalyticsData():
return $default(_that.portfolioBeta,_that.sharpeRatio,_that.projected1yReturn,_that.nifty1yReturn,_that.volatilityIndex,_that.diversificationScore,_that.topPerformer,_that.worstPerformer);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function(@JsonKey(name: 'portfolio_beta')  double portfolioBeta, @JsonKey(name: 'sharpe_ratio')  double sharpeRatio, @JsonKey(name: 'projected_1y_return')  double projected1yReturn, @JsonKey(name: 'nifty_1y_return')  double nifty1yReturn, @JsonKey(name: 'volatility_index')  double volatilityIndex, @JsonKey(name: 'diversification_score')  int diversificationScore, @JsonKey(name: 'top_performer')  String topPerformer, @JsonKey(name: 'worst_performer')  String worstPerformer)?  $default,) {final _that = this;
switch (_that) {
case _AnalyticsData() when $default != null:
return $default(_that.portfolioBeta,_that.sharpeRatio,_that.projected1yReturn,_that.nifty1yReturn,_that.volatilityIndex,_that.diversificationScore,_that.topPerformer,_that.worstPerformer);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _AnalyticsData implements AnalyticsData {
  const _AnalyticsData({@JsonKey(name: 'portfolio_beta') this.portfolioBeta = 1.0, @JsonKey(name: 'sharpe_ratio') this.sharpeRatio = 0, @JsonKey(name: 'projected_1y_return') this.projected1yReturn = 0, @JsonKey(name: 'nifty_1y_return') this.nifty1yReturn = 14.2, @JsonKey(name: 'volatility_index') this.volatilityIndex = 0, @JsonKey(name: 'diversification_score') this.diversificationScore = 0, @JsonKey(name: 'top_performer') this.topPerformer = 'N/A', @JsonKey(name: 'worst_performer') this.worstPerformer = 'N/A'});
  factory _AnalyticsData.fromJson(Map<String, dynamic> json) => _$AnalyticsDataFromJson(json);

@override@JsonKey(name: 'portfolio_beta') final  double portfolioBeta;
@override@JsonKey(name: 'sharpe_ratio') final  double sharpeRatio;
@override@JsonKey(name: 'projected_1y_return') final  double projected1yReturn;
@override@JsonKey(name: 'nifty_1y_return') final  double nifty1yReturn;
@override@JsonKey(name: 'volatility_index') final  double volatilityIndex;
@override@JsonKey(name: 'diversification_score') final  int diversificationScore;
@override@JsonKey(name: 'top_performer') final  String topPerformer;
@override@JsonKey(name: 'worst_performer') final  String worstPerformer;

/// Create a copy of AnalyticsData
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$AnalyticsDataCopyWith<_AnalyticsData> get copyWith => __$AnalyticsDataCopyWithImpl<_AnalyticsData>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$AnalyticsDataToJson(this, );
}

@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _AnalyticsData&&(identical(other.portfolioBeta, portfolioBeta) || other.portfolioBeta == portfolioBeta)&&(identical(other.sharpeRatio, sharpeRatio) || other.sharpeRatio == sharpeRatio)&&(identical(other.projected1yReturn, projected1yReturn) || other.projected1yReturn == projected1yReturn)&&(identical(other.nifty1yReturn, nifty1yReturn) || other.nifty1yReturn == nifty1yReturn)&&(identical(other.volatilityIndex, volatilityIndex) || other.volatilityIndex == volatilityIndex)&&(identical(other.diversificationScore, diversificationScore) || other.diversificationScore == diversificationScore)&&(identical(other.topPerformer, topPerformer) || other.topPerformer == topPerformer)&&(identical(other.worstPerformer, worstPerformer) || other.worstPerformer == worstPerformer));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,portfolioBeta,sharpeRatio,projected1yReturn,nifty1yReturn,volatilityIndex,diversificationScore,topPerformer,worstPerformer);

@override
String toString() {
  return 'AnalyticsData(portfolioBeta: $portfolioBeta, sharpeRatio: $sharpeRatio, projected1yReturn: $projected1yReturn, nifty1yReturn: $nifty1yReturn, volatilityIndex: $volatilityIndex, diversificationScore: $diversificationScore, topPerformer: $topPerformer, worstPerformer: $worstPerformer)';
}


}

/// @nodoc
abstract mixin class _$AnalyticsDataCopyWith<$Res> implements $AnalyticsDataCopyWith<$Res> {
  factory _$AnalyticsDataCopyWith(_AnalyticsData value, $Res Function(_AnalyticsData) _then) = __$AnalyticsDataCopyWithImpl;
@override @useResult
$Res call({
@JsonKey(name: 'portfolio_beta') double portfolioBeta,@JsonKey(name: 'sharpe_ratio') double sharpeRatio,@JsonKey(name: 'projected_1y_return') double projected1yReturn,@JsonKey(name: 'nifty_1y_return') double nifty1yReturn,@JsonKey(name: 'volatility_index') double volatilityIndex,@JsonKey(name: 'diversification_score') int diversificationScore,@JsonKey(name: 'top_performer') String topPerformer,@JsonKey(name: 'worst_performer') String worstPerformer
});




}
/// @nodoc
class __$AnalyticsDataCopyWithImpl<$Res>
    implements _$AnalyticsDataCopyWith<$Res> {
  __$AnalyticsDataCopyWithImpl(this._self, this._then);

  final _AnalyticsData _self;
  final $Res Function(_AnalyticsData) _then;

/// Create a copy of AnalyticsData
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? portfolioBeta = null,Object? sharpeRatio = null,Object? projected1yReturn = null,Object? nifty1yReturn = null,Object? volatilityIndex = null,Object? diversificationScore = null,Object? topPerformer = null,Object? worstPerformer = null,}) {
  return _then(_AnalyticsData(
portfolioBeta: null == portfolioBeta ? _self.portfolioBeta : portfolioBeta // ignore: cast_nullable_to_non_nullable
as double,sharpeRatio: null == sharpeRatio ? _self.sharpeRatio : sharpeRatio // ignore: cast_nullable_to_non_nullable
as double,projected1yReturn: null == projected1yReturn ? _self.projected1yReturn : projected1yReturn // ignore: cast_nullable_to_non_nullable
as double,nifty1yReturn: null == nifty1yReturn ? _self.nifty1yReturn : nifty1yReturn // ignore: cast_nullable_to_non_nullable
as double,volatilityIndex: null == volatilityIndex ? _self.volatilityIndex : volatilityIndex // ignore: cast_nullable_to_non_nullable
as double,diversificationScore: null == diversificationScore ? _self.diversificationScore : diversificationScore // ignore: cast_nullable_to_non_nullable
as int,topPerformer: null == topPerformer ? _self.topPerformer : topPerformer // ignore: cast_nullable_to_non_nullable
as String,worstPerformer: null == worstPerformer ? _self.worstPerformer : worstPerformer // ignore: cast_nullable_to_non_nullable
as String,
  ));
}


}


/// @nodoc
mixin _$UserProfile {

 String get name; String get email; String get picture;@JsonKey(name: 'logged_in') bool get loggedIn; bool get authenticated;
/// Create a copy of UserProfile
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$UserProfileCopyWith<UserProfile> get copyWith => _$UserProfileCopyWithImpl<UserProfile>(this as UserProfile, _$identity);

  /// Serializes this UserProfile to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is UserProfile&&(identical(other.name, name) || other.name == name)&&(identical(other.email, email) || other.email == email)&&(identical(other.picture, picture) || other.picture == picture)&&(identical(other.loggedIn, loggedIn) || other.loggedIn == loggedIn)&&(identical(other.authenticated, authenticated) || other.authenticated == authenticated));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,name,email,picture,loggedIn,authenticated);

@override
String toString() {
  return 'UserProfile(name: $name, email: $email, picture: $picture, loggedIn: $loggedIn, authenticated: $authenticated)';
}


}

/// @nodoc
abstract mixin class $UserProfileCopyWith<$Res>  {
  factory $UserProfileCopyWith(UserProfile value, $Res Function(UserProfile) _then) = _$UserProfileCopyWithImpl;
@useResult
$Res call({
 String name, String email, String picture,@JsonKey(name: 'logged_in') bool loggedIn, bool authenticated
});




}
/// @nodoc
class _$UserProfileCopyWithImpl<$Res>
    implements $UserProfileCopyWith<$Res> {
  _$UserProfileCopyWithImpl(this._self, this._then);

  final UserProfile _self;
  final $Res Function(UserProfile) _then;

/// Create a copy of UserProfile
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? name = null,Object? email = null,Object? picture = null,Object? loggedIn = null,Object? authenticated = null,}) {
  return _then(_self.copyWith(
name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,email: null == email ? _self.email : email // ignore: cast_nullable_to_non_nullable
as String,picture: null == picture ? _self.picture : picture // ignore: cast_nullable_to_non_nullable
as String,loggedIn: null == loggedIn ? _self.loggedIn : loggedIn // ignore: cast_nullable_to_non_nullable
as bool,authenticated: null == authenticated ? _self.authenticated : authenticated // ignore: cast_nullable_to_non_nullable
as bool,
  ));
}

}


/// Adds pattern-matching-related methods to [UserProfile].
extension UserProfilePatterns on UserProfile {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _UserProfile value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _UserProfile() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _UserProfile value)  $default,){
final _that = this;
switch (_that) {
case _UserProfile():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _UserProfile value)?  $default,){
final _that = this;
switch (_that) {
case _UserProfile() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String name,  String email,  String picture, @JsonKey(name: 'logged_in')  bool loggedIn,  bool authenticated)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _UserProfile() when $default != null:
return $default(_that.name,_that.email,_that.picture,_that.loggedIn,_that.authenticated);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String name,  String email,  String picture, @JsonKey(name: 'logged_in')  bool loggedIn,  bool authenticated)  $default,) {final _that = this;
switch (_that) {
case _UserProfile():
return $default(_that.name,_that.email,_that.picture,_that.loggedIn,_that.authenticated);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String name,  String email,  String picture, @JsonKey(name: 'logged_in')  bool loggedIn,  bool authenticated)?  $default,) {final _that = this;
switch (_that) {
case _UserProfile() when $default != null:
return $default(_that.name,_that.email,_that.picture,_that.loggedIn,_that.authenticated);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _UserProfile implements UserProfile {
  const _UserProfile({this.name = '', this.email = '', this.picture = '', @JsonKey(name: 'logged_in') this.loggedIn = false, this.authenticated = false});
  factory _UserProfile.fromJson(Map<String, dynamic> json) => _$UserProfileFromJson(json);

@override@JsonKey() final  String name;
@override@JsonKey() final  String email;
@override@JsonKey() final  String picture;
@override@JsonKey(name: 'logged_in') final  bool loggedIn;
@override@JsonKey() final  bool authenticated;

/// Create a copy of UserProfile
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$UserProfileCopyWith<_UserProfile> get copyWith => __$UserProfileCopyWithImpl<_UserProfile>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$UserProfileToJson(this, );
}

@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _UserProfile&&(identical(other.name, name) || other.name == name)&&(identical(other.email, email) || other.email == email)&&(identical(other.picture, picture) || other.picture == picture)&&(identical(other.loggedIn, loggedIn) || other.loggedIn == loggedIn)&&(identical(other.authenticated, authenticated) || other.authenticated == authenticated));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,name,email,picture,loggedIn,authenticated);

@override
String toString() {
  return 'UserProfile(name: $name, email: $email, picture: $picture, loggedIn: $loggedIn, authenticated: $authenticated)';
}


}

/// @nodoc
abstract mixin class _$UserProfileCopyWith<$Res> implements $UserProfileCopyWith<$Res> {
  factory _$UserProfileCopyWith(_UserProfile value, $Res Function(_UserProfile) _then) = __$UserProfileCopyWithImpl;
@override @useResult
$Res call({
 String name, String email, String picture,@JsonKey(name: 'logged_in') bool loggedIn, bool authenticated
});




}
/// @nodoc
class __$UserProfileCopyWithImpl<$Res>
    implements _$UserProfileCopyWith<$Res> {
  __$UserProfileCopyWithImpl(this._self, this._then);

  final _UserProfile _self;
  final $Res Function(_UserProfile) _then;

/// Create a copy of UserProfile
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? name = null,Object? email = null,Object? picture = null,Object? loggedIn = null,Object? authenticated = null,}) {
  return _then(_UserProfile(
name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,email: null == email ? _self.email : email // ignore: cast_nullable_to_non_nullable
as String,picture: null == picture ? _self.picture : picture // ignore: cast_nullable_to_non_nullable
as String,loggedIn: null == loggedIn ? _self.loggedIn : loggedIn // ignore: cast_nullable_to_non_nullable
as bool,authenticated: null == authenticated ? _self.authenticated : authenticated // ignore: cast_nullable_to_non_nullable
as bool,
  ));
}


}


/// @nodoc
mixin _$AppSettings {

@JsonKey(name: 'ollama_url') String get ollamaUrl;@JsonKey(name: 'model_name') String get modelName; String get theme;@JsonKey(name: 'auto_refresh_nav') bool get autoRefreshNav;@JsonKey(name: 'nav_refresh_interval') int get navRefreshInterval;
/// Create a copy of AppSettings
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$AppSettingsCopyWith<AppSettings> get copyWith => _$AppSettingsCopyWithImpl<AppSettings>(this as AppSettings, _$identity);

  /// Serializes this AppSettings to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is AppSettings&&(identical(other.ollamaUrl, ollamaUrl) || other.ollamaUrl == ollamaUrl)&&(identical(other.modelName, modelName) || other.modelName == modelName)&&(identical(other.theme, theme) || other.theme == theme)&&(identical(other.autoRefreshNav, autoRefreshNav) || other.autoRefreshNav == autoRefreshNav)&&(identical(other.navRefreshInterval, navRefreshInterval) || other.navRefreshInterval == navRefreshInterval));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,ollamaUrl,modelName,theme,autoRefreshNav,navRefreshInterval);

@override
String toString() {
  return 'AppSettings(ollamaUrl: $ollamaUrl, modelName: $modelName, theme: $theme, autoRefreshNav: $autoRefreshNav, navRefreshInterval: $navRefreshInterval)';
}


}

/// @nodoc
abstract mixin class $AppSettingsCopyWith<$Res>  {
  factory $AppSettingsCopyWith(AppSettings value, $Res Function(AppSettings) _then) = _$AppSettingsCopyWithImpl;
@useResult
$Res call({
@JsonKey(name: 'ollama_url') String ollamaUrl,@JsonKey(name: 'model_name') String modelName, String theme,@JsonKey(name: 'auto_refresh_nav') bool autoRefreshNav,@JsonKey(name: 'nav_refresh_interval') int navRefreshInterval
});




}
/// @nodoc
class _$AppSettingsCopyWithImpl<$Res>
    implements $AppSettingsCopyWith<$Res> {
  _$AppSettingsCopyWithImpl(this._self, this._then);

  final AppSettings _self;
  final $Res Function(AppSettings) _then;

/// Create a copy of AppSettings
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? ollamaUrl = null,Object? modelName = null,Object? theme = null,Object? autoRefreshNav = null,Object? navRefreshInterval = null,}) {
  return _then(_self.copyWith(
ollamaUrl: null == ollamaUrl ? _self.ollamaUrl : ollamaUrl // ignore: cast_nullable_to_non_nullable
as String,modelName: null == modelName ? _self.modelName : modelName // ignore: cast_nullable_to_non_nullable
as String,theme: null == theme ? _self.theme : theme // ignore: cast_nullable_to_non_nullable
as String,autoRefreshNav: null == autoRefreshNav ? _self.autoRefreshNav : autoRefreshNav // ignore: cast_nullable_to_non_nullable
as bool,navRefreshInterval: null == navRefreshInterval ? _self.navRefreshInterval : navRefreshInterval // ignore: cast_nullable_to_non_nullable
as int,
  ));
}

}


/// Adds pattern-matching-related methods to [AppSettings].
extension AppSettingsPatterns on AppSettings {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _AppSettings value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _AppSettings() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _AppSettings value)  $default,){
final _that = this;
switch (_that) {
case _AppSettings():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _AppSettings value)?  $default,){
final _that = this;
switch (_that) {
case _AppSettings() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function(@JsonKey(name: 'ollama_url')  String ollamaUrl, @JsonKey(name: 'model_name')  String modelName,  String theme, @JsonKey(name: 'auto_refresh_nav')  bool autoRefreshNav, @JsonKey(name: 'nav_refresh_interval')  int navRefreshInterval)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _AppSettings() when $default != null:
return $default(_that.ollamaUrl,_that.modelName,_that.theme,_that.autoRefreshNav,_that.navRefreshInterval);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function(@JsonKey(name: 'ollama_url')  String ollamaUrl, @JsonKey(name: 'model_name')  String modelName,  String theme, @JsonKey(name: 'auto_refresh_nav')  bool autoRefreshNav, @JsonKey(name: 'nav_refresh_interval')  int navRefreshInterval)  $default,) {final _that = this;
switch (_that) {
case _AppSettings():
return $default(_that.ollamaUrl,_that.modelName,_that.theme,_that.autoRefreshNav,_that.navRefreshInterval);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function(@JsonKey(name: 'ollama_url')  String ollamaUrl, @JsonKey(name: 'model_name')  String modelName,  String theme, @JsonKey(name: 'auto_refresh_nav')  bool autoRefreshNav, @JsonKey(name: 'nav_refresh_interval')  int navRefreshInterval)?  $default,) {final _that = this;
switch (_that) {
case _AppSettings() when $default != null:
return $default(_that.ollamaUrl,_that.modelName,_that.theme,_that.autoRefreshNav,_that.navRefreshInterval);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _AppSettings implements AppSettings {
  const _AppSettings({@JsonKey(name: 'ollama_url') this.ollamaUrl = 'http://localhost:11434', @JsonKey(name: 'model_name') this.modelName = 'qwen3.6:35b', this.theme = 'dark', @JsonKey(name: 'auto_refresh_nav') this.autoRefreshNav = true, @JsonKey(name: 'nav_refresh_interval') this.navRefreshInterval = 300});
  factory _AppSettings.fromJson(Map<String, dynamic> json) => _$AppSettingsFromJson(json);

@override@JsonKey(name: 'ollama_url') final  String ollamaUrl;
@override@JsonKey(name: 'model_name') final  String modelName;
@override@JsonKey() final  String theme;
@override@JsonKey(name: 'auto_refresh_nav') final  bool autoRefreshNav;
@override@JsonKey(name: 'nav_refresh_interval') final  int navRefreshInterval;

/// Create a copy of AppSettings
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$AppSettingsCopyWith<_AppSettings> get copyWith => __$AppSettingsCopyWithImpl<_AppSettings>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$AppSettingsToJson(this, );
}

@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _AppSettings&&(identical(other.ollamaUrl, ollamaUrl) || other.ollamaUrl == ollamaUrl)&&(identical(other.modelName, modelName) || other.modelName == modelName)&&(identical(other.theme, theme) || other.theme == theme)&&(identical(other.autoRefreshNav, autoRefreshNav) || other.autoRefreshNav == autoRefreshNav)&&(identical(other.navRefreshInterval, navRefreshInterval) || other.navRefreshInterval == navRefreshInterval));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,ollamaUrl,modelName,theme,autoRefreshNav,navRefreshInterval);

@override
String toString() {
  return 'AppSettings(ollamaUrl: $ollamaUrl, modelName: $modelName, theme: $theme, autoRefreshNav: $autoRefreshNav, navRefreshInterval: $navRefreshInterval)';
}


}

/// @nodoc
abstract mixin class _$AppSettingsCopyWith<$Res> implements $AppSettingsCopyWith<$Res> {
  factory _$AppSettingsCopyWith(_AppSettings value, $Res Function(_AppSettings) _then) = __$AppSettingsCopyWithImpl;
@override @useResult
$Res call({
@JsonKey(name: 'ollama_url') String ollamaUrl,@JsonKey(name: 'model_name') String modelName, String theme,@JsonKey(name: 'auto_refresh_nav') bool autoRefreshNav,@JsonKey(name: 'nav_refresh_interval') int navRefreshInterval
});




}
/// @nodoc
class __$AppSettingsCopyWithImpl<$Res>
    implements _$AppSettingsCopyWith<$Res> {
  __$AppSettingsCopyWithImpl(this._self, this._then);

  final _AppSettings _self;
  final $Res Function(_AppSettings) _then;

/// Create a copy of AppSettings
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? ollamaUrl = null,Object? modelName = null,Object? theme = null,Object? autoRefreshNav = null,Object? navRefreshInterval = null,}) {
  return _then(_AppSettings(
ollamaUrl: null == ollamaUrl ? _self.ollamaUrl : ollamaUrl // ignore: cast_nullable_to_non_nullable
as String,modelName: null == modelName ? _self.modelName : modelName // ignore: cast_nullable_to_non_nullable
as String,theme: null == theme ? _self.theme : theme // ignore: cast_nullable_to_non_nullable
as String,autoRefreshNav: null == autoRefreshNav ? _self.autoRefreshNav : autoRefreshNav // ignore: cast_nullable_to_non_nullable
as bool,navRefreshInterval: null == navRefreshInterval ? _self.navRefreshInterval : navRefreshInterval // ignore: cast_nullable_to_non_nullable
as int,
  ));
}


}


/// @nodoc
mixin _$SIPTimelinePoint {

 String get date; double get invested; double get value; double get pnl;@JsonKey(name: 'pnl_pct') double get pnlPct;
/// Create a copy of SIPTimelinePoint
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$SIPTimelinePointCopyWith<SIPTimelinePoint> get copyWith => _$SIPTimelinePointCopyWithImpl<SIPTimelinePoint>(this as SIPTimelinePoint, _$identity);

  /// Serializes this SIPTimelinePoint to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is SIPTimelinePoint&&(identical(other.date, date) || other.date == date)&&(identical(other.invested, invested) || other.invested == invested)&&(identical(other.value, value) || other.value == value)&&(identical(other.pnl, pnl) || other.pnl == pnl)&&(identical(other.pnlPct, pnlPct) || other.pnlPct == pnlPct));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,date,invested,value,pnl,pnlPct);

@override
String toString() {
  return 'SIPTimelinePoint(date: $date, invested: $invested, value: $value, pnl: $pnl, pnlPct: $pnlPct)';
}


}

/// @nodoc
abstract mixin class $SIPTimelinePointCopyWith<$Res>  {
  factory $SIPTimelinePointCopyWith(SIPTimelinePoint value, $Res Function(SIPTimelinePoint) _then) = _$SIPTimelinePointCopyWithImpl;
@useResult
$Res call({
 String date, double invested, double value, double pnl,@JsonKey(name: 'pnl_pct') double pnlPct
});




}
/// @nodoc
class _$SIPTimelinePointCopyWithImpl<$Res>
    implements $SIPTimelinePointCopyWith<$Res> {
  _$SIPTimelinePointCopyWithImpl(this._self, this._then);

  final SIPTimelinePoint _self;
  final $Res Function(SIPTimelinePoint) _then;

/// Create a copy of SIPTimelinePoint
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? date = null,Object? invested = null,Object? value = null,Object? pnl = null,Object? pnlPct = null,}) {
  return _then(_self.copyWith(
date: null == date ? _self.date : date // ignore: cast_nullable_to_non_nullable
as String,invested: null == invested ? _self.invested : invested // ignore: cast_nullable_to_non_nullable
as double,value: null == value ? _self.value : value // ignore: cast_nullable_to_non_nullable
as double,pnl: null == pnl ? _self.pnl : pnl // ignore: cast_nullable_to_non_nullable
as double,pnlPct: null == pnlPct ? _self.pnlPct : pnlPct // ignore: cast_nullable_to_non_nullable
as double,
  ));
}

}


/// Adds pattern-matching-related methods to [SIPTimelinePoint].
extension SIPTimelinePointPatterns on SIPTimelinePoint {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _SIPTimelinePoint value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _SIPTimelinePoint() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _SIPTimelinePoint value)  $default,){
final _that = this;
switch (_that) {
case _SIPTimelinePoint():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _SIPTimelinePoint value)?  $default,){
final _that = this;
switch (_that) {
case _SIPTimelinePoint() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String date,  double invested,  double value,  double pnl, @JsonKey(name: 'pnl_pct')  double pnlPct)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _SIPTimelinePoint() when $default != null:
return $default(_that.date,_that.invested,_that.value,_that.pnl,_that.pnlPct);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String date,  double invested,  double value,  double pnl, @JsonKey(name: 'pnl_pct')  double pnlPct)  $default,) {final _that = this;
switch (_that) {
case _SIPTimelinePoint():
return $default(_that.date,_that.invested,_that.value,_that.pnl,_that.pnlPct);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String date,  double invested,  double value,  double pnl, @JsonKey(name: 'pnl_pct')  double pnlPct)?  $default,) {final _that = this;
switch (_that) {
case _SIPTimelinePoint() when $default != null:
return $default(_that.date,_that.invested,_that.value,_that.pnl,_that.pnlPct);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _SIPTimelinePoint implements SIPTimelinePoint {
  const _SIPTimelinePoint({required this.date, this.invested = 0, this.value = 0, this.pnl = 0, @JsonKey(name: 'pnl_pct') this.pnlPct = 0});
  factory _SIPTimelinePoint.fromJson(Map<String, dynamic> json) => _$SIPTimelinePointFromJson(json);

@override final  String date;
@override@JsonKey() final  double invested;
@override@JsonKey() final  double value;
@override@JsonKey() final  double pnl;
@override@JsonKey(name: 'pnl_pct') final  double pnlPct;

/// Create a copy of SIPTimelinePoint
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$SIPTimelinePointCopyWith<_SIPTimelinePoint> get copyWith => __$SIPTimelinePointCopyWithImpl<_SIPTimelinePoint>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$SIPTimelinePointToJson(this, );
}

@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _SIPTimelinePoint&&(identical(other.date, date) || other.date == date)&&(identical(other.invested, invested) || other.invested == invested)&&(identical(other.value, value) || other.value == value)&&(identical(other.pnl, pnl) || other.pnl == pnl)&&(identical(other.pnlPct, pnlPct) || other.pnlPct == pnlPct));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,date,invested,value,pnl,pnlPct);

@override
String toString() {
  return 'SIPTimelinePoint(date: $date, invested: $invested, value: $value, pnl: $pnl, pnlPct: $pnlPct)';
}


}

/// @nodoc
abstract mixin class _$SIPTimelinePointCopyWith<$Res> implements $SIPTimelinePointCopyWith<$Res> {
  factory _$SIPTimelinePointCopyWith(_SIPTimelinePoint value, $Res Function(_SIPTimelinePoint) _then) = __$SIPTimelinePointCopyWithImpl;
@override @useResult
$Res call({
 String date, double invested, double value, double pnl,@JsonKey(name: 'pnl_pct') double pnlPct
});




}
/// @nodoc
class __$SIPTimelinePointCopyWithImpl<$Res>
    implements _$SIPTimelinePointCopyWith<$Res> {
  __$SIPTimelinePointCopyWithImpl(this._self, this._then);

  final _SIPTimelinePoint _self;
  final $Res Function(_SIPTimelinePoint) _then;

/// Create a copy of SIPTimelinePoint
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? date = null,Object? invested = null,Object? value = null,Object? pnl = null,Object? pnlPct = null,}) {
  return _then(_SIPTimelinePoint(
date: null == date ? _self.date : date // ignore: cast_nullable_to_non_nullable
as String,invested: null == invested ? _self.invested : invested // ignore: cast_nullable_to_non_nullable
as double,value: null == value ? _self.value : value // ignore: cast_nullable_to_non_nullable
as double,pnl: null == pnl ? _self.pnl : pnl // ignore: cast_nullable_to_non_nullable
as double,pnlPct: null == pnlPct ? _self.pnlPct : pnlPct // ignore: cast_nullable_to_non_nullable
as double,
  ));
}


}


/// @nodoc
mixin _$SIPYearlySummary {

 String get year; double get invested; int get months;@JsonKey(name: 'cumulative_units') double get cumulativeUnits;@JsonKey(name: 'cumulative_invested') double get cumulativeInvested; double get nav; double get value; double get pnl;@JsonKey(name: 'return_pct') double get returnPct;
/// Create a copy of SIPYearlySummary
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$SIPYearlySummaryCopyWith<SIPYearlySummary> get copyWith => _$SIPYearlySummaryCopyWithImpl<SIPYearlySummary>(this as SIPYearlySummary, _$identity);

  /// Serializes this SIPYearlySummary to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is SIPYearlySummary&&(identical(other.year, year) || other.year == year)&&(identical(other.invested, invested) || other.invested == invested)&&(identical(other.months, months) || other.months == months)&&(identical(other.cumulativeUnits, cumulativeUnits) || other.cumulativeUnits == cumulativeUnits)&&(identical(other.cumulativeInvested, cumulativeInvested) || other.cumulativeInvested == cumulativeInvested)&&(identical(other.nav, nav) || other.nav == nav)&&(identical(other.value, value) || other.value == value)&&(identical(other.pnl, pnl) || other.pnl == pnl)&&(identical(other.returnPct, returnPct) || other.returnPct == returnPct));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,year,invested,months,cumulativeUnits,cumulativeInvested,nav,value,pnl,returnPct);

@override
String toString() {
  return 'SIPYearlySummary(year: $year, invested: $invested, months: $months, cumulativeUnits: $cumulativeUnits, cumulativeInvested: $cumulativeInvested, nav: $nav, value: $value, pnl: $pnl, returnPct: $returnPct)';
}


}

/// @nodoc
abstract mixin class $SIPYearlySummaryCopyWith<$Res>  {
  factory $SIPYearlySummaryCopyWith(SIPYearlySummary value, $Res Function(SIPYearlySummary) _then) = _$SIPYearlySummaryCopyWithImpl;
@useResult
$Res call({
 String year, double invested, int months,@JsonKey(name: 'cumulative_units') double cumulativeUnits,@JsonKey(name: 'cumulative_invested') double cumulativeInvested, double nav, double value, double pnl,@JsonKey(name: 'return_pct') double returnPct
});




}
/// @nodoc
class _$SIPYearlySummaryCopyWithImpl<$Res>
    implements $SIPYearlySummaryCopyWith<$Res> {
  _$SIPYearlySummaryCopyWithImpl(this._self, this._then);

  final SIPYearlySummary _self;
  final $Res Function(SIPYearlySummary) _then;

/// Create a copy of SIPYearlySummary
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? year = null,Object? invested = null,Object? months = null,Object? cumulativeUnits = null,Object? cumulativeInvested = null,Object? nav = null,Object? value = null,Object? pnl = null,Object? returnPct = null,}) {
  return _then(_self.copyWith(
year: null == year ? _self.year : year // ignore: cast_nullable_to_non_nullable
as String,invested: null == invested ? _self.invested : invested // ignore: cast_nullable_to_non_nullable
as double,months: null == months ? _self.months : months // ignore: cast_nullable_to_non_nullable
as int,cumulativeUnits: null == cumulativeUnits ? _self.cumulativeUnits : cumulativeUnits // ignore: cast_nullable_to_non_nullable
as double,cumulativeInvested: null == cumulativeInvested ? _self.cumulativeInvested : cumulativeInvested // ignore: cast_nullable_to_non_nullable
as double,nav: null == nav ? _self.nav : nav // ignore: cast_nullable_to_non_nullable
as double,value: null == value ? _self.value : value // ignore: cast_nullable_to_non_nullable
as double,pnl: null == pnl ? _self.pnl : pnl // ignore: cast_nullable_to_non_nullable
as double,returnPct: null == returnPct ? _self.returnPct : returnPct // ignore: cast_nullable_to_non_nullable
as double,
  ));
}

}


/// Adds pattern-matching-related methods to [SIPYearlySummary].
extension SIPYearlySummaryPatterns on SIPYearlySummary {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _SIPYearlySummary value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _SIPYearlySummary() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _SIPYearlySummary value)  $default,){
final _that = this;
switch (_that) {
case _SIPYearlySummary():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _SIPYearlySummary value)?  $default,){
final _that = this;
switch (_that) {
case _SIPYearlySummary() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String year,  double invested,  int months, @JsonKey(name: 'cumulative_units')  double cumulativeUnits, @JsonKey(name: 'cumulative_invested')  double cumulativeInvested,  double nav,  double value,  double pnl, @JsonKey(name: 'return_pct')  double returnPct)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _SIPYearlySummary() when $default != null:
return $default(_that.year,_that.invested,_that.months,_that.cumulativeUnits,_that.cumulativeInvested,_that.nav,_that.value,_that.pnl,_that.returnPct);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String year,  double invested,  int months, @JsonKey(name: 'cumulative_units')  double cumulativeUnits, @JsonKey(name: 'cumulative_invested')  double cumulativeInvested,  double nav,  double value,  double pnl, @JsonKey(name: 'return_pct')  double returnPct)  $default,) {final _that = this;
switch (_that) {
case _SIPYearlySummary():
return $default(_that.year,_that.invested,_that.months,_that.cumulativeUnits,_that.cumulativeInvested,_that.nav,_that.value,_that.pnl,_that.returnPct);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String year,  double invested,  int months, @JsonKey(name: 'cumulative_units')  double cumulativeUnits, @JsonKey(name: 'cumulative_invested')  double cumulativeInvested,  double nav,  double value,  double pnl, @JsonKey(name: 'return_pct')  double returnPct)?  $default,) {final _that = this;
switch (_that) {
case _SIPYearlySummary() when $default != null:
return $default(_that.year,_that.invested,_that.months,_that.cumulativeUnits,_that.cumulativeInvested,_that.nav,_that.value,_that.pnl,_that.returnPct);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _SIPYearlySummary implements SIPYearlySummary {
  const _SIPYearlySummary({required this.year, this.invested = 0, this.months = 0, @JsonKey(name: 'cumulative_units') this.cumulativeUnits = 0, @JsonKey(name: 'cumulative_invested') this.cumulativeInvested = 0, this.nav = 0, this.value = 0, this.pnl = 0, @JsonKey(name: 'return_pct') this.returnPct = 0});
  factory _SIPYearlySummary.fromJson(Map<String, dynamic> json) => _$SIPYearlySummaryFromJson(json);

@override final  String year;
@override@JsonKey() final  double invested;
@override@JsonKey() final  int months;
@override@JsonKey(name: 'cumulative_units') final  double cumulativeUnits;
@override@JsonKey(name: 'cumulative_invested') final  double cumulativeInvested;
@override@JsonKey() final  double nav;
@override@JsonKey() final  double value;
@override@JsonKey() final  double pnl;
@override@JsonKey(name: 'return_pct') final  double returnPct;

/// Create a copy of SIPYearlySummary
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$SIPYearlySummaryCopyWith<_SIPYearlySummary> get copyWith => __$SIPYearlySummaryCopyWithImpl<_SIPYearlySummary>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$SIPYearlySummaryToJson(this, );
}

@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _SIPYearlySummary&&(identical(other.year, year) || other.year == year)&&(identical(other.invested, invested) || other.invested == invested)&&(identical(other.months, months) || other.months == months)&&(identical(other.cumulativeUnits, cumulativeUnits) || other.cumulativeUnits == cumulativeUnits)&&(identical(other.cumulativeInvested, cumulativeInvested) || other.cumulativeInvested == cumulativeInvested)&&(identical(other.nav, nav) || other.nav == nav)&&(identical(other.value, value) || other.value == value)&&(identical(other.pnl, pnl) || other.pnl == pnl)&&(identical(other.returnPct, returnPct) || other.returnPct == returnPct));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,year,invested,months,cumulativeUnits,cumulativeInvested,nav,value,pnl,returnPct);

@override
String toString() {
  return 'SIPYearlySummary(year: $year, invested: $invested, months: $months, cumulativeUnits: $cumulativeUnits, cumulativeInvested: $cumulativeInvested, nav: $nav, value: $value, pnl: $pnl, returnPct: $returnPct)';
}


}

/// @nodoc
abstract mixin class _$SIPYearlySummaryCopyWith<$Res> implements $SIPYearlySummaryCopyWith<$Res> {
  factory _$SIPYearlySummaryCopyWith(_SIPYearlySummary value, $Res Function(_SIPYearlySummary) _then) = __$SIPYearlySummaryCopyWithImpl;
@override @useResult
$Res call({
 String year, double invested, int months,@JsonKey(name: 'cumulative_units') double cumulativeUnits,@JsonKey(name: 'cumulative_invested') double cumulativeInvested, double nav, double value, double pnl,@JsonKey(name: 'return_pct') double returnPct
});




}
/// @nodoc
class __$SIPYearlySummaryCopyWithImpl<$Res>
    implements _$SIPYearlySummaryCopyWith<$Res> {
  __$SIPYearlySummaryCopyWithImpl(this._self, this._then);

  final _SIPYearlySummary _self;
  final $Res Function(_SIPYearlySummary) _then;

/// Create a copy of SIPYearlySummary
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? year = null,Object? invested = null,Object? months = null,Object? cumulativeUnits = null,Object? cumulativeInvested = null,Object? nav = null,Object? value = null,Object? pnl = null,Object? returnPct = null,}) {
  return _then(_SIPYearlySummary(
year: null == year ? _self.year : year // ignore: cast_nullable_to_non_nullable
as String,invested: null == invested ? _self.invested : invested // ignore: cast_nullable_to_non_nullable
as double,months: null == months ? _self.months : months // ignore: cast_nullable_to_non_nullable
as int,cumulativeUnits: null == cumulativeUnits ? _self.cumulativeUnits : cumulativeUnits // ignore: cast_nullable_to_non_nullable
as double,cumulativeInvested: null == cumulativeInvested ? _self.cumulativeInvested : cumulativeInvested // ignore: cast_nullable_to_non_nullable
as double,nav: null == nav ? _self.nav : nav // ignore: cast_nullable_to_non_nullable
as double,value: null == value ? _self.value : value // ignore: cast_nullable_to_non_nullable
as double,pnl: null == pnl ? _self.pnl : pnl // ignore: cast_nullable_to_non_nullable
as double,returnPct: null == returnPct ? _self.returnPct : returnPct // ignore: cast_nullable_to_non_nullable
as double,
  ));
}


}


/// @nodoc
mixin _$ChatMessage {

 String get role;// 'user' or 'assistant'
 String get content; DateTime? get timestamp;
/// Create a copy of ChatMessage
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$ChatMessageCopyWith<ChatMessage> get copyWith => _$ChatMessageCopyWithImpl<ChatMessage>(this as ChatMessage, _$identity);

  /// Serializes this ChatMessage to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is ChatMessage&&(identical(other.role, role) || other.role == role)&&(identical(other.content, content) || other.content == content)&&(identical(other.timestamp, timestamp) || other.timestamp == timestamp));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,role,content,timestamp);

@override
String toString() {
  return 'ChatMessage(role: $role, content: $content, timestamp: $timestamp)';
}


}

/// @nodoc
abstract mixin class $ChatMessageCopyWith<$Res>  {
  factory $ChatMessageCopyWith(ChatMessage value, $Res Function(ChatMessage) _then) = _$ChatMessageCopyWithImpl;
@useResult
$Res call({
 String role, String content, DateTime? timestamp
});




}
/// @nodoc
class _$ChatMessageCopyWithImpl<$Res>
    implements $ChatMessageCopyWith<$Res> {
  _$ChatMessageCopyWithImpl(this._self, this._then);

  final ChatMessage _self;
  final $Res Function(ChatMessage) _then;

/// Create a copy of ChatMessage
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? role = null,Object? content = null,Object? timestamp = freezed,}) {
  return _then(_self.copyWith(
role: null == role ? _self.role : role // ignore: cast_nullable_to_non_nullable
as String,content: null == content ? _self.content : content // ignore: cast_nullable_to_non_nullable
as String,timestamp: freezed == timestamp ? _self.timestamp : timestamp // ignore: cast_nullable_to_non_nullable
as DateTime?,
  ));
}

}


/// Adds pattern-matching-related methods to [ChatMessage].
extension ChatMessagePatterns on ChatMessage {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _ChatMessage value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _ChatMessage() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _ChatMessage value)  $default,){
final _that = this;
switch (_that) {
case _ChatMessage():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _ChatMessage value)?  $default,){
final _that = this;
switch (_that) {
case _ChatMessage() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String role,  String content,  DateTime? timestamp)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _ChatMessage() when $default != null:
return $default(_that.role,_that.content,_that.timestamp);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String role,  String content,  DateTime? timestamp)  $default,) {final _that = this;
switch (_that) {
case _ChatMessage():
return $default(_that.role,_that.content,_that.timestamp);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String role,  String content,  DateTime? timestamp)?  $default,) {final _that = this;
switch (_that) {
case _ChatMessage() when $default != null:
return $default(_that.role,_that.content,_that.timestamp);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _ChatMessage implements ChatMessage {
  const _ChatMessage({required this.role, required this.content, this.timestamp});
  factory _ChatMessage.fromJson(Map<String, dynamic> json) => _$ChatMessageFromJson(json);

@override final  String role;
// 'user' or 'assistant'
@override final  String content;
@override final  DateTime? timestamp;

/// Create a copy of ChatMessage
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$ChatMessageCopyWith<_ChatMessage> get copyWith => __$ChatMessageCopyWithImpl<_ChatMessage>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$ChatMessageToJson(this, );
}

@override
bool operator ==(Object other) {
  return identical(this, other) || (other.runtimeType == runtimeType&&other is _ChatMessage&&(identical(other.role, role) || other.role == role)&&(identical(other.content, content) || other.content == content)&&(identical(other.timestamp, timestamp) || other.timestamp == timestamp));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode => Object.hash(runtimeType,role,content,timestamp);

@override
String toString() {
  return 'ChatMessage(role: $role, content: $content, timestamp: $timestamp)';
}


}

/// @nodoc
abstract mixin class _$ChatMessageCopyWith<$Res> implements $ChatMessageCopyWith<$Res> {
  factory _$ChatMessageCopyWith(_ChatMessage value, $Res Function(_ChatMessage) _then) = __$ChatMessageCopyWithImpl;
@override @useResult
$Res call({
 String role, String content, DateTime? timestamp
});




}
/// @nodoc
class __$ChatMessageCopyWithImpl<$Res>
    implements _$ChatMessageCopyWith<$Res> {
  __$ChatMessageCopyWithImpl(this._self, this._then);

  final _ChatMessage _self;
  final $Res Function(_ChatMessage) _then;

/// Create a copy of ChatMessage
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? role = null,Object? content = null,Object? timestamp = freezed,}) {
  return _then(_ChatMessage(
role: null == role ? _self.role : role // ignore: cast_nullable_to_non_nullable
as String,content: null == content ? _self.content : content // ignore: cast_nullable_to_non_nullable
as String,timestamp: freezed == timestamp ? _self.timestamp : timestamp // ignore: cast_nullable_to_non_nullable
as DateTime?,
  ));
}


}

// dart format on
