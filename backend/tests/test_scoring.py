import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.scoring import clamp_breakdown, clamp_score, weighted_score


def test_weighted_score_rounds_half_up():
    # 80*0.4 + 75*0.3 + 60*0.15 + 60*0.15 = 72.5；Python 的 round() 是银行家舍入，会得到 72
    assert weighted_score({"skills": 80, "experience": 75, "education": 60, "other": 60}) == 73


def test_weighted_score_ignores_float_noise():
    # 0.3 * 70 在浮点下是 21.000000000000004
    assert weighted_score({"skills": 0, "experience": 70, "education": 0, "other": 0}) == 21


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(72.5, 73), (72.4, 72), ("88", 88), (150, 100), (-5, 0), ("abc", 0), (None, 0)],
)
def test_clamp_score(raw, expected):
    assert clamp_score(raw) == expected


def test_clamp_breakdown_fills_missing_keys():
    assert clamp_breakdown({"skills": 120}) == {"skills": 100, "experience": 0, "education": 0, "other": 0}
    assert clamp_breakdown(None) is None


def test_settings_reject_weights_not_summing_to_one():
    with pytest.raises(ValidationError):
        Settings(score_weights={"skills": 0.5, "experience": 0.5, "education": 0.5, "other": 0.5})


def test_settings_reject_unknown_weight_keys():
    with pytest.raises(ValidationError):
        Settings(score_weights={"skills": 1.0})
