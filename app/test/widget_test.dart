import 'package:flutter_test/flutter_test.dart';
import 'package:monitor_ruido/api.dart';
import 'package:monitor_ruido/main.dart';

void main() {
  testWidgets('primeira abertura mostra a tela de conexão', (tester) async {
    await tester.pumpWidget(const MonitorApp());
    expect(find.text('Conectar ao servidor'), findsOneWidget);
  });

  test('endereço digitado vira URL completa com porta 5000', () {
    expect(ApiClient.normalize('192.168.0.10'), 'http://192.168.0.10:5000');
    expect(ApiClient.normalize(' 192.168.0.10:8000/ '), 'http://192.168.0.10:8000');
    expect(ApiClient.normalize('http://10.0.0.5:5000'), 'http://10.0.0.5:5000');
  });

  test('lê a resposta real do servidor (/api/app/overview)', () {
    final overview = Overview.fromJson({
      'silence': {
        'is_silence_period': true,
        'next_change': {'at': '09:00', 'day_offset': 1, 'silence_starts': false},
        'rules': {'weekday': '22:00–09:00', 'weekend': '15:00–09:00'},
      },
      'houses': [
        {
          'sensor_id': 'sensor_ap1', 'name': 'Casa 1', 'location': 'AP1', 'online': true,
          'seconds_since_last': 0,
          'last_reading': {'rms': 20000.5, 'noise_level': 'alto', 'is_silence_period': true},
          'today': {'readings': 1, 'loud_in_silence': 1},
        },
        {
          'sensor_id': 'sensor_ap2', 'name': 'Casa 2', 'location': 'AP2', 'online': false,
          'seconds_since_last': null, 'last_reading': null,
          'today': {'readings': 0, 'loud_in_silence': 0},
        },
      ],
    });
    expect(overview.silence.active, isTrue);
    expect(overview.silence.next?.at, '09:00');
    expect(overview.houses.first.level, 'alto');
    expect(overview.houses.last.secondsSinceLast, isNull);
  });
}
