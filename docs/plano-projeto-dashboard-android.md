# Plano de Projeto — Dashboard Web e Aplicativo Android

**Produto:** Monitor de Ruído IoT  
**Versão do documento:** 1.0  
**Data:** 08/10/2026  
**Escopo de conectividade:** rede local, sem cloud  
**Público:** equipe de produto, desenvolvimento, testes, implantação e operação

---

## 1. Visão do produto

O sistema monitora o nível relativo de ruído em quatro pontos usando ESP32 e
microfones digitais INMP441. Cada placa calcula o RMS localmente e envia uma
leitura numérica ao computador servidor por Wi-Fi. O servidor armazena os dados
no PostgreSQL e disponibiliza as informações para:

1. **Dashboard Web**, usado no computador servidor;
2. **Aplicativo Android**, usado em celulares conectados à mesma rede local.

O sistema não grava, transmite ou armazena áudio. Ele trabalha somente com
valores agregados de intensidade sonora.

## 2. Decisões de produto

| Decisão | Definição |
|---|---|
| Conectividade | Somente rede local |
| Servidor | Computador local com Docker Desktop |
| API | FastAPI |
| Banco | PostgreSQL |
| Nós IoT | ESP32 DevKit + INMP441 |
| Comunicação ESP32 → servidor | HTTP POST/JSON |
| Atualização do dashboard | Automática |
| Atualização do aplicativo | Automática e manual |
| Métrica | RMS relativo |
| Áudio | Não capturado nem armazenado |
| Quantidade inicial | 4 sensores |

## 3. Arquitetura geral

```text
┌──────────────┐    I2S     ┌──────────────┐
│   INMP441    │ ──────────> │    ESP32     │
└──────────────┘             │ RMS + Wi-Fi  │
                             └──────┬───────┘
                                    │ HTTP POST /api/noise
                                    ▼
                             ┌──────────────┐
                             │ FastAPI      │
                             │ validação    │
                             │ regras       │
                             └──────┬───────┘
                                    ▼
                             ┌──────────────┐
                             │ PostgreSQL   │
                             └──────┬───────┘
                                    │ REST/JSON
                         ┌──────────┴──────────┐
                         ▼                     ▼
                  ┌──────────────┐      ┌──────────────┐
                  │ Dashboard Web│      │ Android App  │
                  └──────────────┘      └──────────────┘
```

## 4. Contrato de dados da API

### 4.1 Envio de leitura pelo ESP32

`POST /api/noise`

```json
{
  "sensor_id": "sensor_ap1",
  "location": "AP1",
  "rms": 12345.67,
  "noise_level": "medio",
  "sequence": 152,
  "device_uptime_ms": 754321
}
```

Regras:

- `sensor_id`: obrigatório, não vazio;
- `location`: obrigatório;
- `rms`: número maior ou igual a zero;
- `noise_level`: `baixo`, `medio`, `alto` ou `muito_alto`;
- `sequence`: inteiro não negativo;
- `device_uptime_ms`: inteiro não negativo.

### 4.2 Saúde do serviço

`GET /health`

```json
{
  "status": "ok",
  "total_readings": 1234
}
```

### 4.3 Visão geral para o aplicativo

`GET /api/app/overview`

O endpoint entrega o estado do horário de silêncio e uma entrada por sensor,
incluindo última leitura, estado online/offline e resumo do dia.

### 4.4 Histórico por sensor

`GET /api/app/houses/{sensor_id}/history`

Entrega 24 blocos horários, resumo de leituras, quantidade de ocorrências
ruidosas e ocorrências durante o horário de silêncio.

## 5. Identidade dos sensores

| Sensor | `sensor_id` | Local inicial | Nome apresentado |
|---|---|---|---|
| 1 | `sensor_ap1` | AP1 | Casa 1 |
| 2 | `sensor_ap2` | AP2 | Casa 2 |
| 3 | `sensor_ap3` | AP3 | Casa 3 |
| 4 | `sensor_ap4` | AP4 | Casa 4 |

O nome exibido poderá ser alterado no cadastro do banco sem mudar o firmware.

---

# Projeto 1 — Dashboard Web

## 6. Objetivo

Entregar uma tela web operacional para o responsável acompanhar os quatro
sensores em tempo real no computador que executa o servidor.

O dashboard atual já possui uma base visual funcional em
`templates/index.html`, com tema escuro, indicadores, alerta de silêncio,
tabela e gráfico. O trabalho do Projeto 1 é transformar essa base em uma
interface operacional validada, responsiva e coerente com os endpoints atuais.

## 7. Usuário principal

### Operador/responsável pelo local

