"""
Tests de integración para los endpoints de la API.

Estrategia de aislamiento:
- Base de datos: SQLite en memoria (fixture `engine` en conftest).  Cada test
  obtiene su propia sesión que hace rollback al terminar, garantizando estado limpio.
- Broker Celery / Redis: se mockea con unittest.mock.patch.  Los tests no
  necesitan infraestructura externa para ejecutarse.
- Autenticación: se valida el comportamiento REAL de verify_api_key; los tests
  envían la cabecera X-API-Key con TEST_API_KEY cuando quieren autenticarse.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from core.db.models import SecurityScan
from tests.conftest import TEST_API_KEY

AUTH = {"X-API-Key": TEST_API_KEY}


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def _make_scan(**kwargs) -> SecurityScan:
    """Crea un objeto SecurityScan con valores por defecto sobreescribibles."""
    defaults = dict(
        celery_task_id=str(uuid.uuid4()),
        target_ip="10.0.0.1",
        open_ports_count=3,
        raw_output="22/tcp open ssh\n80/tcp open http\n443/tcp open https",
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return SecurityScan(**defaults)


# ════════════════════════════════════════════════════════════════════════════
# POST /api/v1/scans — Crear tarea de escaneo
# ════════════════════════════════════════════════════════════════════════════


class TestCreateScan:
    def test_valid_ip_returns_202_with_task_id(self, client):
        """Una IP válida encola la tarea y devuelve 202 con el task_id."""
        mock_task = MagicMock()
        mock_task.id = "fake-task-uuid-001"

        with patch("api.main.scan_ip.delay", return_value=mock_task):
            response = client.post(
                "/api/v1/scans",
                json={"target_ip": "192.168.1.1"},
                headers=AUTH,
            )

        assert response.status_code == 202
        data = response.json()
        assert data["task_id"] == "fake-task-uuid-001"
        assert data["status"] == "PENDING"
        assert "message" in data

    def test_ipv6_address_is_accepted(self, client):
        """Una dirección IPv6 válida también debe ser aceptada."""
        mock_task = MagicMock()
        mock_task.id = "fake-task-uuid-002"

        with patch("api.main.scan_ip.delay", return_value=mock_task):
            response = client.post(
                "/api/v1/scans",
                json={"target_ip": "2001:db8::1"},
                headers=AUTH,
            )

        assert response.status_code == 202

    def test_invalid_ip_returns_422(self, client):
        """Una cadena que no es una IP debe fallar con validación 422."""
        response = client.post(
            "/api/v1/scans",
            json={"target_ip": "not-an-ip-address"},
            headers=AUTH,
        )
        assert response.status_code == 422

    def test_missing_body_returns_422(self, client):
        """Omitir el cuerpo del request debe devolver 422."""
        response = client.post("/api/v1/scans", headers=AUTH)
        assert response.status_code == 422

    def test_missing_api_key_returns_403(self, client):
        """Sin cabecera X-API-Key debe devolver 403."""
        response = client.post("/api/v1/scans", json={"target_ip": "1.1.1.1"})
        assert response.status_code == 403

    def test_wrong_api_key_returns_403(self, client):
        """Una API key incorrecta debe devolver 403 (no 401)."""
        response = client.post(
            "/api/v1/scans",
            json={"target_ip": "1.1.1.1"},
            headers={"X-API-Key": "completely-wrong-key"},
        )
        assert response.status_code == 403

    def test_broker_failure_returns_500(self, client):
        """Si el broker falla al encolar, la API debe retornar 500."""
        with patch(
            "api.main.scan_ip.delay", side_effect=Exception("broker unreachable")
        ):
            response = client.post(
                "/api/v1/scans",
                json={"target_ip": "10.0.0.1"},
                headers=AUTH,
            )
        assert response.status_code == 500


# ════════════════════════════════════════════════════════════════════════════
# GET /api/v1/scans/{task_id} — Consultar estado de tarea
# ════════════════════════════════════════════════════════════════════════════


class TestGetScanStatus:
    def test_pending_task_returns_status(self, client):
        """Una tarea PENDING devuelve su estado sin campos extra."""
        mock_result = MagicMock()
        mock_result.status = "PENDING"

        with patch("api.main.AsyncResult", return_value=mock_result):
            response = client.get("/api/v1/scans/task-pending-001", headers=AUTH)

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-pending-001"
        assert data["status"] == "PENDING"
        assert "result" not in data
        assert "error" not in data

    def test_successful_task_includes_result(self, client):
        """Una tarea SUCCESS devuelve el campo `result` con el payload."""
        mock_result = MagicMock()
        mock_result.status = "SUCCESS"
        mock_result.result = {
            "ip": "1.1.1.1",
            "status": "completed",
            "open_ports_detected": 2,
            "db_persisted": True,
        }

        with patch("api.main.AsyncResult", return_value=mock_result):
            response = client.get("/api/v1/scans/task-success-001", headers=AUTH)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert data["result"]["open_ports_detected"] == 2

    def test_failed_task_includes_error_string(self, client):
        """Una tarea FAILURE expone el error como string (sin stack trace)."""
        mock_result = MagicMock()
        mock_result.status = "FAILURE"
        mock_result.result = RuntimeError("nmap binary not found")

        with patch("api.main.AsyncResult", return_value=mock_result):
            response = client.get("/api/v1/scans/task-failure-001", headers=AUTH)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "FAILURE"
        assert "nmap binary not found" in data["error"]

    def test_missing_api_key_returns_403(self, client):
        """Sin cabecera X-API-Key debe devolver 403."""
        response = client.get("/api/v1/scans/any-task-id")
        assert response.status_code == 403


# ════════════════════════════════════════════════════════════════════════════
# GET /api/v1/scans — Histórico paginado
# ════════════════════════════════════════════════════════════════════════════


class TestListScans:
    def test_empty_db_returns_zero_total(self, client):
        """Con la BD vacía, total debe ser 0 e items una lista vacía."""
        response = client.get("/api/v1/scans", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_returns_persisted_records(self, client, db_session):
        """Los registros añadidos a la BD deben aparecer en la respuesta."""
        db_session.add(_make_scan(target_ip="1.1.1.1"))
        db_session.add(_make_scan(target_ip="8.8.8.8"))
        db_session.flush()

        response = client.get("/api/v1/scans", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_response_schema_fields(self, client, db_session):
        """Cada item debe incluir los campos del schema ScanRecord."""
        db_session.add(_make_scan(target_ip="172.16.0.1", open_ports_count=5))
        db_session.flush()

        response = client.get("/api/v1/scans", headers=AUTH)
        item = response.json()["items"][0]
        assert "id" in item
        assert "celery_task_id" in item
        assert item["target_ip"] == "172.16.0.1"
        assert item["open_ports_count"] == 5
        assert "created_at" in item
        # raw_output NO debe estar expuesto en el listado
        assert "raw_output" not in item

    def test_pagination_limit_restricts_items(self, client, db_session):
        """El parámetro limit debe restringir el número de items devueltos."""
        for i in range(5):
            db_session.add(_make_scan(target_ip=f"10.0.0.{i + 1}"))
        db_session.flush()

        response = client.get("/api/v1/scans?limit=2", headers=AUTH)
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["limit"] == 2

    def test_pagination_skip_offsets_results(self, client, db_session):
        """El parámetro skip debe desplazar el cursor de resultados."""
        for i in range(5):
            db_session.add(_make_scan(target_ip=f"10.0.1.{i + 1}"))
        db_session.flush()

        response = client.get("/api/v1/scans?skip=3&limit=10", headers=AUTH)
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2  # 5 total - 3 skipped = 2
        assert data["skip"] == 3

    def test_default_order_is_most_recent_first(self, client, db_session):
        """Los registros deben devolverse ordenados del más reciente al más antiguo."""
        older = _make_scan(
            target_ip="10.0.2.1",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        newer = _make_scan(
            target_ip="10.0.2.2",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        db_session.add(older)
        db_session.add(newer)
        db_session.flush()

        response = client.get("/api/v1/scans", headers=AUTH)
        items = response.json()["items"]
        assert items[0]["target_ip"] == "10.0.2.2"  # más reciente primero
        assert items[1]["target_ip"] == "10.0.2.1"

    def test_limit_zero_returns_422(self, client):
        """limit=0 debe fallar con 422 (validación: ge=1)."""
        response = client.get("/api/v1/scans?limit=0", headers=AUTH)
        assert response.status_code == 422

    def test_limit_above_max_returns_422(self, client):
        """limit=101 debe fallar con 422 (validación: le=100)."""
        response = client.get("/api/v1/scans?limit=101", headers=AUTH)
        assert response.status_code == 422

    def test_negative_skip_returns_422(self, client):
        """skip negativo debe fallar con 422 (validación: ge=0)."""
        response = client.get("/api/v1/scans?skip=-1", headers=AUTH)
        assert response.status_code == 422

    def test_missing_api_key_returns_403(self, client):
        """Sin cabecera X-API-Key debe devolver 403."""
        response = client.get("/api/v1/scans")
        assert response.status_code == 403
