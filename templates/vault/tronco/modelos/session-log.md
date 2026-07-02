---
date: "{{date}}"
description: "{{description:o que rolou nesta sessão, max 150 chars}}"
session_id: "{{session_id}}"
type: session-log
tags:
  - session
  - log
project: "{{project}}"
created: "{{date}}"
updated: "{{date}}"
---
# {{title:sessão YYYY-MM-DD HH:MM}}

## Contexto
<!-- Por que esta sessão começou, qual objetivo. Preenchido por scripts/session_placeholder.py no SessionStart. -->

## Ações
<!-- Lista cronológica de tools chamadas. Preenchida incrementalmente por scripts/session_update.py no PostToolUse.
     Formato: - [HH:MM:SS] tool=N args=… -->

## Observações
<!-- Events relevantes capturados por hooks (claude-mem, etc). -->

## Resumo
<!-- Preenchido por scripts/session_consolidator.py no Stop. Estrutura: bullets / decisões / open questions. -->

## Related
<!-- Wikilinks para project/atom/decision abertos nesta sessão. -->
