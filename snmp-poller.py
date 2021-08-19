#!/usr/bin/env python3
'''
### snmp-poller
#
Author:           Salvatore Cuzzilla
em@il:            salvatore@cuzzilla.org
Starting date:    21-04-2021
Last change date: 19-08-2021
Release date:     TBD
'''

from pysnmp.hlapi.asyncio import getCmd
import time
import sys
import asyncio
from base.pysnmp_init_class import PySnmpInit
from base.cli_params import cli_params
from utils.data_loader import yml_loader
from utils.data_loader import csv_loader
from utils.logging import pysnmp_logging
import json
import syslog
from os import path

# --- MAX SNMP OIDs per GRP -> data/<oids_data.yml> --- #
MAX_OIDS_GRP_A = 2
MAX_OIDS_GRP_B = 2

app_base_path = path.dirname(path.realpath(__file__))
paths = cli_params(app_base_path)
records = csv_loader(paths['daisy_hosts'])
snmp_params = yml_loader(paths['snmp_params'])
oids = yml_loader(paths['oids'])
logger = pysnmp_logging(paths['logging_path'])

# --- check Max OIDs per GRP - can't be exceeded --- #
if len(oids['GRP_A']) > MAX_OIDS_GRP_A:
    sys.exit(f'GRP(A) max OIDs > {MAX_OIDS_GRP_A}')
if len(oids['GRP_B']) > MAX_OIDS_GRP_B:
    sys.exit(f'GRP(B) max OIDs > {MAX_OIDS_GRP_B}')

snmp_init = PySnmpInit(snmp_params['userName'],
                       snmp_params['authKey'],
                       snmp_params['privKey'])


async def get_async(host):
    '''
    snmp-poll asyncio function
    refer to https://pysnmp.readthedocs.io/en/latest/index.html
    '''
    try:
# --- OID assigment according to GRP id --- #
        if records[host] == 'A':
#           print(oids['GRP_A'])
#           print(oids['GRP_A'][0]['oid1'])
#           print(oids['GRP_A'][1]['oid2'])
            oid0 = snmp_init.init_object_type(oids['GRP_A'][0]['oid0'])
            oid1 = snmp_init.init_object_type(oids['GRP_A'][1]['oid1'])
            response = getCmd(snmp_init.snmp_engine,
                              snmp_init.usm_user_data,
                              snmp_init.init_udp_transport_target(host, snmp_params['localAddress']),
                              snmp_init.context_data,
                              oid0,
                              oid1
                              )
        elif records[host] == 'B':
#           print(oids['GRP_B'])
#           print(oids['GRP_B'][0]['oid1'])
#           print(oids['GRP_B'][1]['oid2'])
#           print(oids['GRP_B'][2]['oid3'])
            oid0 = snmp_init.init_object_type(oids['GRP_B'][0]['oid0'])
            oid1 = snmp_init.init_object_type(oids['GRP_B'][1]['oid1'])
            response = getCmd(snmp_init.snmp_engine,
                              snmp_init.usm_user_data,
                              snmp_init.init_udp_transport_target(host, snmp_params['localAddress']),
                              snmp_init.context_data,
                              oid0,
                              oid1
                              )
        else:
# --- two Systems groups supported --- #
            logger.critical(f'{host}: unhadled device group, wrong/missing info from CSV')
            oid0 = None
            oid1 = None

        errorIndication, errorStatus, errorIndex, varBinds = await response

        if errorIndication:
            logger.critical(f'{host}: {errorIndication}')
        else:
            if errorStatus:
                logger.critical('%s at %s' % (errorStatus.prettyPrint(),
                                              varBinds[int(errorIndex)-1]
                                              if errorIndex else '?'))
# --- output => encoding CSV --- #
#        if len(varBinds) == MAX_OIDS_GRP_A:
#            print(f'{host},{varBinds[0][0]},{varBinds[0][1]}')
#            print(f'{host},{varBinds[1][0]},{varBinds[1][1]}')
#        elif len (varBinds) == MAX_OIDS_GRP_B:
#            print(f'{host},{varBinds[0][0]},{varBinds[0][1]}')
#            print(f'{host},{varBinds[1][0]},{varBinds[1][1]}')
#            print(f'{host},{varBinds[2][0]},{varBinds[2][1]}')
#        else:
#            print(f'{host}: no-data-rcv')

# --- output => encoding JSON --- #
        json_structure = {
          "device":               str(host),
          "snmp_data_grp":        str(records[host]),
          "poller_instance":      str("snmp-poll-nix"),
          "oid0.ssCpuIdle":       None,
          "oid1.memAvailReal":    None
        }

        if len(varBinds) == MAX_OIDS_GRP_A:
            json_structure['oid0.ssCpuIdle'] = float(varBinds[0][1])
            json_structure['oid1.memAvailReal'] = int(varBinds[1][1])
        elif len(varBinds) == MAX_OIDS_GRP_B:
            json_structure['oid0.ssCpuIdle'] = float(varBinds[0][1])
            json_structure['oid1.memAvailReal'] = int(varBinds[1][1])

        syslog.openlog(facility=syslog.LOG_LOCAL1)
        syslog.syslog(json.dumps(json_structure, indent=2))
        with open('/var/log/snmp-poll/snmp-poll.log', 'a') as snmp_poll_out:
            snmp_poll_out.write(json.dumps(json_structure, indent=2))
            snmp_poll_out.write('\n')

    except Exception as err:
#       print('-----------------------------------')
#       print('Exception raised ---> logged(DEBUG)')
#       print('-----------------------------------')
        logger.critical(f'{host}: {err}')

# start = time.time()
asyncio.run(asyncio.wait([get_async(host) for host, os in records.items()]))
# end = time.time()

# print('\nElapsed time for function exec (Asyncio): %.3f\n' % (end - start))
