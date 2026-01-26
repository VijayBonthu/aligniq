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
collection = client.get_or_create_collection(name="AlignIQ")

async def create_embeddings(texts:list[str], model:str, chat_history_id:str) -> list[float]:

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
  
  #Creating metadata for the vector store
  ts = datetime.now(timezone.utc).isoformat()
  metadata = [{
    "chunk_id": f"{chat_history_id}_{idx+1}",
    "chat_history_id": chat_history_id,
    "timestamp": ts
  }
  for idx in range(len(texts))
  ]

  # Create embeddings via OpenAI client. The client may return either a mapping (dict)
  # or a response object. Handle both safely.
  try:
    resp = [
      client_oa.embeddings.create(input=text,model=model).data[0].embedding for text in texts 
    ]
    # resp = client_oa.embeddings.create(input=text, model=model)
    logger.info(f"created embedding for chat_history_id: {chat_history_id}")
  except Exception as e:
     logger.error(f'Error creating embedding for chat_history_id: {chat_history_id}, error: {e}')
     raise RuntimeError(f"Failed to create embeddings: {e}")
     

  # support both dict-like and object-like responses
  # try:
  #   embedding = resp.data[0].embedding
  # except Exception as e:
  #   # raise a clearer error so caller can debug
  #   raise RuntimeError(f"Failed to extract embedding from response: {e}")
  
  # Chroma expects sequences for these fields. Wrap single items in lists.
  try:
    # collection.add(
    #     embeddings=[embedding],
    #     documents=[text],
    #     ids=[f"{chat_history_id}_{chunk_id}"],
    #     metadatas=[metadata]
    # )
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

  # Return the embedding vector so callers can inspect it if needed.
  # logger.info(f"added Embeddings to collection for chat_histotry_id: {chat_history_id}")
  # return f"embeddings created and added to collections successfully"


async def retrieve_similar_embeddings(query_text:str,chat_history_id:str, model:str, top_k:int=5) -> list[str]:

  try:
    query_embedding = client_oa.embeddings.create(input=query_text, model=model).data[0].embedding
    results = collection.query(
      query_embeddings=[query_embedding],
      n_results=top_k,
      where={"chat_history_id": chat_history_id}
    )
    return  results
  except Exception as e:
    logger.error(f"Error retrieving similar embeddings for chat_history_id: {chat_history_id}, error: {e}")
    raise RuntimeError(f"failed to retrieve similar embeddings: {e}")


if __name__ == "__main__":
   
  import asyncio
#   text = "third sample text"
#   model = "text-embedding-3-small"
#   chat_history_id = "chat_history_123"
#   chunk_id = "chunk_123"
#   result = asyncio.run(create_embeddings(text, model, chat_history_id, chunk_id))
#   print(result)
  query_text = "what is the company we are doing this project for?"
  model = "text-embedding-3-small"
  # chat_history_id = "a4bf7ade-5588-4746-81e0-890921e9fd96"
  chat_history_id = "d7fff20d-40c1-4653-8556-dad60830b697"
  answer = asyncio.run(retrieve_similar_embeddings(query_text=query_text, chat_history_id=chat_history_id, model=model, top_k=5))
  print(answer)
  

