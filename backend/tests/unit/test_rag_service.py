import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.rag import service
from app.rag.utils import processing


class RAGServiceTests(unittest.TestCase):
    def test_embedder_is_loaded_once(self):
        processing.get_embedder.cache_clear()
        model = Mock()
        with patch.object(processing, "SentenceTransformer", return_value=model) as sentence_transformer:
            first = processing.get_embedder()
            second = processing.get_embedder()

        self.assertIs(first, second)
        sentence_transformer.assert_called_once_with("all-MiniLM-L6-v2")
        processing.get_embedder.cache_clear()

    def test_builds_missing_index_with_project_data_paths(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            data_directory = project_root / "data"
            data_directory.mkdir()
            with (
                patch.object(service, "PROJECT_ROOT", project_root),
                patch.object(service, "load_dotenv") as load_dotenv,
                patch.dict(os.environ, {
                    "OPENCODE_API_URL": "https://example.test/v1/chat/completions",
                    "OPENCODE_API_KEY": "test-key",
                }),
                patch.object(processing, "get_embedder", return_value=Mock(get_sentence_embedding_dimension=Mock(return_value=384))) as get_embedder,
                patch.object(processing, "extract_text_from_pdfs", return_value=["rules"]),
                patch.object(processing, "chunk_text", return_value=["chunk"]),
                patch.object(processing, "create_faiss_index") as create_index,
            ):
                rag = service.RAGService()

            load_dotenv.assert_called_once_with(project_root / ".env")
            create_index.assert_called_once_with(
                ["chunk"],
                index_path=data_directory / "faiss_index.idx",
                chunks_path=data_directory / "text_chunks.npy",
                embedder=rag.embedder,
            )
            get_embedder.assert_called_once_with()

    def test_query_uses_vector_and_keyword_results_and_returns_api_explanation(self):
        rag = service.RAGService.__new__(service.RAGService)
        rag.api_url = "https://example.test/v1/chat/completions"
        rag.api_key = "test-key"
        rag.model = "test-model"
        rag.embedder = object()
        rag.index_path = Path("data/faiss_index.idx")
        rag.chunks_path = Path("data/text_chunks.npy")
        api_response = Mock()
        api_response.json.return_value = {
            "choices": [{"message": {"content": "Applicable spectrum rules."}}]
        }

        with (
            patch.object(service, "retrieve_relevant_chunks", return_value=["rule text"]) as retrieve,
            patch.object(service.np, "load", return_value=[]),
            patch.object(service.requests, "post", return_value=api_response) as post,
        ):
            explanation = rag.query_rules(145.5, "maritime")

        self.assertEqual(explanation, "Applicable spectrum rules.")
        retrieve.assert_called_once_with(
            "Frequency: 145.5 MHz or 0.1455 GHz; service type: maritime",
            rag.embedder,
            k=10,
            index_path=rag.index_path,
            chunks_path=rag.chunks_path,
        )
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertIn("145.5 MHz", post.call_args.kwargs["json"]["messages"][0]["content"])
        api_response.raise_for_status.assert_called_once()

if __name__ == "__main__":
    unittest.main()