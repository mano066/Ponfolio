import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_colors.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/core/theme/app_gradients.dart';
import 'package:aiei_wealth/services/api_service.dart';

const _suggestions = [
  'How is my overall portfolio doing?',
  'Analyze my mutual fund returns',
  'Should I buy more ITC?',
  'Which MF has the best XIRR?',
  "What's the RSI on TATASTEEL?",
  'Compare my stocks vs mutual funds',
];

class AIChatBot extends StatefulWidget {
  const AIChatBot({super.key});
  @override
  State<AIChatBot> createState() => _AIChatBotState();
}

class _AIChatBotState extends State<AIChatBot> with SingleTickerProviderStateMixin {
  bool _isOpen = false;
  final _messages = <_ChatMsg>[];
  final _inputCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  final _inputFocus = FocusNode();
  bool _loading = false;
  bool _showSuggestions = true;
  late AnimationController _fabAnim;

  @override
  void initState() {
    super.initState();
    _fabAnim = AnimationController(vsync: this, duration: const Duration(milliseconds: 300));
  }

  void _toggle() {
    setState(() => _isOpen = !_isOpen);
    if (_isOpen) {
      _fabAnim.forward();
      Future.delayed(const Duration(milliseconds: 300), () => _inputFocus.requestFocus());
    } else {
      _fabAnim.reverse();
    }
  }

  Future<void> _send([String? text]) async {
    final msg = (text ?? _inputCtrl.text).trim();
    if (msg.isEmpty || _loading) return;
    setState(() {
      _messages.add(_ChatMsg(role: 'user', content: msg));
      _inputCtrl.clear();
      _loading = true;
      _showSuggestions = false;
    });
    _scrollToBottom();
    try {
      final history = _messages.reversed.take(7).toList().reversed
          .map((m) => {'role': m.role, 'content': m.content}).toList();
      final data = await ApiService().chat(msg, history.cast<Map<String, String>>());
      setState(() => _messages.add(_ChatMsg(
        role: 'assistant',
        content: data['reply'] ?? 'Sorry, I couldn\'t generate a response.',
      )));
    } catch (_) {
      setState(() => _messages.add(_ChatMsg(
        role: 'assistant',
        content: '⚠️ Connection error. Make sure the backend is running.',
      )));
    }
    setState(() => _loading = false);
    _scrollToBottom();
  }

  void _scrollToBottom() {
    Future.delayed(const Duration(milliseconds: 100), () {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(_scrollCtrl.position.maxScrollExtent,
            duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
      }
    });
  }

