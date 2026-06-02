"""Lightweight, dependency-free search over the parts catalog.

This is intentionally a thin, swappable layer. It implements a hybrid of
field-weighted keyword matching + token overlap so the demo works offline with
zero external services. The `SearchIndex` interface is the seam where a real
vector store (Chroma, pgvector, Pinecone) and embedding model would drop in for
a production-scale catalog -- the rest of the app only depends on `.search()`.
"""
import re
from collections import Counter
from typing import List

STOPWORDS = {
    "a", "an", "the", "is", "are", "for", "to", "of", "my", "i", "do", "how",
    "with", "and", "on", "in", "it", "this", "that", "can", "you", "me", "need",
    "part", "parts", "number", "fix", "fixing", "replace", "replacement",
}


def tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


class SearchIndex:
    """In-memory hybrid index. Swap this class for a vector-backed implementation
    without touching the catalog or agent layers."""

    # Field weights: a hit in the part name matters more than one in the body.
    FIELD_WEIGHTS = {
        "name": 5.0,
        "category": 3.0,
        "symptoms_fixed": 3.0,
        "brand": 2.0,
        "appliance_type": 2.0,
        "description": 1.0,
    }

    def __init__(self, parts: List[dict]):
        self.parts = parts
        self._docs = {p["ps_number"]: self._build_doc(p) for p in parts}

    def _build_doc(self, part: dict) -> dict:
        """Pre-tokenize each weighted field once at startup."""
        field_tokens = {}
        for field_name in self.FIELD_WEIGHTS:
            value = part.get(field_name, "")
            if isinstance(value, list):
                value = " ".join(value)
            field_tokens[field_name] = Counter(tokenize(value))
        return field_tokens

    def search(
        self,
        query: str,
        appliance_type: str = None,
        brand: str = None,
        limit: int = 5,
    ) -> List[dict]:
        query_tokens = tokenize(query)
        scored = []
        for part in self.parts:
            if appliance_type and part["appliance_type"].lower() != appliance_type.lower():
                continue
            if brand and brand.lower() not in [b.lower() for b in part.get("compatible_products", [])] \
                    and part["brand"].lower() != brand.lower():
                continue
            score = self._score(part["ps_number"], query_tokens)
            # Small bonus for in-stock so recommendations are actionable.
            if part.get("in_stock"):
                score += 0.25
            if score > 0:
                scored.append((score, part))

        # If the query was effectively empty (e.g. only stopwords), fall back to
        # a category/appliance browse rather than returning nothing.
        if not scored and (appliance_type or brand):
            scored = [(0.0, p) for p in self.parts
                      if (not appliance_type or p["appliance_type"].lower() == appliance_type.lower())]

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:limit]]

    def _score(self, ps_number: str, query_tokens: List[str]) -> float:
        if not query_tokens:
            return 0.0
        doc = self._docs[ps_number]
        score = 0.0
        for field_name, weight in self.FIELD_WEIGHTS.items():
            counts = doc[field_name]
            for token in query_tokens:
                if token in counts:
                    score += weight * counts[token]
        return score
