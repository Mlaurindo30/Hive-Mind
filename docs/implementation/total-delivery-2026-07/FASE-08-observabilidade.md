# FASE 08 — Observabilidade e resiliência

**Defeitos:** D-21, D-22
**Owner:** Codex · Claude (critérios de alerta)
**Depende de:** Fase 03 (registro estruturado por job)

> A auditoria só descobriu backup e dream quebrados porque foi ler os arquivos de
> métrica um por um. Isso não escala e não acorda ninguém às 2 da manhã.

**Gate de saída:** todo gate do README tem um alerta correspondente; nenhuma
falha depende de inspeção manual.

---

## T08.1 — Dashboard de saúde consolidado

`scripts/health/health_dashboard.py` passa a agregar, numa única saída:
- estado das 7 tasks (`LastTaskResult`, `LastRunTime`, idade);
- `logs/jobs/<job>-latest.json` de todos os 18 jobs;
- `services.managed.json` (freshness, PIDs vivos, ancestralidade);
- `post-reboot-validation.json`;
- `knowledge_health`;
- doctor de captura;
- último `console-watch`.

---

## T08.2 — Regras de alerta

| Condição | Severidade |
|---|---|
| Qualquer task com `LastTaskResult ≠ 0` | crítico |
| Job com `status ≠ ok` no `-latest.json` | crítico |
| Backup mais recente > 36 h | crítico |
| `dream_cycle_latest.json` `status ≠ ok` ou > 36 h | crítico |
| `services.managed.json` mais velho que 5 min | crítico |
| Serviço `required` não running | crítico |
| `knowledge_health.status = degraded` | alto |
| Provider de captura sem evento novo por > N h | médio |
| `console-watch` com evento Hive-Mind | crítico |

---

## T08.3 — Canal de entrega dos alertas

Decidir e implementar: arquivo + notificação de desktop nativa (sem shell),
ou webhook local. Requisito: **não pode abrir janela**.

---

## T08.4 — Reabilitar o log operacional do Task Scheduler (D-21)

Canal `Microsoft-Windows-TaskScheduler/Operational` está desabilitado — foi o que
impediu o post-mortem do `0x1` do backup. Reabilitar no setup e ler
programaticamente via API de eventos.

---

## T08.5 — Detecção de processo órfão (D-22)

A auditoria achou o PID 22544 (`sinapse-mcp.py`) cujo pai já havia saído. MCPs
stdio devem morrer com o pai.

- Investigar por que sobrevivem (job object ausente? handle herdado?).
- Implementar varredura periódica que **reporta** órfãos (não mata
  automaticamente sem política explícita).

---

## T08.6 — Watchdog do Supervisor

`HiveMind-Supervisor-Watchdog` está **Disabled**. Decidir: remover (a política de
`RestartCount=10 / PT1M` da própria task já cobre) ou reativar com propósito
claro e testado. Task desabilitada com trigger ativo é ambiguidade pura.

---

## T08.7 — Readiness real por serviço

Hoje `state: running` significa "o processo existe". Adicionar readiness por
serviço (endpoint HTTP, arquivo de heartbeat, ou probe específico), para que
"running" e "funcionando" deixem de ser a mesma coisa.

---

## T08.8 — Métricas de restart

`restarts: 0` hoje em todos. Expor histórico: restarts nas últimas 24 h por
serviço, com alerta em flapping.

---

## T08.9 — Retenção e rotação de logs

`logs/` vai crescer com `logs/jobs/` da Fase 03. Política de retenção testada,
sem depender de script externo.

---

## T08.10 — OTel já existe: usar

`hive-otel-collector` roda como serviço gerenciado. Levantar o que ele coleta
hoje e conectar as métricas das Fases 03/06/08, em vez de criar um caminho
paralelo.

---

## T08.11 — Comando único de diagnóstico

`hive-mind doctor` — um comando que roda todos os checks acima e devolve exit
code binário. É o que o dono do projeto executa quando desconfia de algo, e o que
o CI da Fase 07 chama.
