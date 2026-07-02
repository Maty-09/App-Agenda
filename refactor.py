import os
import shutil

moves = {
    'app/database.py': 'app/core/database.py',
    'app/models.py': 'app/core/models.py',
    'app/schemas.py': 'app/core/schemas.py',
    'app/crud.py': 'app/domain_agenda/crud.py',
    'app/routes/admin.py': 'app/domain_crm/router_admin.py',
    'app/routes/cliente.py': 'app/domain_agenda/router_cliente.py',
    'routes/webhook.py': 'app/infrastructure/webhook.py',
    'routes/confirmation.py': 'app/infrastructure/confirmation.py',
    'services/bot_logic.py': 'app/infrastructure/bot_logic.py',
    'services/email_service.py': 'app/infrastructure/email_service.py',
    'services/twilio_service.py': 'app/infrastructure/twilio_service.py',
    'app/utils/email_utils.py': 'app/infrastructure/email_utils.py',
    'app/utils/generar_utm.py': 'app/core/generar_utm.py',
    'utils/humanizer.py': 'app/core/humanizer.py',
}

# Ensure folders exist
dirs = ['app/core', 'app/domain_crm', 'app/domain_agenda', 'app/domain_tenant', 'app/infrastructure']
for d in dirs:
    os.makedirs(d, exist_ok=True)

# Move files
for src, dst in moves.items():
    if os.path.exists(src):
        # ensure destination dir exists
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        print(f"Moved {src} to {dst}")
    else:
        print(f"Not found: {src}")

# Now update all imports in .py files
replacements = [
    ('from app.core.database import SessionLocal, engine, Base', 'from app.core.database import SessionLocal, engine, Base'),
    ('from app.core import models', 'from app.core import models'),
    ('from app.core.database import', 'from app.core.database import'),
    ('import app.core.database', 'import app.core.database'),
    ('from app.core import models', 'from app.core import models'),
    ('import app.core.models', 'import app.core.models'),
    ('from app.core import schemas', 'from app.core import schemas'),
    ('import app.core.schemas', 'import app.core.schemas'),
    
    ('from app.domain_agenda.crud', 'from app.domain_agenda.crud'),
    ('from app.domain_agenda.router_cliente', 'from app.domain_agenda.router_cliente'),
    ('from app.domain_crm.router_admin', 'from app.domain_crm.router_admin'),
    ('from app.infrastructure.webhook', 'from app.infrastructure.webhook'),
    ('from app.infrastructure.confirmation', 'from app.infrastructure.confirmation'),
    
    ('from app.infrastructure.bot_logic', 'from app.infrastructure.bot_logic'),
    ('from app.infrastructure.email_service', 'from app.infrastructure.email_service'),
    ('from app.infrastructure.twilio_service', 'from app.infrastructure.twilio_service'),
    
    ('from app.infrastructure.email_utils', 'from app.infrastructure.email_utils'),
    ('from app.core.generar_utm', 'from app.core.generar_utm'),
    ('from app.core.humanizer', 'from app.core.humanizer'),
    
    ('from app.domain_agenda import router_cliente as cliente
from app.domain_crm import router_admin as admin', 'from app.domain_agenda import router_cliente as cliente\nfrom app.domain_crm import router_admin as admin'),
]

for root, dirs, files in os.walk('.'):
    if 'venv' in root or '__pycache__' in root or '.git' in root or '.gemini' in root:
        continue
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            new_content = content
            for old, new in replacements:
                new_content = new_content.replace(old, new)
                
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Updated imports in {filepath}")

# Also delete empty folders safely
for d in ['app/routes', 'app/utils', 'services', 'routes', 'utils']:
    if os.path.exists(d):
        try:
            os.rmdir(d)
            print(f"Removed empty directory {d}")
        except OSError:
            print(f"Could not remove {d} (probably not empty)")
