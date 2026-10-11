/*
 * Monitor de Ruído - ESP32 DevKit + INMP441
 *
 * Grave este mesmo arquivo nas quatro placas, alterando:
 * SENSOR_ID, LOCATION, WIFI_PASSWORD e SERVER_URL.
 *
 * INMP441:
 * VDD -> 3V3 | GND -> GND | WS -> GPIO25 | SD -> GPIO33
 * SCK -> GPIO26 | L/R -> GND (canal esquerdo)
 *
 * Requer o suporte "esp32 by Espressif Systems" na Arduino IDE.
 * WiFi, HTTPClient e I2S fazem parte do core ESP32.
 */

#include <Arduino.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>
#include <math.h>
#include "driver/i2s.h"

const char *WIFI_SSID = "NET_TDLL";
const char *WIFI_PASSWORD = "TROQUE_PELA_SENHA_DO_WIFI";
const char *SERVER_URL = "http://192.168.15.8:5000/api/noise";
const char *SENSOR_ID = "sensor_ap1";
const char *LOCATION = "AP1";

constexpr i2s_port_t I2S_PORT = I2S_NUM_0;
constexpr int PIN_I2S_WS = 25;
constexpr int PIN_I2S_SD = 33;
constexpr int PIN_I2S_SCK = 26;
constexpr size_t SAMPLE_COUNT = 1024;
constexpr uint32_t SEND_INTERVAL_MS = 5000;
constexpr uint32_t SEQUENCE_BLOCK_SIZE = 1000;
constexpr uint32_t I2S_READ_TIMEOUT_MS = 2000;

Preferences preferences;
uint32_t sequenceNumber = 0;
uint32_t nextSendAt = 0;

bool configureI2S() {
  const i2s_config_t config = {
      .mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_RX),
      .sample_rate = 44100,
      .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
      .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
      .communication_format = I2S_COMM_FORMAT_I2S,
      .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
      .dma_buf_count = 8,
      .dma_buf_len = 256,
      .use_apll = false,
      .tx_desc_auto_clear = false,
      .fixed_mclk = 0,
  };
  const i2s_pin_config_t pins = {
      .bck_io_num = PIN_I2S_SCK,
      .ws_io_num = PIN_I2S_WS,
      .data_out_num = I2S_PIN_NO_CHANGE,
      .data_in_num = PIN_I2S_SD,
  };
  if (i2s_driver_install(I2S_PORT, &config, 0, nullptr) != ESP_OK) {
    Serial.println("Falha ao instalar o driver I2S.");
    return false;
  }
  if (i2s_set_pin(I2S_PORT, &pins) != ESP_OK) {
    Serial.println("Falha ao configurar os pinos I2S.");
    i2s_driver_uninstall(I2S_PORT);
    return false;
  }
  i2s_zero_dma_buffer(I2S_PORT);
  return true;
}

bool readRms(float &rms) {
  int32_t samples[SAMPLE_COUNT];
  size_t bytesRead = 0;
  if (i2s_read(I2S_PORT, samples, sizeof(samples), &bytesRead,
               pdMS_TO_TICKS(I2S_READ_TIMEOUT_MS)) != ESP_OK) {
    Serial.println("Timeout ou erro na leitura I2S.");
    return false;
  }

  const size_t count = bytesRead / sizeof(int32_t);
  double sumSquares = 0.0;
  for (size_t i = 0; i < count; ++i) {
    // O INMP441 entrega 24 bits alinhados em uma palavra de 32 bits.
    const int32_t sample = samples[i] >> 8;
    sumSquares += static_cast<double>(sample) * sample;
  }
  if (count == 0) return false;
  rms = sqrt(sumSquares / count);
  return true;
}

const char *classifyNoise(float rms) {
  if (rms < 5000.0f) return "baixo";
  if (rms < 15000.0f) return "medio";
  if (rms < 30000.0f) return "alto";
  return "muito_alto";
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("Conectando ao Wi-Fi %s", WIFI_SSID);

  const uint32_t deadline = millis() + 20000;
  while (WiFi.status() != WL_CONNECTED && millis() < deadline) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi conectado. IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Wi-Fi não conectado; nova tentativa em breve.");
  }
}

void sendReading(float rms) {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  if (!http.begin(SERVER_URL)) {
    Serial.println("Endpoint inválido.");
    return;
  }
  http.setTimeout(3000);
  http.addHeader("Content-Type", "application/json");
  const String payload = String("{\"sensor_id\":\"") + SENSOR_ID
      + "\",\"location\":\"" + LOCATION
      + "\",\"rms\":" + String(rms, 2)
      + ",\"noise_level\":\"" + classifyNoise(rms)
      + "\",\"sequence\":" + String(sequenceNumber++)
      + ",\"device_uptime_ms\":" + String(millis()) + "}";
  const int status = http.POST(payload);
  Serial.printf("RMS=%.2f nivel=%s HTTP=%d\n", rms, classifyNoise(rms), status);
  if (status < 0) {
    Serial.printf("Falha HTTP: %s\n", http.errorToString(status).c_str());
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(500);
  preferences.begin("noise-monitor", false);
  const uint32_t reservedUntil = preferences.getULong("seq_end", 0);
  sequenceNumber = reservedUntil;
  preferences.putULong("seq_end", reservedUntil + SEQUENCE_BLOCK_SIZE);

  while (!configureI2S()) {
    Serial.println("I2S indisponível; nova tentativa em 5 segundos.");
    delay(5000);
  }
  connectWiFi();
  nextSendAt = millis();
}

void loop() {
  connectWiFi();
  float rms = 0.0f;
  const bool sampleReady = readRms(rms);
  if (static_cast<int32_t>(millis() - nextSendAt) >= 0) {
    if (sampleReady) {
      sendReading(rms);
    } else {
      Serial.println("Amostra descartada; nenhuma leitura falsa será enviada.");
    }
    nextSendAt = millis() + SEND_INTERVAL_MS;
  }
}
