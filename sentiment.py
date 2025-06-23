import csv
import re
import os

# Optional: csak akkor importáljuk, ha AWS-ben vagyunk
try:
    import boto3
except ImportError:
    boto3 = None

LEXICON_CACHE = None

def load_lexicons(path=None, s3_bucket=None, s3_key=None):
    global LEXICON_CACHE
    if LEXICON_CACHE:
        return LEXICON_CACHE

    if path:
        file_path = path
    elif s3_bucket and s3_key:
        # Lokális cache hely AWS Lambda tmp mappában
        file_path = f"/tmp/{os.path.basename(s3_key)}"
        if not os.path.exists(file_path):
            s3 = boto3.client("s3")
            s3.download_file(s3_bucket, s3_key, file_path)
    else:
        raise ValueError("Must provide local path or S3 bucket/key")

    pos_set = set()
    neg_set = set()
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            word = row["Word"].lower()
            if int(row["Positive"]) > 0:
                pos_set.add(word)
            if int(row["Negative"]) > 0:
                neg_set.add(word)

    LEXICON_CACHE = (pos_set, neg_set)
    return LEXICON_CACHE

def tokenize(text):
    return re.findall(r'\b\w+\b', text.lower())

def sentiment_score(text, pos_set, neg_set):
    tokens = tokenize(text)
    pos = sum(1 for w in tokens if w in pos_set)
    neg = sum(1 for w in tokens if w in neg_set)
    total = len(tokens)
    score = (pos - neg) / total if total else 0
    label = 'positive' if score > 0 else 'negative' if score < 0 else 'neutral'
    return {'score': score, 'label': label}