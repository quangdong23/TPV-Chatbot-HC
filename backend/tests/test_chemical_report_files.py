from contextlib import asynccontextmanager
from io import BytesIO
import json

import httpx
import pymupdf
import pytest
from docx import Document
from PIL import Image

from app.api import chemicals
from app.core.config import get_settings
from app.main import app
from app.services import chemical_report_files as files

TEXT = 'Phong R01: hoa chat 001 co 1500 mL. Nhiet do 25 C. ' * 8
ROW = {'room_code': 'R01', 'chemical_code': '001', 'metric': 'Quantity_mL', 'value': 1500, 'unit': 'mL'}


def make_file(ext):
    if ext in ('.md', '.txt'):
        return TEXT.encode()
    if ext == '.json':
        return json.dumps({'items': [ROW], 'report_date': '2026-09-28'}).encode()
    if ext == '.csv':
        return b'room_code,chemical_code,metric,value,unit\nR01,001,Quantity_mL,1500,mL\n'
    if ext == '.xlsx':
        from openpyxl import Workbook
        book=Workbook(); sheet=book.active
        sheet.append(['room_code','chemical_code','metric','value','unit'])
        sheet.append(['R01','001','Quantity_mL',1500,'mL'])
        out=BytesIO();book.save(out);return out.getvalue()
    if ext == '.docx':
        doc=Document();doc.add_paragraph(TEXT)
        table=doc.add_table(rows=1,cols=2)
        table.rows[0].cells[0].text='Chemical';table.rows[0].cells[1].text='Quantity'
        cells=table.add_row().cells;cells[0].text='001';cells[1].text='1500 mL'
        out=BytesIO();doc.save(out);return out.getvalue()
    if ext == '.pdf':
        doc=pymupdf.open();page=doc.new_page()
        page.insert_textbox(pymupdf.Rect(72,72,520,700),TEXT,fontsize=11)
        out=doc.tobytes();doc.close();return out
    out=BytesIO();Image.new('RGB',(100,100),'white').save(out,format='JPEG' if ext in ('.jpg','.jpeg') else 'PNG')
    return out.getvalue()


@pytest.fixture
def mock_ocr(monkeypatch):
    from app.rag.ocr import get_ocr_service
    service=get_ocr_service()
    monkeypatch.setattr(service.settings,'ocr_enabled',True)
    monkeypatch.setattr(service,'ocr_pages',lambda path,indices,**kwargs: {i:TEXT for i in indices})
    return service


@pytest.mark.parametrize('ext', ['.txt','.xlsx','.csv','.json','.pdf','.docx','.jpg','.jpeg','.png','.md'])
def test_read_supported_files(ext,mock_ocr):
    result=files.read_report_file(make_file(ext),'report'+ext)
    assert result.items or '1500' in result.text
    if ext=='.docx':
        assert 'Chemical' in result.text


def test_digital_pdf_does_not_require_vision(monkeypatch,mock_ocr):
    monkeypatch.setattr(mock_ocr.settings,'ocr_enabled',False)
    assert '1500' in files.read_report_file(make_file('.pdf'),'report.PDF').text


def test_scan_failure_is_not_silently_ignored(monkeypatch,mock_ocr):
    monkeypatch.setattr(mock_ocr,'ocr_pages',lambda *args,**kwargs:{})
    with pytest.raises(ValueError,match='trang OCR'):
        files.read_report_file(make_file('.png'),'scan.png')


@pytest.mark.parametrize('ext', ['.txt','.xlsx','.csv','.json','.pdf','.docx','.jpg','.jpeg','.png','.md'])
@pytest.mark.anyio
async def test_upload_extracts_before_reconciliation(ext,monkeypatch,authorized_account,mock_ocr):
    captured={}
    async def extract(text):
        assert '1500' in text
        return {'items':[ROW],'report_date':'2026-09-28'}
    @asynccontextmanager
    async def scope():
        yield object()
    async def review(session,**kwargs):
        captured.update(kwargs)
        return {'results':[], 'analysis_run_id':123}
    monkeypatch.setattr(chemicals,'extract_chemical_document_text',extract)
    monkeypatch.setattr(chemicals,'session_scope',scope)
    monkeypatch.setattr(chemicals,'review_and_reconcile_document',review)
    raw = make_file(ext)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'X-Access-Token':'test-business-token'}) as client:
        response=await client.post('/api/chemicals/document-reviews',files={'file':('report'+ext,raw)})
    assert response.status_code==200,response.text
    assert captured['items'][0]['value'] in (1500,'1500')
    assert captured['file_bytes'] == raw
    assert captured['file_name']=='report'+ext


