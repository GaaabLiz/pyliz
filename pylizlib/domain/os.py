from enum import Enum


class OsType(Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    MAC = "mac"
    ANDROID = "android"
    IOS = "ios"
    UNKNOWN = "unknown"


class OsTheme(Enum):
    LIGHT = "light"
    DARK = "dark"
    UNKNOWN = "unknown"
