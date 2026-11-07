import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import pyodbc

CONN_STR = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=127.0.0.1,1433;"
    "DATABASE=tpv_chemical_monitoring;"
    "UID=sa;PWD=oVhbBzrXqMqArvOiOqLd#K9u;"
    "TrustServerCertificate=yes;Encrypt=yes;"
)

def seed_rich_data():
    conn = pyodbc.connect(CONN_STR)
    conn.autocommit = False
    cursor = conn.cursor()
    tenant_id = 94
    now = datetime(2026, 9, 28, 10, 45, 0, tzinfo=timezone.utc)
    
    try:
        # 1. Update Room names
        cursor.execute("UPDATE chem.Rooms SET RoomName = ? WHERE TenantId = ? AND RoomCode = 'R01'", 'Kho Hóa Chất Trung Tâm A', tenant_id)
        cursor.execute("UPDATE chem.Rooms SET RoomName = ? WHERE TenantId = ? AND RoomCode = 'R02'", 'Phòng Thí Nghiệm & Pha Chế B', tenant_id)
        
        # Room R03
        cursor.execute("SELECT RoomId FROM chem.Rooms WHERE TenantId = ? AND RoomCode = 'R03'", tenant_id)
        row = cursor.fetchone()
        if not row:
            cursor.execute(
                "INSERT INTO chem.Rooms (TenantId, RoomCode, RoomName, IsActive) VALUES (?, 'R03', ?, 1)",
                tenant_id, 'Kho Dung Môi & Phụ Gia C'
            )
            cursor.execute("SELECT RoomId FROM chem.Rooms WHERE TenantId = ? AND RoomCode = 'R03'", tenant_id)
            r03_id = cursor.fetchone()[0]
        else:
            r03_id = row[0]
            cursor.execute("UPDATE chem.Rooms SET RoomName = ? WHERE RoomId = ?", 'Kho Dung Môi & Phụ Gia C', r03_id)

        # 2. Update Chemical names & CAS
        cursor.execute("UPDATE chem.Chemicals SET ChemicalName = ?, CASNumber = '7664-93-9' WHERE TenantId = ? AND ChemicalCode = '001'", 'Axit Sunfuric H2SO4 98%', tenant_id)
        cursor.execute("UPDATE chem.Chemicals SET ChemicalName = ?, CASNumber = '64-17-5' WHERE TenantId = ? AND ChemicalCode = '002'", 'Cồn Công Nghiệp Ethanol 96%', tenant_id)
        cursor.execute("UPDATE chem.Chemicals SET ChemicalName = ?, CASNumber = '67-64-1' WHERE TenantId = ? AND ChemicalCode = '005'", 'Dung môi Acetone kỹ thuật', tenant_id)

        # Add Chemical 007 (NaOH) and 009 (Toluene)
        chem_defs = [
            ('007', 'Xút vảy Natri Hydroxit NaOH 99%', '1310-73-2'),
            ('009', 'Dung môi Toluene C7H8', '108-88-3')
        ]
        
        cids = {}
        for c_code, c_name, cas in chem_defs:
            cursor.execute("SELECT ChemicalId FROM chem.Chemicals WHERE TenantId = ? AND ChemicalCode = ?", tenant_id, c_code)
            crow = cursor.fetchone()
            if not crow:
                cursor.execute(
                    "INSERT INTO chem.Chemicals (TenantId, ChemicalCode, ChemicalName, CASNumber, IsActive) VALUES (?, ?, ?, ?, 1)",
                    tenant_id, c_code, c_name, cas
                )
                cursor.execute("SELECT ChemicalId FROM chem.Chemicals WHERE TenantId = ? AND ChemicalCode = ?", tenant_id, c_code)
                cid = cursor.fetchone()[0]
            else:
                cid = crow[0]
                cursor.execute("UPDATE chem.Chemicals SET ChemicalName = ?, CASNumber = ? WHERE ChemicalId = ?", c_name, cas, cid)
            cids[c_code] = cid

        # Get room IDs
        cursor.execute("SELECT RoomId FROM chem.Rooms WHERE TenantId = ? AND RoomCode = 'R01'", tenant_id)
        r01_id = cursor.fetchone()[0]
        cursor.execute("SELECT RoomId FROM chem.Rooms WHERE TenantId = ? AND RoomCode = 'R02'", tenant_id)
        r02_id = cursor.fetchone()[0]

        # Ensure RoomChemicals
        pairs = [(r01_id, cids['007']), (r03_id, cids['007']), (r02_id, cids['009']), (r03_id, cids['009'])]
        for rid, cid in pairs:
            cursor.execute("SELECT RoomId FROM chem.RoomChemicals WHERE TenantId = ? AND RoomId = ? AND ChemicalId = ?", tenant_id, rid, cid)
            if not cursor.fetchone():
                cursor.execute("INSERT INTO chem.RoomChemicals (TenantId, RoomId, ChemicalId, IsActive) VALUES (?, ?, ?, 1)", tenant_id, rid, cid)

        # Add RoomMeasurement for R03 at 10:45
        cursor.execute("SELECT RoomMeasurementId FROM chem.RoomMeasurements WHERE TenantId = ? AND RoomId = ? AND MeasuredAt = '2026-09-28 10:45:00+00:00'", tenant_id, r03_id)
        rm_row = cursor.fetchone()
        if not rm_row:
            cursor.execute(
                "INSERT INTO chem.RoomMeasurements (TenantId, RoomId, MeasuredAt, TemperatureC, HumidityPct, TVOCPpb, BatchId) "
                "VALUES (?, ?, '2026-09-28 10:45:00+00:00', 25.80, 58.00, 135.00, 1)",
                tenant_id, r03_id
            )
            cursor.execute("SELECT RoomMeasurementId FROM chem.RoomMeasurements WHERE TenantId = ? AND RoomId = ? AND MeasuredAt = '2026-09-28 10:45:00+00:00'", tenant_id, r03_id)
            rm03_id = cursor.fetchone()[0]
        else:
            rm03_id = rm_row[0]

        # Add ChemicalMeasurements for 007 & 009
        # R01 at 10:45 had RM id 7
        cursor.execute("SELECT RoomMeasurementId FROM chem.RoomMeasurements WHERE TenantId = ? AND RoomId = ? AND MeasuredAt = '2026-09-28 10:45:00+00:00'", tenant_id, r01_id)
        rm01_id = cursor.fetchone()[0]
        cursor.execute("SELECT RoomMeasurementId FROM chem.RoomMeasurements WHERE TenantId = ? AND RoomId = ? AND MeasuredAt = '2026-09-28 10:45:00+00:00'", tenant_id, r02_id)
        rm02_id = cursor.fetchone()[0]

        cm_inserts = [
            (rm01_id, r01_id, cids['007'], 25000.0, 0, 14),
            (rm03_id, r03_id, cids['007'], 15000.0, 0, 15),
            (rm02_id, r02_id, cids['009'], 3200.0, 0, 16),
            (rm03_id, r03_id, cids['009'], 5000.0, 0, 17),
        ]
        for r_m_id, rid, cid, qty, anom, row_num in cm_inserts:
            cursor.execute("SELECT ChemicalMeasurementId FROM chem.ChemicalMeasurements WHERE TenantId = ? AND RoomMeasurementId = ? AND ChemicalId = ?", tenant_id, r_m_id, cid)
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO chem.ChemicalMeasurements (TenantId, RoomMeasurementId, RoomId, ChemicalId, QuantityRecordedMl, SourceAnomalyLabel, BatchId, SourceRowNumber) "
                    "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
                    tenant_id, r_m_id, rid, cid, qty, anom, row_num
                )

        conn.commit()
        print("Successfully seeded rich mock data!")
    except Exception as e:
        conn.rollback()
        print("Error seeding mock data:", e)
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    seed_rich_data()
