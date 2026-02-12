#!/bin/bash
# SSL Certificate Generator for Asterisk WebRTC
# This script creates self-signed SSL certificates for Asterisk WSS (WebSocket Secure)

set -e

echo "=========================================="
echo "  Asterisk WebRTC SSL Certificate Setup"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  This script needs sudo privileges to create certificates in /etc/asterisk/keys/"
    echo "Please run with: sudo bash $0"
    exit 1
fi

# Create keys directory if it doesn't exist
KEYS_DIR="/etc/asterisk/keys"
echo "📁 Creating keys directory..."
mkdir -p "$KEYS_DIR"
cd "$KEYS_DIR"

# Get server IP address
echo ""
echo "🔍 Detecting server IP address..."
SERVER_IP=$(hostname -I | awk '{print $1}')
echo "   Detected IP: $SERVER_IP"
echo ""

# Prompt for custom IP if needed
read -p "Is this the correct IP for Asterisk? (y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    read -p "Enter the correct IP address: " SERVER_IP
fi

echo ""
echo "🔐 Generating SSL certificate for $SERVER_IP..."
echo ""

# Generate private key
openssl genrsa -out asterisk.key 2048

# Generate certificate signing request (CSR)
openssl req -new -key asterisk.key -out asterisk.csr -subj "/C=US/ST=State/L=City/O=Organization/OU=IT/CN=$SERVER_IP"

# Generate self-signed certificate valid for 10 years
openssl x509 -req -days 3650 -in asterisk.csr -signkey asterisk.key -out asterisk.crt

# Create combined PEM file (required by Asterisk)
cat asterisk.crt asterisk.key > asterisk.pem

# Set proper permissions
chmod 600 asterisk.key asterisk.pem
chmod 644 asterisk.crt
chown asterisk:asterisk asterisk.* 2>/dev/null || chown root:root asterisk.*

# Clean up CSR
rm asterisk.csr

echo ""
echo "✅ SSL certificates created successfully!"
echo ""
echo "📄 Files created in $KEYS_DIR:"
ls -lh "$KEYS_DIR"/asterisk.*
echo ""

# Update http.conf
HTTP_CONF="/etc/asterisk/http.conf"
echo "📝 Updating Asterisk HTTP configuration..."

# Backup original http.conf
if [ -f "$HTTP_CONF" ]; then
    cp "$HTTP_CONF" "${HTTP_CONF}.backup_$(date +%Y%m%d_%H%M%S)"
    echo "   Backed up: ${HTTP_CONF}.backup_$(date +%Y%m%d_%H%M%S)"
fi

# Create or update http.conf
cat > "$HTTP_CONF" << EOF
[general]
enabled=yes
bindaddr=0.0.0.0
bindport=8088

; Enable TLS/SSL for WebSocket Secure (WSS)
tlsenable=yes
tlsbindaddr=0.0.0.0:8089
tlscertfile=$KEYS_DIR/asterisk.pem
tlsprivatekey=$KEYS_DIR/asterisk.key

; Optional: increase session limits if needed
sessionlimit=1000
session_inactivity=30000
session_keep_alive=15000
EOF

echo "   Updated: $HTTP_CONF"
echo ""

# Reload Asterisk HTTP module
echo "🔄 Reloading Asterisk HTTP module..."
asterisk -rx "module reload res_http_websocket.so" 2>/dev/null || echo "   (Asterisk may need full restart)"
asterisk -rx "http show status" 2>/dev/null || echo "   (Run 'sudo asterisk -rx \"http show status\"' to verify)"
echo ""

echo "=========================================="
echo "  ✅ SSL Certificate Setup Complete!"
echo "=========================================="
echo ""
echo "📋 Next Steps:"
echo ""
echo "1. Restart Asterisk to apply changes:"
echo "   sudo systemctl restart asterisk"
echo ""
echo "2. Verify WSS is listening on port 8089:"
echo "   sudo netstat -tlnp | grep 8089"
echo ""
echo "3. Accept certificate in browser:"
echo "   Open: https://$SERVER_IP:8089/"
echo "   Click 'Advanced' → 'Proceed to $SERVER_IP (unsafe)'"
echo ""
echo "4. Update Django Phone settings:"
echo "   - ICE Host: stun:stun.l.google.com:19302"
echo "   - WebRTC Enabled: ✓ Checked"
echo ""
echo "5. Test WebRTC connection:"
echo "   - Log in as WebRTC agent"
echo "   - Should see green dot + 'Registered'"
echo ""
echo "Certificate Details:"
echo "  Location: $KEYS_DIR/asterisk.pem"
echo "  Valid for: 10 years"
echo "  IP Address: $SERVER_IP"
echo ""
