# Publicação dos projetos separados no GitHub

## Separação definida

### Repositório 1 — Dashboard

Nome sugerido:

```text
monitor-ruido-dashboard
```

Conteúdo:

```text
projeto-1-dashboard/
templates/
main.py
database.py
app_routes.py
app_service.py
silence_policy.py
init.sql
migrations/
Dockerfile
docker-compose.yaml
requirements.txt
iniciar.bat
liberar_firewall.bat
README.md
```

### Repositório 2 — Android

Nome sugerido:

```text
monitor-ruido-android
```

Conteúdo:

```text
app/
projeto-2-android/
README.md
docs/plano-projeto-dashboard-android.md
```

## Publicação local

Depois de criar os dois repositórios vazios no GitHub, execute no PowerShell.
Os comandos abaixo devem ser executados a partir de cópias separadas do
projeto, para que cada repositório contenha somente seu produto.

```powershell
git init
git add .
git commit -m "Inicializa projeto do dashboard"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/monitor-ruido-dashboard.git
git push -u origin main
```

Para o aplicativo:

```powershell
git init
git add .
git commit -m "Inicializa aplicativo Android"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/monitor-ruido-android.git
git push -u origin main
```

## Observação operacional

Os dois produtos dependem do mesmo contrato de API. O endpoint do servidor
deve permanecer compatível:

```text
GET /api/app/overview
GET /api/app/houses/{sensor_id}/history
```

O firmware dos ESP32 permanece no projeto do servidor/infraestrutura ou deve
ser publicado em um terceiro repositório específico, pois não pertence ao
código de interface do dashboard nem ao código Flutter.
