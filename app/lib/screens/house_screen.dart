// =============================================
// house_screen.dart - O dia de uma casa, hora a hora
// =============================================

import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../noise_ui.dart';

class HouseScreen extends StatefulWidget {
  const HouseScreen({super.key, required this.api, required this.house});

  final ApiClient api;
  final House house;

  @override
  State<HouseScreen> createState() => _HouseScreenState();
}

class _HouseScreenState extends State<HouseScreen> {
  static const _refreshEvery = Duration(seconds: 15);

  late House _house;
  History? _history;
  String? _error;
  Timer? _timer;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _house = widget.house;
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
      final history = await widget.api.history(_house.sensorId);
      final overview = await widget.api.overview();
      House updated = _house;
      for (final h in overview.houses) {
        if (h.sensorId == _house.sensorId) updated = h;
      }
      if (mounted) {
        setState(() {
          _history = history;
          _house = updated;
          _error = null;
        });
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      _loading = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final history = _history;
    final error = _error;
    return Scaffold(
      appBar: AppBar(title: Text(_house.name, style: const TextStyle(fontWeight: FontWeight.w700))),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 28),
          children: [
            _CurrentStatus(house: _house),
            const SizedBox(height: 20),
            const Padding(
              padding: EdgeInsets.only(left: 4),
              child: Text(
                'Hoje, hora a hora',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: AppColors.night),
              ),
            ),
            const Padding(
              padding: EdgeInsets.only(left: 4, top: 2, bottom: 10),
              child: Text(
                'Cada barra é uma hora. A altura mostra a intensidade média e a cor, o pior momento. '
                'As faixas azuladas são o horário de silêncio.',
                style: TextStyle(color: AppColors.muted, fontSize: 13, height: 1.35),
              ),
            ),
            if (history == null && error == null)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: CircularProgressIndicator()),
              ),
            if (history == null && error != null)
              SoftCard(child: Text(error, style: const TextStyle(color: AppColors.muted))),
            if (history != null) ...[
              SoftCard(child: HourlyChart(buckets: history.buckets)),
              const SizedBox(height: 12),
              _DaySummary(history: history),
            ],
          ],
        ),
      ),
    );
  }
}

/// Bloco grande com o estado atual da casa.
class _CurrentStatus extends StatelessWidget {
  const _CurrentStatus({required this.house});

  final House house;

  @override
  Widget build(BuildContext context) {
    final info = house.online ? levelInfo(house.level) : kNoSignal;
    final alert = house.online && isLoud(house.level) && house.readingInSilence;
    final seconds = house.secondsSinceLast;

    return SoftCard(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          LevelEmoji(info: info, size: 84),
          const SizedBox(height: 12),
          Text(
            info.label,
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: info.color),
          ),
          const SizedBox(height: 4),
          Text(info.example, textAlign: TextAlign.center, style: const TextStyle(color: AppColors.muted)),
          if (alert) ...[
            const SizedBox(height: 12),
            const AlertChip(text: 'Barulho em horário de silêncio'),
          ],
          const SizedBox(height: 12),
          Text(
            seconds == null ? 'Nenhum dado recebido ainda' : 'Atualizado ${timeAgo(seconds)}',
            style: const TextStyle(color: AppColors.muted, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

/// Gráfico de 24 barras, sem bibliotecas externas.
class HourlyChart extends StatelessWidget {
  const HourlyChart({super.key, required this.buckets});

  final List<HourBucket> buckets;

  @override
  Widget build(BuildContext context) {
    double maxAvg = 0;
    for (final b in buckets) {
      final avg = b.avgRms;
      if (avg != null && avg > maxAvg) maxAvg = avg;
    }

    return Column(
      children: [
        SizedBox(
          height: 170,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (final b in buckets)
                Expanded(
                  child: Container(
                    color: b.isSilence ? AppColors.nightSoft : Colors.transparent,
                    padding: const EdgeInsets.symmetric(horizontal: 1.5),
                    alignment: Alignment.bottomCenter,
                    child: _bar(b, maxAvg),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 6),
        const Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('0h', style: TextStyle(fontSize: 11, color: AppColors.muted)),
            Text('6h', style: TextStyle(fontSize: 11, color: AppColors.muted)),
            Text('12h', style: TextStyle(fontSize: 11, color: AppColors.muted)),
            Text('18h', style: TextStyle(fontSize: 11, color: AppColors.muted)),
            Text('23h', style: TextStyle(fontSize: 11, color: AppColors.muted)),
          ],
        ),
      ],
    );
  }

  Widget _bar(HourBucket b, double maxAvg) {
    final avg = b.avgRms;
    if (b.readings == 0 || avg == null || maxAvg <= 0) {
      return const SizedBox.shrink();
    }
    final info = levelInfo(b.worstLevel);
    final factor = (avg / maxAvg).clamp(0.06, 1.0).toDouble();
    return Tooltip(
      message: '${b.hour}h: ${info.label}',
      child: FractionallySizedBox(
        heightFactor: factor,
        child: Container(
          decoration: BoxDecoration(
            color: info.color,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(4)),
          ),
        ),
      ),
    );
  }
}

/// Números do dia em linguagem simples.
class _DaySummary extends StatelessWidget {
  const _DaySummary({required this.history});

  final History history;

  @override
  Widget build(BuildContext context) {
    final loudest = history.loudestHour;
    final items = <(String, String, String)>[
      ('🔊', 'Tempo barulhento hoje', approxDuration(history.loud)),
      ('🌙', 'Barulho no horário de silêncio', approxDuration(history.loudInSilence)),
      ('⏰', 'Hora mais agitada', loudest == null ? 'sem dados' : 'por volta das ${loudest}h'),
      ('📊', 'Medições recebidas hoje', '${history.readings}'),
    ];

    return SoftCard(
      child: Column(
        children: [
          for (final item in items)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(
                children: [
                  Text(item.$1, style: const TextStyle(fontSize: 20)),
                  const SizedBox(width: 12),
                  Expanded(child: Text(item.$2, style: const TextStyle(color: AppColors.muted))),
                  Text(
                    item.$3,
                    style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.night),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
