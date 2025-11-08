# Autodialer ↔ Asterisk Realtime Integration Guide

This guide explains how to connect the telephony app to your Asterisk server, create extensions, assign them to agents, and place calls. It leverages Asterisk Realtime (PJSIP) using database tables managed by Django.

## Overview

- The telephony app supports Asterisk Realtime via PJSIP tables: `ps_endpoints`, `ps_auths`, `ps_aors`, plus optional `extensions_table` for dialplan.
- Creating a Phone in the UI writes to those Asterisk tables automatically (in `telephony.models.Phone.save()`), so endpoints are provisioned dynamically.
- A management command generates Asterisk config snippets and verifies realtime tables.

---

## 1) Prepare the database for Asterisk Realtime

Asterisk Realtime requires MySQL or PostgreSQL via ODBC; SQLite will not work. If you use `db.sqlite3`, migrate to Postgres/MySQL first.

1) Run migrations and generate config templates
- Command (provided by `telephony/management/commands/setup_asterisk_realtime.py`):
  - `python manage.py setup_asterisk_realtime --sync-existing --create-config`
- This verifies realtime tables and writes:
  - `/tmp/extconfig.conf` (maps realtime tables)
  - `/tmp/res_odbc.conf` (ODBC connection template)
  - `/tmp/pjsip_realtime.conf` (include for PJSIP)

2) Configure ODBC on the Asterisk host
- `/etc/odbcinst.ini`: add PostgreSQL/MySQL driver
- `/etc/odbc.ini`: add DSN `[asterisk]` pointing to your Django DB
- `/etc/asterisk/res_odbc.conf`: create stanza `[asterisk]` (copy from `/tmp/res_odbc.conf`, fill actual DB creds)

3) Map realtime tables in Asterisk
- Copy `/tmp/extconfig.conf` to `/etc/asterisk/extconfig.conf` with at least:
  - `ps_endpoints => odbc,asterisk,ps_endpoints`
  - `ps_auths => odbc,asterisk,ps_auths`
  - `ps_aors => odbc,asterisk,ps_aors`
  - (Optional) `extensions => odbc,asterisk,extensions_table`

4) Include PJSIP realtime
- Add `#include pjsip_realtime.conf` to `/etc/asterisk/pjsip.conf`
- Copy `/tmp/pjsip_realtime.conf` to `/etc/asterisk/pjsip_realtime.conf`
- Ensure a transport exists in your main `pjsip.conf`:
  ```
  [transport-udp]
  type=transport
  protocol=udp
  bind=0.0.0.0:5060
  ```

5) Enable/verify modules and reload
- Ensure modules: `res_odbc.so`, `res_config_odbc.so`, `chan_pjsip.so`, `res_pjsip_*.so`
- Restart Asterisk: `systemctl restart asterisk`
- Validate in CLI:
  - `asterisk -rx "odbc show"`
  - `asterisk -rx "pjsip show endpoints"` (will populate after you create a Phone)

---

## 2) Register the Asterisk Server in the app

- Go to Telephony → Asterisk Servers → Create.
- Fill Server IP, AMI host/port/username/password, ARI host/port/username/password, application.
- Optional test: Telephony → Asterisk Servers → [server] → Test Connection.
  - Simple test in `telephony/views.py:120` sets connection status.
  - A richer ARI test is available in `telephony/services.py:1` (`AsteriskService.test_connection`).

Key files:
- Form fields: `telephony/forms.py:1`
- Model: `telephony/models.py:1`
- Views/URLs: `telephony/views.py:1`, `telephony/urls.py:1`

---

## 3) Create an extension (Phone) — auto-sync to Asterisk

- Navigate to Telephony → Extensions → Create.
  - Fill `extension`, `name`, select `Asterisk Server`, leave `context=agents` unless your dialplan differs, set codecs if needed.
  - Assign to a user now or later (next section).
- Save. The record is synced to Asterisk via `Phone.save()`:
  - Writes to `ps_endpoints`, `ps_auths`, `ps_aors` (`Phone.sync_to_asterisk()`)

Validate in Asterisk CLI:
- `pjsip show endpoint <extension>`

Provision a softphone (MicroSIP/Zoiper):
- Username: `<extension>`
- Password: the Phone `secret` (shown on the extension detail page)
- Domain/Proxy: your Asterisk server IP
- Transport: UDP (unless you configure TLS)

