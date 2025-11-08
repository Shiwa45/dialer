import os
from pathlib import Path

OUT_DIR = Path('docs/generated')
OUT_DIR.mkdir(parents=True, exist_ok=True)

extconfig = """; extconfig.conf - Asterisk Realtime Configuration
[settings]
ps_endpoints => odbc,asterisk,ps_endpoints
ps_auths => odbc,asterisk,ps_auths
ps_aors => odbc,asterisk,ps_aors
; Optional realtime dialplan
; extensions => odbc,asterisk,extensions_table
"""

res_odbc = """; res_odbc.conf - Database Connection Configuration
[asterisk]
enabled => yes
dsn => asterisk
username => postgres
password => Shiwansh@123
pre-connect => yes
max_connections => 20
"""

pjsip_realtime = """; pjsip_realtime.conf - PJSIP Realtime Include
; Add this line to /etc/asterisk/pjsip.conf: #include pjsip_realtime.conf

; Transport should be defined in main pjsip.conf:
; [transport-udp]
; type=transport
; protocol=udp
; bind=0.0.0.0:5060
"""

sorcery = """; sorcery.conf - Map PJSIP objects to realtime tables
[res_pjsip]
endpoint=realtime,ps_endpoints
aor=realtime,ps_aors
auth=realtime,ps_auths
; Optional tables:
; identify=realtime,ps_endpoint_id_ips
; domain_alias=realtime,ps_domain_aliases
"""

files = {
    'extconfig.conf': extconfig,
    'res_odbc.conf': res_odbc,
    'pjsip_realtime.conf': pjsip_realtime,
    'sorcery.conf': sorcery,
}

for name, content in files.items():
    (OUT_DIR / name).write_text(content)
    print(f"Wrote {OUT_DIR / name}")

