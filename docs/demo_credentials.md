# Demo Users and Telephony

Run the demo seeder:

python manage.py seed_demo --wsl-ip <WSL_IP>

Replace <WSL_IP> with your WSL Asterisk IP (e.g., 172.26.7.107). If omitted, it defaults to 127.0.0.1.

## Credentials
- Admin: admin / Demo@12345
- Manager: manager / Demo@123
- Agent: agent1 / Demo@123

## Extension
- Extension: 1001
- Secret: 1001
- Context: agents
- Assigned to: agent1

Softphone settings:
- Domain/SIP Server: <WSL_IP> (e.g., 172.26.7.107)
- Username/Login: 1001
- Password: 1001
- Transport: UDP (or TCP if enabled)

After seeding, visit:
- /users/login/ → log in as agent1
- /agents/ → set status Available and place a call

