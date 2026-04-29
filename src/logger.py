import logging
import sys

# Configure the root logger
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

setup_logging()

def get_logger(name: str):
    return logging.getLogger(name)
