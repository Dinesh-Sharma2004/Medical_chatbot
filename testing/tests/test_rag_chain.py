import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from backend import rag_chain as rc


class RagChainRetrievalTests(unittest.TestCase):
    def test_prompt_optimizer_adds_expected_terms_from_cross_entropy_cases(self):
        with patch.object(rc, "PROMPT_OPTIMIZATION_ENABLED", True):
            rc._load_prompt_optimization_cases.cache_clear()

            result = rc.optimize_prompt_embeddings("Explain anatomy pathology")

        self.assertIn("structure", result["added_terms"])
        self.assertIn("function", result["added_terms"])
        self.assertGreater(result["loss"], 0)
        self.assertIn("structure", result["query"])

    def test_optimized_query_is_used_before_hybrid_reranking(self):
        weak_dense = Document(
            page_content="Brief unrelated note.",
            metadata={"filename": "a.pdf", "page": 0, "doc_id": "a"},
        )
        strong_text = Document(
            page_content=(
                "Cardiomyopathy diagnosis treatment symptom cause clinical mechanism "
                "contraindication classification definition."
            ),
            metadata={"filename": "b.pdf", "page": 1, "doc_id": "b"},
        )
        seen_queries = []
        seen_vectors = []

        def fake_candidates(query, fetch_k, query_vec=None):
            seen_queries.append(query)
            seen_vectors.append(query_vec)
            return [(weak_dense, 0.10), (strong_text, 0.20)]

        with (
            patch.object(rc, "retrieve_candidates", side_effect=fake_candidates),
            patch.object(rc, "optimize_prompt_embedding_vector", return_value=[0.1, 0.2, 0.3]),
            patch.object(rc, "HYBRID_SEARCH_ENABLED", True),
            patch.object(rc, "HYBRID_DENSE_WEIGHT", 0.2),
            patch.object(rc, "HYBRID_TEXT_WEIGHT", 0.7),
            patch.object(rc, "HYBRID_OVERLAP_WEIGHT", 0.1),
            patch.object(rc, "PROMPT_OPTIMIZATION_ENABLED", True),
        ):
            rc._load_prompt_optimization_cases.cache_clear()
            records = rc.retrieve_evidence_records(
                "Explain cardiomyopathy treatment",
                k=2,
                fetch_k=2,
                mode="basic",
            )

        self.assertEqual(records[0]["doc_id"], "b")
        self.assertIn("structure", seen_queries[0])
        self.assertEqual(seen_vectors[0], [0.1, 0.2, 0.3])
        self.assertIn("hybrid_score", records[0])
        self.assertGreater(records[0]["hybrid_score"], records[1]["hybrid_score"])


if __name__ == "__main__":
    unittest.main()
