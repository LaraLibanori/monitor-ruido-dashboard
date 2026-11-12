import main
from auth_deps import build_auth_deps
from conftest import post_reading


def test_rotas_existentes_continuam_funcionando(client):
    assert client.get("/health").json()["status"] == "ok"
    assert post_reading(client, level="baixo").status_code == 200
    overview = client.get("/api/app/overview")
    assert overview.status_code == 200
    assert {h["sensor_id"] for h in overview.json()["houses"]} == {
        "sensor_ap1", "sensor_ap2", "sensor_ap3", "sensor_ap4"}
    history = client.get("/api/app/houses/sensor_ap1/history")
    assert history.status_code == 200 and len(history.json()["buckets"]) == 24
    assert client.get("/api/app/houses/sensor_ap1/history?day=11-11-2026").status_code == 400
    assert client.get("/api/app/houses/nao_existe/history").status_code == 404
    assert client.get("/").status_code == 200
    assert client.get("/api/readings").status_code == 200
    assert client.get("/api/sensors").status_code == 200


def test_morador_ve_somente_casas_autorizadas(client, make_resident):
    ana = make_resident(sensor_ids=["sensor_ap2", "sensor_ap4"])
    houses = client.get("/api/app/overview", headers=ana["headers"]).json()["houses"]
    assert [h["sensor_id"] for h in houses] == ["sensor_ap2", "sensor_ap4"]
    assert client.get("/api/app/houses/sensor_ap2/history", headers=ana["headers"]).status_code == 200
    # Casa de outro morador: mesma resposta de casa inexistente
    assert client.get("/api/app/houses/sensor_ap1/history", headers=ana["headers"]).status_code == 404


def test_admin_ve_todas_as_casas(client, admin):
    houses = client.get("/api/app/overview", headers=admin["headers"]).json()["houses"]
    assert len(houses) == 4


def test_token_invalido_no_app_e_recusado(client):
    response = client.get("/api/app/overview", headers={"Authorization": "Bearer invalido"})
    assert response.status_code == 401


def test_app_pode_exigir_login(client):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    deps = build_auth_deps(main.auth_service, require_auth_for_app=True)
    probe = FastAPI()

    @probe.get("/probe")
    def handler(user=Depends(deps.app_user)):
        return {"user": user and user["email"]}

    assert TestClient(probe).get("/probe").status_code == 401


def test_cors_permite_authorization_para_flutter_web(client):
    preflight = client.options("/api/auth/login", headers={
        "Origin": "http://localhost:53211",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert preflight.status_code == 200
    assert "authorization" in preflight.headers["access-control-allow-headers"].lower()
