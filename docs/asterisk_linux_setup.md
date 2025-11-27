# Linux Autodialer + Asterisk Setup (Native Linux Host)

Use this guide to install Asterisk on a Linux machine and connect it to this autodialer project (Django + PostgreSQL) end to end. Follow the steps in order the first time; afterward you can jump to the section you need. For deeper background, see `docs/asterisk_realtime_setup.md` (Realtime theory) and `docs/agent_calling_quickstart.md` (using the UI).

---

## 0. Know the moving parts

| Component | Purpose | Notes |
| --- | --- | --- |
| Django app (this repo) | Manages agents, campaigns, phones, originate requests | Runs under Gunicorn/devserver. Provides Asterisk realtime tables and ARI/AMI clients. |
| PostgreSQL | Primary DB for Django *and* Asterisk realtime | Must be reachable from the Asterisk host via ODBC. |
| Asterisk | SIP stack + dialer | Reads realtime tables (`ps_endpoints`, `ps_auths`, `ps_aors`) and exposes ARI/AMI for control. |

---

## 1. System prerequisites

Supported: Debian/Ubuntu 20.04+ (commands below use `apt`). For other distros install equivalent packages.

1. Update apt and install toolchain + telephony dependencies:
   ```bash
   sudo apt update
   sudo apt install -y build-essential git curl python3 python3-venv python3-dev \
       asterisk asterisk-core-sounds-en-wav asterisk-moh-opsound-wav \
       unixodbc unixodbc-dev odbc-postgresql dialog
   ```
2. (Optional) Add codecs/media you need (`asterisk-mp3`, `asterisk-codec-g729`, etc.).
3. Ensure ports 5060/UDP (SIP), 10000-20000/UDP (RTP), 8088/TCP (ARI HTTP) and 5038/TCP (AMI) are open on your firewall if agents connect remotely.

---

## 2. PostgreSQL for Django + Asterisk

Install PostgreSQL locally or use an existing server reachable from both Django and Asterisk.

```bash
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql
```

Create a database/user (replace passwords as desired):

```bash
sudo -u postgres psql <<'SQL'
CREATE DATABASE autodialer;
CREATE USER autodialer WITH PASSWORD 'change_me';
ALTER ROLE autodialer WITH LOGIN CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE autodialer TO autodialer;
SQL
```

Allow network access (if Asterisk runs on another host):

1. Edit `/etc/postgresql/<version>/main/postgresql.conf` → set `listen_addresses = '*'`.
2. Edit `/etc/postgresql/<version>/main/pg_hba.conf` → add `host autodialer autodialer 0.0.0.0/0 md5` (or restrict to your subnet).
3. Reload: `sudo systemctl restart postgresql`.

---

## 3. Bootstrap Django locally

1. From the repo root (`/home/shiwansh/dialer`):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
2. Configure DB creds. If you use `.env`, set:
   ```bash
   export DATABASE_URL=postgres://autodialer:change_me@localhost:5432/autodialer
   ```
   Alternatively edit your `settings/*.py` override.
3. Apply migrations and create a superuser:
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```
4. (Optional) Load seed data or run `python manage.py loaddata demo` if you have fixtures.

---

## 4. Generate realtime config from Django

The telephony app ships with `telephony/management/commands/setup_asterisk_realtime.py` to verify tables and emit sample configs.

```bash
python manage.py setup_asterisk_realtime --sync-existing --create-config
```

Outputs:

| File | Destination | Purpose |
| --- | --- | --- |
| `/tmp/res_odbc.conf` | `/etc/asterisk/res_odbc.conf` | Defines DSN for realtime tables. |
| `/tmp/extconfig.conf` | `/etc/asterisk/extconfig.conf` | Maps tables (`ps_*` and optional dialplan). |
| `/tmp/pjsip_realtime.conf` | `/etc/asterisk/pjsip_realtime.conf` | PJSIP include stub (sorcery). |

Inspect the files and adjust DSN/usernames before copying.

---

## 5. Configure ODBC on the Asterisk host

1. **Driver definition** (`/etc/odbcinst.ini`):
   ```ini
   [PostgreSQL]
   Description=PostgreSQL ODBC driver
   Driver=/usr/lib/x86_64-linux-gnu/odbc/psqlodbca.so
   Setup=/usr/lib/x86_64-linux-gnu/odbc/libodbcpsqlS.so
   ```
2. **DSN** (`/etc/odbc.ini`):
   ```ini
   [asterisk]
   Driver=PostgreSQL
   Servername=127.0.0.1         ; or the host where PostgreSQL runs
   Port=5432
   Database=autodialer
   Username=autodialer
   Password=change_me
   ```
3. Test connectivity:
   ```bash
   isql -v asterisk
   ```
   Expect `SQL>`. Exit with `quit`.

---

## 6. Wire realtime + PJSIP

1. Copy the generated files:
   ```bash
   sudo cp /tmp/res_odbc.conf /etc/asterisk/res_odbc.conf
   sudo cp /tmp/extconfig.conf /etc/asterisk/extconfig.conf
   sudo cp /tmp/pjsip_realtime.conf /etc/asterisk/pjsip_realtime.conf
   ```
2. Ensure `res_odbc.conf` includes the DSN `[asterisk]` that matches `/etc/odbc.ini`.
3. In `/etc/asterisk/pjsip.conf`, define or confirm a transport:
   ```ini
   [transport-udp]
   type=transport
   protocol=udp
   bind=0.0.0.0:5060
   ```
4. Include realtime at the bottom of `pjsip.conf`:
   ```
   #include pjsip_realtime.conf
   ```
5. (Optional) Enable realtime dialplan by uncommenting the `extensions` line in `extconfig.conf` and managing contexts in the Django UI (`Telephony → Dialplan`). See the models in `telephony/models.py`.

---

## 7. Enable ARI + AMI for the app

`/etc/asterisk/http.conf`
```ini
[general]
enabled=yes
bindaddr=0.0.0.0
bindport=8088
```

`/etc/asterisk/ari.conf`
```ini
[general]
allowed_origins=*

