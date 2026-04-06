'''
Tests for snmp_poller.

Mocks the pysnmp layer entirely so:
  - No real SNMP agents are needed
  - No pysnmp binary compatibility issues
    (asyncore removal in Python 3.12+)
'''

import sys
import types
import asyncio
import time
import json
import logging
from unittest.mock import (
    MagicMock, AsyncMock, patch, mock_open,
)

import pytest


# --- Mock pysnmp before importing snmp_poller ---
# We mock the pysnmp v7 module tree so tests run without
# a real pysnmp installation.

def _install_pysnmp_mocks():
    mock_modules = {}
    for name in [
        'pysnmp',
        'pysnmp.hlapi',
        'pysnmp.hlapi.v3arch',
        'pysnmp.hlapi.v3arch.asyncio',
        'pysnmp.hlapi.v3arch.asyncio.transport',
    ]:
        mock_modules[name] = types.ModuleType(name)

    v3 = mock_modules['pysnmp.hlapi.v3arch.asyncio']
    v3.get_cmd = AsyncMock(name='get_cmd')
    v3.UdpTransportTarget = MagicMock(
        name='UdpTransportTarget',
    )
    v3.SnmpEngine = MagicMock(name='SnmpEngine')
    v3.UsmUserData = MagicMock(name='UsmUserData')
    v3.ContextData = MagicMock(name='ContextData')
    v3.ObjectIdentity = MagicMock(name='ObjectIdentity')
    v3.ObjectType = MagicMock(name='ObjectType')
    v3.usmHMACMD5AuthProtocol = 'md5-mock'
    v3.usmAesCfb128Protocol = 'aes-mock'

    sys.modules.update(mock_modules)


_install_pysnmp_mocks()

from snmp_poller.poller import (  # noqa: E402
    build_snmp_request, get_async, poll_host,
    _partition_hosts,
)
import snmp_poller.poller as poller_module  # noqa: E402


# --- Config fixtures ---

OIDS_LINUX = [
    {
        'name': 'ssCpuIdle',
        'oid': '.1.3.6.1.4.1.2021.11.11.0',
        'type': 'float',
    },
    {
        'name': 'memAvailReal',
        'oid': '.1.3.6.1.4.1.2021.4.6.0',
        'type': 'int',
    },
]

OIDS_SWITCHES = [
    {
        'name': 'ifInOctets',
        'oid': '.1.3.6.1.2.1.2.2.1.10.1',
        'type': 'int',
    },
    {
        'name': 'ifOutOctets',
        'oid': '.1.3.6.1.2.1.2.2.1.16.1',
        'type': 'int',
    },
    {
        'name': 'sysUpTime',
        'oid': '.1.3.6.1.2.1.1.3.0',
        'type': 'str',
    },
]

SAMPLE_OIDS = {
    'linux_servers': OIDS_LINUX,
    'network_switches': OIDS_SWITCHES,
}

SAMPLE_SNMP_PARAMS = {
    'userName': 'nix',
    'authKey': 'nix1234567',
    'privKey': 'nix1234567',
    'localAddress': '127.0.0.1',
}

SAMPLE_OUTPUT_FILE = '/tmp/test_snmp_poll.log'


def make_mock_snmp_init():
    snmp_init = MagicMock()
    snmp_init.init_object_type = MagicMock(
        side_effect=lambda oid: f'OT({oid})',
    )
    snmp_init.init_udp_transport_target = AsyncMock(
        return_value='transport',
    )
    snmp_init.snmp_engine = 'engine'
    snmp_init.usm_user_data = 'usm'
    snmp_init.context_data = 'ctx'
    return snmp_init


def make_logger():
    logger = logging.getLogger(f'test.{id(object())}')
    logger.critical = MagicMock()
    return logger


def make_varbinds(values):
    '''Simulate pysnmp varBinds: list of (oid, value) tuples.'''
    return [(MagicMock(), v) for v in values]


async def poll(host, group, snmp_init, logger):
    '''Shorthand for calling get_async with standard fixtures.'''
    return await get_async(
        host, group, SAMPLE_OIDS, snmp_init,
        SAMPLE_SNMP_PARAMS, SAMPLE_OUTPUT_FILE, logger,
    )


