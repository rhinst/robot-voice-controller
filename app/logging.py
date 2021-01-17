import logging

logger: logging.Logger = logging.getLogger(__name__.split(".")[0])


def initialize_logger(level: str, filename: str = ""):
    global logger
    logger.setLevel(level.upper())
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler = (
        logging.StreamHandler()
        if filename == ""
        else logging.FileHandler(filename=filename)
    )
    handler.setLevel(level.upper())
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.info("Logger initialized")
