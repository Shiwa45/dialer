# Running Asterisk in WSL with Windows Django + PostgreSQL

This guide walks you through connecting Asterisk (running in WSL/Ubuntu) to your Windows-hosted Django app and PostgreSQL database, then creating extensions, assigning to agents, and testing calls.

Audience: Windows host, WSL2 Ubuntu guest, Asterisk inside WSL, PostgreSQL on Windows (localhost:5432).

---

## 0) Prerequisites

- Windows 10/11 with WSL2 + Ubuntu installed
- Asterisk installed in WSL (e.g., `sudo apt install asterisk`)
- PostgreSQL running on Windows (port 5432, user `postgres`, database `autodialer_db`)
- Django configured to use PostgreSQL (already updated in `autodialer/settings.py`)

---

## 1) Allow Windows PostgreSQL to accept WSL connections

1) Update PostgreSQL to listen on all interfaces (Windows):
- Locate `postgresql.conf` (varies by installer). Common paths:
  - `C:\\Program Files\\PostgreSQL\\<version>\\data\\postgresql.conf`
- Set: `listen_addresses = '*'`

2) Allow WSL subnet in `pg_hba.conf`:
- Open `pg_hba.conf` (same data directory)
- In WSL, get the Windows host IP seen from WSL: `cat /etc/resolv.conf` (look for `nameserver`, e.g., `172.26.224.1`)
- Add a broad allowance for WSL ranges (or your specific subnet), e.g.:
```
host  all  all  172.16.0.0/12  md5
```
- Save and restart PostgreSQL (Windows Services → PostgreSQL → Restart)

---

## 2) Configure ODBC in WSL to reach Windows PostgreSQL

Install ODBC packages in WSL:
```
sudo apt update
sudo apt install -y unixodbc unixodbc-dev odbc-postgresql
```

Configure drivers in `/etc/odbcinst.ini` (ensure PostgreSQL driver exists):
```
[PostgreSQL]
Description=PostgreSQL ODBC driver
Driver=/usr/lib/x86_64-linux-gnu/odbc/psqlodbca.so
Setup=/usr/lib/x86_64-linux-gnu/odbc/libodbcpsqlS.so
```

Create DSN in `/etc/odbc.ini` (replace WINDOWS_HOST_IP with `nameserver` value from `/etc/resolv.conf`):
```
[asterisk]
Driver=PostgreSQL
Servername=WINDOWS_HOST_IP
Port=5432
Database=autodialer_db
Username=postgres
Password=Shiwansh@123
ReadOnly=no
Protocol=7.4
```

---

## 3) Map Asterisk Realtime to your DSN

Create `/etc/asterisk/res_odbc.conf`:
```
[asterisk]
enabled => yes
dsn => asterisk
username => postgres
password => Shiwansh@123
pre-connect => yes
```

Create `/etc/asterisk/extconfig.conf`:
```
[settings]
ps_endpoints => odbc,asterisk,ps_endpoints
ps_auths => odbc,asterisk,ps_auths
ps_aors => odbc,asterisk,ps_aors
; Optional realtime dialplan
; extensions => odbc,asterisk,extensions_table
```

---

## 4) PJSIP transport and realtime include

Ensure a UDP transport exists in `/etc/asterisk/pjsip.conf`:
```
[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:5060
```
Include realtime (at end of `pjsip.conf`):
```
#include pjsip_realtime.conf
```
(You can create `/etc/asterisk/pjsip_realtime.conf` as a comment-only include; realtime mapping is done via `extconfig.conf` and the `ps_*` tables.)

---

## 5) Enable ARI + AMI (Django ↔ Asterisk)

HTTP/ARI – `/etc/asterisk/http.conf`:
```
enabled=yes
bindaddr=0.0.0.0
bindport=8088
```

`/etc/asterisk/ari.conf`:
```
[general]
allowed_origins=*

[autodialer]
type=user
read_only=no
password=amp111
```

