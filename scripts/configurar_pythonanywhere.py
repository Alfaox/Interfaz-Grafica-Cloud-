#!/usr/bin/env python3
"""Genera la configuración privada en el servidor sin mostrar ni empaquetar la clave."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='Dominio que muestra Web, sin https:// ni barras.')
    args = parser.parse_args()
    host = args.host.strip().lower()
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.pythonanywhere\.(?:com|eu)', host):
        parser.error('Usa el dominio exacto de PythonAnywhere, por ejemplo usuario.pythonanywhere.com.')
    archivo = Path.home() / '.agrokodit-produccion.json'
    if archivo.exists():
        actual = json.loads(archivo.read_text())
        if actual.get('hosts') != [host]:
            parser.error('Ya existe configuración para otro dominio. No se cambió ni se regeneró la clave.')
        print('La configuración privada ya existe. Se conservó la clave.')
        return
    datos = {'secret_key': secrets.token_urlsafe(64), 'hosts': [host]}
    descriptor = os.open(archivo, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as salida:
        json.dump(datos, salida)
        salida.write('\n')
    print('Configuración privada creada. No compartas ni subas este archivo al proyecto.')
    print('Dominio:', host)
    print('No se modificó la base de datos.')


if __name__ == '__main__':
    main()
