#!/usr/bin/env python3
"""ZIP con código únicamente, sin base de datos, entorno virtual ni secretos."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
ARCHIVO = ROOT / 'publicacion' / 'agrokodit-pythonanywhere.zip'
CARPETAS = ('config', 'core', 'deploy')
FIJOS = ('manage.py', 'requirements.txt', 'README.md', 'scripts/configurar_pythonanywhere.py', 'docs/PYTHONANYWHERE.md')


def main():
    archivos = [ROOT / p for p in FIJOS]
    for carpeta in CARPETAS:
        archivos.extend(p for p in (ROOT / carpeta).rglob('*') if p.is_file())
    seguros = sorted({p for p in archivos if '__pycache__' not in p.parts and not any(x.startswith('.') for x in p.relative_to(ROOT).parts)
                      and p.suffix not in ('.pyc', '.sqlite3', '.db', '.json', '.zip')})
    ARCHIVO.parent.mkdir(exist_ok=True)
    with ZipFile(ARCHIVO, 'w', ZIP_DEFLATED) as zipfile:
        for archivo in seguros:
            zipfile.write(archivo, 'agrokodit/' + archivo.relative_to(ROOT).as_posix())
    print(f'Paquete creado: {ARCHIVO}')
    print(f'{len(seguros)} archivos; {ARCHIVO.stat().st_size / 1024:.1f} KB. Sin base de datos ni entorno virtual.')


if __name__ == '__main__':
    main()
