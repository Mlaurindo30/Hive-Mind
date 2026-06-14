# Auditoria Real, Isolamento e Prontidão do Hive-Mind

**Data:** 13 de junho de 2026
**Checkout:** `/home/michel/Documentos/Projects/Hive-Mind`
**Baseline Git:** `7f3b394`
**Prontidão após reboot:** **96%**
**Classificação:** apto para produção local controlada; CI remoto ainda não comprovado

## 1. Resumo executivo

O Hive-Mind foi estabilizado no runtime real e também reconstruído em um
checkout descartável sem `.venv`, `.tools` ou repositórios incorporados. O
instalador clonou commits fixos, aplicou patches versionados, criou o ambiente
Python por `uv.lock`, instalou o Claude-Mem pelo `bun.lock`, compilou RTK e
materializou FTS, sqlite-vec e HNSW.

O runtime ativo não usa `~/.claude-mem`, pacote Python global ou Bun global.
As portas `37700`, `37701` e `37702` escutam apenas em `127.0.0.1`. O
Claude-Mem executa por `.tools/bin/bun`; os serviços Python executam pela
`.venv`.

O diretório global foi removido somente após o delta final. O snapshot
auditável está em
`claude-mem/data/backups/cutover-20260613-153528/global-final.db`, com modo
`0400`, `integrity_check=ok`, 159 observações, 205 prompts, 5 resumos e 25
sessões. O arquivo completo da instalação global também foi preservado em
`global-claude-mem-final.tar.gz`, modo `0400`, com SHA-256 registrado.

## 2. Respostas sobre instalação e atualização

- O Claude-Mem é instalado do repositório fixado no manifesto, não via `npx`.
- `bun install --frozen-lockfile` instala dependências em
  `claude-mem/plugin/node_modules`.
- Graphify e NeuralMemory são fontes editáveis locais da `.venv`.
- RTK é compilado do checkout fixado; o toolchain Rust `1.95.0` pode ser
  instalado em `.tools` quando o toolchain do sistema não é funcional.
- Atualizações não são automáticas. `scripts/components.py update` faz update
  explícito, guarda o manifesto anterior e exige nova validação. Atualização
  silenciosa foi rejeitada por risco de incompatibilidade e corrupção.
- `scripts/setup-brain.sh` configura provider/modelo por papel, API key e OAuth.
  Google usa callback loopback; OpenAI usa device flow. Tokens e chaves ficam
  no `.env` do projeto.

## 3. Componentes fixados

| Componente | Versão | Commit |
|---|---:|---|
| Claude-Mem | 13.6.0 | `e9ca97021475f94c468e2f9064504817856adae4` |
| Graphify | 0.8.16 | `990ac706d823bf92275333433fde4ef4782a9139` |
| NeuralMemory | 4.58.0 | `ca6df1008e34e8af6978fd646f9b692640b4738f` |
| RTK | 0.40.0 | `805caf7d069e93370a316682b36aad59d562de2e` |

Customizações necessárias de Graphify e NeuralMemory são reaplicadas por
`patches/` e verificadas pelo manifesto.

## 4. Estado operacional observado

| Unidade | Porta | Executável | Estado |
|---|---:|---|---|
| `sinapse-claude-mem.service` | 37700 | `.tools/bin/bun` | ativo, `NRestarts=0` |
| `sinapse-sqlite-vec.service` | 37701 | `.venv/bin/python` | ativo, `NRestarts=0` |
| `sinapse-graphify-watch.service` | - | `.venv/bin/python3` | ativo, `NRestarts=0` |
| `sinapse-api.service` | 37702 | `.venv/bin/python` | ativo, `NRestarts=0` |

O PID do Claude-Mem tem `cwd` em `claude-mem/` e abre apenas
`claude-mem/data/claude-mem.db`, WAL e SHM.

## 5. Dados e índices

Estado final verificado do UMC:

| Métrica | Valor |
|---|---:|
| Neurônios | 3.384 |
| Sinapses | 1.762 |
| Observações | 311 |
| FTS | 3.384 |
| Vetores sqlite-vec | 3.384 |
| Goals | 1 |
| Arestas causais | 1 |
| Ambiguidades | 2 |

- `PRAGMA integrity_check`: `ok`
- `PRAGMA quick_check`: `ok`
- violações de chave estrangeira no UMC: `0`
- violações de chave estrangeira no Claude-Mem: `0`, após reparo de 48 sessões
  históricas ausentes sem apagar observações
- HNSW e mapa de IDs persistidos e recarregáveis

Intent Memory foi materializada com um goal real de prontidão operacional,
uma observação contendo `goal_id`, `why` e `intent_source`, dois fatos
operacionais e uma relação causal.

Após o reboot, o UMC continha 311 observações. O crescimento ocorreu por
atividade normal dos agentes; as contagens estruturais e os índices
permaneceram consistentes.

## 6. Correções críticas

