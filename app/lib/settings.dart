// =============================================
// settings.dart - Guarda o endereço do servidor no celular
// =============================================

import 'package:shared_preferences/shared_preferences.dart';

class Settings {
  static const _serverKey = 'server_url';

  static Future<String?> loadServer() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_serverKey);
  }

  static Future<void> saveServer(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_serverKey, url);
  }
}
