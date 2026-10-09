// =============================================
// api.dart - Conversa com o servidor (FastAPI no Docker)
// =============================================
// O app só LÊ dados. Rotas usadas:
//   GET /api/app/overview
//   GET /api/app/houses/{sensor_id}/history
// =============================================

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

/// Erro com mensagem já pronta para mostrar ao usuário.
class ApiException implements Exception {
  ApiException(this.message);
  final String message;

  @override
  String toString() => message;
}

int _toInt(dynamic value) => value == null ? 0 : (value as num).toInt();
double? _toDouble(dynamic value) => value == null ? null : (value as num).toDouble();
Map<String, dynamic> _map(dynamic value) =>
    value is Map<String, dynamic> ? value : const <String, dynamic>{};

// ---------------------------------------------
// Modelos
// ---------------------------------------------

class NextChange {
  NextChange({required this.at, required this.dayOffset, required this.silenceStarts});

  final String at; // "22:00"
  final int dayOffset; // 0 = hoje, 1 = amanhã
  final bool silenceStarts; // true = o silêncio vai começar

  factory NextChange.fromJson(Map<String, dynamic> json) => NextChange(
        at: (json['at'] as String?) ?? '',
        dayOffset: _toInt(json['day_offset']),
        silenceStarts: json['silence_starts'] == true,
      );
}

class SilenceStatus {
  SilenceStatus({
    required this.active,
    required this.next,
    required this.weekdayRule,
    required this.weekendRule,
  });

  final bool active;
  final NextChange? next;
  final String weekdayRule; // "22:00–09:00"
  final String weekendRule; // "15:00–09:00"

  factory SilenceStatus.fromJson(Map<String, dynamic> json) {
    final rules = _map(json['rules']);
    final next = json['next_change'];
    return SilenceStatus(
      active: json['is_silence_period'] == true,
      next: next is Map<String, dynamic> ? NextChange.fromJson(next) : null,
      weekdayRule: (rules['weekday'] as String?) ?? '',
      weekendRule: (rules['weekend'] as String?) ?? '',
    );
  }
}

class House {
  House({
    required this.sensorId,
    required this.name,
    required this.location,
    required this.online,
    required this.secondsSinceLast,
    required this.level,
    required this.rms,
    required this.readingInSilence,
    required this.todayReadings,
    required this.todayLoudInSilence,
  });

  final String sensorId;
  final String name; // "Casa 1"
  final String location;
  final bool online;
  final int? secondsSinceLast; // null = nunca enviou dados
  final String? level; // baixo | medio | alto | muito_alto
  final double? rms;
  final bool readingInSilence;
  final int todayReadings;
  final int todayLoudInSilence;

  factory House.fromJson(Map<String, dynamic> json) {
    final last = json['last_reading'];
    final lastMap = last is Map<String, dynamic> ? last : null;
    final today = _map(json['today']);
    final seconds = json['seconds_since_last'];
    return House(
      sensorId: json['sensor_id'] as String,
      name: (json['name'] as String?) ?? (json['sensor_id'] as String),
      location: (json['location'] as String?) ?? '',
      online: json['online'] == true,
      secondsSinceLast: seconds == null ? null : _toInt(seconds),
      level: lastMap?['noise_level'] as String?,
      rms: _toDouble(lastMap?['rms']),
      readingInSilence: lastMap?['is_silence_period'] == true,
      todayReadings: _toInt(today['readings']),
      todayLoudInSilence: _toInt(today['loud_in_silence']),
    );
  }
}

class Overview {
  Overview({required this.silence, required this.houses});

  final SilenceStatus silence;
  final List<House> houses;

  factory Overview.fromJson(Map<String, dynamic> json) => Overview(
        silence: SilenceStatus.fromJson(_map(json['silence'])),
        houses: ((json['houses'] as List<dynamic>?) ?? const <dynamic>[])
            .map((item) => House.fromJson(item as Map<String, dynamic>))
            .toList(),
      );
}

class HourBucket {
  HourBucket({
    required this.hour,
    required this.isSilence,
    required this.readings,
    required this.avgRms,
    required this.worstLevel,
    required this.loud,
    required this.loudInSilence,
  });

  final int hour;
  final bool isSilence;
  final int readings;
  final double? avgRms;
  final String? worstLevel;
  final int loud;
  final int loudInSilence;

