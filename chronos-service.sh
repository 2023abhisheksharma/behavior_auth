#!/usr/bin/env bash
# ==============================================================================
# Chronos-Auth Systemd User Service Manager
# Allows zero-friction installation, management, and autostart on desktop login.
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_FILE="${SYSTEMD_USER_DIR}/chronos-auth.service"
TEMPLATE_FILE="${DIR}/systemd/chronos-auth.service.template"

action="${1:-status}"

print_banner() {
    echo "================================================================"
    echo " 🛡️  Chronos-Auth: Background Systemd Service Manager"
    echo "================================================================"
}

case "$action" in
    install)
        print_banner
        echo "Installing Chronos-Auth as user systemd service..."
        mkdir -p "${SYSTEMD_USER_DIR}"
        
        # Substitute absolute workspace path
        sed "s|@@WORKSPACE_DIR@@|${DIR}|g" "${TEMPLATE_FILE}" > "${SERVICE_FILE}"
        chmod 644 "${SERVICE_FILE}"
        
        echo "Reloading systemd user daemon..."
        systemctl --user daemon-reload
        
        echo "Enabling service to launch automatically on login..."
        systemctl --user enable chronos-auth.service
        
        echo ""
        echo "✅ Chronos-Auth service installed successfully!"
        echo "• Unit File: ${SERVICE_FILE}"
        echo "• Autostart: Enabled on user login"
        echo ""
        echo "To start the background service immediately, run:"
        echo "  ./chronos-service.sh start"
        ;;

    uninstall)
        print_banner
        echo "Uninstalling Chronos-Auth user systemd service..."
        if systemctl --user is-active --quiet chronos-auth.service 2>/dev/null; then
            echo "Stopping active service..."
            systemctl --user stop chronos-auth.service || true
        fi
        
        if [ -f "${SERVICE_FILE}" ]; then
            systemctl --user disable chronos-auth.service 2>/dev/null || true
            rm -f "${SERVICE_FILE}"
            systemctl --user daemon-reload
            echo "✅ Service uninstalled successfully."
        else
            echo "Service file does not exist at ${SERVICE_FILE}."
        fi
        ;;

    start)
        print_banner
        echo "Starting Chronos-Auth systemd service..."
        systemctl --user start chronos-auth.service
        echo "✅ Service started."
        systemctl --user status chronos-auth.service --no-pager
        ;;

    stop)
        print_banner
        echo "Stopping Chronos-Auth systemd service..."
        systemctl --user stop chronos-auth.service
        echo "✅ Service stopped."
        ;;

    restart)
        print_banner
        echo "Restarting Chronos-Auth systemd service..."
        systemctl --user restart chronos-auth.service
        echo "✅ Service restarted."
        systemctl --user status chronos-auth.service --no-pager
        ;;

    status)
        print_banner
        if [ ! -f "${SERVICE_FILE}" ]; then
            echo "⚠️  Chronos-Auth service is NOT installed."
            echo "Run: ./chronos-service.sh install"
            exit 0
        fi
        
        echo "Checking service status..."
        systemctl --user status chronos-auth.service --no-pager || true
        ;;

    *)
        echo "Usage: $0 {install|uninstall|start|stop|restart|status}"
        exit 1
        ;;
esac
