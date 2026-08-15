# FASE 05 — Captura universal

**Defeitos:** D-06, D-07
**Owner:** Kimi (análise de formato) · Codex (implementação de parser)
**Depende de:** Fase 00

Estado na auditoria:

| Provider | Estado | Detalhe |
|---|---|---|
| antigravity | OK | 75 fontes / 50 watch dirs |
| codex | OK | 356 fontes / 17 watch dirs |
| copilot | OK | 27 fontes / 12 watch dirs |
| hermes | OK | 41 sessions / 162 prompts |
| kilo | OK | 11 sessions |
| qwen | OK | 14 fontes |
| claude | OK | 11 628 observations |
| **mimo** | **PARCIAL** | 6 sessions, **0 prompts, 0 turns** |
| **kimi** | **FAIL** | arquivos existem, parser retorna **0 sessions** |
| openclaw / roo / screenpipe / swarmclaw | SKIP | nenhum caminho de origem |

**Gate de saída:** todo provider ou está **OK** ou foi **explicitamente
retirado** do doctor. Nenhum SKIP silencioso.

---

## T05.1 — Engenharia reversa do formato Kimi (Kimi lê, Codex implementa)

Origem: `~/.kimi-code/sessions/wd_runtime_*/session_*/agents/main/wire.jsonl`.
Levantar o schema real: tipos de evento, campo de papel (user/assistant), timestamp,
identificador de sessão, aninhamento por agente (`agents/main` sugere sub-agentes).

**Entregável:** `docs/capture/formats/kimi.md` com o schema documentado.

---

## T05.2 — Implementar o parser Kimi

`scripts/capture/parsers/kimi.py` produzindo sessions/prompts/turns.

**Teste:** fixture com `wire.jsonl` real **anonimizado** ⇒ N sessions, M prompts,
K turns, com asserções exatas.
**Validação viva:** `validate_capture_sources.py` mostra `OK kimi`.
**Fecha:** D-06.

---

## T05.3 — Sub-agentes do Kimi

O caminho `agents/main/` implica que outros agentes gravam em `agents/<nome>/`.
Decidir: capturar todos (com atribuição correta de agente) ou apenas `main`.
Documentar a decisão.

---

## T05.4 — Corrigir o Mimo (0 prompts / 0 turns)

`~/.local/share/mimocode/mimocode.db` produz 6 sessions mas nenhum conteúdo.
Mesmo tratamento: schema documentado, parser corrigido, fixture, teste.

---

## T05.5 — Decidir sobre os 4 providers em SKIP (D-07)

`openclaw`, `roo`, `screenpipe`, `swarmclaw`. Para cada um:
- **Suportado** ⇒ implementar descoberta de caminho + parser + fixture;
- **Retirado** ⇒ remover do registro de providers e do doctor.

Deixar em SKIP silencioso é o pior dos mundos: polui o sinal e esconde
regressão.

---

## T05.6 — Doctor com sinal binário

`validate_capture_sources.py` passa a ter exit code: 0 só se **todos** os
providers registrados estiverem OK. SKIP deixa de existir como estado válido.

**Teste:** provider quebrado ⇒ exit ≠ 0.

---

## T05.7 — Freshness por provider, não só existência

Hoje o doctor prova que a fonte existe e parseia. Falta provar que houve
**atividade recente**. Adicionar, por provider: timestamp do evento mais novo
capturado e alerta se > N horas com o provider em uso.

**Teste:** relógio simulado.

---

## T05.8 — Teste de ponta a ponta por provider

Para cada provider OK: injetar um evento sintético na fonte (em sandbox), rodar o
capture-realtime e provar a cadeia
`fonte → parser → capture-identities.db → claude-mem → UMC`.

Isto é o que a auditoria **não** pôde provar (foi proibido gerar canários).

---

## T05.9 — Contrato de identidade de projeto na captura

Ligado a D-15/T04.4: labels de aplicação e perfil de provider **nunca** podem
virar `project_id`. Regressão já detectada — reforçar com teste por provider.

---

## T05.10 — Documentar a matriz de providers

`docs/capture/providers.md`: para cada provider — caminho de origem, formato,
parser, estado, data da última verificação. Documento vivo, checado pelo
`implementation/validate.py`.
