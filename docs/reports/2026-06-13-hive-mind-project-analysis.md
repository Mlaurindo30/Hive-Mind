# Relatório Executivo e Técnico do Hive-Mind

> **Baseline pré-correções.** As lacunas abaixo foram tratadas posteriormente.
> O estado operacional atualizado está em
> `2026-06-13-auditoria-real-isolamento-hive-mind.md`.

**Data da auditoria:** 13 de junho de 2026
**Checkout:** `/home/michel/Documentos/Projects/Hive-Mind`
**Referência Git:** `HEAD 7f3b394`
**Classificação:** beta avançada / pré-produção
**Método:** código, histórico Git, bancos locais, serviços ativos e testes reais

## 1. Respostas diretas sobre instalação, atualização e OAuth

### O fluxo instala o Claude-Mem a partir do repositório?

**A intenção atual é essa, mas uma instalação limpa ainda não está garantida.**

O `install.sh`:

1. procura `claude-mem/package.json`;
2. se o diretório não existir, clona
   `https://github.com/thedotmack/claude-mem.git` com `--depth 1`;
3. entra em `claude-mem/plugin`;
4. executa `bun install --frozen-lockfile`;
5. cria uma unidade systemd que executa diretamente
   `claude-mem/plugin/scripts/worker-service.cjs`.

Evidência: `install.sh:255-307`.

Portanto, **o Claude-Mem não é instalado via `npx`** no fluxo atual. O runtime
vem de um clone local e das dependências travadas por
`claude-mem/plugin/bun.lock`.

O checkout vivo está em Claude-Mem `13.6.0`, commit
`e9ca97021475f94c468e2f9064504817856adae4`.

### A instalação completa funciona em uma máquina limpa?

**Ainda não. Há um bloqueador de ordenação.**

O worktree executa `uv sync --frozen --all-groups` em `install.sh:114-123`.
Porém, `pyproject.toml:41-43` declara Graphify e NeuralMemory como fontes
editáveis locais:

```toml
graphifyy = { path = "graphify", editable = true }
neural-memory = { path = "neural-memory", editable = true }
```

Os clones desses diretórios só ocorrem depois:

- Graphify: `install.sh:127-137`;
- NeuralMemory: `install.sh:321-331`.

Além disso, esses diretórios não são gitlinks/submodules do repositório
principal. Em um clone realmente novo eles não estarão presentes quando o
`uv sync` for executado. O instalador deve clonar/pinar os componentes antes
da sincronização Python ou usar fontes Git declaradas no lock.

### A instalação usa dependências globais?

O worktree corrigido usa `.venv` e `uv.lock` para pacotes Python
(`install.sh:114-123`, `pyproject.toml:1-43`). O runtime ativo confirma imports
na `.venv`.

Ainda existem pré-requisitos de plataforma externos ao projeto:

- `uv` e a distribuição base do Python gerenciada pelo `uv`;
- Bun em `~/.bun/bin/bun`;
- Node para detecção;
- Cargo/Rust, instalado por `rustup` quando ausente (`install.sh:356-361`);
- systemd e utilitários do sistema.

Isso não equivale a usar pacotes Python globais, mas significa que a instalação
não é inteiramente autocontida.

### Claude-Mem, Graphify, NeuralMemory e RTK atualizam automaticamente?

**Não.**

Não há timer, cron ou script de atualização de versões. O cron atual apenas
reconstrói o grafo a cada seis horas. Existem, inclusive, duas entradas
duplicadas para essa mesma tarefa.

O comportamento por componente é:

| Componente | Instalação atual | Atualização automática |
|---|---|---|
| Claude-Mem | clone raso + `bun install --frozen-lockfile` | não |
| Graphify | clone raso + fonte editável na `.venv` | não |
| NeuralMemory | clone raso + fonte editável na `.venv` | não |
| RTK | clone raso + `cargo build --release` | não |
| Python | `uv sync --frozen --all-groups` | não; reproduz o lock existente |

