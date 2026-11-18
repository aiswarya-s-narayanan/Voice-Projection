import pytest
from avatar_kiosk.speech_text import normalize_speech_text


@pytest.mark.parametrize('text, expected', [
    ('24°C', '24 degrees Celsius'), ('24 ° C', '24 degrees Celsius'),
    ('1℃ and −1°C', '1 degree Celsius and minus 1 degree Celsius'),
    ('-2.5°C / +75°F', 'minus 2.5 degrees Celsius / plus 75 degrees Fahrenheit'),
    ('24–26°C', '24 to 26 degrees Celsius'),
    ('-5--1°C', 'minus 5 to minus 1 degrees Celsius'),
    ('32℉', '32 degrees Fahrenheit'), ('24 degrees C', '24 degrees Celsius'),
    ('90° turn', '90 degrees turn'),
    ('1,000g', '1,000 grams'),
    ('250ml & 1 kg, 20%', '250 milliliters and 1 kilogram, 20 percent'),
    ('Vitamin C, table C, Affogato, Banana Milk Shakes.', 'Vitamin C, table C, Affogato, Banana Milk Shakes.'),
    ('**Welcome** — try [our menu](https://example.com).', 'Welcome, try our menu.'),
])
def test_normalization(text, expected):
    assert normalize_speech_text(text) == expected


def test_users_weather_sentence():
    text = "**It's a pleasant 24°C in Bahrain right now! I recommend our Affogato or Banana Milk Shakes as perfect choices for this weather — which appeals to you?**"
    result = normalize_speech_text(text)
    assert '24 degrees Celsius' in result
    assert 'Affogato or Banana Milk Shakes' in result
    assert '*' not in result and '°' not in result
    assert normalize_speech_text(result) == result
