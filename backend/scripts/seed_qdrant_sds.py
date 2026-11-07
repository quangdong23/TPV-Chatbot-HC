import asyncio
from app.rag.vectorstore import QdrantVectorStore, ChunkPoint
from app.rag.embedding import embed_documents
from app.core.config import get_settings

async def seed_sds():
    settings = get_settings()
    store = QdrantVectorStore(settings=settings)
    store.collection = settings.chemical_qdrant_collection  # chemical_documents
    print("Using collection:", store.collection)
    
    docs = [
        {
            "doc_id": "SDS-H2SO4-001",
            "doc_title": "Phiếu an toàn hóa chất Axit Sunfuric H2SO4 98%",
            "content": (
                "PHIẾU AN TOÀN HÓA CHẤT (SDS/MSDS) - AXIT SUNFURIC (H2SO4) 98%\n"
                "Mã hóa chất nội bộ: 001. Số CAS: 7664-93-9.\n"
                "1. Đặc tính nguy hiểm: Axit vô cơ ăn mòn rất mạnh, gây bỏng da nghiêm trọng và tổn thương mắt vĩnh viễn. Phản ứng sinh nhiệt mãnh liệt khi tiếp xúc với nước.\n"
                "2. Quy định bảo quản và lưu kho: Lưu trữ tại Kho Hóa Chất Trung Tâm A (R01). Nhiệt độ bảo quản khuyến nghị dưới 30°C. Phải lưu trữ trong bồn chứa chuyên dụng chống axit (nhựa HDPE hoặc lót chì), có đê be chống tràn.\n"
                "3. Thiết bị bảo hộ cá nhân (PPE): Bắt buộc kính bảo hộ chống hóa chất, găng tay butyl/nitrile dày chống axit, tạp dề chịu axit, ủng cao su.\n"
                "4. Biện pháp sơ cứu và xử lý sự cố tràn đổ: Nếu dính vào da: xối nước sạch liên tục ít nhất 15 phút, cởi bỏ quần áo dính axit. Tuyệt đối không đổ nước trực tiếp vào axit đặc. Dùng cát khô hoặc vôi bột (Ca(OH)2), tro kiềm để trung hòa và thấm hút trước khi thu gom."
            ),
            "source": "SDS_Internal_v1",
            "metadata": {"chemical_code": "001", "chemical_name": "Axit Sunfuric H2SO4 98%", "doc_type": "SDS"}
        },
        {
            "doc_id": "SDS-ETHANOL-002",
            "doc_title": "Phiếu an toàn hóa chất Cồn Ethanol 96%",
            "content": (
                "PHIẾU AN TOÀN HÓA CHẤT (SDS/MSDS) - CỒN CÔNG NGHIỆP ETHANOL 96%\n"
                "Mã hóa chất nội bộ: 002. Số CAS: 64-17-5.\n"
                "1. Đặc tính nguy hiểm: Chất lỏng và hơi cực kỳ dễ cháy (Flammable Liquid Cat 2). Hơi tạo hỗn hợp nổ với không khí ở nhiệt độ thường.\n"
                "2. Quy định bảo quản: Lưu kho R01. Giữ khu vực kho luôn thông gió cưỡng bức, nhiệt độ không quá 28°C, hệ thống điện chiếu sáng phòng nổ (Ex-proof). Không để gần nguồn phát tia lửa điện hoặc nhiệt.\n"
                "3. Xử lý sự cố cháy nổ: Dùng bình bọt chữa cháy kháng cồn (AR-AFFF), khí CO2 hoặc bột chữa cháy khô ABC. Không dùng tia nước thẳng vì làm tràn cồn loang rộng."
            ),
            "source": "SDS_Internal_v1",
            "metadata": {"chemical_code": "002", "chemical_name": "Cồn Công Nghiệp Ethanol 96%", "doc_type": "SDS"}
        },
        {
            "doc_id": "SDS-ACETONE-005",
            "doc_title": "Phiếu an toàn hóa chất Dung môi Acetone",
            "content": (
                "PHIẾU AN TOÀN HÓA CHẤT (SDS/MSDS) - DUNG MÔI ACETONE KỸ THUẬT\n"
                "Mã hóa chất nội bộ: 005. Số CAS: 67-64-1.\n"
                "1. Đặc tính: Dung môi hữu cơ bay hơi cực nhanh, dễ bắt cháy, nồng độ TVOC cao trong không khí gây chóng mặt, kích ứng đường hô hấp và niêm mạc mắt.\n"
                "2. Cảnh báo nồng độ môi trường: Ngưỡng TVOC tối đa cho phép trong phòng thí nghiệm/kho là 200 ppb. Nếu nồng độ TVOC vượt 200 ppb, phải kích hoạt hệ thống hút khí khẩn cấp và sơ tán nhân sự."
            ),
            "source": "SDS_Internal_v1",
            "metadata": {"chemical_code": "005", "chemical_name": "Dung môi Acetone kỹ thuật", "doc_type": "SDS"}
        }
    ]

    texts = [d["content"] for d in docs]
    embeddings = embed_documents(texts)

    points = []
    for d, emb in zip(docs, embeddings):
        payload = {
            "doc_id": d["doc_id"],
            "doc_title": d["doc_title"],
            "doc_type": d["metadata"].get("doc_type", "SDS"),
            "source": d["source"],
            "tenant_id": 94,
            "section": "An toàn & Bảo quản",
            "chunk_index": 0,
            "latest": True,
            "chemical_code": d["metadata"]["chemical_code"],
            "chemical_name": d["metadata"]["chemical_name"],
            "text": d["content"],
        }
        pt = ChunkPoint(
            doc_id=d["doc_id"],
            chunk_index=0,
            text=d["content"],
            embedding=emb,
            payload=payload,
            snapshot=0
        )
        points.append(pt)

    n = await store.upsert_chunks(points)
    print(f"Successfully upserted {n} SDS chunks into {store.collection}!")

if __name__ == '__main__':
    asyncio.run(seed_sds())
