---
tags: [decision]
status: active
created: 2026-06-01
updated: 2026-06-01
source: hermes-session
---

# PHASE-33 TTS Integration — Closeout Final

## PHASE-33 TTS Integration — Closeout Final (2026-06-01)

### Status: COMPLETE

Todas as 4 pendências herdadas da entrada THOTH-PHASE33-TTS-INTEGRATION-COMPLETE foram resolvidas com código de produção + tests + race-clean.

### Pendências resolvidas

1. **Discord voice messages (multipart upload)**
   - `Client.SendMessageWithFile(ctx, channelID, content, filePath)` em `internal/channel/discord/client.go`: POST `multipart/form-data` para `/channels/{id}/messages` com `payload_json` + `files[0]`. Streaming via `io.Pipe`.
   - `DiscordAdapter.Send` itera `req.Attachments`, identifica MIME `audio/*` e despacha via `SendMessageWithFile`. Text chunk loop bypassed quando áudio é enviado.

2. **FFmpeg availability check**
   - `FFmpegStatus` struct + `CheckFFmpeg()` / `CheckFFmpegForceRefresh()` em `internal/runtime/voice_attachment.go`. Probe via `exec.LookPath("ffmpeg")` + `ffmpeg -version` com timeout 2s. Cache 5min.

3. **Test cleanup de estado global no `cloud/init_test.go`**
   - Adicionado `Unregister(id tts.ProviderID) bool` em `internal/tts/registry_audio.go` (com tag) e `registry_stub.go` (sem tag).
   - `unregisterForTest()` no `init_test.go` agora usa a API real.

4. **Cache LRU in-memory bounded**
   - `LRUCache` thread-safe em `internal/tts/providers/cache.go` usando `container/list` (front=most-recent, back=least-recent). Capacity configurável, eviction LRU no overflow, `Get` faz promote-to-front.
   - `Kokoro` e `Qwen3` providers inicializam cache via setting `cache_capacity` (default 32/16). `getCachedResult` faz snapshot-copy defensivo.

### Bugs latentes corrigidos durante o fechamento

- `synthesizeVoiceAttachment` panicava com `ttsRegistry == nil` (sem nil-check).
- `synthesizeVoiceAttachment` colocava `voiceID` no `req.Voice.ProviderID`, fazendo o registry tentar rotear para um provider inexistente.
- `Registry.Generate` sobrescrevia `DefaultProvider` com `req.Voice.ProviderID` mesmo quando vazio — agora só override quando `ProviderID != ""`.
- `TestResolveTTSAttachmentDir_DefaultPath` confiava em post-test reset; agora reseta o cache no início.

### Métricas finais

- `go test -tags audio -count=1 ./...` → **48 packages, 992 tests pass, 0 fail, 1 skip**
- `go test -tags audio -count=3 ./...` → **3 execuções × 992 = 2892 passed, 0 fail** (sem intermitência)
- `go test -tags audio -count=1 -race ./internal/channel/{discord,telegram,whatsapp}` → **173 passed, 0 race**

### Documentação

- `docs/DELIVERY_LOG.md` — entrada `THOTH-PHASE33-CLOSEOUT` criada
- `docs/TRACEABILITY_MATRIX.md` — REQ-TTS-001/005/006 atualizadas com fase CLOSEOUT; pendências "(PHASE-34)" removidas para itens que foram entregues; REQ-TTS-002/003 ganharam menção a cache LRU; REQ-TTS-007 ganhou menção a Unregister()

### Próximas opportunities (PHASE-34 candidates)

- Cloud TTS providers com httptest mais profundo
- Discord non-audio attachments (image/video)
- Cache persistente em disco (L2 sobre o L1 in-memory)
- FFmpeg-based transcoding (WAV→Opus) quando provider não suporta Opus nativamente

### Referências cruzadas

- ADR-014: `docs/adr/014-tts-architecture.md`
- Skill class-level: `tts-integration` (references/hermes-tts-patterns.md)
- Fonte original PHASE-33-COMPLETE: `docs/DELIVERY_LOG.md` linha ~4480

