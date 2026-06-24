"""
Per-firm Chroma collection for past-project RAG (Bet 3).

One collection per firm: `firm_projects_{firm_id}`. Tenant isolation is enforced
by the collection scope — queries only ever hit the calling firm's collection,
and the `firm_id` is read from the request's JWT (never from the LLM tool
arguments) before the search runs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import chromadb

from config import settings
from openai import OpenAI
from utils.logger import logger
from vectordb.chunking import chunk_text


_client = chromadb.CloudClient(
    api_key=settings.CHROMA_API_KEY,
    tenant=settings.CHROME_TENANT,
    database=settings.CHROMA_DATABASE,
)
_oa = OpenAI(api_key=settings.OPENAI_CHATGPT)


def _collection_name(firm_id: str) -> str:
    # Chroma collection names must match `[a-zA-Z0-9._-]`; firm_id values do.
    return f"firm_projects_{firm_id}"


def _get_collection(firm_id: str):
    return _client.get_or_create_collection(name=_collection_name(firm_id))


def _build_searchable_text(project: dict) -> str:
    """Assemble the corpus we embed: brief + retrospective + final report. We
    chunk this and store with metadata so a single project can match on any
    section."""
    parts = [
        f"# {project.get('project_name', '')}",
        f"Engagement: {project.get('engagement_type') or 'unknown'}",
    ]
    if project.get("summary"):
        parts.append(f"## Summary\n{project['summary']}")
    if project.get("original_brief_md"):
        parts.append(f"## Original brief\n{project['original_brief_md']}")
    if project.get("final_report_md"):
        parts.append(f"## Final report\n{project['final_report_md']}")
    if project.get("retrospective_md"):
        parts.append(f"## Retrospective\n{project['retrospective_md']}")
    if project.get("effort_estimated_weeks") is not None and project.get("effort_actual_weeks") is not None:
        parts.append(
            f"## Effort variance\nEstimated: {project['effort_estimated_weeks']} weeks. "
            f"Actual: {project['effort_actual_weeks']} weeks."
        )
    return "\n\n".join(parts).strip()


async def embed_past_project(firm_id: str, project: dict) -> int:
    """
    Embed (or re-embed) a past project into the firm's collection. Returns the
    number of chunks indexed. Existing chunks for the project_id are deleted
    first so edits don't pile up duplicates.
    """
    project_id = project.get("project_id")
    if not firm_id or not project_id:
        raise ValueError("firm_id and project_id required to embed past project")

    text = _build_searchable_text(project)
    if not text:
        logger.info(f"firm_projects: skipping {project_id} (empty content)")
        return 0

    collection = _get_collection(firm_id)

    # Wipe any prior version of this project from the collection.
    try:
        collection.delete(where={"project_id": project_id})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"firm_projects delete-existing failed for {project_id}: {e}")

    chunks = await chunk_text(text)
    if not chunks:
        return 0

    ts = datetime.now(timezone.utc).isoformat()
    metadatas = [
        {
            "project_id": project_id,
            "project_name": project.get("project_name") or "",
            "engagement_type": project.get("engagement_type") or "",
            "chunk_index": idx,
            "indexed_at": ts,
        }
        for idx in range(len(chunks))
    ]
    ids = [f"{project_id}_{idx+1}" for idx in range(len(chunks))]

    try:
        embeddings = [
            _oa.embeddings.create(input=chunk, model=settings.EMBEDDING_MODEL).data[0].embedding
            for chunk in chunks
        ]
    except Exception as e:
        logger.error(f"firm_projects embeddings failed for {project_id}: {e}")
        raise

    collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)
    logger.info(f"firm_projects: indexed {len(chunks)} chunks for project {project_id}")
    return len(chunks)


async def delete_past_project_embeddings(firm_id: str, project_id: str) -> None:
    """Remove a project's chunks. Safe if nothing exists."""
    try:
        collection = _get_collection(firm_id)
        collection.delete(where={"project_id": project_id})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"firm_projects delete failed for {project_id}: {e}")


async def search_firm_projects(firm_id: str, query: str, k: int = 3) -> list[dict]:
    """
    Semantic search over the firm's past projects. Returns a list of
    {project_id, project_name, engagement_type, snippet, score} dicts.
    Empty list on no firm / empty query / no collection / any error — callers
    treat this as a soft signal.
    """
    if not firm_id or not query:
        return []
    try:
        collection = _get_collection(firm_id)
        embedding = _oa.embeddings.create(input=query, model=settings.EMBEDDING_MODEL).data[0].embedding
        result = collection.query(query_embeddings=[embedding], n_results=k)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"firm_projects search failed for firm {firm_id}: {e}")
        return []

    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]

    hits: list[dict] = []
    for doc, meta, dist in zip(docs, metas, dists):
        hits.append({
            "project_id": meta.get("project_id"),
            "project_name": meta.get("project_name"),
            "engagement_type": meta.get("engagement_type"),
            "snippet": (doc or "")[:600],
            "score": float(dist) if dist is not None else None,
        })
    return hits
