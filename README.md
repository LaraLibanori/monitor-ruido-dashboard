# 📡 Monitor de Ruído — v5 (servidor + app Android)

## ⚡ Guia rápido

**Hardware (cada ESP32):**
1. Conecte o INMP441 conforme `firmware/README.md`.
2. Abra `firmware/esp32_noise_monitor.ino` na Arduino IDE.
3. Configure Wi-Fi, o IP do computador e o par `SENSOR_ID`/`LOCATION`.
4. Grave o arquivo nas quatro placas, usando `sensor_ap1` até `sensor_ap4`.

**Computador (servidor):**
1. Abra o **Docker Desktop** e espere "Engine running".
2. Dê dois cliques em **`iniciar.bat`**. Ele cria o `.env` se precisar, sobe tudo e mostra o endereço para o app.
3. Na primeira vez, se o celular não conectar: botão direito em **`liberar_firewall.bat`** → *Executar como administrador*.

**Celular:**
1. Instale o APK (veja `app/README.md` — dá para gerar pelo GitHub sem instalar nada).
2. Abra o app e digite o endereço que o `iniciar.bat` mostrou (ex.: `192.168.0.10`).

Pronto. Painel web continua em `http://localhost:5000`.

## Documento de projeto

O plano completo dos dois produtos de interface está em:

`docs/plano-projeto-dashboard-android.md`

Ele separa o trabalho em:

- **Projeto 1 — Dashboard Web**
- **Projeto 2 — Aplicativo Android**

e registra arquitetura, requisitos, backlog, critérios de aceite, testes,
dependências e riscos.

Depois de iniciar o servidor, confirme no computador:

```
http://localhost:5000/health
```

O resultado esperado é um JSON com `"status": "ok"`. Para os ESP32, use o
IPv4 mostrado pelo `iniciar.bat`, por exemplo:

```
http://192.168.15.8:5000/api/noise
```

Não use `localhost` na configuração do ESP32: para a placa, `localhost` é a
própria placa.

**Nomes das casas:** o app mostra "Casa 1", "Casa 2"... na ordem dos sensores. Para dar outro nome:
```
docker exec -it noise_db psql -U noiseuser -d noisedb -c "UPDATE sensors SET display_name='Casa da Sueli' WHERE sensor_id='sensor_ap2';"
```

**Atualizações do banco** (pasta `migrations/`) são aplicadas sozinhas quando o sistema liga.

---

# 📘 Guia detalhado de instalação (Windows)

> Esse guia foi feito para quem **nunca usou Docker antes**. Siga passo a passo com calma!

---

## 🧰 O que você vai precisar instalar

### Docker Desktop

O Docker é o programa que vai rodar o sistema. Pense nele como uma "caixinha" que contém tudo que o projeto precisa para funcionar, sem precisar instalar mais nada.

**Como instalar:**

1. Acesse: **https://www.docker.com/products/docker-desktop**
2. Clique em **"Download for Windows"**
3. Abra o instalador baixado e clique em **Next** em tudo
4. Quando terminar, **reinicie o computador**
5. Abra o **Docker Desktop** pela área de trabalho

> ✅ Você saberá que está funcionando quando aparecer uma barrinha verde no canto inferior esquerdo do Docker Desktop escrito **"Engine running"**

---

## 📁 Organizando os arquivos do projeto

Crie uma pasta em qualquer lugar do seu computador — por exemplo na Área de Trabalho — e chame de `noise-monitor`.

Coloque todos os arquivos dentro dela exatamente assim:

```
noise-monitor/
├── docker-compose.yaml
├── Dockerfile
├── init.sql
├── .env                ← você vai criar esse (veja abaixo)
├── requirements.txt
├── main.py
├── database.py
├── silence_policy.py   ← regras da lei do silêncio
├── app_service.py      ← monta as respostas do app
├── app_routes.py       ← rotas do app (/api/app/...)
├── migrations/         ← atualizações automáticas do banco
├── iniciar.bat
├── liberar_firewall.bat
├── app/                ← aplicativo Android (Flutter)
└── templates/
    └── index.html
```

> ⚠️ A pasta `templates` precisa estar dentro de `noise-monitor`, e o `index.html` precisa estar dentro de `templates`.