Precisa responder rapidamente:

- O servidor está funcionando?
- Quais sensores estão online?
- Qual sensor está com nível alto?
- O ruído está ocorrendo durante o horário de silêncio?
- Qual foi o histórico recente?
- Há falha de comunicação?

## 8. Escopo funcional do dashboard

### P0 — obrigatório

1. Exibir o status geral do sistema.
2. Exibir o horário local e o estado do silêncio.
3. Exibir os quatro sensores cadastrados.
4. Exibir status online/offline por sensor.
5. Exibir RMS e nível atual.
6. Exibir horário da última leitura.
7. Destacar ruído alto durante o silêncio.
8. Atualizar os dados automaticamente.
9. Exibir mensagem clara quando a API ou o banco estiver indisponível.
10. Exibir histórico recente por sensor.

### P1 — importante

1. Filtro por sensor.
2. Filtro por nível de ruído.
3. Seleção de período.
4. Gráfico de RMS ao longo do tempo.
5. Gráfico de distribuição por nível.
6. Indicador de taxa de leituras.
7. Indicador de última comunicação.
8. Tabela de últimas leituras.
9. Exportação CSV.

### P2 — evolução

1. Tela de configuração de nomes das casas.
2. Ativação/desativação de sensores.
3. Tela de diagnóstico do sistema.
4. Retenção e limpeza de dados.
5. Impressão de relatório.

## 9. Componentes visuais

### Cabeçalho

- nome do sistema;
- indicador da API;
- relógio local;
- botão de atualização;
- identificação do horário de silêncio.

### Resumo geral

Cards com:

- sensores online;
- sensores offline;
- casas em nível alto;
- ocorrências no silêncio;
- total de leituras no período.

### Cards dos sensores

Cada card deve apresentar:

- nome da casa;
- local;
- sensor ID;
- ponto de estado;
- nível textual;
- RMS;
- última leitura;
- indicação de ocorrência no silêncio.

### Área de gráficos

- RMS por tempo;
- níveis por sensor;
- volume de ocorrências;
- faixas do horário de silêncio.

### Tabela de leituras

Colunas mínimas:

- data/hora;
- sensor;
- local;
- RMS;
- nível;
- silêncio ativo;
- IP de origem.

## 10. Requisitos não funcionais do dashboard

- funcionar em Chrome e Edge atuais;
- funcionar em resolução de notebook;
- ser utilizável em tela de celular como painel secundário;
- não depender de internet para consultar a API local;
- apresentar estado de carregamento;
- apresentar estado sem dados;
- apresentar estado de erro;
- não apagar os últimos dados exibidos quando ocorrer falha temporária;
- não recarregar a página inteira a cada atualização;
- evitar chamadas concorrentes desnecessárias;
- tratar dados ausentes sem quebrar o JavaScript.

## 11. Critérios de aceite do Projeto 1

O dashboard será aprovado quando:

- carregar em `http://localhost:5000`;
- mostrar o estado do servidor;
- mostrar os quatro sensores cadastrados;
- atualizar uma leitura recebida em até 10 segundos;
- marcar um sensor como offline após o tempo configurado;
- destacar nível `alto` ou `muito_alto` no horário de silêncio;
- continuar exibindo o último estado conhecido durante uma falha breve;
- exibir mensagem recuperável quando a API estiver indisponível;
- não apresentar erro de JavaScript no console durante o uso normal;
- funcionar sem chamadas externas obrigatórias em runtime, exceto recursos
  visuais que forem deliberadamente empacotados localmente.

## 12. Plano de implementação do Projeto 1

### Entrega D1 — contrato e estados

- mapear todos os endpoints usados;
- definir modelos JavaScript;
- definir estados `loading`, `ready`, `empty`, `stale` e `error`;
- definir regras de cores;
- definir intervalo de atualização.

### Entrega D2 — painel operacional

- consolidar cabeçalho;
- consolidar cards;
- consolidar alerta de silêncio;
- consolidar tabela;
- validar atualização automática.

### Entrega D3 — gráficos e histórico

- gráfico de RMS;
- seleção de sensor;
- histórico recente;
- tratamento de ausência de dados.

### Entrega D4 — diagnóstico e acabamento

- status da API;
- status do banco;
- mensagens operacionais;
- responsividade;
- revisão visual;
- testes de navegador.

---

# Projeto 2 — Aplicativo Android

## 13. Objetivo

Entregar um aplicativo Android simples, legível e orientado a usuários não
técnicos, permitindo acompanhar as casas pelo celular na mesma rede local.

