import random
import string
from datetime import datetime


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


def gen_random_string(length: int) -> str:
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


def gen_timestamp_log_name(prefix: str, extension: str):
    return prefix + datetime.now().strftime("%Y%m%d_%H%M%S") + extension
