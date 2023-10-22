#!/usr/bin/python

import os


def get_entries_and_filenames_from_cc3_file(filename):
    if not os.path.isfile(filename):
        raise Exception("%s doesn't seem to be a file." % filename)

    ccdata = get_cc3_data(filename)
    output = dict()

    for datum in ccdata:
        if datum['menu'] == '    ':
            output[datum['file']] = datum['desc']
    return output


def get_menufile_data(filename):
    with open(filename, 'r') as fh:
        menulist = fh.readlines()

    output = dict()

    for line in menulist:
        cc3file = line[0:8].strip()
        cc3menutext = line[8:].strip()
        output[cc3file] = cc3menutext
    return output


def get_cc3_data(filename):
    if not os.path.isfile(filename):
        raise Exception("%s doesn't seem to be a file." % filename)

    output = list()

    with open(filename, 'rb') as fh:
        while True:
            # 32 byte records
            entry = fh.read(20)
            file8 = fh.read(8)
            menu = fh.read(4)

            if entry == '':
                break

            rec = dict()
            rec['desc'] = entry.strip()
            rec['file'] = file8.strip()
            rec['menu'] = menu.strip()

            output.append(rec)
    return output