Bulk creation also exists: Telephony → Extensions → Bulk Create.

Key files:
- PJSIP realtime models: `telephony/models.py:160` (`PsEndpoint`, `PsAuth`, `PsAor`)
- Phone + auto-sync: `telephony/models.py:280`
- Views/URLs: `telephony/views.py:1`, `telephony/urls.py:1`

---

## 4) Create an agent user and assign the extension

- Create the user (Users → Add User or Django Admin).
- Ensure they are considered an agent (add to an "Agent" group or your role setup).
- Assign the Phone:
  - Telephony → Extensions → [your extension] → Edit → set the `user` (FK) to that agent.

Once assigned, the originate API uses the logged-in user’s `Phone`.

---

## 5) Dialplan for outbound calls

- Default Phone context is `agents`. Ensure a dialplan exists to route outbound calls:
  - Use Telephony → Dialplan to create a context `agents` and add rules via the UI (`DialplanContext` and `DialplanExtension`).
  - Or manage static dialplan in `/etc/asterisk/extensions.conf`.

Minimal example (static):
```
[agents]
exten => _X.,1,NoOp(Outbound)
 same => n,Dial(PJSIP/${EXTEN}@<your-trunk>,30)
 same => n,Hangup()
```

To drive dialplan from DB, enable `extensions_table` in `extconfig.conf` and manage via the UI.

Key files:
- Dialplan models: `telephony/models.py:584` (DialplanContext), `telephony/models.py:601` (DialplanExtension)
- Optional realtime table: `telephony/models.py:218` (ExtensionsTable)

---

## 6) Agent login and placing calls

- Agent logs in via Users → Login.
- Ensure the agent has an assigned, registered extension.
- Outbound via API (already present):
  - POST `telephony/calls/originate/` with JSON `{ "phone_number": "<E164>", "campaign_id": "<optional>" }`
  - Handler uses the logged-in user’s assigned `Phone` (`telephony/views.py:1450`).
  - Hangup/transfer endpoints: `telephony/views.py:1494`, `telephony/views.py:1506`.
- Or dial from the softphone; Asterisk routes per your dialplan.

---

## 7) Quick checklist

- Database is PostgreSQL/MySQL and accessible to Asterisk via ODBC.
- Asterisk realtime configured and modules loaded (extconfig/res_odbc/pjsip includes).
- Asterisk Server created in the app (for ARI/AMI settings).
- At least one Phone created (ps_* tables populated).
- Softphone registers (`pjsip show registrations`).
- Dialplan “agents” routes outbound calls.
- Agent user exists, assigned to the Phone, and can place calls.

---

## Troubleshooting

- No endpoints in `pjsip show endpoints`:
  - Confirm `/etc/asterisk/extconfig.conf` DSN matches your DB and `odbc show` is OK.
  - Ensure `ps_*` tables have rows (create a Phone in the UI).
- Registration fails:
  - Check transport and NAT settings; verify `secret`; open firewall (5060/UDP and RTP range).
- Originate API returns “No active phone assigned”:
  - Assign the Phone to the agent (Telephony → Extensions → Edit → user).

---

## Optional enhancements

- Wire the “Test Connection” button to `AsteriskService.test_connection` for a live ARI validation.
- Add an Agent Panel with a simple dialpad page that posts to `telephony/calls/originate/`.
- Scaffold a default `agents` dialplan context that dials using the first active Carrier.

---

## Code touchpoints (for reference)

- Asterisk server model/form/views
  - `telephony/models.py:1`, `telephony/forms.py:1`, `telephony/views.py:1`, `telephony/urls.py:1`
- Realtime tables and phone sync
  - `telephony/models.py:160` (`PsEndpoint`, `PsAuth`, `PsAor`)
  - `telephony/models.py:280` (`Phone` with `save()` → `sync_to_asterisk()`)
- Dialplan models (optional realtime)
  - `telephony/models.py:584` (DialplanContext), `telephony/models.py:601` (DialplanExtension)
  - `telephony/models.py:218` (ExtensionsTable)
- Call control endpoints (originate/hangup/transfer)
  - `telephony/views.py:1450`, `telephony/views.py:1494`, `telephony/views.py:1506`
- Management command to set up realtime
  - `telephony/management/commands/setup_asterisk_realtime.py:1`

> After completing the steps above, you should be able to create an extension, register a softphone, assign the extension to an agent, and place calls via the app or the softphone.

