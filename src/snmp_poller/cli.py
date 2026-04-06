'''CLI argument parsing and validation.'''

import argparse
import os
from os import path


# Maps each CLI argument to its required file extension.
EXPECTED_EXTENSIONS = {
    'snmp_params': '.yml',
    'hosts_file': '.csv',
    'oids': '.yml',
}


DEFAULT_OUTPUT_FILE = '/var/log/snmp_poll/snmp_poll.log'
DEFAULT_LOG_DIR = '/var/log/snmp_poll'


def cli_params():
    '''
    Parse and validate CLI arguments.
    Returns a dict with validated file paths and the logging path.
    Creates the log directory if it doesn't exist.
    '''

    parser = argparse.ArgumentParser(
        description='SNMP Poller',
        formatter_class=argparse.RawTextHelpFormatter,
    )

    mandatory = parser.add_argument_group('mandatory arguments')

    mandatory.add_argument('-s',
                           required=True,
                           dest='snmp_params',
                           metavar='<SNMPv3 parameters>',
                           help='load the SNMPv3 required parameters '
                                'from the selected file (YAML format)\n')

    mandatory.add_argument('-l',
                           required=True,
                           dest='hosts_file',
                           metavar='<hostname/IPv4 list>',
                           help='load the hosts from the '
                                'selected file (CSV format)\n')

    mandatory.add_argument('-o',
                           required=True,
                           dest='oids',
                           metavar='<SNMP oid list>',
                           help='load the oid list '
                                'from the selected file (YAML format)\n')

    parser.add_argument('-f',
                        dest='output_file',
                        default=DEFAULT_OUTPUT_FILE,
                        metavar='<output log file>',
                        help='path for JSON poll output '
                             f'(default: {DEFAULT_OUTPUT_FILE})\n')

    parser.add_argument('--log-dir',
                        dest='log_dir',
                        default=DEFAULT_LOG_DIR,
                        metavar='<log directory>',
                        help='directory for application logs '
                             f'(default: {DEFAULT_LOG_DIR})\n')

    parser.add_argument('--engine-pool-size',
                        dest='engine_pool_size',
                        type=int,
                        default=5,
                        metavar='<N>',
                        help='number of SNMP engines per worker '
                             '(default: 5)\n')

    parser.add_argument('--workers',
                        dest='workers',
                        type=int,
                        default=1,
                        metavar='<N>',
                        help='number of worker processes '
                             '(default: 1, single-process)\n')

    args = parser.parse_args()

    # Validate each input file: must exist, non-empty, correct extension.
    for arg_name, expected_ext in EXPECTED_EXTENSIONS.items():
        filepath = getattr(args, arg_name)

        if not path.isfile(filepath):
            parser.error(f'file not found: {filepath}')
        if path.getsize(filepath) == 0:
            parser.error(f'file is empty: {filepath}')

        _, actual_ext = path.splitext(filepath)
        if actual_ext != expected_ext:
            parser.error(
                f'{filepath}: expected {expected_ext} extension, '
                f'got {actual_ext!r}')

    # Create log directory if it doesn't exist yet.
    os.makedirs(args.log_dir, exist_ok=True)

    if args.engine_pool_size < 1:
        parser.error('--engine-pool-size must be >= 1')
    if args.workers < 1:
        parser.error('--workers must be >= 1')

    return {
        'hosts_file':       args.hosts_file,
        'snmp_params':      args.snmp_params,
        'oids':             args.oids,
        'output_file':      args.output_file,
        'engine_pool_size': args.engine_pool_size,
        'workers':          args.workers,
        'logging_path':     path.join(
            args.log_dir, 'snmp_poll_app.log',
        ),
    }
