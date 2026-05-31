#!/usr/bin/env python
import subprocess
import sys
import os

os.chdir(r'c:\Proyecto\App Agenda.worktrees\agents-internal-server-error-fix')
result = subprocess.run([sys.executable, 'run.py'], capture_output=False, text=True)
sys.exit(result.returncode)
