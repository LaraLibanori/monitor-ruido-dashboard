// =============================================
// noise_ui.dart - Tradução do barulho para linguagem do dia a dia
// =============================================
// Aqui mora a "interpretação": o servidor manda
// "alto", o app mostra "Barulhento 😬 - dá para ouvir do corredor".
// =============================================

import 'package:flutter/material.dart';

import 'api.dart';

class AppColors {
  static const night = Color(0xFF23395B); // azul-noite: horário de silêncio
  static const nightSoft = Color(0xFFDDE4F0); // faixa de silêncio no gráfico
  static const background = Color(0xFFF2F4F7);
  static const border = Color(0xFFE1E5EB);
  static const muted = Color(0xFF6B7482);
  static const offline = Color(0xFF9AA3AE);
  static const alert = Color(0xFFD64545);
}

class NoiseLevelInfo {
  const NoiseLevelInfo({
    required this.label,
    required this.emoji,
    required this.example,
    required this.color,
  });

  final String label;
  final String emoji;
  final String example;
  final Color color;
}

/// Ordem do mais silencioso para o mais barulhento.
const kLevelOrder = <String>['baixo', 'medio', 'alto', 'muito_alto'];

const kNoiseLevels = <String, NoiseLevelInfo>{
  'baixo': NoiseLevelInfo(
    label: 'Tranquilo',
    emoji: '😌',
    example: 'Silêncio de biblioteca',
    color: Color(0xFF2E9E6B),
  ),
  'medio': NoiseLevelInfo(
    label: 'Movimento normal',
    emoji: '🙂',
    example: 'Conversa ou TV em volume normal',
    color: Color(0xFFC99700),
  ),
  'alto': NoiseLevelInfo(
    label: 'Barulhento',
    emoji: '😬',
    example: 'Dá para ouvir do corredor',
    color: Color(0xFFE8722A),
  ),
  'muito_alto': NoiseLevelInfo(
    label: 'Muito alto',
    emoji: '📢',
    example: 'Música alta, festa ou obra',
    color: Color(0xFFD64545),
  ),
};

const kNoSignal = NoiseLevelInfo(
  label: 'Sem sinal',
  emoji: '📡',
  example: 'O sensor não está enviando dados',
  color: AppColors.offline,
);

NoiseLevelInfo levelInfo(String? level) => kNoiseLevels[level] ?? kNoSignal;

bool isLoud(String? level) => level == 'alto' || level == 'muito_alto';

/// "agora mesmo", "há 40 s", "há 5 min"...
String timeAgo(int seconds) {
  if (seconds < 10) return 'agora mesmo';
  if (seconds < 60) return 'há $seconds s';
  final minutes = seconds ~/ 60;
  if (minutes < 60) return 'há $minutes min';
  final hours = minutes ~/ 60;
  if (hours < 24) return 'há $hours h';
  final days = hours ~/ 24;
  return days == 1 ? 'há 1 dia' : 'há $days dias';
}

/// Cada leitura representa ~5 segundos de medição.
String approxDuration(int readings) {
  final minutes = (readings * 5 / 60).round();
  if (readings == 0) return 'nenhum';
  if (minutes < 1) return 'menos de 1 min';
  if (minutes < 60) return 'cerca de $minutes min';
  final hours = minutes ~/ 60;
  final rest = minutes % 60;
  return rest == 0 ? 'cerca de $hours h' : 'cerca de $hours h $rest min';
}

String _dayLabel(int offset) {
  if (offset <= 0) return '';
  if (offset == 1) return ' de amanhã';
  return ' daqui a $offset dias';
}

/// "Faça silêncio até as 09:00 de amanhã" / "O silêncio começa às 22:00"
String nextChangeText(SilenceStatus status) {
  final next = status.next;
  if (next == null) {
    return status.active ? 'Respeite o horário de silêncio.' : 'Barulho permitido agora.';
  }
  final day = _dayLabel(next.dayOffset);
  return status.active
      ? 'Faça silêncio até as ${next.at}$day.'
      : 'O silêncio começa às ${next.at}$day.';
}

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(seedColor: AppColors.night);
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: AppColors.background,
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.background,
      foregroundColor: AppColors.night,
      elevation: 0,
      centerTitle: false,
    ),
  );
}

// ---------------------------------------------
// Peças visuais reaproveitadas pelas telas
// ---------------------------------------------

/// Cartão branco com borda suave.
class SoftCard extends StatelessWidget {
  const SoftCard({super.key, required this.child, this.padding = const EdgeInsets.all(16), this.onTap});

  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      margin: EdgeInsets.zero,
      color: Colors.white,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: const BorderSide(color: AppColors.border),
      ),
      child: InkWell(
        onTap: onTap,
        child: Padding(padding: padding, child: child),
      ),
    );
  }
}

/// Círculo colorido com o emoji do nível.
class LevelEmoji extends StatelessWidget {
  const LevelEmoji({super.key, required this.info, this.size = 52});

  final NoiseLevelInfo info;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: info.color.withAlpha(40),
        shape: BoxShape.circle,
      ),
      child: Text(info.emoji, style: TextStyle(fontSize: size * 0.5)),
    );
  }
}

/// Etiqueta vermelha de alerta.
class AlertChip extends StatelessWidget {
  const AlertChip({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.alert.withAlpha(28),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        '🌙 $text',
        style: const TextStyle(color: AppColors.alert, fontSize: 12, fontWeight: FontWeight.w600),
      ),
    );
  }
}

/// Cartão do topo: estamos ou não no horário de silêncio?
class SilenceCard extends StatelessWidget {
  const SilenceCard({super.key, required this.status});

  final SilenceStatus status;

  @override
  Widget build(BuildContext context) {
    final active = status.active;
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: active ? AppColors.night : Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: active ? null : Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          Text(active ? '🌙' : '☀️', style: const TextStyle(fontSize: 34)),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  active ? 'Horário de silêncio' : 'Horário livre',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    color: active ? Colors.white : AppColors.night,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  nextChangeText(status),
                  style: TextStyle(color: active ? Colors.white70 : AppColors.muted),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
