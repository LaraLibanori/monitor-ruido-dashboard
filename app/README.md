# 📱 Monitor de Ruído — aplicativo Android

Aplicativo Flutter que lê a API do servidor (Docker) e mostra o barulho de cada casa
em linguagem simples. Ele **só lê** dados: nunca escreve nada no sistema.

## Jeito 1 — APK pronto pelo GitHub (não precisa instalar nada)

1. Suba o projeto no GitHub (a pasta `.github/` precisa ir junto).
2. Abra a aba **Actions** do repositório → **Gerar APK do app** → **Run workflow**.
3. Espere uns 5–10 minutos até ficar verde ✅.
4. Clique na execução e baixe **monitor-ruido-apk** (vem num .zip com o `app-release.apk`).
5. Mande o APK para o celular (WhatsApp, cabo, Drive) e toque nele para instalar.
   O Android vai pedir para **permitir instalar apps desta fonte**: é só permitir.

## Jeito 2 — Compilar no computador (precisa do Flutter)

1. Instale o Flutter: https://docs.flutter.dev/get-started/install
2. Dê dois cliques em `construir_apk.bat`.
3. O APK sai em `build\app\outputs\flutter-apk\app-release.apk`.

Para testar direto no celular pelo cabo USB (modo desenvolvedor ligado): `flutter run`.

## Usando

1. No computador, rode o `iniciar.bat` da pasta principal e anote o endereço que ele mostra
   (algo como `192.168.0.10`).
2. Abra o app e digite esse endereço. O app testa a conexão antes de salvar.
3. Celular e computador precisam estar **no mesmo Wi-Fi**.

## Estrutura

```
lib/
├── main.dart              início do app
├── api.dart               conversa com o servidor + modelos de dados
├── noise_ui.dart          tradução "alto" → "Barulhento 😬" + peças visuais
├── settings.dart          guarda o endereço do servidor
└── screens/
    ├── connect_screen.dart   digitar o endereço
    ├── home_screen.dart      o prédio: uma linha por casa
    ├── house_screen.dart     o dia da casa, hora a hora
    └── help_screen.dart      explicação das cores e horários
```

A pasta `android/` tem só o `AndroidManifest.xml` (com a liberação de HTTP na rede local);
o resto é gerado automaticamente pelo `flutter create` no primeiro build.
