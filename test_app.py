#!/usr/bin/env python
"""Test script to check if the app can start"""
import sys
import traceback

try:
    print("✓ Iniciando verificación de la aplicación...")
    
    # Test imports
    print("✓ Importando módulos...")
    from app.main import app
    print("✓ Aplicación cargada exitosamente!")
    
    # Check routes
    print("\n✓ Rutas cargadas:")
    for route in app.routes:
        if hasattr(route, 'path'):
            print(f"  - {route.path}")
    
    print("\n✅ La aplicación está funcionando correctamente!")
    
except Exception as e:
    print(f"\n❌ Error encontrado:")
    print(f"  {str(e)}")
    print(f"\n📋 Traceback completo:")
    traceback.print_exc()
    sys.exit(1)
