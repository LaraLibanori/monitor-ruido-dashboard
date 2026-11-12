# Usuários, permissões e notificações

Guia de uso e referência da API de administração do Monitor de Ruído.

## Como funciona

```text
Sensor ESP32
  -> POST /api/noise
  -> leitura salva (horário de silêncio? nível alto/muito alto?)
  -> ocorrência contínua (leituras altas com intervalo máximo de 15 s)
  -> advertência após 2 min -> candidata a multa após 5 min
  -> moradores ativos vinculados àquela casa
  -> push (FCM) e/ou e-mail (SMTP), conforme a preferência de cada um
  -> resultado de cada envio registrado (enviado, simulado, falhou, não enviado)
  -> histórico de notificações disponível no app
```

Papéis:

| Papel | Pode |
|---|---|
| `admin` | Entrar no painel `/admin`, cadastrar/editar/desativar moradores, vincular casas, cadastrar sensores, mudar o horário de silêncio, ver alertas e auditoria. Vê todas as casas. |
| `morador` | Aceitar o convite, entrar no app, ver **somente** as casas vinculadas, ligar/desligar as próprias notificações, alterar nome/telefone e senha. |

## Passo a passo

### 1. Subir o sistema

```powershell
Copy-Item .env.example .env   # edite POSTGRES_PASSWORD e SECRET_KEY
docker compose up -d --build
```

Gere a `SECRET_KEY` com:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. Criar o primeiro administrador

```powershell
docker compose exec app python manage.py create-admin
```

O comando pergunta nome, e-mail e senha (mínimo 8 caracteres). Não existe
usuário ou senha padrão.

### 3. Entrar no painel

Abra `http://SEU-IP:5000/admin` e entre com o e-mail e a senha criados.

### 4. Cadastrar um morador e vincular a uma casa

1. Aba **Moradores** → **Cadastrar morador**.
2. Informe nome, e-mail e, se quiser, telefone.
3. Marque as casas/sensores que a pessoa pode ver.
4. Escolha os canais de alerta: push, e-mail ou ambos.
5. Salve. O painel mostra o **link de convite** (válido por 72 horas).

Com SMTP configurado, o convite segue por e-mail. Sem SMTP, o painel avisa
que o e-mail **não** foi enviado e você compartilha o link (WhatsApp, por
exemplo). Convite por telefone é sempre compartilhado manualmente: o sistema
não envia SMS.

### 5. O morador aceita o convite

O morador abre o link, cria a senha e passa a ter acesso. O contato usado no
convite fica marcado como confirmado. Depois, ele entra no aplicativo com
e-mail e senha; o app registra o aparelho para receber push.

### 6. Testar uma notificação

No painel, botão **Testar alerta** na linha do morador. O resultado mostra o
que aconteceu em cada canal. Para simular um alerta real:

```cmd
curl.exe -X POST "http://localhost:5000/api/noise" -H "Content-Type: application/json" -d "{\"sensor_id\":\"sensor_ap1\",\"location\":\"AP1\",\"rms\":25000,\"noise_level\":\"muito_alto\",\"sequence\":900001,\"device_uptime_ms\":1000}"
```

O alerta só é criado se o momento estiver dentro do horário de silêncio
(aba **Horário de silêncio**). O resultado aparece na aba **Alertas**.

## Configurar e-mail e push

## Fluxo operacional completo

1. O sensor envia uma leitura a cada aproximadamente 5 segundos.
2. Leituras `alto` ou `muito_alto` durante o silêncio iniciam ou continuam uma
   ocorrência. Se não houver leitura alta por 15 segundos, a ocorrência é
   encerrada e uma nova sequência começa separadamente.
3. Após 2 minutos contínuos, o sistema registra uma advertência e envia pelos
   canais ativados do morador.
4. Após 5 minutos contínuos, registra uma ocorrência candidata a multa e envia
   nova notificação. A multa não é aplicada automaticamente: o administrador
   precisa revisar a ocorrência e definir valor, vencimento e aprovação conforme
   o regulamento do condomínio.
