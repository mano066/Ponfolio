import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:aiei_wealth/services/api_service.dart';
import 'package:aiei_wealth/providers/providers.dart';

/// Welcome / Login screen — pixel-perfect match to WelcomeView.tsx
class WelcomeScreen extends ConsumerStatefulWidget {
  final VoidCallback onLogin;
  final VoidCallback onSkip;
  const WelcomeScreen({super.key, required this.onLogin, required this.onSkip});

  @override
  ConsumerState<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends ConsumerState<WelcomeScreen>
    with TickerProviderStateMixin {
  bool _loading = false;
  String _error = '';
  Timer? _pollTimer;
  Timer? _timeoutTimer;
  bool _backendReady = false;
  Timer? _backendCheckTimer;

  // Animated orbs
  late final AnimationController _orbCtrl1;
  late final AnimationController _orbCtrl2;
  late final AnimationController _orbCtrl3;

  @override
  void initState() {
    super.initState();
    _orbCtrl1 = AnimationController(vsync: this, duration: const Duration(seconds: 20))..repeat(reverse: true);
    _orbCtrl2 = AnimationController(vsync: this, duration: const Duration(seconds: 25))..repeat(reverse: true);
    _orbCtrl3 = AnimationController(vsync: this, duration: const Duration(seconds: 15))..repeat(reverse: true);

    // Start checking backend readiness immediately
    _checkBackendReady();
    _backendCheckTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      if (!_backendReady) _checkBackendReady();
    });
  }

  bool _checkInFlight = false;

  Future<void> _checkBackendReady() async {
    // Ping the light status endpoint, one request at a time. Polling the full
    // portfolio every 2s piled up slow requests and starved the server.
    if (_checkInFlight) return;
    _checkInFlight = true;
    try {
      final api = ApiService();
      await api.ping();
      if (mounted && !_backendReady) {
        setState(() {
          _backendReady = true;
          _error = '';
        });
        _backendCheckTimer?.cancel();
      }
    } catch (_) {
      // Backend not ready yet — keep polling
    } finally {
      _checkInFlight = false;
    }
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _timeoutTimer?.cancel();
    _backendCheckTimer?.cancel();
    _orbCtrl1.dispose();
    _orbCtrl2.dispose();
    _orbCtrl3.dispose();
    super.dispose();
  }

  Future<void> _handleGoogleLogin() async {
    if (!_backendReady) return;
    setState(() { _loading = true; _error = ''; });
    try {
      final api = ApiService();
      final data = await api.getGoogleAuthUrl();
      final url = data['url'] as String?;
      if (url == null || url.isEmpty) throw Exception('Failed to get login URL');

      // Open Google login in default browser
      await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);

      // Poll for the callback result every 1.5s
      _pollTimer = Timer.periodic(const Duration(milliseconds: 1500), (timer) async {
        try {
          final profile = await api.getProfile();
          if (profile['logged_in'] == true || profile['authenticated'] == true) {
            timer.cancel();
            _timeoutTimer?.cancel();
            if (mounted) {
              ref.invalidate(profileProvider);
              ref.read(isGuestProvider.notifier).set(false);
              widget.onLogin();
            }
          }
        } catch (_) {}
      });

      // Timeout after 2 minutes
      _timeoutTimer = Timer(const Duration(minutes: 2), () {
        _pollTimer?.cancel();
        if (mounted) setState(() => _loading = false);
      });
    } catch (e) {
      // Show user-friendly error instead of raw exception
      String message;
      if (e.toString().contains('connection') || e.toString().contains('refused') || e.toString().contains('SocketException')) {
        message = 'Backend server is starting up. Please wait a moment and try again.';
      } else {
        message = e.toString().replaceAll(RegExp(r'(DioException|Exception|Error).*?:'), '').trim();
        if (message.length > 100) message = message.substring(0, 100);
      }
      setState(() { _error = message; _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment(-1, -1),
            end: Alignment(1, 1),
            colors: [Color(0xFF0A0E1A), Color(0xFF0F1729), Color(0xFF111B2E), Color(0xFF0A0E1A)],
            stops: [0, 0.3, 0.6, 1.0],
          ),
        ),
        child: Stack(
          children: [
            // ─── Animated Background Orbs ───
            _AnimatedOrb(
              controller: _orbCtrl1,
              color: const Color(0xFF6366F1).withValues(alpha: 0.08),
              size: 500,
              topFactor: -0.2,
              leftFactor: -0.1,
            ),
            _AnimatedOrb(
              controller: _orbCtrl2,
              color: const Color(0xFF10B981).withValues(alpha: 0.06),
              size: 600,
              topFactor: 0.7,
              leftFactor: 0.8,
            ),
            _AnimatedOrb(
              controller: _orbCtrl3,
              color: const Color(0xFFFBBF24).withValues(alpha: 0.04),
              size: 300,
              topFactor: 0.3,
              leftFactor: 0.7,
            ),

            // ─── Main Card ───
            Center(
              child: Container(
                constraints: const BoxConstraints(maxWidth: 460),
                margin: const EdgeInsets.symmetric(horizontal: 24),
                padding: const EdgeInsets.symmetric(horizontal: 48, vertical: 56),
                decoration: BoxDecoration(
                  color: const Color(0xFF0F172A).withValues(alpha: 0.85),
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(color: const Color(0xFF6366F1).withValues(alpha: 0.15)),
                  boxShadow: [
                    BoxShadow(color: Colors.black.withValues(alpha: 0.5), blurRadius: 80, offset: const Offset(0, 25)),
                    BoxShadow(color: const Color(0xFF6366F1).withValues(alpha: 0.1), blurRadius: 0, spreadRadius: 1),
                  ],
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // ─── Logo ───
                    Container(
                      width: 80, height: 80,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(20),
                        gradient: const LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)],
                        ),
                        boxShadow: [BoxShadow(color: const Color(0xFF6366F1).withValues(alpha: 0.3), blurRadius: 32, offset: const Offset(0, 8))],
                      ),
                      child: const Center(
                        child: Text('W', style: TextStyle(color: Colors.white, fontSize: 36, fontWeight: FontWeight.w800, height: 1)),
                      ),
                    ),
                    const SizedBox(height: 24),

                    // ─── Title ───
                    const Text(
                      'Ponfolio',
                      style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700, color: Color(0xFFF1F5F9), letterSpacing: -0.5, height: 1),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Institutional AI-Powered Stock & Mutual Fund Terminal',
                      style: TextStyle(fontSize: 14, color: Color(0xFF64748B), height: 1.5),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 40),

                    // ─── Feature Badges ───
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        _FeatureBadge(icon: '📊', label: 'Portfolio'),
                        const SizedBox(width: 12),
                        _FeatureBadge(icon: '🤖', label: 'AI Advisor'),
                        const SizedBox(width: 12),
                        _FeatureBadge(icon: '📈', label: 'Live Data'),
                      ],
                    ),
                    const SizedBox(height: 36),

                    // ─── Google Sign-In Button ───
                    AnimatedOpacity(
                      opacity: _backendReady ? 1.0 : 0.5,
                      duration: const Duration(milliseconds: 400),
                      child: SizedBox(
                        width: double.infinity,
                        child: Material(
                          color: _loading ? const Color(0xFF1E293B) : (_backendReady ? Colors.white : const Color(0xFF1E293B)),
                          borderRadius: BorderRadius.circular(12),
                          elevation: (_loading || !_backendReady) ? 0 : 4,
                          shadowColor: Colors.black.withValues(alpha: 0.15),
                          child: InkWell(
                            onTap: (_loading || !_backendReady) ? null : _handleGoogleLogin,
                            borderRadius: BorderRadius.circular(12),
                            child: Padding(
                              padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 24),
                              child: Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  if (_loading)
                                    SizedBox(
                                      width: 20, height: 20,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        valueColor: AlwaysStoppedAnimation(const Color(0xFF64748B)),
                                      ),
                                    )
                                  else
                                    _GoogleIcon(),
                                  const SizedBox(width: 12),
                                  Text(
                                    _loading ? 'Signing in...' : 'Sign in with Google',
                                    style: TextStyle(
                                      fontSize: 15,
                                      fontWeight: FontWeight.w600,
                                      color: _loading ? const Color(0xFF64748B) : (_backendReady ? const Color(0xFF1F2937) : const Color(0xFF64748B)),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),

                    // ─── Backend Status / Error ───
                    const SizedBox(height: 12),
                    if (_error.isNotEmpty)
                      Text(_error, style: const TextStyle(color: Color(0xFFEF4444), fontSize: 13))
                    else if (!_backendReady)
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          SizedBox(
                            width: 12, height: 12,
                            child: CircularProgressIndicator(
                              strokeWidth: 1.5,
                              valueColor: AlwaysStoppedAnimation(const Color(0xFFFBBF24).withValues(alpha: 0.8)),
                            ),
                          ),
                          const SizedBox(width: 8),
                          const Text(
                            'Connecting to server...',
                            style: TextStyle(color: Color(0xFFFBBF24), fontSize: 12),
                          ),
                        ],
                      )
                    else
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.check_circle, size: 14, color: const Color(0xFF10B981).withValues(alpha: 0.8)),
                          const SizedBox(width: 6),
                          Text(
                            'Server connected',
                            style: TextStyle(color: const Color(0xFF10B981).withValues(alpha: 0.8), fontSize: 12),
                          ),
                        ],
                      ),

                    const SizedBox(height: 16),

                    // ─── Skip / Guest Button ───
                    AnimatedOpacity(
                      opacity: _backendReady ? 1.0 : 0.4,
                      duration: const Duration(milliseconds: 400),
                      child: SizedBox(
                        width: double.infinity,
                        child: OutlinedButton.icon(
                          onPressed: _backendReady ? () {
                            ref.read(isGuestProvider.notifier).set(true);
                            widget.onSkip();
                          } : null,
                          icon: const Icon(Icons.person_outline, size: 16),
                          label: const Text('Continue as Guest', style: TextStyle(fontSize: 13)),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: const Color(0xFF64748B),
                            disabledForegroundColor: const Color(0xFF475569),
                            side: BorderSide(color: const Color(0xFF64748B).withValues(alpha: _backendReady ? 0.2 : 0.1)),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                            padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 24),
                          ),
                        ),
                      ),
                    ),

                    const SizedBox(height: 24),

                    // ─── Footer ───
                    RichText(
                      textAlign: TextAlign.center,
                      text: TextSpan(
                        style: const TextStyle(fontSize: 11, color: Color(0xFF475569), height: 1.6),
                        children: [
                          const TextSpan(text: '🔐 ', style: TextStyle(fontSize: 12)),
                          const TextSpan(text: 'Google', style: TextStyle(fontWeight: FontWeight.w600, color: Color(0xFF94A3B8))),
                          const TextSpan(text: '  syncs data via Drive  ·  '),
                          const TextSpan(text: '👤 ', style: TextStyle(fontSize: 12)),
                          const TextSpan(text: 'Guest', style: TextStyle(fontWeight: FontWeight.w600, color: Color(0xFF94A3B8))),
                          const TextSpan(text: '  stores data locally'),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Animated floating orb ───
class _AnimatedOrb extends AnimatedWidget {
  final double size;
  final Color color;
  final double topFactor;
  final double leftFactor;

  const _AnimatedOrb({
    required AnimationController controller,
    required this.size,
    required this.color,
    required this.topFactor,
    required this.leftFactor,
  }) : super(listenable: controller);

  @override
  Widget build(BuildContext context) {
    final animation = listenable as AnimationController;
    final screenSize = MediaQuery.of(context).size;
    final yOffset = sin(animation.value * pi * 2) * 30;

    return Positioned(
      top: screenSize.height * topFactor + yOffset,
      left: screenSize.width * leftFactor,
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [color, Colors.transparent],
            stops: const [0, 0.7],
          ),
        ),
      ),
    );
  }
}

