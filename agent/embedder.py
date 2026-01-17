from sentence_transformers import SentenceTransformer  # type: ignore
class E5Embedder:
    def __init__(self, model_name: str = "intfloat/multilingual-e5-small", device: str = "cpu"):

        self._model = SentenceTransformer(model_name, device=device)

    def embed_documents(self, documents: list[str], verbose: bool = False) -> list[list[float]]:
        prefixed = [f"passage: {d}" for d in documents]
        embeddings = self._model.encode(
            prefixed,
            show_progress_bar=verbose,
            normalize_embeddings=True,
        )
        return embeddings.tolist()
