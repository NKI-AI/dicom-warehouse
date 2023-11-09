import configparser
import logging
import logging.config
import os
from tempfile import NamedTemporaryFile
from typing import Optional

from dcmw.paths import CONFIG_DIR, LOG_DIR


def get_logger(logger_name: Optional[str] = "formatted", config_filename: str = "logger.ini") -> logging.Logger:
    """
    Retrieve a logger instance with the specified name. Configures logging if not already configured.

    Args:
    - logger_name (str, optional): Name of the logger instance to retrieve. Defaults to "formatted".
    - config_path (str): Path to the logger configuration file. Defaults to 'config/logger.ini'.

    Returns:
    - logging.Logger: Logger instance with the given name.
    """
    # Only configure logging if it's not already configured
    if not logging.getLogger().hasHandlers():
        # Determine the absolute path to the logger configuration
        config_path = CONFIG_DIR / config_filename

        # Use configparser to modify the log file path
        config = configparser.ConfigParser()
        config.read(config_path)

        # Adjust the log file path dynamically
        log_file_path = LOG_DIR / "logs.txt"
        config["handler_fileHandler"]["args"] = str((str(log_file_path), "a"))

        # Save the modified config to a temporary file and apply it
        with NamedTemporaryFile(delete=False, mode="w+t") as temp_file:
            config.write(temp_file)

        logging.config.fileConfig(temp_file.name, disable_existing_loggers=False)
        os.remove(temp_file.name)

    return logging.getLogger(logger_name)