# --- build_snmp_request tests ---

class TestBuildSnmpRequest:

    @pytest.mark.asyncio
    async def test_known_group_returns_response_and_oid_defs(
        self,
    ):
        snmp_init = make_mock_snmp_init()
        fake_response = (None, None, None, [])
        with patch.object(
            poller_module, 'get_cmd',
            new_callable=AsyncMock,
            return_value=fake_response,
        ):
            result, grp_oids = await build_snmp_request(
                '10.0.0.1', 'linux_servers',
                SAMPLE_OIDS, snmp_init, SAMPLE_SNMP_PARAMS,
            )
        assert result == fake_response
        assert grp_oids is OIDS_LINUX
        assert snmp_init.init_object_type.call_count == 2

    @pytest.mark.asyncio
    async def test_group_with_three_oids(self):
        snmp_init = make_mock_snmp_init()
        fake_response = (None, None, None, [])
        with patch.object(
            poller_module, 'get_cmd',
            new_callable=AsyncMock,
            return_value=fake_response,
        ):
            result, grp_oids = await build_snmp_request(
                '10.0.0.2', 'network_switches',
                SAMPLE_OIDS, snmp_init, SAMPLE_SNMP_PARAMS,
            )
        assert result == fake_response
        assert grp_oids is OIDS_SWITCHES
        assert snmp_init.init_object_type.call_count == 3

    @pytest.mark.asyncio
    async def test_unknown_group_returns_none(self):
        snmp_init = make_mock_snmp_init()
        result, grp_oids = await build_snmp_request(
            '10.0.0.3', 'unknown_group',
            SAMPLE_OIDS, snmp_init, SAMPLE_SNMP_PARAMS,
        )
        assert result is None
        assert grp_oids is None

    @pytest.mark.asyncio
    async def test_passes_all_oids_to_get_cmd(self):
        snmp_init = make_mock_snmp_init()
        with patch.object(
            poller_module, 'get_cmd',
            new_callable=AsyncMock,
            return_value=(None, None, None, []),
        ) as mock_cmd:
            await build_snmp_request(
                '10.0.0.1', 'network_switches',
                SAMPLE_OIDS, snmp_init, SAMPLE_SNMP_PARAMS,
            )
        # engine, usm, transport, context + 3 object_types
        args = mock_cmd.call_args[0]
        assert len(args) == 4 + 3


# --- get_async tests ---