  factory HourBucket.fromJson(Map<String, dynamic> json) => HourBucket(
        hour: _toInt(json['hour']),
        isSilence: json['is_silence'] == true,
        readings: _toInt(json['readings']),
        avgRms: _toDouble(json['avg_rms']),
        worstLevel: json['worst_level'] as String?,
        loud: _toInt(json['loud']),
        loudInSilence: _toInt(json['loud_in_silence']),
      );
}

class History {
  History({
    required this.name,
    required this.date,
    required this.buckets,
    required this.readings,
    required this.loud,
    required this.loudInSilence,
    required this.loudestHour,
  });

  final String name;
  final String date;
  final List<HourBucket> buckets;
  final int readings;
  final int loud;
  final int loudInSilence;
  final int? loudestHour;

  factory History.fromJson(Map<String, dynamic> json) {
    final summary = _map(json['summary']);
    final loudest = summary['loudest_hour'];
    return History(
      name: (json['name'] as String?) ?? '',
      date: (json['date'] as String?) ?? '',
      buckets: ((json['buckets'] as List<dynamic>?) ?? const <dynamic>[])
          .map((item) => HourBucket.fromJson(item as Map<String, dynamic>))
          .toList(),
      readings: _toInt(summary['readings']),
      loud: _toInt(summary['loud']),
      loudInSilence: _toInt(summary['loud_in_silence']),
      loudestHour: loudest == null ? null : _toInt(loudest),
    );
  }
}

// ---------------------------------------------
// Cliente HTTP
// ---------------------------------------------

class ApiClient {
  ApiClient(this.baseUrl);

  /// Ex.: http://192.168.0.10:5000
  final String baseUrl;

  static const _timeout = Duration(seconds: 6);

  /// Aceita "192.168.0.10", "192.168.0.10:5000" ou "http://..." e devolve
  /// sempre no formato completo, usando a porta 5000 se nenhuma for informada.
  static String normalize(String input) {
    var url = input.trim();
    if (url.isEmpty) return url;

    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'http://$url';
    }

    while (url.endsWith('/')) {
      url = url.substring(0, url.length - 1);
    }

    final uri = Uri.tryParse(url);
    if (uri == null) {
      return input.trim();
    }

    // Garante a porta 5000 do servidor local quando o usuário não informou outra.
    if (!uri.hasPort) {
      final scheme = uri.scheme;
      final host = uri.host;
      final path = uri.path.isEmpty ? '' : uri.path;
      final query = uri.query.isEmpty ? '' : '?${uri.query}';
      return '$scheme://$host:5000$path$query';
    }

    return url;
  }

  Future<Overview> overview() async {
    final json = await _get('/api/app/overview');
    return Overview.fromJson(json);
  }

  Future<History> history(String sensorId) async {
    final json = await _get('/api/app/houses/${Uri.encodeComponent(sensorId)}/history');
    return History.fromJson(json);
  }

  Future<Map<String, dynamic>> _get(String path) async {
    final uri = Uri.tryParse('$baseUrl$path');
    if (uri == null) {
      throw ApiException('O endereço "$baseUrl" não é válido.');
    }
    final response = await _send(uri);

    if (response.statusCode == 404 && path.startsWith('/api/app/overview')) {
      throw ApiException(
        'Encontrei o servidor, mas ele não tem as rotas do aplicativo. '
        'Atualize o sistema do computador para a versão 5.',
      );
    }
    if (response.statusCode != 200) {
      throw ApiException('O servidor respondeu com erro ${response.statusCode}.');
    }

    try {
      // bodyBytes + utf8 garante que acentos ("Área", "Sueli") cheguem certos
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is Map<String, dynamic>) return decoded;
    } on FormatException {
      // cai no erro abaixo
    }
    throw ApiException('O servidor respondeu algo que o app não entendeu.');
  }

  Future<http.Response> _send(Uri uri) async {
    try {
      return await http.get(uri).timeout(_timeout);
    } on TimeoutException {
      throw ApiException(
        'O servidor em $baseUrl não respondeu a tempo. '
        'Confira se o computador está ligado e no mesmo Wi-Fi do celular.',
      );
    } catch (_) {
      throw ApiException(
        'Não consegui conectar em $baseUrl. '
        'Confira o endereço e se o celular está no mesmo Wi-Fi do computador.',
      );
    }
  }
}
