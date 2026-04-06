'''
Scalability benchmark — 50 concurrent SNMP agents.

Compares different pysnmp concurrency strategies to find
the optimal approach for large-scale polling.

Run with:
  pytest tests/integration/test_scalability.py -m integration -s
'''

import asyncio
import subprocess
import shutil
import time

import pytest

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


pytestmark = pytest.mark.integration

NUM_CONTAINERS = 50
BASE_PORT = 10200
OID = '.1.3.6.1.4.1.2021.4.6.0'

HAS_PODMAN = shutil.which('podman') is not None


def image_exists():
    if not HAS_PODMAN:
        return False
    r = subprocess.run(
        ['podman', 'image', 'exists', 'snmpd-test'],
        capture_output=True,
    )
    return r.returncode == 0


skip_no_podman = pytest.mark.skipif(
    not HAS_PODMAN, reason='podman not available',
)
skip_no_image = pytest.mark.skipif(
    not image_exists(),
    reason='snmpd-test image not built',
)


def start_container(name, port):
    r = subprocess.run(
        [
            'podman', 'run', '-d',
            '--name', name,
            '-p', f'{port}:161/udp',
            'snmpd-test',
        ],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f'Failed: {r.stderr}'


def stop_container(name):
    subprocess.run(
        ['podman', 'stop', '-t', '1', name],
        capture_output=True,
    )
    subprocess.run(
        ['podman', 'rm', '-f', name],
        capture_output=True,
    )


def make_usm():
    return UsmUserData(
        'nix', 'nix1234567', 'nix1234567',
        authProtocol=usmHMACMD5AuthProtocol,
        privProtocol=usmAesCfb128Protocol,
    )


def print_stats(label, total_s, per_host_ms):
    avg = sum(per_host_ms) / len(per_host_ms)
    sequential = sum(per_host_ms)
    speedup = sequential / (total_s * 1000)
    print(
        f'  {label:40s} '
        f'wall={total_s*1000:6.0f}ms  '
        f'avg/host={avg:6.1f}ms  '
        f'speedup={speedup:4.1f}x'
    )
    return total_s


@pytest.fixture(scope='module')
def containers():
    print(f'\nStarting {NUM_CONTAINERS} containers...')
    start = time.monotonic()

    hosts = []
    for i in range(NUM_CONTAINERS):
        name = f'snmpd-bench-{i}'
        port = BASE_PORT + i
        stop_container(name)
        start_container(name, port)
        hosts.append({
            'host': '127.0.0.1',
            'port': port,
            'name': name,
        })

    elapsed = time.monotonic() - start
    print(f'Containers started in {elapsed:.1f}s')
    time.sleep(3)

    yield hosts

    print(f'\nStopping {NUM_CONTAINERS} containers...')
    start = time.monotonic()
    for h in hosts:
        stop_container(h['name'])
    elapsed = time.monotonic() - start
    print(f'Containers stopped in {elapsed:.1f}s')


async def timed_poll(poll_fn, c):
    '''Time a single poll call, return ms.'''
    start = time.monotonic()
    err, _, _, varbinds = await poll_fn(c)
    elapsed = (time.monotonic() - start) * 1000
    assert err is None, f'{c["name"]}: {err}'
    assert int(varbinds[0][1]) > 0
    return elapsed


async def run_bench(label, poll_fn, containers):
    '''Run a benchmark: all hosts concurrent, return stats.'''
    start = time.monotonic()
    times = await asyncio.gather(*[
        timed_poll(poll_fn, c) for c in containers
    ])
    total = time.monotonic() - start
    print_stats(label, total, times)
    return total, times


@skip_no_podman
@skip_no_image
class TestScalability:

    @pytest.mark.asyncio
    async def test_00_baseline(self, containers):
        '''Single-host latency baseline.'''
        c = containers[0]
        engine = SnmpEngine()
        usm = make_usm()
        ctx = ContextData()

        # Warm up.
        transport = await UdpTransportTarget.create(
            (c['host'], c['port']), timeout=5, retries=2,
        )
        await get_cmd(
            engine, usm, transport, ctx,
            ObjectType(ObjectIdentity(OID)),
        )

        times = []
        for _ in range(10):
            t = await UdpTransportTarget.create(
                (c['host'], c['port']),
                timeout=5, retries=2,
            )
            start = time.monotonic()
            await get_cmd(
                engine, usm, t, ctx,
                ObjectType(ObjectIdentity(OID)),
            )
            times.append((time.monotonic() - start) * 1000)

        avg = sum(times) / len(times)
        print(
            f'\n  Baseline (1 host): '
            f'avg={avg:.1f}ms  '
            f'min={min(times):.1f}ms  '
            f'max={max(times):.1f}ms'
        )

    @pytest.mark.asyncio
    async def test_01_engine_per_request(self, containers):
        '''A: New SnmpEngine per request (no sharing).'''

        async def poll(c):
            t = await UdpTransportTarget.create(
                (c['host'], c['port']),
                timeout=5, retries=2,
            )
            return await get_cmd(
                SnmpEngine(), make_usm(), t, ContextData(),
                ObjectType(ObjectIdentity(OID)),
            )

        print()
        await run_bench(
            'A: Engine per request', poll, containers,
        )

    @pytest.mark.asyncio
    async def test_02_engine_pool(self, containers):
        '''
        B: Pool of N engines, requests distributed round-robin.
        Tests pool sizes 5, 10, 25, 50.
        '''
        print()
        for pool_size in [5, 10, 25, 50]:
            engines = [SnmpEngine() for _ in range(pool_size)]
            usms = [make_usm() for _ in range(pool_size)]
            ctxs = [ContextData() for _ in range(pool_size)]

            async def make_poll(idx):
                # Capture idx in closure.
                engine = engines[idx % pool_size]
                usm = usms[idx % pool_size]
                ctx = ctxs[idx % pool_size]

                async def poll(c):
                    t = await UdpTransportTarget.create(
                        (c['host'], c['port']),
                        timeout=5, retries=2,
                    )
                    return await get_cmd(
                        engine, usm, t, ctx,
                        ObjectType(ObjectIdentity(OID)),
                    )
                return poll

            poll_fns = [
                await make_poll(i)
                for i in range(len(containers))
            ]

            start = time.monotonic()
            times = await asyncio.gather(*[
                timed_poll(fn, c)
                for fn, c in zip(poll_fns, containers)
            ])
            total = time.monotonic() - start
            print_stats(
                f'B: Engine pool (size={pool_size})',
                total, times,
            )

    @pytest.mark.asyncio
    async def test_03_semaphore_throttle(self, containers):
        '''
        C: Engine per request but throttled with semaphore.
        Tests concurrency limits 10, 25, 50.
        '''
        print()
        for limit in [10, 25, 50]:
            sem = asyncio.Semaphore(limit)

            async def poll(c):
                async with sem:
                    t = await UdpTransportTarget.create(
                        (c['host'], c['port']),
                        timeout=5, retries=2,
                    )
                    return await get_cmd(
                        SnmpEngine(), make_usm(),
                        t, ContextData(),
                        ObjectType(ObjectIdentity(OID)),
                    )

            start = time.monotonic()
            times = await asyncio.gather(*[
                timed_poll(poll, c) for c in containers
            ])
            total = time.monotonic() - start
            print_stats(
                f'C: Semaphore (limit={limit})',
                total, times,
            )

    @pytest.mark.asyncio
    async def test_04_repeated_rounds(self, containers):
        '''
        Best approach polled 5 times to check consistency.
        '''

        async def poll(c):
            t = await UdpTransportTarget.create(
                (c['host'], c['port']),
                timeout=5, retries=2,
            )
            return await get_cmd(
                SnmpEngine(), make_usm(),
                t, ContextData(),
                ObjectType(ObjectIdentity(OID)),
            )

        print()
        round_totals = []
        for i in range(5):
            start = time.monotonic()
            results = await asyncio.gather(*[
                poll(c) for c in containers
            ])
            elapsed = time.monotonic() - start
            round_totals.append(elapsed)
            for err, _, _, _ in results:
                assert err is None

            print(f'  Round {i+1}: {elapsed*1000:.0f}ms')

        avg = sum(round_totals) / len(round_totals)
        print(f'  Avg: {avg*1000:.0f}ms')
