import pytest
import handler_internal

class DummyEntry:
    def __init__(self, title, link):
        self.title = title
        self.link = link

def mock_feedparser_parse(url):
    # Simulate a feed with two entries
    class Feed:
        entries = [
            DummyEntry("Apple reports record profits", "http://example.com/apple"),
            DummyEntry("Microsoft launches new product", "http://example.com/msft"),
        ]
    return Feed()

def mock_getFeedArticleText(url):
    # Return dummy article text based on URL
    if "apple" in url:
        return "AAPL had a great quarter."
    if "msft" in url:
        return "MSFT is innovating again."
    return ""

def mock_load_lexicons(path=None, s3_bucket=None, s3_key=None):
    # Return dummy positive/negative word sets
    return ({"great", "innovating"}, {"bad", "loss"})

def test_lambda_handler_internal(monkeypatch):
    # Patch dependencies
    monkeypatch.setattr(handler_internal, "feedparser", type("feedparser", (), {"parse": mock_feedparser_parse}))
    monkeypatch.setattr(handler_internal, "getFeedArticleText", mock_getFeedArticleText)
    monkeypatch.setattr(handler_internal, "load_lexicons", mock_load_lexicons)

    processed_urls = set()
    def check_processed_callback(url):
        return url in processed_urls

    persisted = []
    def persist_callback(record):
        persisted.append(record)
        processed_urls.add(record["url"])

    # Run the handler
    results = handler_internal.lambda_handler_internal(
        event={},
        context=None,
        check_processed_callback=check_processed_callback,
        persist_callback=persist_callback,
        get_last_feed_pubdate_callback=None,
        set_last_feed_pubdate_callback=None
    )

    assert len(results) == 2, "Expected 2 processed articles"
    assert any("AAPL" in rec["tickers"] for rec in results), "Expected AAPL in results"
    assert any("MSFT" in rec["tickers"] for rec in results),  "Expected MSFT in results"
    assert all("sentiment" in rec for rec in results), "Expected sentiment in all results"
    assert persisted == results, "Expected persisted records to match results"