// ─── Feature badge pill ───
class _FeatureBadge extends StatelessWidget {
  final String icon;
  final String label;
  const _FeatureBadge({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF6366F1).withValues(alpha: 0.08),
        border: Border.all(color: const Color(0xFF6366F1).withValues(alpha: 0.12)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          Text(icon, style: const TextStyle(fontSize: 20)),
          const SizedBox(height: 4),
          Text(label, style: const TextStyle(fontSize: 12, color: Color(0xFF94A3B8))),
        ],
      ),
    );
  }
}

// ─── Google 'G' icon (custom painter to avoid SVG dependency) ───
class _GoogleIcon extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 20, height: 20,
      child: CustomPaint(painter: _GoogleLogoPainter()),
    );
  }
}

class _GoogleLogoPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final double w = size.width;
    final double h = size.height;
    final center = Offset(w / 2, h / 2);
    final radius = w / 2;

    // Blue arc (top-right)
    final bluePaint = Paint()..color = const Color(0xFF4285F4)..style = PaintingStyle.stroke..strokeWidth = 3.5..strokeCap = StrokeCap.butt;
    canvas.drawArc(Rect.fromCircle(center: center, radius: radius * 0.8), -0.5, 1.8, false, bluePaint);

    // Red arc (top-left)
    final redPaint = Paint()..color = const Color(0xFFEA4335)..style = PaintingStyle.stroke..strokeWidth = 3.5..strokeCap = StrokeCap.butt;
    canvas.drawArc(Rect.fromCircle(center: center, radius: radius * 0.8), -2.3, 1.8, false, redPaint);

    // Yellow arc (bottom-left)
    final yellowPaint = Paint()..color = const Color(0xFFFBBC05)..style = PaintingStyle.stroke..strokeWidth = 3.5..strokeCap = StrokeCap.butt;
    canvas.drawArc(Rect.fromCircle(center: center, radius: radius * 0.8), 1.3, 1.8, false, yellowPaint);

    // Green arc (bottom-right)
    final greenPaint = Paint()..color = const Color(0xFF34A853)..style = PaintingStyle.stroke..strokeWidth = 3.5..strokeCap = StrokeCap.butt;
    canvas.drawArc(Rect.fromCircle(center: center, radius: radius * 0.8), 3.1, 0.6, false, greenPaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
