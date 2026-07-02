"""
lut_ai — LUT Evaluation & Ranking Tool

A tool for evaluating LUT (Look-Up Table) color grading results,
providing AI-powered ranking, local heuristic scoring, and
query-based LUT matching.

Core components:
  - models:      Data models (ColorStats, EvalResult, etc.)
  - bindings:    ctypes bindings to C core library
  - lut_apply:   LUT loading and tetrahedral interpolation
  - ai_interface: OpenAI-compatible API for AI ranking
  - local_eval:  Pure-formula heuristic evaluation (via C)
  - query_match: LUT matching against text queries
  - cli:         Rich-based CLI interface
"""

__version__ = "1.0.0"
