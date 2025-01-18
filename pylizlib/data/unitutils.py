

def convert_byte_to_mb(byte: int) -> float:
    return byte / (1024 * 1024)


def get_total_sec_from_msec(msec: int) -> int:
    return msec // 1000


def get_sec60_from_msec(msec: int) -> int:
    return get_total_sec_from_msec(msec) % 60


def get_min_from_msec(msec: int) -> int:
    return get_total_sec_from_msec(msec) // 60