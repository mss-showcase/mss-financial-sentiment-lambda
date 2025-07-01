import os
import boto3
import ast
import random
from time import time, sleep
import feedparser
import requests
from bs4 import BeautifulSoup
from sentiment import load_lexicons, sentiment_score
from dynamodb_callbacks import persist_callback
from decimal import Decimal

# SQS setup
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL")
sqs = boto3.client("sqs")

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

IS_LOCAL = os.getenv("IS_LOCAL", "false").lower() == "true"

if IS_LOCAL:
    POS, NEG = load_lexicons(path="Loughran-McDonald_MasterDictionary_1993-2024.csv")
else:
    POS, NEG = load_lexicons(
        s3_bucket="mss-data-bucket",
        s3_key="Loughran-McDonald_MasterDictionary_1993-2024.csv"
    )

# Ticker to company name/aliases mapping for fulltext detection
TICKER_ALIASES = {
    "AAPL": ["AAPL", "Apple", "Apple Inc."],
    "MSFT": ["MSFT", "Microsoft", "Microsoft Corp", "Microsoft Corporation"],
    "GOOGL": ["GOOGL", "Google", "Alphabet", "Alphabet Inc."],
    "AMZN": ["AMZN", "Amazon", "Amazon.com", "Amazon.com Inc."],
    "NVDA": ["NVDA", "Nvidia", "Nvidia Corporation"],
    "META": ["META", "Meta", "Facebook", "Meta Platforms", "Meta Platforms Inc."],
    "TSLA": ["TSLA", "Tesla", "Tesla Inc."]
}

def detect_related_tickers(text, ticker_aliases=TICKER_ALIASES):
    """
    Returns a list of tickers whose aliases are found in the text (case-insensitive).
    """
    found = []
    text_upper = text.upper()
    for ticker, aliases in ticker_aliases.items():
        for alias in aliases:
            if alias.upper() in text_upper:
                found.append(ticker)
                break
    return found

def getFeedArticleText(url):
    """
    Downloads the main article text from the given URL.
    Tries to extract the main content using BeautifulSoup.
    Uses a random browser user agent for the request.
    Introduces a random delay to avoid throttling.
    Returns None for 404, 400, 401, 403. Raises for 5xx and timeouts.
    """
    sleep(random.uniform(1, 5))
    try:
        headers = {
            "User-Agent": random.choice(USER_AGENTS)
        }
        response = requests.get(url, timeout=10, headers=headers)
        if response.status_code in (400, 401, 403, 404):
            print(f"Permanent error {response.status_code} for {url}, dropping.")
            return None
        if 500 <= response.status_code < 600:
            print(f"Server error {response.status_code} for {url}, will retry.")
            response.raise_for_status()  # Will be caught below
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        group_div = soup.find("div", class_="group")
        if group_div:
            text = group_div.get_text(separator=" ", strip=True)
            if text.strip():
                return text
        article = soup.find("article")
        if article:
            paragraphs = article.find_all("p")
            text = " ".join(p.get_text() for p in paragraphs)
            if text.strip():
                return text
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text() for p in paragraphs)
        return text.strip()
    except requests.exceptions.Timeout:
        print(f"Timeout fetching {url}, will retry.")
        raise  # Let SQS retry
    except Exception as e:
        print(f"Error fetching article text: {e}")
        raise  # Let SQS retry

def filterTextByTickers(entry, text, tickers):
    """
    Returns True if any ticker symbol or company name is mentioned in the entry title or text.
    """
    content = (entry.title + " " + text).upper()
    for ticker in tickers:
        if ticker.upper() in content:
            return True
    return False

def convert_floats(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats(i) for i in obj]
    else:
        return obj

def run_process_mode(event, context):
    """
    Consumes SQS messages, fetches article text, runs sentiment, and stores in DynamoDB.
    Handles retry logic and drops items after 5 attempts.
    Detects related tickers using fulltext/company name matching.
    """
    results = []
    records = event.get('Records', [])
    for record in records:
        msg = ast.literal_eval(record['body'])
        url = msg['url']
        title = msg['title']
        feedUrl = msg['feedUrl']
        pubdate = msg['pubdate']
        retry_count = msg.get('retry_count', 0)
        try:
            text = getFeedArticleText(url)
            if text is None:
                print(f"Dropping message for {url} due to permanent error.")
                continue
            # Detect tickers in title + article text
            related_tickers = detect_related_tickers(title + " " + text)
            if not related_tickers:
                print(f"No related tickers found for {url}, skipping.")
                continue
            sentiment = sentiment_score(text, POS, NEG)
            result = {
                "url": url,
                "title": title,
                "tickers": ",".join(related_tickers),  # Flatten tickers to comma-separated string
                "sentiment_score": sentiment["score"],  # Flatten sentiment score
                "sentiment_label": sentiment["label"],  # Flatten sentiment label
                "feedUrl": feedUrl,
                "pubdate": pubdate
            }
            result = convert_floats(result)
            persist_callback(result)
            results.append(result)
        except Exception as e:
            if retry_count >= 5:
                print(f"Dropping message for {url} after {retry_count} retries. Last error: {e}")
                continue
            msg['retry_count'] = retry_count + 1
            sqs.send_message(QueueUrl=SQS_QUEUE_URL, MessageBody=str(msg))
            print(f"Re-queued message for {url}, retry_count={msg['retry_count']}, error: {e}")
    return results

def parse_tickers_from_string(ticker_string):
    """
    Parses a comma-separated ticker string back to a list.
    """
    return [ticker.strip() for ticker in ticker_string.split(",") if ticker.strip()]
