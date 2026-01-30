#!/usr/bin/env python
import os, sys

# --- مهم: MySQLdb ← PyMySQL ---
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except Exception:
    pass

def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tkdjango.settings')
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
