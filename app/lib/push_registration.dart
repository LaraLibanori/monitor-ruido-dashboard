import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

import 'api.dart';

/// Firebase is optional until the app is configured with native credentials.
class PushRegistration {
  static Future<void> start(ApiClient api) async {
    if (api.authToken == null || api.authToken!.isEmpty) return;
    try {
      await Firebase.initializeApp();
      final messaging = FirebaseMessaging.instance;
      await messaging.requestPermission();
      final token = await messaging.getToken();
      if (token != null) {
        await api.registerDevice(token, _platform);
      }
      messaging.onTokenRefresh.listen((newToken) {
        api.registerDevice(newToken, _platform);
      });
    } catch (_) {
      // A build without google-services.json or APNs setup remains usable.
    }
  }

  static String get _platform {
    if (Platform.isIOS) return 'ios';
    if (Platform.isAndroid) return 'android';
    return 'web';
  }

  static Future<void> remove(ApiClient api) async {
    try {
      final token = await FirebaseMessaging.instance.getToken();
      if (token != null) await api.removeDevice(token);
    } catch (_) {
      // Cleanup is best effort when Firebase is not configured.
    }
  }
}
