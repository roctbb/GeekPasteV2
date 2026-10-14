"""Data-only comparison rules retained when importing older IO tasks."""
from decimal import Decimal, DecimalException, localcontext
import re
import unicodedata


COMPATIBILITY_LABELS = {
    'strip_suffix': 'Конец вывода — без крайних пробелов',
    'lower_suffix': 'Конец вывода — без учёта регистра',
    'lower_exact': 'Весь вывод — без учёта регистра',
    'normalized_suffix': 'Конец вывода — нормализация Unicode и пробелов',
    'exact_suffix': 'Точный конец вывода — без конечных переносов строк',
    'last_time': 'Время ЧЧ:ММ в конце вывода',
    'last_integer': 'Последнее целое число в конце вывода',
    'integer_tokens': 'Целые числа — формат Python int',
    'integer_tokens_ascii30': 'Целые числа — ASCII, до 30 символов',
    'keyword_integers_ascii30': 'Слово без учёта регистра, затем целые числа ASCII',
    'word_integer_ascii30': 'Точное слово и одно целое число ASCII',
    'splitlines': 'Точные строки — разделители строк Python',
    'word_lower': 'Одно слово — без учёта регистра',
    'rational_absolute': 'Число — точная дробь и абсолютный допуск 10⁻⁶',
}
TIME_AT_END = re.compile(r'(?<!\d)((?:[01]\d|2[0-3]):[0-5]\d)\s*$')
INTEGER_AT_END = re.compile(r'(?<![+\-\d])([+-]?\d+)\s*$')
DECIMAL_NUMBER = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')
RATIONAL_REFERENCE = re.compile(r'([+-]?[0-9]{1,100})/([0-9]{1,100})\Z')


def normalized(text):
    return ' '.join(unicodedata.normalize('NFKC', text).replace('\u00a0', ' ').split())


def rational_parts(expected):
    match = RATIONAL_REFERENCE.fullmatch(expected.strip())
    if not match or int(match[2]) == 0:
        raise ValueError('Для сравнения с дробью задайте эталон числитель/знаменатель; знаменатель должен быть положительным.')
    return int(match[1]), int(match[2])


def _ascii_integers(tokens):
    if any(len(token) > 30 or not re.fullmatch(r'[+-]?[0-9]+', token) for token in tokens):
        raise ValueError('Invalid integer')
    return list(map(int, tokens))


def compatibility_equal(actual, expected, comparison):
    try:
        if comparison == 'strip_suffix':
            return actual.strip().endswith(expected.strip())
        if comparison == 'lower_suffix':
            return actual.strip().lower().endswith(expected.lower())
        if comparison == 'lower_exact':
            return actual.strip().lower() == expected.lower()
        if comparison == 'normalized_suffix':
            return normalized(actual).endswith(normalized(expected))
        if comparison == 'exact_suffix':
            return actual.replace('\r\n', '\n').replace('\r', '\n').rstrip('\n').endswith(expected)
        if comparison in ('last_time', 'last_integer'):
            pattern = TIME_AT_END if comparison == 'last_time' else INTEGER_AT_END
            left, right = pattern.search(actual), pattern.search(normalized(expected))
            return bool(left and right and (left[1] == right[1] if comparison == 'last_time'
                                            else int(left[1]) == int(right[1])))
        if comparison == 'splitlines':
            return actual.splitlines() == expected.splitlines()
        left, right = actual.split(), expected.split()
        if comparison == 'integer_tokens':
            return list(map(int, left)) == list(map(int, right))
        if comparison == 'integer_tokens_ascii30':
            return _ascii_integers(left) == _ascii_integers(right)
        if comparison == 'keyword_integers_ascii30':
            return bool(left and right and left[0].upper() == right[0]
                        and _ascii_integers(left[1:]) == _ascii_integers(right[1:]))
        if comparison == 'word_integer_ascii30':
            return (len(left) == len(right) == 2 and left[0] == right[0]
                    and _ascii_integers(left[1:]) == _ascii_integers(right[1:]))
        if comparison == 'word_lower':
            return len(left) == len(right) == 1 and left[0].lower() == right[0].lower()
        if comparison == 'rational_absolute':
            if len(left) != 1 or len(left[0]) > 100 or not DECIMAL_NUMBER.fullmatch(left[0]):
                return False
            numerator, denominator = rational_parts(expected)
            with localcontext() as context:
                context.prec = 80
                value = Decimal(left[0])
                return value.is_finite() and abs(value * denominator - numerator) <= Decimal('0.000001') * denominator
    except (ValueError, DecimalException, OverflowError):
        return False
    raise ValueError('Неизвестный способ сравнения.')
