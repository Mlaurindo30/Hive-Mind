---
tags: [decision]
status: active
created: 2026-06-09
updated: 2026-06-09
source: hermes-session
---

# Unified Memory Core Architecture Decision

## Decisão: Unificação do Motor de Memória (Unified Memory Core - UMC)

### Contexto
O projeto Sinapse Agent possui atualmente uma arquitetura de memória fragmentada em 5 camadas, utilizando diferentes formatos (JSON, SQLite, Chroma) e linguagens (Python, Node, Rust). Embora funcional, essa fragmentação gera latência, dificuldade de manutenção e inconsistência entre os backends.

### Decisão
Iremos evoluir a arquitetura para o **Unified Memory Core (UMC)**.

1. **Banco de Dados Central:** Utilizaremos um único banco de dados **SQLite** como o "cérebro compartilhado".
2. **Esquema Base:** O esquema do **NeuralMemory** será adotado como a estrutura mestre devido à sua sofisticação na representação de neurônios (nós) e sinapses (arestas/relações).
3. **Integração de Componentes:**
   - **Graphify:** Deixará de gerar `graph.json` e passará a indexar o vault Obsidian diretamente nas tabelas `neurons` e `synapses` do banco UMC.
   - **claude-mem:** Migrará seu armazenamento de observações e timeline para o banco UMC, permitindo que eventos temporais sejam relacionados estruturalmente aos conceitos do vault.
   - **NeuralMemory:** Continuará operando seu motor cognitivo (ativação por espalhamento) sobre este banco unificado.
4. **Busca Vetorial Nativa:** Utilizaremos a extensão `sqlite-vec` para embutir embeddings diretamente no SQLite, eliminando a necessidade de serviços externos como Chroma para a maioria dos casos de uso locais.
5. **Obsidian como SSoT:** O vault continua sendo a fonte única de verdade (arquivos Markdown). O banco UMC é um "índice vivo" ultra-rápido desse vault.

### Consequências
- **Positivas:** Latência reduzida (zero IPC entre backends), sincronização garantida, deploy simplificado (um único arquivo `.db`), maior robustez.
- **Negativas:** Requer refatoração significativa nos plugins de escrita e nos scripts de indexação.
- **Risco:** Desempenho do SQLite com grandes volumes de dados vetoriais (precisa de benchmarking com `sqlite-vec`).

### Próximos Passos
1. Criar um protótipo do banco UMC com o esquema unificado.
2. Modificar o indexador do Graphify para escrever no SQLite.
3. Atualizar o plugin `sinapse-memory.py` para realizar consultas SQL unificadas em vez de chamadas multi-backend.
