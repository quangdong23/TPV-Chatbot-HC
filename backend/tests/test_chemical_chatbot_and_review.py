"""Kiểm thử toàn diện cho Chatbot Hóa chất (Feature 1) và Soát tài liệu & Bất thường (Feature 2)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.context import Principal, use_principal
from app.db import chemical_session
from app.db.chemical_models import (
    ChemicalBase,
    ChemicalMeasurement,
    RoomMeasurement,
)
from app.db.chemical_session import (
    ChemicalReadOnlyViolation,
    readonly_session_scope,
    session_scope,
)
from app.db.erp_auth import AccountAccess
from app.main import app
from app.services.chemical_anomaly import run_anomaly_detection, update_alert_status
from app.services.chemical_chat import answer_chemical_question
from app.services.chemical_importer import (
    ChemicalImportError,
    import_chemical_measurements,
)
from app.services.chemical_reconciliation import review_and_reconcile_document
from app.tools import chemical as chem_tools

SAMPLE_CSV = """Timestamp,Room_ID,Chemical_ID,Quantity_Recorded_mL,Temperature_C,Humidity_pct,TVOC_ppb,Anomaly_Label
2026-09-28T17:30:00+07:00,R01,001,1500.00,25.00,55.00,110.00,0
2026-09-28T17:30:00+07:00,R01,002,1800.50,25.00,55.00,110.00,0
2026-09-28T17:30:00+07:00,R02,005,2000.00,26.50,60.00,130.00,0
2026-09-28T17:45:00+07:00,R01,001,1545.00,25.20,55.50,115.00,1
2026-09-28T17:45:00+07:00,R01,002,1795.00,25.20,55.50,115.00,0
2026-09-28T17:45:00+07:00,R02,005,1990.00,31.50,61.00,210.00,1
"""


def make_principal(
    tenant_id: int = 94,
    user_id: str = "421",
    permissions: tuple[str, ...] = ("Ai.AiChatbot", "Ai.DocumentReview", "Ai.ReportSummary.Create"),
    admin: bool = False,
) -> Principal:
    return Principal(
        tenant_id=tenant_id,
        user_id=user_id,
        source="token",
        access=AccountAccess(
            int(user_id),
            tenant_id,
            "chem_user",
            "Chem",
            "User",
            permissions=frozenset(permissions),
            is_static_admin=admin,
        ),
    )


@pytest.fixture
async def chem_db():
    """Khởi tạo SQLite in-memory có ATTACH schema ``chem`` cho bộ kiểm thử."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _attach_chem_schema(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS chem")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(ChemicalBase.metadata.create_all)

    chemical_session.configure_engine(engine)
    yield engine
    await chemical_session.dispose()


async def test_import_idempotency_leading_zeros_and_env_deduplication(chem_db):
    """Kiểm tra import: chống trùng SHA-256, giữ số 0 đầu (001), chuẩn hóa UTC, không nhân bản RoomMeasurements."""
    who = make_principal(tenant_id=94)
    with use_principal(who):
        async with session_scope() as session:
            res1 = await import_chemical_measurements(
                session,
                file_bytes=SAMPLE_CSV.encode("utf-8"),
                file_name="giam_sat_28_09.csv",
            )
            assert res1["status"] == "Completed"
            assert res1["already_imported"] is False
            assert res1["source_row_count"] == 6
            assert res1["inserted_row_count"] == 6
            assert res1["rejected_row_count"] == 0
            # 6 dòng CSV (2 mốc giờ x 2 phòng) chỉ tạo đúng 4 bản ghi RoomMeasurements độc lập
            rm_count = len((await session.execute(select(RoomMeasurement))).scalars().all())
            cm_count = len((await session.execute(select(ChemicalMeasurement))).scalars().all())
            assert rm_count == 4
            assert cm_count == 6

        # Import lại cùng file hash -> không tạo bản ghi trùng
        async with session_scope() as session:
            res2 = await import_chemical_measurements(
                session,
                file_bytes=SAMPLE_CSV.encode("utf-8"),
                file_name="giam_sat_28_09_copy.csv",
            )
            assert res2["already_imported"] is True
            assert res2["batch_id"] == res1["batch_id"]

        # Kiểm tra mã hóa chất giữ nguyên số 0 đầu ("001", "002", "005") và MeasuredAt đúng giờ dữ liệu gốc
        cat = await chem_tools.search_chemical_catalog()
        codes = [c["chemical_code"] for c in cat["items"]]
        assert codes == ["001", "002", "005"]

        latest = await chem_tools.get_latest_measurement(room_code="R01", chemical_code="001")
        assert latest["count"] == 1
        item = latest["items"][0]
        # 2026-09-28T17:45:00+07:00 == 2026-09-28T10:45:00+00:00
        assert item["measured_at"] == "2026-09-28T10:45:00+00:00"
        assert item["quantity_recorded_ml"] == 1545.0