O aplicativo atual já possui a base Flutter em `app/`, com telas de conexão,
visão geral, histórico e ajuda. O trabalho do Projeto 2 é concluir a experiência
e validar o comportamento em aparelho Android real.

## 14. Usuário principal

### Morador/responsável

Precisa responder pelo celular:

- o sistema está conectado?
- há ruído alto agora?
- em qual casa?
- o ruído ocorre no horário de silêncio?
- como foi o comportamento durante o dia?

## 15. Escopo funcional do aplicativo

### P0 — obrigatório

1. Tela de conexão ao servidor local.
2. Validação real da conexão antes de salvar.
3. Salvamento do endereço do servidor.
4. Tela inicial com todas as casas.
5. Estado online/offline por casa.
6. Nível atual e linguagem simples.
7. Alerta durante horário de silêncio.
8. Atualização automática.
9. Tela de histórico por casa.
10. Tela de ajuda.
11. Tratamento de erro de rede.
12. Funcionamento com zero, dois ou quatro sensores.

### P1 — importante

1. Botão de atualização manual.
2. Indicador de última atualização.
3. Exibição do RMS para usuários avançados.
4. Seleção de dia no histórico.
5. Configuração do intervalo de atualização.
6. Tela de diagnóstico da conexão local.

### P2 — evolução

1. Notificação local de ruído durante o silêncio.
2. Exportação de histórico.
3. Tema claro/escuro.
4. Compartilhamento de relatório.
5. Leitura por QR Code do endereço do servidor.

## 16. Fluxo principal do aplicativo

```text
Abrir app
   ↓
Existe servidor salvo?
   ├── Não → Tela de conexão
   └── Sim → Tentar overview
                  ├── Sucesso → Tela inicial
                  └── Falha → Tela de erro + trocar endereço
```

### Tela de conexão

Deve aceitar:

```text
192.168.15.8
192.168.15.8:5000
http://192.168.15.8:5000
```

O app deve normalizar o endereço e adicionar a porta 5000 quando ausente.

### Tela inicial

Deve apresentar:

- status do horário de silêncio;
- resumo do prédio;
- cards das casas;
- indicador de sincronização;
- botão de ajuda;
- botão para trocar servidor.

### Tela da casa

Deve apresentar:

- status atual;
- nível em linguagem simples;
- indicador de alerta;
- gráfico de 24 horas;
- resumo diário;
- hora mais agitada;
- quantidade de leituras;
- leituras no horário de silêncio.

## 17. Linguagem do usuário

| Nível técnico | Texto do aplicativo |
|---|---|
| `baixo` | Tranquilo |
| `medio` | Movimento normal |
| `alto` | Barulhento |
| `muito_alto` | Muito alto |
| sem leitura | Sem sinal |

O aplicativo deve explicar que os níveis são uma referência relativa e não uma
medição oficial em decibéis.

## 18. Requisitos não funcionais do aplicativo

- Flutter estável compatível com o `pubspec.yaml`;
- Android com HTTP local habilitado;
- mensagens em português do Brasil;
- acessibilidade visual mínima;
- textos legíveis em telas pequenas;
- não travar sem internet externa;
- não perder o último endereço salvo;
- não apresentar tela vazia sem explicação;
- impedir chamadas duplicadas enquanto uma chamada está em andamento;
- cancelar timers ao destruir a tela;
- não exibir stack trace para o usuário.

## 19. Critérios de aceite do Projeto 2

O aplicativo será aprovado quando:

- instalar em aparelho Android real;
- abrir corretamente na primeira execução;
- aceitar o IP do computador;
- testar o servidor antes de salvar;
- exibir as quatro casas;
- atualizar os dados sem fechar a tela;
- mostrar sensor offline de forma clara;
- abrir o histórico de cada casa;
- funcionar com histórico vazio;
- tratar servidor desligado;
- preservar os últimos dados durante erro temporário;
- exibir corretamente acentos e caracteres em português;
- não apresentar erro de layout em telas comuns;
- passar os testes Flutter disponíveis.

## 20. Plano de implementação do Projeto 2

### Entrega A1 — conexão

- revisar normalização de URL;
- validar endereço inválido;
- melhorar mensagens de rede;
- testar HTTP local;
- testar servidor desligado e religado.

### Entrega A2 — experiência principal

- validar resumo geral;
- validar cards;
- validar estados de nível;
- validar atualização automática;
- validar estado sem sensores.

### Entrega A3 — histórico

- validar gráfico;
- validar 24 horas;
- validar dia sem dados;
- validar resumo;
- validar atualização da casa.

### Entrega A4 — release Android

- revisar manifesto;
- gerar APK release;
- instalar em aparelho físico;
- testar Wi-Fi local;
- documentar instalação;
- executar checklist de aceite.