class TestGetAsync:

    @pytest.mark.asyncio
    async def test_successful_poll_linux(self):
        logger = make_logger()
        snmp_init = make_mock_snmp_init()
        varbinds = make_varbinds([92.5, 2048000])
        with patch.object(
            poller_module, 'build_snmp_request',
            new_callable=AsyncMock,
            return_value=(
                (None, None, None, varbinds), OIDS_LINUX,
            ),
        ), patch.object(
            poller_module, 'syslog',
        ), patch('builtins.open', mock_open()):
            await poll(
                '10.0.0.1', 'linux_servers',
                snmp_init, logger,
            )

        logger.critical.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_poll_switches(self):
        logger = make_logger()
        snmp_init = make_mock_snmp_init()
        varbinds = make_varbinds([123456, 654321, '1:02:33:44'])

        with patch.object(
            poller_module, 'build_snmp_request',
            new_callable=AsyncMock,
            return_value=(
                (None, None, None, varbinds), OIDS_SWITCHES,
            ),
        ), patch.object(
            poller_module, 'syslog',
        ), patch('builtins.open', mock_open()):
            await poll(
                '10.0.0.2', 'network_switches',
                snmp_init, logger,
            )

        logger.critical.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_group_logs_critical(self):
        logger = make_logger()
        snmp_init = make_mock_snmp_init()
        await poll(
            '10.0.0.1', 'unknown_group', snmp_init, logger,
        )

        logger.critical.assert_called_once()
        msg = logger.critical.call_args[0][0]
        assert 'unhandled device group' in msg

    @pytest.mark.asyncio
    async def test_error_indication_logs_critical(self):
        logger = make_logger()
        snmp_init = make_mock_snmp_init()
        with patch.object(
            poller_module, 'build_snmp_request',
            new_callable=AsyncMock,
            return_value=(
                ('timeout', None, None, []), OIDS_LINUX,
            ),
        ):
            await poll(
                '10.0.0.1', 'linux_servers',
                snmp_init, logger,
            )

        logger.critical.assert_called_once()
        assert 'timeout' in logger.critical.call_args[0][0]

    @pytest.mark.asyncio
    async def test_error_status_logs_critical(self):
        logger = make_logger()
        snmp_init = make_mock_snmp_init()
        mock_status = MagicMock()
        mock_status.prettyPrint.return_value = 'noSuchName'

        with patch.object(
            poller_module, 'build_snmp_request',
            new_callable=AsyncMock,
            return_value=(
                (None, mock_status, 1, [('oid', 'val')]),
                OIDS_LINUX,
            ),
        ):
            await poll(
                '10.0.0.1', 'linux_servers',
                snmp_init, logger,
            )

        logger.critical.assert_called_once()
        msg = logger.critical.call_args[0][0]
        assert 'noSuchName' in msg

    @pytest.mark.asyncio
    async def test_exception_is_caught_and_logged(self):
        logger = make_logger()
        snmp_init = make_mock_snmp_init()

        with patch.object(
            poller_module, 'build_snmp_request',
            new_callable=AsyncMock,
            side_effect=ConnectionError('connection refused'),
        ):
            await poll(
                '10.0.0.1', 'linux_servers',
                snmp_init, logger,
            )

        logger.critical.assert_called_once()
        msg = logger.critical.call_args[0][0]
        assert 'connection refused' in msg

    @pytest.mark.asyncio
    async def test_json_output_linux_group(self):
        '''JSON output fields come from config.'''
        logger = make_logger()
        snmp_init = make_mock_snmp_init()
        varbinds = make_varbinds([88.0, 512000])
        written_data = []

        m = mock_open()
        m().write = MagicMock(
            side_effect=lambda data: written_data.append(data),
        )

        with patch.object(
            poller_module, 'build_snmp_request',
            new_callable=AsyncMock,
            return_value=(
                (None, None, None, varbinds), OIDS_LINUX,
            ),
        ), patch.object(
            poller_module, 'syslog',
        ), patch('builtins.open', m):
            await poll(
                '10.0.0.1', 'linux_servers',
                snmp_init, logger,
            )

        out = json.loads(written_data[0])
        assert out['device'] == '10.0.0.1'
        assert out['snmp_data_grp'] == 'linux_servers'
        assert out['ssCpuIdle'] == 88.0
        assert out['memAvailReal'] == 512000

    @pytest.mark.asyncio
    async def test_json_output_switches_group(self):
        '''Different group produces different fields.'''
        logger = make_logger()
        snmp_init = make_mock_snmp_init()
        varbinds = make_varbinds([100, 200, '0:05:00:00'])
        written_data = []

        m = mock_open()
        m().write = MagicMock(
            side_effect=lambda data: written_data.append(data),
        )

        with patch.object(
            poller_module, 'build_snmp_request',
            new_callable=AsyncMock,
            return_value=(
                (None, None, None, varbinds), OIDS_SWITCHES,
            ),
        ), patch.object(
            poller_module, 'syslog',
        ), patch('builtins.open', m):
            await poll(
                '10.0.0.2', 'network_switches',
                snmp_init, logger,
            )

        out = json.loads(written_data[0])
        assert out['device'] == '10.0.0.2'
        assert out['snmp_data_grp'] == 'network_switches'
        assert out['ifInOctets'] == 100
        assert out['ifOutOctets'] == 200
        assert out['sysUpTime'] == '0:05:00:00'
        assert 'ssCpuIdle' not in out
        assert 'memAvailReal' not in out

    @pytest.mark.asyncio
    async def test_type_casting(self):
        '''Values are cast per config type field.'''
        logger = make_logger()
        snmp_init = make_mock_snmp_init()
        varbinds = make_varbinds(['92', '1024'])
        written_data = []

        m = mock_open()
        m().write = MagicMock(
            side_effect=lambda data: written_data.append(data),
        )

        with patch.object(
            poller_module, 'build_snmp_request',
            new_callable=AsyncMock,
            return_value=(
                (None, None, None, varbinds), OIDS_LINUX,
            ),
        ), patch.object(
            poller_module, 'syslog',
        ), patch('builtins.open', m):
            await poll(
                '10.0.0.1', 'linux_servers',
                snmp_init, logger,
            )

        out = json.loads(written_data[0])
        assert isinstance(out['ssCpuIdle'], float)
        assert isinstance(out['memAvailReal'], int)


