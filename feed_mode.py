import os
import feedparser
import boto3
from time import time
from dynamodb_callbacks import get_last_feed_pubdate_callback, set_last_feed_pubdate_callback, check_processed_callback

# SQS setup
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL")
sqs = boto3.client("sqs")

def run_feed_mode(event, context):
    """
    Reads RSS feeds, deduplicates, and pushes new entries to SQS. Updates feed pubdate in DynamoDB.
    """
    feedUrls = ["https://www.cnbc.com/id/15839069/device/rss/rss.html"]
    results = []
    for feedUrl in feedUrls:
        feed = feedparser.parse(feedUrl)
        feed_pubdate = getattr(feed.feed, "published", None) or getattr(feed.feed, "pubDate", None)
        if feed_pubdate:
            last_pubdate = get_last_feed_pubdate_callback(feedUrl)
            if last_pubdate and feed_pubdate <= last_pubdate:
                print(f"Feed {feedUrl} already processed up to {last_pubdate}")
                continue
        for entry in feed.entries:
            url = entry.link
            title = entry.title
            text = title  # Only title for now, full text will be fetched in process mode
            # Check if this entry (by URL) is already processed or enqueued
            if check_processed_callback(url):
                print(f"Entry already processed or enqueued: {url}")
                continue
            msg = {
                "url": url,
                "title": title,
                "feedUrl": feedUrl,
                "pubdate": getattr(entry, "published", None) or getattr(entry, "pubDate", None) or time(),
                "retry_count": 0
            }
            sqs.send_message(QueueUrl=SQS_QUEUE_URL, MessageBody=str(msg))
            print(f"Enqueued feed entry: {msg}")  # Log the enqueued message
            results.append(msg)
        if feed_pubdate:
            set_last_feed_pubdate_callback(feedUrl, feed_pubdate)
    return results
