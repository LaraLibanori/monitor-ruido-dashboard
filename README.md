# Monitor de Ruído IoT

Sistema local de monitoramento de ruído com **ESP32**, **INMP441**,
**FastAPI**, **PostgreSQL**, **Docker** e aplicativo **Flutter**.

O projeto coleta somente uma métrica numérica de intensidade sonora (RMS).
Ele **não grava, transmite ou armazena áudio**.

## Sumário

- [Visão geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Status do projeto](#status-do-projeto)
- [Pré-requisitos](#pré-requisitos)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Inicialização rápida](#inicialização-rápida)
- [Configuração](#configuração)
- [Hardware e firmware](#hardware-e-firmware)
- [API](#api)
- [Dashboard Web](#dashboard-web)
- [Aplicativo Android e Flutter Web](#aplicativo-android-e-flutter-web)
- [Testes e validação](#testes-e-validação)
- [Operação e manutenção](#operação-e-manutenção)
- [Solução de problemas](#solução-de-problemas)
- [Documentação complementar](#documentação-complementar)

## Visão geral

O sistema foi projetado para funcionar exclusivamente na rede local:

```text
INMP441 -> ESP32 -> Wi-Fi local -> FastAPI -> PostgreSQL
                                      |-> Dashboard Web
                                      |-> Aplicativo Android
                                      |-> Flutter Web
```

O computador que executa o Docker é o servidor da aplicação. Os ESP32, o
celular e o computador precisam estar conectados à mesma rede.

### Sensores oficiais

| Sensor | Identificador | Local inicial |
|---|---|---|
| 1 | `sensor_ap1` | AP1 |
| 2 | `sensor_ap2` | AP2 |
| 3 | `sensor_ap3` | AP3 |
| 4 | `sensor_ap4` | AP4 |

## Arquitetura

### Backend

- **FastAPI**: API HTTP, validação do payload, rate limiting e dashboard.
- **PostgreSQL**: armazenamento das leituras e cadastro dos sensores.
- **Docker Compose**: execução reproduzível do backend e do banco.
- **Migrations**: atualizações incrementais aplicadas ao iniciar a API.
- **CORS**: permite o Flutter Web local em `localhost` e `127.0.0.1`,
  incluindo portas de desenvolvimento variáveis.

### Firmware

Cada ESP32:

1. lê o INMP441 por I2S;
2. calcula o RMS;
3. classifica o nível relativo;
4. conecta ao Wi-Fi;
5. envia JSON para `POST /api/noise` a cada aproximadamente cinco segundos;
6. reserva sequências na memória flash para sobreviver a reinicializações.

### Interfaces

- **Dashboard Web**: acompanhamento das leituras, status e histórico recente.
- **Android**: visão geral das casas, status online/offline e histórico.
- **Flutter Web**: acesso à API local durante o desenvolvimento, com CORS
  configurado no backend.

## Status do projeto

### Implementado

- API FastAPI e PostgreSQL em Docker.
- Quatro sensores cadastrados.
- Recebimento e validação de leituras.
- Deduplicação por `(sensor_id, sequence)`.
- Regras de horário de silêncio.
- Dashboard Web.
- Aplicativo Flutter.
- CORS para desenvolvimento Flutter Web local.
- Health check e documentação de instalação.

### Validações realizadas

- API local respondendo HTTP 200.
- Leitura manual aceita por `POST /api/noise`.
- Leituras reais de ESP32 recebidas com `HTTP=200`.
- Quatro sensores preparados para uso.
- Dashboard operando sem dependência obrigatória de CDN.

### Validações dependentes do ambiente

- Compilação final na Arduino IDE instalada pelo usuário.
- Teste físico de cada ESP32 e INMP441.
- Calibração dos limiares RMS no local.
- Instalação e teste do APK em Android físico.
- Teste integrado contínuo de 24 horas.

Os critérios detalhados estão em `docs/roteiro-validacao-final.md`.

## Pré-requisitos

### Servidor

- Windows 10/11.
- Docker Desktop com **Engine running**.
- Computador conectado à rede local.
- Porta TCP `5000` disponível.
- Porta TCP `5432` disponível apenas localmente para o PostgreSQL.

### Hardware

- ESP32 DevKit.
- Microfone digital INMP441.
- Cabo USB e alimentação adequada.
- Rede Wi-Fi compatível com o ESP32, normalmente 2,4 GHz.

### Desenvolvimento Android

- Flutter SDK compatível com o `pubspec.yaml`.
- Android SDK e dispositivo/emulador, para testes Android.
- Java 17, conforme o workflow de build.

## Estrutura do projeto

```text
monitor-ruido-v5/
├── app/                           # Aplicativo Flutter
├── firmware/                      # Código dos ESP32 e manual
├── migrations/                    # Migrations PostgreSQL
├── templates/
│   └── index.html                 # Dashboard Web
├── docs/                          # Arquitetura, validação e operação
├── main.py                        # Aplicação FastAPI
├── app_routes.py                  # Rotas específicas do app
├── app_service.py                 # Serviço de apresentação do app
├── database.py                    # Persistência e migrations
├── silence_policy.py              # Regras de horário de silêncio
├── init.sql                       # Schema inicial e sensores
├── Dockerfile
├── docker-compose.yaml
├── requirements.txt
└── .env.example
```

## Inicialização rápida

Abra um CMD ou PowerShell na raiz do projeto:

```powershell
cd D:\OneDrive\Downloads\monitor-ruido-v5\monitor-ruido-v5
docker compose up -d --build
```

Verifique os serviços:

```powershell
docker compose ps
```

O esperado é que `noise_db` e `noise_app` estejam em execução.

Teste a API:

```powershell
curl.exe http://localhost:5000/health
```

Resposta esperada:

```json
{"status":"ok","total_readings":0}
```

Abra o dashboard em:

```text
http://localhost:5000
```

Para acompanhar os logs:

```powershell
docker compose logs -f app
```

Para parar os serviços:

```powershell
docker compose down
```

> `docker compose down` remove os contêineres, mas preserva o volume
> `postgres_data`. Para apagar os dados, use `docker compose down -v` somente
> se essa perda for intencional.

## Configuração

### Arquivo `.env`

Copie o modelo:

```powershell
Copy-Item .env.example .env
```

Edite `.env` conforme o ambiente:

```env
POSTGRES_DB=noisedb
POSTGRES_USER=noiseuser
POSTGRES_PASSWORD=troque-esta-senha

RATE_LIMIT_MAX=100
RATE_LIMIT_WINDOW=60

APP_TIMEZONE=America/Sao_Paulo
SILENCE_START_WEEKDAY=22:00
SILENCE_START_WEEKEND=15:00
SILENCE_END=09:00

OFFLINE_AFTER_SECONDS=60
CORS_ALLOW_ORIGINS=http://localhost,http://127.0.0.1
```

O arquivo `.env` contém configuração local e não deve ser publicado.

Após alterar variáveis:

```powershell
docker compose up -d --build app
```

### IP do computador na rede local

Descubra o IPv4:

```powershell
ipconfig
```

Exemplo de endereço do servidor:

```text
192.168.0.139
```

Esse endereço será usado pelo ESP32 e pelo celular. Não use `localhost` no
firmware ou no Android: nesses dispositivos, `localhost` aponta para o próprio
dispositivo.

## Hardware e firmware

O firmware está em:

```text
firmware/esp32_noise_monitor.ino
```

### Ligações do INMP441

| INMP441 | ESP32 |
|---|---|
| VDD | 3V3 |
| GND | GND |
| WS/LRCL | GPIO25 |
| SD/DOUT | GPIO33 |
| SCK/BCLK | GPIO26 |
| L/R | GND |

Use somente 3,3 V no INMP441.

### Configuração de cada placa

No início do firmware:

```cpp
const char *WIFI_SSID = "NOME_DA_REDE";
const char *WIFI_PASSWORD = "SENHA_DA_REDE";
const char *SERVER_URL = "http://192.168.0.139:5000/api/noise";
const char *SENSOR_ID = "sensor_ap1";
const char *LOCATION = "AP1";
```

Grave cada placa com um identificador exclusivo:

| Placa | `SENSOR_ID` | `LOCATION` |
|---|---|---|
| 1 | `sensor_ap1` | `AP1` |
| 2 | `sensor_ap2` | `AP2` |
| 3 | `sensor_ap3` | `AP3` |
| 4 | `sensor_ap4` | `AP4` |

Na Arduino IDE:

1. Instale **esp32 by Espressif Systems**.
2. Abra o arquivo `.ino`.
3. Selecione **ESP32 Dev Module**.
4. Selecione a porta COM.
5. Clique em **Verify** e depois em **Upload**.
6. Abra o Serial Monitor em `115200` baud.

Saída esperada:

```text
Wi-Fi conectado. IP: 192.168.x.x
RMS=...
nivel=...
HTTP=200
```

### RMS e calibração

Os níveis atuais são relativos ao sinal digital do INMP441:

```text
baixo       < 5000
medio       < 15000
alto        < 30000
muito_alto  >= 30000
```

Esses valores **não são decibéis oficiais**. Para calibrar:

1. registre o RMS em silêncio por cinco minutos;
2. registre o ambiente em condição normal;
3. registre um ruído alto conhecido;
4. ajuste `classifyNoise()`;
5. regrave todas as placas com a mesma tabela;
6. documente os valores finais.

## API

### Health check

```http
GET /health
```

```powershell
curl.exe http://localhost:5000/health
```

### Receber leitura do ESP32

```http
POST /api/noise
Content-Type: application/json
```

Exemplo no CMD:

```cmd
curl.exe -X POST "http://localhost:5000/api/noise" -H "Content-Type: application/json" -d "{\"sensor_id\":\"sensor_ap1\",\"location\":\"AP1\",\"rms\":12345,\"noise_level\":\"medio\",\"sequence\":100000,\"device_uptime_ms\":1000}"
```

Payload:

```json
{
  "sensor_id": "sensor_ap1",
  "location": "AP1",
  "rms": 12345.0,
  "noise_level": "medio",
  "sequence": 100000,
  "device_uptime_ms": 1000
}
```

### Leituras recentes

```http
GET /api/readings
```

```powershell
curl.exe http://localhost:5000/api/readings
```

### Visão geral do aplicativo

```http
GET /api/app/overview
```

### Histórico de uma casa

```http
GET /api/app/houses/{sensor_id}/history
```

Exemplo:

```powershell
curl.exe http://localhost:5000/api/app/houses/sensor_ap1/history
```

### CORS para Flutter Web

O backend aceita origens locais como:

```text
http://localhost:56536
http://127.0.0.1:56536
```

Para testar o header:

```powershell
curl.exe -i -H "Origin: http://localhost:56536" http://localhost:5000/api/app/overview
```

Procure:

```text
access-control-allow-origin: http://localhost:56536
```

## Dashboard Web

Acesse:

```text
http://localhost:5000
```

O dashboard apresenta:

- última leitura recebida;
- sensor e localização;
- RMS e classificação;
- histórico recente;
- status da API;
- horário de silêncio;
- gráfico de intensidade;
- indicação de leituras durante o horário de silêncio.

O dashboard não depende de Tailwind, Chart.js ou Google Fonts externos. O
gráfico utiliza `canvas` nativo e o layout possui estilos locais de fallback,
permitindo teste sem internet.

## Aplicativo Android e Flutter Web

O código Flutter está em `app/`.

### Desenvolvimento

```powershell
cd app
flutter pub get
flutter analyze
flutter test
flutter run
```

Para executar no Flutter Web:

```powershell
flutter run -d chrome
```

Use a URL do servidor local configurado pelo aplicativo:

```text
http://192.168.0.139:5000
```

### APK de release

```powershell
flutter build apk --release
```

O APK será gerado em:

```text
app/build/app/outputs/flutter-apk/app-release.apk
```

No Android físico, computador e celular devem estar na mesma rede. Não use
`localhost` no celular.

## Testes e validação

### Teste sem hardware

```powershell
curl.exe http://localhost:5000/health
curl.exe http://localhost:5000/api/app/overview
```

Envie uma leitura manual e confirme que ela aparece no dashboard:

```cmd
curl.exe -X POST "http://localhost:5000/api/noise" -H "Content-Type: application/json" -d "{\"sensor_id\":\"sensor_ap1\",\"location\":\"AP1\",\"rms\":12345,\"noise_level\":\"medio\",\"sequence\":100000,\"device_uptime_ms\":1000}"
```

### Teste com os quatro ESP32

Para cada placa, confirme:

- Wi-Fi conectado;
- IP atribuído;
- RMS variável;
- pelo menos três respostas `HTTP=200`;
- leitura visível no dashboard;
- sequência crescente após reinicialização.

### Teste offline

1. Abra o dashboard com dados disponíveis.
2. Desconecte o computador da internet.
3. Atualize com `Ctrl+F5`.
4. Confirme tabela e gráfico.

### Teste de estabilidade

Depois de validar os quatro sensores:

1. mantenha computador, Docker e roteador ligados;
2. mantenha os quatro ESP32 alimentados;
3. registre saúde da API e status dos sensores;
4. execute o acompanhamento por 24 horas.

O roteiro detalhado e a tabela de acompanhamento estão em
`docs/roteiro-validacao-final.md`.

## Operação e manutenção

### Ver logs

```powershell
docker compose logs -f app
docker compose logs -f db
```

### Reiniciar a API

```powershell
docker compose restart app
```

### Recriar a API após alteração de código

```powershell
docker compose up -d --build app
```

### Atualizar migrations

As migrations pendentes são aplicadas automaticamente quando a API inicia.
Não edite migrations já aplicadas; crie uma nova migration numerada.

### Renomear uma casa

```powershell
docker exec -it noise_db psql -U noiseuser -d noisedb -c "UPDATE sensors SET display_name='Casa da Sueli' WHERE sensor_id='sensor_ap2';"
```

## Solução de problemas

### `HTTP=-1` no ESP32

Verifique:

- Docker está em execução;
- IP do computador está correto;
- ESP32 e computador estão na mesma rede;
- firewall permite a porta TCP `5000`;
- firmware não está usando `localhost`.

### `Wi-Fi não conectado`

Verifique o SSID, a senha e se a rede é compatível com o ESP32.

### `Timeout ou erro na leitura I2S`

Verifique a alimentação de 3,3 V e cada ligação do INMP441:
`WS`, `SD`, `SCK`, `L/R`, `GND`.

### Flutter Web bloqueado por CORS

Reconstrua a API:

```powershell
docker compose up -d --build app
```

Teste:

```powershell
curl.exe -i -H "Origin: http://localhost:56536" http://localhost:5000/api/app/overview
```

### Porta 5000 ocupada

Identifique o processo que usa a porta ou altere o mapeamento no
`docker-compose.yaml`. Se alterar a porta, atualize também o firmware e o
endereço configurado no aplicativo.

### Sensor aparece offline

O padrão é considerar offline um sensor sem leitura há mais de 60 segundos.
Verifique o Serial Monitor e o endpoint `/api/app/overview`.

## Documentação complementar

| Documento | Conteúdo |
|---|---|
| `firmware/README.md` | Instalação, pinagem e gravação do ESP32 |
| `docs/plano-projeto-dashboard-android.md` | Arquitetura, requisitos, backlog e critérios |
| `docs/relatorio-final-preparacao-hardware.md` | Preparação para hardware e instalação |
| `docs/roteiro-validacao-final.md` | Testes do servidor, sensores, Android e 24 horas |
| `projeto-1-dashboard/README.md` | Escopo do Dashboard Web |
| `projeto-2-android/README.md` | Escopo do aplicativo Android |

## Segurança e limitações

- O sistema foi projetado para rede local, não para exposição direta na
  internet.
- O arquivo `.env` não deve ser versionado.
- O endpoint de ingestão dos sensores não possui autenticação por token nesta
  versão.
- O RMS é relativo ao sensor e ao ganho do circuito.
- Não declare os níveis como decibéis sem calibração com instrumento de
  referência.
- Não há captura ou armazenamento de áudio.

## Licença

Este repositório não define uma licença de distribuição. Consulte os
responsáveis pelo projeto antes de reutilizar ou publicar o código.