async def test_import_rejects_invalid_rows_and_missing_columns(chem_db):
    """Từ chối file thiếu cột và các dòng có giá trị âm, độ ẩm > 100%, mâu thuẫn môi trường."""
    who = make_principal(tenant_id=94)
    with use_principal(who):
        async with session_scope() as session:
            with pytest.raises(ChemicalImportError):
                await import_chemical_measurements(
                    session,
                    file_bytes=b"Room_ID,Chemical_ID\nR01,001\n",
                    file_name="missing_cols.csv",
                )

        bad_csv = """Timestamp,Room_ID,Chemical_ID,Quantity_Recorded_mL,Temperature_C,Humidity_pct,TVOC_ppb,Anomaly_Label
2026-09-28T18:00:00+07:00,R01,001,-10.00,25.00,55.00,110.00,0
2026-09-28T18:00:00+07:00,R01,002,1500.00,25.00,120.00,110.00,0
2026-09-28T18:00:00+07:00,R01,003,1500.00,25.00,55.00,-5.00,0
2026-09-28T18:00:00+07:00,R01,004,1500.00,25.00,55.00,100.00,0
2026-09-28T18:00:00+07:00,R01,005,1500.00,29.99,55.00,100.00,0
"""
        async with session_scope() as session:
            res = await import_chemical_measurements(
                session,
                file_bytes=bad_csv.encode("utf-8"),
                file_name="bad_rows.csv",
            )
            # Chỉ có dòng 004 hợp lệ; dòng 005 mâu thuẫn nhiệt độ (29.99 vs 25.00) tại cùng R01 18:00 nên bị từ chối
            assert res["inserted_row_count"] == 1
            assert res["rejected_row_count"] == 4


async def test_tenant_isolation_room_permissions_and_readonly_guard(chem_db):
    """Kiểm tra phân quyền tenant/phòng, chặn truyền TenantId tùy ý và chặn ghi trên readonly_session_scope."""
    tenant_94 = make_principal(tenant_id=94)
    tenant_64 = make_principal(tenant_id=64)
    restricted_r01_only = make_principal(
        tenant_id=94,
        permissions=("Ai.AiChatbot", "Chem.Room.R01"),
    )

    with use_principal(tenant_94):
        async with session_scope() as session:
            await import_chemical_measurements(
                session,
                file_bytes=SAMPLE_CSV.encode("utf-8"),
                file_name="tenant94.csv",
            )

    # Tenant 64 không đọc được dữ liệu của Tenant 94
    with use_principal(tenant_64):
        res_64 = await chem_tools.get_latest_measurement()
        assert res_64["empty"] is True
        assert res_64["count"] == 0

    # User chỉ có quyền phòng R01 không được đọc phòng R02
    with use_principal(restricted_r01_only):
        rooms = await chem_tools.compare_rooms()
        assert [r["room_code"] for r in rooms["items"]] == ["R01"]
        with pytest.raises(PermissionError):
            await chem_tools.get_latest_measurement(room_code="R02")

    # Không thể truyền tenant_id tùy ý vào SQL tool
    with use_principal(tenant_94):
        with pytest.raises(PermissionError):
            await chem_tools.get_latest_measurement(tenant_id=64)

        # Phiên chỉ đọc của chatbot chặn mọi câu lệnh ghi trực tiếp
        async with readonly_session_scope() as ro_session:
            with pytest.raises(ChemicalReadOnlyViolation):
                await ro_session.execute(text("DELETE FROM chem.Rooms WHERE TenantId = 94"))


