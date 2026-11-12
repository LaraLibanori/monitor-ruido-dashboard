// =============================================
// main.dart - Ponto de partida do app
// =============================================
// Corrente do sistema:
//   ESP32 (sensor) -> Wi-Fi -> Docker no computador (FastAPI)
//   -> Wi-Fi -> este aplicativo (só lê e interpreta a API)
// =============================================

import 'package:flutter/material.dart';

import 'api.dart';
import 'noise_ui.dart';
import 'screens/connect_screen.dart';
import 'screens/home_screen.dart';
import 'settings.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final savedServer = await Settings.loadServer();
  final authToken = await Settings.loadAuthToken();
  runApp(MonitorApp(savedServer: savedServer, authToken: authToken));
}

class MonitorApp extends StatelessWidget {
  const MonitorApp({super.key, this.savedServer, this.authToken});

  /// Endereço salvo da última vez (null na primeira abertura).
  final String? savedServer;
  final String? authToken;

  @override
  Widget build(BuildContext context) {
    final server = savedServer;
    return MaterialApp(
      title: 'Monitor de Ruído',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: server == null
          ? const ConnectScreen()
          : HomeScreen(api: ApiClient(server, authToken: authToken)),
    );
  }
}