  void _clear() => setState(() { _messages.clear(); _showSuggestions = true; });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Stack(children: [
      // Chat panel
      if (_isOpen) Positioned(
        right: 24, bottom: 80, width: 420, height: 560,
        child: Material(
          color: Colors.transparent,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
              child: Container(
                decoration: BoxDecoration(
                  color: c.bg1.withValues(alpha: 0.95),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: c.bd2),
                  boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.4), blurRadius: 30, offset: const Offset(0, 10))],
                ),
                child: Column(children: [
                  // Header
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      gradient: AppGradients.brand,
                      borderRadius: const BorderRadius.only(topLeft: Radius.circular(16), topRight: Radius.circular(16)),
                    ),
                    child: Row(children: [
                      Container(width: 32, height: 32, decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.2), borderRadius: BorderRadius.circular(8)),
                        child: const Icon(LucideIcons.bot, size: 18, color: Colors.white)),
                      const SizedBox(width: 12),
                      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Text('AI Wealth Advisor', style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w700)),
                        Text('Powered by Local LLM', style: TextStyle(color: Colors.white.withValues(alpha: 0.7), fontSize: 10, fontWeight: FontWeight.w500)),
                      ])),
                      if (_messages.isNotEmpty) IconButton(
                        icon: const Icon(LucideIcons.trash2, size: 14, color: Colors.white70),
                        onPressed: _clear, tooltip: 'Clear chat',
                        padding: EdgeInsets.zero, constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
                      ),
                      IconButton(
                        icon: const Icon(LucideIcons.x, size: 16, color: Colors.white),
                        onPressed: _toggle, padding: EdgeInsets.zero,
                        constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
                      ),
                    ]),
                  ),
                  // Messages
                  Expanded(child: _messages.isEmpty && _showSuggestions
                    ? _buildSuggestions(c) : _buildMessages(c)),
                  // Input
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(border: Border(top: BorderSide(color: c.bd))),
                    child: Row(children: [
                      Expanded(child: TextField(
                        controller: _inputCtrl, focusNode: _inputFocus,
                        style: AppTextStyles.body(c.t1),
                        decoration: InputDecoration(
                          hintText: 'Ask about your portfolio...',
                          hintStyle: AppTextStyles.body(c.t4),
                          border: InputBorder.none, isDense: true,
                          contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                        ),
                        onSubmitted: (_) => _send(),
                      )),
                      const SizedBox(width: 8),
                      Material(
                        color: _loading ? c.bg3 : c.blue,
                        borderRadius: BorderRadius.circular(8),
                        child: InkWell(
                          borderRadius: BorderRadius.circular(8),
                          onTap: _loading ? null : () => _send(),
                          child: Container(
                            padding: const EdgeInsets.all(8),
                            child: _loading
                              ? SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: c.t3))
                              : const Icon(LucideIcons.send, size: 16, color: Colors.white),
                          ),
                        ),
                      ),
                    ]),
                  ),
                ]),
              ),
            ),
          ),
        ),
      ),
      // FAB
      Positioned(
        right: 24, bottom: 24,
        child: GestureDetector(
          onTap: _toggle,
          child: Container(
            width: 52, height: 52,
            decoration: BoxDecoration(
              gradient: AppGradients.brand, shape: BoxShape.circle,
              boxShadow: [BoxShadow(color: c.blue.withValues(alpha: 0.4), blurRadius: 20, offset: const Offset(0, 4))],
            ),
            child: Center(child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 200),
              child: _isOpen
                ? const Icon(LucideIcons.x, size: 22, color: Colors.white, key: ValueKey('close'))
                : const Icon(LucideIcons.bot, size: 22, color: Colors.white, key: ValueKey('bot')),
            )),
          ),
        ),
      ),
    ]);
  }

  Widget _buildSuggestions(AppColorScheme c) {
    return Padding(padding: const EdgeInsets.all(16), child: Column(
      crossAxisAlignment: CrossAxisAlignment.start, children: [
        const SizedBox(height: 8),
        Text('💡 Try asking:', style: AppTextStyles.label(c.t3)),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: _suggestions.map((s) => Material(
          color: c.bg3, borderRadius: BorderRadius.circular(8),
          child: InkWell(
            borderRadius: BorderRadius.circular(8),
            onTap: () => _send(s),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(border: Border.all(color: c.bd), borderRadius: BorderRadius.circular(8)),
              child: Text(s, style: AppTextStyles.bodySmall(c.t2)),
            ),
          ),
        )).toList()),
      ],
    ));
  }

  Widget _buildMessages(AppColorScheme c) {
    return ListView.builder(
      controller: _scrollCtrl, padding: const EdgeInsets.all(12),
      itemCount: _messages.length + (_loading ? 1 : 0),
      itemBuilder: (_, i) {
        if (i == _messages.length) {
          // Loading indicator
          return Align(alignment: Alignment.centerLeft, child: Container(
            margin: const EdgeInsets.only(top: 8),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(color: c.bg3, borderRadius: BorderRadius.circular(12)),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2, color: c.blue)),
              const SizedBox(width: 8),
              Text('Thinking...', style: AppTextStyles.bodySmall(c.t3)),
            ]),
          ));
        }
        final msg = _messages[i];
        final isUser = msg.role == 'user';
        return Align(
          alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            constraints: const BoxConstraints(maxWidth: 340),
            decoration: BoxDecoration(
              color: isUser ? c.blue.withValues(alpha: 0.15) : c.bg3,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: isUser ? c.blue.withValues(alpha: 0.2) : c.bd),
            ),
            child: SelectableText(msg.content, style: AppTextStyles.bodySmall(isUser ? c.t1 : c.t2)),
          ),
        );
      },
    );
  }

  @override
  void dispose() { _inputCtrl.dispose(); _scrollCtrl.dispose(); _inputFocus.dispose(); _fabAnim.dispose(); super.dispose(); }
}

class _ChatMsg {
  final String role;
  final String content;
  _ChatMsg({required this.role, required this.content});
}
