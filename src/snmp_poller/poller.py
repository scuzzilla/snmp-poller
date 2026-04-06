'''Core polling logic — builds SNMP requests and polls hosts concurrently.'''

import asyncio
import json
import multiprocessing
import syslog

from pysnmp.hlapi.asyncio import getCmd

from snmp_poller.cli import cli_params
from snmp_poller.data_loader import yml_loader, csv_loader
from snmp_poller.logging import pysnmp_logging
from snmp_poller.snmp_init import PySnmpInit

# Maps OID config 'type' strings to Python callables
# used to cast SNMP response values before JSON output.
TYPE_CASTERS = {
    'int': int,
    'float': float,
    'str': str,
}


def build_snmp_request(host, group, oids, snmp_init, snmp_params):
    '''
    Build OIDs and SNMP getCmd response for a given host and group.
    Returns (getCmd coroutine, group_oid_defs) or (None, None) if
    the group is not defined in config.
    '''
    grp_oids = oids.get(group)
    if grp_oids is None:
        return None, None

    object_types = [
        snmp_init.init_object_type(entry['oid'])
        for entry in grp_oids
    ]

    transport = snmp_init.init_udp_transport_target(
        host, snmp_params['localAddress'],
    )
    response = getCmd(
        snmp_init.snmp_engine,
        snmp_init.usm_user_data,
        transport,
        snmp_init.context_data,
        *object_types,
    )

    return response, grp_oids


def _build_result(host, group, grp_oids, var_binds):
    '''Build the JSON-serializable result dict from SNMP response.'''
    result = {
        "device": host,
        "snmp_data_grp": group,
        "poller_instance": "snmp_poll_nix",
    }

    # Map each OID response to its config-defined name/type.
    # var_binds[i] is (oid, value); [1] gets the value.
    for i, entry in enumerate(grp_oids):
        if i < len(var_binds):
            caster = TYPE_CASTERS.get(
                entry.get('type', 'str'), str,
            )
            result[entry['name']] = caster(
                var_binds[i][1]
            )

    return result


async def get_async(host, group, oids, snmp_init, snmp_params,
                    output_file, logger):
    '''
    Poll a single host via SNMPv3 and write the result as JSON.

    Used in single-process mode. Each call is a coroutine — multiple
    hosts are polled concurrently via asyncio.gather() in main().

    See: https://pysnmp.readthedocs.io/en/latest/index.html
    '''
    try:
        response, grp_oids = build_snmp_request(
            host, group, oids, snmp_init, snmp_params,
        )
        if response is None:
            logger.critical(
                f'{host}: unhandled device group "{group}", '
                f'wrong/missing info from CSV'
            )
            return

        # pysnmp returns a 4-tuple: (errorIndication, errorStatus,
        # errorIndex, varBinds). errorIndication is a transport-level
        # error; errorStatus is an SNMP protocol-level error.
        err_indication, err_status, err_index, var_binds = (
            await response
        )

        if err_indication:
            logger.critical(f'{host}: {err_indication}')
            return
        if err_status:
            err_at = (
                var_binds[int(err_index) - 1]
                if err_index else '?'
            )
            logger.critical(
                f'{err_status.prettyPrint()} at {err_at}'
            )
            return

        result = _build_result(host, group, grp_oids, var_binds)
        output = json.dumps(result, indent=2)
        syslog.syslog(output)
        with open(output_file, 'a') as f:
            f.write(output + '\n')

    except Exception as err:
        logger.critical(f'{host}: {err}')


async def poll_host(host, group, oids, snmp_init, snmp_params,
                    logger):
    '''
    Poll a single host and return the result dict, or None on error.

    Used in multiprocessing mode — results are collected and
    written centrally by the supervisor process.
    '''
    try:
        response, grp_oids = build_snmp_request(
            host, group, oids, snmp_init, snmp_params,
        )
        if response is None:
            logger.critical(
                f'{host}: unhandled device group "{group}", '
                f'wrong/missing info from CSV'
            )
            return None

        err_indication, err_status, err_index, var_binds = (
            await response
        )

        if err_indication:
            logger.critical(f'{host}: {err_indication}')
            return None
        if err_status:
            err_at = (
                var_binds[int(err_index) - 1]
                if err_index else '?'
            )
            logger.critical(
                f'{err_status.prettyPrint()} at {err_at}'
            )
            return None

        return _build_result(host, group, grp_oids, var_binds)

    except Exception as err:
        logger.critical(f'{host}: {err}')
        return None


