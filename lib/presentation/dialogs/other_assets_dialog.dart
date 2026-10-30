import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/core/theme/app_gradients.dart';
import 'package:aiei_wealth/providers/allocation_provider.dart';

/// Glassmorphic modal dialog for manually adding Gold, Cash, International,
/// REITs, and Debt asset values.
class OtherAssetsDialog extends ConsumerStatefulWidget {
  const OtherAssetsDialog({super.key});

  static Future<void> show(BuildContext context) {
    return showDialog(
      context: context,
      barrierColor: Colors.black54,
      builder: (_) => const OtherAssetsDialog(),
    );
  }

  @override
  ConsumerState<OtherAssetsDialog> createState() => _OtherAssetsDialogState();
}

class _OtherAssetsDialogState extends ConsumerState<OtherAssetsDialog> {
  static const _assetCategories = [
    {'key': 'Gold', 'icon': LucideIcons.gem, 'color': Color(0xFFFFD740)},
    {'key': 'Cash', 'icon': LucideIcons.banknote, 'color': Color(0xFF00E676)},
    {'key': 'Debt', 'icon': LucideIcons.shieldCheck, 'color': Color(0xFF448AFF)},
    {'key': 'International', 'icon': LucideIcons.globe, 'color': Color(0xFF7C4DFF)},
    {'key': 'REITs', 'icon': LucideIcons.building, 'color': Color(0xFFFF9100)},
  ];

  final _controllers = <String, TextEditingController>{};

  @override
  void initState() {
    super.initState();
    final current = ref.read(otherAssetsProvider);
    for (final cat in _assetCategories) {
      final key = cat['key'] as String;
      final value = current[key] ?? 0.0;
      _controllers[key] = TextEditingController(
        text: value > 0 ? value.toStringAsFixed(0) : '',
      );
    }
  }

  @override
  void dispose() {
    for (final c in _controllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  void _save() {
    final updated = <String, double>{};
    for (final cat in _assetCategories) {
      final key = cat['key'] as String;
      final text = _controllers[key]!.text.trim();
      if (text.isNotEmpty) {
        final value = double.tryParse(text) ?? 0;
        if (value > 0) updated[key] = value;
      }
    }
    ref.read(otherAssetsProvider.notifier).setAll(updated);
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;

    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        width: 480,
        padding: const EdgeInsets.all(0),
        decoration: BoxDecoration(
          color: c.bg2,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: c.bd),
          boxShadow: [
            BoxShadow(color: Colors.black.withValues(alpha: 0.4), blurRadius: 40, offset: const Offset(0, 16)),
          ],
        ),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          // ── Header with gradient bar ──
          Container(
            height: 3,
            decoration: BoxDecoration(
              gradient: AppGradients.statGold,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(16),
                topRight: Radius.circular(16),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 20, 24, 0),
            child: Row(children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  gradient: AppGradients.statGold,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(LucideIcons.wallet, size: 18, color: Colors.white),
              ),
              const SizedBox(width: 12),
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Other Assets', style: AppTextStyles.heading3(c.t1)),
                Text('Gold, Cash, Debt, International, REITs',
                    style: AppTextStyles.captionXs(c.t3)),
              ]),
              const Spacer(),
              IconButton(
                icon: Icon(LucideIcons.x, size: 18, color: c.t3),
                onPressed: () => Navigator.of(context).pop(),
              ),
            ]),
          ),
          const SizedBox(height: 20),

          // ── Asset input fields ──
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Column(
              children: _assetCategories.map((cat) {
                final key = cat['key'] as String;
                final icon = cat['icon'] as IconData;
                final color = cat['color'] as Color;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Row(children: [
                    Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Icon(icon, size: 16, color: color),
                    ),
                    const SizedBox(width: 12),
                    SizedBox(
                      width: 100,
                      child: Text(key, style: AppTextStyles.body(c.t1)),
                    ),
                    Expanded(
                      child: Container(
                        height: 38,
                        decoration: BoxDecoration(
                          color: c.bg3,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: c.bd),
                        ),
                        child: TextField(
                          controller: _controllers[key],
                          keyboardType: TextInputType.number,
                          inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                          style: AppTextStyles.mono(c.t1).copyWith(fontSize: 13),
                          decoration: InputDecoration(
                            prefixText: '₹ ',
                            prefixStyle: AppTextStyles.mono(c.t3).copyWith(fontSize: 13),
                            hintText: '0',
                            hintStyle: AppTextStyles.mono(c.t4).copyWith(fontSize: 13),
                            border: InputBorder.none,
                            contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                          ),
                        ),
                      ),
                    ),
                  ]),
                );
              }).toList(),
            ),
          ),
          const SizedBox(height: 8),

          // ── Actions ──
          Container(
            padding: const EdgeInsets.fromLTRB(24, 12, 24, 20),
            child: Row(children: [
              Text(
                'Values are stored locally',
                style: AppTextStyles.captionXs(c.t4),
              ),
              const Spacer(),
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: Text('Cancel', style: AppTextStyles.body(c.t3)),
              ),
              const SizedBox(width: 8),
              Material(
                borderRadius: BorderRadius.circular(8),
                child: Ink(
                  decoration: BoxDecoration(
                    gradient: AppGradients.blueIndigo,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(8),
                    onTap: _save,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                      child: Row(mainAxisSize: MainAxisSize.min, children: [
                        const Icon(LucideIcons.save, size: 14, color: Colors.white),
                        const SizedBox(width: 6),
                        Text('Save', style: AppTextStyles.body(Colors.white).copyWith(fontWeight: FontWeight.w600)),
                      ]),
                    ),
                  ),
                ),
              ),
            ]),
          ),
        ]),
      ),
    );
  }
}
