def test_sec_to_string():
    from src.balaambot.utils import sec_to_string
    assert sec_to_string(5) == "00:05"
    assert sec_to_string(65) == "01:05"
    assert sec_to_string(3665) == "01:01:05"
