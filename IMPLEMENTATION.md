# Documento de Implementação — Hive-Mind

## 1. Resumo executivo
O projeto **Hive-Mind** é a evolução do Sinapse Agent. O objetivo é criar uma camada de memória universal e persistente para agentes de IA, utilizando um único banco de dados SQLite centralizado (UMC) que integra as dimensões Estrutural (Grafos), Temporal (Logs) e Associativa (Vetores). O estado atual é de fragmentação entre JSON, SQLite e Chroma. O resultado esperado é uma redução drástica na latência de consulta, maior consistência de dados e uma integração visual rica através do Obsidian.

## 2. Escopo da implementação

### Obrigatório para MVP (Fases 1 e 2) - CONCLUÍDO
- [x] Criação do banco de dados unificado SQLite com suporte a `sqlite-vec` e `FTS5`.
- [x] Refatoração do **Graphify** para indexar o vault diretamente no SQLite.
- [x] Motor de busca híbrido (Texto + Vetor + Grafo) em uma única interface SQL.
- [x] Plugin de leitura unificado para o agente Hermes.

### Recomendado para versão beta (Fases 3 e 4) - CONCLUÍDO
- [x] Migração total dos logs do **claude-mem** para o banco UMC.
- [x] Servidor MCP unificado expondo o UMC para agentes externos (Cursor, Claude Code).
- [x] Dashboard de visualização no Obsidian via plugin SQLite.
- [x] Integração de Logs do RTK.
- [x] Auto-Link Semântico (Soft-Links).

### Fase Atual: Inteligência Superior (Fase 6) - CONCLUÍDO
- [x] **Real-time Watcher:** Sincronização instantânea do Obsidian para o SQLite (fim do gap de 6h).

### Entrega 13 — 09/06/2026 (Ciclo de Sonho Completo & OAuth)
**Resumo da entrega:** Fase 7 concluída. O Hive-Mind agora consolida memórias e sincroniza com o Vault.
**O que foi implementado:**
- **Reflexão Episódica:** Motor que extrai fatos e preferências de observações brutas.
- **Sincronização com o Vault:** Escrita automática de memórias consolidadas em `brain/Consolidated.md`.
- **OAuth Inquebrável:** Fluxo Loopback para Google e Codex-Handshake para OpenAI, permitindo login via terminal.
- **Auto-Discovery de Elite:** Descoberta dinâmica de modelos (incluindo Codex 5.x) em tempo real.
- **UX Maestro:** Interface `setup-dreamer.sh` unificada para todos os provedores.
**Vantagem:** O Ciclo de Sonho agora funciona de ponta a ponta, transformando a atividade diária do agente em conhecimento persistente e legível no Obsidian.

### Fase 8 — Enxame Multi-Máquina (P2P Sync) - CONCLUÍDO
- [x] Migração de IDs para UUID v4 (prevenção de colisões P2P).
- [x] Implementação de Determinismo de Hash no Ciclo de Sonho.
- [x] Swarm Auditor para verificação de integridade entre Vault e SQLite.
- [x] Suporte a sincronização descentralizada via Syncthing.

---

### Próximas Fases
- [x] Fase 9 — Fusão Semântica e Consenso (Semantic Merge). — CONCLUÍDO
- [x] Fase 10 — Memória Visual Avançada (Deep Portal) — EM FINALIZAÇÃO (multimodal docs)

### Fase 2 — Refatoração do Indexador (Graphify 2.0) - OK
### Fase 3 — Unificação Temporal e Motor Híbrido - OK
### Fase 4 — Obsidian como Interface (Portal) - OK
### Fase 6 — Real-time Watcher - OK
### Fase 7 — O Ciclo de Sonho (Hive-Dreamer) - OK

---

## 8. Política de atualização do documento

### Entrega 12 — 10/06/2026 (Início do Hive-Dreamer)
**Resumo da entrega:** Fase 7 iniciada com motor maestro multi-provider.
**O que foi implementado:**
- Criado o motor `scripts/dream_cycle.py`.
- Suporte agnóstico a LLMs: Gemini (Cloud), DeepSeek (Cloud) e Ollama (Local).
- Implementado Estágio 1: Reflexão Episódica (Extração de fatos e preferências).
- Sistema de controle de consolidação via metadados no SQLite.
**Próximos passos:** Implementar escrita automática de fatos no Vault (Estágio 2).

### Entrega 11 — 09/06/2026 (Real-time Watcher)
**Resumo da entrega:** Fase 6 concluída. O Hive-Mind agora é "Cérebro Acordado".
**O que foi implementado:**
- Modificado `graphify/graphify/watch.py` para incluir arquivos `.md` no ciclo de rebuild automático.
- Corrigida lógica de exportação UMC para rodar mesmo quando não há mudança na topologia (garantindo atualização de conteúdo/vetores).
- Criado script de serviço `scripts/start-watcher.sh`.
- Instalada dependência `watchdog` no ambiente virtual.
**Vantagem:** O gap de 6 horas foi eliminado. Qualquer alteração no Obsidian é refletida no SQLite e nos vetores em ~2 segundos.

### Entrega 10 — 09/06/2026 (Criptografia de Segredos & Vault)
**Resumo da entrega:** Implementação do Hive-Mind Vault com criptografia de nível de campo.

---

## 11. Definição geral de pronto
O Hive-Mind está agora em estado de **Sincronização Ativa**. O "sistema nervoso" (SQLite) reage instantaneamente aos estímulos do "corpo" (Obsidian).