Reexecutar `install.sh --force` recompila RTK, mas não executa `git pull`.
Para os demais componentes, se o diretório já existe, nem sequer ocorre novo
clone. Não existe política de atualização, pin de commit upstream ou rollback.

Versões vivas:

- Claude-Mem 13.6.0;
- Graphify 0.8.16;
- NeuralMemory 4.58.0;
- RTK 0.40.0.

### O OAuth é configurado pelo `setup-brain`?

**Sim.**

O `install.sh` oferece o `setup-brain.sh` ao final quando o Dreamer ainda não
está configurado e a execução é interativa (`install.sh:626-647`). Em modo
não interativo, `--provider` e `--model` salvam apenas o papel Dreamer
(`install.sh:528-539`); credenciais continuam dependendo do `.env` ou de uma
execução posterior do Brain Selector.

O `setup-brain.py`:

- configura Dreamer, Graphify, Vision e Síntese (`setup-brain.py:64-84`);
- permite API key, OAuth ou provider local (`setup-brain.py:241-271`);
- permite trocar chave, refazer login e remover credenciais
  (`setup-brain.py:193-239`);
- descobre modelos do provider selecionado (`setup-brain.py:273-315`);
- grava credenciais, provider, modelo e fallback no `.env` do projeto.

OAuth implementado:

- Google: loopback em localhost, exige
  `GOOGLE_OAUTH_CLIENT_ID/SECRET` (`core/auth.py:38-53`,
  `core/auth.py:204-246`);
- OpenAI: device flow/Codex handshake (`core/auth.py:55-72`,
  `core/auth.py:247-282`);
- refresh automático no runtime (`core/auth.py:284-303`,
  `core/llm_client.py:231-247`).

Estado configurado, sem exposição de segredos:

| Papel | Primário | Fallback |
|---|---|---|
| Dreamer | `google/gemini-2.5-flash` | `ollama-cloud/deepseek-v4-flash` |
| Graphify | `openai/gpt-5.4-mini` | nenhum |
| Vision | `ollama/llava:7b` | `ollama/qwen3.5:9b` |
| Síntese | `google/gemini-flash-latest` | `ollama-cloud/gemma4:31b` |

Google e OpenAI possuem access/refresh token no `.env`; o teste real anterior
mostrou falha de refresh Google e ativação funcional do fallback. Logo,
“configurado” não significa “credencial atualmente válida”.

## 2. Resumo executivo e objetivo do produto

O Hive-Mind é uma infraestrutura local-first de memória coletiva para agentes.
Seu objetivo é transformar eventos, conversas, arquivos, decisões e contexto
visual em conhecimento persistente, consultável e consolidado.

O produto combina:

- Markdown/Obsidian como fonte humana canônica;
- SQLite como Unified Memory Core;
- FTS5, sqlite-vec e Graphify para recuperação;
- Claude-Mem e NeuralMemory como memórias complementares;
- Dream Cycle para redução e consolidação;
- MCP, hooks, plugin, CLI e REST como canais de acesso;
- Syncthing e exportação assinada como base de federação.

A arquitetura é ampla e tecnicamente consistente, mas a maturidade operacional
é desigual. Memória, consulta, watcher e runtime local estão funcionais. Intent
Memory, causalidade, HNSW e federação têm código e testes unitários, porém quase
nenhum estado materializado no banco vivo.

## 3. Escopo funcional e limites

### Escopo comprovado

- captura de decisões, aprendizados, prompts e observações;
- busca estrutural, textual e semântica;
- persistência em SQLite e Markdown;
- watcher de mudanças no vault;
- consolidação LLM com validação Pydantic e fallback;
- MCP com dez tools;
- API autenticada local;
- memória visual;
- exportação seletiva, redator e assinatura no nível de código;
- sincronização P2P baseada em arquivos.

### Limites observados

