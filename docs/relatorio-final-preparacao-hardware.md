# Relatório final de preparação — Monitor de Ruído IoT

## 1. Resumo executivo

O projeto implementa quatro nós ESP32 com microfones INMP441, um servidor
local FastAPI/PostgreSQL, um dashboard web e um aplicativo Android Flutter.
O fluxo oficial é:

```text
INMP441 -> ESP32 -> Wi-Fi local -> FastAPI -> PostgreSQL
                                      |-> Dashboard Web
                                      |-> Aplicativo Android
```

O sistema foi desenhado para funcionar sem nuvem. O computador que executa o
Docker precisa estar ligado e conectado à mesma rede Wi-Fi dos ESP32 e do
celular.

## 2. Componentes e ligações

Para cada conjunto:

| Componente | Quantidade |
|---|---:|
| ESP32 DevKit | 1 por ponto de medição |
| INMP441 | 1 por ESP32 |
| Cabo USB e fonte 5 V | 1 por ESP32 |
| Computador com Docker Desktop | 1 |
| Roteador Wi-Fi 2,4 GHz | 1 |

Ligação do INMP441:

| INMP441 | ESP32 |
|---|---|
| VDD | 3V3 |
| GND | GND |
| WS/LRCL | GPIO25 |
| SD/DOUT | GPIO33 |
| SCK/BCLK | GPIO26 |
| L/R | GND |

Nunca alimente o INMP441 com 5 V. O pino L/R em GND seleciona o canal
esquerdo, que corresponde à configuração `I2S_CHANNEL_FMT_ONLY_LEFT`.

## 3. Código do hardware

O código completo está em `firmware/esp32_noise_monitor.ino`. Ele:

1. Inicializa o barramento I2S em 44,1 kHz e 32 bits.
2. Lê blocos de 1024 amostras.
3. Converte as amostras do INMP441 para RMS.
4. Classifica o resultado como `baixo`, `medio`, `alto` ou `muito_alto`.
5. Conecta e reconecta ao Wi-Fi.
6. Envia um `POST` a cada aproximadamente cinco segundos.
7. Usa timeout de leitura I2S e timeout HTTP.
8. Reserva sequências persistentes na memória `Preferences`, evitando que um
   reboot volte à sequência zero e seja rejeitado pela deduplicação do banco.
9. Descarta amostras I2S inválidas, evitando registrar falso nível `baixo`.

Configuração obrigatória no início do arquivo:

```cpp
const char *WIFI_SSID = "NOME_DA_REDE";
const char *WIFI_PASSWORD = "SENHA_DA_REDE";
const char *SERVER_URL = "http://IP_DO_COMPUTADOR:5000/api/noise";
const char *SENSOR_ID = "sensor_ap1";
const char *LOCATION = "AP1";
```

Grave uma configuração diferente em cada placa:

| Placa | SENSOR_ID | LOCATION |
|---|---|---|
| 1 | `sensor_ap1` | `AP1` |
| 2 | `sensor_ap2` | `AP2` |
| 3 | `sensor_ap3` | `AP3` |
| 4 | `sensor_ap4` | `AP4` |

O firmware não mede decibéis calibrados. O campo `rms` é uma medida relativa
do sinal digital do INMP441. Os limiares atuais são iniciais e precisam ser
calibrados no local:

```cpp
baixo       < 5000
medio       < 15000
alto        < 30000
muito_alto  >= 30000
```

## 4. Código do software

### Backend e banco

- `main.py`: API FastAPI, validação do payload, rate limit, dashboard e health
  check.
- `database.py`: pool PostgreSQL, migrations, persistência, consultas e
  deduplicação.
- `app_service.py` e `app_routes.py`: respostas específicas do Android.
- `silence_policy.py`: regra de horário de silêncio e fuso horário.
- `init.sql`: schema inicial e os quatro sensores.
- `migrations/`: atualizações incrementais do banco.
- `docker-compose.yaml`: PostgreSQL em `127.0.0.1:5432` e API em `0.0.0.0:5000`.
- `templates/index.html`: dashboard web.

Endpoint usado pelo ESP32:

```http
POST /api/noise
Content-Type: application/json
```

Exemplo:

```json
{
  "sensor_id": "sensor_ap1",
  "location": "AP1",
  "rms": 12345,
  "noise_level": "medio",
  "sequence": 100,
  "device_uptime_ms": 500000
}
```

Endpoints principais:

```text
GET  /health
GET  /api/readings
GET  /api/app/overview
GET  /api/app/houses/{sensor_id}/history
```

### Aplicativo Android

O código Flutter está em `app/`. O cliente:

- salva o endereço do servidor local;
- mostra as quatro casas/sensores;
- informa online/offline;
- exibe o nível atual;
- consulta histórico por casa;
- mostra resumo horário e situação da lei do silêncio.

O repositório separado do produto está documentado em
`projeto-2-android/README.md`.

## 5. O que está pronto

- Arquitetura local ESP32 → FastAPI → PostgreSQL.
- Firmware inicial completo para ESP32 + INMP441.
- Pinagem documentada.
- Quatro identificadores oficiais de sensores.
- API com validação de dados.
- Persistência PostgreSQL.
- Migrations automáticas.
- Deduplicação por `(sensor_id, sequence)`.
- Correção do reboot do ESP32 com sequência persistente.
- Dashboard web.
- Dashboard sem dependência obrigatória de CDN: o gráfico usa `canvas`
  nativo e as fontes possuem fallback local.
- Aplicativo Android Flutter.
- Docker Compose.
- Health check.
- Workflow GitHub para análise, testes e geração do APK.
- Documentação de instalação e operação.
- Repositórios separados planejados/publicados:
  `LaraLibanori/monitor-ruido-dashboard` e
  `LaraLibanori/monitor-ruido-android`.

## 6. O que ainda falta validar

Estas atividades não podem ser comprovadas apenas lendo o código:

1. Compilar o firmware na Arduino IDE com a versão instalada do core ESP32.
2. Gravar uma placa e confirmar o Serial Monitor em 115200 baud.
3. Confirmar `HTTP=200` por pelo menos cinco minutos.
4. Confirmar que a leitura aparece no dashboard e no PostgreSQL.
5. Repetir o teste para as quatro placas.
6. Liberar a porta TCP 5000 no Firewall do Windows, se necessário.
7. Calibrar os limiares RMS no local de instalação.
8. Instalar o APK em um Android real e testar o IP do computador.
9. Executar teste integrado contínuo de pelo menos 24 horas.
10. Confirmar visualmente o dashboard sem internet; a lógica e o gráfico não
    dependem mais de CDN, mas o layout deve ser revisado em navegador offline.
11. Publicar no GitHub as últimas correções locais, caso ainda não estejam no
    remoto.

## 7. Sequência segura de instalação

### Etapa A — Servidor

No computador:

```powershell
cd D:\OneDrive\Downloads\monitor-ruido-v5\monitor-ruido-v5
docker compose up -d --build
curl.exe http://localhost:5000/health
```

Esperado:

```json
{"status":"ok","total_readings":0}
```

Descubra o IPv4 do computador com `ipconfig`. Use esse endereço no firmware,
por exemplo `http://192.168.15.8:5000/api/noise`.

### Etapa B — Teste sem hardware

```powershell
curl.exe -X POST http://localhost:5000/api/noise `
  -H "Content-Type: application/json" `
  -d '{"sensor_id":"sensor_ap1","location":"AP1","rms":12345,"noise_level":"medio","sequence":1,"device_uptime_ms":1000}'
```

Esperado: resposta HTTP 200 e uma leitura visível no dashboard.

### Etapa C — Primeiro ESP32

1. Monte somente o sensor `sensor_ap1`.
2. Configure o SSID, senha, IP do computador e `sensor_ap1`.
3. Grave o firmware.
4. Abra o Serial Monitor em 115200.
5. Confirme IP Wi-Fi, RMS e `HTTP=200`.
6. Desligue e religue a placa.
7. Confirme que as sequências continuam avançando e que novas leituras são
   aceitas.

### Etapa D — Demais ESP32

Repita a etapa C alterando somente:

```text
sensor_ap2 / AP2
sensor_ap3 / AP3
sensor_ap4 / AP4
```

## 8. Critérios de aceite

O projeto estará operacional para uso quando:

- `/health` responder `status=ok`;
- o teste manual de `POST /api/noise` responder 200;
- cada ESP32 conectar ao Wi-Fi;
- cada ESP32 enviar leituras sem `HTTP=-1`;
- os quatro sensores aparecerem no dashboard;
- o Android consultar `/api/app/overview`;
- um reboot não interromper a sequência do sensor;
- leituras duplicadas não criarem registros duplicados;
- o sistema permanecer estável no teste de 24 horas;
- os níveis RMS forem calibrados e documentados no local.

## 9. Conclusão

O software está estruturado para iniciar a integração e gravação em hardware,
mas a etapa final depende obrigatoriamente de teste físico. A primeira
instalação deve usar apenas um ESP32; somente depois de confirmar Wi-Fi,
I2S, HTTP, banco e dashboard deve-se gravar as outras três placas.
