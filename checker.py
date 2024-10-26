from difflib import SequenceMatcher
import re

def similarity(a, b):
    a = a.lower()
    b = b.lower()


    a = re.sub(r'//.*?$|/\*.*?\*/', '', a, flags=re.DOTALL | re.MULTILINE)
    b = re.sub(r'//.*?$|/\*.*?\*/', '', b, flags=re.DOTALL | re.MULTILINE)

    a = a.replace(" ", "").replace("\t", "").replace("\n", "")
    b = b.replace(" ", "").replace("\t", "").replace("\n", "")

    return round(SequenceMatcher(None, a, b).ratio()*100)
