from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.middleware.cors import CORSMiddleware

from app import auth
from app.config import Settings, settings
from app.main import app

ISSUER = "https://suite.test/"
AUDIENCE = "compras-api"
EMPRESA_ID = 7
EMPRESA_CLAVE = "TEST_EMPRESA"


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._privada = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        cls.privada_pem = cls._privada.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        cls.publica_pem = (
            cls._privada.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("utf-8")
        )

        cls._respaldo = {
            "app_env": settings.app_env,
            "auth_enabled": settings.auth_enabled,
            "jwt_public_key": settings.jwt_public_key,
            "jwt_public_key_path": settings.jwt_public_key_path,
            "jwt_issuer": settings.jwt_issuer,
            "jwt_audience": settings.jwt_audience,
            "jwt_leeway_seconds": settings.jwt_leeway_seconds,
            "empresa_id": settings.empresa_id,
            "empresa_clave": settings.empresa_clave,
        }

        settings.app_env = "local"
        settings.auth_enabled = True
        settings.jwt_public_key = cls.publica_pem
        settings.jwt_public_key_path = ""
        settings.jwt_issuer = ISSUER
        settings.jwt_audience = AUDIENCE
        settings.jwt_leeway_seconds = 30
        settings.empresa_id = EMPRESA_ID
        settings.empresa_clave = EMPRESA_CLAVE
        auth._load_public_key.cache_clear()

        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        for campo, valor in cls._respaldo.items():
            setattr(settings, campo, valor)
        auth._load_public_key.cache_clear()

    def _token(
        self,
        *,
        permissions: list[str] | None = None,
        modules: list[str] | None = None,
        empresa_id: int = EMPRESA_ID,
        empresa_clave: str = EMPRESA_CLAVE,
        issuer: str = ISSUER,
        audience: str = AUDIENCE,
        ttl: int = 300,
    ) -> str:
        ahora = datetime.now(timezone.utc)
        payload = {
            "sub": "42",
            "empresa_id": empresa_id,
            "empresa_clave": empresa_clave,
            "roles": ["admin"],
            "legacy_role": "admin",
            "modules": ["compras"] if modules is None else modules,
            "permissions": (
                ["compras.ver"] if permissions is None else permissions
            ),
            "iss": issuer,
            "aud": audience,
            "iat": ahora,
            "exp": ahora + timedelta(seconds=ttl),
            "jti": "test-jti",
        }
        return jwt.encode(payload, self.privada_pem, algorithm="RS256")

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _cors_origenes(self) -> list[str]:
        for middleware in app.user_middleware:
            if middleware.cls is CORSMiddleware:
                return list(middleware.kwargs.get("allow_origins") or [])
        return []

    def test_health_es_publico(self) -> None:
        respuesta = self.client.get("/health")
        self.assertEqual(respuesta.status_code, 200)

    def test_endpoint_privado_sin_token(self) -> None:
        respuesta = self.client.get("/auth/me")
        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(
            respuesta.headers.get("www-authenticate"),
            "Bearer",
        )

    def test_endpoint_privado_sin_token_reportes(self) -> None:
        respuesta = self.client.get("/reportes/kpis")
        self.assertEqual(respuesta.status_code, 401)

    def test_token_valido(self) -> None:
        respuesta = self.client.get(
            "/auth/me",
            headers=self._auth(self._token()),
        )
        self.assertEqual(respuesta.status_code, 200)
        body = respuesta.json()
        self.assertEqual(body["sub"], "42")
        self.assertEqual(body["empresa_id"], EMPRESA_ID)
        self.assertEqual(body["modules"], ["compras"])
        self.assertEqual(body["permissions"], ["compras.ver"])

    def test_token_expirado(self) -> None:
        respuesta = self.client.get(
            "/auth/me",
            headers=self._auth(self._token(ttl=-120)),
        )
        self.assertEqual(respuesta.status_code, 401)

    def test_token_con_audiencia_incorrecta(self) -> None:
        respuesta = self.client.get(
            "/auth/me",
            headers=self._auth(self._token(audience="otra-api")),
        )
        self.assertEqual(respuesta.status_code, 401)

    def test_token_con_emisor_incorrecto(self) -> None:
        respuesta = self.client.get(
            "/auth/me",
            headers=self._auth(self._token(issuer="https://otro.test/")),
        )
        self.assertEqual(respuesta.status_code, 401)

    def test_token_de_otra_empresa(self) -> None:
        respuesta = self.client.get(
            "/auth/me",
            headers=self._auth(self._token(empresa_id=EMPRESA_ID + 1)),
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_token_sin_modulo(self) -> None:
        respuesta = self.client.get(
            "/auth/me",
            headers=self._auth(self._token(modules=[])),
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_token_sin_permiso_ver(self) -> None:
        respuesta = self.client.get(
            "/auth/me",
            headers=self._auth(
                self._token(permissions=["compras.importar"])
            ),
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_importar_exige_permiso_importar(self) -> None:
        respuesta = self.client.post(
            "/compras/importar",
            headers=self._auth(self._token()),
            files={"archivo": ("prueba.csv", b"a,b\n1,2\n", "text/csv")},
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_procesamiento_exige_permiso_importar(self) -> None:
        respuesta = self.client.post(
            "/procesamiento/upload",
            headers=self._auth(self._token()),
            files={"archivo": ("prueba.xlsx", b"contenido", "application/octet-stream")},
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_procesamiento_lote_y_carga_exigen_permiso_importar(self) -> None:
        cabeceras = self._auth(self._token())

        respuesta = self.client.post(
            "/procesamiento/upload-lote",
            headers=cabeceras,
            files={
                "archivos": (
                    "prueba.xlsx",
                    b"contenido",
                    "application/octet-stream",
                )
            },
        )
        self.assertEqual(respuesta.status_code, 403)

        respuesta = self.client.post("/procesamiento/cargar", headers=cabeceras)
        self.assertEqual(respuesta.status_code, 403)

    def test_exportar_exige_permiso_exportar(self) -> None:
        cabeceras = self._auth(self._token())
        rutas = (
            "/compras/exportar",
            "/exportar/importadores",
            "/exportar/proveedores",
            "/exportar/importaciones",
        )
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta, headers=cabeceras)
                self.assertEqual(respuesta.status_code, 403)
                self.assertEqual(
                    respuesta.json()["detail"],
                    "El permiso compras.exportar no está autorizado.",
                )

    def test_auth_activa_sin_llave_responde_503(self) -> None:
        llave_original = settings.jwt_public_key
        ruta_original = settings.jwt_public_key_path
        settings.jwt_public_key = ""
        settings.jwt_public_key_path = "/tmp/opencode/no-existe-jwt-public.pem"
        auth._load_public_key.cache_clear()
        try:
            respuesta = self.client.get(
                "/auth/me",
                headers=self._auth(self._token()),
            )
        finally:
            settings.jwt_public_key = llave_original
            settings.jwt_public_key_path = ruta_original
            auth._load_public_key.cache_clear()

        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(
            respuesta.json()["detail"],
            "La autenticación JWT no está configurada.",
        )

    def test_cors_preflight_permite_origen_configurado(self) -> None:
        origenes = self._cors_origenes()
        if not origenes:
            self.skipTest("No hay orígenes CORS configurados.")
        origen = origenes[0]

        respuesta = self.client.options(
            "/auth/me",
            headers={
                "Origin": origen,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.headers.get("access-control-allow-origin"),
            origen,
        )
        self.assertEqual(
            respuesta.headers.get("access-control-allow-credentials"),
            "true",
        )
        self.assertIn("Origin", respuesta.headers.get("vary", ""))

    def test_cors_rechaza_origen_no_configurado(self) -> None:
        respuesta = self.client.options(
            "/auth/me",
            headers={
                "Origin": "https://origen-no-permitido.test",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIsNone(respuesta.headers.get("access-control-allow-origin"))

    def test_cors_incluye_credenciales_en_respuesta(self) -> None:
        origenes = self._cors_origenes()
        if not origenes:
            self.skipTest("No hay orígenes CORS configurados.")
        origen = origenes[0]

        respuesta = self.client.get("/auth/me", headers={"Origin": origen})

        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(
            respuesta.headers.get("access-control-allow-origin"),
            origen,
        )
        self.assertEqual(
            respuesta.headers.get("access-control-allow-credentials"),
            "true",
        )

    def test_auth_desactivada_devuelve_contexto_local(self) -> None:
        settings.auth_enabled = False
        try:
            respuesta = self.client.get("/auth/me")
        finally:
            settings.auth_enabled = True

        self.assertEqual(respuesta.status_code, 200)
        body = respuesta.json()
        self.assertEqual(body["sub"], "local-dev")
        self.assertIn("compras.ver", body["permissions"])
        self.assertIn("compras.importar", body["permissions"])
        self.assertIn("compras.exportar", body["permissions"])

    def test_produccion_no_permite_auth_desactivada(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                app_env="production",
                auth_enabled=False,
            )


if __name__ == "__main__":
    unittest.main()