- o Vault é canônico, mas vários writers também escrevem diretamente no banco;
- não existe instalação limpa reproduzível validada a partir somente do Git;
- atualização de componentes não é automatizada;
- federação não possui neurônios exportáveis no estado vivo;
- não há importação federada bidirecional comprovada;
- HNSW não possui índice materializado nem neurônios marcados como indexados;
- goals e causalidade não possuem dados vivos;
- recovery não restaura efetivamente o UMC a partir de backup.

## 4. Arquitetura comprovada

### Vault e UMC

`cerebro/` é definido como fonte canônica e `hive_mind.db` como índice
reconstruível (`docs/01-architecture.md:35`). O schema inclui neurons,
synapses, observations, vault de segredos, ambiguities, FTS5, sqlite-vec,
memórias visuais, documentos e causalidade
(`core/umc_schema.sql:1-140`).

O acesso SQLite ativa foreign keys e `busy_timeout=5000`
(`core/database.py:42-57`). O schema usa WAL
(`core/umc_schema.sql:139-141`).

### Graphify

Graphify observa o vault, extrai estrutura e gera `graph.json`/HTML. O watcher
ativo executa o pacote local 0.8.16. A correção local de deleção passa caminhos
alterados à reconstrução e possui teste no repositório aninhado.

### Claude-Mem

O Claude-Mem 13.6.0 opera em `127.0.0.1:37700` com banco
`claude-mem/data/claude-mem.db`. O runtime usa o checkout local e não abre
`~/.claude-mem`.

### NeuralMemory e RTK

NeuralMemory 4.58.0 é fonte editável na `.venv`, com dados em
`neural-memory/data`. RTK 0.40.0 é compilado em
`rtk/target/release/rtk`.

### Dream Cycle e multimodal

O Dream Cycle resolve configuração por papel, valida saídas com Pydantic,
classifica falhas e usa fallback explícito. Vision e documentos possuem schema
e pipeline, mas o banco vivo tem duas memórias visuais e zero documentos.

### HM-11 e HM-12

HM-11 adicionou planner, campos de intenção, causalidade e HNSW. HM-12 adicionou
visibility, redator, assinatura e endpoint de exportação. A implementação está
presente, mas a adoção no estado vivo é mínima.

## 5. Fluxos

### Escrita

1. Agente chama MCP, hook, CLI, plugin ou REST.
2. Writers usam arquivo temporário + `os.replace`
   (`core/memory/writers.py:34-45`).
3. Watcher observa o Markdown e atualiza Graphify/UMC.
4. Claude-Mem registra prompts e sessões no banco temporal local.

### Indexação

1. Graphify gera grafo estrutural.
2. FTS5 recebe conteúdo por triggers (`core/umc_schema.sql:75-102`).
3. sqlite-vec mantém embeddings.
4. HNSW deveria indexar `indexed_at IS NULL`
   (`core/hnsw_index.py:184-210`), mas todos os 3.381 neurons permanecem com
   `indexed_at=NULL`.

### Consulta

O MCP combina backends estruturais, temporais e associativos. O contrato vivo
expõe dez tools em `scripts/sinapse-mcp.py:37-180`, retornadas por
`tools/list` em `scripts/sinapse-mcp.py:338-339`.

### Consolidação

Observações entram na fila, são destiladas, validadas, roteadas e sintetizadas.
Falha de autenticação pode acionar fallback; falha sem fallback leva à
quarentena.

### Exportação federada

O endpoint seleciona somente visibility `shared/public`
(`scripts/sinapse-api.py:261-287`), redige e opcionalmente assina. Contudo,
erros de redator ou assinatura são apenas registrados e a exportação continua
(`scripts/sinapse-api.py:293-309`). Esse comportamento é fail-open.

## 6. Stakeholders e canais

| Stakeholder | Interesse | Canal |
|---|---|---|
| Operador/proprietário | privacidade, disponibilidade, recuperação | CLI, REST, systemd |
| Claude Code e Codex | memória compartilhada e hooks | MCP, hooks |
| Hermes | contexto automático | plugin nativo |
| Outros agentes | interoperabilidade | MCP stdio, REST |
| Usuário do Obsidian | conhecimento legível/editável | Vault |
| Nós federados | sincronização e confiança | Syncthing, export Ed25519 |
| Mantenedores | evolução, testes, releases | Git, CI, lockfiles |

