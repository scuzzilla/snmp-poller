'''Core polling logic — builds SNMP requests and polls hosts concurrently.'''

import asyncio
import json
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


async def get_async(host, group, oids, snmp_init, snmp_params,
                    output_file, logger):
    '''
    Poll a single host via SNMPv3 and write the result as JSON.

    Each call is a coroutine — multiple hosts are polled
    concurrently via asyncio.gather() in main().

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

        output = json.dumps(result, indent=2)
        syslog.syslog(output)
        with open(output_file, 'a') as f:
            f.write(output + '\n')

    except Exception as err:
        logger.critical(f'{host}: {err}')


def main():
    '''Entry point — load config, init SNMP, poll all hosts.'''
    paths = cli_params()

    records = csv_loader(paths['hosts_file'])
    snmp_params = yml_loader(paths['snmp_params'])
    oids = yml_loader(paths['oids'])
    logger = pysnmp_logging(paths['logging_path'])

    snmp_init = PySnmpInit(
        snmp_params['userName'],
        snmp_params['authKey'],
        snmp_params['privKey'],
    )

    syslog.openlog(facility=syslog.LOG_LOCAL1)

    # Build one coroutine per host, then poll all concurrently.
    output_file = paths['output_file']
    tasks = [
        get_async(
            host, group, oids, snmp_init,
            snmp_params, output_file, logger,
        )
        for host, group in records.items()
    ]
    asyncio.run(asyncio.gather(*tasks))

    syslog.closelog()
