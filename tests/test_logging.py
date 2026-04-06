'''
Tests for snmp_poller.logging.
'''

import os
import logging

from snmp_poller.logging import pysnmp_logging


class TestPysnmpLogging:

    def test_returns_logger(self, tmp_path):
        log_file = tmp_path / 'test.log'
        logger = pysnmp_logging(str(log_file))

        assert isinstance(logger, logging.Logger)
        assert logger.name == 'snmp_poller'

    def test_creates_log_file_on_write(self, tmp_path):
        log_file = tmp_path / 'test.log'
        logger = pysnmp_logging(str(log_file))

        logger.info('test message')

        assert os.path.isfile(log_file)
        with open(log_file) as f:
            content = f.read()
        assert 'test message' in content

    def test_log_format(self, tmp_path):
        log_file = tmp_path / 'test.log'
        logger = pysnmp_logging(str(log_file))

        logger.warning('format check')

        with open(log_file) as f:
            line = f.read()
        # Format: "DD-MM-YYYY HH:MM:SS - LEVEL - MODULE - MSG"
        assert ' - WARNING - ' in line
        assert 'format check' in line

    def test_debug_level_captured(self, tmp_path):
        log_file = tmp_path / 'test.log'
        logger = pysnmp_logging(str(log_file))

        logger.debug('debug msg')

        with open(log_file) as f:
            content = f.read()
        assert 'debug msg' in content

    def test_no_duplicate_handlers(self, tmp_path):
        log_file = tmp_path / 'test.log'

        logger1 = pysnmp_logging(str(log_file))
        handler_count = len(logger1.handlers)

        logger2 = pysnmp_logging(str(log_file))

        assert logger1 is logger2
        assert len(logger2.handlers) == handler_count

    def teardown_method(self):
        # Clean up the shared logger between tests to avoid
        # handler leaks across test methods.
        logger = logging.getLogger('snmp_poller')
        for h in logger.handlers[:]:
            h.close()
            logger.removeHandler(h)
