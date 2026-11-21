"""Versioned, owner-filtered hybrid retrieval. MySQL is the visibility authority."""

from pathlib import Path
import io
import json
import httpx
from sqlalchemy import select
from .db import Session, Document
from .config import settings
from .models import gateway


def es(method, path, **kwargs):
    with httpx.Client(timeout=60, trust_env=False) as client:
        response = client.request(method, settings.elastic_url + path, **kwargs)
    response.raise_for_status()
    return response.json()


def embedder():
    """Compatibility entry point; loading and caching belong to the model gateway."""
    return gateway.local_model("embedding")


def embed(texts):
    return embedder().encode(texts, normalize_embeddings=True, batch_size=16).tolist()


def parse_file(raw, name):
    ext = Path(name).suffix.lower()
    if ext in {".txt", ".md"}:
        return [("正文", raw.decode("utf-8-sig"))]
    if ext == ".pdf":
        from pypdf import PdfReader

        pages = PdfReader(io.BytesIO(raw)).pages
        if len(pages) > 150:
            raise ValueError("PDF 超过 150 页，请拆分后上传")
        return [(f"第 {i + 1} 页", page.extract_text() or "") for i, page in enumerate(pages)]
    if ext == ".docx":
        from docx import Document as Docx
        import zipfile

        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if sum(x.file_size for x in z.infolist()) > 30 * 1024**2:
                raise ValueError("文档解压后超过限制")
        doc = Docx(io.BytesIO(raw))
        parts = [(f"段落 {i + 1}", p.text) for i, p in enumerate(doc.paragraphs) if p.text.strip()]
        for i, table in enumerate(doc.tables):
            rows = [" | ".join(c.text for c in r.cells) for r in table.rows]
            parts.extend((f"表 {i + 1} 行 {j + 1}", rows[0] + "\n" + row) for j, row in enumerate(rows[1:]))
        return parts
    raise ValueError("支持 TXT、MD、文字 PDF 和 DOCX")


def chunks(parts, size=450, overlap=80):
    result = []
    for anchor, text in parts:
        text = text.strip()
        for start in range(0, len(text), size - overlap):
            fragment = text[start : start + size]
            if fragment.strip():
                result.append({"text": fragment, "anchor": anchor, "offset": start, "chunk": len(result)})
    return result


def index_document(doc_id):
    with Session() as db:
        doc = db.get(Document, doc_id)
        if not doc or doc.status == "deleted":
            return
        owner, name, digest, version = doc.owner, doc.name, doc.digest, doc.version + 1
        info = dict(doc.info)
        doc.status = "indexing"
        db.commit()
    try:
        parts = parse_file((Path(settings.data_dir) / "uploads" / doc_id).read_bytes(), name)
        segments = chunks(parts)
        if not segments:
            raise ValueError("未提取到文字；当前解析器不支持扫描页和嵌入图片 OCR，请补充文字版本")
        if len(segments) > 2000:
            raise ValueError("切分后超过 2000 个片段，请拆分文档")
        vectors = embed([s["text"] for s in segments])
        mapping = {
            "mappings": {
                "properties": {
                    "owner": {"type": "keyword"},
                    "doc_id": {"type": "keyword"},
                    "revision": {"type": "keyword"},
                    "text": {"type": "text", "analyzer": "standard"},
                    "vector": {"type": "dense_vector", "dims": 512, "index": True, "similarity": "cosine"},
                }
            }
        }
        with httpx.Client(timeout=30, trust_env=False) as client:
            check = client.head(settings.elastic_url + "/" + settings.elastic_index)
        if check.status_code == 404:
            es("PUT", "/" + settings.elastic_index, json=mapping)
        bulk = []
        for part, vector in zip(segments, vectors):
            bulk.extend(
                [
                    json.dumps({"index": {"_id": f"{doc_id}:{version}:{part['chunk']}"}}),
                    json.dumps(
                        {
                            **part,
                            "owner": owner,
                            "doc_id": doc_id,
                            "revision": f"{doc_id}:{version}",
                            "name": name,
                            "digest": digest,
                            "vector": vector,
                        },
                        ensure_ascii=False,
                    ),
                ]
            )
        response = es(
            "POST",
            "/" + settings.elastic_index + "/_bulk?refresh=wait_for",
            content="\n".join(bulk) + "\n",
            headers={"Content-Type": "application/x-ndjson"},
        )
        if response.get("errors"):
            raise ValueError("索引写入存在失败片段，旧版本继续可见")
        with Session.begin() as db:
            doc = db.get(Document, doc_id, with_for_update=True)
            if doc.status != "deleted" and doc.digest == digest:
                doc.version, doc.status = version, "ready"
                doc.info = {
                    **info,
                    "chunks": len(segments),
                    "warning": "图片内容未进入索引；来源为用户导入资料",
                }
    except Exception as exc:
        with Session.begin() as db:
            doc = db.get(Document, doc_id, with_for_update=True)
            if doc and doc.status != "deleted":
                doc.status = "failed"
                doc.info = {**doc.info, "error": str(exc)[:400]}


def rrf(lists, k=60):
    scores, objects = {}, {}
    for hits in lists:
        for rank, hit in enumerate(hits, 1):
            key = hit["_id"]
            scores[key] = scores.get(key, 0) + 1 / (k + rank)
            objects[key] = hit
    return [(objects[key], score) for key, score in sorted(scores.items(), key=lambda x: -x[1])]


def search(owner, query, limit=5):
    with Session() as db:
        docs = db.scalars(
            select(Document).where(
                Document.owner == owner, Document.status != "deleted", Document.version > 0
            )
        ).all()
        revisions = [f"{d.id}:{d.version}" for d in docs]
    if not revisions:
        return {"hits": [], "support": "none", "message": "尚无已索引的私人资料"}
    filters = [{"term": {"owner": owner}}, {"terms": {"revision": revisions}}]
    vector = embed([query])[0]
    lexical = es(
        "POST",
        "/" + settings.elastic_index + "/_search",
        json={
            "size": 8,
            "_source": {"excludes": ["vector"]},
            "query": {"bool": {"must": [{"match": {"text": query}}], "filter": filters}},
        },
    )["hits"]["hits"]
    semantic = es(
        "POST",
        "/" + settings.elastic_index + "/_search",
        json={
            "size": 8,
            "_source": {"excludes": ["vector"]},
            "knn": {
                "field": "vector",
                "query_vector": vector,
                "k": 8,
                "num_candidates": 40,
                "filter": {"bool": {"filter": filters}},
            },
        },
    )["hits"]["hits"]
    combined = rrf([lexical, semantic])[:8]
    hits = [{**h["_source"], "id": h["_id"], "rrf_score": score} for h, score in combined]
    if settings.reranker_enabled and hits:
        hits = rerank(query, hits)
    # Recheck visibility after query to prevent delete/version-switch races leaking stale content.
    with Session() as db:
        visible = {
            f"{d.id}:{d.version}"
            for d in db.scalars(
                select(Document).where(
                    Document.owner == owner, Document.status != "deleted", Document.version > 0
                )
            ).all()
        }
    hits = [h for h in hits if h["revision"] in visible][:limit]
    return {
        "hits": hits,
        "support": "candidates" if hits else "none",
        "message": "检索相关性不等于支持答案；请核对来源与适用日期",
    }


def reranker():
    return gateway.local_model("rerank")


def rerank(query, hits):
    scores = reranker().predict([(query, h["text"]) for h in hits])
    return sorted(
        [{**h, "rerank_score": float(s)} for h, s in zip(hits, scores)], key=lambda h: -h["rerank_score"]
    )
