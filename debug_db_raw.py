import os
import django
import sys
from django.db import connection

sys.path.append('/home/shiwansh/dialer')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

def inspect_endpoint(ext):
    print(f"--- Raw SQL Inspection for {ext} ---")
    with connection.cursor() as cursor:
        # Check columns
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'ps_endpoints'")
        columns = [col[0] for col in cursor.fetchall()]
        print(f"Available Columns: {columns}")
        
        # Check values
        cursor.execute(f"SELECT * FROM ps_endpoints WHERE id = '{ext}'")
        row = cursor.fetchone()
        if row:
            # Map cols to values
            data = dict(zip(columns, row)) # imprecise if order doesn't match but good enough for finding keys
            # better verify order
            
            # Re-fetch as dict
            cursor.execute(f"SELECT * FROM ps_endpoints WHERE id = '{ext}'")
            desc = cursor.description
            row_dict = {desc[i][0]: value for i, value in enumerate(row)}
            
            print("\nEndpoint Data:")
            keys_to_check = ['transport', 'aors', 'auth', 'media_encryption', 'use_avpf', 'ice_support', 'direct_media', 'dtls_verify', 'webrtc']
            for k in keys_to_check:
                val = row_dict.get(k, "MISSING_COLUMN")
                print(f"  {k}: {val}")
        else:
            print("Row not found!")

inspect_endpoint('1001')
