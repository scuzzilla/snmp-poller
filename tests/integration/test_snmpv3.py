'''
Integration tests for snmp_poller using real SNMP agents.

Requires:
  - podman
  - The snmpd-test container image (built from tests/integration/)
  - pysnmp >= 7 (pip install 'pysnmp>=7')

Run with:
  pytest tests/integration/ -m integration

These tests are skipped automatically if podman is not available
or the container image is not built.
'''

import asyncio
import json
import shutil
import subprocess
import time

import pytest

# pysnmp v7 async API — used directly for integration tests
# because pysnmp v4 (the app's dependency) can't run on
# Python 3.12+ due to the removed asyncore module.
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    UsmUserData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    get_cmd,
    usmHMACMD5AuthProtocol,
    usmAesCfb128Protocol,
)

# OIDs that are reliably available in a containerized snmpd.
# ssCpuIdle (.1.3.6.1.4.1.2021.11.11.0) does NOT work in
# containers (needs /proc/stat access), so we use alternatives.
OID_SYS_DESCR = '.1.3.6.1.2.1.1.1.0'
OID_SYS_UPTIME = '.1.3.6.1.2.1.1.3.0'
OID_MEM_TOTAL = '.1.3.6.1.4.1.2021.4.5.0'
OID_MEM_AVAIL = '.1.3.6.1.4.1.2021.4.6.0'
OID_MEM_FREE = '.1.3.6.1.4.1.2021.4.11.0'


# --- Markers and skips ---

pytestmark = pytest.mark.integration

HAS_PODMAN = shutil.which('podman') is not None


def image_exists():
    '''Check if snmpd-test image is built.'''
    if not HAS_PODMAN:
        return False
    result = subprocess.run(
        ['podman', 'image', 'exists', 'snmpd-test'],
        capture_output=True,
    )
    return result.returncode == 0


skip_no_podman = pytest.mark.skipif(
    not HAS_PODMAN,
    reason='podman not available',
)
skip_no_image = pytest.mark.skipif(
    not image_exists(),
    reason='snmpd-test image not built '
           '(run: podman build -t snmpd-test '
           '-f tests/integration/Containerfile '
           'tests/integration/)',
)


# --- Container lifecycle ---

def start_container(name, host_port):
    '''Start an snmpd container, return container ID.'''
    result = subprocess.run(
        [
            'podman', 'run', '-d',
            '--name', name,
            '-p', f'{host_port}:161/udp',
            'snmpd-test',
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f'Failed to start container: {result.stderr}'
    )
    # Give snmpd time to initialize.
    time.sleep(1)
    return result.stdout.strip()


def stop_container(name):
    '''Stop and remove a container by name.'''
    subprocess.run(
        ['podman', 'stop', '-t', '1', name],
        capture_output=True,
    )
    subprocess.run(
        ['podman', 'rm', '-f', name],
        capture_output=True,
    )


# --- SNMP query helpers ---

async def snmpv3_get(host, port, *oid_strings):
    '''
    Perform a real SNMPv3 GET using the integration test
    credentials (nix / nix1234567 / MD5+AES).
    '''
    transport = await UdpTransportTarget.create(
        (host, port), timeout=5, retries=2,
    )
    return await get_cmd(
        SnmpEngine(),
        UsmUserData(
            'nix', 'nix1234567', 'nix1234567',
            authProtocol=usmHMACMD5AuthProtocol,
            privProtocol=usmAesCfb128Protocol,
        ),
        transport,
        ContextData(),
        *[
            ObjectType(ObjectIdentity(oid))
            for oid in oid_strings
        ],
    )


# --- Fixtures ---

@pytest.fixture(scope='module')
def snmpd_container():
    '''Start a single snmpd container for the test module.'''
    name = 'snmpd-integration-test'
    port = 10161
    stop_container(name)
    start_container(name, port)
    yield {'host': '127.0.0.1', 'port': port, 'name': name}
    stop_container(name)


@pytest.fixture(scope='module')
def snmpd_containers():
    '''Start multiple snmpd containers for scalability tests.'''
    count = 5
    base_port = 10170
    containers = []

    for i in range(count):
        name = f'snmpd-scale-test-{i}'
        port = base_port + i
        stop_container(name)
        start_container(name, port)
        containers.append({
            'host': '127.0.0.1',
            'port': port,
            'name': name,
        })

    yield containers

    for c in containers:
        stop_container(c['name'])


# --- Tests ---

@skip_no_podman
@skip_no_image
class TestSNMPv3Polling:
    '''Test real SNMP polling against a live snmpd agent.'''

    @pytest.mark.asyncio
    async def test_poll_sysDescr(self, snmpd_container):
        '''sysDescr should return the OS description string.'''
        err, status, idx, varbinds = await snmpv3_get(
            snmpd_container['host'],
            snmpd_container['port'],
            OID_SYS_DESCR,
        )

        assert err is None, f'errorIndication: {err}'
        assert not status
        assert len(varbinds) == 1
        value = str(varbinds[0][1])
        assert 'Linux' in value

    @pytest.mark.asyncio
    async def test_poll_memAvailReal(self, snmpd_container):
        '''memAvailReal should return a positive integer (kB).'''
        err, status, idx, varbinds = await snmpv3_get(
            snmpd_container['host'],
            snmpd_container['port'],
            OID_MEM_AVAIL,
        )

        assert err is None, f'errorIndication: {err}'
        assert not status
        assert len(varbinds) == 1
        value = int(varbinds[0][1])
        assert value > 0

    @pytest.mark.asyncio
    async def test_poll_multiple_oids(self, snmpd_container):
        '''Polling multiple OIDs in one request.'''
        err, status, idx, varbinds = await snmpv3_get(
            snmpd_container['host'],
            snmpd_container['port'],
            OID_MEM_TOTAL,
            OID_MEM_AVAIL,
            OID_MEM_FREE,
        )

        assert err is None
        assert not status
        assert len(varbinds) == 3

        mem_total = int(varbinds[0][1])
        mem_avail = int(varbinds[1][1])
        mem_free = int(varbinds[2][1])
        assert mem_total > 0
        assert mem_avail > 0
        assert mem_free > 0
        assert mem_total >= mem_avail

    @pytest.mark.asyncio
    async def test_wrong_credentials_fail(
        self, snmpd_container,
    ):
        '''Bad auth key should produce an error.'''
        transport = await UdpTransportTarget.create(
            (
                snmpd_container['host'],
                snmpd_container['port'],
            ),
            timeout=3, retries=1,
        )
        err, status, idx, varbinds = await get_cmd(
            SnmpEngine(),
            UsmUserData(
                'nix', 'WRONGKEY!!!!', 'WRONGKEY!!!!',
                authProtocol=usmHMACMD5AuthProtocol,
                privProtocol=usmAesCfb128Protocol,
            ),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(OID_MEM_AVAIL)),
        )

        # Should get an error — either errorIndication
        # (timeout/auth failure) or errorStatus.
        assert err is not None or status

    @pytest.mark.asyncio
    async def test_nonexistent_oid(self, snmpd_container):
        '''Querying a non-existent OID returns noSuchInstance.'''
        oid = '.1.3.6.1.4.1.99999.1.2.3'
        err, status, idx, varbinds = await snmpv3_get(
            snmpd_container['host'],
            snmpd_container['port'],
            oid,
        )

        assert err is None
        # Response contains the OID but with a
        # noSuchInstance or noSuchObject exception value.
        assert len(varbinds) == 1


