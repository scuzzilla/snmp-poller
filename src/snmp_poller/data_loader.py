'''YAML and CSV data loaders for configuration and host records.'''

import csv
import yaml


def yml_loader(yml_path) -> dict:
    '''
    Load and return data from a YAML file.
    Raises FileNotFoundError or yaml.YAMLError on failure.
    '''
    with open(yml_path, 'r') as yml_file:
        return yaml.full_load(yml_file)


def csv_loader(csv_path) -> dict:
    '''
    Load host records from a CSV file.
    Expected format: hostname/IP,group_name
    Returns {host: group} mapping.
    '''
    records = {}
    with open(csv_path, 'r', newline='') as csv_file:
        for row_num, row in enumerate(csv.reader(csv_file), start=1):
            if not row or row[0].strip() == '':
                continue
            if len(row) < 2:
                raise ValueError(
                    f'{csv_path}:{row_num}: expected at least 2 columns, '
                    f'got {len(row)}: {row}')
            records[row[0].strip()] = row[1].strip()
    return records
