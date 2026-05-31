#!/usr/bin/env python
"""
Diagnostic report for App Agenda
This script validates all the fixes we made
"""
import sys
import os
from pathlib import Path
import traceback

def main():
    print("=" * 70)
    print("📋 REPORTE DE DIAGNÓSTICO - APP AGENDA")
    print("=" * 70 + "\n")
    
    project_root = Path(r'c:\Proyecto\App Agenda.worktrees\agents-internal-server-error-fix')
    os.chdir(project_root)
    sys.path.insert(0, str(project_root))
    
    # 1. Verify Python version
    print("1️⃣  VERSIÓN DE PYTHON")
    print(f"   {sys.version}\n")
    
    # 2. Verify requirements
    print("2️⃣  VERIFICANDO DEPENDENCIAS")
    deps = {
        'fastapi': 'FastAPI',
        'uvicorn': 'Uvicorn',
        'sqlalchemy': 'SQLAlchemy',
        'pydantic': 'Pydantic',
        'jinja2': 'Jinja2'
    }
    
    missing = []
    for module, name in deps.items():
        try:
            mod = __import__(module)
            version = getattr(mod, '__version__', 'desconocida')
            print(f"   ✅ {name}: {version}")
        except ImportError:
            print(f"   ❌ {name}: NO INSTALADO")
            missing.append(name)
    
    if missing:
        print(f"\n   ⚠️  Instala las dependencias faltantes:")
        print(f"   pip install -r requirements.txt\n")
        return 1
    
    # 3. Verify templates directory
    print("\n3️⃣  VERIFICANDO DIRECTORIO DE TEMPLATES")
    templates_dir = project_root / "templates"
    print(f"   Ruta: {templates_dir}")
    print(f"   ¿Existe? {templates_dir.exists()}")
    
    if templates_dir.exists():
        html_files = sorted(templates_dir.glob("*.html"))
        print(f"   Archivos HTML: {len(html_files)}")
        for f in html_files:
            print(f"     ✓ {f.name}")
    else:
        print(f"   ❌ DIRECTORIO NO ENCONTRADO")
        return 1
    
    # 4. Verify database
    print("\n4️⃣  VERIFICANDO BASE DE DATOS")
    db_path = project_root / "agendamientos.db"
    print(f"   Ruta: {db_path}")
    print(f"   ¿Existe? {db_path.exists()}")
    
    # 5. Import and validate app
    print("\n5️⃣  VALIDANDO APLICACIÓN")
    try:
        print("   Importando app.main...")
        from app.main import app
        print("   ✅ app.main importado exitosamente\n")
        
        # Count routes
        routes = []
        for route in app.routes:
            if hasattr(route, 'path'):
                methods = getattr(route, 'methods', set())
                routes.append((route.path, methods))
        
        print(f"   Total de rutas: {len(routes)}")
        
        # Check critical routes
        critical_routes = [
            ("/admin/login", {"GET", "POST"}),
            ("/admin/panel", {"GET"}),
            ("/cliente/agendar_web", {"GET", "POST"})
        ]
        
        print("\n   ✓ Rutas críticas:")
        for route_path, expected_methods in critical_routes:
            found = False
            for registered_path, registered_methods in routes:
                if registered_path == route_path:
                    found = True
                    print(f"     ✅ {route_path} {registered_methods}")
                    break
            if not found:
                print(f"     ❌ {route_path} NO ENCONTRADA")
        
        return 0
        
    except Exception as e:
        print(f"   ❌ Error al importar aplicación:")
        print(f"      {str(e)}\n")
        print("   Traceback:")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = main()
    
    print("\n" + "=" * 70)
    if exit_code == 0:
        print("✅ DIAGNÓSTICO COMPLETADO - APLICACIÓN LISTA")
        print("\nPara ejecutar la aplicación:")
        print("   python run.py")
        print("\nAccede a: http://localhost:8000/admin/login")
    else:
        print("❌ DIAGNÓSTICO MOSTRÓ PROBLEMAS")
    print("=" * 70)
    
    sys.exit(exit_code)
