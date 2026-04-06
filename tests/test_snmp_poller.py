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
# pysnmp 4.x depends on asyncore (removed in Python 3.12+),
# so we build a minimal mock module tree.

def _install_pysnmp_mocks():
    mock_modules = {}
    for name in [
        'pysnmp', 'pysnmp.hlapi',
        'pysnmp.hlapi.asyncio',
        'pysnmp.hlapi.auth',
        'pysnmp.smi', 'pysnmp.smi.rfc1902',
    ]:
        mock_modules[name] = types.ModuleType(name)

    hlapi_asyncio = mock_modules['pysnmp.hlapi.asyncio']
    hlapi_asyncio.getCmd = MagicMock(name='getCmd')
    hlapi_asyncio.UdpTransportTarget = MagicMock(
        name='UdpTransportTarget',
    )

    hlapi = mock_modules['pysnmp.hlapi']
    hlapi.SnmpEngine = MagicMock(name='SnmpEngine')
    hlapi.UsmUserData = MagicMock(name='UsmUserData')
    hlapi.ContextData = MagicMock(name='ContextData')
    hlapi.ObjectIdentity = MagicMock(name='ObjectIdentity')
    hlapi.ObjectType = MagicMock(name='ObjectType')

    auth = mock_modules['pysnmp.hlapi.auth']
    auth.usmHMACMD5AuthProtocol = 'md5-mock'
    auth.usmAesCfb128Protocol = 'aes-mock'

    sys.modules.update(mock_modules)


_install_pysnmp_mocks()

from snmp_poller.poller import (  # noqa: E402
    build_snmp_request, get_async,
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
    snmp_init.init_udp_transport_target = MagicMock(
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

    def test_known_group_returns_response_and_oid_defs(self):
        snmp_init = make_mock_snmp_init()
        with patch.object(
            poller_module, 'getCmd', return_value='fake',
        ):
            response, grp_oids = build_snmp_request(
                '10.0.0.1', 'linux_servers',
                SAMPLE_OIDS, snmp_init, SAMPLE_SNMP_PARAMS,
            )
        assert response == 'fake'
        assert grp_oids is OIDS_LINUX
        assert snmp_init.init_object_type.call_count == 2

    def test_group_with_three_oids(self):
        snmp_init = make_mock_snmp_init()
        with patch.object(
            poller_module, 'getCmd', return_value='fake',
        ):
            response, grp_oids = build_snmp_request(
                '10.0.0.2', 'network_switches',
                SAMPLE_OIDS, snmp_init, SAMPLE_SNMP_PARAMS,
            )
        assert response == 'fake'
        assert grp_oids is OIDS_SWITCHES
        assert snmp_init.init_object_type.call_count == 3

    def test_unknown_group_returns_none(self):
        snmp_init = make_mock_snmp_init()
        response, grp_oids = build_snmp_request(
            '10.0.0.3', 'unknown_group',
            SAMPLE_OIDS, snmp_init, SAMPLE_SNMP_PARAMS,
        )
        assert response is None
        assert grp_oids is None

    def test_passes_all_oids_to_getCmd(self):
        snmp_init = make_mock_snmp_init()
        with patch.object(
            poller_module, 'getCmd', return_value='fake',
        ) as mock_cmd:
            build_snmp_request(
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
        fake = AsyncMock(
            return_value=(None, None, None, varbinds),
        )

        with patch.object(
            poller_module, 'build_snmp_request',
            return_value=(fake(), OIDS_LINUX),
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
        fake = AsyncMock(
            return_value=(None, None, None, varbinds),
        )

        with patch.object(
            poller_module, 'build_snmp_request',
            return_value=(fake(), OIDS_SWITCHES),
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
        fake = AsyncMock(
            return_value=('timeout', None, None, []),
        )

        with patch.object(
            poller_module, 'build_snmp_request',
            return_value=(fake(), OIDS_LINUX),
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
        fake = AsyncMock(
            return_value=(None, mock_status, 1, [('oid', 'val')]),
        )

        with patch.object(
            poller_module, 'build_snmp_request',
            return_value=(fake(), OIDS_LINUX),
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

        async def exploding_response():
            raise ConnectionError('connection refused')

        with patch.object(
            poller_module, 'build_snmp_request',
            return_value=(exploding_response(), OIDS_LINUX),
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
        fake = AsyncMock(
            return_value=(None, None, None, varbinds),
        )
        written_data = []

        m = mock_open()
        m().write = MagicMock(
            side_effect=lambda data: written_data.append(data),
        )

        with patch.object(
            poller_module, 'build_snmp_request',
            return_value=(fake(), OIDS_LINUX),
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
        fake = AsyncMock(
            return_value=(None, None, None, varbinds),
        )
        written_data = []

        m = mock_open()
        m().write = MagicMock(
            side_effect=lambda data: written_data.append(data),
        )

        with patch.object(
            poller_module, 'build_snmp_request',
            return_value=(fake(), OIDS_SWITCHES),
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
        fake = AsyncMock(
            return_value=(None, None, None, varbinds),
        )
        written_data = []

        m = mock_open()
        m().write = MagicMock(
            side_effect=lambda data: written_data.append(data),
        )

        with patch.object(
            poller_module, 'build_snmp_request',
            return_value=(fake(), OIDS_LINUX),
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

        async def slow_response():
            await asyncio.sleep(simulated_latency)
            return (None, None, None, make_varbinds([95.0, 1024]))

        def mock_build(host, group, oids, si, sp):
            return slow_response(), OIDS_LINUX

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

        async def tracked_response(oid_defs):
            values = [0] * len(oid_defs)
            call_count['ok'] += 1
            return (None, None, None, make_varbinds(values))

        def mock_build(host, group, oids, si, sp):
            grp_oids = oids.get(group)
            if grp_oids is None:
                return None, None
            return tracked_response(grp_oids), grp_oids

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

        async def fake_response(oid_defs):
            values = list(range(len(oid_defs)))
            return (None, None, None, make_varbinds(values))

        def mock_build(host, group, oids, si, sp):
            grp_oids = oids.get(group)
            return fake_response(grp_oids), grp_oids

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
