from time_windows import minutes_to_hhmm
from data_loader import _to_minutes, _safe_str


def test_excel_fraction_to_minutes():
    assert _to_minutes(0.25) == 360
    assert _to_minutes(0.020833333333333332) == 30


def test_safe_str_nan():
    assert _safe_str(float('nan')) is None
    assert _safe_str('nan') is None
    assert _safe_str('  ABC ') == 'ABC'


def test_minutes_format():
    assert minutes_to_hhmm(390) == '06:30'
