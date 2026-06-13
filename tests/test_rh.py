from models import RHParams
from validators import validate_rh


def test_rh_validity():
    rh = RHParams(vacation_duration=450, pause_duration=30, start_min=390, end_max=1260)
    assert validate_rh(rh) == []
    assert rh.useful_one_shift_duration == 395
