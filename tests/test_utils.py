import pytest
from balaambot.utils import sec_to_string

@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "00:00"),
        (5, "00:05"),
        (65, "01:05"),
        (3600, "01:00:00"),
        (3665, "01:01:05"),
    ],
)
def test_sec_to_string(seconds, expected):
    assert sec_to_string(seconds) == expected

