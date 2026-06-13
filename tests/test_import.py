from data_loader import _ns, _quantity_to_int
import pytest


def test_header_normalization():
    assert _ns('Nature du Flux \n(champ libre)') == _ns('Nature du Flux (champ libre)')


def test_formula_quantity_blocks():
    with pytest.raises(ValueError):
        _quantity_to_int('=A1+B1')
