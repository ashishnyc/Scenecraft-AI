"""Integration tests for trend fetchers with mocked external APIs."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_fetch_google_trends_returns_signals():
    import pandas as pd

    mock_df = pd.DataFrame({"AI tools": [45, 60, 80], "python": [30, 50, 70]})
    mock_pt = MagicMock()
    mock_pt.interest_over_time.return_value = mock_df

    # TrendReq is imported inside the nested function; patch at the source module
    with patch("pytrends.request.TrendReq", return_value=mock_pt):
        # Bypass run_in_executor so tests run synchronously
        import asyncio
        async def fake_executor(executor, fn):
            return fn()

        with patch.object(asyncio.get_event_loop(), "run_in_executor", new=fake_executor):
            from app.services import trend_fetcher
            import importlib
            importlib.reload(trend_fetcher)
            results = await trend_fetcher.fetch_google_trends(["AI tools", "python"])

    assert len(results) == 2
    assert any(r["topic"] == "AI tools" for r in results)


@pytest.mark.asyncio
async def test_fetch_google_trends_empty_dataframe():
    import pandas as pd

    mock_pt = MagicMock()
    mock_pt.interest_over_time.return_value = pd.DataFrame()

    with patch("pytrends.request.TrendReq", return_value=mock_pt):
        import asyncio
        async def fake_executor(executor, fn):
            return fn()

        with patch.object(asyncio.get_event_loop(), "run_in_executor", new=fake_executor):
            from app.services import trend_fetcher
            results = await trend_fetcher.fetch_google_trends(["niche topic"])

    assert results == []


@pytest.mark.asyncio
async def test_fetch_news_skipped_when_no_api_key():
    mock_settings = MagicMock()
    mock_settings.NEWS_API_KEY = ""

    # get_settings is imported inside fetch_news_headlines
    with patch("app.core.config.get_settings", return_value=mock_settings):
        from app.services import trend_fetcher
        results = await trend_fetcher.fetch_news_headlines("AI")

    assert results == []


@pytest.mark.asyncio
async def test_fetch_reddit_skipped_when_no_credentials():
    mock_settings = MagicMock()
    mock_settings.REDDIT_CLIENT_ID = ""

    with patch("app.core.config.get_settings", return_value=mock_settings):
        from app.services import trend_fetcher
        results = await trend_fetcher.fetch_reddit_posts(["technology"])

    assert results == []
