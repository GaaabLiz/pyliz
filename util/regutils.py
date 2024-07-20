import re


def is_valid_url(url: str):
    # Definizione di un'espressione regolare per verificare l'URL
    regex = re.compile(
        r'^(?:http|ftp)s?://' # Schema
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' # Dominio
        r'localhost|' # o localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|' # o indirizzo IPv4
        r'\[?[A-F0-9]*:[A-F0-9:]+\]?)' # o indirizzo IPv6
        r'(?::\d+)?' # Porta opzionale
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    # Verifica se l'URL corrisponde all'espressione regolare
    if re.match(regex, url) is not None:
        return True
    else:
        return False

