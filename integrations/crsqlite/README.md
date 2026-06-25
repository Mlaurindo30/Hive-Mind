# CR-SQLite (vlcn-io) — vendor para Hive-Mind

Sincronização CRDT do `hive_mind.db` entre múltiplas instâncias
(workstation, laptop, servidor) **sem servidor central**, usando
[CR-SQLite](https://github.com/vlcn-io/cr-sqlite) (v0.16.3, 2024-01-17).

## Anatomia

Esta é uma **cliente externa** (política §0.2 do
[`docs/10-implementation-roadmap.md`](../../docs/10-implementation-roadmap.md)):

```
integrations/crsqlite/        # este vendor
├── README.md                  # este arquivo
├── __init__.py                # API pública
├── client.py                  # wrapper Python (load_extension, sync)
├── crsqlite.so                # Linux x86_64/aarch64 (binário nativo)
├── crsqlite.dylib             # macOS x86_64/aarch64
├── crsqlite.dll               # Windows x86_64
```

`integrations/` é onde mora tudo que vem de fora (vendors, clones).
`core/` é o cérebro central — não recebe binários baixados.

## Como o binário chega aqui

`install.sh` (etapa opcional 13) baixa o zip da release oficial e extrai
neste diretório:

- **Linux x86_64:** `crsqlite-linux-x86_64.zip` → `crsqlite.so`
- **Linux aarch64:** `crsqlite-linux-aarch64.zip` → `crsqlite.so`
- **macOS x86_64:** `crsqlite-darwin-x86_64.zip` → `crsqlite.dylib`
- **macOS aarch64:** `crsqlite-darwin-aarch64.zip` → `crsqlite.dylib`
- **Windows x86_64:** `crsqlite-win-x86_64.zip` → `crsqlite.dll`

Re-executável: `bash install.sh --crsqlite` (ver etapa correspondente).

## Uso

```python
import sqlite3
from integrations.crsqlite import (
    enable_crdt, get_changes_since, apply_changes, finalize,
)

conn = sqlite3.connect("hive_mind.db")
enable_crdt(conn)  # idempotente

# Exporta mudancas locais desde a versao N
changes = get_changes_since(conn, db_version=0)

# Aplica mudancas de um peer
apply_changes(conn, peer_changes)

# Antes de fechar:
finalize(conn)
```

## Schema requirement

Tabelas que vão virar CRR precisam de:

1. **PK `NOT NULL` explícita** (SQLite aceita PK nula por padrão).
2. **Toda coluna `NOT NULL` precisa de `DEFAULT`.**

CR-SQLite rejeita com `Table X has no primary key or primary key is
nullable` e `Table X has a NOT NULL column without a DEFAULT VALUE`. O
o schema CRR-compatível (`core/umc_schema_crr.sql`) já está corrigido para P8.

## Por que não usar `import crsqlite`

Não existe wheel Python no PyPI. O caminho oficial é **binário
pré-compilado por plataforma em GitHub Releases**, carregado via
`sqlite3.Connection.load_extension`. Ver [`client.py`](client.py) para o
wrapper completo.

## Testes

```bash
pytest tests/integration/test_crdt.py -v
```

Os testes usam o binário real (sem mocks) e cobrem: export local,
convergência entre 2 DBs, conflito LWW, version tracking, finalize.

## Referencias

- [github.com/vlcn-io/cr-sqlite](https://github.com/vlcn-io/cr-sqlite)
- [Observable notebook do tantaman (basic setup)](https://observablehq.com/@tantaman/cr-sqlite-basic-setup)
- Roadmap interno: `docs/10-implementation-roadmap.md` §4 P8 + §7 Sprint 3.1
