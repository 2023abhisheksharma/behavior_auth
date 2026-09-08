#!/usr/bin/env bash
# ==============================================================================
# Chronos-Auth Desktop Launcher Installer
# Installs application menu shortcuts and desktop icons with high-res branding.
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS_DIR="${HOME}/.local/share/applications"
DESKTOP_DIR="${HOME}/Desktop"
TEMPLATE="${DIR}/assets/chronos-auth.desktop.template"

echo "================================================================"
echo " 🖥️  Chronos-Auth: Desktop Launcher Setup"
echo "================================================================"

# Ensure assets exist
if [ ! -f "${DIR}/assets/chronos-auth.png" ]; then
    echo "Generating application branding assets..."
    "${DIR}/python_engine/venv/bin/python" -c "
import sys
from pathlib import Path
sys.path.insert(0, '${DIR}/python_engine')
from chronos_auth.tray_manager import generate_and_save_assets
generate_and_save_assets(Path('${DIR}/assets'))
"
fi

mkdir -p "${APPS_DIR}"

# 1. Install into Application Menu
TARGET_DESKTOP="${APPS_DIR}/chronos-auth.desktop"
sed "s|@@WORKSPACE_DIR@@|${DIR}|g" "${TEMPLATE}" > "${TARGET_DESKTOP}"
chmod +x "${TARGET_DESKTOP}"
echo "✅ Installed to application menu: ${TARGET_DESKTOP}"

# 2. Update desktop database if command available
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "${APPS_DIR}" 2>/dev/null || true
fi

# 3. Install to ~/Desktop if folder exists
if [ -d "${DESKTOP_DIR}" ]; then
    DESK_TARGET="${DESKTOP_DIR}/Chronos-Auth.desktop"
    sed "s|@@WORKSPACE_DIR@@|${DIR}|g" "${TEMPLATE}" > "${DESK_TARGET}"
    chmod +x "${DESK_TARGET}"
    if command -v gio &> /dev/null; then
        gio set "${DESK_TARGET}" "metadata::trusted" yes 2>/dev/null || true
    fi
    echo "✅ Installed to user Desktop: ${DESK_TARGET}"
fi

echo ""
echo "Chronos-Auth is now accessible from your system application menu!"
