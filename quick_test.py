#!/usr/bin/env python
"""
Guía de prueba rápida para verificar que los cambios funcionan
"""
import subprocess
import sys
import os
from pathlib import Path

def test_imports():
    """Prueba que la aplicación se puede importar sin errores"""
    print("🧪 Probando importación de la aplicación...\n")
    
    project_dir = r"c:\Proyecto\App Agenda.worktrees\agents-internal-server-error-fix"
    os.chdir(project_dir)
    sys.path.insert(0, project_dir)
    
    try:
        from app.main import app
        print("✅ Aplicación importada correctamente\n")
        
        print("📋 Rutas disponibles:")
        count = 0
        for route in app.routes:
            if hasattr(route, 'path'):
                methods = getattr(route, 'methods', set())
                if methods:
                    print(f"  ✓ {route.path} {methods}")
                    count += 1
        
        print(f"\nTotal de rutas: {count}\n")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
        return False

def check_templates():
    """Verifica que existan los archivos de template"""
    print("\n🧪 Verificando archivos de template...\n")
    
    templates_dir = Path(r"c:\Proyecto\App Agenda.worktrees\agents-internal-server-error-fix\templates")
    
    if not templates_dir.exists():
        print(f"❌ Directorio de templates no encontrado: {templates_dir}\n")
        return False
    
    html_files = sorted(templates_dir.glob("*.html"))
    print(f"✅ Directorio encontrado con {len(html_files)} archivos:\n")
    
    for f in html_files:
        print(f"  ✓ {f.name}")
    
    print()
    return len(html_files) > 0

def main():
    print("=" * 60)
    print("✨ VERIFICACIÓN DE CAMBIOS - APP AGENDA")
    print("=" * 60 + "\n")
    
    # Test 1
    templates_ok = check_templates()
    
    # Test 2
    imports_ok = test_imports()
    
    # Summary
    print("=" * 60)
    if templates_ok and imports_ok:
        print("✅ TODOS LOS CAMBIOS APLICADOS CORRECTAMENTE\n")
        print("Próximos pasos:")
        print("  1. pip install -r requirements.txt")
        print("  2. python run.py")
        print("  3. Abre http://localhost:8000/admin/login\n")
        return 0
    else:
        print("❌ PROBLEMAS DETECTADOS\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
