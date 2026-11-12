"""HTTP downloads published to a destination file."""

import os
import tempfile

import requests

from pylizlib.core.domain.operation import Operation
from pylizlib.core.log.pylizLogger import logger


def download_file(url: str, destinazione: str, on_progress: callable, timeout: float = 30) -> Operation[None]:
    """Download a response to a same-directory temporary file, then replace the destination."""
    response = None
    temporary_path = None
    try:
        response = requests.get(url, stream=True, timeout=timeout)
        response.raise_for_status()
        totale = int(response.headers.get("content-length", 0) or 0)
        scaricato = 0
        percentuale = 0

        destination_dir = os.path.dirname(os.path.abspath(destinazione))
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination_dir, prefix=".download-", delete=False) as file:
            temporary_path = file.name
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    file.write(chunk)
                    scaricato += len(chunk)

                    if totale > 0:
                        nuova_percentuale = min(99, int(scaricato * 100 / totale))
                    else:
                        nuova_percentuale = percentuale
                    if nuova_percentuale > percentuale:
                        percentuale = nuova_percentuale
                        on_progress(percentuale)
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_path, destinazione)
        temporary_path = None
        if percentuale < 100:
            on_progress(100)
        logger.debug("Download completed!")
        return Operation(status=True)
    except Exception as error:
        return Operation(status=False, error=str(error))
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
