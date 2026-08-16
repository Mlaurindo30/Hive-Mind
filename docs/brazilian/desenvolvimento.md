# Desenvolvimento

Como alterar o Hive-Mind, testar, construir e publicar releases.

Público-alvo: quem contribui código ou documentação.

---

## Como alterar

1. **Consulte antes de agir.** Leia o estado atual do projeto (`sinapse_query`,
   ou ) antes de tocar em algo que já pode
   ter decisão registrada.
2. **Localize o dono da área.** Cada área tem um único responsável — veja a
   matriz [alteração → documentação](#matriz-alteração--documentação).
3. **Faça a mudança no código primeiro**, depois a documentação, **na mesma
   entrega**. Um comportamento novo sem documento atualizado não está pronto
   (regra 7 de manutenção — ver [README.md](README.md#regras-de-manutenção)).
4. **Rode os testes** da camada correspondente antes de declarar concluído
   (ver [Testes](#testes)).
5. **Registre o que é reutilizável** (decisão ou aprendizado) no cérebro, com
   evidência do que foi verificado.

---

## Matriz alteração → documentação

| Alteração | Documentação obrigatória |
|---|---|
| CLI nativo `hive-mind` | [cli.md](cli.md), [README.md](README.md) |
| Registro MCP de agentes | [agentes.md](agentes.md) |
| Provider de captura / identidade de projeto | [captura.md](captura.md), [capture/providers.md](capture/providers.md) |
| Daemon / manifesto de serviços | [runtime.md](runtime.md), runbook de operações |
| Banco / schema | [pipeline-dados.md](pipeline-dados.md), notas de migração |
| Modelos de IA / Model Gateway | [modelos-ia.md](modelos-ia.md), [modelos-ia.md](modelos-ia.md) |
| Dream Cycle | [pipeline-dados.md](pipeline-dados.md) |
| Instalação | [instalacao.md](instalacao.md) (e variantes por plataforma) |
| Health / doctor / observabilidade | [observabilidade.md](observabilidade.md) |
| Segurança | [seguranca.md](seguranca.md) |
| Release | [CHANGELOG.md](../CHANGELOG.md), release notes |

Toda entrega que altera comportamento em uma dessas áreas só pode ser
considerada concluída com a documentação correspondente atualizada na mesma
entrega.

---

## Testes

Antes de qualquer commit:

```bash
./tests/run_all.sh                    # suíte completa (Smoke → Unit → Integration → E2E)
bash tests/smoke/test_smoke.sh        # mínimo aceitável se a suíte for longa
```

| Nível | Comando | Requisitos | Nota |
|---|---|---|---|
| Smoke | `bash tests/smoke/test_smoke.sh` | binários no PATH | diagnóstico rápido (< 5 min) |
| Unit | `uv run pytest tests/unit/ -v` | pytest, Python 3.12 | mocks; **não chama LLM real** |
| Integration | `HIVE_RUN_INTEGRATION=1 uv run pytest tests/integration/ -v` | backends reais | gate explícito via env |
| E2E | `uv run pytest tests/e2e/ -v` | sistema completo | ciclo completo de sessão |
| Real (K9) | `./tests/run_real_knowledge.sh` | ambiente real | suíte de conhecimento separada |
| npm | `npm test` (em `npm/`) | Node 18+ | `node --test test/doctor.test.js test/supervisor.test.js` |

- **Unit não chama LLM real.** A lógica em torno do LLM é testada com dados
  determinísticos; o modelo real só entra em `tests/test_synthesis.py` e nos
  fluxos E2E.
- **Contagem de testes:** a suíte cresce rápido — não trate um número fixo como
  meta. Meça com
  `rg -n "^\s*(async\s+def|def)\s+test_" tests | wc -l` (funções) e
  `rg -l "^\s*(async\s+def|def)\s+test_" tests | wc -l` (arquivos).
- **Skips nomeados "service-offline"** indicam estado `degraded`, não sucesso
  pleno.

### Contratos de CI

- `python scripts/release/validate_package.py --source-root .` valida o
  contrato de versão de release (ver [Release](#release)) — roda no workflow
  Windows (`.github/workflows/test-windows.yml`).
- Contrato de restart policy do Docker:
  `tests/unit/test_compose_restart_policy.py` falha se algum serviço de compose
  obrigatório não declarar `restart: unless-stopped`.

---

## Build

O projeto é um pacote Python gerenciado por `uv` + `hatchling`, com um pacote
npm separado em `npm/`.

```bash
uv sync                      # ambiente reproduzível (.venv + uv.lock), inclui grupo dev
uv sync --extra reranker     # + dependência opcional do reranker cross-encoder
uv build                     # gera sdist + wheel em dist/
```

- Python: `>=3.12,<3.13` (definido em `pyproject.toml`).
- O pacote expõe os entrypoints `hive-mind` (`hive_mind.cli:main`) e
  `hive-mindd` (`hive_mind.daemon.main:main`), além dos gui-scripts do Windows.
- O build do wheel inclui recursos (`src/hive_mind/resources/`) e **exclui**
  segredos e estado: `.env`, `.env.*`, `*.secret`, `hive_mind.db`,
  `hive_mind.db-*`, `logs/`, `backups/`, `config/keys/` (ver `[tool.hatch.build]`).

---

## Release

O contrato de versão exige que **sete locais** concordem com a mesma versão
semântica e que ela **não regrida** abaixo da última tag git. O validador é
`scripts/release/validate_package.py`.

| Local | Campo |
|---|---|
| `pyproject.toml` | `[project] version` |
| `npm/package.json` | `version` |
| `core/version.py` | `__version__` |
| `scripts/services/sinapse-api.py` | `version="..."` |
| `scripts/services/sinapse_mcp.py` | `"serverInfo": {..., "version": "..."}` |
| `core/telemetry.py` | `"service.version": "..."` |
| `CHANGELOG.md` | `## Unreleased ... vX.Y.Z` |

Sequência de release:

1. **Bump de versão** nos sete locais acima, todos para a mesma versão.
2. **Changelog**: escreva a entrada `## Unreleased ... vX.Y.Z` no topo do
   [`CHANGELOG.md`](../CHANGELOG.md), nas seções `Added` / `Changed` / `Fixed`.
3. **Valide o contrato**:
   ```bash
   python scripts/release/validate_package.py --source-root .
   ```
   (sai 0 se tudo concorda e a versão não regride; senão lista cada local e a
   divergência.)
4. **Tag**:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
5. **GitHub Release**: `gh release create vX.Y.Z` com as release notes
   derivadas do changelog.
6. **npm publish separado**: o pacote `hive-sinapse-mind` vive em `npm/` e é
   publicado independentemente:
   ```bash
   cd npm && npm publish
   ```

O npm é um pacote **distinto** (`hive-sinapse-mind`, Node ≥ 18, entrypoint
`bin/hive-mind.js`) — versionado em conjunto com o Python pelo contrato acima,
mas publicado separadamente.

---

## Fronteiras

Nunca commitar, **em nenhuma circunstância**:

- `.env` — chaves de API, tokens, OAuth secrets.
- `hive_mind.db` — memória pessoal (banco inteiro, incluindo a tabela de
  segredos criptografados).
- `~/.claude-mem/` e `claude-mem/data/lightrag/` — observações e embeddings.
- `backups/` — backups do UMC.
- `*.secret`, `config/keys/**` — credenciais.
- `logs/` e `dist/` — artefatos locais.

`.gitignore` cobre `.env` e `*.db`; `[tool.hatch.build]` exclui os mesmos do
wheel/sdist. Guardrails adicionais no [AGENTS.md](../AGENTS.md) (raiz):

- nunca modificar `cerebro/` sem o Watcher ativo (ou rodar
  `./scripts/graph/build-graph.sh` depois);
- nunca duplicar dado entre o vault e as ferramentas externas — o vault é a
  fonte única;
- nunca hardcodar modelos de LLM — o sistema obedece
  `HIVE_*_PROVIDER/MODEL` do `.env`;
- novo código que cria/modifica arquivo do vault **deve** usar as constantes de
  `core/paths.py`, não caminhos hardcoded.

Relacionado:

- [README.md](README.md) — índice e regras de manutenção
- [cli.md](cli.md) — o CLI nativo e seus subgrupos
- [captura.md](captura.md) — testes que protegem a identidade canônica
- [runtime.md](runtime.md) — manifesto e daemon
-  — estado atual por fase
