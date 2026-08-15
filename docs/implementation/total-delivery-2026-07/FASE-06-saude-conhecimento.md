# FASE 06 — Saúde do conhecimento

**Defeitos:** D-08, D-10
**Owner:** Codex (pipeline) · Qwen/Hermes (batch local via Ollama) · Claude (validação)
**Depende de:** Fase 00; T03.7 (backpressure) para não reacumular

Estado na auditoria (`sinapse_health`, `status: degraded`):

| Métrica | Valor | Limite |
|---|---:|---|
| `neurons_total` | 1447 | — |
| `neurons_vectorized_pct` | 92,05 % | ok |
| `observations_total` | 5259 | — |
| `observations_linked_pct` | **3,31 %** | ❌ < 80 % |
| `discoveries_pending` | **3928** | ❌ > 500 |
| `document_vectors` | 1329 fontes / **0 vetores** | ❌ |
| `summary_vectors` | 1 / 0 | ❌ |
| `milvus_sync_lag` | 1332 | ⚠ |
| `tombstones_total` | 7 | ok |

**Gate de saída:** `knowledge_health.status = ok`.

---

## T06.1 — Classificar antes de escrever

`sinapse_promote_knowledge(dry_run=true)` sobre os 3 928 pendentes. Entender a
distribuição por tipo/origem **antes** de qualquer escrita. Muito provavelmente
há classes inteiras que deveriam ser descartadas, não promovidas.

**Entregável:** relatório de classificação.

---

## T06.2 — Drenar em lotes com medição

Executar promoção em lotes, medindo `observations_linked_pct` e
`discoveries_pending` a cada lote. Parar e reavaliar se a taxa de erro subir.

**Meta:** `observations_linked_pct ≥ 80 %`, `discoveries_pending ≤ 500`.

---

## T06.3 — Investigar por que só 3,31 % ficam ligados

3,31 % é baixo demais para ser volume — é sintoma de defeito no vínculo
`observation.neuron_id`. Investigar antes de drenar em massa, senão o backlog
volta.

**Teste:** ingestão de uma observação conhecida ⇒ neuron criado ⇒ `neuron_id`
gravado na observação.

---

## T06.4 — Quarentena de erros estruturais

`sinapse_promote_knowledge` já quarentena erros estruturais. Expor o volume e o
motivo dominante; uma classe de erro respondendo por milhares de itens é bug, não
dado ruim.

---

## T06.5 — Vetorizar os 1 329 documentos (D-10)

`document_vectors` em 0 %. Descobrir por que o pipeline de documentos não
alimenta o Milvus (a coleção existe; `memory_vectors` está em 92 %).

**Teste de integração:** ingerir um documento ⇒ vetor aparece na coleção
`document_vectors` ⇒ `sinapse_query` recupera por similaridade.

---

## T06.6 — Backfill de vetores de documento

Após a correção, backfill dos 1 329 com Ollama local (Qwen/Hermes), em lotes com
checkpoint.

**Meta:** `document_vectors ≥ 90 %`.

---

## T06.7 — `summary_vectors`

1 fonte / 0 vetores. Volume trivial, mas indica o mesmo defeito de pipeline.
Corrigir junto com T06.5.

---

## T06.8 — Zerar o `milvus_sync_lag`

Lag de 1 332 em `memory_vectors`. Diagnosticar: escrita assíncrona sem
reconciliação? Falha silenciosa de flush? Adicionar reconciliador periódico.

**Teste:** escrever N neurônios, forçar reconciliação, lag → 0.

---

## T06.9 — Alertas de saúde do conhecimento

`scripts/health/alert_dispatcher.py` dispara quando
`knowledge_health.status = degraded`, nomeando a métrica que estourou.

**Teste:** limiar artificial ⇒ alerta com a métrica correta.

---

## T06.10 — Provar a cadeia Dream ponta a ponta

O que a auditoria **não** pôde provar (o último ciclo falhou). Após a Fase 03,
numa execução natural bem-sucedida, rastrear notas criadas e provar:

```
Dream → arquivo .md no vault → frontmatter com project metadata →
backlinks → indexação no Graphify → recuperável por sinapse_query
```

**Entregável:** evidência com os IDs/caminhos reais da execução.

---

## T06.11 — Separar dívida histórica de comportamento do writer atual

Notas antigas com frontmatter fora do padrão não podem reprovar o writer atual.
Marcar a fronteira temporal e medir as duas populações separadamente.

---

## T06.12 — TTL de revisão em operação

O protocolo prevê `review_date`/`next_review` com penalidade de staleness. Provar
que está funcionando: nota vencida é demovida no ranking e listada na auditoria.

**Teste:** nota com `next_review` no passado ⇒ score penalizado.
