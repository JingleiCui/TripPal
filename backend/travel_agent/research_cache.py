"""基于 ES/BGE 与所有者隔离的语义研究缓存。

这里只缓存 POI 查询结果；不缓存库存、预订状态、酒店价格或私人 RAG 内容。
失败按缓存未命中处理；仅凭相似度不能覆盖硬性查询约束。
"""

import hashlib
import json
import re
from datetime import timedelta
from .observability import logger
from .config import settings
from .db import now
from .knowledge import es, embed
from .providers import amap


def scope_for(owner, city, constraints):
    safe = {k: constraints.get(k) for k in ["indoor_only", "style", "excluded_ids", "needs_accommodation"]}
    return hashlib.sha256(
        json.dumps([owner, city, safe, "amap-v3-poi-v1"], sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def semantic_eligible(query):
    # Negation, IDs, numerical or directional conditions require an exact provider query.
    return not re.search(
        r"\d|不|无|禁止|除外|以外|不要|仅|只|东|西|南|北|附近|公里|\b(?:no|not|without|except|only|near|north|south|east|west)\b",
        query,
        re.I,
    )


def lookup(owner, city, query, constraints):
    if not settings.semantic_cache_enabled or not semantic_eligible(query):
        return None
    vector = embed([query])[0]
    filters = [
        {"term": {"owner": owner}},
        {"term": {"scope": scope_for(owner, city, constraints)}},
        {"range": {"expires": {"gt": now().isoformat()}}},
    ]
    try:
        response = es(
            "POST",
            "/" + settings.semantic_cache_index + "/_search",
            json={
                "size": 1,
                "_source": {"excludes": ["vector"]},
                "knn": {
                    "field": "vector",
                    "query_vector": vector,
                    "k": 1,
                    "num_candidates": 10,
                    "filter": {"bool": {"filter": filters}},
                },
            },
        )
    except Exception:
        return None
    hits = response.get("hits", {}).get("hits", [])
    if not hits:
        return None
    hit = hits[0]
    similarity = 2 * hit["_score"] - 1
    if similarity < settings.semantic_cache_similarity:
        return None
    saved = hit["_source"]
    return {
        "results": saved["results"],
        "original_query": saved["query"],
        "similarity": similarity,
        "stored_at": saved["created"],
    }


def store(owner, city, query, constraints, results):
    if not results or not semantic_eligible(query):
        return
    index = settings.semantic_cache_index
    try:
        es(
            "PUT",
            "/" + index,
            json={
                "mappings": {
                    "properties": {
                        "owner": {"type": "keyword"},
                        "scope": {"type": "keyword"},
                        "expires": {"type": "date"},
                        "created": {"type": "date"},
                        "vector": {
                            "type": "dense_vector",
                            "dims": 512,
                            "index": True,
                            "similarity": "cosine",
                        },
                        "results": {"type": "object", "enabled": False},
                    }
                }
            },
        )
    except Exception:
        logger.warning("semantic_cache_index_failed", exc_info=True)
    scope = scope_for(owner, city, constraints)
    ident = hashlib.sha256((scope + "\0" + query).encode()).hexdigest()
    es(
        "PUT",
        "/" + index + "/_doc/" + ident + "?refresh=wait_for",
        json={
            "owner": owner,
            "scope": scope,
            "query": query,
            "created": now().isoformat(),
            "expires": (now() + timedelta(seconds=settings.semantic_cache_seconds)).isoformat(),
            "vector": embed([query])[0],
            "results": results,
        },
    )


def search(owner, city, query, constraints, on_event=None):
    try:
        cached = lookup(owner, city, query, constraints)
    except Exception:
        cached = None
    if cached:
        if on_event:
            on_event(
                hit=True,
                original_query=cached["original_query"],
                similarity=cached["similarity"],
                stored_at=cached["stored_at"],
            )
        return cached["results"]
    result = amap.search_places(city, query)
    try:
        if settings.semantic_cache_enabled:
            store(owner, city, query, constraints, result)
    except Exception:
        logger.warning("semantic_cache_store_failed", exc_info=True)
    if on_event:
        on_event(hit=False)
    return result
