

def convert_byte_to_mb(byte: int) -> float:
    return byte / (1024 * 1024)


def get_total_sec_from_msec(msec: int) -> int:
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

