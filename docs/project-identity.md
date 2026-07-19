# Project Identity

Como o Hive-Mind decide a qual projeto pertence cada sessão, observação,
neurônio e vetor.

Referências: [ADR-006](implementation/ARCHITECTURE-DECISIONS.md),
[design](superpowers/specs/2026-07-17-canonical-project-identity-and-windows-capture-design.md).

## Por que existe

O projeto era derivado do último diretório do `cwd`. Isso produzia
identidades falsas e fragmentava o cérebro:

```
Hive-Mind
hive-mind-windows-zero-install          ← worktree do MESMO repositório
Hive-Mind/hive-mind-windows-zero-install
Qwen                                    ← nome do aplicativo
Microsoft VS Code                       ← nome do aplicativo
miche                                   ← diretório do usuário
hermes                                  ← provider
```

Cada rótulo virava um projeto separado em Claude Mem, UMC, Dream Cycle,
Markdown, vetores e grafos.

## Os dois campos

| Campo | Significado | Onde vive |
|---|---|---|
| `project_id` | identificador estável usado em banco, filtros, Dream Cycle e vetores | `observations.workspace_id`; frontmatter `project_id` |
| `project_name` | nome humano exibido na interface | `observations.project`; frontmatter `project_name` |

Worktree, branch, provider e surface são **metadados**, nunca identidade.

## Ordem de resolução

`ProjectIdentityResolver` ([scripts/capture/project_identity.py](../scripts/capture/project_identity.py))
aplica, em ordem:

1. projeto explícito fornecido e validado — `explicit`
2. `HIVE_PROJECT_ID` / `HIVE_PROJECT_ROOT` — `environment_id`
3. workspace oficial fornecido pelo aplicativo
4. `git rev-parse --show-toplevel` — `git_root` (confiança 0.96)
5. `git rev-parse --git-common-dir` — `git_common_dir` (0.96)
6. remote Git normalizado — `git_remote` (0.95)
7. mapa explícito de aliases — `alias_root` (0.90)
8. markers conhecidos do projeto — `marker` (0.80)
9. `unclassified/<provider>` — `unclassified_provider` (0.0)

`Path(cwd).name` nunca é identidade canônica.

### Regra do git common dir

Raiz e worktrees que compartilham o mesmo `git-common-dir` recebem o
**mesmo** `project_id`:

```
D:\Hive-Mind                                              → hive-mind
D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install → hive-mind
```

A branch (`codex/control-plane-redesign`) e o nome da worktree
(`hive-mind-windows-zero-install`) ficam apenas em metadados.

## Aliases

[config/project-aliases.yaml](../config/project-aliases.yaml) declara
explicitamente os projetos conhecidos:

```yaml
projects:
  - project_id: hive-mind
    project_name: Hive-Mind
    remotes: [https://github.com/Mlaurindo30/Hive-Mind.git]
    roots:
      - 'D:\Hive-Mind'
      - 'D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install'
    git_common_dirs: ['D:\Hive-Mind\.git']
    aliases: [Hive-Mind, hive-mind-windows-zero-install, ...]
```

Remotes são normalizados sem credenciais. Paths comparam-se de forma
case-insensitive no Windows; junctions e symlinks são resolvidos; paths
Unicode e com espaços funcionam.

## Projeto ativo vs. projeto mencionado

Mencionar um projeto na conversa **não** o torna o projeto ativo:

```
Qwen aberto em C:\Users\miche\Documents\Qwen, conversa cita Hive-Mind
→ active_project:      unclassified/qwen
→ referenced_projects: [hive-mind]
```

A resolução semântica só ocorre com a política habilitada, acima do
limiar configurado, registrada como `semantic_reference` e auditável.
Nunca há classificação silenciosa.

## Propagação

```
parser → sessão normalizada → ProjectIdentityResolver
       → capture_core.ingest() → Claude Mem
       → bridge (workspace_id = project_id) → UMC
       → Dream Cycle → Markdown → índices → consulta
```

O bridge ([core/knowledge/claude_mem_bridge.py](../core/knowledge/claude_mem_bridge.py))
grava `workspace_id = project_id` e preserva o envelope
`project_identity` em `observations.metadata`.

## Dados legados

Registros anteriores a este trabalho carregam `workspace_id='default'`.
Eles **não são reescritos nem apagados** (ADR-012). Continuam legíveis e
são classificados como `legacy_label`.

Para inventariá-los sem alterar nada:

```powershell
hive-mind projects audit
hive-mind projects audit --json
```

A migração histórica exige backup, dry-run, plano transacional,
rollback e autorização explícita.

## Estado de implementação

Ver [docs/implementation/CURRENT-STATE.md](implementation/CURRENT-STATE.md).
O resolver está implementado e coberto por testes; a validação
operacional por provider é a entrega D003/D004.