1. Instalação reordenada para clonar componentes antes de `uv sync`.
2. Manifesto de commits, patches versionados, update e rollback explícitos.
3. Bun copiado para `.tools/bin`; nenhum serviço usa `~/.bun/bin`.
4. Quatro unidades systemd geradas idempotentemente por script.
5. `setup_umc.py` deixou de apagar `search_vec` durante a verificação.
6. Graphify passou a exportar todos os nós, conteúdo e vetores ao UMC.
7. HNSW passou a persistir mapa de IDs e usar o mesmo espaço FastEmbed.
8. Recovery passou a fazer backup consistente, restore atômico e rebuild.
9. Exportação federada tornou-se fail-closed para redação e assinatura.
10. Importação federada exige chave confiada, assinatura Ed25519 e namespace.
11. Neurônios federados não são retransmitidos, evitando loops.
12. Auditoria sem `--fix` não move arquivos nem escreve ambiguidades.
13. Runner de integração falha quando todos os testes são ignorados.
14. API ganhou métricas autenticadas sem expor conteúdo.
15. Contrato MCP e documentação foram alinhados para dez tools.

## 7. Testes executados

### Checkout principal

| Suíte | Resultado |
|---|---|
| Smoke com PATH restrito | 16 passed |
| Unitários | 210 passed |
| Integração real | 35 passed, 1 skip legítimo |
| E2E | 22 passed |
| Graphify watcher | 20 passed |
| NeuralMemory sandbox | 25 passed |

### Reboot real

- `boot_id` anterior: `b669eff1-746d-452f-8045-ce7ac4c28bc1`
- `boot_id` validado: `260c49ad-15cb-465b-bda7-acb5753aeff8`
- quatro serviços ativos, todos com `NRestarts=0`;
- portas `37700`, `37701` e `37702` apenas em `127.0.0.1`;
- UMC: `integrity_check=ok`, `quick_check=ok`, zero FKs inválidas;
- UMC: 3.384 neurônios, 3.384 FTS e 3.384 vetores;
- Claude-Mem: 159 observações, 159 vetores e zero FKs inválidas;
- nenhum processo do usuário referencia `~/.claude-mem`;
- smoke pós-reboot: 16 passed.

A unidade versionada `sinapse-post-reboot-validation.service` grava a
evidência em `logs/post-reboot-validation.json`. A primeira execução revelou
duas falhas no próprio validador, carregamento ausente de `sqlite-vec` e
tratamento incompleto de permissões em `/proc`; ambas foram corrigidas,
cobertas por testes e a unidade foi reexecutada com sucesso.

### Instalação limpa descartável

O checkout descartável foi criado sem os quatro componentes, `.venv`,
`.tools`, bancos ou HNSW. O bootstrap clonou e aplicou os patches, e os testes
foram executados com os serviços do checkout principal parados.

| Suíte | Resultado |
|---|---|
| Smoke | 16 passed |
| Unitários | 205 passed |
| Integração real | 34 passed, 2 skips legítimos |
| E2E | 22 passed |

### Federação em duas instâncias

- exportação assinada A → B: 1 neurônio importado e indexado;
- exportação assinada B → A: 1 neurônio importado e indexado;
- fingerprints completos conferidos contra chaves confiadas;
- adulteração rejeitada por teste;
- retransmissão de neurônio federado bloqueada.

## 8. CI, recovery e observabilidade

- GitHub Actions agora instala versões fixas de uv, Bun e Rust, executa
  bootstrap dos componentes, build do RTK, worker real e `tests/run_all.sh`.
- O push de `d1b5eb9` disparou o run remoto
  [27484471086](https://github.com/Mlaurindo30/sinapse_agent/actions/runs/27484471086).
  O GitHub não iniciou nenhuma etapa e registrou a anotação: a conta está
  bloqueada por problema de cobrança. Portanto, a CI remota permanece sem
  evidência verde por bloqueio administrativo externo, não por falha observada
  no workflow.
- Recovery possui backup SQLite consistente, manifestos, restore atômico,
  rebuild de FTS/sqlite-vec/HNSW e verificação de integridade.
- `/api/v1/metrics` exige Bearer token e publica uptime, PID, contagens,
  `quick_check`, FKs e presença dos índices.

## 9. Dependências externas remanescentes

Dependências externas ao checkout são apenas plataforma/bootstrap:

- `uv` e a distribuição Python base gerenciada por ele;
- kernel, systemd, bash, curl, Git, sqlite3 e compilador do sistema;
- registros mínimos em diretórios dos agentes apontando para o checkout.

Pacotes Python, Bun de runtime, dependências JavaScript, modelos, bancos e
executáveis RTK usados em operação ficam no projeto.

## 10. Riscos residuais

| Risco | Impacto | Situação |
|---|---|---|
| Regressão futura de boot | médio | unidade pós-reboot versionada e executada |
| Conta GitHub bloqueada por cobrança | médio | job remoto nem inicia; desbloqueio administrativo necessário |
| OAuth externo pode expirar ou ser revogado | médio | refresh e fallback testados |
| Warning Starlette/httpx | baixo | sem falha funcional |
| Update real de upstream não exercitado | médio | operação é explícita e fail-fast |

## 11. Prontidão

**96% após reboot real.**

O projeto já atende instalação reproduzível, isolamento, dados íntegros,
serviços locais, recovery, observabilidade, Intent Memory, causalidade, HNSW e
federação bidirecional. O gate local de reboot foi concluído. O percentual não
chega a 100% porque o workflow ainda precisa ficar verde no GitHub e
credenciais OAuth externas exigem validação periódica fora do controle do
checkout.
