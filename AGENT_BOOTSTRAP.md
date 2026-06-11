# Hive-Mind — Agent Bootstrap & Installation Guide

> **Público-alvo:** Agentes de IA (ou desenvolvedores humanos) realizando instalação limpa.
> **Abordagem:** Instalação ponta a ponta sem dependências bloqueantes ou menus interativos.

---

## 1. Pré-requisitos de Sistema

Antes de iniciar, garanta que os interpretadores e compiladores básicos estejam instalados no PATH do sistema operacional:

```bash
# 1. Dependências do Python (Python 3.10+) e Git
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git curl build-essential

# 2. Node.js (v18+) e Bun (para claude-mem)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt install -y nodejs
curl -fsSL https://bun.sh/install | bash
export PATH="$HOME/.bun/bin:$PATH"

# 3. Rust e Cargo (para compilação do RTK)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
export PATH="$HOME/.cargo/bin:$PATH"

# 4. Ollama (Opcional - para processamento local)
curl -fsSL https://ollama.com/install.sh | sh
```

---

## 2. Bootstrapping Não-Interativo (O Script Principal)

O Hive-Mind possui um instalador integrado (`install.sh`) que faz o clone automático dos repositórios embarcados (`graphify`, `claude-mem`, `neural-memory`, `rtk`), compila os módulos em Rust, instala dependências em Node e Python, e cria os serviços systemd locais.

Para executar o instalador de forma **não-interativa e silenciosa** (ideal para agentes executando scripts em background):

```bash
# 1. Garanta permissão de execução
chmod +x install.sh

# 2. Execute o instalador em modo headless
./install.sh --non-interactive --with-tests
```

*Nota: A flag `--non-interactive` pula a abertura do menu Python interativo (`setup-dreamer.py`) que travaria a entrada padrão (stdin).*

---

## 3. Configuração de Variáveis de Ambiente e Chaves (`.env`)

Após o instalador rodar, crie o arquivo `.env` na raiz do projeto (`$SINAPSE_HOME`) copiando o arquivo de exemplo:

```bash
cp .env.example .env
```

Edite o arquivo `.env` configurando as variáveis necessárias. A lista completa de variáveis requeridas pelo sistema para rodar é:

```env
# ── Gemini API (Google)
GOOGLE_API_KEY="sua_chave_gemini_aqui"

# ── Configuração de Provedor de Consolidação (Dreamer)
HIVE_DREAMER_PROVIDER="google" # Opções: google, anthropic, openai, ollama
HIVE_DREAMER_MODEL="gemini-1.5-flash"

# ── Criptografia de Cofre e Segurança da REST API
HIVE_MIND_API_KEY="sua_chave_secreta_para_rest_api"
HIVE_MIND_MASTER_KEY="gerar_chave_fernet_32_bytes_base64" # Use o script abaixo para gerar
```

*Dica para o agente gerar a `HIVE_MIND_MASTER_KEY`:*
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## 4. Inicialização do Grafo de Conhecimento e Bancos de Dados

Antes de rodar a aplicação, é necessário iniciar o banco SQLite unificado e preencher o Grafo de Conhecimento inicial:

```bash
# 1. Inicializar tabelas e migrações do SQLite (hive_mind.db)
python3 core/database.py

# 2. Reconstruir/gerar o arquivo graph.json inicial a partir do vault cerebro/
./scripts/build-graph.sh
```

---

## 5. Validação da Instalação e Testes

Execute as ferramentas de integridade para garantir que tudo foi instalado e linkado corretamente nas portas padrões:

```bash
# 1. Verificar a saúde de todos os backends da memória (UMC, claude-mem, nmem, rtk)
python3 scripts/sinapse-write.py health

# 2. Rodar a bateria completa de testes da aplicação
./tests/run_all.sh
```

---

## 6. Fluxos de Operação Comuns para Agentes

Uma vez instalado, os agentes de IA podem interagir com a memória do Hive-Mind usando a CLI integrada ou a API REST:

*   **Salvar uma Decisão no Vault:**
    ```bash
    python3 scripts/sinapse-write.py decision --title "Nova Arquitetura" --content "Decidido usar PostgreSQL para..."
    ```
*   **Salvar um Aprendizado:**
    ```bash
    python3 scripts/sinapse-write.py learning --title "Evitar LIKE em JSON no SQLite" --content "Consultas do tipo LIKE..."
    ```
*   **Consultar Conhecimento na Memória Híbrida:**
    ```bash
    python3 scripts/sinapse-write.py query "busca de dados sobre SQLite"
    ```
*   **Finalizar uma Sessão (consolidar estado):**
    ```bash
    python3 scripts/sinapse-write.py session-end --summary "Resumo do trabalho de refatoração do banco de dados"
    ```
