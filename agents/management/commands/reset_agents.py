# agents/management/commands/reset_agents.py

from django.core.management.base import BaseCommand
from django.db import connection
from django.core.management import call_command

class Command(BaseCommand):
    help = 'Reset agents app by dropping tables and recreating migrations'

    def handle(self, *args, **options):
        cursor = connection.cursor()
        
        # List of agents tables to drop
        tables_to_drop = [
            'agents_agenthotkey',
            'agents_agentqueue', 
            'agents_agentscript',
            'agents_agentskill',
            'agents_agentbreakcode',
            'agents_agentperformancegoal',
            'agents_agentnote',
            'agents_agentwebrtcsession',
            'agents_agentcallbacktask',
            'agents_agentskilllevel',
        ]
        
        # Drop tables if they exist
        for table in tables_to_drop:
            try:
                cursor.execute(f"DROP TABLE IF EXISTS {table};")
                self.stdout.write(f"Dropped table {table}")
            except Exception as e:
                self.stdout.write(f"Could not drop {table}: {e}")
        
        # Remove migration entries from django_migrations table
        try:
            cursor.execute("DELETE FROM django_migrations WHERE app = 'agents';")
            self.stdout.write("Removed agents migration entries")
        except Exception as e:
            self.stdout.write(f"Could not remove migration entries: {e}")
        
        self.stdout.write(
            self.style.SUCCESS('Successfully reset agents app. Now run makemigrations and migrate.')
        )