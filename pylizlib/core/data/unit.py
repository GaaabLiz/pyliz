

def convert_byte_to_mb(byte: int) -> float:
    """
    Convert byte to megabyte.
    1 MB = 1024 * 1024 bytes
    :param byte: Size in bytes
    :return: Size in megabytes
    """
    return byte / (1024 * 1024)


def get_total_sec_from_msec(msec: int) -> int:
    """
    Convert milliseconds to total seconds.
    :param msec: Time in milliseconds
    :return: Time in total seconds
    """
    return msec // 1000


def get_sec60_from_msec(msec: int) -> int:
    return get_total_sec_from_msec(msec) % 60


def get_min_from_msec(msec: int) -> int:
    return get_total_sec_from_msec(msec) // 60


def convert_months_number_to_str(number: int) -> str:
    months = {
        1: "January",
        2: "February",
        3: "March",
        4: "April",
        5: "May",
        6: "June",
        7: "July",
        8: "August",
        9: "September",
        10: "October",
        11: "November",
        12: "December"
    }
    return months.get(number, "Invalid Month")

def get_normalized_gb_mb_str(total_size: float ) -> str:
    size_mb = total_size / (1024 * 1024)
    if size_mb < 1000:
        return f"{size_mb:.2f} MB"
    size_gb = size_mb / 1024
    return f"{size_gb:.2f} GB"