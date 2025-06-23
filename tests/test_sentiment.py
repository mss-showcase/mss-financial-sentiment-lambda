import os
import pytest
from sentiment import load_lexicons, sentiment_score

# A teszt fájlon belül relatív útvonal a szótárhoz
DICTIONARY_PATH = os.path.join(os.path.dirname(__file__), '..', 'Loughran-McDonald_MasterDictionary_1993-2024.csv')

@pytest.fixture(scope="session")
def lexicons():
    pos, neg = load_lexicons(DICTIONARY_PATH)
    return pos, neg

def test_positive_sentiment(lexicons):
    pos, neg = lexicons
    text = "The company delivered strong revenue growth and exceeded expectations."
    result = sentiment_score(text, pos, neg)
    assert result["label"] == "positive"
    assert result["score"] > 0

def test_negative_sentiment(lexicons):
    pos, neg = lexicons
    text = "The company reported disappointing earnings and profit warnings."
    result = sentiment_score(text, pos, neg)
    assert result["label"] == "negative"
    assert result["score"] < 0

def test_neutral_sentiment(lexicons):
    pos, neg = lexicons
    text = "The company held a press conference to present its annual strategy."
    result = sentiment_score(text, pos, neg)
    assert result["label"] == "neutral"
