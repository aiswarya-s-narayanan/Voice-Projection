"""Conservative English speech normalization before Piper synthesis.

Only explicit symbols/units are expanded; ordinary letters and menu names stay
unchanged. The displayed text and emotion metadata retain the user's wording.
"""
import re

NUMBER = r'[+−-]?\d+(?:[.,]\d+)?'


def spoken_number(value):
    value = value.replace('−', '-')
    if value.startswith('-'):
        return 'minus ' + value[1:]
    if value.startswith('+'):
        return 'plus ' + value[1:]
    return value


def normalize_speech_text(text):
    text = text.replace('℃', '°C').replace('℉', '°F')
    # Strip common presentation markup without reading asterisks/backticks aloud.
    text = re.sub(r'\[([^\]]+)\]\([^\s)]+\)', r'\1', text)
    text = re.sub(r'\*\*(.+?)\*\*|__(.+?)__', lambda m: m[1] or m[2], text)
    text = text.replace('`', '')

    def temperature(match):
        value, unit = match.group(1), match.group(2)
        degree = 'degree' if abs(float(value.replace('−', '-').replace(',', ''))) == 1 else 'degrees'
        return f'{spoken_number(value)} {degree} ' + ('Celsius' if unit.upper() == 'C' else 'Fahrenheit')

    text = re.sub(rf'(?<![\w.])({NUMBER})\s*[-–]\s*({NUMBER})\s*°\s*([CF])\b',
                  lambda m: f"{spoken_number(m[1])} to {spoken_number(m[2])} degrees " + ('Celsius' if m[3].upper() == 'C' else 'Fahrenheit'), text, flags=re.I)
    text = re.sub(rf'(?<![\w.])({NUMBER})\s*(?:°\s*|degrees?\s+)([CF])\b', temperature, text, flags=re.I)
    text = re.sub(rf'(?<![\w.])({NUMBER})\s*°(?![A-Za-z])',
                  lambda m: spoken_number(m[1]) + (' degree' if abs(float(m[1].replace('−','-').replace(',',''))) == 1 else ' degrees'), text)
    units = {'kg': ('kilogram', 'kilograms'), 'g': ('gram', 'grams'),
             'mg': ('milligram', 'milligrams'), 'ml': ('milliliter', 'milliliters'),
             'mL': ('milliliter', 'milliliters'), 'km': ('kilometer', 'kilometers'),
             'cm': ('centimeter', 'centimeters'), 'L': ('liter', 'liters')}
    def measure(match):
        number, unit = match[1], match[2]
        singular = abs(float(number.replace('−','-').replace(',',''))) == 1
        return spoken_number(number) + ' ' + units[unit][0 if singular else 1]
    text = re.sub(rf'(?<![\w.])({NUMBER})\s*(' + '|'.join(units) + r')\b', measure, text)
    text = re.sub(rf'(?<![\w.])({NUMBER})\s*%', lambda m: spoken_number(m[1]) + ' percent', text)
    text = re.sub(r'\s*&\s*', ' and ', text)
    text = text.replace('—', ', ').replace('–', ', ')
    text = re.sub(r'\s+([,;:!?])', r'\1', text)
    return re.sub(r'\s+', ' ', text).strip()
