import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from services.get_embeddings import get_embedding

def test_embeddings():
    print("Testing RETRIEVAL_QUERY...")
    res_query = get_embedding("test query", task_type="RETRIEVAL_QUERY")
    if res_query and len(res_query) == 768:
        print("RETRIEVAL_QUERY success")
    else:
        print(f"RETRIEVAL_QUERY failed: len={len(res_query) if res_query else 0}")

    print("\nTesting RETRIEVAL_DOCUMENT...")
    res_doc = get_embedding("test document", task_type="RETRIEVAL_DOCUMENT")
    if res_doc and len(res_doc) == 768:
        print("RETRIEVAL_DOCUMENT success")
    else:
        print(f"RETRIEVAL_DOCUMENT failed: len={len(res_doc) if res_doc else 0}")

if __name__ == "__main__":
    test_embeddings()
