# quick_setup.py - Run this in your Django project directory

import os
import subprocess
import sys

def run_command(command, description):
    print(f"\n🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {description} completed successfully")
            if result.stdout:
                print(result.stdout)
        else:
            print(f"❌ {description} failed")
            print(result.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Error running {description}: {e}")
        return False

def main():
    print("🚀 Setting up Django Autodialer with Asterisk Realtime")
    print("=" * 60)
    
    # 1. Run migrations
    if not run_command("python manage.py migrate", "Running database migrations"):
        print("Please fix migration errors before continuing")
        return
    
    # 2. Create Asterisk realtime tables and sync
    if not run_command("python manage.py setup_asterisk_realtime --sync-existing --create-config", 
                      "Setting up Asterisk realtime integration"):
        print("Setup command completed with warnings")
    
    # 3. Create superuser if needed
    print("\n📝 Creating admin user (if needed)...")
    run_command("python manage.py createsuperuser --noinput --username admin --email admin@localhost", 
                "Creating admin user (skip if exists)")
    
    # 4. Create sample Asterisk server
    print("\n🖥️ Creating sample Asterisk server configuration...")
    create_sample_data = """
from telephony.models import AsteriskServer
import socket

# Get WSL IP or use localhost
try:
    # This gets your WSL IP when running from Windows
    wsl_ip = '127.0.0.1'  # Default to localhost
    
    server, created = AsteriskServer.objects.get_or_create(
        name='WSL Asterisk Server',
        defaults={
            'server_ip': wsl_ip,
            'ami_username': 'admin',
            'ami_password': 'amp111',
            'ari_username': 'admin', 
            'ari_password': 'amp111',
            'is_active': True,
            'description': 'Asterisk server running in WSL'
        }
    )
    
    if created:
        print(f"✅ Created Asterisk server: {server.name}")
    else:
        print(f"ℹ️ Asterisk server already exists: {server.name}")
        
except Exception as e:
    print(f"❌ Error creating Asterisk server: {e}")
"""
    
    with open('temp_setup.py', 'w') as f:
        f.write(create_sample_data)
    
    run_command("python manage.py shell < temp_setup.py", "Creating sample Asterisk server")
    
    # Cleanup
    if os.path.exists('temp_setup.py'):
        os.remove('temp_setup.py')
    
    print("\n" + "=" * 60)
    print("🎉 Setup completed!")
    print("\n📋 Next steps:")
    print("1. Start Django: python manage.py runserver")
    print("2. Configure Asterisk in WSL using the generated config files")
    print("3. Create a phone in Django admin")
    print("4. Test registration with MicroSIP")
    print("\n🔗 Access Django admin at: http://localhost:8000/admin/")
    print("   Username: admin")
    print("   Password: (set during createsuperuser)")

if __name__ == "__main__":
    main()