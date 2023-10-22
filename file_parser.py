#!/usr/bin/env python3

import sys
import os
import struct

tool_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(tool_dir)

import checksum


class FileParser:
    def read_binary_file_into_unsigned_ints(self, filename):
        uint_8s = []
        with open(filename, 'rb') as fh:
            ch = fh.read(1)
            while ch != b'':
                uint_8s.append(struct.unpack('B', ch)[0])
                ch = fh.read(1)
        return uint_8s

    def calc_crcs_for_file(self, filename):
        if os.path.isfile(filename) is False:
            raise Exception(f"{filename} doesn't seem to be a file")

        rom_file_len = os.path.getsize(filename)
        uint_8s = self.read_binary_file_into_unsigned_ints(filename)

        # determine file type via the 3-byte header
        if uint_8s[0] == 0x4C and uint_8s[1] == 0x54 and uint_8s[2] == 0x4F:
            data, warnings = self.parse_luigi(uint_8s)

        elif uint_8s[1] == (0xFF ^ uint_8s[2]):
            data, warnings = self.parse_rom(uint_8s)

        else:
            data, warnings = self.parse_bin(uint_8s)

        data['file_length'] = rom_file_len
        return (data, warnings)

    def calc_md5s_for_file(self, filename):
        # hmmm...  apparently these used to be different?
        return self.calc_crcs_for_file(filename)

    def parse_bin(self, uint_8s):
        # bin is just a data blob
        data = {}
        warnings = []
        data['rom_file_type'] = 'bin'
        data['bin_crc32'] = f"{checksum.crc32(uint_8s):08X}"
        data['bin_md5'] = checksum.md5_hex_str(uint_8s)
        return (data, warnings)

    def parse_luigi(self, uint_8s):
        raise Exception("Must be implemented in child class.")
        return

    def parse_rom(self, uint_8s):
        raise Exception("Must be implemented in child class.")
        return