# --- Scalability / concurrency tests ---

class TestAsyncScalability:

    @pytest.mark.asyncio
    async def test_concurrent_polling_scales(self):
        '''
        50 hosts with 0.1s simulated latency each.
        Concurrent: ~0.1s. Sequential would be 5s.
        '''
        num_hosts = 50
        simulated_latency = 0.1

        records = {
            f'10.0.0.{i}': 'linux_servers'
            for i in range(1, num_hosts + 1)
        }
        snmp_init = make_mock_snmp_init()
        logger = make_logger()

        async def mock_build(host, group, oids, si, sp):
            await asyncio.sleep(simulated_latency)
            vb = make_varbinds([95.0, 1024])
            return (None, None, None, vb), OIDS_LINUX

        with patch.object(
            poller_module, 'build_snmp_request',
            side_effect=mock_build,
        ), patch.object(
            poller_module, 'syslog',
        ), patch('builtins.open', mock_open()):

            tasks = [
                poll(host, group, snmp_init, logger)
                for host, group in records.items()
            ]

            start = time.monotonic()
            await asyncio.gather(*tasks)
            elapsed = time.monotonic() - start

        assert elapsed < 1.0, (
            f'Polling {num_hosts} hosts took {elapsed:.2f}s'
            f' — expected under 1s with concurrency'
        )

    @pytest.mark.asyncio
    async def test_partial_failures_dont_block_others(self):
        '''
        Failures (unknown group) should not block
        successful hosts from completing.
        '''
        records = {
            '10.0.0.1': 'linux_servers',
            '10.0.0.2': 'unknown_group',
            '10.0.0.3': 'network_switches',
            '10.0.0.4': 'linux_servers',
        }
        snmp_init = make_mock_snmp_init()
        logger = make_logger()

        call_count = {'ok': 0}

        async def mock_build(host, group, oids, si, sp):
            grp_oids = oids.get(group)
            if grp_oids is None:
                return None, None
            values = [0] * len(grp_oids)
            call_count['ok'] += 1
            return (
                (None, None, None, make_varbinds(values)),
                grp_oids,
            )

        with patch.object(
            poller_module, 'build_snmp_request',
            side_effect=mock_build,
        ), patch.object(
            poller_module, 'syslog',
        ), patch('builtins.open', mock_open()):

            tasks = [
                poll(host, group, snmp_init, logger)
                for host, group in records.items()
            ]
            await asyncio.gather(*tasks)

        assert call_count['ok'] == 3
        assert logger.critical.call_count == 1

    @pytest.mark.asyncio
    async def test_mixed_groups_polled_concurrently(self):
        '''
        Different groups get different OID sets,
        all polled concurrently.
        '''
        records = {
            '10.0.0.1': 'linux_servers',
            '10.0.0.2': 'network_switches',
            '10.0.0.3': 'linux_servers',
        }
        snmp_init = make_mock_snmp_init()
        logger = make_logger()
        written_data = []

        async def mock_build(host, group, oids, si, sp):
            grp_oids = oids.get(group)
            values = list(range(len(grp_oids)))
            return (
                (None, None, None, make_varbinds(values)),
                grp_oids,
            )

        m = mock_open()
        m().write = MagicMock(
            side_effect=lambda data: written_data.append(data),
        )

        with patch.object(
            poller_module, 'build_snmp_request',
            side_effect=mock_build,
        ), patch.object(
            poller_module, 'syslog',
        ), patch('builtins.open', m):

            tasks = [
                poll(host, group, snmp_init, logger)
                for host, group in records.items()
            ]
            await asyncio.gather(*tasks)

        results = [
            json.loads(d) for d in written_data if d.strip()
        ]
        groups_seen = {r['snmp_data_grp'] for r in results}
        assert groups_seen == {
            'linux_servers', 'network_switches',
        }
        assert len(results) == 3

        for r in results:
            if r['snmp_data_grp'] == 'linux_servers':
                assert 'ssCpuIdle' in r
                assert 'memAvailReal' in r
                assert 'ifInOctets' not in r
            else:
                assert 'ifInOctets' in r
                assert 'ifOutOctets' in r
                assert 'sysUpTime' in r
                assert 'ssCpuIdle' not in r


