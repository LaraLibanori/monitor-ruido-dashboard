// =============================================
// help_screen.dart - Explica o app para quem não é especialista
// =============================================

import 'package:flutter/material.dart';

import '../api.dart';
import '../noise_ui.dart';

class HelpScreen extends StatelessWidget {
  const HelpScreen({super.key, this.silence});

  final SilenceStatus? silence;

  @override
  Widget build(BuildContext context) {
    final rules = silence;
    return Scaffold(
      appBar: AppBar(title: const Text('Entenda', style: TextStyle(fontWeight: FontWeight.w700))),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 28),
        children: [
          const _Section(
            emoji: '🌡️',
            title: 'O que o sensor mede?',
            body: 'Cada casa tem um sensor que funciona como um termômetro de barulho: '
                'ele mede só o quão alto está o ambiente, várias vezes por minuto. '
                'O sensor não grava sons nem conversas. Nenhum áudio sai dele.',
          ),
          const SizedBox(height: 12),
          SoftCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '🎨 O que cada cor quer dizer',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: AppColors.night),
                ),
                const SizedBox(height: 12),
                for (final level in kLevelOrder) _LevelRow(info: levelInfo(level)),
                const _LevelRow(info: kNoSignal),
              ],
            ),
          ),
          const SizedBox(height: 12),
          _Section(
            emoji: '🌙',
            title: 'Horário de silêncio',
            body: rules == null || rules.weekdayRule.isEmpty
                ? 'Os horários seguem a convenção do condomínio.'
                : 'Segundo a convenção do condomínio:\n'
                    '• Segunda a sexta: silêncio das ${rules.weekdayRule.replaceAll('–', ' às ')}.\n'
                    '• Sábado e domingo: silêncio das ${rules.weekendRule.replaceAll('–', ' às ')}.\n'
                    'Barulho "Tranquilo" ou "Movimento normal" nunca gera alerta.',
          ),
          const SizedBox(height: 12),
          const _Section(
            emoji: '📏',
            title: 'Uma observação honesta',
            body: 'Os níveis comparam o barulho entre casas e horários. '
                'Eles não são uma medição oficial em decibéis e não substituem '
                'um aparelho certificado para fins legais.',
          ),
        ],
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.emoji, required this.title, required this.body});

  final String emoji;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return SoftCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '$emoji $title',
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: AppColors.night),
          ),
          const SizedBox(height: 8),
          Text(body, style: const TextStyle(height: 1.45)),
        ],
      ),
    );
  }
}

class _LevelRow extends StatelessWidget {
  const _LevelRow({required this.info});

  final NoiseLevelInfo info;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          LevelEmoji(info: info, size: 42),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(info.label, style: TextStyle(fontWeight: FontWeight.w700, color: info.color)),
                Text(info.example, style: const TextStyle(color: AppColors.muted, fontSize: 13)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