[autodialer]
type=user
read_only=no
password=<strong-secret>
```

`/etc/asterisk/manager.conf`
```ini
[general]
enabled = yes
webenabled = no

[autodialer]
secret = <another-secret>
read = all,system,call,reporting,originate
write = all,system,call,reporting,originate
```

Record the ARI/AMI credentials; you will need them inside Django (`Telephony → Asterisk Servers`).

---

## 8. Restart and verify Asterisk

```bash
sudo systemctl restart asterisk
sudo asterisk -rx "module show like odbc"
sudo asterisk -rx "odbc show"
sudo asterisk -rx "pjsip show endpoints"
```

`pjsip show endpoints` will list phones after you create them in Django.

---

## 9. Finish configuration inside Django

1. **Add the Asterisk server record**  
   UI path: `Telephony → Asterisk Servers → Create`. Input:
   - Host/Port for ARI (`http://<asterisk-ip>:8088`) plus user/password/application.
   - AMI host/port/user/password.
   - Click “Test Connection” to confirm ARI/AMI reachability (`telephony/services.py:AsteriskService`).

2. **Create a Phone (extension)**  
   `Telephony → Extensions → Create`.
   - Extension number (e.g., `1001`), name, codecs.
   - Select the Asterisk Server.
   - Context defaults to `agents`.
   Saving writes rows to `ps_endpoints`, `ps_auths`, `ps_aors` (see `telephony/models.py:PsEndpoint/PsAuth/PsAor`).

3. **Assign the Phone to an agent user**  
   - Create/choose a user (`Users → Add User`).
   - Edit the Phone and set the `user` field so originate requests know which endpoint to use.

4. **Register a softphone**  
   - SIP server: your Asterisk IP.
   - Username: extension.
   - Password: Phone secret (visible on the extension detail page).
   - Transport: UDP unless you enabled TLS.
   Verify via `asterisk -rx "pjsip show contacts"` or `pjsip show endpoint <ext>`.

### Optional — generate static carrier configs

If you prefer to manage trunks/dialplan with flat files (like GoAutoDial/ViciDial), use the helper command to render all active carriers into `/etc/asterisk/pjsip_custom.conf` and `/etc/asterisk/extensions_custom.conf`:

```bash
sudo .venv/bin/python manage.py render_carrier_configs \
    --pjsip-out /etc/asterisk/pjsip_custom.conf \
    --dialplan-out /etc/asterisk/extensions_custom.conf \
    --context from-campaign
sudo asterisk -rx "pjsip reload"
sudo asterisk -rx "dialplan reload"
```

- Run with `--dry-run` to preview the snippets.
- Include the files once in your main configs (`#include pjsip_custom.conf`, `#include extensions_custom.conf`).
- Carriers without a `dial_prefix` are still rendered to PJSIP but skipped in the dialplan block so you can wire them manually.

---

## 10. Smoke-test the autodialer

1. Start Django services:
   ```bash
   source .venv/bin/activate
   python manage.py runserver 0.0.0.0:8000
   ```
   (Run Celery/Redis if your campaign flow requires it; see `docs/local_dev_setup.md`.)
2. Log in with your agent user → Agent Dashboard.
3. Set agent status to `Available`.
4. Place a call via Agent UI or API:
   ```bash
   http POST http://localhost:8000/telephony/calls/originate/ \
        phone_number=15551234567
   ```
   Monitor `telephony/services.py` logs and `asterisk -rvvvvv`.
5. Confirm CDR/CallLog entries in Django admin and ensure the call leg appears in the Asterisk CLI.

---

## 11. Troubleshooting checklist

- `pjsip show endpoints` empty → verify `/etc/asterisk/extconfig.conf` DSN matches `/etc/odbc.ini`, and that the Django DB has rows in `ps_*` (create a Phone).
- `isql -v asterisk` fails → check PostgreSQL firewall, credentials, and `pg_hba.conf`.
- ARI/AMI tests fail in the UI → confirm `http.conf`, `ari.conf`, `manager.conf` match the host/port you entered and that firewalls allow 8088/5038.
- Softphone cannot register → ensure the Phone secret matches, transport matches the one defined in `pjsip.conf`, and NAT settings (if remote) are correct.
- Originate API errors → tail Django logs, confirm the agent has an assigned Phone and the Asterisk server status is “Connected”.

For advanced dialing logic and ARI hooks, inspect:

- `telephony/services.py` – `AsteriskService`, originate/hangup helpers.
- `telephony/views.py` – originate endpoints around line 1450.
- `docs/asterisk_realtime_setup.md` – deeper dive on realtime tables.
- `docs/agent_calling_quickstart.md` – agent workflow once setup is complete.

---

## 12. Next steps

- Automate this process with Ansible or shell scripts once you validate manually.
- Add monitoring: `asterisk -rx "core show channels"`, `ari show applications`.
- Harden security (fail2ban, strong secrets, TLS transports) before exposing ports publicly.
