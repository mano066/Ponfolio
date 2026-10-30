import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:aiei_wealth/services/api_service.dart';

/// System Check screen — verifies all backend SERVICES are reachable
/// before launching the dashboard. This is a generic check (not user-specific).
class SystemCheckScreen extends ConsumerStatefulWidget {
  final VoidCallback onContinue;
  const SystemCheckScreen({super.key, required this.onContinue});

  @override
  ConsumerState<SystemCheckScreen> createState() => _SystemCheckScreenState();
}

class _ServiceStatus {
  final String name;
  final String subtitle;
  final IconData icon;
  bool? available; // null = checking, true = reachable, false = offline
  String? detail;

  _ServiceStatus({
    required this.name,
    required this.subtitle,
    required this.icon,
  });
}

class _SystemCheckScreenState extends ConsumerState<SystemCheckScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulseCtrl;
  bool _allDone = false;

  final List<_ServiceStatus> _services = [
    _ServiceStatus(name: 'Yahoo Finance', subtitle: 'Stock market data',    icon: LucideIcons.trendingUp),
    _ServiceStatus(name: 'MF API',        subtitle: 'Mutual fund NAV data', icon: LucideIcons.landmark),
    _ServiceStatus(name: 'Google Account', subtitle: 'Cloud sync',          icon: LucideIcons.cloud),
    _ServiceStatus(name: 'Zerodha Kite',  subtitle: 'Live trading',        icon: LucideIcons.zap),
    _ServiceStatus(name: 'Ollama AI',     subtitle: 'AI analysis engine',   icon: LucideIcons.bot),
  ];

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat(reverse: true);
    _runChecks();
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    super.dispose();
  }

  Future<void> _runChecks() async {
    final api = ApiService();

    // ── 1. Yahoo Finance — is the backend API reachable? ──
    // Backend starts async, so retry with delay until it's ready
    bool backendReady = false;
    for (int attempt = 0; attempt < 10; attempt++) {
      await Future.delayed(Duration(milliseconds: attempt == 0 ? 300 : 1500));
      try {
        await api.getPortfolio();
        _update(0, true, 'Service available');
        backendReady = true;
        break;
      } catch (_) {
        if (attempt == 9) {
          _update(0, false, 'Service unavailable');
        }
      }
    }

    // ── 2. MF API — can we reach MF data? ──
    await Future.delayed(const Duration(milliseconds: 300));
    try {
      await api.getMFPortfolio();
      _update(1, true, 'Service available');
    } catch (_) {
      _update(1, false, 'Service unavailable');
    }

    // ── 3. Google Auth — is the auth service running? ──
    await Future.delayed(const Duration(milliseconds: 300));
    try {
      await api.getProfile(); // Just check if endpoint responds
      _update(2, true, 'Service available');
    } catch (_) {
      _update(2, false, 'Auth service offline');
    }

    // ── 4. Zerodha Kite — check MCP availability ──
    //    MCP is configured server-side. User just needs to login.
    await Future.delayed(const Duration(milliseconds: 300));
    try {
      final status = await api.getKiteStatus();
      final configured = status['configured'] == true;
      final mcpAvailable = status['mcp_available'] == true;
      final connected = status['connected'] == true;
      if (connected) {
        _update(3, true, 'Connected as ${status['user_id'] ?? 'user'}');
      } else if (configured || mcpAvailable) {
        _update(3, true, 'Ready — login to connect');
      } else {
        _update(3, false, 'MCP not available');
      }
    } catch (_) {
      _update(3, false, 'MCP server offline');
    }

    // ── 5. Ollama AI — is the server running? ──
    await Future.delayed(const Duration(milliseconds: 300));
    try {
      final result = await api.testOllama();
      final serverOk = result['server_connected'] == true;
      if (serverOk) {
        _update(4, true, 'Server running');
      } else {
        _update(4, false, 'Server not reachable');
      }
    } catch (_) {
      _update(4, false, 'Ollama not running');
    }

    setState(() => _allDone = true);
  }

  void _update(int index, bool ok, String detail) {
    setState(() {
      _services[index].available = ok;
      _services[index].detail = detail;
    });
  }

  @override
  Widget build(BuildContext context) {
    final availableCount = _services.where((s) => s.available == true).length;
    final totalChecked = _services.where((s) => s.available != null).length;

    return Scaffold(
      backgroundColor: const Color(0xFF0A0E1A),
      body: Center(
        child: Container(
          constraints: const BoxConstraints(maxWidth: 480),
          margin: const EdgeInsets.symmetric(horizontal: 24),
          padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 48),
          decoration: BoxDecoration(
            color: const Color(0xFF0F172A).withValues(alpha: 0.9),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: const Color(0xFF6366F1).withValues(alpha: 0.12)),
            boxShadow: [
              BoxShadow(color: Colors.black.withValues(alpha: 0.5), blurRadius: 60, offset: const Offset(0, 20)),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // ─── Animated Hub Icon ───
              AnimatedBuilder(
                animation: _pulseCtrl,
                builder: (_, child) => Container(
                  width: 64, height: 64,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: const Color(0xFF6366F1).withValues(alpha: 0.1 + _pulseCtrl.value * 0.05),
                  ),
                  child: Icon(LucideIcons.activity, size: 28, color: Color.lerp(const Color(0xFF6366F1), const Color(0xFF818CF8), _pulseCtrl.value)),
                ),
              ),
              const SizedBox(height: 20),

              const Text('System Check', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700, color: Color(0xFFF1F5F9), letterSpacing: -0.3)),
              const SizedBox(height: 6),
              Text(
                _allDone
                    ? '$availableCount/${_services.length} services connected'
                    : 'Checking services...',
                style: const TextStyle(fontSize: 13, color: Color(0xFF64748B)),
              ),
              const SizedBox(height: 32),

              // ─── Service List (staggered entrance) ───
              ...List.generate(_services.length, (i) => _ServiceRow(service: _services[i], index: i)),

              const SizedBox(height: 32),

              // ─── Continue Button ───
              SizedBox(
                width: double.infinity,
                child: AnimatedOpacity(
                  opacity: totalChecked == _services.length ? 1.0 : 0.4,
                  duration: const Duration(milliseconds: 300),
                  child: Material(
                    borderRadius: BorderRadius.circular(14),
                    child: Ink(
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(14),
                        gradient: const LinearGradient(colors: [Color(0xFF6366F1), Color(0xFF818CF8)]),
                      ),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(14),
                        onTap: totalChecked == _services.length ? widget.onContinue : null,
                        child: const Padding(
                          padding: EdgeInsets.symmetric(vertical: 16),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text('Continue', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.white)),
                              SizedBox(width: 8),
                              Icon(LucideIcons.arrowRight, size: 18, color: Colors.white),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ServiceRow extends StatefulWidget {
  final _ServiceStatus service;
  final int index;
  const _ServiceRow({required this.service, required this.index});

  @override
  State<_ServiceRow> createState() => _ServiceRowState();
}

class _ServiceRowState extends State<_ServiceRow>
    with TickerProviderStateMixin {
  late AnimationController _slideCtrl;
  late Animation<double> _slideFade;
  late Animation<Offset> _slideOffset;
  AnimationController? _statusCtrl;
  Animation<double>? _statusAnim;
  bool? _lastStatus;

  @override
  void initState() {
    super.initState();
    _slideCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 400));
    _slideFade = CurvedAnimation(parent: _slideCtrl, curve: Curves.easeOut);
    _slideOffset = Tween<Offset>(begin: const Offset(40, 0), end: Offset.zero)
        .animate(CurvedAnimation(parent: _slideCtrl, curve: Curves.easeOutCubic));
    // Stagger each row
    Future.delayed(Duration(milliseconds: 80 * widget.index), () {
      if (mounted) _slideCtrl.forward();
    });
  }

  @override
  void didUpdateWidget(_ServiceRow old) {
    super.didUpdateWidget(old);
    if (widget.service.available != _lastStatus && widget.service.available != null) {
      _lastStatus = widget.service.available;
      _statusCtrl?.dispose();
      _statusCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 500));
      _statusAnim = widget.service.available!
          ? Tween<double>(begin: 0, end: 1).animate(
              CurvedAnimation(parent: _statusCtrl!, curve: Curves.elasticOut))
          : Tween<double>(begin: 0, end: 1).animate(
              CurvedAnimation(parent: _statusCtrl!, curve: Curves.easeOutBack));
      _statusCtrl!.forward();
    }
  }

  @override
  void dispose() {
    _slideCtrl.dispose();
    _statusCtrl?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final service = widget.service;
    final Color borderColor;
    final Color iconBgColor;
    final Color iconColor;

    if (service.available == null) {
      borderColor = const Color(0xFF334155);
      iconBgColor = const Color(0xFF6366F1).withValues(alpha: 0.12);
      iconColor = const Color(0xFF6366F1);
    } else if (service.available!) {
      borderColor = const Color(0xFF10B981).withValues(alpha: 0.2);
      iconBgColor = const Color(0xFF10B981).withValues(alpha: 0.12);
      iconColor = const Color(0xFF10B981);
    } else {
      borderColor = const Color(0xFFF59E0B).withValues(alpha: 0.2);
      iconBgColor = const Color(0xFFF59E0B).withValues(alpha: 0.12);
      iconColor = const Color(0xFFF59E0B);
    }

    return AnimatedBuilder(
      animation: _slideCtrl,
      builder: (_, __) => Transform.translate(
        offset: _slideOffset.value,
        child: Opacity(
          opacity: _slideFade.value,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            decoration: BoxDecoration(
              color: const Color(0xFF1E293B).withValues(alpha: 0.5),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: borderColor),
            ),
            child: Row(
              children: [
                AnimatedContainer(
                  duration: const Duration(milliseconds: 300),
                  width: 40, height: 40,
                  decoration: BoxDecoration(
                    color: iconBgColor,
                    borderRadius: BorderRadius.circular(10),
                    boxShadow: service.available == true ? [
                      BoxShadow(color: iconColor.withValues(alpha: 0.2), blurRadius: 8),
                    ] : null,
                  ),
                  child: Icon(service.icon, size: 18, color: iconColor),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(service.name, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: Color(0xFFF1F5F9))),
                      const SizedBox(height: 2),
                      Text(
                        service.detail ?? service.subtitle,
                        style: TextStyle(
                          fontSize: 11,
                          color: service.available == false
                              ? const Color(0xFFF59E0B)
                              : const Color(0xFF64748B),
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                // Status indicator with animation
                if (service.available == null)
                  const SizedBox(
                    width: 22, height: 22,
                    child: CircularProgressIndicator(strokeWidth: 2, valueColor: AlwaysStoppedAnimation(Color(0xFF6366F1))),
                  )
                else _buildStatusIcon(service.available!),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildStatusIcon(bool ok) {
    final scale = _statusAnim?.value ?? 1.0;
    if (ok) {
      return AnimatedBuilder(
        animation: _statusCtrl ?? const AlwaysStoppedAnimation(1.0),
        builder: (_, __) => Transform.scale(
          scale: (_statusAnim?.value ?? 1.0).clamp(0.0, 1.5),
          child: Container(
            width: 24, height: 24,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFF10B981).withValues(alpha: 0.15),
              boxShadow: [
                BoxShadow(color: const Color(0xFF10B981).withValues(alpha: scale * 0.3), blurRadius: scale * 8),
              ],
            ),
            child: const Icon(LucideIcons.checkCircle2, size: 16, color: Color(0xFF10B981)),
          ),
        ),
      );
    } else {
      return AnimatedBuilder(
        animation: _statusCtrl ?? const AlwaysStoppedAnimation(1.0),
        builder: (_, __) {
          final shake = _statusCtrl != null && _statusCtrl!.isAnimating
              ? (scale * 4 * (scale > 0.5 ? 1 - scale : scale)).clamp(-3.0, 3.0)
              : 0.0;
          return Transform.translate(
            offset: Offset(shake, 0),
            child: Container(
              width: 24, height: 24,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: const Color(0xFFF59E0B).withValues(alpha: 0.15),
              ),
              child: const Icon(LucideIcons.alertCircle, size: 16, color: Color(0xFFF59E0B)),
            ),
          );
        },
      );
    }
  }
}
