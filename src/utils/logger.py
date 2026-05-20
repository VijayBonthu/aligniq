import logging
import os
import sys


def setup_logger():
    """
    Container-friendly logger setup.
    - LOG_LEVEL env var controls verbosity (DEBUG locally, INFO in staging, WARNING in prod).
    - stdout only — Docker awslogs driver ships stdout to CloudWatch.
    - No file handler: container filesystems are ephemeral and disk I/O is wasted.
    """
    root = logging.getLogger()
    root.handlers = []

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    root.setLevel(getattr(logging, level_name, logging.INFO))

    # Noisy libraries we don't need at INFO
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    formatter = logging.Formatter(
        "%(asctime)s - [%(filename)s:%(lineno)d - %(funcName)s()] - %(levelname)s - %(message)s"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # Opt-in file handler for local debugging on Windows where stdout capture
    # can be unreliable. Set LOG_TO_FILE=true in .env to enable.
    if os.getenv("LOG_TO_FILE", "false").lower() == "true":
        try:
            os.makedirs("logs", exist_ok=True)
            file_handler = logging.FileHandler("logs/app.log", encoding="utf-8")
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError:
            pass

    root.propagate = False
    return root


logger = logging.getLogger(__name__)
