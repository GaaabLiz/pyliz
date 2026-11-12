"""User and application directory locations."""

import os


def get_home_dir():
    """Return the current user's home directory using the platform convention.

    Returns:
        str: The expanded home-directory path.
    """
    return os.path.expanduser("~")


def get_app_home_dir(app_name, create_if_not: bool = True):
    """Return a named directory under the current user's home directory.

    Args:
        app_name (str): Directory name to append to the home directory.
        create_if_not (bool): Create the directory when it does not exist.

    Returns:
        str: Application-directory path.
    """
    app_home_dir = os.path.join(get_home_dir(), app_name)
    if create_if_not and not os.path.exists(app_home_dir):
        os.makedirs(app_home_dir)
    return app_home_dir
