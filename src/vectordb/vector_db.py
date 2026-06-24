import chromadb
from config import settings
from openai import OpenAI
import tiktoken
from datetime import datetime, timezone
from utils.logger import logger
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
  
client = chromadb.CloudClient(
  api_key= settings.CHROMA_API_KEY,
  tenant= settings.CHROME_TENANT,
  database= settings.CHROMA_DATABASE
)

client_oa = OpenAI(api_key=settings.OPENAI_CHATGPT)
embedding_function = OpenAIEmbeddings(model=settings.EMBEDDING_MODEL, api_key=settings.OPENAI_CHATGPT)
collection = client.get_or_create_collection(name="GroundedIQ")

def _embed_batched(texts: list[str], model: str, batch_size: int = 100) -> list[list[float]]:
  """Embed `texts` in batches (the OpenAI embeddings API accepts a list input and
  returns vectors in order). Replaces the previous one-call-per-chunk loop.

  Records embedding-token usage into llm_call_log via the bound recorder so the
  project COGS total matches the OpenAI usage dashboard (embeddings are a separate
  line item there). No-op when no recorder is bound."""
  from utils.llm_metrics import get_recorder

  embeddings: list[list[float]] = []
  total_tokens = 0
  for start in range(0, len(texts), batch_size):
    batch = texts[start:start + batch_size]
    resp = client_oa.embeddings.create(input=batch, model=model)
    embeddings.extend(item.embedding for item in resp.data)
    try:
      total_tokens += int(getattr(resp, "usage", None).total_tokens or 0)
    except Exception:
      pass

  recorder = get_recorder()
  if recorder is not None and total_tokens:
    recorder.record(
      agent_name="embedding", model=model,
      input_tokens=total_tokens, cached_input_tokens=0, output_tokens=0, latency_ms=0,
    )
  return embeddings


async def create_embeddings(
  texts: list[str],
  model: str,
  chat_history_id: str,
  metadatas: list[dict] | None = None,
  document_id: str | None = None,
) -> str:
  """Embed `texts` and (re)store them under `chat_history_id`.

  `metadatas` (parallel to `texts`) may carry section_id/heading_text/content_type
  from section-aware chunking; they are merged into the base metadata so chat
  retrieval can filter by content_type (e.g. diagrams) or section. Existing
  embeddings for the chat are deleted first so a regeneration fully replaces them.
  """
  if not texts:
    logger.info(f"create_embeddings: no chunks to embed for chat_history_id: {chat_history_id}")
    return "no chunks to embed"

  #Deleting the existing embedding for the chat_hisotry_id if exists
  try:
    existing = collection.get(where={"chat_history_id": chat_history_id})
    if not existing or len(existing) == 0:
      logger.info(f"No existing embeddings found for the chat_hisotry_id: {chat_history_id}")
    else:
      logger.info(f"Existing embedding found for chat_history_id: {chat_history_id}")
      collection.delete(where={"chat_history_id": chat_history_id})
      logger.info(f"Deleting existing embeddings for chat_history_Id: {chat_history_id}")
  except Exception as e:
    logger.error(f"Error checking/deleting existing embedding for chat_history_id: {chat_history_id}, error: {e}")
    raise RuntimeError(f"failed to check/delete exisitng embeddings: {e}")

  #Creating metadata for the vector store. Chroma rejects None values, so only
  # non-empty fields are included.
  ts = datetime.now(timezone.utc).isoformat()
  metadata = []
  for idx in range(len(texts)):
    meta = {
      "chunk_id": f"{chat_history_id}_{idx+1}",
      "chat_history_id": chat_history_id,
      "timestamp": ts,
    }
    if document_id:
      meta["document_id"] = document_id
    if metadatas and idx < len(metadatas) and metadatas[idx]:
      for k, v in metadatas[idx].items():
        if v not in (None, ""):
          meta[k] = v
    metadata.append(meta)

  # Create embeddings via OpenAI client (batched). Ensure a recorder is bound so
  # the embedding cost is captured even when indexing runs outside a pipeline/chat
  # context (which already bind a richer-scoped recorder).
  from contextlib import nullcontext
  from utils.llm_metrics import get_recorder, LLMCallRecorder, use_recorder
  _embed_ctx = nullcontext() if get_recorder() is not None else use_recorder(
    LLMCallRecorder(chat_history_id=chat_history_id)
  )
  try:
    with _embed_ctx:
      resp = _embed_batched(texts, model)
    logger.info(f"created {len(resp)} embeddings for chat_history_id: {chat_history_id}")
  except Exception as e:
     logger.error(f'Error creating embedding for chat_history_id: {chat_history_id}, error: {e}')
     raise RuntimeError(f"Failed to create embeddings: {e}")

  try:
    collection.add(
      ids=[f"{chat_history_id}_{idx+1}" for idx in range(len(texts))],
      embeddings=resp,
      documents=texts,
      metadatas=metadata
    )
    logger.info(f"added Embeddings to collection for chat_histotry_id: {chat_history_id}")
    return f"embeddings created and added to collections successfully"
  except Exception as e:
     logger.error(f"Error adding embeddings to collection for chat_history_id: {chat_history_id}, error: {e}")
     raise RuntimeError(f"failed to add embeddings to collection: {e}")


