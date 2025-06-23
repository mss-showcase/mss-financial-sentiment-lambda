import os
import boto3
import time

DYNAMODB_SENTIMENT_ARTICLES_TABLE = os.environ.get("DYNAMODB_SENTIMENT_ARTICLES_TABLE", "mss_sentiment_articles")
DYNAMODB_SENTIMENT_FEEDS_TABLE = os.environ.get("DYNAMODB_SENTIMENT_FEEDS_TABLE", "mss_sentiment_feeds")
dynamodb = boto3.resource("dynamodb")
article_table = dynamodb.Table(DYNAMODB_SENTIMENT_ARTICLES_TABLE)
feed_table = dynamodb.Table(DYNAMODB_SENTIMENT_FEEDS_TABLE)

def get_last_feed_pubdate_callback(feed_url):
    """
    Gets the last processed pubDate for a feed.
    """
    resp = feed_table.get_item(Key={"id": feed_url})
    if "Item" in resp:
        return resp["Item"].get("last_pubdate")
    return None

def set_last_feed_pubdate_callback(feed_url, pubdate):
    """
    Sets the last processed pubDate for a feed.
    """
    feed_table.put_item(Item={"id": feed_url, "last_pubdate": pubdate})

def check_processed_callback(url, article_pubdate=None):
    """
    Checks if the article URL is already processed.
    Optionally, can check pubdate if needed.
    """
    resp = article_table.get_item(Key={"id": url})
    if "Item" in resp:
        # Optionally, compare pubdate if provided
        if article_pubdate and "pubdate" in resp["Item"]:
            return resp["Item"]["pubdate"] >= article_pubdate
        return True
    return False

def persist_callback(record):
    """
    Persists the article record to DynamoDB, with 60-day TTL.
    """
    ttl_seconds = int(time.time()) + 60 * 24 * 60 * 60  # 60 days from now
    record["ttl"] = ttl_seconds
    record["id"] = record["url"]  # Ensure id is set for the hash key
    article_table.put_item(Item=record)