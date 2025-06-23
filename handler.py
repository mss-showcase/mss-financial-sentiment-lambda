from handler_internal import lambda_handler_internal
try:
    from dynamodb_callbacks import check_processed_callback, persist_callback, get_last_feed_pubdate_callback, set_last_feed_pubdate_callback
except ImportError:
    check_processed_callback = None
    persist_callback = None

def lambda_handler(event, context):
    result = lambda_handler_internal(
        event,
        context,
        check_processed_callback=check_processed_callback,
        persist_callback=persist_callback,
        get_last_feed_pubdate_callback=get_last_feed_pubdate_callback,
        set_last_feed_pubdate_callback=set_last_feed_pubdate_callback
    )
    return {
        "statusCode": 200,
        "body": result
    }