async def embed_report(markdown: str, model: str, chat_history_id: str, document_id: str | None = None) -> str:
  """Section-aware chunk + embed for a markdown report (the chat retrieval store).

  Single entry point for every report ingest site: produces fence-atomic,
  section-tagged chunks (vectordb.chunking.chunk_report) and stores them with
  content_type/section metadata. Embeddings are now a *fallback* path — the chat
  serves sections/diagrams deterministically from report_content — so this is
  best-effort; callers already treat embedding failure as non-fatal.
  """
  from vectordb.chunking import chunk_report

  chunks = chunk_report(markdown)
  if not chunks:
    logger.info(f"embed_report: no chunks produced for chat_history_id: {chat_history_id}")
    return "no chunks to embed"
  texts = [c["text"] for c in chunks]
  metadatas = [
    {"section_id": c["section_id"], "heading_text": c["heading_text"], "content_type": c["content_type"]}
    for c in chunks
  ]
  return await create_embeddings(
    texts=texts, model=model, chat_history_id=chat_history_id,
    metadatas=metadatas, document_id=document_id,
  )


async def retrieve_similar_embeddings(
  query_text: str,
  chat_history_id: str,
  model: str,
  top_k: int = 5,
  content_type: str | None = None,
) -> list[str]:
  """Semantic search scoped to one chat. `content_type` optionally filters to a
  chunk class (e.g. 'diagram', 'prose', 'table'). Returns the raw Chroma result
  (documents + metadatas + distances)."""
  try:
    query_embedding = client_oa.embeddings.create(input=query_text, model=model).data[0].embedding
    if content_type:
      where = {"$and": [{"chat_history_id": chat_history_id}, {"content_type": content_type}]}
    else:
      where = {"chat_history_id": chat_history_id}
    results = collection.query(
      query_embeddings=[query_embedding],
      n_results=top_k,
      where=where,
    )
    return  results
  except Exception as e:
    logger.error(f"Error retrieving similar embeddings for chat_history_id: {chat_history_id}, error: {e}")
    raise RuntimeError(f"failed to retrieve similar embeddings: {e}")


# if __name__ == "__main__":
   
#   import asyncio
#   text = "third sample text"
#   model = "text-embedding-3-small"
#   chat_history_id = "chat_history_123"
#   chunk_id = "chunk_123"
#   result = asyncio.run(create_embeddings(text, model, chat_history_id, chunk_id))
#   print(result)
  # query_text = "what is the company we are doing this project for?"
  # model = "text-embedding-3-small"
  # # chat_history_id = "a4bf7ade-5588-4746-81e0-890921e9fd96"
  # chat_history_id = "d7fff20d-40c1-4653-8556-dad60830b697"
  # answer = asyncio.run(retrieve_similar_embeddings(query_text=query_text, chat_history_id=chat_history_id, model=model, top_k=5))
  # print(answer)
  

