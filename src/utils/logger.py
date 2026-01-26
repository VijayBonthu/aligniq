import logging
import sys
from logging.handlers import RotatingFileHandler

# Create a logger instance
logger = logging.getLogger(__name__)

def setup_logger():
    # Get the root logger
    logger = logging.getLogger()

    # Clear any existing handlers
    logger.handlers = []

    # Set the logging level
    logger.setLevel(logging.INFO)

    # Suppress watchfiles logging to prevent infinite loop
    # (watchfiles logs to root logger, which writes to app.log, triggering more changes)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)

    # Create formatter with file name, line number, and function name
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - [%(filename)s:%(lineno)d - %(funcName)s()] - %(levelname)s - %(message)s'
    )

    # Create and configure console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Create and configure file handler
    file_handler = RotatingFileHandler(
        'app.log',
        maxBytes=10000000,
        encoding='utf-8',  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Prevent propagation to avoid duplicate logs
    logger.propagate = False

    return logger 