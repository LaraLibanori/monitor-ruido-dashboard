// =============================================
// connect_screen.dart - Digitar o endereço do computador
// =============================================

import 'package:flutter/material.dart';

import '../api.dart';
import '../noise_ui.dart';
import '../settings.dart';
import 'home_screen.dart';

class ConnectScreen extends StatefulWidget {
  const ConnectScreen({super.key, this.initialUrl});

  final String? initialUrl;

  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen> {
  late final TextEditingController _controller;
  bool _testing = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: _displayAddress(widget.initialUrl));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  /// Mostra "192.168.0.10:5000" em vez de "http://192.168.0.10:5000".
  static String _displayAddress(String? url) {
    if (url == null) return '';
    return url.replaceFirst('https://', '').replaceFirst('http://', '');
  }

  Future<void> _connect() async {
    final url = ApiClient.normalize(_controller.text);
    if (url.isEmpty) {
      setState(() => _error = 'Digite o endereço que apareceu no computador.');
      return;
    }

    FocusScope.of(context).unfocus();
    setState(() {
      _testing = true;
      _error = null;
    });

    try {
      final api = ApiClient(url);
      await api.overview(); // testa de verdade antes de salvar
      await Settings.saveServer(url);
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute<void>(builder: (_) => HomeScreen(api: api)),
        (route) => false,
      );
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Monitor de Ruído')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
        children: [
          const Text('📡', style: TextStyle(fontSize: 56)),
          const SizedBox(height: 8),
          Text(
            'Conectar ao servidor',
            style: text.headlineSmall?.copyWith(fontWeight: FontWeight.w700, color: AppColors.night),
          ),
          const SizedBox(height: 8),
          const Text(
            'O aplicativo mostra os dados do computador que está rodando o sistema. '
            'Digite o endereço que aparece na tela preta quando você abre o "iniciar.bat".',
            style: TextStyle(color: AppColors.muted, height: 1.4),
          ),
          const SizedBox(height: 24),
          TextField(
            controller: _controller,
            keyboardType: TextInputType.url,
            autocorrect: false,
            textInputAction: TextInputAction.go,
            onSubmitted: (_) => _testing ? null : _connect(),
            decoration: InputDecoration(
              labelText: 'Endereço do computador',
              hintText: '192.168.0.10',
              helperText: 'A porta 5000 é colocada sozinha se você não digitar.',
              prefixIcon: const Icon(Icons.computer_outlined),
              errorText: _error,
              errorMaxLines: 4,
              filled: true,
              fillColor: Colors.white,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
            ),
          ),
          const SizedBox(height: 20),
          SizedBox(
            height: 52,
            child: FilledButton.icon(
              onPressed: _testing ? null : _connect,
              icon: _testing
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.wifi),
              label: Text(_testing ? 'Testando conexão...' : 'Conectar'),
            ),
          ),
          const SizedBox(height: 28),
          const _Tips(),
        ],
      ),
    );
  }
}

class _Tips extends StatelessWidget {
  const _Tips();

  @override
  Widget build(BuildContext context) {
    const tips = [
      ('📶', 'O celular precisa estar no mesmo Wi-Fi do computador.'),
      ('🐳', 'No computador, o Docker Desktop precisa estar aberto e o sistema ligado.'),
      ('🛡️', 'Se não conectar, rode o "liberar_firewall.bat" no computador como administrador.'),
      ('🏠', 'Wi-Fi de visitantes às vezes bloqueia aparelhos de conversarem entre si.'),
    ];
    return SoftCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Não conectou? Confira:',
            style: TextStyle(fontWeight: FontWeight.w700, color: AppColors.night),
          ),
          const SizedBox(height: 10),
          for (final tip in tips)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(tip.$1),
                  const SizedBox(width: 10),
                  Expanded(child: Text(tip.$2, style: const TextStyle(height: 1.3))),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
