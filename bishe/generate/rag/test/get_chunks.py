from typing import List
def split_into_chunks(doc_file:str) -> List[str]:
    with open(doc_file, 'r', encoding='utf-8') as f:
        content = f.read()
    return [chunk for chunk in content.split("\n\n")]

chunks = split_into_chunks('doc.md')
for i,chunk in enumerate(chunks):
    print(f"[{i}] {chunk}\n")

from sentence_transformers import SentenceTransformer

embedding_model = SentenceTransformer("shibing624/text2vec-base-chinese")

def embed_chunk(chunk: str) -> List[float]:
    embedding = embedding_model.encode(chunk, normalize_embeddings=True)
    return embedding.tolist()


# embedding = embed_chunk("测试内容")
# print(len(embedding))
# print(embedding)

embeddings = [embed_chunk(chunk) for chunk in chunks]

print(len(embeddings))
print(embeddings[0])

import chromadb

chromadb_client = chromadb.PersistentClient("./chroma.db")
chromadb_collection = chromadb_client.get_or_create_collection(name="default")

def save_embeddings(chunks: List[str], embeddings: List[List[float]]) -> None:
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        chromadb_collection.add(
            documents=[chunk],
            embeddings=[embedding],
            ids=[str(i)]
        )

save_embeddings(chunks, embeddings)

def retrieve(query: str, top_k: int) -> List[str]:
    query_embedding = embed_chunk(query)
    results = chromadb_collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k
    )
    return results['documents'][0]

query = "哆啦A梦使用的3个秘密道具分别是什么？"
retrieved_chunks = retrieve(query, 5)

for i, chunk in enumerate(retrieved_chunks):
    print(f"[{i}] {chunk}\n")