AMI – `/etc/asterisk/manager.conf`:
```
[general]
enabled=yes
webenabled=no

[admin]
secret=amp111
read=all,system,call,reporting,originate
write=all,system,call,reporting,originate
```

In Django (Telephony → Asterisk Servers), use:
- AMI host: `localhost`, port `5038`, user `admin`, password `amp111`
- ARI host: `localhost`, port `8088`, user `autodialer`, password `amp111`, application `autodialer`

WSL localhost forwarding lets Windows reach WSL services on `127.0.0.1:<port>`.

---

## 6) Restart and verify in Asterisk

If systemd is available:
```
sudo systemctl restart asterisk
```
Otherwise:
```
sudo service asterisk restart
# or attach
sudo asterisk -rvvvvv
```

Verify ODBC + realtime:
```
asterisk -rx "odbc show"
asterisk -rx "pjsip show endpoints"
```
(Endpoints appear after you create Phones in Django.)

---

## 7) Create Asterisk Server + Extension in Django

1) Create Asterisk Server: Telephony → Asterisk Servers → Create
- Fill ARI/AMI fields as above; save and optionally click “Test Connection”.

2) Create Extension: Telephony → Extensions → Create
- Extension: e.g., `1001`
- Bind to your Asterisk Server
- Context: `agents` (default)
- Save (auto-syncs to `ps_endpoints`, `ps_auths`, `ps_aors`)

3) Verify from Asterisk:
```
asterisk -rx "pjsip show endpoint 1001"
```

4) Assign extension to a user: Telephony → Extensions → [1001] → Edit → set `user` to your agent.

---

## 8) Register a softphone (Windows)

Configure MicroSIP/Zoiper on Windows:
- Domain/Proxy: `127.0.0.1`
- Username: `1001`
- Password: secret shown on the extension detail page
- Transport: UDP

Check in Asterisk:
```
asterisk -rx "pjsip show registrations"
asterisk -rx "pjsip show contacts"
```

---

## 9) Minimal dialplan for testing

If you don’t have a trunk yet, add a simple local test in `/etc/asterisk/extensions.conf`:
```
[agents]
exten => 7000,1,NoOp(Echo Test)
 same => n,Answer()
 same => n,Echo()
 same => n,Hangup()
```
Reload the dialplan:
```
asterisk -rx "dialplan reload"
```
From the softphone (1001), dial `7000` → you should hear your audio echoed.

To place real outbound calls, add a trunk and route (Carrier in Django, or static PJSIP peer), then create a rule like:
```
[agents]
exten => _X.,1,NoOp(Outbound)
 same => n,Dial(PJSIP/${EXTEN}@your-trunk,30)
 same => n,Hangup()
```

---

## 10) Troubleshooting

- `odbc show` not connected:
  - Confirm `/etc/odbc.ini` Servername matches Windows host IP found in `/etc/resolv.conf`
  - Ensure Windows `pg_hba.conf` allows WSL subnet; PostgreSQL restarted; firewall allows 5432
- No endpoints in `pjsip show endpoints`:
  - Create a Phone in Django; check Postgres `ps_*` tables; run migrations; restart Asterisk
- Django cannot reach ARI/AMI:
  - Verify WSL `http.conf`, `ari.conf`, `manager.conf`; test `http://127.0.0.1:8088/ari/` from Windows browser
- Softphone cannot register:
  - Open Windows firewall for UDP 5060 (and RTP range); check `pjsip set logger on` in Asterisk console
- Audio issues:
  - Ensure codecs (ulaw/alaw) align; check NAT settings; validate RTP port ranges are open

---

## Appendix: Useful Asterisk CLI commands

```
asterisk -rvvvvv             # Attach to console
pjsip show endpoints         # List endpoints
pjsip show endpoint 1001     # Endpoint details
pjsip show contacts          # Registered contacts
pjsip set logger on          # SIP debug
odbc show                    # ODBC status
core show modules            # Loaded modules
core restart now             # Restart Asterisk core
```

Once you complete the above, you’ll be able to create extensions in Django, see them live in Asterisk, register softphones from Windows, and test calls through WSL Asterisk.

