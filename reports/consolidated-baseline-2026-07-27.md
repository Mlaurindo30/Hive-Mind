# Consolidated baseline declaration — 2026-07-27

Status: baseline consolidada operacionalmente

## Declaração

Com base no estado atual do host em 27 de julho de 2026, o runtime ativo em
`D:\Hive-Mind` deve ser tratado como a baseline consolidada operacional do
projeto Hive-Mind.

Esta declaração não significa “missão 100% encerrada sem ressalvas”. Ela
significa que:

- a raiz ativa que realmente opera o Hive-Mind já é `D:\Hive-Mind`;
- a linha de desenvolvimento em `backups/worktrees` não contém commits mais
  novos do que a raiz ativa;
- o runtime ativo passou os gates locais fortes do próprio projeto;
- os riscos restantes são de fechamento final de escopo e prova residual, não
  de uma segunda árvore operacional concorrente.

## Evidência usada

### 1. Identidade da raiz ativa

- root: `D:\Hive-Mind`
- branch: `codex/universal-provider-capture`
- HEAD: `52a8441b3b661c15a9385a98d042f2e3c70d0277`

### 2. Relação Git com a worktree de desenvolvimento

- worktree de desenvolvimento:
  `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install`
- branch: `codex/control-plane-redesign`
- HEAD: `315befe40856f476734440a5bf3819bc47e993b4`
- leitura já estabelecida nesta missão:
  - `DEVELOPMENT` é ancestral de `ACTIVE`
  - não há commits exclusivos na worktree de desenvolvimento a resgatar

Implicação:

- o estado operacional atual não depende de promover a worktree de backup como
  nova fonte primária;
- a raiz ativa já contém a linha operacional mais nova e válida.

### 3. Gate pós-reboot aprovado

Relatório:

- [post-reboot-validation.json](D:\Hive-Mind\logs\post-reboot-validation.json)

Resultado:

- `status = pass`
- `services_healthy = true`
- `canonical_runtime_paths = true`
- `unhealthy_required_services = []`

### 4. Auditoria de path operacional

Comando executado:

- `D:\Hive-Mind\.venv\Scripts\python.exe D:\Hive-Mind\scripts\health\audit_runtime_paths_windows.py --root D:\Hive-Mind`

Resultado:

- `findings = []`

Implicação:

- não há referência operacional ativa, nesta amostra, para roots não canônicas
  do Hive-Mind.

### 5. Delivery/legado controlado

Leitura atual:

- outbox histórico: `0`
- `unclassified/legacy`: `0`
- `default/ins`: preservado como histórico, não backlog vivo

Implicação:

- o runtime consolidado atual não está bloqueado pelo legado perigoso antigo.

### 6. Providers com prova real no host

Com prova de fonte real + ingestão:

- `antigravity`
- `codex`
- `copilot`
- `hermes`
- `kilo`
- `kimi`
- `mimo`
- `qwen`

Sem prova real suficiente no host atual:

- `openclaw`
- `roo`
- `screenpipe`
- `swarmclaw`

## Interpretação correta da baseline

Esta baseline consolidada significa:

- a operação real já converge para `D:\Hive-Mind`;
- os validadores locais mais fortes do projeto aprovam esse runtime;
- o bootstrap atual, mesmo preservando uma task protegida legada, já é
  compatível com a raiz canônica e não mantém fallback redundante em Startup.

## O que ainda não está implicitamente resolvido

Esta declaração **não** resolve automaticamente:

1. a decisão formal sobre aceitar ou não, como estado final suportado, a task
   protegida `HiveMind-Supervisor` como wrapper legado compatível;
2. a marcação de `openclaw`, `roo`, `screenpipe` e `swarmclaw` como `WORKING`
   sem fonte real no host;
3. a limpeza administrativa de worktrees/snapshots ainda registrados fora da
   raiz ativa.

## Conclusão

Em 27 de julho de 2026, o estado tecnicamente correto é:

- `D:\Hive-Mind` já é a baseline consolidada operacional do Hive-Mind;
- o que resta para concluir a missão inteira não é substituir essa baseline,
  mas fechar as ressalvas finais com prova suficiente.