def _partition_hosts(records, num_workers):
    '''Split {host: group} dict into num_workers roughly-equal chunks.'''
    items = list(records.items())
    chunks = []
    chunk_size = len(items) // num_workers
    remainder = len(items) % num_workers
    start = 0

    for i in range(num_workers):
        end = start + chunk_size + (1 if i < remainder else 0)
        chunks.append(dict(items[start:end]))
        start = end

    return chunks


def _worker_process(host_chunk, snmp_params, oids,
                    engine_pool_size, logging_path,
                    result_queue):
    '''
    Entry point for each worker process.
    Creates its own engine pool and event loop, polls assigned
    hosts, pushes result dicts onto result_queue.
    '''
    logger = pysnmp_logging(logging_path)

    engine_pool = [
        PySnmpInit(
            snmp_params['userName'],
            snmp_params['authKey'],
            snmp_params['privKey'],
        )
        for _ in range(engine_pool_size)
    ]

    async def _run():
        tasks = [
            poll_host(
                host, group, oids,
                engine_pool[i % engine_pool_size],
                snmp_params, logger,
            )
            for i, (host, group) in enumerate(
                host_chunk.items()
            )
        ]
        results = await asyncio.gather(*tasks)
        for r in results:
            if r is not None:
                result_queue.put(r)

    asyncio.run(_run())
    # Sentinel: tells supervisor this worker is done.
    result_queue.put(None)


def _run_multiprocess(records, snmp_params, oids,
                      engine_pool_size, output_file,
                      logging_path, num_workers):
    '''
    Distribute hosts across worker processes, collect results
    centrally, and write output from the supervisor process.
    '''
    chunks = _partition_hosts(records, num_workers)
    result_queue = multiprocessing.Queue()

    processes = []
    for chunk in chunks:
        if not chunk:
            continue
        p = multiprocessing.Process(
            target=_worker_process,
            args=(
                chunk, snmp_params, oids,
                engine_pool_size, logging_path,
                result_queue,
            ),
        )
        p.start()
        processes.append(p)

    active_workers = len(processes)

    # Drain results and write centrally — single file handle,
    # no contention between processes.
    syslog.openlog(facility=syslog.LOG_LOCAL1)
    workers_done = 0
    with open(output_file, 'a') as f:
        while workers_done < active_workers:
            item = result_queue.get()
            if item is None:
                workers_done += 1
                continue
            output = json.dumps(item, indent=2)
            syslog.syslog(output)
            f.write(output + '\n')

    for p in processes:
        p.join()

    syslog.closelog()


def main():
    '''Entry point — load config, init SNMP, poll all hosts.'''
    paths = cli_params()

    records = csv_loader(paths['hosts_file'])
    snmp_params = yml_loader(paths['snmp_params'])
    oids = yml_loader(paths['oids'])
    logger = pysnmp_logging(paths['logging_path'])

    pool_size = paths['engine_pool_size']
    num_workers = paths['workers']
    output_file = paths['output_file']

    if num_workers <= 1:
        # Single-process mode — existing behavior.
        engine_pool = [
            PySnmpInit(
                snmp_params['userName'],
                snmp_params['authKey'],
                snmp_params['privKey'],
            )
            for _ in range(pool_size)
        ]

        syslog.openlog(facility=syslog.LOG_LOCAL1)

        tasks = [
            get_async(
                host, group, oids,
                engine_pool[i % pool_size],
                snmp_params, output_file, logger,
            )
            for i, (host, group) in enumerate(records.items())
        ]
        asyncio.run(asyncio.gather(*tasks))

        syslog.closelog()
    else:
        # Multiprocessing mode — distribute across workers.
        _run_multiprocess(
            records, snmp_params, oids, pool_size,
            output_file, paths['logging_path'], num_workers,
        )
