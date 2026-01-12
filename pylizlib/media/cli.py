from pylizlib.media import media_app
from pylizlib.media.script import organizer


@media_app.command()
def temp():
    """
    Template command for media_app.
    """
    print("This is a temporary command in media_app.")


if __name__ == "__main__":
    media_app()