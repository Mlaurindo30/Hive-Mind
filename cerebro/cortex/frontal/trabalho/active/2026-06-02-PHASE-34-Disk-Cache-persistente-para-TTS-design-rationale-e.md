---
tags: [decision]
status: active
created: 2026-06-02
updated: 2026-06-02
source: hermes-session
---

# PHASE-34 Disk Cache persistente para TTS — design rationale e trade-offs

## Contexto

PHASE-33 fechou a integração TTS end-to-end. Restava um gap operacional:
o cache LRUCache in-memory (L1) era perdido no restart do processo.
Pra workloads long-running (Thoth do Michel é exatamente isso),
um cache L1-only significa que cada restart recomeça do zero e
toda frase TTS-ada tem o custo total de synthesis (~5s para Cebolinha
VoiceClone, ~300ms para Kokoro pm_alex).

## Decisão

Implementar DiskCache L2 como backing store do L1, opt-in via settings
de provider. Wired em Kokoro e Qwen3 (os 2 providers nativos que
escrevem em Python subprocess — onde synthesis é caro o suficiente
pra cache fazer diferença real).

## Arquitetura

```
Generate(req)
  │
  ├─► L1.Get(key) ──── HIT ──► return clone
  │
  ├─► L2.Get(key) ──── HIT ──► promote to L1; return
  │
  ├─► provider.Generate() (subprocess)
  │     │
  │     ▼
  │   audio bytes
  │     │
  │     ├─► L1.Put(key, snapshot)
  │     └─► L2.Put(key, snapshot, audio)
  │
  └─► return
```

## Formato de arquivo

- Sidecar JSON (`<key>.json`): `CacheEntry` com ProviderID, VoiceID,
  AudioFormat, AudioURI, SampleRateHz, Channels, Bitrate, CreatedAt,
  Metadata, CachedAt.
- Áudio puro (`<key>.<ext>`): bytes do TTS provider.
- Key = `sha256(text + \0 + voice + \0 + format + \0 + extra)`.
  NUL separator impede colisão (voice="alice"+format="wav" ≠
  voice="alicewav"+format="").

## Trade-offs considerados

| Alternativa | Pros | Cons | Decidido? |
|-------------|------|------|-----------|
| JSONL+sidecar (escolhido) | Zero deps, debug-ável, Git-friendly | 2 syscalls por Get (Stat+Read) | ✅ |
| BoltDB | Embedded KV, Get rápido | CGo + versão pinning | ❌ — CGo bad fit |
| SQLite+WAL | Familiar, indexable | Schema migration burden, ~1MB lib | ❌ — overkill |
| BadgerDB | Pure Go, LSM tree | Mais uma dep, startup cost | ❌ — overengineered |
| in-memory only (status quo) | Já feito | Não persiste | ❌ — gap que estamos fechando |

## Por que JSONL+sidecar venceu

- Zero dependências novas (BoltDB e BadgerDB ambos somam complexidade
  de versionamento de schema; SQLite lib adiciona ~1MB binário).
- Layout "1 entrada = 2 arquivos" é trivial de inspecionar (`ls
  cache/`, `cat <key>.json`, `xxd <key>.wav`).
- Permite streaming write via `WriteFileFromReader` (WriteFile +
  temp+rename atomic) — providers HTTP-based do futuro ganham isso
  sem refactor.
- TTL via `os.Chtimes` modtime: não precisa parsear JSON só pra checar
  freshness no `Has()` (que é chamado em tight loops).

## Bug encontrado durante impl

`Has()` original usava `info.ModTime()` (FS) e `Get()` usava
`entry.CachedAt` (in-JSON). Os dois podiam divergir em alguns segundos
pela precisão do FS (ext4=1ns, FAT32=2s). `TestDiskCache_HasRespectsTTL`
flaky no Windows. Fix: Put chama `os.Chtimes(audioPath, cachedAt, cachedAt)`
e o mesmo no sidecar. Has e Get agora concordam no TTL.

## Settings expostos

- `disk_cache_enabled=true` (default false) — opt-in
- `disk_cache_dir=/path` (default `${THOTH_TTS_ATTACHMENT_DIR}/cache`)
- `disk_cache_ttl=30m` (default 30min, mesmo do voice_attachment reaper)

## Comportamento fail-safe

- `disk_cache_enabled=false` ou `disk_cache_dir=""` → L2 desabilitado
  completamente, zero overhead, L1 alone funciona
- L2 init falha (dir inválido, permission denied) → provider continua
  só com L1 silenciosamente, sem erro
- L2 write falha (disk full) → log silencioso, L1 ainda serve
- L2 read malformed JSON → treat as miss, não panic

## Resultados

- 26 tests novos (18 DiskCache + 8 L1L2 integration), 0 fail
- 1024/1024 tests totais, 0 fail, 0 race
- Performance: L1 hit ~50ns (LRU lookup), L2 hit ~200μs (Stat+Read),
  provider.Generate ~5s (Cebolinha) / ~300ms (Kokoro)

## Próxima (PHASE-34 candidate b)

FFmpeg-based transcoding. O `FFmpegStatus` já existe, falta código
que **use** o FFmpeg pra converter WAV→Opus quando o channel precisa
de Opus nativo (Telegram voice).

