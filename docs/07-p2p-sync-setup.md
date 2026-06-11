# 07 — Configuração P2P Swarm (Enxame Multi-Máquina)

O Hive-Mind suporta a sincronização de memória entre múltiplas máquinas de forma descentralizada, utilizando o **Syncthing** para o transporte de arquivos e o **Swarm Auditor** para garantir a integridade do índice local.

---

## 1. Configuração do Transporte (Syncthing)

O Syncthing é o "músculo" que move os arquivos Markdown entre seus dispositivos de forma segura e P2P.

1.  **Instalação:** Instale o Syncthing em todas as máquinas (PC, Laptop, VPS).
    *   Linux: `sudo apt install syncthing`
    *   Mac/Windows: Baixe em [syncthing.net](https://syncthing.net/)
2.  **Compartilhamento:** Adicione a pasta `cerebro/` do Hive-Mind como uma pasta compartilhada.
3.  **Conexão:** Conecte seus dispositivos usando as IDs exclusivas do Syncthing.
4.  **Configuração Sugerida:**
    *   **Tipo de Pasta:** "Enviar e Receber".
    *   **Versão de Arquivos:** Recomendamos "Versão Simples" (pelo menos 5 versões) para proteger contra edições conflitantes.

---

## 2. Integridade e Auditoria (Swarm Auditor)

Como o Syncthing sincroniza apenas arquivos, o seu banco de dados SQLite local (`hive_mind.db`) pode ficar desatualizado quando novos arquivos chegam de outras máquinas.

### 2.1 O que o Auditor faz?
O script `scripts/audit_memory.py` realiza uma "varredura de consciência":
*   Verifica se todos os arquivos no `cerebro/atlas/` estão indexados no SQLite.
*   Compara o **Hash de Integridade** do arquivo físico com o hash guardado no banco.
*   Se houver divergência (ex: uma nota alterada em outra máquina), ele reindexa o neurônio, atualizando os vetores e a busca textual (FTS).

### 2.2 Como executar a Auditoria
Para apenas verificar o estado da memória:
```bash
python3 scripts/audit_memory.py
```

Para **corrigir** e sincronizar o banco de dados com os novos arquivos recebidos:
```bash
python3 scripts/audit_memory.py --fix
```

---

## 3. Fluxo de Trabalho Recomendado

Para manter seu enxame saudável:

1.  Mantenha o **Syncthing** rodando em segundo plano.
2.  O **Watcher (Fase 6)** tentará atualizar o banco em tempo real para mudanças locais.
3.  Execute o **Auditor** (`--fix`) periodicamente (ou via cron) para garantir que arquivos recebidos via P2P foram processados:
    *   `0 * * * * cd /path/to/hive-mind && python3 scripts/audit_memory.py --fix >> logs/audit.log 2>&1`

---

## 4. Auditoria de Proveniência (Quem disse o quê?)

Cada nota no Atlas contém metadados de proveniência no frontmatter:
```yaml
agent: hermes
trust_level: 2
integrity_hash: ad7b99051a912139
```
Se você notar uma informação estranha, pode rastrear qual agente a gerou e verificar se o hash de integridade ainda é válido usando o script de auditoria.