5. O morador vê as notificações no ícone de sino do app, com canal, status e
   ocorrência relacionada.
6. Para uma reforma, o morador solicita sensor, período e descrição. O
   administrador aprova ou rejeita em `/api/admin/renovations`. Durante uma
   autorização aprovada, o ruído é registrado, mas não gera escalonamento para
   multa.

As durações são configuráveis por `NOISE_WARNING_SECONDS`,
`NOISE_FINE_SECONDS` e `NOISE_CONTINUITY_GAP_SECONDS`. O padrão é 120, 300 e
15 segundos.

### Sem credenciais (modo simulado)

É o padrão. Tudo funciona, mas nenhum e-mail ou push sai de verdade: cada
envio fica registrado como **simulado** e aparece no log do servidor
(`docker compose logs -f app`). O painel mostra um aviso enquanto algum canal
estiver nesse modo. Serve para testar o fluxo completo sem contas externas.

### E-mail real (SMTP)

No `.env`:

```env
SMTP_HOST=smtp.seuprovedor.com
SMTP_PORT=587
SMTP_USER=usuario
SMTP_PASSWORD=senha-ou-senha-de-app
SMTP_FROM=Monitor de Ruído <alertas@seudominio.com>
```

Porta 587 usa STARTTLS; porta 465 usa SSL. No Gmail é preciso uma
"senha de app". Depois: `docker compose up -d app`.

### Push real (Firebase Cloud Messaging)

1. Crie um projeto em <https://console.firebase.google.com>.
2. **Configurações do projeto → Contas de serviço → Gerar nova chave privada**.
3. Salve o arquivo como `secrets/firebase.json` (a pasta não vai para o Git).
4. No `.env`: `FCM_CREDENTIALS_PATH=/run/secrets/firebase.json`
5. `docker compose up -d app`
6. No app Flutter, adicione o `google-services.json` (Android) e o
   `GoogleService-Info.plist` (iOS) do mesmo projeto — veja o README do app.

### O que exige credenciais reais

| Item | Sem credenciais | Com credenciais |
|---|---|---|
| Login, convites, permissões, alertas, histórico | Funciona | Funciona |
| E-mail de convite e de alerta | Simulado (link aparece no painel) | Enviado por SMTP |
| Push no celular | Simulado | Enviado pelo FCM |

## Variáveis de ambiente

| Variável | Obrigatória | Padrão | Para quê |
|---|---|---|---|
| `POSTGRES_PASSWORD` | Sim | — | Senha do banco |
| `SECRET_KEY` | Sim, em uso real | chave temporária | Protege tokens; sem ela as sessões caem a cada reinício |
| `SESSION_TTL_HOURS` | Não | 12 | Validade do login |
| `INVITE_TTL_HOURS` | Não | 72 | Validade do convite |
| `APP_REQUIRE_AUTH` | Não | false | `true` = app só mostra casas após login |
| `PUBLIC_BASE_URL` | Não | endereço do painel | Endereço usado nos links de convite |
| `NOISE_CONTINUITY_GAP_SECONDS` | Não | 15 | Intervalo máximo entre leituras para manter a mesma ocorrência |
| `NOISE_WARNING_SECONDS` | Não | 120 | Tempo contínuo até a advertência |
| `NOISE_FINE_SECONDS` | Não | 300 | Tempo contínuo até a candidata a multa |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Só para e-mail real | — | Provedor de e-mail |
| `FCM_CREDENTIALS_PATH` | Só para push real | — | Conta de serviço do Firebase |

## Rotas

Autenticação: `Authorization: Bearer <token>` (token devolvido no login).
Documentação interativa: `http://SEU-IP:5000/docs`.

### Acesso

| Método | Rota | Quem | O que faz |
|---|---|---|---|
| POST | `/api/auth/login` | público | Entra com e-mail e senha; devolve token |
| POST | `/api/auth/logout` | logado | Revoga o token |
| GET | `/api/auth/me` | logado | Dados do usuário e validade da sessão |
| GET | `/api/auth/invites/{token}` | público | Dados do convite |
| POST | `/api/auth/invites/accept` | público | Aceita o convite e cria a senha |