async def test_document_review_reconciliation_and_day28_day29_scenarios(chem_db):
    """Kiểm tra tính năng Soát tài liệu, bao gồm đầy đủ kịch bản dữ liệu ngày 28 nhưng ngày 29 mới viết báo cáo."""
    who = make_principal(tenant_id=94)
    with use_principal(who):
        async with session_scope() as session:
            await import_chemical_measurements(
                session,
                file_bytes=SAMPLE_CSV.encode("utf-8"),
                file_name="base_28_09.csv",
            )

            # Soát báo cáo lập vào ngày 29/09/2026 (trong khi DB chỉ có dữ liệu đến 28/09/2026 17:45+07:00)
            review_items = [
                # 1. Ghi rõ ngày đo 28/09 17:45 và số liệu khớp -> matched
                {
                    "row_number": 1,
                    "room_code": "R01",
                    "chemical_code": "001",
                    "measured_at": "2026-09-28T17:45:00+07:00",
                    "metric": "Quantity_mL",
                    "value": 1545.00,
                    "unit": "mL",
                },
                # 2. Biên bản đề ngày 29/09, dòng không ghi giờ đo riêng (MeasuredAt=None), lấy số chốt cuối ngày 28/09 (1795 mL = 1.795 L) -> matched_latest_snapshot (kèm quy đổi đơn vị L -> mL)
                {
                    "row_number": 2,
                    "room_code": "R02",
                    "chemical_code": "005",
                    "measured_at": None,
                    "metric": "Quantity_mL",
                    "value": 1.99,
                    "unit": "L",
                },
                # 3. Ghi nhầm ngày đo thành 29/09 17:45 nhưng con số trùng khớp hoàn toàn với ngày 28/09 17:45 -> timestamp_mismatch
                {
                    "row_number": 3,
                    "room_code": "R01",
                    "chemical_code": "002",
                    "measured_at": "2026-09-29T17:45:00+07:00",
                    "metric": "Quantity_mL",
                    "value": 1795.00,
                    "unit": "mL",
                },
                # 4. Ghi số đo mới phát sinh của ngày 29/09 09:00 (khi DB mới cập nhật đến ngày 28/09) -> out_of_data_range (db_value = None, không trả 0)
                {
                    "row_number": 4,
                    "room_code": "R01",
                    "chemical_code": "001",
                    "measured_at": "2026-09-29T09:00:00+07:00",
                    "metric": "Quantity_mL",
                    "value": 1410.00,
                    "unit": "mL",
                },
                # 5. Chỉ số môi trường cấp phòng (không có ChemicalCode) bị lệch giá trị -> value_mismatch
                {
                    "row_number": 5,
                    "room_code": "R01",
                    "chemical_code": None,
                    "measured_at": "2026-09-28T17:45:00+07:00",
                    "metric": "Temperature_C",
                    "value": 28.00,
                    "unit": "C",
                },
                # 6. Sai đơn vị không quy đổi được (kg cho thể tích mL) -> unit_mismatch
                {
                    "row_number": 6,
                    "room_code": "R01",
                    "chemical_code": "001",
                    "measured_at": "2026-09-28T17:30:00+07:00",
                    "metric": "Quantity_mL",
                    "value": 1.5,
                    "unit": "kg",
                },
                # 7. Mã hóa chất không tồn tại -> unknown_chemical
                {
                    "row_number": 7,
                    "room_code": "R01",
                    "chemical_code": "099",
                    "measured_at": "2026-09-28T17:30:00+07:00",
                    "metric": "Quantity_mL",
                    "value": 100.0,
                    "unit": "mL",
                },
                # 8. Mã phòng không tồn tại -> unknown_room
                {
                    "row_number": 8,
                    "room_code": "R99",
                    "chemical_code": "001",
                    "measured_at": "2026-09-28T17:30:00+07:00",
                    "metric": "Quantity_mL",
                    "value": 100.0,
                    "unit": "mL",
                },
                # 9. Giá trị âm bất hợp lệ -> invalid_value
                {
                    "row_number": 9,
                    "room_code": "R01",
                    "chemical_code": "001",
                    "measured_at": "2026-09-28T17:30:00+07:00",
                    "metric": "Quantity_mL",
                    "value": -50.0,
                    "unit": "mL",
                },
            ]

            review_res = await review_and_reconcile_document(
                session,
                items=review_items,
                file_name="bao_cao_kiem_tra_29_09.csv",
                report_date="2026-09-29T08:30:00+07:00",
                check_missing_in_report=True,
            )

            by_row = {r["report_row_number"]: r for r in review_res["results"] if r["report_row_number"] is not None}
            assert by_row[1]["status"] == "matched"
            assert by_row[1]["abs_diff"] == 0.0

            assert by_row[2]["status"] == "matched_latest_snapshot"
            assert by_row[2]["report_value"] == 1990.0
            assert by_row[2]["report_unit"] == "mL"
            assert by_row[2]["db_value"] == 1990.0
            assert by_row[2]["db_measured_at"] == "2026-09-28T10:45:00+00:00"

            assert by_row[3]["status"] == "timestamp_mismatch"
            assert by_row[3]["db_measured_at"] == "2026-09-28T10:45:00+00:00"

            assert by_row[4]["status"] == "out_of_data_range"
            assert by_row[4]["db_value"] is None  # Không bao giờ trả số 0 giả!

            assert by_row[5]["status"] == "value_mismatch"
            assert by_row[5]["chemical_code"] is None
            assert by_row[5]["db_value"] == 25.2

            assert by_row[6]["status"] == "unit_mismatch"
            assert by_row[7]["status"] == "unknown_chemical"
            assert by_row[8]["status"] == "unknown_room"
            assert by_row[9]["status"] == "invalid_value"

            # Tại mốc 28/09 17:45 của phòng R01, báo cáo mới kê khai hóa chất 001 (dòng 1) mà bỏ sót hóa chất 002 -> missing_in_report
            missing_in_rep = [r for r in review_res["results"] if r["status"] == "missing_in_report"]
            assert len(missing_in_rep) == 1
            assert missing_in_rep[0]["room_code"] == "R01"
            assert missing_in_rep[0]["chemical_code"] == "002"
            assert missing_in_rep[0]["db_value"] == 1795.0


