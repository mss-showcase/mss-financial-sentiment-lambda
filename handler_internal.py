import os
import random
from time import time, sleep
import feedparser
import requests
from bs4 import BeautifulSoup
from sentiment import load_lexicons, sentiment_score

IS_LOCAL = os.getenv("IS_LOCAL", "false").lower() == "true"

USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    # Chrome on Android
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
]

def lambda_handler_internal(
    event,
    context,
    check_processed_callback=None,
    persist_callback=None,
    get_last_feed_pubdate_callback=None,
    set_last_feed_pubdate_callback=None
):
    if IS_LOCAL:
        POS, NEG = load_lexicons(path="Loughran-McDonald_MasterDictionary_1993-2024.csv")
    else:
        POS, NEG = load_lexicons(
            s3_bucket="mss-data-bucket",
            s3_key="Loughran-McDonald_MasterDictionary_1993-2024.csv"
        )

    tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']
    feedUrls = ["https://www.cnbc.com/id/15839069/device/rss/rss.html"]
    results = []

    for feedUrl in feedUrls:
        feed = feedparser.parse(feedUrl)
        feed_pubdate = getattr(feed.feed, "published", None) or getattr(feed.feed, "pubDate", None)
        if get_last_feed_pubdate_callback and feed_pubdate:
            last_pubdate = get_last_feed_pubdate_callback(feedUrl)
            if last_pubdate and feed_pubdate <= last_pubdate:
                print(f"Feed {feedUrl} already processed up to {last_pubdate}")
                continue  # Skip this feed

        for entry in feed.entries:
            article_pubdate = getattr(entry, "published", None) or getattr(entry, "pubDate", None)
            url = entry.link
            # Optionally skip by article pubDate
            if check_processed_callback and check_processed_callback(url, article_pubdate):
                continue
            # Check if already processed
            if check_processed_callback and check_processed_callback(url):
                continue
            text = getFeedArticleText(url)
            related_tickers = [ticker for ticker in tickers if ticker.upper() in (entry.title + " " + text).upper()]
            if related_tickers:
                sentiment = sentiment_score(text, POS, NEG)
                record = {
                    "url": url,
                    "title": entry.title,
                    "tickers": related_tickers,
                    "sentiment": sentiment,
                    "feedUrl": feedUrl,
                    "pubdate": article_pubdate if article_pubdate else time()
                }
                results.append(record)
                if persist_callback:
                    persist_callback(record)
                else:
                    print(record)
            sleep(random.uniform(3, 10))  # Random delay between 3 and 10 seconds
        # After processing, update last processed feed pubDate
        if set_last_feed_pubdate_callback and feed_pubdate:
            set_last_feed_pubdate_callback(feedUrl, feed_pubdate)
    return results

def getFeedArticleText(url):
    """
    Downloads the main article text from the given URL.
    Tries to extract the main content using BeautifulSoup.
    Uses a random browser user agent for the request.
    """
    try:
        headers = {
            "User-Agent": random.choice(USER_AGENTS)
        }
        response = requests.get(url, timeout=10, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        # Try to extract main article text from <div class="group"> - in case of CNBC this is where the main content is usually found
        group_div = soup.find("div", class_="group")
        if group_div:
            text = group_div.get_text(separator=" ", strip=True)
            if text.strip():
                return text
        # Try to extract main article text from <article>
        article = soup.find("article")
        if article:
            paragraphs = article.find_all("p")
            text = " ".join(p.get_text() for p in paragraphs)
            if text.strip():
                return text
        # Fallback: get all <p> tags
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text() for p in paragraphs)
        return text.strip()
    except Exception as e:
        print(f"Error fetching article text: {e}")
        return ""

def filterTextByTickers(entry, text, tickers):
    """
    Returns True if any ticker symbol or company name is mentioned in the entry title or text.
    """
    content = (entry.title + " " + text).upper()
    for ticker in tickers:
        if ticker.upper() in content:
            return True
    return False
