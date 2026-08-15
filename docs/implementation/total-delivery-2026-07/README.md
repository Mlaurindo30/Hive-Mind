# Hive-Mind — Programa de Entrega Total

> Origem: auditoria read-only de **2026-07-30 20:35 -03:00** sobre o runtime vivo em
> `D:\Hive-Mind` (HEAD `52a8441`).
> Relatório-fonte: `D:\Hive-Mind-Audit\20260730-203504\current-runtime-readonly\HIVE-MIND-CURRENT-READONLY-AUDIT.md`

Este diretório é o **plano de execução canônico** até o projeto estar 100 %
funcional, reproduzível e sem nenhuma janela de console.

---

## Princípios inegociáveis

1. **Python é o dono de tudo.** Nenhum `.ps1`, `.psm1`, `.vbs`, `.cmd` no
   projeto. As **únicas** duas exceções permitidas são `install.bat` e
   `setup-brain.bat` — wrappers finos de instalação/configuração, executados
   manualmente por um humano, nunca por task, serviço, hook ou processo
   permanente.
2. **Zero janelas.** Nenhuma janela de console pode aparecer enquanto o projeto
   roda. A garantia tem que vir do **binário** (PE Subsystem 2), não de uma flag
   de runtime que alguém pode esquecer.
3. **Nada silencioso.** Nenhum job pode sair com código 0 tendo falhado
   internamente. Nenhum estágio pode falhar sem produzir alerta.
4. **Reprodutível ou não existe.** Se um `git clone` limpo não produz o
   comportamento, o comportamento não conta como entregue.
5. **Evidência, não afirmação.** Toda task fecha com: teste automatizado +
   validação no runtime vivo + prova de que a instalação limpa produz o mesmo.

---

## Fases

| # | Fase | Arquivo | Bloqueia | Gate de saída |
|---|---|---|---|---|
| 00 | Reprodutibilidade | [FASE-00](FASE-00-reprodutibilidade.md) | **tudo** | `git status` vazio, HEAD publicado |
| 01 | Zero janelas (garantia por binário) | [FASE-01](FASE-01-zero-janelas.md) | 07 | 0 eventos de console em 30 min sem agente |
| 02 | Erradicação total de shell | [FASE-02](FASE-02-erradicacao-shell.md) | 07 | 0 `.ps1/.psm1/.vbs/.cmd` no repo |
| 03 | Falhas silenciosas | [FASE-03](FASE-03-falhas-silenciosas.md) | 07 | backup e dream com 3 execuções verdes |
| 04 | Contratos e suíte de testes | [FASE-04](FASE-04-contratos-testes.md) | 07 | `pytest` = 0 failed |
| 05 | Captura universal | [FASE-05](FASE-05-captura-universal.md) | — | todos os providers OK ou retirados |
| 06 | Saúde do conhecimento | [FASE-06](FASE-06-saude-conhecimento.md) | — | `knowledge_health = ok` |
| 07 | Clean install PROVEN | [FASE-07](FASE-07-clean-install.md) | release | CI em máquina descartável verde |
| 08 | Observabilidade e resiliência | [FASE-08](FASE-08-observabilidade.md) | — | alertas cobrindo todos os gates |
| 09 | Documentação viva | [FASE-09](FASE-09-documentacao-viva.md) | — | 0 documento STALE |
| 10 | Endurecimento e segurança | [FASE-10](FASE-10-endurecimento.md) | release | auditoria de segurança fechada |

Ordem de execução:

```
00 ─┬─> 01 ─┬─> 07 ─> RELEASE
    ├─> 02 ─┤
    ├─> 03 ─┤
    ├─> 04 ─┘
    ├─> 05
    ├─> 06
    ├─> 08
    ├─> 09
    └─> 10
```

---

## Squad — RACI