---

## ⚙️ Criando o arquivo `.env`

Esse arquivo guarda as configurações do banco de dados. Você precisa criar ele do zero.

1. Abra o **Bloco de Notas** (pesquise "Bloco de Notas" no menu Iniciar)
2. Cole esse conteúdo:

```
POSTGRES_DB=noisedb
POSTGRES_USER=noiseuser
POSTGRES_PASSWORD=MinhaSenh@2025

RATE_LIMIT_MAX=100
RATE_LIMIT_WINDOW=60

APP_TIMEZONE=America/Sao_Paulo
SILENCE_START_WEEKDAY=22:00
SILENCE_START_WEEKEND=15:00
SILENCE_END=09:00
```

> 💡 Existe um modelo pronto no arquivo `.env.example`. As quatro linhas do silêncio são opcionais: se não existirem, o sistema usa a convenção do Ed. Letícia (seg–sex 22h–9h, sáb–dom 15h–9h).

3. Clique em **Arquivo → Salvar como**
4. Navegue até a pasta `noise-monitor`
5. No campo **"Nome do arquivo"** digite: `.env`
6. No campo **"Tipo"** selecione: **Todos os arquivos (\*.\*)**
7. Clique em **Salvar**

> ⚠️ Se salvar como `.env.txt` não vai funcionar! Confira se o nome está exatamente `.env`

---

## 🚀 Rodando o projeto

### Passo 1 — Abra o terminal na pasta do projeto

1. Abra o **Explorador de Arquivos**
2. Navegue até a pasta `noise-monitor`
3. Clique na **barra de endereço** (onde aparece o caminho, tipo `C:\Users\...`)
4. Digite `cmd` e aperte **Enter**

Um terminal preto vai abrir já dentro da pasta certa.

### Passo 2 — Suba o projeto

No terminal, digite exatamente esse comando e aperte **Enter**:

```
docker compose up -d --build
```

> ⏳ Na **primeira vez** vai demorar alguns minutos — ele está baixando e configurando tudo. É normal aparecer várias linhas passando na tela.

Quando o cursor voltar, você pode fechar o terminal. O sistema continuará rodando em segundo plano.

### Passo 3 — Verifique no Docker Desktop

Abra o **Docker Desktop**. Você vai ver algo assim:

```
noise-monitor
  ├── noise_db    ✅ Running
  └── noise_app   ✅ Running
```

Se os dois estiverem com ícone verde e escrito **Running**, está tudo funcionando! 🎉

---

## 🌐 Acessando o dashboard

Abra o navegador e acesse:

```
http://localhost:5000
```

O painel de monitoramento de ruído vai aparecer.

---

## ▶️ Ligar e desligar o sistema

Pelo **Docker Desktop** você não precisa mais abrir terminal nenhum:

| O que fazer | Como fazer no Docker Desktop |
|---|---|
| **Ligar** | Clique no botão ▶️ ao lado de `noise-monitor` |
| **Desligar** | Clique no botão ⏹️ ao lado de `noise-monitor` |
| **Ver erros** | Clique em `noise_app` e depois em **Logs** |

---

## ❓ Problemas comuns

**O Docker Desktop não abre ou dá erro na instalação**
→ Verifique se o Windows está atualizado. O Docker precisa do Windows 10 versão 2004 ou mais recente.

**Aparece erro "port 5000 already in use"**
→ Algum outro programa está usando a porta 5000. Reinicie o computador e tente de novo.

**O `noise_app` aparece como "Restarting" no Docker Desktop**
→ Clique nele, vá em **Logs** e veja a mensagem de erro.

**Salvei o `.env` como `.env.txt` sem querer**
→ Delete o arquivo errado, crie novamente seguindo o passo acima, e depois clique em **Restart** no `noise-monitor` dentro do Docker Desktop.

---

## 📌 Resumo rápido

```
1. Instalar o Docker Desktop
2. Colocar os arquivos na pasta noise-monitor
3. Criar o arquivo .env
4. Abrir cmd na pasta → rodar: docker compose up -d --build
5. Abrir o navegador em: http://localhost:5000
```

---

*Qualquer dúvida é só perguntar! 😊*