async def test_anomaly_detection_reproducibility_and_alert_deduplication(chem_db):
    """Kiểm tra phát hiện bất thường: giữ nguyên SourceAnomalyLabel, tái lập kết quả và chống lặp Alert."""
    who = make_principal(tenant_id=94)
    rules = [
        {
            "rule_code": "TVOC_HIGH",
            "rule_type": "threshold",
            "metric": "TVOC_ppb",
            "severity": "high",
            "version_no": 1,
            "parameters": {"max_value": 200.0},
        },
        {
            "rule_code": "QTY_SPIKE",
            "rule_type": "spike_drop",
            "metric": "Quantity_mL",
            "severity": "medium",
            "version_no": 1,
            "parameters": {"max_abs_delta": 30.0},
        },
    ]

    with use_principal(who):
        async with session_scope() as session:
            await import_chemical_measurements(
                session,
                file_bytes=SAMPLE_CSV.encode("utf-8"),
                file_name="anom_test.csv",
            )
            run1 = await run_anomaly_detection(session, rules=rules, create_alerts=True)
            assert run1["summary"]["total_findings"] == 2
            assert run1["summary"]["new_alerts"] == 2

            # Chạy lại cùng dữ liệu và cùng version rule -> cho cùng kết quả Finding, nhưng không nhân bản Alert
            run2 = await run_anomaly_detection(session, rules=rules, create_alerts=True)
            assert run2["summary"]["total_findings"] == 2
            assert run2["summary"]["new_alerts"] == 0
            assert run2["summary"]["existing_alerts"] == 2

            for f in run1["findings"]:
                # Không dùng từ "rò rỉ", "thất thoát", "nguy hiểm" khi chưa có căn cứ
                for forbidden in ("rò rỉ", "thất thoát", "nguy hiểm"):
                    assert forbidden not in f["explanation"].lower()

            # Cập nhật trạng thái Alert và kiểm tra SourceAnomalyLabel không bị ghi đè
            alert_id = run1["alerts"][0]["alert_id"]
            updated = await update_alert_status(
                session,
                alert_id=alert_id,
                new_status="Acknowledged",
                comment="Đã tiếp nhận kiểm tra phòng R02",
                assigned_to="ky_thuat_01",
            )
            assert updated["status"] == "Acknowledged"

            src_labels = await chem_tools.get_source_anomaly_labels(session=session)
            assert src_labels["count"] == 2


