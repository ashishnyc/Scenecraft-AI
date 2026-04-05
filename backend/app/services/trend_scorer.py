"""Trend scoring: combines recency, engagement, and relevance into a 0-1 score."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

# Source weights (must sum to 1.0)
SOURCE_WEIGHTS = {
    "google_trends": 0.40,
    "reddit": 0.35,
    "news": 0.25,
}

# Engagement normalisation caps (to avoid outlier domination)
_REDDIT_SCORE_CAP = 50_000
_NEWS_RELEVANCE_CAP = 1.0  # already 0-1 from API


def _recency_factor(age_hours: float) -> float:
    """Exponential decay: score = 1 at 0h, ~0.5 at 24h, ~0.25 at 48h."""
    if age_hours <= 0:
        return 1.0
    return math.exp(-0.693 * age_hours / 24)  # half-life = 24 h


def score_google_trend(topic: str, interest_value: int, age_hours: float = 0) -> float:
    """
    interest_value: 0-100 as returned by pytrends.
    Returns a score in [0, 1].
    """
    normalised_interest = max(0, min(interest_value, 100)) / 100
    recency = _recency_factor(age_hours)
    raw = normalised_interest * recency * SOURCE_WEIGHTS["google_trends"]
    return round(raw, 4)


def score_reddit_post(
    title: str,
    score: int,
    num_comments: int,
    age_hours: float = 0,
) -> float:
    """
    score: upvotes.  num_comments: comment count.
    Returns a score in [0, 1].
    """
    engagement = min(score + num_comments * 2, _REDDIT_SCORE_CAP) / _REDDIT_SCORE_CAP
    recency = _recency_factor(age_hours)
    raw = engagement * recency * SOURCE_WEIGHTS["reddit"]
    return round(raw, 4)


def score_news_article(
    headline: str,
    relevance: float = 1.0,
    age_hours: float = 0,
) -> float:
    """
    relevance: 0-1 (1.0 if unknown).
    Returns a score in [0, 1].
    """
    norm_relevance = max(0.0, min(relevance, _NEWS_RELEVANCE_CAP))
    recency = _recency_factor(age_hours)
    raw = norm_relevance * recency * SOURCE_WEIGHTS["news"]
    return round(raw, 4)


def combine_scores(scores: list[float]) -> float:
    """Aggregate multiple signals for the same topic (take max, not sum)."""
    return round(max(scores) if scores else 0.0, 4)
