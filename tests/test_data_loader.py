'''
Tests for snmp_poller.data_loader.
'''

import os
import tempfile

import pytest

from snmp_poller.data_loader import yml_loader, csv_loader


@pytest.fixture
def tmp_dir():
    '''Provide a temporary directory, cleaned up after test.'''
    with tempfile.TemporaryDirectory() as d:
        yield d


def write_file(directory, name, content):
    '''Helper to write a temp file and return its path.'''
    filepath = os.path.join(directory, name)
    with open(filepath, 'w') as f:
        f.write(content)
    return filepath


# --- yml_loader tests ---

class TestYmlLoader:

    def test_loads_valid_yaml(self, tmp_dir):
        path = write_file(tmp_dir, 'data.yml', (
            'userName: nix\n'
            'authKey: secret\n'
        ))
        result = yml_loader(path)
        assert result == {'userName': 'nix', 'authKey': 'secret'}

    def test_loads_nested_yaml(self, tmp_dir):
        path = write_file(tmp_dir, 'oids.yml', (
            'linux_servers:\n'
            '  - name: cpu\n'
            '    oid: .1.3.6\n'
            '    type: float\n'
        ))
        result = yml_loader(path)
        assert 'linux_servers' in result
        assert result['linux_servers'][0]['name'] == 'cpu'

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            yml_loader('/nonexistent/file.yml')

    def test_empty_yaml_returns_none(self, tmp_dir):
        path = write_file(tmp_dir, 'empty.yml', '')
        result = yml_loader(path)
        assert result is None


# --- csv_loader tests ---

class TestCsvLoader:

    def test_loads_valid_csv(self, tmp_dir):
        path = write_file(tmp_dir, 'hosts.csv', (
            '192.168.1.1,linux_servers\n'
            '10.0.0.1,network_switches\n'
        ))
        result = csv_loader(path)
        assert result == {
            '192.168.1.1': 'linux_servers',
            '10.0.0.1': 'network_switches',
        }

    def test_strips_whitespace(self, tmp_dir):
        path = write_file(tmp_dir, 'hosts.csv', (
            '  192.168.1.1 , linux_servers \n'
        ))
        result = csv_loader(path)
        assert result == {'192.168.1.1': 'linux_servers'}

    def test_skips_blank_lines(self, tmp_dir):
        path = write_file(tmp_dir, 'hosts.csv', (
            '192.168.1.1,linux_servers\n'
            '\n'
            '10.0.0.1,network_switches\n'
        ))
        result = csv_loader(path)
        assert len(result) == 2

    def test_skips_whitespace_only_lines(self, tmp_dir):
        path = write_file(tmp_dir, 'hosts.csv', (
            '192.168.1.1,linux_servers\n'
            '   \n'
        ))
        result = csv_loader(path)
        assert len(result) == 1

    def test_malformed_row_raises(self, tmp_dir):
        path = write_file(tmp_dir, 'hosts.csv', (
            '192.168.1.1\n'
        ))
        with pytest.raises(ValueError, match='expected at least 2'):
            csv_loader(path)

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            csv_loader('/nonexistent/file.csv')

    def test_empty_file_returns_empty_dict(self, tmp_dir):
        path = write_file(tmp_dir, 'empty.csv', '')
        result = csv_loader(path)
        assert result == {}

    def test_extra_columns_ignored(self, tmp_dir):
        path = write_file(tmp_dir, 'hosts.csv', (
            '192.168.1.1,linux_servers,extra,stuff\n'
        ))
        result = csv_loader(path)
        assert result == {'192.168.1.1': 'linux_servers'}
