# Recuperação focada da captura Claude Mem — 2026-07-29

## Escopo

Somente o fluxo Claude Mem foi investigado:

`fonte Codex -> parser -> capture-realtime -> worker :37700 -> LLM -> observations/session_summaries`

Não foram alterados provider, modelo, credenciais, `setup-brain` ou scripts
PowerShell. Graphify, Graphiti, RTK e a auditoria dos demais providers ficaram
fora desta intervenção.

## Causa confirmada

O worker Claude Mem estava ativo em `127.0.0.1:37700` e gravava
`user_prompts`, mas o backend selecionado pelo `setup-brain` não estava
disponível em `127.0.0.1:11434`.

O fluxo do worker grava prompts antes da chamada ao modelo. Observações e
resumos, porém, dependem do gerador. Os logs mostravam:

- `OpenRouter network error: Unable to connect`;
- duas tentativas esgotadas;
- `Generator failed`;
- finalização/remoção da sessão sem materializar a fila aceita.

Evidência temporal anterior à recuperação:

- prompt mais recente: 2026-07-29 04:25Z;
- observação mais recente: 2026-07-28 02:52Z;
- resumo mais recente: 2026-07-28 02:43Z.

## Poluição por replay

O cutover alterou o checkpoint de captura:

- legado: `C:\Users\miche\.claude-mem\capture-state.db`;
- canônico: `D:\Hive-Mind\claude-mem\data\capture-state.db`.

O checkpoint canônico não havia incorporado o legado. Para a sessão Codex
ativa, 724 hashes que o banco antigo já conhecia ainda estavam pendentes no
novo. Isso provocou replay histórico e crescimento artificial da fila.

## Ações executadas

1. O Ollama foi iniciado sem alterar a configuração.
2. Foi confirmado que `granite4.1:8b` existe no host.
3. O autostart oficial `Ollama.lnk`, existente mas desabilitado pelo Windows,
   foi reativado em `StartupApproved`.
4. Foi criado backup SQLite consistente do checkpoint canônico.
5. O checkpoint legado foi incorporado com operações aditivas e idempotentes:
   - 8.245 hashes inseridos;
   - 184 sessões inseridas;
   - nenhum prompt, observação ou resumo apagado.
6. `SeenStore` passou a importar automaticamente o checkpoint SQLite legado
   durante o cutover, usando `INSERT OR IGNORE`.
7. `sinapse-capture-realtime` foi reiniciado isoladamente para carregar a
   correção Python.

## Evidência após recuperação

O worker voltou a chamar o modelo e materializou novas análises:

- `obsIds=[11747]`;
- `obsIds=[11762]`.

O capturador também enfileirou `type=summarize`. No fechamento desta
intervenção, esse resumo ainda não havia sido materializado porque existia uma
fila anterior de observações à frente. Portanto, o estado não deve ser
declarado 100% concluído.

## Testes

O teste de regressão foi criado antes da implementação e falhou inicialmente
com:

`TypeError: SeenStore.__init__() got an unexpected keyword argument 'legacy_db_path'`

Depois da correção:

```text
tests/unit/test_capture_core.py
18 passed
```

## Arquivos alterados

- `src/hive_mind/capture/engine.py`
- `tests/unit/test_capture_core.py`

Nenhum `.ps1` foi editado.

## Backup e rollback

- diretório:
  `D:\Hive-Mind-Archive\20260729-014212\capture-state-migration`
- banco anterior:
  `capture-state.before-legacy-merge.db`
- manifesto de rollback:
  `rollback.json`

## Inconsistência ainda aberta no control plane

A migração de ownership para Python existe em:

- `hive_mind.maintenance.runtime_services`;
- `hive_mind.maintenance.windows_runtime`;
- `hive-mindd`.

Entretanto, o estado atual ainda contém vestígios incompatíveis com o desenho
sem PowerShell:

- `config/runtime.yaml` declara o módulo inexistente
  `python -m claude_mem.worker`;
- `runtime_services.py` ainda materializa `claude-mem-local.ps1`;
- tarefas Supervisor/Watchdog ainda usam VBS/PowerShell.

Esses vestígios não foram modificados nesta correção focada. Eles exigem um
cutover separado do control plane para um launcher Python único do Claude Mem,
sem reabrir o `setup-brain` nem alterar as configurações que voltaram a
funcionar.
