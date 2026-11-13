from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt


def _lista(valor: str) -> list[str]:
    return [item.strip() for item in valor.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera un JWT RS256 de desarrollo para probar la API."
    )
    parser.add_argument("--sub", default="1", help="ID del usuario")
    parser.add_argument("--empresa-id", type=int, default=1)
    parser.add_argument("--empresa-clave", default="LOCAL")
    parser.add_argument(
        "--roles",
        default="admin",
        help="Roles separados por coma",
    )
    parser.add_argument(
        "--legacy-role",
        default="admin",
        help="Rol legado para compatibilidad",
    )
    parser.add_argument(
        "--modules",
        default="compras",
        help="Módulos separados por coma",
    )
    parser.add_argument(
        "--permissions",
        default="compras.ver,compras.importar,compras.exportar",
        help="Permisos separados por coma",
    )
    parser.add_argument("--ttl", type=int, default=300, help="Segundos de vigencia")
    parser.add_argument(
        "--issuer",
        default=os.getenv("JWT_ISSUER") or "https://suite.local/",
        help="Emisor del token. También lee JWT_ISSUER.",
    )
    parser.add_argument(
        "--audience",
        default=os.getenv("JWT_AUDIENCE") or "compras-api",
        help="Audiencia del token. También lee JWT_AUDIENCE.",
    )
    parser.add_argument(
        "--private-key",
        default=os.getenv("JWT_PRIVATE_KEY_PATH", ""),
        help="Ruta de la llave privada PEM. También lee JWT_PRIVATE_KEY_PATH.",
    )
    args = parser.parse_args()

    if not args.private_key:
        print(
            "Falta --private-key o JWT_PRIVATE_KEY_PATH.",
            file=sys.stderr,
        )
        return 2

    llave = Path(args.private_key).read_text(encoding="utf-8")
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(args.sub),
        "empresa_id": args.empresa_id,
        "empresa_clave": args.empresa_clave,
        "roles": _lista(args.roles),
        "legacy_role": args.legacy_role,
        "modules": _lista(args.modules),
        "permissions": _lista(args.permissions),
        "iss": args.issuer,
        "aud": args.audience,
        "iat": ahora,
        "exp": ahora + timedelta(seconds=args.ttl),
        "jti": os.urandom(16).hex(),
    }
    print(jwt.encode(payload, llave, algorithm="RS256"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
