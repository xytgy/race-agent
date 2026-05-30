from app.config.settings import settings
from app.service.vector_service import VectorService


def create_vector_store() -> VectorService:
    vector_store = settings.vector_store.lower().strip()
    if vector_store == "faiss":
        return VectorService()
    raise ValueError(f"unsupported_vector_store: {settings.vector_store}")
