"""Unit tests for the trend scoring logic."""
import pytest
from app.services.trend_scorer import (
    score_google_trend,
    score_reddit_post,
    score_news_article,
    combine_scores,
    SOURCE_WEIGHTS,
)


class TestGoogleTrendScoring:
    def test_max_interest_fresh_returns_source_weight(self):
        score = score_google_trend("AI tools", interest_value=100, age_hours=0)
        assert abs(score - SOURCE_WEIGHTS["google_trends"]) < 0.001

    def test_zero_interest_returns_zero(self):
        score = score_google_trend("nothing", interest_value=0, age_hours=0)
        assert score == 0.0

    def test_older_signal_scores_lower(self):
        fresh = score_google_trend("AI", 80, age_hours=0)
        old = score_google_trend("AI", 80, age_hours=48)
        assert fresh > old

    def test_interest_clamped_above_100(self):
        normal = score_google_trend("AI", 100, age_hours=0)
        clamped = score_google_trend("AI", 999, age_hours=0)
        assert normal == clamped

    def test_score_in_valid_range(self):
        score = score_google_trend("AI", 75, age_hours=12)
        assert 0.0 <= score <= 1.0


class TestRedditScoring:
    def test_high_score_fresh_near_source_weight(self):
        score = score_reddit_post("Top AI video", score=50000, num_comments=0, age_hours=0)
        assert abs(score - SOURCE_WEIGHTS["reddit"]) < 0.001

    def test_score_increases_with_comments(self):
        low = score_reddit_post("Topic", score=1000, num_comments=0, age_hours=0)
        high = score_reddit_post("Topic", score=1000, num_comments=500, age_hours=0)
        assert high > low

    def test_older_post_scores_lower(self):
        fresh = score_reddit_post("Topic", 5000, 200, age_hours=0)
        stale = score_reddit_post("Topic", 5000, 200, age_hours=72)
        assert fresh > stale

    def test_score_in_valid_range(self):
        score = score_reddit_post("Topic", 10000, 300, age_hours=6)
        assert 0.0 <= score <= 1.0


class TestNewsScoring:
    def test_max_relevance_fresh_equals_source_weight(self):
        score = score_news_article("AI breakthrough", relevance=1.0, age_hours=0)
        assert abs(score - SOURCE_WEIGHTS["news"]) < 0.001

    def test_lower_relevance_gives_lower_score(self):
        high = score_news_article("Topic", relevance=1.0, age_hours=0)
        low = score_news_article("Topic", relevance=0.3, age_hours=0)
        assert high > low

    def test_score_in_valid_range(self):
        score = score_news_article("Topic", relevance=0.7, age_hours=5)
        assert 0.0 <= score <= 1.0


class TestCombineScores:
    def test_returns_max(self):
        assert combine_scores([0.1, 0.4, 0.2]) == 0.4

    def test_empty_list_returns_zero(self):
        assert combine_scores([]) == 0.0

    def test_single_value(self):
        assert combine_scores([0.35]) == 0.35


class TestRecencyDecay:
    def test_24h_approximately_half(self):
        """Score at 24h should be ~50% of score at 0h."""
        fresh = score_google_trend("AI", 100, age_hours=0)
        day_old = score_google_trend("AI", 100, age_hours=24)
        ratio = day_old / fresh
        assert 0.45 < ratio < 0.55
