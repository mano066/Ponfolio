import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/models/conviction_models.dart';
import 'providers.dart';

/// The conviction board. Fundamentals change quarterly and theses change when
/// the user edits them, so this is fetched once and invalidated after every
/// edit rather than polled.
final convictionBoardProvider =
    FutureProvider.autoDispose<ConvictionBoard>((ref) async {
  // A guest must not be shown somebody's holdings or reasoning.
  if (ref.watch(isGuestProvider)) return ConvictionBoard.empty;
  final api = ref.read(apiServiceProvider);
  return ConvictionBoard.fromJson(await api.getConvictionBoard());
});
