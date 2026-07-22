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

### Normalização de remote

`normalize_git_remote()` reduz qualquer forma de URL a `host/caminho`,
sem credenciais, sem `.git`, tudo em minúsculas:

```
https://user:secret@GitHub.com/Owner/Repo.git  ┐
ssh://git@github.com/Owner/Repo.git            ├─→ github.com/owner/repo
git@github.com:Owner/Repo.git                  ┘
```

As chaves do índice do registry são sempre normalizadas na carga.
`by_remote()` aceita tanto a URL crua quanto um remote **já normalizado**
— o resolver passa o valor que `_inspect_git` normalizou, e uma segunda
normalização rejeitaria essa forma (não tem esquema nem `:`).

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

## Onde a identidade estava vazando (D004-R2)

O `ProjectIdentityResolver` resolve corretamente. O problema era **quem o
consultava**: dos dois entrypoints de captura declarados no `runtime.yaml`,
só um chamava `attach_project_identity`.

| Entrypoint | Identidade |
|---|---|
| `capture-realtime.py` (serviço) | canônica |
| `capture-tailer.py` (job) | rótulo livre do parser |

E o motor aceitava o rótulo como autoridade:

```python
proj = sess.get("project_name") or sess.get("project") or PROJECT
```

Resultado medido em dados reais: texto de prompt virou nome de projeto
(`preciso-que-verifique-o-por-que-3`, 37 observações) e a worktree virou um
projeto separado da própria raiz (`hive-mind-windows-zero-install`, 15).

**A correção não é fazer o tailer lembrar de chamar o resolver** — dois
lugares que precisam lembrar da coisa certa é exatamente como isto nasceu.
A identidade passa a ser decidida dentro do ingest nativo
(`hive_mind.capture.ingest`), e os entrypoints fornecem apenas evidências.

Ver [capture/providers.md](capture/providers.md).

### O nome, não só o id (D004-R2)

O `project_id` de uma worktree já estava correto — deriva do git common dir,
que raiz e worktree compartilham. O `project_name` vinha de
`Path(repository_root).name`, e `repository_root` de uma worktree **é** o
diretório da worktree:

```
raiz      id=local/57883d1f7914  name=acme-service
worktree  id=local/57883d1f7914  name=acme-service-feature
```

Como o nome é o campo que o Claude Mem indexa, corrigir só o id não corrigia
nada de visível. `project_name` passa a derivar do git common dir.

