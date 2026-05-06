import logging
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging() -> None:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_eth_dex_radar_configured", False):
        return

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    app_file_handler = logging.FileHandler(logs_dir / "app.log", encoding="utf-8")
    app_file_handler.setLevel(logging.INFO)
    app_file_handler.setFormatter(formatter)

    errors_file_handler = logging.FileHandler(logs_dir / "errors.log", encoding="utf-8")
    errors_file_handler.setLevel(logging.ERROR)
    errors_file_handler.setFormatter(formatter)

    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(app_file_handler)
    root_logger.addHandler(errors_file_handler)
    setattr(root_logger, "_eth_dex_radar_configured", True)
