# FASE 10 — Endurecimento e segurança

**Defeitos:** D-05, D-16, D-24
**Owner:** Claude (escopo) · Codex (implementação)
**Depende de:** estabilização das fases anteriores

**Gate de saída:** auditoria de segurança dedicada fechada; nenhuma dependência
de terceiro capaz de abrir janela.

---

## T10.1 — Auditoria de segurança dedicada (D-16)

Escopo próprio, não coberto pela auditoria de runtime:

- superfície de rede: hoje `:37700` (claude-mem) e `:11434` (Ollama) em
  `127.0.0.1`; `sinapse-api` e `sinapse-mcp-http` — confirmar bind e
  autenticação;
- containers: Milvus, FalkorDB, RagFlow, MinIO, ES, MySQL, Redis — portas
  expostas, credenciais default, volumes;
- permissões de `cerebro/` e o modelo de vault write enforcement;
- rotação de segredos e presença de credenciais em `backups/`;
- `RunLevel = Limited` das tasks — confirmar que é suficiente e mínimo.

---

## T10.2 — Executar os scrubs de verdade

`scrub-capture-outbox`, `scrub-env-backups`, `scrub-runtime-artifacts` existem
(implicando que material com forma de segredo é conhecido), mas não há evidência
de execução. Rodar com `--dry-run`, revisar, aplicar.

---

## T10.3 — Pre-commit de varredura de segredos

Depois da Fase 00, garantir que não volte a acontecer: hook de pre-commit
**nativo em Python** (não `.ps1`, não `.cmd`) que varre o diff por material com
forma de segredo.

---

## T10.4 — `powershell.exe` do plugin claude-mem (D-05)

O plugin `thedotmack/claude-mem@13.12.4` invoca `powershell.exe -NoProfile
-EncodedCommand` (CIM lookup) a cada ~40 s. **Usa `windowsHide:!0`**, portanto
não pisca janela — mas é dependência de terceiro fora do nosso contrato.

Ordem de preferência:
1. **Substituir o health-check** — o worker já expõe `/health` em `:37700`, que
   a auditoria confirmou responder `HTTP 200`. A consulta CIM é redundante.
2. Fixar a versão do plugin e abrir issue upstream.
3. Patch local no launcher gerenciado, se necessário.

---

## T10.5 — Fixar versões de dependências de terceiro

`claude-mem@13.12.4`, `bun`, `uv`, imagens Docker. Uma atualização silenciosa que
remova `windowsHide` reintroduz o problema que a Fase 01 fechou.

---

## T10.6 — Reduzir a duplicação de processo do trampolim `uv` (D-24)

Cada serviço gerenciado custa **2 processos**: `.venv\Scripts\python.exe` (shim de
45 KB) exec-a `.uv\python\...\python.exe` (91 KB). São 7 serviços = 14 processos.

Avaliar apontar os specs direto ao interpretador base mantendo `sys.prefix`
canônico via `PYTHONHOME`/`.pth`. Medir antes: o ganho pode não justificar o
risco de quebrar a canonicidade que a Fase 01 garante.

**Teste:** após a mudança, os probes continuam retornando
`sys_prefix = <root>\.venv`.

---

## T10.7 — Limites de recurso por serviço

Nenhum serviço tem teto de memória/CPU. Um `distill_validate` de 39,5 min
(Fase 03) mostra que um estágio pode consumir a máquina inteira sem freio.

---

## T10.8 — Política de retenção de `backups/`

`backups/` contém snapshots com `.ps1`/`.vbs` históricos e potencialmente
segredos. Definir retenção, mover para fora do repositório ou cifrar.

---

## T10.9 — Isolamento entre projetos

O `project_id` e a captura cruzam múltiplos providers e múltiplos projetos.
Confirmar que memória de um projeto não vaza para consultas de outro — ligado a
D-15/T04.4.

---

## T10.10 — Recuperação de desastre

Provar o caminho completo: `backup restore` num diretório alternativo, subir o
runtime a partir dele, confirmar integridade do cérebro. Backup que nunca foi
restaurado não é backup.
