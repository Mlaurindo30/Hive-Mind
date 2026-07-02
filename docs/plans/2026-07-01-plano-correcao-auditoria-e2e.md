# Plano de Correção — Auditoria Ponta a Ponta de 2026-07-01

**Origem:** relatório de investigação E2E executado em 2026-07-01 (sessão de auditoria real:
instalação, build, startup, testes, fluxo E2E, persistência, observabilidade, segurança e docs).
**Estado da auditoria:** 4/4 suítes verdes (558U + 110I + 22E2E + smoke), persistência REST→SQLite
comprovada (obs `0944f63a-ff0d-4c02-bc80-74b44e3fd689`), 6 problemas identificados.

**Regra de ordem:** as fases estão em ordem de execução obrigatória. F1 e F2 são bloqueantes de
release; F3–F6 são recomendadas. Cada fase termina com um gate de verificação executável.

---

## F1 — ALTO: `/api/v1/query` híbrido nunca retorna resultados (bloqueante)

**Causa raiz:** `scripts/services/sinapse-api.py:post_query` (linha ~420) chama
`route_query(query, top_k=…)` **sem** `sinapse_query_fn`. Em `core/retrieval/router.py:419-425`,
`_route_hybrid` retorna vazio com `missing_context=["hybrid:context_fusion_indisponivel"]` quando a
fn é `None` — e `hybrid` é o intent de fallback padrão. Evidência ao vivo: REST → `results:[]`,
`confidence:0.0`; mesmo marker via MCP → hit `confidence:0.808`.

**Referências corretas já existentes no código:**
- `scripts/services/sinapse_mcp.py:461-477` — memoíza `sm._query_vault_knowledge` num
  `legacy_holder` e passa `sinapse_query_fn=_legacy_query`.
- `scripts/services/sinapse-write.py:128` — `route_query(args.text, sinapse_query_fn=sm._query_vault_knowledge)`.
- Import do módulo de fusão: `import sinapse_memory as sm` funciona após
  `from plugins.hermes import sinapse_memory as _sinapse_memory_adapter` (shim que registra o
  módulo; ver `sinapse_mcp.py:31-33`). O `sys.path` do projeto já é garantido no topo do
  `sinapse-api.py` (linhas 19-25).

### Passos
1. **Editar `scripts/services/sinapse-api.py`:**
   - Adicionar import lazy dentro de `post_query` (evita custo/risco no startup do serviço):
     ```python
     from plugins.hermes import sinapse_memory as _sm_adapter  # registra o módulo
     import sinapse_memory as sm
     ```
   - Passar a fn com memoização por request (mesmo padrão do MCP):
     ```python
     legacy_holder = {"result": None}
     def _legacy_query(q: str):
         if legacy_holder["result"] is None:
             legacy_holder["result"] = sm._query_vault_knowledge(q)
         return legacy_holder["result"]

     routed = route_query(
         data.get("query", ""),
         top_k=int(data.get("limit", 5)),
         workspace_id=current_workspace_id(),
         sinapse_query_fn=_legacy_query,
     )
     ```
   - Nota: hoje `post_query` também **não propaga `workspace_id`** para o router (default
     `"default"`), o que quebraria o isolamento K10 multi-tenant na busca. Corrigir junto.
2. **Tratar indisponibilidade:** se a fusão retornar `None`, manter o contrato atual
   (`missing_context` preenchido) — não levantar 500.
3. **Teste de integração novo** `tests/integration/test_api_query_hybrid.py`:
   - Marker `@pytest.mark.integration` + `requires_service`.
   - Sobe a app FastAPI via `TestClient` (importando `sinapse-api.py` como módulo) com
     `HIVE_MIND_API_KEY` de teste.
   - Grava uma observação com marker único via `POST /api/v1/observations`.
   - `POST /api/v1/query` com intent híbrido e assevera: `retrieval_path[0].status == "hit"`
     **ou** `results != []` para uma consulta que sabidamente tem contexto (ex.: termo do vault).
   - Assevera que `missing_context` NÃO contém `hybrid:context_fusion_indisponivel`.
4. **Smoke ao vivo (gate):**
   ```bash
   systemctl --user restart sinapse-api.service
   # com token do ambiente: POST /api/v1/query {"query":"knowledge promotion architecture"}
   # esperado: results não-vazio, confidence > 0
   ```

