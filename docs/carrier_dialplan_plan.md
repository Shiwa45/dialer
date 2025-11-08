Carrier + Dialplan Unification Plan

Goal

- Manage trunk (carrier) provisioning and outbound dialplan in a single place in Telephony.
- Support two registration types: IP-based and Registration-based.
- Auto-sync PJSIP realtime (ps_endpoints, ps_auths, ps_aors, ps_registrations) and dialplan (extensions_table) when a carrier is saved.
- Campaigns simply select/align to the dial prefix; origination uses Local/<prefix><number>@from-campaign so Asterisk dialplan picks the right carrier.

Data model

- telephony.models.Carrier
  - Add fields:
    - registration_type: CharField choices [ip, registration], default ip
    - dial_prefix: CharField(max_length=10, blank=True)
    - dial_timeout: PositiveIntegerField(default=60)
  - Keep existing: name, protocol=pjsip, server_ip, port, username, password, auth_username, codec, qualify, nat, etc.

- telephony.models.PsRegistration (new, realtime table)
  - id: CharField (primary key) — use carrier name or slug
  - server_uri: CharField — e.g. sip:provider.domain:5060
  - client_uri: CharField — e.g. sip:username@provider.domain
  - contact_user: CharField (optional)
  - outbound_auth: CharField — matches ps_auths.id
  - transport: CharField (optional, default ‘transport-udp’)

Sync logic

- On Carrier.save():
  - PJSIP endpoint/auth/aor
    - endpoint.id = carrier.name; aors/auth reference the same id.
    - allow = codec; disallow = all; direct_media=no; force_rport/rewrite_contact=yes
  - IP-based:
    - ps_aors.contact = sip:<server_ip>:<port>
    - remove ps_registrations row if present
  - Registration-based:
    - ps_aors.contact = '' (registration manages contact)
    - upsert ps_registrations with server_uri=sip:<server_ip>:<port>, client_uri=sip:<username>@<server_ip>, outbound_auth=<endpoint id>
  - Dialplan (extensions_table) in context ‘from-campaign’ on the same server:
    - Pattern _<dial_prefix>X.
      1) NoOp(Outbound via <carrier>: ${EXTEN})
      2) Set(STRIPPED=${EXTEN:<len(prefix)>})
      3) Dial(PJSIP/<carrier>/${STRIPPED},<dial_timeout>)
      4) Hangup()
    - If dial_prefix changed, remove old pattern then write new.

Forms/UI

- Update CarrierForm to include registration_type, dial_prefix, dial_timeout.
- Update carrier_form.html to render the new fields with brief help text.
- Keep Add Extension form for granular lines; also includes the outbound generator toggle that can create a prefix block from within the same form.

Campaign integration

- Campaigns already have a dial_prefix field. They should be configured with the same prefix as the intended carrier’s dial_prefix. Origination uses Local/<prefix><number>@from-campaign, allowing the dialplan to select the carrier.
- (Optional future) Add a direct carrier reference to Campaign and auto-sync its dial_prefix from the carrier.

Rollout steps

1) Add model fields (Carrier.registration_type, .dial_prefix, .dial_timeout) and PsRegistration model + migrations.
2) Extend Carrier.save() to sync PJSIP + ps_registrations + dialplan as above.
3) Update CarrierForm + template; add simple inline field help.
4) Verify: create IP-based carrier (prefix 9) → ps_aors.contact present, dialplan rules exist; create Registration-based carrier (prefix 91) → ps_registrations present, dialplan rules exist.
5) Place a call from a campaign with matching dial_prefix; verify routing via selected carrier/gateway.

