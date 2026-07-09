# Captura Universal de Providers - Design

**Data:** 2026-07-09

**Status:** aprovado

## Objetivo

Fazer o Hive-Mind capturar prompts e eventos em tempo real de todos os providers suportados, inclusive no Windows, sem exigir a execucao manual de scripts e sem depender da abertura previa do Claude Code. O mecanismo universal deve ser instalado para todos os providers conhecidos, detectar os providers presentes na maquina e ativar somente os encontrados.

## Escopo

O desenho cobre Claude Code, Codex, Antigravity Desktop, Antigravity CLI, Gemini CLI, Copilot, Roo, Kilo, Kimi, Hermes, Mimo, OpenClaw e SwarmClaw. Providers futuros entram pelo mesmo contrato declarativo.

O trabalho inclui:

- inicializacao automatica no logon do usuario no Windows;
- transporte nativo para Windows, Linux e macOS;
- hooks gerenciados onde o provider oferece uma interface de hooks;
- observacao de JSONL, arquivos reescritos e SQLite/WAL onde hooks nao existem;
- fila persistente e reenvio quando o Claude-Mem estiver indisponivel;
- deteccao, saude e teste sintetico por provider;
- validacao e recuperacao da `.venv` durante a instalacao.

Nao faz parte do escopo modificar binarios fechados, injetar codigo em processos de terceiros ou inventar hooks para interfaces que nao os oferecem.

## Decisao Arquitetural

A captura sera hibrida. Cada provider declara a melhor fonte disponivel, nesta ordem de preferencia:

1. `native_hook`;
2. `managed_hook`;
3. notificacao de filesystem do sistema operacional;
4. observacao incremental de SQLite/WAL;
5. polling limitado;
6. importacao historica manual.

Hooks nativos ou gerenciados fornecem a menor latencia. Watchers e polling simulam o mesmo contrato de eventos para providers que nao oferecem hooks, sem alterar seus binarios ou formatos internos.

## Contrato de Evento

Todas as fontes produzem um `ProviderEvent` com os seguintes campos:

```text
provider: str
session_id: str
event_id: str
event_type: session_start | prompt | tool_use | tool_result | assistant | session_end
occurred_at: str
project: str | null
cwd: str | null
content: str
metadata: dict
```

A identidade de deduplicacao sera calculada a partir de `provider + session_id + event_id + content_hash`. Eventos sem identificador nativo recebem um identificador deterministico derivado da origem, posicao e conteudo.

## Componentes

### ProviderRegistry

Catalogo declarativo de providers. Cada entrada informa detector, fontes disponiveis, parser, transportes permitidos, prioridade e requisitos opcionais. Um provider conhecido mas ausente fica `inactive` e nao consome recursos.

### ProviderDetector

Detecta um provider por executavel, configuracao e diretorios com dados validos. A mera existencia de um diretorio vazio nao ativa captura.

### EventSource

Interface comum para hook, filesystem, SQLite/WAL e polling. Cada implementacao apenas detecta e extrai eventos; nao chama Claude-Mem nem modelos.

### EventNormalizer

Converte a saida especifica de cada parser para `ProviderEvent`, aplica limites, redacao de segredos e validacao de esquema.

### CaptureQueue

Fila SQLite persistente dentro do projeto, com estados `pending`, `delivered`, `retry` e `dead_letter`. A gravacao na fila e a fronteira de durabilidade: depois dela, o processo do provider pode encerrar sem perder o evento.

### ClaudeMemSink

Unico componente autorizado a chamar os endpoints de sessao do Claude-Mem. Entrega eventos em ordem por sessao, confirma sucesso antes de marcar `delivered` e usa backoff limitado para falhas transitorias.

### CaptureSupervisor

Detecta providers, inicia fontes, reinicia fontes com falha, drena a fila e publica saude. Ele e o unico dono do servico de captura.

### HookInstaller

Instala hooks somente em providers com contrato oficial ou configuracao suportada. Cada hook executa uma entrada rapida, le JSON pelo stdin, grava na fila e retorna sem aguardar Claude-Mem, Ollama ou geracao de observacoes.

### StartupRegistrar

No Windows, registra uma tarefa no logon do usuario apontando para um script PowerShell sob a raiz do Hive-Mind. A tarefa inicia o supervisor e nao referencia worktrees, `.gemini` ou caminhos temporarios. Linux continua com `systemd --user`; macOS continua com `launchd`.

## Ciclo de Vida no Windows

```text
Logon do usuario
  -> tarefa Hive-Mind
  -> script PowerShell em G:\Hive-Mind
  -> supervisor
  -> Claude-Mem worker
  -> Universal Capture Service
  -> deteccao de providers
  -> fontes ativas
  -> normalizacao
  -> fila persistente
  -> Claude-Mem
```

O MCP nao inicia o capturador como processo filho. Isso evita duplicacao, processos orfaos e dependencia do primeiro agente aberto.

