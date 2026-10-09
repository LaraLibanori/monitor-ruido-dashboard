# Projeto 1 — Dashboard Web

Este diretório identifica o produto Dashboard Web do Monitor de Ruído IoT.

## Código de execução

O dashboard é servido pelo backend local:

```text
templates/index.html
```

O servidor FastAPI, o banco PostgreSQL e o ambiente Docker ficam na raiz do
projeto porque são compartilhados pelo dashboard, pelo aplicativo Android e
pelos ESP32.

## Executar

Na raiz do projeto:

```text
iniciar.bat
```

Depois abra:

```text
http://localhost:5000
```

## Funcionalidades

- monitoramento dos sensores;
- leitura RMS;
- classificação do ruído;
- estado online/offline;
- alerta de horário de silêncio;
- tabela de leituras;
- gráficos;
- atualização automática;
- histórico por sensor.

## APIs consumidas

- `GET /health`
- `GET /api/readings`
- `GET /api/sensors`
- `GET /api/rate-status`
- `GET /api/silence-status`

## Critério de aceite

O dashboard deve abrir sem erro, mostrar os quatro sensores, atualizar leituras
reais e indicar um sensor como offline depois do tempo configurado em
`OFFLINE_AFTER_SECONDS`.
