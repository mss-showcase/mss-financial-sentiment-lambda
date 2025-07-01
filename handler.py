import os
try:
    from dynamodb_callbacks import check_processed_callback, persist_callback, get_last_feed_pubdate_callback, set_last_feed_pubdate_callback
except ImportError:
    check_processed_callback = None
    persist_callback = None
from feed_mode import run_feed_mode
from process_mode import run_process_mode

def lambda_handler(event, context):
    run_mode = os.getenv("RUN_MODE", "FEED").upper()
    if run_mode == "FEED":
        result = run_feed_mode(event, context)
    elif run_mode == "PROCESS":
        result = run_process_mode(event, context)
    else:
        raise ValueError(f"Unknown RUN_MODE: {run_mode}")
    return {
        "statusCode": 200,
        "body": result
    }
