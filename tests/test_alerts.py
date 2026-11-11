import main
from conftest import post_reading


def _register_device(client, user, token_suffix="a"):
    token = f"fcm-{token_suffix}-" + "x" * 40
    assert client.post("/api/me/devices", json={"token": token, "platform": "android"},
                       headers=user["headers"]).status_code == 204
    return token


def _deliveries():
    with main.db.transaction() as cur:
        cur.execute("""SELECT u.email, d.channel, d.status, d.kind FROM notification_deliveries d
                       JOIN users u ON u.id = d.user_id WHERE d.kind = 'alert' ORDER BY d.id""")
        return [dict(r) for r in cur.fetchall()]


def _events():
    with main.db.transaction() as cur:
        cur.execute("SELECT sensor_id, reading_id FROM alert_events ORDER BY id")
        return [dict(r) for r in cur.fetchall()]


def test_alerta_no_horario_de_silencio(client, make_resident, always_silence, outbox):
    ana = make_resident(sensor_ids=["sensor_ap1"])
    _register_device(client, ana)
    response = post_reading(client, level="muito_alto")
    assert response.status_code == 200

    assert len(_events()) == 1
    assert {(d["channel"], d["status"]) for d in _deliveries()} == {("push", "simulated"), ("email", "simulated")}
    push = outbox["push"][-1]
    assert push.data["sensor_id"] == "sensor_ap1"
    assert "horário de silêncio" in push.title


def test_sem_alerta_fora_do_horario_de_silencio(client, make_resident, monkeypatch):
    make_resident()
    monkeypatch.setattr(main.policy, "is_silence", lambda moment: False)
    post_reading(client, level="muito_alto")
    assert _events() == []


def test_sem_alerta_para_nivel_baixo_ou_medio(client, make_resident, always_silence):
    make_resident()
    post_reading(client, level="baixo", sequence=1)
    post_reading(client, level="medio", sequence=2)
    assert _events() == []


def test_nao_duplica_alertas(client, make_resident, always_silence):
    make_resident()
    post_reading(client, sequence=1)
    post_reading(client, sequence=1)          # reenvio do ESP32 (mesma sequência)
    post_reading(client, sequence=2)          # nova leitura dentro do intervalo mínimo
    post_reading(client, sequence=3, level="muito_alto")
    assert len(_events()) == 1
    # Reprocessar a mesma leitura também não duplica
    reading_id = _events()[0]["reading_id"]
    assert main.alert_service.process_reading(reading_id) is None
    # Um único aviso: e-mail simulado + push "skipped" (morador sem aparelho registrado)
    assert sorted((d["channel"], d["status"]) for d in _deliveries()) == [
        ("email", "simulated"), ("push", "skipped")]


def test_novo_alerta_depois_do_intervalo(client, make_resident, always_silence):
    make_resident()
    post_reading(client, sequence=1)
    with main.db.transaction() as cur:
        cur.execute("UPDATE alert_events SET created_at = created_at - INTERVAL '16 minutes'")
    post_reading(client, sequence=2)
    assert len(_events()) == 2


def test_alerta_respeita_casa_preferencias_e_inativos(client, admin, make_resident, always_silence):
    make_resident(email="ana@exemplo.com", sensor_ids=["sensor_ap1"])
    make_resident(email="beto@exemplo.com", name="Beto", sensor_ids=["sensor_ap2"])          # outra casa
    make_resident(email="caio@exemplo.com", name="Caio", sensor_ids=["sensor_ap1"],
                  notifications={"email": False, "push": True})                             # só push
    dani = make_resident(email="dani@exemplo.com", name="Dani", sensor_ids=["sensor_ap1"])
    client.patch(f"/api/admin/users/{dani['user']['id']}", json={"active": False}, headers=admin["headers"])
    make_resident(email="edu@exemplo.com", name="Edu", sensor_ids=["sensor_ap1"], accept=False)  # pendente

    post_reading(client, sensor_id="sensor_ap1")
    got = {(d["email"], d["channel"]) for d in _deliveries()}  # push sem aparelho = "skipped", mas registrado
    assert got == {("ana@exemplo.com", "push"), ("ana@exemplo.com", "email"), ("caio@exemplo.com", "push")}


def test_sensor_inativo_nao_alerta(client, admin, make_resident, always_silence):
    make_resident()
    client.patch("/api/admin/sensors/sensor_ap1", json={"active": False}, headers=admin["headers"])
    post_reading(client)
    assert _events() == []


def test_falha_no_envio_fica_registrada(client, make_resident, always_silence):
    from notifications import DeliveryResult

    class BrokenEmail:
        name = "smtp"

        def send(self, to, subject, body):
            return DeliveryResult("failed", "smtp", "SMTPAuthenticationError: senha inválida")

    main.alert_service.email = BrokenEmail()
    make_resident(notifications={"email": True, "push": False})
    response = post_reading(client)
    assert response.status_code == 200  # a leitura é salva mesmo com falha no aviso
    assert [(d["channel"], d["status"]) for d in _deliveries()] == [("email", "failed")]


def test_erro_inesperado_no_alerta_nao_derruba_leitura(client, make_resident, always_silence, monkeypatch):
    make_resident()

    def explode(*args, **kwargs):
        raise RuntimeError("provedor fora do ar")

    monkeypatch.setattr(main.alert_service.users, "recipients_for_sensor", explode)
    assert post_reading(client).status_code == 200


def test_token_fcm_invalido_e_removido(client, make_resident, always_silence):
    from notifications import DeliveryResult

    class Push:
        name = "fcm"

        def send(self, tokens, title, body, data=None):
            return DeliveryResult("failed", "fcm", "HTTP 404: UNREGISTERED", invalid_tokens=list(tokens))

    main.alert_service.push = Push()
    ana = make_resident(notifications={"email": False, "push": True})
    _register_device(client, ana)
    post_reading(client)
    assert client.get("/api/auth/me", headers=ana["headers"]).json()["devices"] == 0


def test_notificacao_de_teste_e_historico(client, admin, make_resident, always_silence):
    ana = make_resident()
    test = client.post(f"/api/admin/users/{ana['user']['id']}/notifications/test", headers=admin["headers"])
    assert test.status_code == 200
    assert {r["channel"] for r in test.json()["results"]} == {"email", "push"}

    post_reading(client)
    alerts = client.get("/api/admin/alerts", headers=admin["headers"]).json()
    assert alerts[0]["sensor_id"] == "sensor_ap1" and alerts[0]["deliveries"]

    mine = client.get("/api/me/alerts", headers=ana["headers"]).json()
    assert len(mine) == 1
    assert all(d["user_id"] == ana["user"]["id"] for d in mine[0]["deliveries"])
