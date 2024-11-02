from enum import Enum

from util import fileutils


class FileType(Enum):
    IMAGE = "IMAGE"
    TEXT = "TEXT"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"
    DIRECTORY = "DIRECTORY"
    LINK = "LINK"
    SHORTCUT = "SHORTCUT"
    SYSTEM = "SYSTEM"
    ARCHIVE = "ARCHIVE"
    CODE = "CODE"
    DATABASE = "DATABASE"
    EXECUTABLE = "EXECUTABLE"
    FONT = "FONT"
    PRESENTATION = "PRESENTATION"
    SPREADSHEET = "SPREADSHEET"
    WEB = "WEB"
    WORD = "WORD"
    PDF = "PDF"
    SLIDE = "SLIDE"
    SHEET = "SHEET"
    DRAWING = "DRAWING"
    FORM = "FORM"
    SLIDE_SHOW = "SLIDE_SHOW"
    SHEET_SET = "SHEET_SET"
    MAP = "MAP"
    EBOOK = "EBOOK"
    EMAIL = "EMAIL"
    CALENDAR = "CALENDAR"
    CONTACT = "CONTACT"
    TASK = "TASK"
    NOTE = "NOTE"
    JOURNAL = "JOURNAL"
    BOOKMARK = "BOOKMARK"
    LINKEDIN = "LINKEDIN"
    FACEBOOK = "FACEBOOK"
    TWITTER = "TWITTER"
    INSTAGRAM = "INSTAGRAM"
    YOUTUBE = "YOUTUBE"
    VIMEO = "VIMEO"
    TIKTOK = "TIKTOK"
    PINTEREST = "PINTEREST"
    SNAPCHAT = "SNAPCHAT"
    REDDIT = "REDDIT"
    TUMBLR = "TUMBLR"
    WHATSAPP = "WHATSAPP"
    TELEGRAM = "TELEGRAM"
    SIGNAL = "SIGNAL"
    DISCORD = "DISCORD"
    SLACK = "SLACK"
    ZOOM = "ZOOM"
    MICROSOFT_TEAMS = "MICROSOFT_TEAMS"
    GOOGLE_MEET = "GOOGLE_MEET"
    SKYPE = "SKYPE"
    WECHAT = "WECHAT"
    QQ = "QQ"
    LINE = "LINE"
    KAKAOTALK = "KAKAOTALK"
    VIBER = "VIBER"