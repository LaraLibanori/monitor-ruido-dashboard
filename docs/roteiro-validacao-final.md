# Roteiro de validação final

Este roteiro separa os testes que podem ser feitos no computador dos testes
que exigem ESP32, INMP441 e Android físico.

## 1. Validação do computador

Execute na raiz do projeto:

```powershell
python -m py_compile main.py database.py app_service.py app_routes.py silence_policy.py
docker compose config --quiet
docker compose up -d --build
curl.exe http://localhost:5000/health
```

O health check deve retornar HTTP 200 e `"status":"ok"`.

## 2. Teste da API sem hardware

Use uma sequência alta para evitar colisão com dados antigos:

```powershell
curl.exe -X POST http://localhost:5000/api/noise `
  -H "Content-Type: application/json" `
  -d '{"sensor_id":"sensor_ap1","location":"AP1","rms":12345,"noise_level":"medio","sequence":100000,"device_uptime_ms":1000}'
```

Confirme:

```powershell
curl.exe http://localhost:5000/api/readings
curl.exe http://localhost:5000/api/app/overview
```

## 3. Teste do dashboard offline

1. Inicie o Docker com internet disponível.
2. Abra `http://localhost:5000`.
3. Desative a internet do computador.
4. Atualize a página.
5. Confirme que os dados, tabela e gráfico continuam funcionando.

O dashboard não usa mais Tailwind, Chart.js ou Google Fonts por CDN. O gráfico
é desenhado pelo `canvas` nativo do navegador. O layout pode usar fontes e
estilos de fallback locais.

Após qualquer alteração de migration, recrie apenas o serviço da API para que
ele execute as migrations pendentes:

```powershell
docker compose up -d --build app
```

O banco também remove duplicatas antigas e passa a rejeitar novas repetições
da mesma combinação `sensor_id` + `sequence`.

## 4. Teste de cada ESP32

Para cada placa:

1. Configure SSID, senha, IP do computador e o par correto de sensor/local.
2. Grave `firmware/esp32_noise_monitor.ino`.
3. Abra o Serial Monitor em 115200 baud.
4. Confirme o IP Wi-Fi.
5. Aguarde pelo menos três mensagens `HTTP=200`.
6. Produza som próximo ao INMP441 e confirme mudança no RMS.
7. Desligue e religue a placa.
8. Confirme que as novas sequências continuam sendo aceitas.

Tabela de registro:

| Placa | Sensor | IP ESP32 | HTTP 200 | Reboot OK | RMS varia |
|---|---|---|---|---|---|
| 1 | sensor_ap1 | | [ ] | [ ] | [ ] |
| 2 | sensor_ap2 | | [ ] | [ ] | [ ] |
| 3 | sensor_ap3 | | [ ] | [ ] | [ ] |
| 4 | sensor_ap4 | | [ ] | [ ] | [ ] |

## 5. Calibração RMS

Os valores atuais são apenas classificação relativa. Para calibrar:

1. Deixe cada sensor em silêncio por pelo menos cinco minutos.
2. Registre o RMS mínimo, médio e máximo.
3. Faça sons conhecidos em três níveis.
4. Escolha limites que não classifiquem o ruído ambiente como `alto`.
5. Altere `classifyNoise()` no firmware.
6. Regrave todas as placas com a mesma tabela de limites.
7. Registre os limites finais no relatório do projeto.

O sistema não deve ser apresentado como medição oficial em decibéis sem
calibração com instrumento de referência.

## 6. Teste Android

```powershell
cd app
flutter pub get
flutter analyze
flutter test
flutter build apk --release
```

Instale o APK em um Android conectado à mesma rede. Informe o IPv4 do
computador, sem usar `localhost`, e confirme:

- visão geral das quatro casas;
- status online/offline;
- nível atual;
- histórico;
- funcionamento após desligar temporariamente o Wi-Fi.

## 7. Teste de estabilidade de 24 horas

Antes de iniciar:

- apague apenas os dados de teste, se necessário;
- anote a sequência inicial de cada sensor;
- mantenha computador, Docker e roteador ligados;
- não altere o firmware durante o teste.

Durante o teste, registre a cada hora:

| Hora | AP1 | AP2 | AP3 | AP4 | API saudável | Observação |
|---|---|---|---|---|---|---|
| 0h | | | | | | |
| 1h | | | | | | |
| 6h | | | | | | |
| 12h | | | | | | |
| 24h | | | | | | |

Critério de aprovação: API saudável durante todo o período, sem perda
persistente de sensor, sem crescimento anormal de erros HTTP e com sequências
crescentes após reinicializações.
