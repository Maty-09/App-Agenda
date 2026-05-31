#!/usr/bin/env python
"""
Script para identificar el error exacto
"""
import sys
import os
from pathlib import Path

# Setup path
project_dir = Path(r"c:\Proyecto\App Agenda.worktrees\agents-internal-server-error-fix")
os.chdir(project_dir)
sys.path.insert(0, str(project_dir))

print("🔍 DEBUGGING - Intentando reproducir el error\n")

try:
    print("1. Importando app...")
    from app.main import app
    print("   ✅ App importada\n")
    
    print("2. Verificando routes...")
    found_login = False
    for route in app.routes:
        if hasattr(route, 'path') and '/admin/login' in route.path:
            found_login = True
            print(f"   ✅ Encontrada: {route.path}")
            print(f"      Métodos: {getattr(route, 'methods', 'N/A')}")
            print(f"      Endpoint: {getattr(route, 'endpoint', 'N/A')}\n")
    
    if not found_login:
        print("   ❌ Ruta /admin/login NO encontrada\n")
    
    print("3. Intentando importar routes.admin...")
    from app.routes import admin
    print("   ✅ admin.router importado\n")
    
    print("4. Verificando templates...")
    from app.routes.admin import TEMPLATES_DIR
    print(f"   TEMPLATES_DIR: {TEMPLATES_DIR}\n")
    
    templates_path = Path(TEMPLATES_DIR)
    if templates_path.exists():
        print(f"   ✅ Directorio existe")
        html_file = templates_path / "admin_login.html"
        if html_file.exists():
            print(f"   ✅ admin_login.html existe\n")
        else:
            print(f"   ❌ admin_login.html NO existe\n")
    else:
        print(f"   ❌ Directorio NO existe\n")
    
    print("5. Verificando templates object...")
    from app.routes.admin import templates
    print(f"   ✅ templates object: {type(templates)}\n")
    
    print("6. Intentando renderizar template con TestClient...")
    try:
        from starlette.testclient import TestClient
        
        client = TestClient(app)
        response = client.get("/admin/login")
        
        print(f"   Status Code: {response.status_code}\n")
        if response.status_code == 200:
            print(f"   ✅ Página cargada correctamente!")
        else:
            print(f"   ❌ Error: {response.status_code}")
            print(f"\n   Contenido de la respuesta:")
            print(f"   {response.text[:800]}\n")
    except ImportError:
        print("   ⚠️  starlette.testclient no disponible\n")
    
    print("=" * 60)
    print("✅ DIAGNÓSTICO COMPLETADO - Todo parece estar bien")
    
except Exception as e:
    print(f"\n❌ ERROR CRÍTICO:\n{str(e)}\n")
    import traceback
    print("TRACEBACK COMPLETO:")
    traceback.print_exc()
