# =============================================
# smoke_test.py - Testa o sistema rodando de verdade (Docker ou local)
# =============================================
# Uso:
#   python scripts/smoke_test.py http://localhost:5000 admin@exemplo.com senha-do-admin
# Percorre: health, painel, login, cadastro de morador, convite, permissões,
# leitura de sensor, alerta e histórico. Só usa a biblioteca padrão.
# Cria um morador de teste (smoke-...@exemplo.com) e o desativa no final.
# =============================================

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def call(base, method, path, body=None, token=None, expect=200):
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    if status != expect:
        raise SystemExit(f"FALHOU {method} {path}: esperado {expect}, veio {status}: {raw[:300]!r}")
    print(f"ok  {method:5} {path.split('?')[0]} -> {status}")
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return raw.decode(errors="replace")


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__ or "uso: smoke_test.py URL EMAIL SENHA")
    base, email, password = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
    stamp = int(time.time())

    call(base, "GET", "/health")
    call(base, "GET", "/")
    call(base, "GET", "/admin")
    call(base, "GET", "/api/app/overview")
    call(base, "GET", "/api/app/houses/sensor_ap1/history")
    call(base, "GET", "/api/admin/users", expect=401)

    admin = call(base, "POST", "/api/auth/login", {"email": email, "password": password})["token"]
    status = call(base, "GET", "/api/admin/notifications/status", token=admin)
    print(f"    provedores: e-mail={status['email']} push={status['push']}")

    created = call(base, "POST", "/api/admin/users", {
        "name": "Morador Smoke", "email": f"smoke-{stamp}@exemplo.com", "sensor_ids": ["sensor_ap1"],
    }, token=admin, expect=201)
    invite_token = urllib.parse.parse_qs(urllib.parse.urlparse(created["invite"]["invite_url"]).query)["token"][0]
    call(base, "GET", f"/convite?token={invite_token}")
    resident = call(base, "POST", "/api/auth/invites/accept",
                    {"token": invite_token, "password": f"smoke-{stamp}-senha"})["token"]

    houses = call(base, "GET", "/api/app/overview", token=resident)["houses"]
    assert [h["sensor_id"] for h in houses] == ["sensor_ap1"], houses
    call(base, "GET", "/api/app/houses/sensor_ap2/history", token=resident, expect=404)
    call(base, "GET", "/api/admin/users", token=resident, expect=403)
    call(base, "POST", "/api/me/devices", {"token": f"smoke-device-{stamp}-{'x' * 30}", "platform": "android"},
         token=resident, expect=204)

    # Força "sempre silêncio" para o alerta ser determinístico, e restaura depois
    rules = call(base, "GET", "/api/admin/settings/silence", token=admin)
    call(base, "PUT", "/api/admin/settings/silence",
         {"weekday_start": "00:00", "weekend_start": "00:00", "end": "00:00"}, token=admin)
    try:
        call(base, "POST", "/api/noise", {
            "sensor_id": "sensor_ap1", "location": "AP1", "rms": 25000.0,
            "noise_level": "muito_alto", "sequence": stamp, "device_uptime_ms": 1,
        })
        for _ in range(20):
            alerts = call(base, "GET", "/api/me/alerts", token=resident)
            if alerts and alerts[0]["deliveries"]:
                break
            time.sleep(0.5)
        else:
            raise SystemExit("FALHOU: o alerta não foi gerado.")
        for delivery in alerts[0]["deliveries"]:
            print(f"    alerta -> {delivery['channel']}: {delivery['status']} ({delivery['provider']})")
    finally:
        call(base, "PUT", "/api/admin/settings/silence",
             {k: rules[k] for k in ("weekday_start", "weekend_start", "end")}, token=admin)
        call(base, "PATCH", f"/api/admin/users/{created['user']['id']}", {"active": False}, token=admin)

    call(base, "GET", "/api/auth/me", token=resident, expect=401)  # desativado perde a sessão
    call(base, "POST", "/api/auth/logout", token=admin, expect=204)
    print("\nSMOKE TEST OK")


if __name__ == "__main__":
    main()
