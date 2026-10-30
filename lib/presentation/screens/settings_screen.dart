import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/core/extensions.dart';
import 'package:aiei_wealth/core/theme/app_colors.dart';
import 'package:aiei_wealth/core/theme/app_text_styles.dart';
import 'package:aiei_wealth/presentation/widgets/common.dart';
import 'package:aiei_wealth/services/api_service.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});
  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  final _ollamaUrlCtrl = TextEditingController(text: 'http://localhost:11434');
  String _selectedModel = 'llama3.2';
  List<String> _models = [];
  bool _testing = false;
  bool? _ollamaConnected;
  Map<String, dynamic>? _testResult;
  bool _saving = false;
  bool _saved = false;

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    try {
      final data = await ApiService().getSettings();
      setState(() {
        _ollamaUrlCtrl.text = data['ollama_url'] ?? 'http://localhost:11434';
        _selectedModel = data['ollama_model'] ?? 'llama3.2';
      });
      _loadModels();
    } catch (_) {}
  }

  Future<void> _loadModels() async {
    try {
      final data = await ApiService().getOllamaModels();
      setState(() {
        _models = List<String>.from(data['models'] ?? []);
        _ollamaConnected = data['connected'] as bool?;
      });
    } catch (_) {
      setState(() => _ollamaConnected = false);
    }
  }

  Future<void> _testConnection() async {
    setState(() { _testing = true; _testResult = null; });
    try {
      final data = await ApiService().testOllama();
      setState(() => _testResult = data);
    } catch (e) {
      setState(() => _testResult = {'status': 'error', 'message': '$e'});
    }
    setState(() => _testing = false);
  }

  Future<void> _save() async {
    setState(() { _saving = true; _saved = false; });
    try {
      await ApiService().updateSettings({'ollama_url': _ollamaUrlCtrl.text, 'ollama_model': _selectedModel});
      setState(() => _saved = true);
      _loadModels();
      Future.delayed(const Duration(seconds: 3), () { if (mounted) setState(() => _saved = false); });
    } catch (_) {}
    setState(() => _saving = false);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return ListView(padding: const EdgeInsets.all(0), children: [
      // Header
      Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(color: c.bg2, borderRadius: BorderRadius.circular(12), border: Border.all(color: c.bd)),
        child: Row(children: [
          Container(width: 48, height: 48,
            decoration: BoxDecoration(
              gradient: const LinearGradient(colors: [Color(0x338B5CF6), Color(0x334F46E5)]),
              borderRadius: BorderRadius.circular(14)),
            child: const Icon(LucideIcons.settings, size: 24, color: Color(0xFFA78BFA))),
          const SizedBox(width: 16),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('App Settings', style: AppTextStyles.heading3(c.t1)),
            Text('Configure AI model, Ollama connection, and app preferences', style: AppTextStyles.bodySmall(c.t3)),
          ])),
          if (_saved) Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(color: c.upBg, borderRadius: BorderRadius.circular(8)),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(LucideIcons.check, size: 14, color: c.up),
              const SizedBox(width: 4),
              Text('Saved!', style: AppTextStyles.badge(c.up)),
            ]),
          ),
        ]),
      ),
      const SizedBox(height: 20),

      // Ollama Server card
      Container(
        decoration: BoxDecoration(color: c.bg2, borderRadius: BorderRadius.circular(12), border: Border.all(color: c.bd)),
        child: Column(children: [
          // Section header with connection status
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.bd))),
            child: Row(children: [
              Container(width: 32, height: 32,
                decoration: BoxDecoration(color: const Color(0x1AFF9100), borderRadius: BorderRadius.circular(7)),
                child: const Icon(LucideIcons.server, size: 16, color: Color(0xFFFF9100))),
              const SizedBox(width: 12),
              Text('Ollama AI Server', style: AppTextStyles.sectionTitle(c.t1)),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: _ollamaConnected == true ? c.upBg : _ollamaConnected == false ? c.dnBg : c.goldBg,
                  borderRadius: BorderRadius.circular(12)),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Container(width: 6, height: 6,
                    decoration: BoxDecoration(shape: BoxShape.circle,
                      color: _ollamaConnected == true ? c.up : _ollamaConnected == false ? c.dn : c.gold)),
                  const SizedBox(width: 6),
                  Text(_ollamaConnected == true ? 'Connected' : _ollamaConnected == false ? 'Disconnected' : 'Checking...',
                    style: AppTextStyles.captionXs(_ollamaConnected == true ? c.up : _ollamaConnected == false ? c.dn : c.gold).copyWith(fontWeight: FontWeight.w700)),
                ]),
              ),
            ]),
          ),
          Padding(padding: const EdgeInsets.all(20), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            // URL field
            Text('OLLAMA SERVER URL', style: AppTextStyles.label(c.t3)),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(child: TextField(controller: _ollamaUrlCtrl, style: AppTextStyles.mono(c.t1),
                decoration: const InputDecoration(hintText: 'http://localhost:11434'))),
              const SizedBox(width: 8),
              HeaderButton(icon: _saving ? null : const Icon(LucideIcons.check, size: 14, color: Colors.white),
                text: _saving ? 'Saving...' : 'Save', loading: _saving,
                gradient: const LinearGradient(colors: [Color(0xFF7C3AED), Color(0xFF4F46E5)]),
                onTap: _save),
            ]),
            Padding(padding: const EdgeInsets.only(top: 6),
              child: Text('Default: http://localhost:11434 — Change if Ollama runs on another machine', style: AppTextStyles.captionXs(c.t4))),
            const SizedBox(height: 20),

            // Model selection
            Text('AI MODEL', style: AppTextStyles.label(c.t3)),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                decoration: BoxDecoration(color: c.bg0, border: Border.all(color: c.bd), borderRadius: BorderRadius.circular(8)),
                child: DropdownButton<String>(
                  value: _models.contains(_selectedModel) ? _selectedModel : null,
                  isExpanded: true, underline: const SizedBox(), dropdownColor: c.bg2,
                  style: AppTextStyles.mono(c.t1),
                  hint: Text(_selectedModel.isEmpty ? 'Select model' : '$_selectedModel (saved)', style: AppTextStyles.mono(c.t4)),
                  items: _models.map((m) => DropdownMenuItem(value: m, child: Text(m))).toList(),
                  onChanged: (v) => setState(() => _selectedModel = v ?? _selectedModel),
                ),
              )),
              const SizedBox(width: 8),
              HeaderButton(icon: Icon(LucideIcons.refreshCw, size: 14, color: c.t3), text: null, onTap: _loadModels),
            ]),
            if (_models.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 6),
              child: Text('${_models.length} model(s) available on Ollama', style: AppTextStyles.captionXs(c.t4))),
            const SizedBox(height: 20),

            // Action buttons
            Container(
              padding: const EdgeInsets.only(top: 16),
              decoration: BoxDecoration(border: Border(top: BorderSide(color: c.bd.withValues(alpha: 0.3)))),
              child: Row(children: [
                HeaderButton(
                  icon: Icon(LucideIcons.zap, size: 14, color: _testing ? const Color(0xFFFF9100) : Colors.white),
                  text: _testing ? 'Testing...' : '⚡ Test Connection',
                  gradient: _testing ? null : const LinearGradient(colors: [Color(0xFFEA580C), Color(0xFFD97706)]),
                  loading: _testing, onTap: _testConnection),
                const SizedBox(width: 12),
                HeaderButton(
                  icon: Icon(LucideIcons.check, size: 14, color: _saving ? c.t3 : Colors.white),
                  text: _saving ? 'Saving...' : 'Save Settings',
                  gradient: _saving ? null : const LinearGradient(colors: [Color(0xFF7C3AED), Color(0xFF4F46E5)]),
                  loading: _saving, onTap: _save),
              ]),
            ),

            // Test result
            if (_testResult != null) ...[
              const SizedBox(height: 16),
              _buildTestResult(c),
            ],
          ])),
        ]),
      ),
      const SizedBox(height: 20),

      // System Info card
      Container(
        decoration: BoxDecoration(color: c.bg2, borderRadius: BorderRadius.circular(12), border: Border.all(color: c.bd)),
        child: Column(children: [
          SectionHeader(icon: LucideIcons.cpu, iconBg: c.blueBg, iconColor: c.blue, title: 'System Info'),
          Padding(padding: const EdgeInsets.all(20), child: Row(children: [
            Expanded(child: _infoTile(c, 'BACKEND', 'FastAPI @ localhost:8182')),
            const SizedBox(width: 12),
            Expanded(child: _infoTile(c, 'DESKTOP', 'Flutter Desktop')),
            const SizedBox(width: 12),
            Expanded(child: _infoTile(c, 'AI ENGINE', _selectedModel.isNotEmpty ? _selectedModel : '—')),
            const SizedBox(width: 12),
            Expanded(child: _infoTile(c, 'DATA SOURCE', 'Yahoo Finance + mfapi.in')),
          ])),
        ]),
      ),
      const SizedBox(height: 40),
    ]);
  }

  Widget _buildTestResult(AppColorScheme c) {
    final status = (_testResult!['status'] ?? '').toString();
    final isOk = status == 'ok';
    final isModelMissing = status == 'model_missing';
    final color = isOk ? c.up : isModelMissing ? c.gold : c.dn;
    final bg = isOk ? c.upBg : isModelMissing ? c.goldBg : c.dnBg;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(12), border: Border.all(color: color.withValues(alpha: 0.2))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(isOk ? LucideIcons.check : isModelMissing ? LucideIcons.alertTriangle : LucideIcons.x, size: 16, color: color),
          const SizedBox(width: 8),
          Text(isOk ? 'All Good!' : isModelMissing ? 'Model Not Found' : 'Connection Failed',
            style: AppTextStyles.bodyBold(color)),
        ]),
        const SizedBox(height: 8),
        _testLine(c, 'Server', _testResult!['server_connected'] == true ? '✅ Connected' : '❌ Not reachable'),
        if (_testResult!['models_available'] != null)
          _testLine(c, 'Models', (List<dynamic>.from(_testResult!['models_available'] ?? [])).join(', ')),
        if (_testResult!['current_model'] != null)
          _testLine(c, 'Selected', '${_testResult!['current_model']} ${_testResult!['model_found'] == true ? '✅' : '❌ not installed'}'),
        if (_testResult!['test_response'] != null)
          _testLine(c, 'Generation', _testResult!['test_response'] == true ? '✅ Working' : '⏳ Skipped'),
        if (_testResult!['message'] != null)
          Padding(padding: const EdgeInsets.only(top: 4), child: Text('Error: ${_testResult!['message']}', style: AppTextStyles.bodySmall(c.dn))),
      ]),
    );
  }

  Widget _testLine(AppColorScheme c, String label, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 2),
    child: Row(children: [
      Text('$label: ', style: AppTextStyles.bodySmall(c.t3)),
      Expanded(child: Text(value, style: AppTextStyles.bodySmall(c.t2))),
    ]),
  );

  Widget _infoTile(AppColorScheme c, String label, String value) => Container(
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(color: c.bg0, borderRadius: BorderRadius.circular(12), border: Border.all(color: c.bd.withValues(alpha: 0.3))),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: AppTextStyles.label(c.t4).copyWith(fontSize: 10)),
      const SizedBox(height: 4),
      Text(value, style: AppTextStyles.mono(c.t1)),
    ]),
  );

  @override
  void dispose() { _ollamaUrlCtrl.dispose(); super.dispose(); }
}