### Morador (o próprio usuário)

| Método | Rota | O que faz |
|---|---|---|
| PATCH | `/api/me` | Altera nome/telefone |
| POST | `/api/me/password` | Troca a senha (encerra as sessões) |
| GET / PUT | `/api/me/preferences` | Liga/desliga e-mail e push |
| POST | `/api/me/devices` | Registra o token FCM do aparelho |
| POST | `/api/me/devices/remove` | Remove o token (logout) |
| GET | `/api/me/alerts` | Alertas das casas autorizadas |
| POST | `/api/me/notifications/test` | Envia um teste para si |
| GET | `/api/me/notifications` | Histórico de notificações recebidas |
| GET / POST | `/api/me/renovations` | Lista / solicita autorização de reforma |

### Administrador

| Método | Rota | O que faz |
|---|---|---|
| GET / POST | `/api/admin/users` | Lista / cadastra e convida |
| GET / PATCH | `/api/admin/users/{id}` | Detalha / edita, desativa, vincula casas |
| POST | `/api/admin/users/{id}/invite` | Novo convite (o anterior deixa de valer) |
| POST | `/api/admin/users/{id}/notifications/test` | Notificação de teste |
| GET / POST | `/api/admin/sensors` | Lista / cadastra sensor |
| PATCH | `/api/admin/sensors/{sensor_id}` | Renomeia, ativa/desativa |
| GET | `/api/admin/sensors/{sensor_id}/recipients` | Quem recebe alertas da casa |
| GET / PUT | `/api/admin/settings/silence` | Horário de silêncio |
| GET | `/api/admin/alerts` | Alertas e resultado dos envios |
| GET | `/api/admin/deliveries` | Últimos envios (alertas, convites, testes) |
| GET | `/api/admin/notifications/status` | Provedores em uso |
| GET | `/api/admin/audit` | Auditoria |
| GET / PATCH | `/api/admin/renovations` | Lista / aprova ou rejeita reformas |
| GET / PATCH | `/api/admin/fines` | Lista / aprova, cancela ou marca multas como pagas |

### Aplicativo

`GET /api/app/overview` e `GET /api/app/houses/{sensor_id}/history`
continuam iguais. Com token de morador, devolvem apenas as casas vinculadas;
com token de administrador, todas. Sem token, continuam abertas na rede
local, a não ser que `APP_REQUIRE_AUTH=true`.

## Segurança

- Senhas guardadas com hash scrypt e sal aleatório.
- Tokens de sessão e de convite ficam no banco apenas como HMAC-SHA256.
- Bloqueio temporário após 5 senhas erradas seguidas.
- Desativar um usuário encerra as sessões dele na hora.
- Ações administrativas ficam na auditoria.
- **Ainda em HTTP.** Fora da rede local é obrigatório colocar HTTPS na frente
  (proxy reverso com certificado) antes de expor o sistema.
- `POST /api/noise`, `/api/readings`, `/api/sensors` e o painel de leituras
  `/` continuam sem login, como antes, para os ESP32 e a rede local.
- A candidata a multa é apenas um registro para decisão administrativa; não há
  cobrança, boleto ou integração financeira automática.

## Testes

```powershell
python -m pip install -r requirements-dev.txt
$env:TEST_DATABASE_URL = "postgresql://noiseuser:SUA-SENHA@localhost:5432/noisedb_test"
python -m pytest -q
```

Os testes recriam o banco `noisedb_test` a cada execução e usam os provedores
simulados. Smoke test contra o sistema rodando:

```powershell
python scripts/smoke_test.py http://localhost:5000 admin@exemplo.com SENHA
```

O smoke test cria um morador `smoke-...@exemplo.com` e o desativa ao final.

## Reverter a migração

```powershell
Get-Content migrations/rollback/006_users_and_notifications.down.sql | docker compose exec -T db psql -U noiseuser -d noisedb
```

Apaga usuários, convites, alertas e auditoria; leituras e sensores ficam.