---

## 21. Dependências entre os projetos

| Dependência | Impacto |
|---|---|
| API `/api/app/overview` | Dashboard e Android |
| API `/api/app/houses/{id}/history` | Histórico do dashboard e Android |
| Campo `is_silence_period` | Alertas e relatórios |
| Cadastro de sensores | Cards e lista de casas |
| Timezone configurado | Datas, horários e histórico |
| `OFFLINE_AFTER_SECONDS` | Estado offline nas duas interfaces |
| Contrato de níveis | Cores e textos nas duas interfaces |

O contrato da API deve ser tratado como uma interface compartilhada. Qualquer
mudança deve atualizar simultaneamente:

1. backend;
2. dashboard;
3. aplicativo;
4. testes;
5. documentação.

## 22. Estratégia de testes integrada

### Cenário 1 — operação normal

1. Subir Docker.
2. Confirmar `/health`.
3. Ligar quatro ESP32.
4. Confirmar leituras no banco.
5. Abrir dashboard.
6. Abrir aplicativo.
7. Conferir os quatro sensores.

### Cenário 2 — sensor offline

1. Desligar um ESP32.
2. Aguardar `OFFLINE_AFTER_SECONDS`.
3. Confirmar estado offline no dashboard.
4. Confirmar estado offline no Android.
5. Confirmar preservação da última leitura.

### Cenário 3 — horário de silêncio

1. Configurar horário de teste curto.
2. Enviar leitura `alto`.
3. Confirmar `is_silence_period`.
4. Confirmar alerta no dashboard.
5. Confirmar alerta no aplicativo.

### Cenário 4 — falha do servidor

1. Desligar o container da API.
2. Confirmar mensagem de erro.
3. Confirmar que as telas não travam.
4. Religar o container.
5. Confirmar recuperação automática.

## 23. Backlog inicial priorizado

### Dashboard

| ID | Item | Prioridade |
|---|---|---|
| DASH-001 | Consolidar estados de carregamento e erro | P0 |
| DASH-002 | Exibir status dos quatro sensores | P0 |
| DASH-003 | Exibir alerta de silêncio | P0 |
| DASH-004 | Atualizar dados sem recarregar a página | P0 |
| DASH-005 | Exibir histórico por sensor | P0 |
| DASH-006 | Melhorar responsividade | P1 |
| DASH-007 | Adicionar filtros de período e sensor | P1 |
| DASH-008 | Adicionar exportação CSV | P2 |

### Android

| ID | Item | Prioridade |
|---|---|---|
| APP-001 | Validar conexão local | P0 |
| APP-002 | Exibir overview das casas | P0 |
| APP-003 | Exibir status offline | P0 |
| APP-004 | Exibir alerta de silêncio | P0 |
| APP-005 | Exibir histórico de 24 horas | P0 |
| APP-006 | Validar mensagens de erro | P0 |
| APP-007 | Gerar APK release | P0 |
| APP-008 | Adicionar seleção de dia | P1 |
| APP-009 | Adicionar notificações locais | P2 |

## 24. Riscos e controles

| Risco | Controle |
|---|---|
| IP do computador mudar | Reserva DHCP no roteador |
| Firewall bloquear porta 5000 | Script de liberação e diagnóstico |
| Wi-Fi de convidados isolar dispositivos | Usar rede privada principal |
| Limiares RMS inadequados | Calibração física documentada |
| API mudar sem atualizar clientes | Contrato versionado e testes |
| Banco não iniciar | Healthcheck e logs Docker |
| Sensor perder Wi-Fi | Reconexão automática no firmware |
| App perder conexão | Último estado + mensagem recuperável |
| Dependência externa do dashboard | Preferir recursos locais em produção |

## 25. Definição de pronto

Um item só será considerado pronto quando:

- estiver implementado;
- estiver integrado ao contrato da API;
- tiver tratamento de erro;
- tiver teste correspondente;
- estiver documentado quando necessário;
- tiver sido validado no fluxo real;
- não quebrar dashboard, Android ou firmware.

O produto completo só será liberado após o teste integrado dos quatro sensores
e a validação em aparelho Android real.

## 26. Ordem de execução recomendada

1. Congelar o contrato da API.
2. Finalizar o dashboard operacional.
3. Validar o dashboard com leituras reais.
4. Finalizar a conexão e overview do Android.
5. Finalizar histórico e estados offline do Android.
6. Gerar APK release.
7. Executar testes integrados.
8. Realizar calibração dos sensores.
9. Documentar instalação e operação.
10. Liberar a versão de campo.

