# Firmware dos nós ESP32

## Instalação

1. Instale a [Arduino IDE](https://www.arduino.cc/en/software).
2. Em **Preferences > Additional Boards Manager URLs**, adicione:
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
3. No **Boards Manager**, instale **esp32 by Espressif Systems**.
4. Selecione **ESP32 Dev Module**, a porta USB e abra `esp32_noise_monitor.ino`.

## Ligações

| INMP441 | ESP32 |
|---|---|
| VDD | 3V3 |
| GND | GND |
| WS | GPIO 25 |
| SD | GPIO 33 |
| SCK | GPIO 26 |
| L/R | GND |

Use apenas **3,3 V** no INMP441.

## Configuração das quatro placas

No começo do arquivo, informe a senha do Wi-Fi e o IPv4 do computador que
executa o Docker:

```cpp
const char *WIFI_PASSWORD = "senha_do_wifi";
const char *SERVER_URL = "http://192.168.15.8:5000/api/noise";
```

Grave uma placa por vez com estes valores:

| Placa | `SENSOR_ID` | `LOCATION` |
|---|---|---|
| 1 | `sensor_ap1` | `AP1` |
| 2 | `sensor_ap2` | `AP2` |
| 3 | `sensor_ap3` | `AP3` |
| 4 | `sensor_ap4` | `AP4` |

O computador e os ESP32 devem estar na mesma rede Wi-Fi. O IP da URL é o IP
do computador, não o IP do celular.

O firmware reserva blocos de sequências na memória flash usando `Preferences`.
Assim, depois de desligar e ligar a placa, o contador não volta para zero e
as leituras continuam sendo aceitas pela deduplicação do banco.

## Teste

Abra o Serial Monitor em **115200 baud**. A placa deve mostrar o próprio IP e
imprimir `HTTP=200` aproximadamente a cada 5 segundos. Teste o servidor no
navegador por `http://IP_DO_COMPUTADOR:5000/health`.

Se aparecer `HTTP=-1`, confira o IP, o Docker e o firewall do Windows.
Os limiares RMS (`5000`, `15000`, `30000`) seguem o material fornecido e
devem ser calibrados no ambiente real, porque dependem do ganho e da posição
do microfone.

Após gravar, faça este teste em cada placa:

1. Confirme o IP no Serial Monitor.
2. Confirme pelo menos três respostas `HTTP=200`.
3. Desligue e ligue a placa.
4. Confirme que novas respostas `HTTP=200` continuam ocorrendo.
