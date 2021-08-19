'''
### data_loader
#
Author:           Salvatore Cuzzilla
em@il:            salvatore@cuzzilla.org
Starting date:    21-04-2021
Last change date: 19-08-2021
Release date:     TBD
'''


def yml_loader(yml_path) -> dict:
    '''
    load data from YAML file format
    '''
    import yaml

    with open(f'{yml_path}', 'r') as yml_file:
        params = yaml.full_load(yml_file)

    return params


def csv_loader(csv_path) -> list:
    '''
    load data from CSV file format
    '''
    import csv

    records = {}
    with open(f'{csv_path}', 'r', newline='') as csv_file:
        obj_reader = csv.reader(csv_file)
        for rcrd in obj_reader:
            records[rcrd[0]] = rcrd[1]

    return records