Se o Claude-Mem ainda nao estiver saudavel, a captura continua gravando na fila. O sink drena os eventos quando o worker retornar.

## Matriz Inicial de Providers

| Provider | Fonte primaria | Fallback |
|---|---|---|
| Claude Code | hooks nativos Claude-Mem | importacao de transcript |
| Codex | hooks gerenciados | `rollout-*.jsonl` |
| Antigravity Desktop | `transcript_full.jsonl` | polling Windows |
| Antigravity CLI | `transcript_full.jsonl` | polling |
| Gemini CLI | integracao Claude-Mem | importacao de transcript |
| Copilot | transcript ou extensao | polling de workspace |
| Roo | arquivo ou SQLite/WAL | polling |
| Kilo | SQLite/WAL | polling |
| Kimi | `context.jsonl` | polling |
| Hermes | hook/plugin | `state.db` |
| Mimo | SQLite/WAL | polling |
| OpenClaw | hook/plugin quando disponivel | SQLite |
| SwarmClaw | SQLite/WAL | polling |

## Parsers

Parsers devem retornar todos os prompts ainda presentes na origem, nao apenas o ultimo. O estado de entrega e responsabilidade da fila e da deduplicacao, nao do parser.

Parsers de fontes reescritas devem tolerar linhas incompletas durante escrita e tentar novamente sem marcar o evento como entregue. Parsers SQLite devem abrir conexoes somente leitura, respeitar WAL e usar cursores incrementais quando o esquema permitir.

## Confiabilidade e Erros

Nao havera `except: pass` no caminho de captura. Cada provider expoe:

- estado `inactive`, `watching`, `degraded` ou `failed`;
- transporte ativo;
- ultima deteccao;
- ultima entrega;
- quantidade pendente;
- erro mais recente;
- reinicializacoes;
- resultado do ultimo teste sintetico.

Um provider com falha nao bloqueia outros providers. Falhas transitorias usam backoff. Eventos que excederem o limite de tentativas vao para `dead_letter`, permanecendo inspecionaveis e reprocessaveis.

## Privacidade e Limites

Antes da fila, o normalizador aplica:

- limite configuravel de tamanho por evento;
- redacao de tokens, chaves, cabecalhos de autorizacao e valores de `.env`;
- exclusao configuravel de providers, projetos e tipos de evento;
- permissoes de arquivo restritas ao usuario atual.

## Instalacao e Ambiente Python

O projeto exige `Python >=3.12,<3.13`. O instalador usa `uv python install 3.12`
quando nao houver um interpretador compativel e cria a `.venv` com `uv venv
--python 3.12`. Ele nao depende do Python 3.12 estar previamente instalado no
Windows nem do launcher `py` possuir essa versao.

Uma `.venv` cujo executavel existe mas aponta para um Python removido e considerada invalida. O instalador apresenta diagnostico claro e a reconstrui de forma controlada, preservando `.env`, dados e configuracoes.

O runtime e os scripts permanecem direcionados para a raiz escolhida pelo usuario, por exemplo `G:\Hive-Mind`.
Nesta maquina, a raiz canonica e `G:\Hive-Mind`; em uma instalacao nova, o
registrador persiste a raiz resolvida pelo instalador em vez de assumir uma
unidade ou pasta fixa.

## Metas de Latencia

- hook: persistencia local em ate 500 ms;
- notificacao de arquivo ou SQLite: ate 2 segundos;
- polling de fallback: ate 5 segundos;
- zero perda durante reinicio do Claude-Mem;
- zero duplicacao apos reprocessamento.

## Criterios de Aceite

Um provider so e `healthy` apos um teste ponta a ponta:

1. produzir um prompt sintetico com identificador unico;
2. detectar o evento na fonte selecionada;
3. normalizar para `ProviderEvent`;
4. persistir na fila;
5. entregar ao Claude-Mem;
6. localizar o identificador pela busca temporal;
7. reiniciar o servico e comprovar ausencia de duplicacao;
8. interromper Claude-Mem, produzir outro evento, restaurar o worker e comprovar entrega posterior.

A validacao global inclui:

- instalacao limpa em Windows sem Python 3.12 previamente instalado, com
  provisionamento automatico da versao compativel pelo `uv`;
- inicio automatico apos logoff e logon reais;
- Antigravity Desktop capturando todos os `USER_INPUT` da sessao;
- Codex e Claude Code mantendo seus hooks e fallbacks;
- provider quebrado sem degradar os demais;
- saude exibindo fonte, atraso, fila e ultimo erro por provider.

## Fases

1. Corrigir validacao da `.venv`, supervisor e inicio automatico.
2. Introduzir `ProviderEvent`, fila persistente e sink.
3. Separar os transportes multiplataforma do parser.
4. Corrigir Antigravity Desktop e Codex.
5. Implementar hooks gerenciados.
6. Migrar os demais adapters.
7. Adicionar diagnostico e testes sinteticos por provider.
8. Executar instalacao limpa, reinicio e validacao ponta a ponta.