**Riscos:** o import do adapter carrega o stack de fusão dentro do processo da API (latência da
primeira query ~1-2s, igual ao MCP). Mitigação: import lazy + memoização; opcionalmente aquecer no
`startup` event.

---

## F2 — MÉDIO: fix do crash-loop e feature K10 não commitados (bloqueante)

**Causa raiz:** às 18:35 de 2026-07-01 o serviço crash-loopou 3× com
`ModuleNotFoundError: No module named 'core'` e o systemd desistiu
(`StartLimitIntervalSec=60`, `StartLimitBurst=3`) até restart manual às 18:39. O fix
(`sys.path` bootstrap, `sinapse-api.py:19-25`) existe **apenas no working tree**. Um
`git checkout`/rollback reintroduz a indisponibilidade.

### Passos
1. Revisar o diff completo do working tree (20+ arquivos modificados + untracked):
   `sinapse-api.py` (sys.path fix + K10 workspace middleware + endpoints),
   `tests/unit/test_sinapse_api_workspace_flag.py` (13 testes, já passando na suíte),
   `cerebro/…` (artefatos de grafo/vault regenerados), `causal_edges.json`, `decision/`.
2. Separar em commits lógicos:
   - **Commit A (urgente):** `fix(api): garante project root no sys.path quando executado via systemd`
     — somente o bloco das linhas 19-25 + F1 se já aplicado.
   - **Commit B:** `feat(K10): multi-workspace na REST API (middleware + /workspaces + flag)` +
     teste novo.
   - **Commit C:** artefatos de vault/grafo regenerados (ou deixar para o fluxo automático, se
     houver política de não commitar `cerebro/` manualmente — verificar `.gitignore`/convenção).
3. Rodar `./tests/run_all.sh` antes de cada commit (gate: 4/4 suítes).
4. Gate final: `git stash && systemctl --user restart sinapse-api.service` **não** pode falhar
   (ou seja, o HEAD commitado precisa subir sozinho) — depois `git stash pop` se sobrar algo.

---

## F3 — MÉDIO: REST API sem spans OTEL

**Evidência:** `logs/otel-spans.log` tem spans de `mcp.sinapse_*`, `dream.*`, `capture.ingest`,
mas **0 spans** de endpoints REST. Sem trace/correlation ID na resposta HTTP.

**Infra já existente:** `core/telemetry.py` expõe `init_telemetry()` (idempotente, ativado por
`LANGFUSE_PUBLIC_KEY`) e o contextmanager `span(name, attributes)`; o collector local
(`hive-otel-collector.service`, porta 3100) já aceita OTLP/HTTP JSON.

### Passos
1. Em `sinapse-api.py`, chamar `init_telemetry()` no startup (após load_dotenv).
2. Adicionar middleware HTTP (junto ao `workspace_middleware`):
   ```python
   @app.middleware("http")
   async def telemetry_middleware(request, call_next):
       with span(f"api.{request.url.path}", {"method": request.method}) as s:
           response = await call_next(request)
           # anexar trace_id ao response header
           response.headers["X-Trace-Id"] = format(s.get_span_context().trace_id, "032x") if s else ""
           return response
   ```
   (ajustar à API real do helper `span()`; se ele não devolver o objeto span, estender
   `core/telemetry.py` para devolvê-lo — mudança pequena e retrocompatível).
3. Atributos mínimos por span: `method`, `path`, `status_code`, `workspace_id`.
   **Nunca** logar token, body ou conteúdo de observações (PII).
4. Teste: request ao vivo → `tail logs/otel-spans.log` deve conter `"name": "api./api/v1/health"`
   e a resposta deve ter `X-Trace-Id`.
5. Gate: `grep -c '"name": "api.' logs/otel-spans.log` > 0 após smoke.

---

## F4 — MÉDIO: política de restart do systemd permite desistência permanente

**Evidência:** `StartLimitIntervalSec=60` + `StartLimitBurst=3` + `RestartSec=5` → 3 falhas em
15s esgotam o burst e o serviço fica morto até intervenção manual.