@pytest.mark.parametrize('name,raw,status', [('report.exe',b'bad',415),('broken.pdf',b'not pdf',422),('empty.md',b'',422)])
@pytest.mark.anyio
async def test_bad_upload_never_opens_write_session(name,raw,status,monkeypatch,authorized_account):
    def no_session():
        raise AssertionError('must not open session')
    monkeypatch.setattr(chemicals,'session_scope',no_session)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'X-Access-Token':'test-business-token'}) as client:
        response=await client.post('/api/chemicals/document-reviews',files={'file':(name,raw)})
    assert response.status_code==status,response.text


@pytest.mark.parametrize('ext', ['.txt','.xlsx','.csv','.json','.pdf','.docx','.jpg','.jpeg','.png','.md'])
@pytest.mark.anyio
async def test_preview_only_reads_and_never_opens_reconciliation(ext, monkeypatch, authorized_account, mock_ocr):
    async def extract(text):
        return {'items': [ROW], 'report_date': '2026-11-07T08:00:00+07:00'}
    def no_session():
        raise AssertionError('Preview must not write a reconciliation run')
    monkeypatch.setattr(chemicals, 'extract_chemical_document_text', extract)
    monkeypatch.setattr(chemicals, 'session_scope', no_session)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers={'X-Access-Token':'test-business-token'}) as client:
        response = await client.post('/api/chemicals/document-reviews/preview', files={'file': ('report'+ext, make_file(ext))})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['items'][0]['value'] in (1500, '1500')
    assert body['items'][0]['chemical_code'] == '001'
    assert 'analysis_run_id' not in body


@pytest.mark.anyio
async def test_confirmed_edits_go_to_reconciliation_without_reextracting(monkeypatch, authorized_account):
    captured = {}
    @asynccontextmanager
    async def scope():
        yield object()
    async def review(session, **kwargs):
        captured.update(kwargs)
        return {'results': []}
    async def no_extract(*args):
        raise AssertionError('Confirmed rows must not be extracted again')
    monkeypatch.setattr(chemicals, 'session_scope', scope)
    monkeypatch.setattr(chemicals, 'review_and_reconcile_document', review)
    monkeypatch.setattr(chemicals, 'extract_chemical_document_text', no_extract)
    corrected = {**ROW, 'value': '1,25', 'unit': 'L', 'measured_at': '2026-11-07T08:00:00+07:00'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers={'X-Access-Token':'test-business-token'}) as client:
        response = await client.post('/api/chemicals/document-reviews', json={'file_name':'report.pdf', 'items':[corrected]})
    assert response.status_code == 200, response.text
    assert captured['items'][0]['value'] == '1,25'
    assert captured['items'][0]['chemical_code'] == '001'
    assert captured['items'][0]['unit'] == 'L'


@pytest.mark.anyio
@pytest.mark.parametrize('raw_metric,unit', [('Quantity_L','L'),('Quantity_mL','L'),('quantity_l',None)])
async def test_preview_normalizes_volume_without_changing_source_amount(raw_metric,unit,monkeypatch,authorized_account):
    async def chat_json(*args, **kwargs):
        assert kwargs['thinking'] is False
        return {'items':[{**ROW,'metric':raw_metric,'value':1.25,'unit':unit}], 'report_date':None}
    from types import SimpleNamespace
    monkeypatch.setattr(chemicals,'get_llm',lambda:SimpleNamespace(chat_json=chat_json))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'X-Access-Token':'test-business-token'}) as client:
        response=await client.post('/api/chemicals/document-reviews/preview',files={'file':('report.txt','Phòng R01: hóa chất 001 còn 1,25 L.'.encode())})
    assert response.status_code==200,response.text
    row=response.json()['items'][0]
    assert (row['metric'],row['value'],row['unit'])==('Quantity_mL',1.25,'L')