async def test_hybrid_chatbot_source_precedence_and_empty_handling(chem_db):
    """Kiểm tra Chatbot Hybrid: ưu tiên SQL Server cho số liệu, Qdrant cho hướng dẫn SDS/SOP, trả rỗng đúng chuẩn."""
    who = make_principal(tenant_id=94)

    async def fake_qdrant_retriever(query: str, chemical_code: str | None = None, room_code: str | None = None, top_n: int = 4):
        return [
            {
                "doc_id": "SDS-001",
                "doc_title": "Tài liệu An toàn Hóa chất 001 (SDS)",
                "chunk_id": "SDS-001#c1",
                "section": "Mục 7: Bảo quản",
                "version": "v2.1",
                "source_type": "sds",
                "chemical_code": chemical_code or "001",
                "cas_number": "67-64-1",
                "text": "Bảo quản hóa chất 001 ở nơi thoáng mát dưới 30°C. (Báo cáo cũ từng ghi lượng 9999 mL).",
                "score": 0.92,
                "collection": get_settings().chemical_qdrant_collection,
            }
        ]

    with use_principal(who):
        async with session_scope() as session:
            await import_chemical_measurements(
                session,
                file_bytes=SAMPLE_CSV.encode("utf-8"),
                file_name="chat_test.csv",
            )

        # 1. Câu hỏi kết hợp (vừa hỏi lượng hóa chất 001 tại phòng R01 vừa hỏi hướng dẫn bảo quản SDS)
        res_hybrid = await answer_chemical_question(
            "Lượng mới nhất của hóa chất 001 tại phòng R01 là bao nhiêu và hướng dẫn bảo quản trong SDS thế nào?",
            custom_retriever=fake_qdrant_retriever,
        )
        assert res_hybrid["intent"] == "hybrid"
        assert res_hybrid["precedence_policy"]["quantitative_and_anomalies"] == "sql_server"
        assert res_hybrid["precedence_policy"]["guidelines_and_sds"] == "qdrant"
        # Câu trả lời lấy đúng con số 1545.00 mL từ SQL Server và trích dẫn SDS-001 v2.1 từ Qdrant
        assert "1545.00 mL" in res_hybrid["answer"]
        assert "SDS-001" in res_hybrid["answer"]
        assert "v2.1" in res_hybrid["answer"]
        assert "[Nguồn SQL Server" in res_hybrid["answer"]
        assert "[Nguồn Tài liệu Qdrant" in res_hybrid["answer"]

        # 2. Câu hỏi cho phòng/hóa chất không có dữ liệu -> trả "Không có dữ liệu", không trả số 0 giả
        res_empty = await answer_chemical_question(
            "Lượng hóa chất 019 tại phòng R05 ngày 2026-09-28 là bao nhiêu?",
            custom_retriever=fake_qdrant_retriever,
        )
        assert "Không có dữ liệu" in res_empty["answer"]
        assert "0.00 mL" not in res_empty["answer"]

        # 3. Đảm bảo cấu hình Qdrant hóa chất tách riêng và SQLite pháp lý không bị thay đổi
        cfg = get_settings()
        assert cfg.chemical_qdrant_collection == "chemical_documents"
        assert cfg.qdrant_collection == "tpv_documents"
        assert "legal.db" in cfg.database_url


