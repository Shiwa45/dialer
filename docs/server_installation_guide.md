# Autodialer Manual Installation Guide

This guide provides step-by-step instructions to manually install and configure the Autodialer system on a fresh Ubuntu 24.04 server.

## 1. System Dependencies

First, update your system and install the required packages.

```bash
sudo apt-get update
sudo apt-get install -y \
  python3-venv python3-dev build-essential \
  libpq-dev postgresql postgresql-contrib \
  redis-server \
  unixodbc odbc-postgresql \
  asterisk
```

Enable and start the services:
```bash
sudo systemctl enable --now redis-server
sudo systemctl enable --now postgresql
sudo systemctl enable --now asterisk
```

## 2. PostgreSQL Database Setup

Create the database user and database. Replace `Shiwansh@123` with your desired password (update `.env` later).

```bash
# Enter postgres shell
sudo -u postgres psql

# Run inside sql shell:
CREATE USER postgres WITH PASSWORD 'Shiwansh@123';
ALTER USER postgres WITH PASSWORD 'Shiwansh@123';
CREATE DATABASE autodialer_db OWNER postgres;
\q
```

## 3. Asterisk Configuration

> [!TIP]
> **Example Configuration Files**: You can find a complete set of example configuration files in the `asterisk_configs_example/` directory of this repository. You can copy them to `/etc/asterisk/` and edit as needed.

You need to create or edit the following files in `/etc/asterisk/`.

### 3.1. Database Connector (`/etc/asterisk/res_odbc.conf`)
Configure Asterisk to talk to PostgreSQL.
```ini
[asterisk]
enabled => yes
dsn => asterisk
username => postgres
password => Shiwansh@123
pre-connect => yes
max_connections => 20
```

### 3.2. Realtime Mapping (`/etc/asterisk/extconfig.conf`)
Tell Asterisk to load endpoints/auths from the database.
```ini
[settings]
ps_endpoints => odbc,asterisk,ps_endpoints
ps_auths => odbc,asterisk,ps_auths
ps_aors => odbc,asterisk,ps_aors
```

### 3.3. PJSIP Sorcery (`/etc/asterisk/sorcery.conf`)
Map internal objects to database tables.
```ini
[res_pjsip]
endpoint=realtime,ps_endpoints
aor=realtime,ps_aors
auth=realtime,ps_auths
```

### 3.4. PJSIP Include (`/etc/asterisk/pjsip_realtime.conf`)
Config for realtime transport.
```ini
; Transport should be defined in main pjsip.conf
; [transport-udp]
; type=transport
; protocol=udp
; bind=0.0.0.0:5060
```

### 3.5. Update MainConfigs
You must include the above files in the main Asterisk configs.

**Edit `/etc/asterisk/pjsip.conf`**:
Add these lines at the end:
```ini
#include pjsip_realtime.conf
#include pjsip_custom.conf
```

**Edit `/etc/asterisk/extensions.conf`**:
Add this line at the end:
```ini
#include extensions_custom.conf
```

### 3.6. Custom Carrier Config & Dialplan (Automated)

Instead of manually editing `pjsip_custom.conf` and `extensions_custom.conf`, you can use the built-in management command to generate them from your database carriers.

**Command:**
```bash
cd /opt/autodialer/dialer
source env/bin/activate
python manage.py render_carrier_configs
```
*Reload Asterisk after running this command: `sudo asterisk -rx "core reload"`*

If you prefer to configure manually, see the examples below.

### 3.7. Custom Carrier Config (Manual Example) (`/etc/asterisk/pjsip_custom.conf`)
Define your trunk/carrier here. Example for OpenVox:
```ini
[openvox]
type=endpoint
transport=transport-udp
context=from-campaign
disallow=all
allow=ulaw,alaw,gsm
aors=openvox_aor
rewrite_contact=yes
dtmf_mode=rfc2833
rtp_symmetric=yes
force_rport=yes
direct_media=no
from_domain=192.168.1.113

[openvox_aor]
type=aor
max_contacts=1
remove_existing=yes
qualify_frequency=60
contact=sip:192.168.1.113:5060

[openvox-identify]
type=identify
endpoint=openvox
match=192.168.1.113
```

### 3.7. Custom Dialplan (`/etc/asterisk/extensions_custom.conf`)
Handles outbound calls and AMD (Answering Machine Detection).
```ini
[from-campaign]
exten => _X.,1,NoOp(Outbound Campaign Call to ${EXTEN})
 same => n,Set(CHANNEL(hangup_handler_push)=hangup-handler,s,1)
 same => n,Set(DIAL_TIMEOUT=${DIAL_TIMEOUT:-30})
 same => n,GotoIf($["${AMD_ENABLED}" = "1"]?find_carrier:dial_direct)
 same => n(dial_direct),Dial(PJSIP/openvox/sip:${EXTEN}@192.168.1.113:5060,${DIAL_TIMEOUT},U(amd-handler^${CALL_TYPE}^${CAMPAIGN_ID}^${LEAD_ID}^${HOPPER_ID}))
 same => n,Hangup()

[amd-handler]
exten => s,1,NoOp(AMD Check)
 same => n,GotoIf($["${AMD_ENABLED}" = "1"]?run_amd:send_to_stasis)
 same => n(run_amd),AMD()
 same => n,GotoIf($["${AMDSTATUS}" = "MACHINE"]?machine:send_to_stasis)
 same => n(machine),Hangup()
 same => n(send_to_stasis),Stasis(autodialer,${CALL_TYPE},${CAMPAIGN_ID},${LEAD_ID},${HOPPER_ID})
 same => n,Return()

[hangup-handler]
exten => s,1,Return()
```

### 3.8. ODBC System Config (`/etc/odbc.ini` and `/etc/odbcinst.ini`)

**/etc/odbcinst.ini**:
```ini
[PostgreSQL Unicode]
Description=PostgreSQL ODBC driver (Unicode)
Driver=/usr/lib/x86_64-linux-gnu/odbc/psqlodbcw.so
Setup=/usr/lib/x86_64-linux-gnu/odbc/libodbcpsqlS.so
UsageCount=1
```

**/etc/odbc.ini**:
```ini
[asterisk]
Description=Asterisk Realtime DB
Driver=PostgreSQL Unicode
Servername=127.0.0.1
Port=5432
Database=autodialer_db
Username=postgres
Password=Shiwansh@123
ReadOnly=No
```

## 4. Application Setup

### Repository & Env
Clone the repo and create the environment:
```bash
git clone git@github.com:Shiwa45/dialer.git
cd dialer
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

### Environment Variables
Create a `.env` file in the project root:
```ini
DB_NAME=autodialer_db
DB_USER=postgres
DB_PASSWORD=Shiwansh@123
DB_HOST=127.0.0.1
DB_PORT=5432
REDIS_URL=redis://127.0.0.1:6379/0
USE_REDIS=1
```

### Database & Static Files
```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

## 5. Running the System

Start the services using the provided script or manually:
```bash
./start_autodialer.sh
```

Or manually run:
1.  **Django (Daphne)**: `daphne -b 0.0.0.0 -p 8000 autodialer.asgi:application`
2.  **ARI Worker**: `python manage.py ari_worker`
3.  **Hopper**: `python manage.py hopper_fill`
4.  **Dialer**: `python manage.py predictive_dialer`
