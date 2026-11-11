import main
from conftest import auth_header, invite_token


def test_login_e_me(client, admin):
    me = client.get("/api/auth/me", headers=admin["headers"])
    assert me.status_code == 200
    assert me.json()["role"] == "admin"
    assert me.json()["status"] == "ativo"
    assert "password_hash" not in me.json()


def test_login_senha_errada_nao_revela_motivo(client, admin):
    wrong = client.post("/api/auth/login", json={"email": "admin@exemplo.com", "password": "errada123"})
    unknown = client.post("/api/auth/login", json={"email": "ninguem@exemplo.com", "password": "errada123"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_login_bloqueia_apos_varias_falhas(client, admin):
    for _ in range(5):
        client.post("/api/auth/login", json={"email": "admin@exemplo.com", "password": "errada123"})
    blocked = client.post("/api/auth/login", json={"email": "admin@exemplo.com", "password": "senha-admin-1"})
    assert blocked.status_code == 429


def test_email_nao_diferencia_maiusculas(client, admin):
    ok = client.post("/api/auth/login", json={"email": "ADMIN@Exemplo.com", "password": "senha-admin-1"})
    assert ok.status_code == 200


def test_sem_token_e_token_invalido(client):
    assert client.get("/api/auth/me").status_code == 401
    bad = client.get("/api/auth/me", headers=auth_header("token-que-nao-existe"))
    assert bad.status_code == 401
    assert bad.headers["www-authenticate"] == "Bearer"


def test_logout_revoga_token(client, admin):
    assert client.post("/api/auth/logout", headers=admin["headers"]).status_code == 204
    assert client.get("/api/auth/me", headers=admin["headers"]).status_code == 401


def test_sessao_expirada(client, admin):
    with main.db.transaction() as cur:
        cur.execute("UPDATE user_sessions SET expires_at = NOW() - INTERVAL '1 minute'")
    assert client.get("/api/auth/me", headers=admin["headers"]).status_code == 401


def test_senha_guardada_com_hash(client, admin):
    with main.db.transaction() as cur:
        cur.execute("SELECT password_hash FROM users WHERE email = 'admin@exemplo.com'")
        stored = cur.fetchone()["password_hash"]
        cur.execute("SELECT token_hash FROM user_sessions")
        token_hash = cur.fetchone()["token_hash"]
    assert stored.startswith("scrypt$") and "senha-admin-1" not in stored
    assert admin["headers"]["Authorization"].split()[1] != token_hash


# ---------------- convites ----------------

def test_convite_completo(client, admin, outbox):
    created = client.post("/api/admin/users", headers=admin["headers"], json={
        "name": "Bruno Lima", "email": "bruno@exemplo.com", "phone": "(11) 91234-5678",
        "sensor_ids": ["sensor_ap2"],
    })
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["user"]["status"] == "convite_pendente"
    assert data["user"]["phone"] == "11912345678"
    # Sem SMTP: o envio é registrado como simulado, nunca como "sent"
    assert data["invite"]["delivery"]["status"] == "simulated"
    assert outbox["email"][0].to == "bruno@exemplo.com"
    assert data["invite"]["invite_url"] in outbox["email"][0].body

    token = invite_token(data["invite"])
    # Antes de aceitar, não consegue entrar
    assert client.post("/api/auth/login", json={"email": "bruno@exemplo.com", "password": "qualquer123"}).status_code == 401

    info = client.get(f"/api/auth/invites/{token}")
    assert info.status_code == 200 and info.json()["name"] == "Bruno Lima"

    weak = client.post("/api/auth/invites/accept", json={"token": token, "password": "123"})
    assert weak.status_code == 422

    accepted = client.post("/api/auth/invites/accept", json={"token": token, "password": "senha-bruno-1"})
    assert accepted.status_code == 200
    user = accepted.json()["user"]
    assert user["status"] == "ativo" and user["contact_verified"] is True

    again = client.post("/api/auth/invites/accept", json={"token": token, "password": "senha-bruno-2"})
    assert again.status_code == 409
    login = client.post("/api/auth/login", json={"email": "bruno@exemplo.com", "password": "senha-bruno-1"})
    assert login.status_code == 200


def test_convite_expirado(client, make_resident):
    pending = make_resident(accept=False)
    with main.db.transaction() as cur:
        cur.execute("UPDATE user_invites SET expires_at = NOW() - INTERVAL '1 minute'")
    token = invite_token(pending["invite"])
    assert client.get(f"/api/auth/invites/{token}").status_code == 410
    assert client.post("/api/auth/invites/accept", json={"token": token, "password": "senha-ana-123"}).status_code == 410


def test_reenvio_invalida_convite_anterior(client, admin, make_resident):
    pending = make_resident(accept=False)
    old_token = invite_token(pending["invite"])
    new = client.post(f"/api/admin/users/{pending['user']['id']}/invite", json={"channel": "email"},
                      headers=admin["headers"])
    assert new.status_code == 200
    assert client.get(f"/api/auth/invites/{old_token}").status_code == 404
    assert client.get(f"/api/auth/invites/{invite_token(new.json())}").status_code == 200


def test_convite_por_telefone_exige_telefone_e_nao_finge_envio(client, admin):
    no_phone = client.post("/api/admin/users", headers=admin["headers"], json={
        "name": "Caio", "email": "caio@exemplo.com", "invite_channel": "phone",
    })
    assert no_phone.status_code == 422
    with_phone = client.post("/api/admin/users", headers=admin["headers"], json={
        "name": "Caio", "email": "caio@exemplo.com", "phone": "+55 11 98888-7777", "invite_channel": "phone",
    })
    assert with_phone.status_code == 201
    delivery = with_phone.json()["invite"]["delivery"]
    assert delivery["status"] == "skipped" and delivery["provider"] == "manual"


def test_morador_desativado_nao_aceita_convite(client, admin, make_resident):
    pending = make_resident(accept=False)
    client.patch(f"/api/admin/users/{pending['user']['id']}", json={"active": False}, headers=admin["headers"])
    token = invite_token(pending["invite"])
    assert client.post("/api/auth/invites/accept", json={"token": token, "password": "senha-ana-123"}).status_code == 403


# ---------------- área do morador ----------------

def test_morador_atualiza_perfil_preferencias_e_aparelho(client, make_resident):
    ana = make_resident()
    patched = client.patch("/api/me", json={"phone": "11 97777-6666"}, headers=ana["headers"])
    assert patched.status_code == 200 and patched.json()["phone"] == "11977776666"

    prefs = client.put("/api/me/preferences", json={"email": False}, headers=ana["headers"])
    assert prefs.json() == {"email": False, "push": True}

    device = {"token": "fcm-token-" + "x" * 40, "platform": "android"}
    assert client.post("/api/me/devices", json=device, headers=ana["headers"]).status_code == 204
    assert client.get("/api/auth/me", headers=ana["headers"]).json()["devices"] == 1
    removed = client.post("/api/me/devices/remove", json={"token": device["token"]}, headers=ana["headers"])
    assert removed.status_code == 204


def test_troca_de_senha_encerra_sessoes(client, make_resident):
    ana = make_resident()
    wrong = client.post("/api/me/password", headers=ana["headers"],
                        json={"current_password": "errada-123", "new_password": "nova-senha-1"})
    assert wrong.status_code == 401
    ok = client.post("/api/me/password", headers=ana["headers"],
                     json={"current_password": "senha-morador-1", "new_password": "nova-senha-1"})
    assert ok.status_code == 204
    assert client.get("/api/auth/me", headers=ana["headers"]).status_code == 401
    assert client.post("/api/auth/login", json={"email": "ana@exemplo.com", "password": "nova-senha-1"}).status_code == 200
