#!/usr/bin/env bash
# Monitor de Ruído - iniciar o servidor (Linux / macOS)
# Uso:  ./iniciar.sh
set -e
cd "$(dirname "$0")"

if ! docker version >/dev/null 2>&1; then
  echo "[ERRO] O Docker não está rodando. Abra o Docker e tente de novo."; exit 1
fi
[ -f .env ] || { cp .env.example .env; echo "Arquivo .env criado a partir do .env.example."; }

echo "Subindo o sistema (na primeira vez demora alguns minutos)..."
docker compose up -d --build

echo
echo "Sistema no ar! Painel: http://localhost:5000"
echo "No APLICATIVO do celular, digite um destes endereços:"
if command -v hostname >/dev/null && hostname -I >/dev/null 2>&1; then
  for ip in $(hostname -I); do echo "   $ip"; done
else
  ipconfig getifaddr en0 2>/dev/null || echo "   (descubra o IP do computador nas configurações de rede)"
fi
echo "O celular precisa estar no MESMO Wi-Fi deste computador."
