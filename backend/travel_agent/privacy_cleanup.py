"""Durable cleanup after SQL account removal, safe to replay after ES outages."""

from pathlib import Path
import shutil
import re
from sqlalchemy import select
from .db import Session, PrivacyCleanup
from .config import settings
from .knowledge import es


def process_pending(limit=10):
    with Session() as db:
        ids = db.scalars(
            select(PrivacyCleanup.id).where(PrivacyCleanup.status == "pending").limit(limit)
        ).all()
    for ident in ids:
        with Session.begin() as db:
            item = db.get(PrivacyCleanup, ident, with_for_update=True)
            if not item or item.status != "pending":
                continue
            try:
                if not re.fullmatch(r"[A-Za-z0-9_-]+", item.owner):
                    raise ValueError("invalid owner ID")
                shutil.rmtree(Path(settings.data_dir) / "note-imports" / item.owner, ignore_errors=False) if (
                    Path(settings.data_dir) / "note-imports" / item.owner).exists() else None
                for index in [settings.elastic_index, settings.semantic_cache_index]:
                    es(
                        "POST",
                        "/" + index + "/_delete_by_query?refresh=true&ignore_unavailable=true",
                        json={"query": {"term": {"owner": item.owner}}},
                    )
                for document_id in item.document_ids:
                    # IDs come from server-generated document rows, never user file paths.
                    if not document_id.isalnum():
                        raise ValueError("invalid document ID")
                    (Path(settings.data_dir) / "uploads" / document_id).unlink(missing_ok=True)
            except Exception as exc:
                # Store only the error class, never upstream URLs/credentials or document text.
                item.last_error = type(exc).__name__
                item.attempts += 1
            else:
                item.status, item.last_error, item.document_ids = "done", "", []
                # No personal identifier needs to remain after cleanup.
                item.owner = ""
