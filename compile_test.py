#!/usr/bin/env python3
import py_compile
import sys
import os

os.chdir(r'c:\Proyecto\App Agenda.worktrees\agents-internal-server-error-fix')

print("=" * 60)
print("COMPILANDO ARCHIVOS PYTHON")
print("=" * 60)

files_to_compile = [
    "app/routes/admin.py",
    "app/routes/cliente.py",
    "app/main.py"
]

all_ok = True

for file_path in files_to_compile:
    print(f"\n📝 Compilando: {file_path}")
    try:
        py_compile.compile(file_path, doraise=True)
        print(f"   ✅ {file_path} compilado exitosamente")
    except py_compile.PyCompileError as e:
        print(f"   ❌ ERROR en {file_path}:")
        print(f"   {e}")
        all_ok = False

print("\n" + "=" * 60)
print("INTENTANDO IMPORTAR LA APP")
print("=" * 60)

try:
    sys.path.insert(0, '.')
    from app.main import app
    print("✅ App importada exitosamente")
    print("✅ FastAPI app está disponible")
except Exception as e:
    print(f"❌ ERROR al importar app:")
    print(f"   {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    all_ok = False

print("\n" + "=" * 60)
if all_ok:
    print("✅ TODAS LAS PRUEBAS PASARON")
else:
    print("❌ HUBO ERRORES - VER ARRIBA")
print("=" * 60)

sys.exit(0 if all_ok else 1)