@pytest.mark.anyio
@pytest.mark.parametrize('metric',['Quantity_g','Weight_g','Invented_Metric'])
async def test_unsupported_metrics_rejected_before_database(metric,monkeypatch,authorized_account):
    def no_session(): raise AssertionError('Unsupported metrics must not query/write SQL')
    monkeypatch.setattr(chemicals,'session_scope',no_session)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'X-Access-Token':'test-business-token'}) as client:
        response=await client.post('/api/chemicals/document-reviews',json={'items':[{**ROW,'metric':metric}]})
    assert response.status_code==422,response.text
    assert 'chưa được hỗ trợ' in response.json()['error']['message']
    assert metric in response.json()['error']['message']


@pytest.mark.anyio
@pytest.mark.parametrize('stage,exception,status,code',[
    ('extract',TimeoutError('secret endpoint'),504,'TIMEOUT'),
    ('extract',httpx.ConnectError('secret endpoint'),502,'MODEL_UNREACHABLE'),
    ('ocr',httpx.ReadTimeout('secret endpoint'),504,'TIMEOUT'),
    ('ocr',httpx.ConnectError('secret endpoint'),502,'MODEL_UNREACHABLE'),
])
async def test_model_failure_keeps_stage_and_error_category(stage,exception,status,code,monkeypatch,authorized_account):
    from types import SimpleNamespace
    from app.rag.ocr import get_ocr_service
    if stage=='extract':
        async def fail(*args,**kwargs): raise exception
        monkeypatch.setattr(chemicals,'get_llm',lambda:SimpleNamespace(chat_json=fail))
        name,raw='report.txt',TEXT.encode()
    else:
        service=get_ocr_service()
        monkeypatch.setattr(service.settings,'ocr_enabled',True)
        def fail(*args,**kwargs): raise exception
        # Actual thread-pool OCR propagation, not a mock of ocr_pages.
        monkeypatch.setattr(service,'_ocr_one',fail)
        name,raw='report.png',make_file('.png')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'X-Access-Token':'test-business-token'}) as client:
        response=await client.post('/api/chemicals/document-reviews/preview',files={'file':(name,raw)})
    assert response.status_code==status,response.text
    error=response.json()['error']
    assert error['code']==code
    assert ('OCR' if stage=='ocr' else 'trích xuất') in error['message']
    assert 'secret endpoint' not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize('model_result,status,phrase',[
    ({'items':[]},422,'không tìm thấy số liệu'),
    ([],502,'sai định dạng'),
    ({'items':'invalid'},502,'sai định dạng'),
    ({'items':[{'room_code':'R01'}]},502,'thiếu mã phòng hoặc giá trị'),
])
async def test_empty_data_and_malformed_model_response_are_different(model_result,status,phrase,monkeypatch,authorized_account):
    from types import SimpleNamespace
    async def chat_json(*args,**kwargs): return model_result
    monkeypatch.setattr(chemicals,'get_llm',lambda:SimpleNamespace(chat_json=chat_json))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'X-Access-Token':'test-business-token'}) as client:
        response=await client.post('/api/chemicals/document-reviews/preview',files={'file':('report.txt',TEXT.encode())})
    assert response.status_code==status,response.text
    assert phrase in response.json()['error']['message']


@pytest.mark.anyio
@pytest.mark.parametrize('source,value,status', [
    ('Phòng R01, hóa chất 001: 1,545 L.', '1,545', 200),
    ('Phòng R01, hóa chất 001: 1,545 L.', 1.545, 200),
    ('Phòng R01, hóa chất 001: 1,545 L.', 1545, 502),
    ('Phòng R01, hóa chất 001: 0 mL.', '0', 200),
    ('Phòng R01, hóa chất 001: 1500 mL.', 9999, 502),
])
async def test_extraction_does_not_change_source_decimal(source,value,status,monkeypatch,authorized_account):
    from types import SimpleNamespace
    async def chat_json(*args,**kwargs):
        return {'items':[{**ROW,'value':value,'unit':'L'}]}
    monkeypatch.setattr(chemicals,'get_llm',lambda:SimpleNamespace(chat_json=chat_json))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'X-Access-Token':'test-business-token'}) as client:
        response=await client.post('/api/chemicals/document-reviews/extract',json={'text':source})
    assert response.status_code==status,response.text
    if status==502:
        assert 'không khớp số' in response.json()['error']['message']
