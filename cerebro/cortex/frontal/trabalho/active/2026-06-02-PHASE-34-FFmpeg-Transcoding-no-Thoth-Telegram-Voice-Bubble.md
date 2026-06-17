---
tags: [decision]
status: active
created: 2026-06-02
updated: 2026-06-02
source: hermes-session
---

# PHASE-34 FFmpeg Transcoding no Thoth (Telegram Voice Bubble)

Implementado transcoding local no Thoth (sem depender do wrapper Python do Hermes) para converter áudio não-OGG em OGG/Opus antes do envio ao Telegram como Voice.

Resumo:
- Novo pacote: internal/audio/transcoder.go
- API: Transcode + WAVToOpusCached + MP3ToOpusCached
- Cache L3 por arquivo (sha256(input+opts), TTL)
- Erro explícito quando ffmpeg indisponível: ErrFFmpegUnavailable
- Wiring no adapter Telegram via transcodeToVoiceBestEffort
- Sem quebra de delivery: falha de transcode mantém fallback legado (telebot.Audio)
- Testes: pacote audio + telegram helper + suíte completa com race

Motivação:
- Hermes já tinha caminho Python (_convert_to_opus), mas Thoth precisava capacidade nativa no runtime Go para evitar dependência operacional cruzada.
- Reuso de conceito do Hermes (ffmpeg + opus mono 64k), sem acoplamento ao código Python do Hermes.

Evidência:
- go test -count=1 ./internal/audio/... ./internal/channel/telegram/... -> 139 pass
- go test -tags audio -count=1 -race ./... -> 1036 pass, 0 fail, 0 race

Trade-off:
- Melhor isolamento do Thoth.
- Introduz cache local .transcode-cache por diretório de attachment; próxima otimização é integrar com reaper global.
