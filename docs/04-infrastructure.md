# 04 — Infraestrutura e Escopo

> **Hive-Mind v2.0.0** — Requisitos, serviços, sincronização P2P e variáveis de ambiente.

---

## 1. Requisitos de Software

### Runtime

| Dependência | Versão | Uso |
|-------------|--------|-----|
| Python | 3.10+ | Núcleo do sistema, scripts de IA, MCP |
| SQLite | 3.44+ | Unified Memory Core com `sqlite-vec` |
| Syncthing | 1.27+ | Sincronização P2P de arquivos Markdown |
| uv | 0.4+ | Gerenciador de pacotes Python |

### Bibliotecas de Ingestão (Fase 10)
- `pypdf`: Extração de texto de PDFs.
- `python-docx`: Leitura de documentos Word.
- `PyMuPDF` (fitz): Extração de imagens de documentos.
- `mss`: Captura de tela de alta performance.

---

## 2. Variáveis de Ambiente (.env)

O Hive-Mind é configurado via arquivo `.env` na raiz do projeto. Nomes de modelos nunca devem ser hardcoded nos scripts.

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `SINAPSE_HOME` | Caminho raiz do projeto | `/home/user/hive-mind` |
| `HIVE_DREAMER_PROVIDER` | Provedor de LLM para consolidação | `google`, `openai`, `deepseek`, `ollama` |
| `HIVE_DREAMER_MODEL` | Modelo específico para o Ciclo de Sonho | `gemini-2.0-flash`, `gpt-4o`, `deepseek-v3` |
| `OLLAMA_LOCAL` | URL do Ollama se provedor for local | `http://localhost:11434` |
| `GOOGLE_API_KEY` | Chave de API para Google/Gemini | `AIza...` |
| `OPENAI_API_KEY` | Chave de API para OpenAI/Codex | `sk-...` |

---

## 3. Serviços e Daemonização

### Real-time Watcher (Sistema Nervoso)
O serviço `scripts/start-watcher.sh` deve rodar em background. Ele utiliza a biblioteca `watchdog` para detectar mudanças em `cerebro/` e atualizar o `hive_mind.db` instantaneamente.

### Swarm Sync (Syncthing)
A sincronização P2P é delegada ao **Syncthing**. 
- Compartilhe a pasta `cerebro/` entre suas máquinas.
- O Hive-Mind detectará arquivos recebidos e disparará o **Swarm Auditor** para integridade.

---

## 4. Cron Jobs e Manutenção

O rebuild de 6 horas foi substituído pelo Watcher em tempo real. Os crons agora são focados em manutenção de saúde:

```cron
# Auditoria de integridade e resolução de conflitos (1x por hora)
0 * * * * cd $SINAPSE_HOME && ./scripts/audit_memory.py --fix >> logs/audit.log 2>&1

# Backup completo do banco UMC (diário às 3am)
0 3 * * * cp $SINAPSE_HOME/hive_mind.db $SINAPSE_HOME/backups/hive_mind_$(date +\%F).db
```

---

## 5. Estrutura de Diretórios (v2.0.0)

```
~/Documentos/Projects/Hive-Mind/
├── cerebro/                         # Vault Obsidian (Fonte de Verdade)
│   ├── atlas/                       # Conhecimento estruturado (Markdown)
│   ├── inbox/                       # Dados brutos recebidos (Temporal)
│   │   ├── visual/                  # Screenshots capturados
│   │   └── documents/               # PDFs e DOCXs para processamento
│   └── conflicts/                   # Arquivo de conflitos P2P resolvidos
├── core/                            # Código fonte do UMC e Schemas
├── scripts/                         # Ferramentas operacionais e Ciclo de Sonho
└── hive_mind.db                     # O Unified Memory Core (SQLite)
```

---

## 8. Segurança

### 8.1 Princípios

1. **Nenhuma porta exposta à rede externa.** Todos os serviços escutam em localhost ou usam stdio.
2. **API keys no `.env`**, nunca commitadas (`.gitignore`).
3. **Dry-run mode** disponível para testes sem side effects.
4. **Atomic writes** previnem corrupção de arquivos em falhas.

### 8.2 Arquivos Sensíveis

| Arquivo | Conteúdo | Proteção |
|---------|----------|----------|
| `.env` | `GOOGLE_API_KEY`, tokens | `.gitignore`, permissões 600 |
| `.env.example` | Template sem valores reais | Commitado |
| `claude-mem/data/` | Observações, embeddings | `.gitignore` |
| `graphify-out/cache/` | Cache regenerável | `.gitignore` |

### 8.3 Superfície de Ataque

| Vetor | Risco | Mitigação |
|-------|-------|-----------|
| Worker HTTP (37700) | Acesso local não autorizado | `127.0.0.1` only |
| Injeção em queries | MCP/CLI recebe input arbitrário | Regex sanitization, timeouts |
| Path traversal | Escrita de arquivos no vault | `_sanitize_slug()` remove `/`, `..` |
| JSON injection | graph.json parsing | `json.load()` + schema validation |

---

## 9. Escopo do Sistema

### 9.1 O que o Sinapse Agent FAZ

- ✅ Indexa vault Obsidian em knowledge graph queryable
- ✅ Trackeia eventos de agentes com busca temporal (FTS5 + Chroma)
- ✅ Otimiza comandos shell em tempo real (RTK)
- ✅ Fornece busca associativa (spreading activation)
- ✅ Injeta contexto do vault automaticamente no prompt (Hermes, Claude Code, Codex)
- ✅ Salva decisões e aprendizados no vault automaticamente
- ✅ Funciona offline (fallback determinístico sem LLMs)
- ✅ Suporta múltiplos agentes via 3 métodos de integração

### 9.2 O que o Sinapse Agent NÃO FAZ

- ❌ Não substitui o Obsidian como editor de vault
- ❌ Não é um agente de IA (é uma camada de memória para agentes)
- ❌ Não treina modelos próprios
- ❌ Não faz busca na internet
- ❌ Não gerencia autenticação de usuários
- ❌ Não é um banco de dados distribuído

---

## 10. Deploy Típico

```
┌─────────────────────────────────────────────────┐
│                 VPS / Servidor Local              │
│                                                   │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ Ollama   │  │ claude-  │  │ Graphify       │  │
│  │ (LLMs)   │  │ mem      │  │ (indexador)    │  │
│  │ :11434   │  │ :37700   │  │ stdio MCP      │  │
│  └──────────┘  └──────────┘  └───────────────┘  │
│                                                   │
│  ┌──────────────────────────────────────────┐    │
│  │        sinapse-memory (plugin/MCP)        │    │
│  │  ┌─────────┐  ┌────────┐  ┌───────────┐  │    │
│  │  │ nmem    │  │HTTP API│  │ graph.json │  │    │
│  │  │ recall  │  │ client │  │ reader     │  │    │
│  │  └─────────┘  └────────┘  └───────────┘  │    │
│  └──────────────────────────────────────────┘    │
│                       │                           │
│                       ▼                           │
│  ┌──────────────────────────────────────────┐    │
│  │           Vault Obsidian (cerebro/)       │    │
│  │           ~200 arquivos .md               │    │
│  └──────────────────────────────────────────┘    │
│                                                   │
│  Cron (6h): build-graph.sh                        │
│  Cron (dom): sync-diario.sh                       │
└─────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
   ┌──────────┐                  ┌──────────┐
   │ Hermes   │                  │ Claude   │
   │ (plugin) │                  │ Code     │
   └──────────┘                  │ (MCP)    │
                                 └──────────┘
```
