// =============================================
// home_screen.dart - Visão do prédio (uma linha por casa)
// =============================================

import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../noise_ui.dart';
import 'connect_screen.dart';
import 'help_screen.dart';
import 'house_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.api});

  final ApiClient api;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  static const _refreshEvery = Duration(seconds: 5); // mesmo ritmo do ESP32

  Overview? _data;
  String? _error;
  Timer? _timer;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(_refreshEvery, (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    if (_loading) return;
    _loading = true;
    try {
      final data = await widget.api.overview();
      if (mounted) {
        setState(() {
          _data = data;
          _error = null;
        });
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      _loading = false;
    }
  }

  void _openSettings() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => ConnectScreen(initialUrl: widget.api.baseUrl)),
    );
  }

  void _openHelp() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => HelpScreen(silence: _data?.silence)),
    );
  }

  void _openHouse(House house) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => HouseScreen(api: widget.api, house: house)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Monitor de Ruído', style: TextStyle(fontWeight: FontWeight.w700)),
        actions: [
          IconButton(
            tooltip: 'Entenda as cores',
            icon: const Icon(Icons.help_outline),
            onPressed: _openHelp,
          ),
          IconButton(
            tooltip: 'Trocar servidor',
            icon: const Icon(Icons.settings_outlined),
            onPressed: _openSettings,
          ),
        ],
      ),
      body: data == null ? _buildFirstLoad() : _buildContent(data),
    );
  }

  Widget _buildFirstLoad() {
    final error = _error;
    if (error == null) {
      return const Center(child: CircularProgressIndicator());
    }
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const SizedBox(height: 40),
        const Text('🔌', textAlign: TextAlign.center, style: TextStyle(fontSize: 56)),
        const SizedBox(height: 12),
        const Text(
          'Sem conexão com o servidor',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: AppColors.night),
        ),
        const SizedBox(height: 8),
        Text(error, textAlign: TextAlign.center, style: const TextStyle(color: AppColors.muted, height: 1.4)),
        const SizedBox(height: 24),
        FilledButton.icon(onPressed: _load, icon: const Icon(Icons.refresh), label: const Text('Tentar de novo')),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: _openSettings,
          icon: const Icon(Icons.edit_outlined),
          label: const Text('Trocar endereço'),
        ),
      ],
    );
  }

  Widget _buildContent(Overview data) {
    final error = _error;
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
        children: [
          if (error != null) ...[
            _ConnectionWarning(message: error),
            const SizedBox(height: 12),
          ],
          SilenceCard(status: data.silence),
          const SizedBox(height: 12),
          _BuildingSummary(overview: data),
          const SizedBox(height: 20),
          const Padding(
            padding: EdgeInsets.only(left: 4, bottom: 8),
            child: Text(
              'Casas',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: AppColors.night),
            ),
          ),
          if (data.houses.isEmpty)
            const SoftCard(
              child: Text(
                'Nenhum sensor cadastrado ainda. Assim que um sensor enviar dados, ele aparece aqui.',
                style: TextStyle(color: AppColors.muted),
              ),
            ),
          for (final house in data.houses)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: HouseCard(house: house, onTap: () => _openHouse(house)),
            ),
        ],
      ),
    );
  }
}

/// Faixa amarela quando a conexão caiu mas ainda temos os últimos dados.
class _ConnectionWarning extends StatelessWidget {
  const _ConnectionWarning({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF4D6),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('⚠️'),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Mostrando os últimos dados recebidos. $message',
              style: const TextStyle(fontSize: 13, height: 1.3),
            ),
          ),
        ],
      ),
    );
  }
}

/// Uma frase que resume o prédio inteiro.
class _BuildingSummary extends StatelessWidget {
  const _BuildingSummary({required this.overview});

  final Overview overview;

  @override
  Widget build(BuildContext context) {
    final loud = overview.houses.where((h) => h.online && isLoud(h.level)).toList();
    final loudInSilence = loud.where((h) => h.readingInSilence).toList();
    final offline = overview.houses.where((h) => !h.online).length;

    String emoji;
    String title;
    String subtitle;
    Color color;

    if (loudInSilence.isNotEmpty) {
      emoji = '⚠️';
      title = 'Barulho em horário de silêncio';
      subtitle = loudInSilence.map((h) => h.name).join(', ');
      color = AppColors.alert;
    } else if (loud.isNotEmpty) {
      emoji = '🔊';
      title = loud.length == 1 ? '1 casa barulhenta agora' : '${loud.length} casas barulhentas agora';
      subtitle = '${loud.map((h) => h.name).join(', ')}. Fora do horário de silêncio, então é permitido.';
      color = const Color(0xFFE8722A);
    } else {
      emoji = '😌';
      title = 'Tudo tranquilo no prédio';
      subtitle = 'Nenhuma casa barulhenta agora.';
      color = const Color(0xFF2E9E6B);
    }

    if (offline > 0) {
      subtitle += offline == 1 ? '\n📡 1 sensor sem sinal.' : '\n📡 $offline sensores sem sinal.';
    }

    return SoftCard(
      child: Row(
        children: [
          Text(emoji, style: const TextStyle(fontSize: 30)),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: color)),
                const SizedBox(height: 2),
                Text(subtitle, style: const TextStyle(color: AppColors.muted, height: 1.35)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Cartão de uma casa na lista.
class HouseCard extends StatelessWidget {
  const HouseCard({super.key, required this.house, required this.onTap});

  final House house;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final info = house.online ? levelInfo(house.level) : kNoSignal;
    final alert = house.online && isLoud(house.level) && house.readingInSilence;
    final seconds = house.secondsSinceLast;

    final String detail;
    if (house.online) {
      detail = info.example;
    } else if (seconds == null) {
      detail = 'Ainda não enviou nenhum dado';
    } else {
      detail = 'Última leitura ${timeAgo(seconds)}';
    }

    return SoftCard(
      onTap: onTap,
      padding: const EdgeInsets.all(14),
      child: Row(
        children: [
          LevelEmoji(info: info),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  house.name,
                  style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700, color: AppColors.night),
                ),
                const SizedBox(height: 2),
                Text(info.label, style: TextStyle(color: info.color, fontWeight: FontWeight.w700)),
                Text(detail, style: const TextStyle(color: AppColors.muted, fontSize: 13)),
                if (alert) ...[
                  const SizedBox(height: 8),
                  const AlertChip(text: 'Horário de silêncio'),
                ],
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              if (house.online && seconds != null)
                Text(timeAgo(seconds), style: const TextStyle(color: AppColors.muted, fontSize: 12)),
              const Icon(Icons.chevron_right, color: AppColors.muted),
            ],
          ),
        ],
      ),
    );
  }
}
