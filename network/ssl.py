import ssl

import certifi
import urllib3


def ignore_context_ssl():
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def setup2323():
    ssl_context = ssl.create_default_context(cafile=certifi.where())

