#!/usr/bin/env bash
# =============================================================================
# Vault write enforcement (opt-in) — federated-memory EXP-001 hardening
# =============================================================================
# Makes the promotion flow a physical guarantee instead of a convention:
# agents lose direct write access to the vault; only the dedicated service
# user (which runs the Dream Cycle / writers) can promote content into it.
# Agents keep read access and can only deposit into cerebro/90-intake/.
#
# Why not plain chmod by the owner? EXP-001 (federated-memory) showed that
# an adversarial agent instructed to ignore the contract simply writes the
# file — and chmod by the owner is useless because the agent runs AS the
# owner. Real enforcement needs a separate system user.
#
# Usage (requires root):
#   sudo ./scripts/setup/setup-vault-enforcement.sh            # apply
#   sudo ./scripts/setup/setup-vault-enforcement.sh --status   # inspect only
#   sudo ./scripts/setup/setup-vault-enforcement.sh --revert   # undo
#
# After applying:
#   - Run vault-writing services as SERVICE_USER (hive-dreamer), e.g.:
#       sudo -u hive-dreamer python3 scripts/dream/dream_cycle.py --once --real
#   - Agents (running as your user) keep read access via group and write
#     access only in cerebro/90-intake/. core/memory/writers.py falls back
#     to the intake area automatically when a direct write is denied.
# =============================================================================
set -euo pipefail

# Platforms: Linux (useradd/setfacl, tested) and macOS (sysadminctl/chmod +a,
# BETA — validated on paper, not yet on hardware). Windows native uses the
# PowerShell sibling: scripts/setup/setup-vault-enforcement.ps1 (icacls, BETA).
OS_NAME="$(uname -s)"
case "$OS_NAME" in
    Linux|Darwin) ;;
    *)
        echo "ERROR: unsupported platform '$OS_NAME'." >&2
        echo "Windows native: run scripts/setup/setup-vault-enforcement.ps1 as Administrator." >&2
        exit 1
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VAULT_DIR="${VAULT_DIR:-$PROJECT_ROOT/cerebro}"
INTAKE_DIR="$VAULT_DIR/90-intake"
SERVICE_USER="${HIVE_SERVICE_USER:-hive-dreamer}"
SHARED_GROUP="${HIVE_SHARED_GROUP:-hive-mind}"
HUMAN_USER="${SUDO_USER:-$(id -un)}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

stat_owner() {
    if [ "$OS_NAME" = "Darwin" ]; then stat -f '%Su:%Sg' "$1" 2>/dev/null; else stat -c '%U:%G' "$1" 2>/dev/null; fi
}
stat_mode_owner() {
    if [ "$OS_NAME" = "Darwin" ]; then stat -f '%Lp %Su:%Sg' "$1" 2>/dev/null; else stat -c '%a %U:%G' "$1" 2>/dev/null; fi
}

status() {
    echo "Vault:        $VAULT_DIR"
    echo "Owner:        $(stat_owner "$VAULT_DIR" || echo 'n/a')"
    echo "Intake:       $INTAKE_DIR ($(stat_mode_owner "$INTAKE_DIR" || echo 'missing'))"
    echo "Service user: $(id "$SERVICE_USER" 2>/dev/null || echo 'not created')"
    if [ -d "$VAULT_DIR" ] && touch "$VAULT_DIR/.write-probe" 2>/dev/null; then
        rm -f "$VAULT_DIR/.write-probe"
        echo -e "Enforcement:  ${YELLOW}OFF${NC} (current user can write directly to the vault)"
    else
        echo -e "Enforcement:  ${GREEN}ON${NC} (direct vault write denied for current user)"
    fi
}

if [ "${1:-}" = "--status" ]; then
    status
    exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}ERROR${NC} this script needs root (sudo) to create the service user and apply ownership." >&2
    exit 1
fi

if [ ! -d "$VAULT_DIR" ]; then
    echo -e "${RED}ERROR${NC} vault not found at $VAULT_DIR" >&2
    exit 1
fi

if [ "${1:-}" = "--revert" ]; then
    echo "Reverting: returning vault ownership to $HUMAN_USER..."
    chown -R "$HUMAN_USER:$HUMAN_USER" "$VAULT_DIR"
    find "$VAULT_DIR" -type d -exec chmod u+rwx {} +
    find "$VAULT_DIR" -type f -exec chmod u+rw {} +
    echo -e "  ${GREEN}OK${NC} enforcement reverted (service user/group kept; remove manually if desired)."
    exit 0
fi

echo "Applying vault write enforcement..."

