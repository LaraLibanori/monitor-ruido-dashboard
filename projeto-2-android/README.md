# Projeto 2 — Aplicativo Android

Este diretório identifica o produto Aplicativo Android do Monitor de Ruído IoT.

## Código de execução

O aplicativo Flutter fica em:

```text
app/
```

O backend local e o contrato da API ficam na raiz do projeto porque são
compartilhados com o Dashboard Web e com os ESP32.

## Executar

Com Flutter instalado:

```text
cd app
flutter pub get
flutter test
flutter run
```

Para gerar o APK:

```text
cd app
flutter build apk --release
```

O APK será gerado em:

```text
app/build/app/outputs/flutter-apk/app-release.apk
```

## Funcionalidades

- conexão com o servidor local;
- salvamento do endereço do servidor;
- visão geral das casas;
- classificação em linguagem simples;
- alerta de ruído no horário de silêncio;
- indicação de sensor sem sinal;
- histórico por casa;
- gráfico por hora;
- atualização automática;
- tela de ajuda.

## APIs consumidas

- `GET /api/app/overview`
- `GET /api/app/houses/{sensor_id}/history`

## Critério de aceite

O aplicativo deve ser instalado em Android real, conectar ao IP do computador,
mostrar os quatro sensores e continuar exibindo o último estado conhecido
quando ocorrer uma falha temporária de rede.
