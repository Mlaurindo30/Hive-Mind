# Máquina virgem para o teste de instalação limpa do Hive-Mind.
#
# Simula o que o README promete: "Linux with user systemd, Git, curl, uv,
# Node 18+, Bun and internet access". Nada do Hive-Mind é pré-instalado —
# o clone e o ./install.sh acontecem em runtime, via run-clean-install-test.sh.
#
# systemd roda como PID 1 para que `systemctl --user` (units sinapse-*)
# funcione como numa máquina real.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        systemd systemd-sysv dbus dbus-user-session \
        sudo git curl wget ca-certificates unzip \
        sqlite3 nodejs npm \
        python3 python3-venv \
        build-essential pkg-config \
        locales cron \
    && rm -rf /var/lib/apt/lists/* \
    && locale-gen en_US.UTF-8

ENV LANG=en_US.UTF-8

# Usuário comum, como numa máquina de verdade (uid fixo p/ XDG_RUNTIME_DIR)
RUN userdel -r ubuntu 2>/dev/null || true \
    && useradd -m -u 1000 -s /bin/bash hive \
    && echo 'hive ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/hive

# Pré-requisitos de usuário exigidos pelo install.sh: uv e Bun
USER hive
WORKDIR /home/hive
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && curl -fsSL https://bun.sh/install | bash
ENV PATH="/home/hive/.local/bin:/home/hive/.bun/bin:${PATH}"

USER root
# Não mascarar o user manager: o teste depende de systemd --user
STOPSIGNAL SIGRTMIN+3
CMD ["/lib/systemd/systemd"]