async def test_chemical_api_endpoints_end_to_end(chem_db):
    """Kiểm thử các REST API /api/chemicals/* và /api/chemical-chat."""
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from app.agents import quyen
    from app.api import chemicals as chemicals_api

    test_app = FastAPI()
    test_app.include_router(chemicals_api.router)

    @test_app.exception_handler(quyen.ThieuQuyen)
    async def _denied(request: Request, exc: quyen.ThieuQuyen):
        return JSONResponse(status_code=403, content={"detail": exc.message})

    @test_app.exception_handler(PermissionError)
    async def _perm_err(request: Request, exc: PermissionError):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    who = make_principal(tenant_id=94)
    unprivileged = make_principal(tenant_id=94, permissions=())

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:
        # Không có quyền -> 403
        with use_principal(unprivileged):
            r_denied = await client.get("/api/chemicals/rooms")
            assert r_denied.status_code == 403

        with use_principal(who):
            # Truyền tenant_id qua query string -> bị chặn 403
            r_override = await client.get("/api/chemicals/rooms?tenant_id=64")
            assert r_override.status_code == 403

            # 1. POST /api/chemicals/imports
            r_imp = await client.post(
                "/api/chemicals/imports",
                files={"file": ("sample.csv", SAMPLE_CSV.encode("utf-8"), "text/csv")},
            )
            assert r_imp.status_code == 200
            batch_id = r_imp.json()["batch_id"]

            # 2. GET /api/chemicals/imports/{batch_id}
            r_batch = await client.get(f"/api/chemicals/imports/{batch_id}")
            assert r_batch.status_code == 200
            assert r_batch.json()["inserted_row_count"] == 6

            # 3. GET /api/chemicals/rooms & /api/chemicals/catalog
            r_rooms = await client.get("/api/chemicals/rooms")
            assert r_rooms.status_code == 200
            assert [x["room_code"] for x in r_rooms.json()["items"]] == ["R01", "R02"]

            r_cat = await client.get("/api/chemicals/catalog")
            assert r_cat.status_code == 200
            assert [x["chemical_code"] for x in r_cat.json()["items"]] == ["001", "002", "005"]

            # 4. GET /api/chemicals/measurements & /api/chemicals/environment
            r_meas = await client.get("/api/chemicals/measurements?room_code=R01&chemical_code=001")
            assert r_meas.status_code == 200
            assert r_meas.json()["count"] == 2

            r_env = await client.get("/api/chemicals/environment?room_code=R01")
            assert r_env.status_code == 200
            assert r_env.json()["count"] == 2

            # 5. POST /api/chemicals/document-reviews
            r_rev = await client.post(
                "/api/chemicals/document-reviews",
                json={
                    "file_name": "bien_ban_29_09.csv",
                    "report_date": "2026-09-29T09:00:00+07:00",
                    "items": [
                        {
                            "row_number": 1,
                            "room_code": "R01",
                            "chemical_code": "001",
                            "measured_at": None,
                            "metric": "Quantity_mL",
                            "value": 1545.0,
                            "unit": "mL",
                        }
                    ],
                },
            )
            assert r_rev.status_code == 200
            rev_data = r_rev.json()
            assert rev_data["results"][0]["status"] == "matched_latest_snapshot"

            # 6. POST /api/chemicals/analysis-runs & GET /api/chemicals/anomalies
            r_run = await client.post(
                "/api/chemicals/analysis-runs",
                json={
                    "run_type": "anomaly_detection",
                    "rules": [
                        {
                            "rule_code": "TEMP_HIGH",
                            "rule_type": "threshold",
                            "metric": "Temperature_C",
                            "severity": "high",
                            "parameters": {"max_value": 30.0},
                        }
                    ],
                },
            )
            assert r_run.status_code == 200
            assert r_run.json()["summary"]["total_findings"] == 1

            r_anom = await client.get("/api/chemicals/anomalies")
            assert r_anom.status_code == 200
            assert r_anom.json()["count"] == 1

            # 7. POST /api/chemical-chat
            r_chat = await client.post(
                "/api/chemical-chat",
                json={"question": "Số liệu mới nhất của hóa chất 001 tại phòng R01 là bao nhiêu?"},
            )
            assert r_chat.status_code == 200
            assert "1545.00 mL" in r_chat.json()["answer"]


