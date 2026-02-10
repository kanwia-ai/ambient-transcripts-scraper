# tests/test_embeddings.py
import pytest
np = pytest.importorskip("numpy")
pytest.importorskip("sentence_transformers")
from processing.embeddings import EmbeddingGenerator

def test_embedding_generator_create():
    generator = EmbeddingGenerator(model_name='all-MiniLM-L6-v2')

    text = "This is a test meeting transcript."
    embedding = generator.generate_embedding(text)

    assert isinstance(embedding, np.ndarray)
    assert embedding.shape[0] == 384  # all-MiniLM-L6-v2 dimension