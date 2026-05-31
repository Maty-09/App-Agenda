#!/usr/bin/env python
"""Comprehensive verification script"""
import sys
import traceback
import os

def check_syntax(filepath):
    """Check Python syntax"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            compile(f.read(), filepath, 'exec')
        return True, None
    except SyntaxError as e:
        return False, str(e)

def main():
    print("🔍 Verificando sintaxis de todos los archivos Python...\n")
    
    app_dir = "app"
    errors = []
    
    for root, dirs, files in os.walk(app_dir):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                success, error = check_syntax(filepath)
                if success:
                    print(f"✅ {filepath}")
                else:
                    print(f"❌ {filepath}")
                    errors.append((filepath, error))
    
    if errors:
        print("\n\n❌ ERRORES DE SINTAXIS ENCONTRADOS:\n")
        for filepath, error in errors:
            print(f"  {filepath}:")
            print(f"    {error}\n")
        return 1
    
    print("\n\n✅ ¡Todos los archivos tienen sintaxis correcta!\n")
    
    # Try importing the app
    print("🔍 Intentando cargar la aplicación...\n")
    try:
        from app.main import app
        print("✅ Aplicación cargada exitosamente!")
        print("\n📋 Rutas registradas:")
        for route in app.routes:
            if hasattr(route, 'path'):
                print(f"  - {route.path}")
        return 0
    except Exception as e:
        print(f"❌ Error al cargar la aplicación:")
        print(f"  {str(e)}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
