import subprocess


def is_windows_dark_theme() -> bool:
    import platform
    if platform.system() != "Windows":
        return False

    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0  # 0 = dark, 1 = light
    except Exception:
        return False


def is_macos_dark_theme():
    try:
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        return result.stdout.strip().lower() == "dark"
    except Exception:
        return False


def is_dark_theme() -> bool:
    try:
        # Windows specific check
        import platform
        if platform.system() == "Windows":
            return is_windows_dark_theme()
        elif platform.system() == "Darwin":
            return is_macos_dark_theme()
        else:
            # Fallback cross-platform using Qt palette
            raise Exception("Unsupported OS")
    except Exception:
        raise Exception("An error occurred while checking the theme. Please check your system settings.")