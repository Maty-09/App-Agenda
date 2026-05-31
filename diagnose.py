#!/usr/bin/env python
"""Comprehensive diagnostic to identify the Internal Server Error"""
import sys
import os
from pathlib import Path

def diagnose():
    print("=" * 60)
    print("🔍 DIAGNÓSTICO COMPLETO DE LA APLICACIÓN")
    print("=" * 60 + "\n")
    
    # 1. Check Python version
    print("1️⃣  Versión de Python:")
    print(f"   {sys.version}\n")
    
    # 2. Check dependencies
    print("2️⃣  Verificando dependencias críticas:")
    deps = ["fastapi", "uvicorn", "sqlalchemy", "pydantic", "jinja2"]
    for dep in deps:
        try:
            mod = __import__(dep)
            version = getattr(mod, "__version__", "desconocida")
            print(f"   ✓ {dep}: {version}")
        except ImportError:
            print(f"   ✗ {dep}: NO INSTALADO")
    
    # 3. Check templates directory
    print("\n3️⃣  Verificando directorio de templates:")
    project_root = Path(__file__).resolve().parent
    templates_dir = project_root / "templates"
    print(f"   Ruta esperada: {templates_dir}")
    print(f"   ¿Existe? {templates_dir.exists()}")
    
    if templates_dir.exists():
        html_files = list(templates_dir.glob("*.html"))
        print(f"   Archivos HTML: {len(html_files)}")
        for f in sorted(html_files):
            print(f"     - {f.name}")
    
    # 4. Check database
    print("\n4️⃣  Verificando base de datos:")
    db_path = project_root / "agendamientos.db"
    print(f"   Ruta esperada: {db_path}")
    print(f"   ¿Existe? {db_path.exists()}")
    
    # 5. Try importing app
    print("\n5️⃣  Intentando importar la aplicación:")
    try:
        os.chdir(project_root)
        sys.path.insert(0, str(project_root))
        
        print("   Importando app.main...")
        from app.main import app
        print("   ✓ app.main importado exitosamente")
        
        print("\n   Rutas disponibles:")
        routes_count = 0
        for route in app.routes:
            if hasattr(route, 'path'):
                methods = getattr(route, 'methods', set())
                if methods:
                    print(f"     - {route.path} {methods}")
                    routes_count += 1
        print(f"\n   Total de rutas: {routes_count}")
        
        # Check if /admin/login route exists
        admin_login_found = False
        for route in app.routes:
            if hasattr(route, 'path') and route.path == "/admin/login":
                admin_login_found = True
                print("\n   ✓ Ruta /admin/login encontrada")
                break
        
        if not admin_login_found:
            print("\n   ✗ Ruta /admin/login NO ENCONTRADA")
        
        return 0
        
    except Exception as e:
        print(f"   ✗ Error al importar:")
        print(f"     {str(e)}")
        import traceback
        print("\n   Traceback:")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(diagnose())
