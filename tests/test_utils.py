import pytest

import balaambot.utils as utils
from balaambot.utils import sec_to_string, get_cache, set_cache, memory_cache

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


@pytest.fixture(autouse=True)
def force_memory_cache(monkeypatch):
    """
    Ensure USE_REDIS is False so we use the in-process memory_cache
    and start each test with a clean slate.
    """
    monkeypatch.setattr(utils, "USE_REDIS", False)
    memory_cache.clear()
    yield
    memory_cache.clear()


@pytest.mark.asyncio
async def test_set_and_get_cache_memory():
    # Arrange
    data = {"foo": "bar", "num": 123}

    # Act
    await set_cache("mykey", data)
    # direct inspection of memory_cache:
    assert "mykey" in memory_cache
    assert memory_cache["mykey"] == data

    # fetch via async get_cache
    result = await get_cache("mykey")

    # Assert
    assert result == data


@pytest.mark.asyncio
async def test_set_overwrites_existing():
    # Arrange
    await set_cache("dupkey", {"a": 1})
    # Act: overwrite
    new_obj = {"a": 2, "b": 3}
    await set_cache("dupkey", new_obj)
    result = await get_cache("dupkey")

    # Assert
    assert result == new_obj


@pytest.mark.asyncio
async def test_get_cache_missing_key_raises_value_error():
    with pytest.raises(KeyError) as excinfo:
        await get_cache("no_such_key")
    assert "no_such_key" in str(excinfo.value)