## 7. Requisitos

### Funcionais

- persistir e recuperar memória textual e temporal;
- consultar por FTS, vetores e grafo;
- consolidar conhecimento com proveniência;
- oferecer configuração LLM por papel;
- permitir compartilhamento seletivo e auditável.

### Técnicos

- Python 3.12 na `.venv`;
- SQLite WAL, FTS5 e sqlite-vec;
- Bun para Claude-Mem;
- Graphify/NeuralMemory locais;
- MCP JSON-RPC e FastAPI;
- lockfiles e versões reproduzíveis.

### Operacionais

- serviços idempotentes e sem instâncias duplicadas;
- health checks;
- backup e recovery real;
- atualização deliberada e reversível;
- CI equivalente ao runtime local.

### Segurança

- credenciais apenas no `.env`;
- API em localhost por padrão;
- comparação constante do token;
- dados private por padrão;
- redação fail-closed antes da exportação;
- assinatura obrigatória quando solicitada;
- permissões restritas nos bancos e chaves.

## 8. Estado atual verificado

### UMC

| Métrica | Estado vivo |
|---|---:|
| Neurônios | 3.381 |
| Sinapses | 1.762 |
| Observações UMC | 288 |
| Ambiguidades | 2 |
| Memórias visuais | 2 |
| Documentos | 0 |
| Arestas causais | 0 |
| Neurônios private | 3.381 |
| Neurônios shared/public | 0 |
| Neurônios HNSW indexados | 0 |
| Observações com `goal_id` | 0 |
| Observações com `why` | 0 |
| Tabela goals | ainda não materializada |

### Claude-Mem

| Métrica | Estado vivo |
|---|---:|
| Observações | 159 |
| Prompts | 206 |
| Resumos | 5 |
| Sessões | 26 |
| Vetores | 159 |

As métricas “228 observações” e “3.361 neurônios” do plano anterior estão
desatualizadas. Também é necessário distinguir as 288 observações do UMC das
159 observações do Claude-Mem.

### Runtime

Quatro unidades estão ativas, todas com `NRestarts=0`:

- `sinapse-claude-mem.service`;
- `sinapse-sqlite-vec.service`;
- `sinapse-graphify-watch.service`;
- `sinapse-api.service`.

As portas `37700`, `37701` e `37702` escutam somente em `127.0.0.1`.

## 9. Validação executada

Resultados do worktree instalado:

| Suíte/fluxo | Resultado |
|---|---|
| Unitários | 191 passed |
| Smoke com PATH restrito | 15 passed |
| Integração real | 33 passed, 1 skip legítimo |
| E2E | 22 passed |
| Graphify watcher | 20 passed |
| MCP Sinapse | initialize e 10 tools |
| MCP Claude-Mem | initialize e tools |
| MCP NeuralMemory | initialize, com warning async |
| REST | health 200, sem auth 401, com auth 200 |
| Dream Cycle | fallback real funcional |

A afirmação “191 testes, 0 skipped” descreve somente a suíte unitária.

O dado “29 testes de integração ignorados” também está superado no worktree:
`tests/run_all.sh:32-35` força `HIVE_RUN_INTEGRATION=1`, e
`tests/integration/conftest.py:45-53` falha a sessão se todos os testes forem
ignorados.

## 10. HEAD, worktree e runtime

### HEAD

O `HEAD` ainda contém:

- instalador com fallback para `pip --user` e Python global;
- API com host padrão `0.0.0.0`;
- runner de testes usando `python3`;
- workflow CI que instala dependências globalmente e passa flags pytest não
  registradas (`--run-integration`, `--run-e2e`).

Evidências: versão `HEAD` de `install.sh:135-152`,
`scripts/sinapse-api.py:354-360`, `tests/run_all.sh:26-29` e
`.github/workflows/test.yml:17-66`.

### Worktree

