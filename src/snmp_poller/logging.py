'''Application logging setup.'''

import logging


def pysnmp_logging(logging_file_path):
    '''
    Create and return a logger that writes to the given file.
    Safe to call multiple times — reuses the existing logger
    and avoids adding duplicate handlers.
    '''
    logger = logging.getLogger('snmp_poller')
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        fh = logging.FileHandler(logging_file_path)
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(module)s - %(message)s",
            "%d-%m-%Y %H:%M:%S",
            "%",
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger
