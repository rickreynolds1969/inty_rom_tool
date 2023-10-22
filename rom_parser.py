#!/usr/bin/env python3

import sys
import os

tool_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(tool_dir)

import checksum
from file_parser import FileParser


class RomParser(FileParser):
    def parse_rom(self, uint_8s):
        # Here's a short description of the ROM format's overall structure:
        #
        # 1.  Header  (3 bytes)
        #     a.  Signature / auto-baud byte (0xA8 for Intellicart, 0x41 for CC3 if
        #         I recall).
        #     b.  Byte indicating # of ROM segments that follow the header.
        #     c.  Byte containing 2s complement of 1(b)
        #
        # 2.  A list of ROM segments.  Each segment consists of:
        #     a.  Upper 8 bits of starting address in Intellicart address space
        #     b.  Upper 8 bits of ending address in Intellicart address space
        #     c.  16-bit data for range implied by 2(a) and 2(b), sent in
        #         big-endian order
        #     d.  CRC-16 for all of 2(a), 2(b) and 2(c)
        #
        # 3.  Attribute table (16 bytes).  Each byte contains 2 nibbles describing
        #     the Read, Write, Narrow (8-bit), and Bankswitch flags for all 32 2K
        #     segments of memory in Intellivision address space.
        #
        # 4.  Fine Address table (32 bytes).  Each byte contains 2 nibbles
        #     indicating the starting and ending 256-word segment that's
        #     valid within each 2K segment.
        #
        # 5.  Table checksum (2 bytes).  CRC-16 of items 3 and 4.

        data = {}
        warnings = []
        data['rom_file_type'] = 'rom'

        # I don't do anything with this data, but I grab it anyway
        flag = uint_8s[0]
        if flag == 0xa8:
            data['icart_or_cc3'] = 'icart'
        elif flag == 0x41 or flag == 0x61:
            data['icart_or_cc3'] = 'cc3'

        data['num_data_segments'] = uint_8s[1]

        # read the rom segments (3)
        ofs = 3
        rom_data = []
        data_crc16s = []
        for i in range(0, uint_8s[1]):
            start_of_this_block = ofs
            lo = uint_8s[ofs] << 8
            ofs += 1
            hi = (uint_8s[ofs] << 8) + 0x100
            ofs += 1

            if hi < lo:
                warnings.append('Bad rom segment defined (hi addr below lo)')

            #
            # get this rom segment
            #

            # need to preallocate indices
            if hi > len(rom_data) - 1:
                fill_lower = len(rom_data)
                fill_higher = hi
                for k in range(fill_lower, fill_higher):
                    rom_data.append(None)

            for j in range(lo, hi):
                rom_data[j] = (uint_8s[ofs] << 8) | (uint_8s[ofs + 1] & 0xFF)
                ofs += 2

            # check the CRC-16 (for grins?)
            crc_expect = (uint_8s[ofs] << 8) | (uint_8s[ofs + 1] & 0xFF)
            crc_actual = checksum.crc16(uint_8s, start_of_this_block, 2 * (hi - lo) + 2)

            data_crc16s.append(crc_expect)

            if crc_expect != crc_actual:
                warnings.append("Block found whose CRC entry doesn't match the CRC of the actual data: CRC in "
                                "rom=%x, CRC calculated=%x" % (crc_expect, crc_actual))
            ofs += 2

        data['rom_data_crc16s'] = ','.join(map(lambda x: "%04X" % x, data_crc16s))

        # read the attribute & fine address tables (3 & 4)
        start_of_attribute_table = ofs
        attr = []
        for i in range(0, 48):
            attr.append(uint_8s[ofs])
            ofs += 1

        # check the CRC of the previous tables (5)
        crc_expect = (uint_8s[ofs] << 8) | (uint_8s[ofs + 1] & 0xFF)
        crc_actual = checksum.crc16(uint_8s, start_of_attribute_table, 48)

        data['rom_attr_crc16'] = "%04X" % crc_expect

        if crc_expect != crc_actual:
            warnings.append("Attribute and fine address tables' CRC entry doesn't match the CRC of the actual data: "
                            "CRC in rom=%x, CRC calculated=%x" % (crc_expect, crc_actual))

        ofs += 2

        data['processed_bytes'] = ofs

        # print("rlrDEBUG rom_data=")
        # for i in range(0, len(rom_data)):
        #     sys.stdout.write("%04d " % rom_data[i])
        #     if i % 20 == 0:
        #         sys.stdout.write("\n")
        # sys.stdout.write("\n")

        data['rom_data_md5'] = checksum.md5_hex_str(rom_data)
        data['rom_attr_md5'] = checksum.md5_hex_str(attr)
        return (data, warnings)