O worktree possui 49 entradas modificadas/não rastreadas. As melhorias de
isolamento, `.venv`, `uv.lock`, API localhost e integração real ainda não fazem
parte do `HEAD`.

Os repositórios aninhados também não são submodules e apresentam:

- Claude-Mem: 2 entradas;
- Graphify: 5 entradas;
- NeuralMemory: limpo;
- RTK: 2 entradas.

### Runtime

O runtime ativo usa as correções do worktree e está mais avançado que o HEAD.
Uma reinstalação a partir do Git publicado não reproduzirá automaticamente esse
estado.

## 11. Cronograma reconstruído

| Data/hora | Commit | Marco |
|---|---|---|
| 24/05 16:36 | `e3f1b2c` | busca/salvamento temporal Claude-Mem |
| 24/05 22:41 | `95c285d` | fusão paralela, Zettelkasten e API cloud |
| 09/06 18:58 | `53c0cd4` | busca híbrida |
| 10/06 18:32–21:37 | `3561117` a `e8bda39` | ambiguidades, visão, fases 7–10, testes e vault |
| 12/06 00:09 | `d6deec7` | vault, cliente LLM, MCP e testes vision |
| 12/06 19:19 | `1acc12b` | configuração LLM por papel e fallback |
| 12/06 22:44 | `06f78a1` | Sprint A/B, validators, RRF e analytics |
| 13/06 00:45 | `e1a1a51` | HM-11 |
| 13/06 01:00 | `0b3d632` | HM-12 |
| 13/06 01:58 | `f793170` | sweep documental v3 |
| 13/06 10:33–12:34 | `348bafb` a `7f3b394` | setup-brain e OAuth |
| 13/06 15:35–16:05 | worktree | isolamento real, cutover e testes |

HM-11 foi commitada 1h45 após a Sprint A/B e HM-12 somente 15 minutos depois
de HM-11. Isso é muito inferior às estimativas originais de vários dias e
explica a ausência de janela real de integração/federação.

## 12. Riscos e dependências

| Risco | Prob. | Impacto | Estado |
|---|---|---|---|
| instalação limpa falha antes de clonar fontes locais | alta | crítico | aberto |
| melhorias relevantes só no worktree | alta | alto | aberto |
| CI diverge do runtime e usa dependência global | alta | alto | aberto |
| export continua após falha de redação/assinatura | média | crítico | aberto |
| recovery não restaura UMC | alta | alto | aberto |
| componentes upstream sem pin/upgrade policy | alta | médio | aberto |
| dois crons duplicados de rebuild | alta | baixo/médio | aberto |
| Google OAuth configurado, mas refresh falha | alta | médio | mitigado por fallback |
| todos os neurons private | alta | médio | federação sem conteúdo |
| HNSW sem índice vivo | alta | médio | feature não integrada |
| Intent Memory/causalidade sem dados | alta | médio | feature não adotada |
| contrato MCP documentado como 9 tools | alta | baixo | drift documental |
| auditoria read-only move conflitos | média | alto | aberto |
| schema fragmentado por migrações tardias | média | médio | aberto |
| API exposta em `0.0.0.0` | baixa no runtime | alto | corrigido no worktree |
| integrações todas ignoradas | baixa no worktree | alto | corrigido localmente |

### Auditoria “read-only” com efeito colateral

Mesmo sem `--fix`, `audit_memory.py` cria `cerebro/conflicts/` e move arquivos
`.sync-conflict-*` para esse diretório (`scripts/audit_memory.py:146-192`).
Portanto, o modo descrito como read-only não é estritamente read-only.

### Recovery

`recover.sh` verifica/recria `graph.json`, reinicia o Claude-Mem e executa
health check (`scripts/recover.sh:11-50`). Ele não restaura `hive_mind.db`,
não aplica backup, não valida FTS/vec e não reconstrói explicitamente todo o
UMC.

### Schema fragmentado