@pytest.mark.parametrize('live', [False, True])
async def test_ocr_preview_edited_rows_and_database_results(chem_db, monkeypatch, tmp_path, live):
    """Full report -> preview -> confirmed edits -> actual repository queries on isolated DB."""
    import os
    if live and os.environ.get('RUN_HC_OCR_LIVE') != '1':
        pytest.skip('Set RUN_HC_OCR_LIVE=1 for real OCR and extraction model')
    from io import BytesIO
    from types import SimpleNamespace
    from fastapi import FastAPI
    from PIL import Image, ImageDraw, ImageFont
    from app.api import chemicals
    from app.rag.ocr import get_ocr_service
    from app.services.llm import get_llm
    lines = [
        'BÁO CÁO HÓA CHẤT - Ngày lập: 29/09/2026 08:00 (UTC+7)',
        'Phòng R01, hóa chất 001: 1,545 L.',
        'Thời điểm đo: 28/09/2026 17:45 (UTC+7).',
        'Phòng R01, hóa chất 002: 1,795 L.',
        'Thời điểm đo: 28/09/2026 17:45 (UTC+7).',
        'Phòng R02, hóa chất 005: 0 mL.',
        'Thời điểm đo: 28/09/2026 17:45 (UTC+7).',
        'Phòng R01, hóa chất 001: 1234 mL.',
        'Thời điểm đo: 01/01/2030 08:00 (UTC+7).',
    ]
    image=Image.new('RGB',(1600,850),'white')
    draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',30)
    for i,line in enumerate(lines):draw.text((40,40+70*i),line,font=font,fill='black')
    raw=BytesIO();image.save(raw,format='PNG')
    rows=[
        {'room_code':'R01','chemical_code':'001','metric':'Quantity_L','value':1.545,'unit':'L','measured_at':'2026-09-28T17:45:00+07:00'},
        {'room_code':'R01','chemical_code':'002','metric':'Quantity_L','value':1.795,'unit':'L','measured_at':'2026-09-28T17:45:00+07:00'},
        {'room_code':'R02','chemical_code':'005','metric':'Quantity_mL','value':0,'unit':'mL','measured_at':'2026-09-28T17:45:00+07:00'},
        {'room_code':'R01','chemical_code':'001','metric':'Quantity_mL','value':1234,'unit':'mL','measured_at':'2030-01-01T08:00:00+07:00'},
    ]
    service=get_ocr_service()
    monkeypatch.setattr(service.settings,'ocr_enabled',True)
    if not live:
        monkeypatch.setattr(service,'_ocr_one',lambda *args:'\n'.join(lines))
        async def extract(*args,**kwargs):
            return {'items':rows,'report_date':'2026-09-29T08:00:00+07:00'}
        monkeypatch.setattr(chemicals,'get_llm',lambda:SimpleNamespace(chat_json=extract))
    else:
        original_pages=service.ocr_pages
        def traced_pages(*args, **kwargs):
            pages=original_pages(*args, **kwargs)
            import json
            (tmp_path/'live_ocr.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2))
            return pages
        monkeypatch.setattr(service,'ocr_pages',traced_pages)
    test_app=FastAPI();test_app.include_router(chemicals.router)
    who=make_principal(tenant_id=94)
    try:
        with use_principal(who):
            async with session_scope() as session:
                await import_chemical_measurements(session,file_bytes=SAMPLE_CSV.encode(),file_name='isolated-reference.csv')
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app),base_url='http://test') as client:
                preview=await client.post('/api/chemicals/document-reviews/preview',files={'file':('report.png',raw.getvalue())})
                assert preview.status_code==200,preview.text
                body=preview.json()
                if live:
                    import json
                    (tmp_path/'live_preview.json').write_text(json.dumps(body,ensure_ascii=False,indent=2))
                assert len(body['items'])==4,body
                for row in body['items']: assert row['metric']=='Quantity_mL',row
                by_key={(r['room_code'],r['chemical_code'],float(str(r['value']).replace(',', '.'))):r for r in body['items']}
                matched=by_key[('R01','001',1.545)]
                assert matched['unit']=='L'
                corrected=by_key[('R01','002',1.795)]
                corrected['value']='1,8' # user edits the extracted value before confirmation
                confirm=await client.post('/api/chemicals/document-reviews',json={
                    'file_name':body['file_name'],'items':body['items'],
                    'report_date':body['report_date'],'check_missing_in_report':False})
                assert confirm.status_code==200,confirm.text
                results=confirm.json()['results']
                exact=next(r for r in results if r['chemical_code']=='001' and r['status']=='matched')
                assert (exact['report_value'],exact['report_unit'],exact['db_value'])==(1545,'mL',1545)
                changed=next(r for r in results if r['chemical_code']=='002')
                assert changed['status']=='value_mismatch'
                assert changed['report_value']==1800 and changed['db_value']==1795 and changed['abs_diff']==5
                zero=next(r for r in results if r['chemical_code']=='005')
                assert zero['report_value']==0 and zero['db_value']==1990 and zero['status']=='value_mismatch'
                missing=next(r for r in results if r['status']=='out_of_data_range')
                assert missing['db_value'] is None
                if live:
                    import json
                    (tmp_path/'live_result.json').write_text(json.dumps({'preview':body,'results':results},ensure_ascii=False,indent=2))
    finally:
        if live: await get_llm().close()
