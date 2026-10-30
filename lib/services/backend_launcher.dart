import 'dart:io';
import 'package:flutter/foundation.dart';

/// Automatically starts the Python backend server alongside the Flutter app.
/// The backend process runs as a child process and is killed when the app exits.
class BackendLauncher {
  static Process? _backendProcess;
  static bool _started = false;

  /// Attempts to start the backend server.
  /// Returns true if the backend was started or is already running.
  static Future<bool> start() async {
    if (_started) return true;

    // Determine the backend directory relative to the executable
    final exeDir = File(Platform.resolvedExecutable).parent;

    // Check multiple possible backend locations.
    // In a dev build the exe sits at <repo>\build\windows\x64\runner\Release,
    // so parent^4 == <repo>\build and the backend is at <repo>\backend.
    final repoBuildDir = exeDir.parent.parent.parent.parent.path;
    final candidates = [
      exeDir.path + r'\backend',                    // Installed: backend bundled next to exe
      repoBuildDir + r'\..\backend',                // Dev: <repo>\backend (current layout)
      repoBuildDir + r'\..\..\stock_app\backend',   // Legacy dev location (kept for back-compat)
    ];

    String? backendDir;
    for (final dir in candidates) {
      final mainPy = File('$dir${Platform.pathSeparator}main.py');
      if (mainPy.existsSync()) {
        backendDir = dir;
        break;
      }
    }

    if (backendDir == null) {
      debugPrint('[Backend] No backend directory found, skipping auto-start');
      return false;
    }

    // Check if backend is already running on port 8182
    if (await _isPortInUse(8182)) {
      debugPrint('[Backend] Port 8182 already in use — backend is running');
      _started = true;
      return true;
    }

    // Find Python executable — check bundled first, then venv, then system
    String? pythonExe;

    // 1. Bundled embedded Python (installed alongside the app)
    final bundledPython = '${exeDir.path}${Platform.pathSeparator}python${Platform.pathSeparator}python.exe';
    if (File(bundledPython).existsSync()) {
      pythonExe = bundledPython;
      debugPrint('[Backend] Using bundled Python: $bundledPython');
    }

    // 2. Check for venv inside backend dir
    if (pythonExe == null) {
      final venvPython = '$backendDir${Platform.pathSeparator}.venv${Platform.pathSeparator}Scripts${Platform.pathSeparator}python.exe';
      if (File(venvPython).existsSync()) {
        pythonExe = venvPython;
        debugPrint('[Backend] Using venv Python: $venvPython');
      }
    }

    // 3. Fallback to system Python
    if (pythonExe == null) {
      try {
        final result = await Process.run('python', ['--version']);
        if (result.exitCode == 0) {
          pythonExe = 'python';
          debugPrint('[Backend] Using system Python');
        }
      } catch (_) {}
    }

    if (pythonExe == null) {
      debugPrint('[Backend] Python not found — backend cannot auto-start');
      return false;
    }

    // Start the backend with a wrapper script that logs errors
    try {
      debugPrint('[Backend] Starting: $pythonExe main.py in $backendDir');

      // Set PYTHONPATH so embedded Python can find local backend modules
      final env = Map<String, String>.from(Platform.environment);
      env['PYTHONPATH'] = backendDir;
      // Ignore any roaming per-user site-packages so the bundled embeddable
      // Python uses ONLY the deps we ship — prevents version conflicts on
      // machines that happen to have a global %APPDATA%\Python install.
      env['PYTHONNOUSERSITE'] = '1';

      // Create a launcher script that captures errors to a log file
      final logFile = '${exeDir.path}${Platform.pathSeparator}backend.log';
      final mainPyPath = '$backendDir${Platform.pathSeparator}main.py';
      final launcherScript = '''
import sys, os, traceback

sys.path.insert(0, r"$backendDir")
os.chdir(r"$backendDir")

# Redirect stdout/stderr to log file
log_path = r"$logFile"
try:
    log = open(log_path, "w", encoding="utf-8", buffering=1)
    sys.stdout = log
    sys.stderr = log
except Exception:
    pass

try:
    print(f"[Backend] Starting from {os.getcwd()}")
    print(f"[Backend] Python: {sys.executable}")
    print(f"[Backend] sys.path: {sys.path[:5]}")
    # Use runpy to execute main.py with __name__ == "__main__"
    # This ensures the uvicorn.run() block inside 'if __name__ == "__main__"' executes
    import runpy
    runpy.run_path(r"$mainPyPath", run_name="__main__")
except Exception:
    traceback.print_exc()
    sys.exit(1)
''';

      final launcherFile = File('${exeDir.path}${Platform.pathSeparator}_backend_launcher.py');
      await launcherFile.writeAsString(launcherScript);

      _backendProcess = await Process.start(
        pythonExe,
        [launcherFile.path],
        workingDirectory: backendDir,
        environment: env,
        mode: ProcessStartMode.detached,
      );
      debugPrint('[Backend] Started with PID ${_backendProcess!.pid}');
      debugPrint('[Backend] Log file: $logFile');
      _started = true;

      // Wait a moment for the server to boot
      await Future.delayed(const Duration(seconds: 2));

      // Verify it's actually running
      for (int i = 0; i < 10; i++) {
        if (await _isPortInUse(8182)) {
          debugPrint('[Backend] Server is ready on port 8182');
          return true;
        }
        await Future.delayed(const Duration(milliseconds: 500));
      }

      // If port isn't up, check the log for errors
      try {
        final log = await File(logFile).readAsString();
        if (log.contains('Traceback') || log.contains('Error')) {
          debugPrint('[Backend] STARTUP ERROR - check $logFile');
          debugPrint('[Backend] Last 500 chars: ${log.substring(log.length > 500 ? log.length - 500 : 0)}');
        }
      } catch (_) {}

      debugPrint('[Backend] Server started but port 8182 not responding yet');
      return true;
    } catch (e) {
      debugPrint('[Backend] Failed to start: $e');
      return false;
    }
  }

  /// Stop the backend process when the app exits.
  static void stop() {
    if (_backendProcess != null) {
      debugPrint('[Backend] Stopping PID ${_backendProcess!.pid}');
      _backendProcess!.kill();
      _backendProcess = null;
      _started = false;
    }
  }

  /// Check if a port is in use (i.e., backend is already running).
  static Future<bool> _isPortInUse(int port) async {
    try {
      final socket = await Socket.connect('127.0.0.1', port,
          timeout: const Duration(milliseconds: 500));
      socket.destroy();
      return true;
    } catch (_) {
      return false;
    }
  }
}
