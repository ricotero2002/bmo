import os
import sys
import subprocess
from pathlib import Path

def print_help():
    print("Uso: python scripts/migrate_db.py [comando] [motor]")
    print("")
    print("Comandos:")
    print("  upgrade    - Ejecuta 'alembic upgrade head' (por defecto)")
    print("  generate   - Genera una nueva migración con autogenerate")
    print("               (ej: python scripts/migrate_db.py generate postgres \"Mi mensaje\")")
    print("  stamp      - Marca la base de datos con una versión específica sin ejecutar SQL")
    print("               (ej: python scripts/migrate_db.py stamp oracle 001)")
    print("")
    print("Motores soportados para target:")
    print("  postgres   - Usa variables locales de Postgres (por defecto)")
    print("  oracle     - Fuerza uso de Oracle (requiere vars de entorno configuradas)")
    print("")

def main():
    # Cargar variables de entorno desde .env y .env.local
    try:
        from dotenv import load_dotenv
        project_root = Path(__file__).resolve().parents[1]
        load_dotenv(project_root / ".env")
        load_dotenv(project_root / ".env.local", override=True)
    except ImportError:
        pass

    print("=== Script Automatizado de Base de Datos (Alembic) ===")
    
    command = "upgrade"
    db_type = "postgres"
    migration_msg = "auto_migration"
    
    if len(sys.argv) > 1:
        if sys.argv[1] in ["--help", "-h"]:
            print_help()
            sys.exit(0)
        command = sys.argv[1].lower()
        
    if len(sys.argv) > 2:
        db_type = sys.argv[2].lower()
        
    if len(sys.argv) > 3 and command == "generate":
        migration_msg = sys.argv[3]
    
    if db_type == "oracle":
        print("[info] Forzando configuración: ORACLE")
        os.environ["DB_TYPE"] = "oracle"
    else:
        print("[info] Forzando configuración: POSTGRES LOCAL")
        os.environ["DB_TYPE"] = "postgres"

    # Ejecutar Alembic usando el módulo de python para evitar problemas de PATH local
    if command == "upgrade":
        cmd = [sys.executable, "-m", "alembic", "upgrade", "head"]
    elif command == "generate":
        cmd = [sys.executable, "-m", "alembic", "revision", "--autogenerate", "-m", migration_msg]
    elif command == "stamp":
        revision_id = sys.argv[3] if len(sys.argv) > 3 else "head"
        cmd = [sys.executable, "-m", "alembic", "stamp", revision_id]
    else:
        print(f"[error] Comando desconocido: {command}")
        print_help()
        sys.exit(1)
        
    print(f"-> Ejecutando: {' '.join(cmd)}")
    
    # Aseguramos que la llamada se ejecute en el root del proyecto
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(cmd, cwd=str(project_root))
    
    if result.returncode == 0:
        print("=== Operación Completada Exitosamente ===")
    else:
        print("=== Error en Alembic ===")
        sys.exit(result.returncode)

if __name__ == "__main__":
    main()
