import sys,asyncio,json,os
from pathlib import Path
sys.path.insert(0,'.')
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.context import Principal,use_principal
from app.db.erp_auth import AccountAccess
from app.db import chemical_session
from app.db.chemical_models import ChemicalBase
from app.services.chemical_importer import import_chemical_measurements
from app.services.chemical_reconciliation import review_and_reconcile_document
from app.services.chemical_report_files import read_report_file
from app.api.chemicals import extract_chemical_document_text
from app.services.llm import get_llm
import anyio
ROOT=Path(__file__).resolve().parents[1]
async def main():
    engine=create_async_engine('sqlite+aiosqlite:///:memory:')
    @event.listens_for(engine.sync_engine,'connect')
    def attach(conn,record):conn.execute("ATTACH DATABASE ':memory:' AS chem")
    async with engine.begin() as conn:await conn.run_sync(ChemicalBase.metadata.create_all)
    chemical_session.configure_engine(engine)
    who=Principal(tenant_id=94,user_id='421',access=AccountAccess(421,94,'test','Test','',permissions=frozenset({'Ai.AiChatbot','Ai.DocumentReview','Ai.ReportSummary.Create'})))
    results=[]
    try:
        with use_principal(who):
            async with chemical_session.session_scope() as session:
                loaded=await import_chemical_measurements(session,file_bytes=(ROOT/'01_du_lieu_goc/du_lieu_goc.csv').read_bytes(),file_name='du_lieu_goc.csv',strict=True)
                assert loaded['inserted_row_count']==8,loaded
            golden=json.loads((ROOT/'03_dap_an/ket_qua_mong_doi.json').read_text())
            paths=[ROOT/f'02_bao_cao_kiem_thu/{stem}.{ext}' for stem in ['bao_cao_dung','bao_cao_co_sai_so'] for ext in ['csv','xlsx','json']]
            if os.environ.get('HC_LIVE')=='1':paths += [ROOT/'02_bao_cao_kiem_thu/bao_cao_co_sai_so.png',ROOT/'02_bao_cao_kiem_thu/bao_cao_co_sai_so_scan.pdf']
            for file in paths:
                contents=await anyio.to_thread.run_sync(read_report_file,file.read_bytes(),file.name)
                items=contents.items
                date=contents.report_date or golden['report_date']
                if not items:
                    extracted=await extract_chemical_document_text(contents.text)
                    items=extracted['items']
                    for index,row in enumerate(items,1):row['row_number']=index
                    date=extracted.get('report_date') or date
                async with chemical_session.session_scope() as session:
                    result=await review_and_reconcile_document(session,items=items,file_name=file.name,report_date=date,check_missing_in_report=True)
                if file.stem=='bao_cao_dung':
                    assert result['summary']['counts_by_status']=={'matched':9},result
                else:
                    assert len(result['results'])==9,result
                    for actual,expected in zip(result['results'],golden['items'],strict=True):
                        assert actual['status']==expected['status'],(file.name,actual,expected)
                        for field,expected_field in [('report_value','report_value_normalized'),('db_value','db_value'),('abs_diff','difference')]:
                            assert actual[field]==expected[expected_field],(file.name,field,actual,expected)
                results.append({'file':file.name,'counts':result['summary']['counts_by_status'],'verified':True,'results':result['results']})
                print(file.name,result['summary']['counts_by_status'],flush=True)
        (ROOT/'03_dap_an/ket_qua_da_kiem_chung.json').write_text(json.dumps({'database':'Isolated SQLite using the application repository and reconciliation code; no customer SQL Server writes','imported_rows':loaded['inserted_row_count'],'runs':results},ensure_ascii=False,indent=2))
    finally:
        await chemical_session.dispose()
        if os.environ.get('HC_LIVE')=='1':await get_llm().close()
asyncio.run(main())
