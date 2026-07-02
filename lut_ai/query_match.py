"""
query_match.py — LUT query matching

Given a list of EvalResults and a user text query, returns
the top matching LUTs. Uses AI when available, falls back
to simple keyword matching.
"""

from .models import EvalResult


def keyword_match(results: list[EvalResult],
                  query: str,
                  top_n: int = 3) -> list[tuple[EvalResult, float, str]]:
    """Simple keyword-based matching fallback.

    Matches the query against LUT names, tags, and descriptions.
    No AI required.

    Args:
        results: List of evaluation results.
        query: User's search query.
        top_n: Maximum number of results to return.

    Returns:
        Sorted list of (result, match_score, reason) tuples.
    """
    query_lower = query.lower()
    keywords = query_lower.split()

    scored: list[tuple[EvalResult, float, list[str]]] = []

    for r in results:
        score = 0.0
        reasons = []

        name_lower = r.name.lower()
        desc_lower = r.description.lower()
        tags_lower = [t.lower() for t in r.style_tags]
        analysis_lower = r.analysis.lower() if r.analysis else ""

        for kw in keywords:
            # Name match (highest weight)
            if kw in name_lower:
                score += 30.0
                reasons.append(f"name matches '{kw}'")

            # Tag match
            if any(kw in t for t in tags_lower):
                score += 20.0
                reasons.append(f"tag matches '{kw}'")

            # Description match
            if kw in desc_lower:
                score += 10.0
                reasons.append(f"description matches '{kw}'")

            # Analysis match
            if kw in analysis_lower:
                score += 5.0
                reasons.append(f"analysis matches '{kw}'")

            # Score proximity (for numeric queries like ">80", "90")
            if kw.isdigit():
                val = int(kw)
                if abs(r.score - val) < 10:
                    score += (10 - abs(r.score - val))
                    reasons.append(f"score close to {val}")

        if score > 0:
            scored.append((r, score, "; ".join(reasons)))

    scored.sort(key=lambda x: x[1], reverse=True)

    result = []
    for r, s, reason in scored[:top_n]:
        result.append((r, s, reason))

    return result
