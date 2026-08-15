# Hive-Mind — runtime container (greenfield).
#
# O app NÃO é um pacote puro: `core/`, `scripts/`, `integrations/` e `plugins/`
# rodam a partir do checkout do repositório (sys.path na raiz), então o source
# completo é copiado. O vault (`cerebro/`) é montado como volume pelo compose.
#
# Uso:
#   docker build -t hive-mind .
#   docker compose up -d          # backends + app (ver docker-compose.yml)
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_COMPILE_BYTECODE=1

# Dependências de sistema: build-essential (hnswlib/sqlite-vec), git/curl
# (editables + runtime), libgomp1 (fastembed).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential pkg-config \
        git curl ca-certificates \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# uv (gestor de pacotes canônico do projeto)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Camada de dependências (cache por uv.lock)
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# Source restante (core/, scripts/, integrations/, plugins/, config/)
COPY core ./core
COPY scripts ./scripts
COPY integrations ./integrations
COPY plugins ./plugins
COPY config ./config
COPY templates ./templates

# Vault é volume (não copiado na imagem)
RUN mkdir -p /app/cerebro /app/logs /app/.hive-mind/state

EXPOSE 37702 37780

# Daemon control-plane em modo managed + HTTP loopback.
# O vault e o hive_mind.db são montados pelo docker-compose.
CMD ["uv", "run", "hive-mindd", "run", "--serve", "--host", "0.0.0.0", "--port", "37780"]
