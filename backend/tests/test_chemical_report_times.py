from types import SimpleNamespace
from datetime import timezone

import httpx
import pytest

from app.api import chemicals
from app.main import app
from app.services.chemical_importer import parse_timestamp_utc
from app.services.chemical_report_times import restore_source_times
from app.services.integration_errors import IntegrationError

TABLE = '''Ngày lập báo cáo: 08/11/2026 09:30 (UTC+7)
| Dòng | Phòng | Mã hóa chất | Thời điểm đo | Chỉ số | Giá trị | Đơn vị |
|---|---|---|---|---|---|---|
| 1 | R01 | 001 | 2026-11-07T08:00:00+07:00 | Quantity_mL | 1500 | mL |
| 2 | R01 | 002 | 2026-11-08T08:00:00+07:00 | Quantity_mL | 1234 | mL |
| 3 | R01 | 001 | 2026-11-08T08:00:00+07:00 | Quantity_mL | 1500 | mL |
'''
ITEMS = [
    {'room_code':'R01','chemical_code':'001','metric':'Quantity_mL','value':1500,'unit':'mL','measured_at':'2026-11-07T01:00:00Z'},
    {'room_code':'R01','chemical_code':'002','metric':'Quantity_mL','value':1234,'unit':'mL','measured_at':'2026-11-07T23:00:00Z'},
    {'room_code':'R01','chemical_code':'001','metric':'Quantity_mL','value':1500,'unit':'mL','measured_at':'2026-11-07T23:00:00Z'},
]


def test_restore_exact_source_rows_including_duplicate_room_code_and_amount():
    rows, report = restore_source_times(TABLE, ITEMS, '2026-11-07T23:30:00Z')
    assert report == '2026-11-08T09:30:00+07:00'
    assert rows[0]['measured_at'] == '2026-11-07T08:00:00+07:00'
    assert rows[1]['measured_at'] == rows[2]['measured_at'] == '2026-11-08T08:00:00+07:00'
    assert parse_timestamp_utc(rows[2]['measured_at']).isoformat() == '2026-11-08T01:00:00+00:00'
    assert ITEMS[2]['measured_at'] == '2026-11-07T23:00:00Z' # no mutation of model/source input


def test_table_binding_uses_identity_not_only_row_order():
    table = '\n'.join(TABLE.splitlines()[:3] + [TABLE.splitlines()[4]])
    row = {**ITEMS[1], 'measured_at':None}
    restored, _ = restore_source_times(table, [row], None)
    assert restored[0]['measured_at'] == '2026-11-08T08:00:00+07:00'


def test_reordered_duplicate_source_rows_require_verification():
    with pytest.raises(IntegrationError, match='trùng'):
        restore_source_times(TABLE, [ITEMS[2],ITEMS[1]],None)


@pytest.mark.parametrize('offset,expected_utc', [('+07:00','2026-11-08T01:00:00+00:00'),('-05:00','2026-11-08T13:00:00+00:00')])
def test_preserves_source_offsets_instead_of_hardcoding_utc7(offset,expected_utc):
    text = f'Phòng R01 hóa chất 001 có 1500 mL, đo lúc 2026-11-08T08:00:00{offset}.'
    rows,_ = restore_source_times(text,[{**ITEMS[0],'measured_at':expected_utc}],None)
    assert rows[0]['measured_at'] == f'2026-11-08T08:00:00{offset}'
    assert parse_timestamp_utc(rows[0]['measured_at']).isoformat() == expected_utc


def test_prose_wrong_time_is_rejected_instead_of_becoming_missing_database():
    text='Phòng R01 hóa chất 001 có 1500 mL, đo lúc 2026-11-08T08:00:00+07:00.'
    with pytest.raises(IntegrationError, match='Thời điểm trích xuất không khớp'):
        restore_source_times(text,[ITEMS[2]],None)


def test_prose_vietnamese_date_can_be_validated_by_code():
    text='Phòng R01 hóa chất 001 có 1500 mL. Thời điểm đo: 08/11/2026 08:00 (UTC+7).'
    rows,_=restore_source_times(text,[{**ITEMS[0],'measured_at':'2026-11-08T01:00:00Z'}],None)
    assert rows[0]['measured_at']=='2026-11-08T08:00:00+07:00'


def test_no_measurement_time_stays_null():
    text='Ngày lập báo cáo: 08/11/2026 09:30 (UTC+7). Phòng R01 còn 1500 mL.'
    rows,_=restore_source_times(text,[{**ITEMS[0],'measured_at':None}],None)
    assert rows[0]['measured_at'] is None


@pytest.mark.anyio
async def test_api_corrects_shifted_model_times_before_preview(monkeypatch,authorized_account):
    async def chat_json(*args,**kwargs):return {'items':ITEMS,'report_date':'2026-11-07T23:30:00Z'}
    monkeypatch.setattr(chemicals,'get_llm',lambda:SimpleNamespace(chat_json=chat_json))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'X-Access-Token':'test-business-token'}) as client:
        response=await client.post('/api/chemicals/document-reviews/extract',json={'text':TABLE})
    assert response.status_code==200,response.text
    assert response.json()['items'][2]['measured_at']=='2026-11-08T08:00:00+07:00'
    assert response.json()['report_date']=='2026-11-08T09:30:00+07:00'


def test_model_cannot_invent_measurement_time_from_report_header():
    text='Ngày lập báo cáo: 08/11/2026 09:30 (UTC+7). Phòng R01 còn 1500 mL.'
    with pytest.raises(IntegrationError, match='Không tìm thấy thời điểm đo'):
        restore_source_times(text,[ITEMS[0]],None)
