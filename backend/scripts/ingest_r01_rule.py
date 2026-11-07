import asyncio
from pathlib import Path
from app.rag.vectorstore import QdrantVectorStore, ChunkPoint
from app.rag.embedding import embed_documents
from app.rag.chunking import Chunker
from app.core.config import get_settings

async def ingest_file():
    settings = get_settings()
    store = QdrantVectorStore(settings=settings)
    store.collection = settings.chemical_qdrant_collection  # chemical_documents
    print("Ingesting into collection:", store.collection)
    
    file_path = Path("/home/abc/long_workspace/TPV-Chatbot-HC/data_samples/QUY_TAC_AN_TOAN_PHONG_R01.md")
    content = file_path.read_text(encoding="utf-8")
    
    chunker = Chunker()
    raw_chunks = chunker.split(content)
    print(f"Parsed {len(raw_chunks)} chunks from file.")
    
    texts = [c.text for c in raw_chunks]
    embeddings = embed_documents(texts)
    
    points = []
    doc_id = "QC-AN-TOAN-R01-v2.0"
    doc_title = "Quy chuẩn và Nội quy an toàn phòng lưu trữ hóa chất R01"
    
    for c, emb in zip(raw_chunks, embeddings):
        payload = {
            "doc_id": doc_id,
            "doc_title": doc_title,
            "doc_type": "QUY_DINH",
            "source": "NoiQuyKho_R01",
            "tenant_id": 94,
            "section": c.section or "Nội quy kho R01",
            "chapter": c.chapter or "",
            "chunk_index": c.index,
            "latest": True,
            "room_code": "R01",
            "text": c.text,
        }
        pt = ChunkPoint(
            doc_id=doc_id,
            chunk_index=c.index,
            text=c.text,
            embedding=emb,
            payload=payload,
            snapshot=0
        )
        points.append(pt)
        
    n = await store.upsert_chunks(points)
    print(f"Successfully ingested {n} chunks into Qdrant collection {store.collection}!")

if __name__ == '__main__':
    asyncio.run(ingest_file())
