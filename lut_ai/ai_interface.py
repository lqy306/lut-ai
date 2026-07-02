"""
ai_interface.py — OpenAI-compatible Chat API for LUT ranking

Compatible with any OpenAI-format API (change base_url to
switch providers). Supports streaming responses.
"""

import json
import os
from typing import Optional

import requests

from .models import EvalResult, RankingResult
from . import log


def _resolve_api_key(api_key: str) -> str:
    """Resolve API key from argument or environment variables.

    Checks in order: argument, LUTAI_API_KEY, OPENAI_API_KEY.
    """
    if api_key:
        return api_key
    for var in ("LUTAI_API_KEY", "OPENAI_API_KEY"):
        val = os.environ.get(var, "")
        if val:
            return val
    return ""


# ── System prompt ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a professional colorist and film stylist. \
You analyze LUT (Look-Up Table) color grading results with expert precision.

You will receive color statistics for multiple LUTs applied to the same \
source image. From these statistics, infer what the processed image LOOKS like \
in terms of mood, temperature, contrast, saturation, and overall visual style.

For each LUT, describe the actual visual impression a viewer would see:
- Is it warm and golden, or cool and sterile?
- Does it pop with contrast or feel soft and dreamy?
- What cinematic or photographic style does it evoke?

Then rank them from best to worst for general creative use.

Respond ONLY with valid JSON, no markdown, no explanation outside the JSON."""


def _build_user_prompt(stats_texts: list[tuple[str, str]],
                       language: str = "zh") -> str:
    """Build the user message for the AI.

    Args:
        stats_texts: List of (lut_name, stats_serialized_text) pairs.
        language: "zh" for Chinese, "en" for English.

    Returns:
        Formatted prompt string.
    """
    lines = ["Color statistics below are extracted from the SAME reference image "
             "processed through different LUTs. From these numbers, infer ",
             "what the actual visual result looks like to the eye."]
    lines.append("")

    for name, text in stats_texts:
        note = " (unprocessed original)" if name.endswith("(original)") else ""
        lines.append(f"--- {name}{note} ---")
        lines.append(text)
        lines.append("")

    lines.append("")
    lines.append(
        'Please output a JSON object with this exact structure:\n'
        '{\n'
        '  "rankings": [\n'
        '    {\n'
        '      "name": "LUT name",\n'
        '      "rank": 1,\n'
        '      "score": 92,\n'
        '      "style_tags": ["warm", "vintage", "cinematic"],\n'
        '      "description": "What the image actually looks like — e.g. '
        '\'Warm golden tones, boosted contrast, reminds of classic film.\'"\n'
        '      "analysis": "Detailed visual breakdown (100-200 words)"\n'
        '    }\n'
        '  ],\n'
        '  "best_lut": "Best LUT name",\n'
        '  "best_reason": "Why this LUT produces the best visual result"\n'
        '}'
    )

    lines.append(
        f"\nReply in this language: {language}.\n"
        "If you don't understand what language this is, reply in English."
    )

    return "\n".join(lines)


def _build_query_prompt(
    results: list[EvalResult],
    query: str,
    language: str = "zh"
) -> str:
    """Build prompt for query matching.

    Args:
        results: Existing evaluation results.
        query: User's search query string.
        language: Response language.

    Returns:
        Formatted prompt string.
    """
    lines = [
        "I have the following LUT evaluation results:",
        ""
    ]

    for r in results:
        tags_str = ", ".join(r.style_tags)
        lines.append(
            f"- {r.name}: score={r.score:.0f}, "
            f"tags=[{tags_str}], desc={r.description}"
        )
        if r.analysis:
            lines.append(f"  analysis: {r.analysis[:200]}")
        lines.append("")

    lines.append(f"User query: {query}")
    lines.append("")
    lines.append(
        'Please return the top 3 matching LUTs in JSON:\n'
        '{\n'
        '  "matches": [\n'
        '    {\n'
        '      "name": "LUT name",\n'
        '      "match_score": 85,\n'
        '      "reason": "Why it matches"\n'
        '    }\n'
        '  ]\n'
        '}'
    )

    lines.append(
        f"\nReply in this language: {language}.\n"
        "If you don't understand what language this is, reply in English."
    )

    return "\n".join(lines)


# ── AI API call ──────────────────────────────────────────────────────────

def _parse_ranking_response(text: str) -> RankingResult:
    """Parse JSON from AI response into RankingResult.

    Handles JSON code blocks and loose formatting.
    """
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        # Remove ```json and ``` markers
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    data = json.loads(text.strip())

    rankings = []
    for item in data.get("rankings", []):
        rankings.append(EvalResult(
            name=item.get("name", ""),
            rank=item.get("rank", 0),
            score=float(item.get("score", 50)),
            style_tags=item.get("style_tags", []),
            description=item.get("description", ""),
            analysis=item.get("analysis", ""),
            eval_source="ai",
        ))

    return RankingResult(
        rankings=rankings,
        best_lut=data.get("best_lut", ""),
        best_reason=data.get("best_reason", ""),
    )


def _parse_query_response(text: str, results: list[EvalResult]
                          ) -> list[tuple[EvalResult, float, str]]:
    """Parse query match JSON from AI response.

    Returns:
        List of (result, match_score, reason) tuples sorted by score.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    data = json.loads(text.strip())

    # Build name -> result lookup
    lookup = {r.name: r for r in results}

    matches = []
    for item in data.get("matches", []):
        name = item.get("name", "")
        score = float(item.get("match_score", 0))
        reason = item.get("reason", "")
        if name in lookup:
            matches.append((lookup[name], score, reason))

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches


def call_ai_ranking(
    stats_texts: list[tuple[str, str]],
    base_url: str = "https://api.openai.com/v1",
    api_key: str = "",
    model: str = "gpt-4o",
    temperature: float = 0.3,
    language: str = "zh",
    stream: bool = True,
    max_items: int = 50,
) -> RankingResult:
    """Call AI API for LUT ranking.

    Args:
        stats_texts: List of (lut_name, stats_serialized) pairs.
        base_url: OpenAI-compatible API base URL.
        api_key: API key.
        model: Model name.
        temperature: Sampling temperature.
        language: Response language ("zh" or "en").
        stream: Whether to use streaming.
        max_items: Max LUTs to send to AI (0 = unlimited).

    Returns:
        Parsed RankingResult.
    """
    api_key = _resolve_api_key(api_key)

    if not api_key:
        raise ValueError(
            "API key required. Set OPENAI_API_KEY env var or pass api_key.")

    # Truncate to avoid context window exceeded
    n_total = len(stats_texts)
    if max_items > 0 and n_total > max_items:
        stats_texts = stats_texts[:max_items]
        log.info(f"Truncated AI input: {n_total} → {max_items} LUTs")

    user_prompt = _build_user_prompt(stats_texts, language)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "stream": stream,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    url = base_url.rstrip("/") + "/chat/completions"
    response = requests.post(url, headers=headers, json=payload,
                             stream=stream, timeout=120)

    if response.status_code != 200:
        raise RuntimeError(
            f"API error {response.status_code}: {response.text[:500]}")

    if stream:
        # Accumulate streaming response
        collected = []
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        collected.append(content)
                except json.JSONDecodeError:
                    continue
        full_text = "".join(collected)
    else:
        data = response.json()
        full_text = (data.get("choices", [{}])[0]
                     .get("message", {})
                     .get("content", ""))

    if not full_text:
        raise RuntimeError("Empty response from AI API")

    return _parse_ranking_response(full_text)


def call_ai_query_match(
    results: list[EvalResult],
    query: str,
    base_url: str = "https://api.openai.com/v1",
    api_key: str = "",
    model: str = "gpt-4o",
    temperature: float = 0.3,
    language: str = "zh",
    stream: bool = True,
) -> list[tuple[EvalResult, float, str]]:
    """Match LUTs to a user query via AI.

    Args:
        results: Existing evaluation results.
        query: User query string.
        (other params same as call_ai_ranking)

    Returns:
        Sorted list of (result, match_score, reason) tuples.
    """
    api_key = _resolve_api_key(api_key)

    if not api_key:
        raise ValueError(
            "API key required. Set OPENAI_API_KEY env var or pass api_key.")

    user_prompt = _build_query_prompt(results, query, language)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "stream": stream,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    url = base_url.rstrip("/") + "/chat/completions"
    response = requests.post(url, headers=headers, json=payload,
                             stream=stream, timeout=120)

    if response.status_code != 200:
        raise RuntimeError(
            f"API error {response.status_code}: {response.text[:500]}")

    if stream:
        collected = []
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        collected.append(content)
                except json.JSONDecodeError:
                    continue
        full_text = "".join(collected)
    else:
        data = response.json()
        full_text = (data.get("choices", [{}])[0]
                     .get("message", {})
                     .get("content", ""))

    if not full_text:
        raise RuntimeError("Empty response from AI API")

    return _parse_query_response(full_text, results)


def call_ai_question(
    rankings: list[EvalResult],
    question: str,
    base_url: str = "https://api.openai.com/v1",
    api_key: str = "",
    model: str = "gpt-4o",
    language: str = "English",
) -> str:
    """Ask a free-form question about evaluated LUTs.

    Args:
        rankings: List of evaluated LUT results.
        question: User's question (e.g. "which one is most cinematic?").
        (other params same as call_ai_ranking)

    Returns:
        AI's answer as a string.
    """
    api_key = _resolve_api_key(api_key)
    if not api_key:
        return "AI not configured. Set LUTAI_API_KEY or OPENAI_API_KEY."

    lines = [
        "I have evaluated several LUTs on a reference image. Here are the results:",
        "",
    ]
    for r in rankings[:20]:  # limit context
        tags = ", ".join(r.style_tags)
        lines.append(f"- {r.name}: score={r.score:.0f}, tags=[{tags}]")
        lines.append(f"  description: {r.description}")
        if r.analysis:
            lines.append(f"  analysis: {r.analysis[:200]}")
        lines.append("")

    lines.append(f"User question: {question}")
    lines.append("")
    lines.append(
        f"Reply in this language: {language}.\n"
        "If you don't understand what language this is, reply in English.\n"
        "Give a concise, insightful answer as a professional colorist."
    )

    user_prompt = "\n".join(lines)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a professional colorist. "
             "Answer questions about LUT color grading concisely and insightfully."},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "stream": False,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    url = base_url.rstrip("/") + "/chat/completions"
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code != 200:
            return f"API error: {response.status_code}"
        data = response.json()
        text = (data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", ""))
        return text.strip()
    except Exception as e:
        return f"Error: {e}"
