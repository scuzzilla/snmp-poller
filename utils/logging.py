'''
### pysnmp_logging
#
Author:           Salvatore Cuzzilla
em@il:            salvatore@cuzzilla.org
Starting date:    21-04-2021
Last change date: 19-08-2021
Release date:     TBD
'''


def pysnmp_logging(logging_file_path):
    '''
    logging function
    '''

    import logging

    # logger creation
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # file handler creation & formatter set
    fh = logging.FileHandler(logging_file_path)

    # formatter prototipe
    formatter = logging.Formatter("%(asctime)s - "
                                  "%(levelname)s - "
                                  "%(module)s - "
                                  "%(message)s", "%d-%m-%Y %H:%M:%S", "%")

    # formatter set to the associated streamHandler
    fh.setFormatter(formatter)

    # adding the choosen streamHandler to the logger
    logger.addHandler(fh)

    return logger
