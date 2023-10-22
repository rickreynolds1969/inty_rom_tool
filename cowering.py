#!/usr/bin/python

import re


def read_cowering_data(filename):
    output = dict()
    with open(filename, 'r') as fh:
        in_game = False

        for line in fh.readlines():
            if line[:4] == 'game':
                in_game = True
                continue

            if in_game is True:
                if line == ')':
                    in_game = False
                    continue

            p = re.compile('.*description "(.*)"')
            matcher = p.search(line)
            if matcher is not None:
                good_name = matcher.group(1)

            p = re.compile('.*rom \( name.*size.*crc ([0-9a-f]+) \)', re.IGNORECASE)
            matcher = p.search(line)
            if matcher is not None:
                crc = matcher.group(1).lower()

                while len(crc) < 8:
                    crc = "0" + crc

                if good_name == '':
                    print(f"WARN: good_name is blank: crc={crc}")

                output[crc] = good_name

                good_name = ''
                crc = 0

    return output
