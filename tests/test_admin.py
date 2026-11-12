import main


def test_rotas_admin_exigem_admin(client, make_resident):
    assert client.get("/api/admin/users").status_code == 401
    ana = make_resident()
    for method, url in [
        ("get", "/api/admin/users"), ("get", "/api/admin/sensors"), ("get", "/api/admin/alerts"),
        ("get", "/api/admin/audit"), ("get", "/api/admin/settings/silence"),
    ]:
        assert getattr(client, method)(url, headers=ana["headers"]).status_code == 403, url
    forbidden = client.post("/api/admin/users", headers=ana["headers"],
                            json={"name": "X", "email": "x@exemplo.com"})
    assert forbidden.status_code == 403


def test_cadastro_validacoes(client, admin, make_resident):
    make_resident()
    dup = client.post("/api/admin/users", headers=admin["headers"],
                      json={"name": "Outra", "email": "ANA@exemplo.com"})
    assert dup.status_code == 409
    bad_email = client.post("/api/admin/users", headers=admin["headers"],
                            json={"name": "Outra", "email": "sem-arroba"})
    assert bad_email.status_code == 422
    bad_sensor = client.post("/api/admin/users", headers=admin["headers"],
                             json={"name": "Outra", "email": "outra@exemplo.com", "sensor_ids": ["nao_existe"]})
    assert bad_sensor.status_code == 422
    # Nada foi criado pelas tentativas inválidas
    emails = [u["email"] for u in client.get("/api/admin/users", headers=admin["headers"]).json()]
    assert sorted(emails) == ["admin@exemplo.com", "ana@exemplo.com"]


def test_editar_associar_e_desativar_morador(client, admin, make_resident):
    ana = make_resident()
    user_id = ana["user"]["id"]
    edited = client.patch(f"/api/admin/users/{user_id}", headers=admin["headers"], json={
        "name": "Ana S. Souza", "sensor_ids": ["sensor_ap2", "sensor_ap3"],
        "notifications": {"push": False},
    })
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["name"] == "Ana S. Souza"
    assert body["sensor_ids"] == ["sensor_ap2", "sensor_ap3"]
    assert body["notifications"] == {"email": True, "push": False}

    off = client.patch(f"/api/admin/users/{user_id}", headers=admin["headers"], json={"active": False})
    assert off.json()["status"] == "inativo"
    # Sessão do morador desativado cai na hora, e o login é recusado
    assert client.get("/api/auth/me", headers=ana["headers"]).status_code == 401
    assert client.post("/api/auth/login", json={"email": "ana@exemplo.com", "password": "senha-morador-1"}).status_code == 401


def test_admin_nao_desativa_a_si_mesmo(client, admin):
    me = admin["user"]["id"]
    assert client.patch(f"/api/admin/users/{me}", headers=admin["headers"], json={"active": False}).status_code == 409
    assert client.patch(f"/api/admin/users/{me}", headers=admin["headers"], json={"role": "morador"}).status_code == 409


def test_sensores_crud_e_destinatarios(client, admin, make_resident):
    created = client.post("/api/admin/sensors", headers=admin["headers"], json={
        "sensor_id": "sensor_ap5", "location": "AP5", "display_name": "Casa da Sueli",
    })
    assert created.status_code == 201, created.text
    assert client.post("/api/admin/sensors", headers=admin["headers"],
                       json={"sensor_id": "sensor_ap5", "location": "AP5"}).status_code == 409
    assert client.post("/api/admin/sensors", headers=admin["headers"],
                       json={"sensor_id": "com espaço", "location": "AP5"}).status_code == 422

    renamed = client.patch("/api/admin/sensors/sensor_ap5", headers=admin["headers"],
                           json={"display_name": "Casa 5", "active": False})
    assert renamed.json()["display_name"] == "Casa 5" and renamed.json()["active"] is False
    assert client.patch("/api/admin/sensors/nao_existe", headers=admin["headers"],
                        json={"display_name": "x"}).status_code == 404

    make_resident(email="ana@exemplo.com", sensor_ids=["sensor_ap1"])
    make_resident(email="beto@exemplo.com", name="Beto", sensor_ids=["sensor_ap1"],
                  notifications={"email": False, "push": False})
    make_resident(email="caio@exemplo.com", name="Caio", sensor_ids=["sensor_ap1"], accept=False)
    recipients = client.get("/api/admin/sensors/sensor_ap1/recipients", headers=admin["headers"]).json()
    # Beto desligou tudo; Caio ainda não aceitou o convite
    assert [r["email"] for r in recipients] == ["ana@exemplo.com"]

    sensors = {s["sensor_id"]: s for s in client.get("/api/admin/sensors", headers=admin["headers"]).json()}
    assert set(sensors["sensor_ap1"]["residents"]) == {"Ana Souza", "Beto", "Caio"}


def test_horario_de_silencio_configuravel_e_persistido(client, admin):
    bad = client.put("/api/admin/settings/silence", headers=admin["headers"],
                     json={"weekday_start": "25:00", "weekend_start": "15:00", "end": "09:00"})
    assert bad.status_code == 422
    ok = client.put("/api/admin/settings/silence", headers=admin["headers"],
                    json={"weekday_start": "23:00", "weekend_start": "14:00", "end": "08:00"})
    assert ok.status_code == 200
    assert client.get("/api/silence-status").json()["rules"] == {"weekday": "23:00–08:00", "weekend": "14:00–08:00"}

    # Simula reinício: volta ao padrão do .env e recarrega do banco
    main.policy.update(weekday_start="22:00", weekend_start="15:00", end="09:00")
    main.auth_service.load_silence_settings()
    assert main.policy.rules()["weekday_start"] == "23:00"


def test_auditoria_registra_acoes(client, admin, make_resident):
    make_resident()
    actions = [a["action"] for a in client.get("/api/admin/audit", headers=admin["headers"]).json()]
    for expected in ("usuario_criado", "convite_emitido", "convite_aceito", "login"):
        assert expected in actions


def test_status_dos_provedores(client, admin):
    status = client.get("/api/admin/notifications/status", headers=admin["headers"]).json()
    assert status["email_real"] is False and status["push_real"] is False


def test_paginas_html(client):
    admin_page = client.get("/admin")
    assert admin_page.status_code == 200 and "Administração" in admin_page.text
    invite_page = client.get("/convite?token=abc")
    assert invite_page.status_code == 200
    assert invite_page.headers["referrer-policy"] == "no-referrer"
    presentation_page = client.get("/apresentacao")
    assert presentation_page.status_code == 200
    assert "Visão executiva" in presentation_page.text
