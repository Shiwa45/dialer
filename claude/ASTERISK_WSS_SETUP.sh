# CRITICAL: Asterisk WSS Transport Setup
# ========================================
#
# Your `pjsip show transports` shows ONLY transport-udp.
# WebRTC REQUIRES a WSS (WebSocket Secure) transport.
# Without it, JsSIP can connect but calls WILL FAIL.
#
# Run these commands on your Asterisk server:

# ─── STEP 1: Generate self-signed certificate ────────────────────
sudo mkdir -p /etc/asterisk/keys
cd /etc/asterisk/keys

# Generate self-signed cert (valid for 10 years)
sudo openssl req -x509 -nodes -days 3650 \
    -newkey rsa:2048 \
    -keyout asterisk.key \
    -out asterisk.crt \
    -subj "/CN=192.168.1.60"

# Combine for Asterisk
sudo cat asterisk.crt asterisk.key > asterisk.pem
sudo chown asterisk:asterisk asterisk.*
sudo chmod 600 asterisk.key asterisk.pem


# ─── STEP 2: Enable HTTPS/WSS in http.conf ───────────────────────
# Edit /etc/asterisk/http.conf and ensure it contains:

cat << 'EOF' | sudo tee /etc/asterisk/http.conf
[general]
enabled=yes
bindaddr=0.0.0.0
bindport=8088
tlsenable=yes
tlsbindaddr=0.0.0.0:8089
tlscertfile=/etc/asterisk/keys/asterisk.crt
tlsprivatekey=/etc/asterisk/keys/asterisk.key
EOF


# ─── STEP 3: Add WSS transport to pjsip.conf ─────────────────────
# Add this BEFORE any endpoints in /etc/asterisk/pjsip.conf:
# (Keep your existing transport-udp, just ADD transport-wss)

# Check if transport-wss already exists:
sudo grep -n "transport-wss" /etc/asterisk/pjsip.conf

# If NOT found, add it:
cat << 'EOF' | sudo tee -a /etc/asterisk/pjsip.conf

[transport-wss]
type=transport
protocol=wss
bind=0.0.0.0

EOF


# ─── STEP 4: Reload Asterisk ─────────────────────────────────────
sudo asterisk -rx "module reload res_http_websocket.so"
sudo asterisk -rx "module reload res_pjsip.so"

# Or if that doesn't work:
sudo systemctl restart asterisk


# ─── STEP 5: Verify ──────────────────────────────────────────────
sudo asterisk -rx "pjsip show transports"
# Should now show BOTH:
#   transport-udp    udp    0.0.0.0:5060
#   transport-wss    wss    0.0.0.0

sudo asterisk -rx "http show status"
# Should show:
#   HTTPS Server Enabled and Bound to 0.0.0.0:8089


# ─── STEP 6: Browser cert acceptance ─────────────────────────────
# Since this is a self-signed cert, open this URL in your browser:
#   https://192.168.1.60:8089/
# Click "Advanced" → "Accept the Risk" / "Proceed"
# Do this ONCE per browser. Without this, wss:// connections will fail.


# ─── STEP 7: Firewall ────────────────────────────────────────────
# Ensure port 8089 is open:
sudo ufw allow 8089/tcp 2>/dev/null
sudo firewall-cmd --add-port=8089/tcp --permanent 2>/dev/null
sudo firewall-cmd --reload 2>/dev/null


# ─── ICE_HOST field in Django Phone admin ─────────────────────────
# In your Phone edit page, set ice_host to just:
#   stun:stun.l.google.com:19302
#
# OR leave it EMPTY (the code will use the default STUN).
#
# Do NOT paste JSON arrays into the ice_host field.
# The code now handles parsing automatically.
