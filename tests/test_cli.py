'''
Tests for snmp_poller.cli.
'''

import os
import tempfile

import pytest

from snmp_poller.cli import cli_params


@pytest.fixture
def tmp_dir():
    '''Provide a temporary directory, cleaned up after test.'''
    with tempfile.TemporaryDirectory() as d:
        yield d


def write_file(directory, name, content='placeholder'):
    '''Helper to write a temp file and return its path.'''
    filepath = os.path.join(directory, name)
    with open(filepath, 'w') as f:
        f.write(content)
    return filepath


def make_valid_args(tmp_dir):
    '''Create valid config files and return CLI args list.'''
    snmp = write_file(tmp_dir, 'auth.yml', 'userName: nix\n')
    hosts = write_file(tmp_dir, 'hosts.csv', '10.0.0.1,linux\n')
    oids = write_file(tmp_dir, 'oids.yml', 'linux:\n  - name: x\n')
    log_dir = os.path.join(tmp_dir, 'logs')
    return ['-s', snmp, '-l', hosts, '-o', oids, '--log-dir', log_dir]


class TestCliParams:

    def test_valid_args_returns_paths(self, tmp_dir, monkeypatch):
        args = make_valid_args(tmp_dir)
        monkeypatch.setattr('sys.argv', ['snmp-poller'] + args)

        result = cli_params()

        assert result['snmp_params'].endswith('.yml')
        assert result['hosts_file'].endswith('.csv')
        assert result['oids'].endswith('.yml')
        assert 'logging_path' in result
        assert 'output_file' in result

    def test_creates_log_directory(self, tmp_dir, monkeypatch):
        args = make_valid_args(tmp_dir)
        log_dir = os.path.join(tmp_dir, 'logs')
        monkeypatch.setattr('sys.argv', ['snmp-poller'] + args)

        cli_params()

        assert os.path.isdir(log_dir)

    def test_logging_path_inside_log_dir(
        self, tmp_dir, monkeypatch,
    ):
        args = make_valid_args(tmp_dir)
        log_dir = os.path.join(tmp_dir, 'logs')
        monkeypatch.setattr('sys.argv', ['snmp-poller'] + args)

        result = cli_params()

        assert result['logging_path'].startswith(log_dir)
        assert result['logging_path'].endswith(
            'snmp_poll_app.log',
        )

    def test_custom_output_file(self, tmp_dir, monkeypatch):
        args = make_valid_args(tmp_dir)
        custom_path = os.path.join(tmp_dir, 'custom.log')
        args.extend(['-f', custom_path])
        monkeypatch.setattr('sys.argv', ['snmp-poller'] + args)

        result = cli_params()

        assert result['output_file'] == custom_path

    def test_missing_file_exits(self, tmp_dir, monkeypatch):
        snmp = '/nonexistent/auth.yml'
        hosts = write_file(tmp_dir, 'hosts.csv', 'data\n')
        oids = write_file(tmp_dir, 'oids.yml', 'data\n')
        monkeypatch.setattr('sys.argv', [
            'snmp-poller', '-s', snmp, '-l', hosts, '-o', oids,
        ])

        with pytest.raises(SystemExit):
            cli_params()

    def test_empty_file_exits(self, tmp_dir, monkeypatch):
        snmp = write_file(tmp_dir, 'auth.yml', '')
        hosts = write_file(tmp_dir, 'hosts.csv', 'data\n')
        oids = write_file(tmp_dir, 'oids.yml', 'data\n')
        monkeypatch.setattr('sys.argv', [
            'snmp-poller', '-s', snmp, '-l', hosts, '-o', oids,
        ])

        with pytest.raises(SystemExit):
            cli_params()

    def test_wrong_extension_exits(
        self, tmp_dir, monkeypatch,
    ):
        snmp = write_file(tmp_dir, 'auth.txt', 'data\n')
        hosts = write_file(tmp_dir, 'hosts.csv', 'data\n')
        oids = write_file(tmp_dir, 'oids.yml', 'data\n')
        monkeypatch.setattr('sys.argv', [
            'snmp-poller', '-s', snmp, '-l', hosts, '-o', oids,
        ])

        with pytest.raises(SystemExit):
            cli_params()

    def test_csv_with_yml_extension_exits(
        self, tmp_dir, monkeypatch,
    ):
        snmp = write_file(tmp_dir, 'auth.yml', 'data\n')
        hosts = write_file(tmp_dir, 'hosts.yml', 'data\n')
        oids = write_file(tmp_dir, 'oids.yml', 'data\n')
        monkeypatch.setattr('sys.argv', [
            'snmp-poller', '-s', snmp, '-l', hosts, '-o', oids,
        ])

        with pytest.raises(SystemExit):
            cli_params()
