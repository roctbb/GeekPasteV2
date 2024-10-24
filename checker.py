from difflib import SequenceMatcher

def similarity(a, b):
    return round(SequenceMatcher(None, a, b).ratio()*100)