### Passos
1. Editar a unit (fonte no repo que gera `~/.config/systemd/user/sinapse-api.service` — localizar
   template em `scripts/setup/` ou `config/`; se a unit for gerada pelo `install.sh`, corrigir lá
   para não regredir em reinstalação):
   ```ini
   [Unit]
   StartLimitIntervalSec=300
   StartLimitBurst=5

   [Service]
   Restart=on-failure
   RestartSec=15
   ```
   Racional: 5 tentativas espaçadas de 15s cobrem falhas transitórias (rede, .env montado tarde)
   sem crash-loop agressivo; 300s de janela evita desistência por rajada curta.
2. Aplicar o mesmo padrão às demais units críticas: `sinapse-claude-mem`, `sinapse-sqlite-vec`,
   `sinapse-capture-realtime`, `sinapse-graphify-watch`, `hive-otel-collector`.
3. `systemctl --user daemon-reload && systemctl --user restart sinapse-api.service`.
4. Gate: `systemctl --user show sinapse-api -p StartLimitIntervalUSec -p StartLimitBurst` reflete
   os novos valores; health 200 após restart.

---

## F5 — BAIXO: lacunas de documentação (README)

**Evidências da auditoria:**
- Tabela "Cloud Memory API" lista 6 endpoints; a API real expõe também `/api/v1/workspaces`
  (sem auth, só contagens), `/api/v1/metrics`, `/api/v1/knowledge/health`, `/api/v1/sync/export`,
  `/api/v1/sync/import`, `/api/v1/neurons/import`.
- Tabela de env vars não documenta `HIVE_MIND_CORS_ORIGINS` (default
  `http://localhost:37700,http://localhost:8000`) nem `HIVE_MIND_API_HOST` (default `127.0.0.1`).

### Passos
1. Completar a tabela de endpoints do README (método, rate limit, auth sim/não, descrição —
   copiar os limites reais dos decorators `@limiter.limit`).
2. Adicionar `HIVE_MIND_CORS_ORIGINS` e `HIVE_MIND_API_HOST` à tabela de configuração, com a
   nota de segurança: mudar o host para bind público exige revisar F6.
3. Registrar no `CHANGELOG.md` as correções F1–F4.
4. Gate: releitura da tabela vs `grep '@app\.' scripts/services/sinapse-api.py` — 1:1.

---

## F6 — BAIXO: `/api/v1/workspaces` sem auth (decisão consciente, condicionar)

**Evidência:** endpoint aberto por design (comentário no código: "retorna apenas contagens").
Testado ao vivo: HTTP 200 sem token, expõe IDs de workspaces e contagens. Risco só se
`HIVE_MIND_API_HOST` deixar de ser `127.0.0.1`.

### Passos
1. Condicionar: exigir auth quando o bind não for loopback:
   ```python
   _host = os.environ.get("HIVE_MIND_API_HOST", "127.0.0.1")
   _workspaces_deps = [] if _host in ("127.0.0.1", "localhost", "::1") else [Depends(verify_api_key)]
   @app.get("/api/v1/workspaces", dependencies=_workspaces_deps)
   ```
   (ou simplesmente exigir auth sempre — decisão de produto; a variante condicional preserva o
   uso atual por operadores locais).
2. Teste unitário cobrindo os dois modos (flag de host).
3. Gate: com host público simulado, GET sem token → 401/403.

---

## Ordem de execução e gates consolidados

| # | Fase | Bloqueante? | Gate |
|---|------|-------------|------|
| 1 | F1 query híbrida | **Sim** | `POST /api/v1/query` retorna hit real + teste integração novo verde |
| 2 | F2 commits | **Sim** | HEAD sobe sozinho via systemd; `run_all.sh` 4/4 |
| 3 | F3 OTEL na API | Não | spans `api.*` no otel-spans.log + `X-Trace-Id` na resposta |
| 4 | F4 restart policy | Não | novos limites visíveis no `systemctl show`; unit template do installer atualizado |
| 5 | F5 README | Não | tabela 1:1 com os decorators reais |
| 6 | F6 workspaces auth | Não | 401 com bind público simulado |

**Critério de pronto global:** repetir o probe E2E da auditoria (gravar marker → query REST →
confirmar SQLite → conferir span com trace_id) com **todas** as etapas OK — o que hoje falha nas
etapas query-REST e span-REST.
