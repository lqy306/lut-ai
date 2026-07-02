"""
models.py — Data models for LUT evaluation

All data is represented with plain dataclasses for easy
serialization and interchange.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ColorStats:
    """8 color features extracted from a processed image (纯数学计算)."""
    avg_r: float = 0.0       # RGB平均 (0–255)
    avg_g: float = 0.0
    avg_b: float = 0.0
    avg_h: float = 0.0       # HSV平均 (H:0–360, S/V:0–100)
    avg_s: float = 0.0
    avg_v: float = 0.0
    contrast: float = 0.0    # 亮度标准差
    warm_bias: float = 0.0   # >0暖调, <0冷调

    def serialize(self) -> str:
        """Serialize to short text for AI prompts."""
        return (
            f"RGB avg: {self.avg_r:.1f} {self.avg_g:.1f} {self.avg_b:.1f}\n"
            f"HSV avg: {self.avg_h:.1f} {self.avg_s:.1f} {self.avg_v:.1f}\n"
            f"Contrast: {self.contrast:.2f}\n"
            f"Warm bias: {self.warm_bias:+.2f} ({'warm' if self.warm_bias > 0 else 'cool'})"
        )


@dataclass
class EvalResult:
    """Evaluation result for a single LUT."""
    name: str                          # LUT file name
    rank: int = 0                      # Ranking position
    score: float = 0.0                 # Score (0–100)
    style_tags: list[str] = field(default_factory=list)  # Style tags
    description: str = ""              # One-sentence description
    analysis: str = ""                 # Detailed analysis (AI only)
    stats: Optional[ColorStats] = None # Associated color stats
    eval_source: str = "local"         # "ai" or "local"


@dataclass
class RankingResult:
    """Complete ranking response."""
    rankings: list[EvalResult] = field(default_factory=list)
    best_lut: str = ""
    best_reason: str = ""


@dataclass
class QueryMatch:
    """Query match result for a single LUT."""
    name: str = ""
    match_score: float = 0.0  # 0–100
    reason: str = ""


@dataclass
class AppConfig:
    """Application configuration."""
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o"
    temperature: float = 0.3
    language: str = "en"         # "zh" or "en"
    lut_dirs: list[str] = field(default_factory=list)
    image_path: str = ""
    use_ai: bool = False
    stream: bool = True
    max_luts: int = 0            # 0 = all
    selected_luts: list[str] = field(default_factory=list)  # empty = all
    selected_images: list[str] = field(default_factory=list)  # empty = first found
    compress_pixels: bool = False    # Limit total pixels before processing
    max_pixels: int = 200000         # Target max width × height
    include_original: bool = True    # Include unprocessed reference in results
    query: str = ""              # Query string for matching
    results_file: str = ""       # Saved results file path
    save_results: str = ""       # Save results to JSON file