# --- Partition tests ---

class TestPartitionHosts:

    def test_even_split(self):
        records = {f'h{i}': 'g' for i in range(12)}
        chunks = _partition_hosts(records, 4)
        assert len(chunks) == 4
        assert all(len(c) == 3 for c in chunks)
        all_hosts = set()
        for c in chunks:
            all_hosts.update(c.keys())
        assert all_hosts == set(records.keys())

    def test_uneven_split(self):
        records = {f'h{i}': 'g' for i in range(10)}
        chunks = _partition_hosts(records, 3)
        assert len(chunks) == 3
        sizes = sorted(len(c) for c in chunks)
        assert sizes == [3, 3, 4]

    def test_more_workers_than_hosts(self):
        records = {'h0': 'a', 'h1': 'b', 'h2': 'c'}
        chunks = _partition_hosts(records, 10)
        assert len(chunks) == 10
        non_empty = [c for c in chunks if c]
        assert len(non_empty) == 3

    def test_single_worker(self):
        records = {f'h{i}': 'g' for i in range(5)}
        chunks = _partition_hosts(records, 1)
        assert len(chunks) == 1
        assert chunks[0] == records

    def test_preserves_host_group_mapping(self):
        records = {'h0': 'linux', 'h1': 'switches'}
        chunks = _partition_hosts(records, 2)
        combined = {}
        for c in chunks:
            combined.update(c)
        assert combined == records


# --- poll_host tests ---

class TestPollHost:

    @pytest.mark.asyncio
    async def test_returns_dict_on_success(self):
        snmp_init = make_mock_snmp_init()
        logger = make_logger()
        varbinds = make_varbinds([95.0, 1024])

        with patch.object(
            poller_module, 'build_snmp_request',
            new_callable=AsyncMock,
            return_value=(
                (None, None, None, varbinds), OIDS_LINUX,
            ),
        ):
            result = await poll_host(
                '10.0.0.1', 'linux_servers',
                SAMPLE_OIDS, snmp_init,
                SAMPLE_SNMP_PARAMS, logger,
            )

        assert result is not None
        assert result['device'] == '10.0.0.1'
        assert result['snmp_data_grp'] == 'linux_servers'
        assert result['ssCpuIdle'] == 95.0
        assert result['memAvailReal'] == 1024

    @pytest.mark.asyncio
    async def test_returns_none_on_unknown_group(self):
        snmp_init = make_mock_snmp_init()
        logger = make_logger()

        result = await poll_host(
            '10.0.0.1', 'unknown',
            SAMPLE_OIDS, snmp_init,
            SAMPLE_SNMP_PARAMS, logger,
        )

        assert result is None
        logger.critical.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_error_indication(self):
        snmp_init = make_mock_snmp_init()
        logger = make_logger()

        with patch.object(
            poller_module, 'build_snmp_request',
            new_callable=AsyncMock,
            return_value=(
                ('timeout', None, None, []), OIDS_LINUX,
            ),
        ):
            result = await poll_host(
                '10.0.0.1', 'linux_servers',
                SAMPLE_OIDS, snmp_init,
                SAMPLE_SNMP_PARAMS, logger,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        snmp_init = make_mock_snmp_init()
        logger = make_logger()

        with patch.object(
            poller_module, 'build_snmp_request',
            new_callable=AsyncMock,
            side_effect=ConnectionError('refused'),
        ):
            result = await poll_host(
                '10.0.0.1', 'linux_servers',
                SAMPLE_OIDS, snmp_init,
                SAMPLE_SNMP_PARAMS, logger,
            )

        assert result is None
        logger.critical.assert_called_once()