O schema base não contém `goal_id`, `why`, `indexed_at` ou tabela `goals`.
Esses elementos são adicionados em migrações ou sob demanda
(`core/database.py:167-222`, `scripts/planner.py:93-124`). Isso dificulta
bootstrap, inspeção e compatibilidade.

## 13. Controles existentes

Controles comprovados:

- SQLite WAL e `busy_timeout`;
- foreign keys habilitadas;
- writes Markdown atômicos;
- Pydantic para outputs estruturados;
- quarentena e classificação de erros;
- Fernet para vault de segredos;
- Ed25519 e payload canônico (`core/signing.py:22-159`);
- rate limiting;
- `secrets.compare_digest` no Bearer token
  (`scripts/sinapse-api.py:154-158`);
- localhost como default no worktree
  (`scripts/sinapse-api.py:354-360`);
- visibility `private` por padrão;
- backups do cutover e permissões restritas.

## 14. Lacunas documentação x código x aceite

1. Documentação declara nove tools; o MCP oferece dez.
2. README afirma que `install.sh` “faz tudo”, mas o bootstrap limpo está com
   ordem incorreta.
3. Documentação descreve HNSW incremental, mas zero neurons foram indexados.
4. Intent Memory está documentada como entregue, mas não há goals nem
   observações associadas a goal/why.
5. Causalidade está documentada, mas existem zero arestas.
6. Federação existe como exportação unilateral; não há conteúdo exportável nem
   teste real entre duas instâncias.
7. O runtime seguro não corresponde ao HEAD.
8. A CI não reproduz `.venv`/`uv.lock` e contém flags pytest inexistentes.
9. O cron legado de seis horas permanece apesar da documentação dizer que foi
   removido em favor do watcher.
10. A exportação não cumpre fail-closed quando redator ou signing falham.

## 15. Maturidade

### Classificação

**Beta avançada / pré-produção.**

Justificativa:

- núcleo local e memória temporal operacionais;
- suíte local ampla e integrações reais aprovadas;
- isolamento de runtime comprovado;
- segurança básica consistente;
- instalação limpa, CI, recovery e federação ainda insuficientes;
- features HM-11/HM-12 presentes mais como capacidade de código do que como
  fluxo operacional materializado.

## 16. Recomendações priorizadas

### P0

1. Reordenar o instalador: clonar/pinar fontes antes de `uv sync`.
2. Versionar `pyproject.toml`, `uv.lock` e correções de runtime.
3. Refazer CI com `uv sync --frozen --all-groups` e `tests/run_all.sh`.
4. Tornar redação e assinatura fail-closed.
5. Implementar recovery real do UMC, FTS e vetores.

### P1

1. Definir manifesto de versões/commits dos quatro projetos aninhados.
2. Criar comando explícito de update com backup, teste e rollback; não usar
   atualização silenciosa automática.
3. Consolidar schema base e migrações versionadas.
4. Atualizar todos os contratos/documentos para dez tools.
5. Remover cron duplicado e reconciliar watcher versus rebuild periódico.

### P2

1. Materializar e testar Intent Memory em fluxo real.
2. Construir e validar HNSW no banco vivo.
3. Persistir relações causais reais.
4. Implementar import federado com verificação Ed25519.
5. Criar neurons `shared` de teste e validar export/import entre duas instâncias.

### P3

1. Benchmarks de latência e qualidade.
2. Métricas e observabilidade por serviço.
3. Chaos/restart/reboot tests.
4. Testes de upgrade e downgrade dos componentes aninhados.

## 17. Critérios de aceite do relatório

- Afirmações relevantes possuem referência de código/linha ou evidência de execução.
- HEAD, worktree e runtime foram tratados separadamente.
- Métricas antigas foram substituídas por contagens vivas.
- Dez tools MCP foram registradas.
- Testes unitários foram distinguidos da suíte completa.
- Funcionalidades sem dados ou fluxo real não foram classificadas como plenamente entregues.
- Stakeholders, requisitos, riscos, dependências, cronograma e marcos foram incluídos.
- Nenhum arquivo existente foi alterado por esta entrega; apenas este relatório foi criado.
