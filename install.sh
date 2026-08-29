#!/usr/bin/env bash
echo "Installing script, systemd files." 

# Exit immediately if a command exits with a non-zero status
set -e

# Configuration variables
RUN_USER="upawar"
REPO_URL="https://github.com/uttampc1/machinesapp.git"

INSTALL_BIN_DIR="/usr/local/bin"
LIST_MACHINES="${INSTALL_BIN_DIR}/list_machines"
REMINDER_SCRIPT="${INSTALL_BIN_DIR}/machine_reservation_reminder.sh"

INSTALL_APP_DIR="/opt/machinesapp"
SERVICE_NAME="machinesapp.service"

APP_DB_DIR="/var/lib/machinesapp"

SERVICE_DIR="/etc/systemd/system"
RESERVATION_REMINDER_SERVICE="${SERVICE_DIR}/machine_reservation_reminder.service"
RESERVATION_REMINDER_TIMER="${SERVICE_DIR}/machine_reservation_reminder.timer"
MACHINESAPP_ISALIVE_SERVICE="${SERVICE_DIR}/machinesapp-isalive.service"
MACHINESAPP_ISALIVE_TIMER="${SERVICE_DIR}/machinesapp-isalive.timer"
RESERVATION_WEB_SERVICE="${SERVICE_DIR}/${SERVICE_NAME}"

echo "=== Starting Installation for $SERVICE_NAME ==="

# 1. Install system dependencies
echo "Installing system packages..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git

# 2. Create a dedicated system user for security
if ! id "$RUN_USER" &>/dev/null; then
    echo "Creating system user: $RUN_USER..."
    sudo useradd -r -s /bin/false "$RUN_USER"
fi

# Create a DB directory
sudo mkdir -p  "$APP_DB_DIR"
sudo chown     "$RUN_USER":"$RUN_USER" "$APP_DB_DIR"
sudo chmod 755 "$APP_DB_DIR"

# 3. Clone the repository
echo "Cloning repository into $INSTALL_APP_DIR..."
if [ -d "$INSTALL_APP_DIR" ]; then
    echo "Directory $INSTALL_APP_DIR already exists. Removing old files..."
    sudo rm -rf "$INSTALL_APP_DIR"
fi
sudo git clone "$REPO_URL" "$INSTALL_APP_DIR"

# 4. Set up Python Virtual Environment
echo "Setting up Python virtual environment..."
sudo python3 -m venv "$INSTALL_APP_DIR/venv"

# 5. Install Python dependencies
echo "Installing requirements from requirements.txt..."
sudo "$INSTALL_APP_DIR/venv/bin/pip" install --upgrade pip
sudo "$INSTALL_APP_DIR/venv/bin/pip" install -r "$INSTALL_APP_DIR/requirements.txt"

# Ensure gunicorn is installed to serve Flask in production
sudo "$INSTALL_APP_DIR/venv/bin/pip" install gunicorn

# 6. Set proper ownership permissions
echo "Setting permissions..."
sudo chown -R "$RUN_USER":"$RUN_USER" "$INSTALL_APP_DIR"

# 7. Copy the Systemd Service File
echo "Copy systemd service configuration..."
INSTALL_CONFIG_DIR="/usr/local/etc"
sudo mkdir -p "$INSTALL_CONFIG_DIR"
sudo cp ./reservation.config                 "${INSTALL_CONFIG_DIR}/reservation.config"
sudo cp machinesapp.service                  "${RESERVATION_WEB_SERVICE}"
sudo cp machine_reservation_reminder.sh      "${REMINDER_SCRIPT}"
sudo cp machine_reservation_reminder.service "${RESERVATION_REMINDER_SERVICE}"
sudo cp machine_reservation_reminder.timer   "${RESERVATION_REMINDER_TIMER}"
sudo cp machinesapp-isalive.service          "${MACHINESAPP_ISALIVE_SERVICE}"
sudo cp machinesapp-isalive.timer            "${MACHINESAPP_ISALIVE_TIMER}"

sudo chmod 444 "${INSTALL_CONFIG_DIR}/reservation.config"
sudo chmod 644 "${RESERVATION_WEB_SERVICE}"
sudo chmod 644 "${RESERVATION_REMINDER_SERVICE}"
sudo chmod 644 "${RESERVATION_REMINDER_TIMER}"

# 8. Enable and Start the Service
echo "Reloading systemd, enabling and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl enable --now "$RESERVATION_REMINDER_TIMER"
sudo systemctl restart "$SERVICE_NAME"

echo "Waiting for service..."
sleep 2

if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "Service started successfully."
else
    echo "ERROR: $SERVICE_NAME failed to start"
    sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
    sudo journalctl -xeu "$SERVICE_NAME" --no-pager || true
    exit 1
fi

sudo systemctl enable --now machine_reservation_reminder.timer

echo "=== Installation Completed Successfully! ==="
echo "Service status:"
sudo systemctl status "$SERVICE_NAME" --no-pager
sudo systemctl status machine_reservation_reminder.timer --no-pager
echo "Check the log: journalctl -u machinesapp-isalive.service -n 50 --no-pager"
