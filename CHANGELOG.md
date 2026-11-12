# Histórico de versões

Este projeto usa versionamento semântico (`MAJOR.MINOR.PATCH`) para as
entregas do sistema. Os números abaixo descrevem os marcos efetivamente
implementados no histórico do repositório; commits de checkpoint do Copilot
não são considerados versões.

## [0.6.0] - 2026-11-12

### Ocorrências e notificações

- Adicionadas ocorrências contínuas por sensor, com encerramento após o
  intervalo configurado sem leituras altas.
- Adicionada transição de advertência e candidata a multa por duração
  contínua do ruído.
- Adicionado histórico de notificações no aplicativo Flutter.
- Adicionados parâmetros `NOISE_CONTINUITY_GAP_SECONDS`,
  `NOISE_WARNING_SECONDS` e `NOISE_FINE_SECONDS`.

### Reformas e multas

- Moradores podem solicitar autorização de reforma para uma casa vinculada.
- Administradores podem aprovar, rejeitar ou cancelar solicitações.
- Ruído durante reforma aprovada fica registrado, sem escalonamento para
  advertência ou multa.
- Adicionado registro administrativo de multa com aprovação, cancelamento,
  valor, vencimento, observações e marcação como paga.
- Adicionadas abas de reformas e multas ao painel administrativo.
- A multa continua sendo apenas um registro: não há boleto ou cobrança
  financeira automática.

### Operação e apresentação

- Adicionadas as migrations `007_noise_incidents_renovations.sql` e rollback.
- Atualizado o smoke test para validar o fluxo de ocorrências contínuas.
- Adicionada apresentação visual, diagrama de arquitetura e fluxo operacional.
- Regenerados os arquivos Android necessários para o build do aplicativo.

## [0.5.2] - 2026-11-11

### Segurança e estabilidade

- Adicionado limite de tentativas de login por endereço IP, além do limite
  por combinação de IP e e-mail.
- Adicionadas poda e limitação do número de chaves mantidas pelo throttling
  em memória.
- Incluídos testes para spray de credenciais e crescimento limitado do mapa
  de falhas.

### Cliente e notificações

- O aplicativo Flutter registra tokens FCM no backend.
- O aplicativo atualiza o token quando ele muda e remove o token no logout.
- O fluxo de push continua usando modo simulado quando o Firebase não está
  configurado.

## [0.5.1] - 2026-11-11

### Autenticação e notificações

- Adicionado login do usuário no aplicativo Flutter.
- Adicionado registro de aparelhos para notificações push.
- Adicionada integração do cliente com o fluxo de sessão Bearer do backend.
- Adicionada documentação de configuração do Firebase.

## [0.5.0] - 2026-11-11

### Usuários e acesso

- Adicionados os papéis `admin` e `morador`.
- Adicionadas sessões Bearer com expiração, revogação e hash dos tokens no
  banco.
- Adicionado hash de senha com scrypt.
- Adicionados convites com validade, aceitação e definição inicial de senha.
- Adicionadas validações, auditoria e proteção contra tentativas repetidas de
  login.

### Administração

- Adicionado painel `/admin`.
- Adicionado cadastro, edição, ativação e desativação de usuários.
- Adicionada associação de moradores a sensores/casas.
- Adicionado cadastro e edição de sensores.
- Adicionada configuração persistida do horário de silêncio.
- Adicionadas consultas de auditoria, alertas, entregas e status dos
  provedores.

### Alertas

- Adicionados alertas para níveis `alto` e `muito_alto` durante o horário de
  silêncio.
- Adicionado intervalo de cooldown por sensor.
- Adicionado envio por e-mail SMTP e push FCM HTTP v1.
- Adicionados provedores de console para testes sem credenciais reais.
- Adicionado registro de cada entrega, falha, simulação ou token inválido.

### Banco, operação e validação

- Adicionada migration `006_users_and_notifications.sql` e seu rollback.
- Adicionado comando `manage.py create-admin`.
- Adicionados testes de API com PostgreSQL e smoke test Docker no CI.
- Adicionada documentação operacional de usuários e notificações.

## [0.4.0] - 2026-11-10

### Qualidade e operação

- Corrigido o fallback da conexão PostgreSQL.
- Adicionada validação contínua do backend no GitHub Actions.
- Consolidada a execução reproduzível com Docker Compose.
- Mantidos health check, migrations incrementais e validação automatizada.

## [0.3.0] - 2026-10-18

### Aplicações e documentação

- Adicionado suporte de CORS para Flutter Web em `localhost` e
  `127.0.0.1`, incluindo portas variáveis.
- Atualizado o README com arquitetura, inicialização, configuração, API,
  hardware, testes e operação.
- Documentada a validação offline do dashboard e os requisitos de hardware.

## [0.2.0] - 2026-10-11

### Dashboard e validação

- Consolidado o dashboard web offline.
- Documentado o fluxo de validação do ESP32, INMP441, rede local e API.
- Registradas as limitações que dependem de hardware físico, calibração e
  ambiente do usuário.

## [0.1.0] - 2026-10-08

### Base inicial

- Criada a estrutura inicial do Monitor de Ruído IoT.
- Definido o fluxo ESP32 + INMP441 + Wi-Fi + FastAPI + PostgreSQL.
- Criado o recebimento de leituras de ruído e a base do dashboard.

## Convenções

- `MAJOR`: mudança incompatível de API, banco ou operação.
- `MINOR`: funcionalidade nova compatível com a versão anterior.
- `PATCH`: correção, endurecimento de segurança, documentação ou ajuste
  compatível.
- A versão do projeto fica em `VERSION`.
- A versão exibida pela API em `main.py` identifica a API e pode evoluir
  separadamente do pacote completo do projeto.

## Limitações da versão atual

- SMTP real depende de `SMTP_HOST`, credenciais e remetente configurados.
- FCM real depende de uma conta de serviço Firebase montada no container.
- Convite por telefone gera um link manual; SMS e WhatsApp não estão
  integrados.
- `SECRET_KEY` deve ser definida para preservar sessões após reinícios.
- O funcionamento físico dos sensores e a calibração dos limiares RMS ainda
  dependem do ambiente instalado.