# =============================================================================
# macOS branch (BETA — sysadminctl + chmod +a; validated on paper, not on
# hardware yet). Same model: service user owns the vault, human keeps rw via
# ACL, everyone else denied; intake stays group-writable.
# =============================================================================
if [ "$OS_NAME" = "Darwin" ]; then
    echo -e "  ${YELLOW}BETA${NC} macOS enforcement — review output carefully."
    if ! dscl . -read "/Groups/$SHARED_GROUP" >/dev/null 2>&1; then
        gid=$(( $(dscl . -list /Groups PrimaryGroupID | awk '{print $2}' | sort -n | tail -1) + 1 ))
        dscl . -create "/Groups/$SHARED_GROUP" PrimaryGroupID "$gid"
    fi
    if ! id "$SERVICE_USER" >/dev/null 2>&1; then
        sysadminctl -addUser "$SERVICE_USER" -roleAccount -shell /usr/bin/false 2>/dev/null \
            || { echo -e "  ${RED}ERROR${NC} sysadminctl role account creation failed"; exit 1; }
    fi
    dseditgroup -o edit -a "$SERVICE_USER" -t user "$SHARED_GROUP"
    dseditgroup -o edit -a "$HUMAN_USER" -t user "$SHARED_GROUP"
    echo -e "  ${GREEN}OK${NC} user $SERVICE_USER + group $SHARED_GROUP (member: $HUMAN_USER)"

    chown -R "$SERVICE_USER:$SHARED_GROUP" "$VAULT_DIR"
    find "$VAULT_DIR" -type d -exec chmod 750 {} +
    find "$VAULT_DIR" -type f -exec chmod 640 {} +
    # Human editing via macOS ACL (inherited).
    chmod -R +a "user:$HUMAN_USER allow read,write,delete,add_file,add_subdirectory,list,search,file_inherit,directory_inherit" "$VAULT_DIR"
    mkdir -p "$INTAKE_DIR"
    chown "$SERVICE_USER:$SHARED_GROUP" "$INTAKE_DIR"
    chmod 770 "$INTAKE_DIR"
    echo -e "  ${GREEN}OK${NC} vault owned by $SERVICE_USER; intake group-writable: $INTAKE_DIR"
    echo ""
    status
    exit 0
fi

# =============================================================================
# Linux branch (tested)
# =============================================================================
# 1. Shared group (read access for humans/agents) and service user (sole writer).
getent group "$SHARED_GROUP" >/dev/null || groupadd --system "$SHARED_GROUP"
id "$SERVICE_USER" &>/dev/null || useradd --system --no-create-home \
    --shell /usr/sbin/nologin --gid "$SHARED_GROUP" "$SERVICE_USER"
usermod -aG "$SHARED_GROUP" "$HUMAN_USER"
echo -e "  ${GREEN}OK${NC} user $SERVICE_USER + group $SHARED_GROUP (member: $HUMAN_USER)"

# 1b. Path traversal for the service user: the vault usually lives under the
#     human's HOME (e.g. /home/michel, mode 750), which the service user
#     cannot traverse. Grant execute-only (x) ACLs along the path — traverse
#     without listing/reading. Without this, the service user cannot reach
#     the vault at all (observed in the first E2E probe).
if command -v setfacl &>/dev/null; then
    path="$(dirname "$VAULT_DIR")"
    while [ "$path" != "/" ]; do
        if ! sudo -u "$SERVICE_USER" test -x "$path" 2>/dev/null; then
            setfacl -m "u:$SERVICE_USER:x" "$path"
            echo -e "  ${GREEN}OK${NC} traverse ACL (x) for $SERVICE_USER on $path"
        fi
        path="$(dirname "$path")"
    done
else
    echo -e "  ${YELLOW}warn${NC} setfacl unavailable — ensure $SERVICE_USER can traverse the path to the vault."
fi

# 2. Vault: owned by the service user; group reads, others nothing.
#    setgid on directories keeps group inheritance for new files.
chown -R "$SERVICE_USER:$SHARED_GROUP" "$VAULT_DIR"
find "$VAULT_DIR" -type d -exec chmod 2750 {} +
find "$VAULT_DIR" -type f -exec chmod 640 {} +
echo -e "  ${GREEN}OK${NC} vault owned by $SERVICE_USER, group-readable, no direct group write"

# 3. Intake area: the single group-writable surface.
mkdir -p "$INTAKE_DIR"
chown "$SERVICE_USER:$SHARED_GROUP" "$INTAKE_DIR"
chmod 2770 "$INTAKE_DIR"
echo -e "  ${GREEN}OK${NC} intake area group-writable: $INTAKE_DIR"

# 4. Human editing (Obsidian) via ACL — humans are not adversarial agents;
#    the threat model targets automated agents, which should run WITHOUT
#    this ACL (e.g., a separate 'hive-agent' user, or accept group-read only).
if command -v setfacl &>/dev/null; then
    setfacl -R -m "u:$HUMAN_USER:rwX" -m "d:u:$HUMAN_USER:rwX" "$VAULT_DIR"
    echo -e "  ${GREEN}OK${NC} ACL: $HUMAN_USER keeps rw for human editing (Obsidian/Syncthing)"
    echo -e "  ${YELLOW}note${NC} agents running as $HUMAN_USER inherit this ACL. For full"
    echo    "       adversarial enforcement, run agents as a user without the ACL."
else
    echo -e "  ${YELLOW}warn${NC} setfacl not available — $HUMAN_USER has group read-only."
fi

echo ""
status
echo ""
echo "Next steps:"
echo "  - Run vault writers as the service user, e.g.:"
echo "      sudo -u $SERVICE_USER python3 scripts/dream/dream_cycle.py --once --real"
echo "  - Agent writes now land in $INTAKE_DIR (writers fall back automatically)."