| Agente | Responsabilidade | Não faz |
|---|---|---|
| **Claude** | Arquitetura, contratos, decisões, gates de aceitação, revisão adversarial, documentação viva, auditoria | Não implementa em lote |
| **Codex** | Implementação, refatoração, migrações mecânicas multi-arquivo, escrita de testes | Não decide contrato |
| **Kimi** | Leitura de contexto longo: diffs gigantes, logs históricos, formatos de origem de captura, levantamento de dívida | Não edita código de produção |
| **Kilo / Copilot** | Assistência inline, boilerplate de teste | Não toca runtime |
| **Qwen / Hermes / Mimo** | Jobs batch locais via Ollama (vetorização, promoção de conhecimento) | Não toca código |

**Regra de fronteira:** Codex implementa, Claude aceita. Nenhum merge sem o gate
da fase verde e verificado por evidência.

---

## Defeitos rastreados (da auditoria)

| ID | Defeito | Fase |
|---|---|---|
| D-01 | Runtime vivo não está em nenhum commit (27 módulos untracked) | 00 |
| D-02 | `HiveMind-Backup` falha `0x1` há 2 dias, silenciosamente | 03 |
| D-03 | HEAD ainda embarca 38 `.ps1/.vbs` | 00, 02 |
| D-04 | `runtime_services.py:1007` — literal `powershell` morto | 02 |
| D-05 | Plugin claude-mem invoca `powershell.exe` a cada ~40 s (com `windowsHide`) | 10 |
| D-06 | Parser do Kimi retorna 0 sessions | 05 |
| D-07 | 4 providers em SKIP silencioso | 05 |
| D-08 | `knowledge_health = degraded` (3,31 % linked, 3928 pendentes) | 06 |
| D-09 | Dream Cycle falha e sai com código 0 | 03 |
| D-10 | 1329 documentos, 0 vetores | 06 |
| D-11 | Clean install `NOT_PROVEN` por construção | 00, 07 |
| D-12 | `_WindowsLock` ignora `state_dir`, usa mutex global | 04 |
| D-13 | 4 testes de fronteira de arquitetura falhando | 02, 04 |
| D-14 | Contrato do owner de backup divergente | 04 |
| D-15 | 3 regressões de identidade/governança | 04 |
| D-16 | Segredos nunca varridos nos 108 paths untracked | 00, 10 |
| D-17 | Documentos vivos contradizem o runtime | 09 |
| D-18 | Serviços rodam em `python.exe` (subsystem 3) + flag, não em binário GUI | 01 |
| D-19 | `claude-hook.cmd` (Orca) dispara `cmd.exe` a cada evento de hook | 01 |
| D-20 | Hook do Claude usa `python.exe`, assimétrico com o Codex | 01 |
| D-21 | Log operacional do Task Scheduler desabilitado | 08 |
| D-22 | MCP stdio órfão sobrevive ao pai (PID 22544) | 08 |
| D-23 | `UnicodeDecodeError` ao ler stdout de subprocesso (CP-1252 vs UTF-8) | 04 |
| D-24 | Trampolim `uv` duplica cada processo de serviço | 10 |

---

## Critério de GO para release

Todos verdadeiros simultaneamente:

- [ ] `git status --porcelain` vazio e HEAD publicado com upstream
- [ ] `pytest tests/unit` = **0 failed**
- [ ] Zero arquivo `.ps1/.psm1/.vbs/.cmd` no repositório (exceto `install.bat`, `setup-brain.bat`)
- [ ] Zero binário de PE Subsystem 3 referenciado por task, serviço, hook ou MCP
- [ ] Zero evento de console em janela de **30 min sem nenhum agente aberto**
- [ ] `HiveMind-Backup` e `HiveMind-DreamCycle`: 3 execuções naturais consecutivas com `LastTaskResult = 0x0` **e** artefato correspondente
- [ ] `knowledge_health.status = ok`
- [ ] CI de máquina descartável = **PROVEN**, incluindo o teste negativo
- [ ] `CURRENT-STATE.md` regenerado e batendo com o runtime vivo
