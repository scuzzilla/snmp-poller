'''
### cli_params
#
Author:           Salvatore Cuzzilla
em@il:            salvatore@cuzzilla.org
Starting date:    21-04-2021
Last change date: 19-08-2021
Release date:     TBD
'''


def cli_params(app_base_path):
    '''
    Input cli params; simple validity checks performed
    '''

    import argparse
    from argparse import RawTextHelpFormatter
    from os import path

    valid_logs = False
    valid_hosts = False
    valid_v3auth = False
    valid_oids = False
    valid_ext = False

    if path.isdir(f'{app_base_path}/logs'):
        valid_logs = True
        logging_path = f'{app_base_path}/logs/snmp-poll-app.log'
    else:
        print('Invalid local logs path')

    parser = argparse.ArgumentParser(description='SNMP Poller',
                                     formatter_class=RawTextHelpFormatter)

    mandatory = parser.add_argument_group('mandatory arguments')

    mandatory.add_argument('-s',
                           required=True,
                           dest='snmp_params',
                           action='store',
                           metavar='<SNMPv3 parameters>',
                           help='load the SNMPv3 required parameters '
                                'from the selected file (YAML format)\n')

    mandatory.add_argument('-l',
                           required=True,
                           dest='daisy_hosts',
                           action='store',
                           metavar='<hostname/IPv4 list>',
                           help='load the hosts from the '
                                'selected file (CSV format)\n')

    mandatory.add_argument('-o',
                           required=True,
                           dest='oids',
                           action='store',
                           metavar='SNMP oid list',
                           help='load the oid list '
                                'from the selected file (YAML format)\n')

    args = parser.parse_args()

    list_valid_ext = ['csv',
                      'yml', ]

    if path.isfile(args.snmp_params) and path.getsize(args.snmp_params):
        valid_v3auth = True
    else:
        print('Invalid SNMPv3\'s params file selected [-s]')

    if path.isfile(args.daisy_hosts) and path.getsize(args.daisy_hosts):
        valid_hosts = True
    else:
        print('Invalid hosts\'s file selected [-l]')

    if path.isfile(args.oids) and path.getsize(args.oids):
        valid_oids = True
    else:
        print('Invalid oid\'s file selected [-o]')

    for ext in list_valid_ext:
        if ext in (args.daisy_hosts or args.snmp_params):
            valid_ext = True

    if valid_ext is False:
        print('Invalid file extension: either .yml | .csv [-s | -l]')

    if valid_logs and \
       valid_hosts and \
       valid_v3auth and \
       valid_oids and \
       valid_ext:
        params = {'daisy_hosts': args.daisy_hosts,
                  'snmp_params': args.snmp_params,
                  'oids': args.oids,
                  'logging_path': logging_path, }
        return params
    else:
        raise SystemExit
