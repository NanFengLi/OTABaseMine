import chromadb
from sentence_transformers import SentenceTransformer
from typing import List

embedding_model = SentenceTransformer("shibing624/text2vec-base-chinese")

def embed_chunk(chunk: str) -> List[float]:
    embedding = embedding_model.encode(chunk, normalize_embeddings=True)
    return embedding.tolist()

chromadb_client = chromadb.PersistentClient("./chroma.db")
chromadb_collection = chromadb_client.get_collection(name="default")
chromadb_collection.upsert(
            documents=["this is a test"],
            embeddings=[embed_chunk("this is a test")],
            ids=["test_id"]
        )
results = chromadb_collection.query(
    query_embeddings=[embed_chunk("test")],
    n_results=2,
)

print(results)