import 'package:flutter/material.dart';

import '../api.dart';
import '../noise_ui.dart';

class NotificationHistoryScreen extends StatefulWidget {
  const NotificationHistoryScreen({super.key, required this.api});

  final ApiClient api;

  @override
  State<NotificationHistoryScreen> createState() =>
      _NotificationHistoryScreenState();
}

class _NotificationHistoryScreenState
    extends State<NotificationHistoryScreen> {
  List<NotificationRecord>? _items;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final items = await widget.api.notifications();
      if (mounted) setState(() { _items = items; _error = null; });
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final items = _items;
    return Scaffold(
      appBar: AppBar(title: const Text('Notificações')),
      body: items == null
          ? (_error == null
              ? const Center(child: CircularProgressIndicator())
              : Center(child: Text(_error!)))
          : RefreshIndicator(
              onRefresh: _load,
              child: items.isEmpty
                  ? ListView(children: const [
                      Padding(
                        padding: EdgeInsets.all(32),
                        child: Text('Nenhuma notificação registrada ainda.',
                            textAlign: TextAlign.center),
                      ),
                    ])
                  : ListView.builder(
                      physics: const AlwaysScrollableScrollPhysics(),
                      padding: const EdgeInsets.all(16),
                      itemCount: items.length,
                      itemBuilder: (_, index) => _NotificationCard(items[index]),
                    ),
            ),
    );
  }
}

class _NotificationCard extends StatelessWidget {
  const _NotificationCard(this.item);

  final NotificationRecord item;

  @override
  Widget build(BuildContext context) {
    final isFine = item.stage == 'fine_candidate';
    final title = isFine ? 'Ocorrência para análise de multa' : 'Advertência de ruído';
    final channel = item.channel == 'push' ? 'Notificação no app' : 'E-mail';
    final status = item.status == 'sent'
        ? 'enviado'
        : item.status == 'simulated'
            ? 'simulado'
            : item.status;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: SoftCard(
        child: ListTile(
          contentPadding: EdgeInsets.zero,
          leading: Icon(isFine ? Icons.gavel : Icons.notifications_active,
              color: isFine ? Colors.deepOrange : AppColors.alert),
          title: Text(title),
          subtitle: Text('$channel - $status\n${item.detail ?? ''}'),
          isThreeLine: true,
        ),
      ),
    );
  }
}
