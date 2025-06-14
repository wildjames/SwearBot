import concurrent.futures

FUTURES_EXECUTOR = concurrent.futures.ProcessPoolExecutor()


def sec_to_string(val: float) -> str:
    """Convert a number of seconds to a human-readable string, (HH:)MM:SS."""
    sec_in_hour = 60 * 60
    d = ""
    if val >= sec_in_hour:
        d += f"{int(val // sec_in_hour):02d}:"
        val = val % sec_in_hour
    d += f"{int(val // 60):02d}:{int(val % 60):02d}"
    return d