@skip_no_podman
@skip_no_image
class TestConcurrentPolling:
    '''
    Test that multiple SNMP agents can be polled concurrently
    using asyncio.gather.
    '''

    @pytest.mark.asyncio
    async def test_concurrent_poll_multiple_agents(
        self, snmpd_containers,
    ):
        '''
        Poll all containers concurrently. Total time should be
        much less than N * single-request time.
        '''

        async def poll_one(container):
            err, status, idx, varbinds = await snmpv3_get(
                container['host'],
                container['port'],
                OID_MEM_AVAIL,
            )
            assert err is None, (
                f'{container["name"]}: {err}'
            )
            assert not status
            return int(varbinds[0][1])

        start = time.monotonic()
        results = await asyncio.gather(
            *[poll_one(c) for c in snmpd_containers],
        )
        elapsed = time.monotonic() - start

        # All containers should return valid memory values.
        assert len(results) == len(snmpd_containers)
        for val in results:
            assert val > 0

        # Concurrent should complete in under 5s total.
        assert elapsed < 5.0, (
            f'Concurrent poll of {len(snmpd_containers)} '
            f'agents took {elapsed:.2f}s'
        )

    @pytest.mark.asyncio
    async def test_json_output_matches_expected_format(
        self, snmpd_containers,
    ):
        '''
        Simulate the app's output logic: poll, build JSON,
        verify fields match the config-driven approach.
        '''
        container = snmpd_containers[0]

        err, status, idx, varbinds = await snmpv3_get(
            container['host'],
            container['port'],
            OID_MEM_TOTAL,
            OID_MEM_AVAIL,
        )

        assert err is None
        assert len(varbinds) == 2

        # Build JSON the same way poller.py does.
        oid_defs = [
            {'name': 'memTotalReal', 'type': 'int'},
            {'name': 'memAvailReal', 'type': 'int'},
        ]
        type_casters = {
            'int': int, 'float': float, 'str': str,
        }

        json_structure = {
            'device': container['host'],
            'snmp_data_grp': 'linux_servers',
            'poller_instance': 'snmp_poll_nix',
        }
        for i, entry in enumerate(oid_defs):
            caster = type_casters[entry['type']]
            json_structure[entry['name']] = (
                caster(varbinds[i][1])
            )

        output = json.dumps(json_structure, indent=2)
        parsed = json.loads(output)

        assert parsed['device'] == container['host']
        assert parsed['snmp_data_grp'] == 'linux_servers'
        assert isinstance(parsed['memTotalReal'], int)
        assert isinstance(parsed['memAvailReal'], int)
        assert parsed['memTotalReal'] > 0
        assert parsed['memAvailReal'] > 0
