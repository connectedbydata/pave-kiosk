#!/bin/bash

# Kiosk Security Policy Installer
# Configures Chromium/Chrome policies to whitelist only allowed domains.
# MUST be run with sudo privileges.

if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run this script with sudo (e.g., sudo ./setup_security_policy.sh)" >&2
    exit 1
fi

echo "=================================================="
echo "Installing Kiosk Browser Security Policies..."
echo "=================================================="

# Policy content whitelisting local flask app, kiosk domains, and YouTube embeds
POLICY_JSON='{
  "URLBlocklist": [
    "*"
  ],
  "URLAllowlist": [
    "http://localhost:*/*",
    "http://127.0.0.1:*/*",
    "https://pave.pairs.site/*",
    "https://www.letstalkai.org.uk/*",
    "https://www.citizens-track.org/*",
    "https://citizens-track.org/*",
    "https://*.youtube.com/*",
    "https://*.youtube-nocookie.com/*",
    "https://*.ytimg.com/*",
    "https://fonts.googleapis.com/*",
    "https://fonts.gstatic.com/*"
  ],
  "AutofillAddressEnabled": false,
  "AutofillCreditCardEnabled": false,
  "PasswordManagerEnabled": false
}'

# Target directories for Chromium (standard on Raspberry Pi OS) and Google Chrome (general Linux)
CHROMIUM_DIR="/etc/chromium/policies/managed"
CHROME_DIR="/etc/opt/chrome/policies/managed"

install_policy() {
    local target_dir="$1"
    local browser_name="$2"
    
    echo "Setting up policy for $browser_name..."
    mkdir -p "$target_dir"
    echo "$POLICY_JSON" > "$target_dir/kiosk_whitelist_policy.json"
    chmod 644 "$target_dir/kiosk_whitelist_policy.json"
    echo "✓ Policy installed at $target_dir/kiosk_whitelist_policy.json"
}

# Install policies
install_policy "$CHROMIUM_DIR" "Chromium"
install_policy "$CHROME_DIR" "Google Chrome"

echo "=================================================="
echo "Security Policy Installation Complete!"
echo "Please restart your Chromium/Chrome browser for the"
echo "policies to take effect."
echo "=================================================="
