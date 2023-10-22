#!/usr/bin/env python3

import sys
import os

tool_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(tool_dir)

import checksum
from file_parser import FileParser


class LuigiParser(FileParser):
    def parse_luigi(self, uint_8s):
        # Here's a short description of the LUIGI format's overall structure:
        #
        # 1.  Header (32 bytes)
        #     --------+---------------------------------
        #      Bytes  | Details
        #     --------+---------------------------------
        #       0 2   | Signature: 0x4C 0x54 0x4F
        #        3    | version - should be 1
        #       4 19  | 128 bit vector of feature compatibility flags
        #      20 27  | Unique ID
        #      28 30  | all 0
        #       31    | header CRC32/4 checksum
        #     --------+---------------------------------
        #
        # 2.  blocks with headers
        #     --------+------------------------------
        #      Bytes  | Details
        #     --------+------------------------------
        #        0    | Data block type
        #       1 2   | Payload length
        #        3    | Header checksum (DOWCRC)
        #       4 7   | CRC32/4 checksum for payload
        #       8 ?   | END Payload data
        #     --------+------------------------------

        data = {}
        warnings = []
        luigi_meta = {}

        # confirm that this is a luigi rom
        if uint_8s[0] != 0x4C or uint_8s[1] != 0x54 or uint_8s[2] != 0x4F:
            raise Exception("parse_luigi: not a luigi file - header signature is wrong")

        data['rom_file_type'] = 'luigi'

        # check the version in the file header
        ofs = 3
        if uint_8s[ofs] != 1:
            raise Exception(f"This is a version {uint_8s[ofs]} luigi file, not supported by this tool")

        # grab data from the compatibility vector

        # compatibility flags
        #
        # -----+--------+----------------------------------------------------------------------------
        #  ofs |  Bits  | Description
        # -----+--------+----------------------------------------------------------------------------
        #      |  0 1   | Intellivoice compatibility
        #   4  |  2 3   | ECS compatibility
        #      |  4 5   | Intellivision 2 compatibility
        #      |  6 7   | Keyboard Component compatibility
        #  --- |  ---   | ---
        #      |  8 9   | Compatibility field version number
        #   5  | 10 11  | Tutorvision compatibility
        #      | 12 15  | Reserved for flags based on bits 8-9
        #  --- |  ---   | ---
        #      | 16 17  | JLP accelerator enable
        #  6 7 | 18 21  | Reserved for JLP related flags
        #      | 22 31  | JLP flash save game size (in sectors)
        #  --- |  ---   | ---
        #      |   32   | Enable Locutus' memory mapper at $1000-$14FF
        # 8 11 | 33 62  | Reserved
        #      |   63   | Explicit vs implicit features flag
        #  --- |  ---   | ---
        # 12 19| 64 127 | Reserved
        # -----+--------+----------------------------------------------------------------------------
        #
        # for the various 2-byte feature flags above, their meanings are as follows
        #
        # ------+--------------+---------------------------------------------------------------------
        #  Bits | Meaning      | Details
        # ------+--------------+---------------------------------------------------------------------
        #   00  | Incompatible | The device must not be present when using this program.
        #   01  | Tolerates    | Program operates correctly in the presence of this hardware.
        #   10  | Enhanced     | Program provides extra functionality when this hardware is present.
        #   11  | Requires     | Program requires this hardware to operate correctly.
        # ------+--------------+---------------------------------------------------------------------

        # quick map of the 8 bytes in the compatibility features portion of the header. Each chunk shows one byte
        # with bit numbers in proper position under the byte offset within the header

        #    4        5         6       7
        #
        #          111111   22221111 33222222
        # 76543210 54321098 32109876 10987654

        #    8        9        10       11
        #
        # 33333333 44444444 55555544 66665555
        # 98765432 76543210 54321098 32109876

        compats = ('Incompatible', 'Tolerates', 'Enhanced', 'Requires')

        ofs = 4
        luigi_meta['keyb_compat'] = compats[(uint_8s[ofs] >> 6) & 0x03]
        luigi_meta['inty2_compat'] = compats[(uint_8s[ofs] >> 4) & 0x03]
        luigi_meta['ecs_compat'] = compats[(uint_8s[ofs] >> 2) & 0x03]
        luigi_meta['ivoice_compat'] = compats[uint_8s[ofs] & 0x03]

        ofs = 5
        tv_compat_ver = uint_8s[ofs] & 0x03
        if tv_compat_ver >= 0x01:
            luigi_meta['tv_compat'] = compats[(uint_8s[ofs] >> 2) & 0x03]

        # for the JLP accelerator enable
        #
        # ------+--------------+---------------------------------------------------------------------
        #  Bits | Meaning      | Details
        # ------+--------------+---------------------------------------------------------------------
        #   00  | Disabled     | JLP acceleration is completely off
        #   01  | Accel On     | JLP acceleration and RAM enabled on reset; no Flash
        #   10  | Accel Off /  | JLP acceleration and RAM available but disabled on reset,
        #       | Flash Enable |   Flash memory available
        #   11  | Accel On /   | JLP acceleration and RAM enabled on reset,
        #       | Flash Enable |   Flash memory available
        # ------+--------------+---------------------------------------------------------------------

        ofs = 6
        jlps = ('Disabled', 'Accel On', 'Accel Off/Flash', 'Accel On/Flash')
        luigi_meta['jlp_accel'] = jlps[uint_8s[ofs] & 0x03]

        ofs = 11
        implicits = ('Features Implicit', 'Features Explicit')
        luigi_meta['explicit_implicit'] = implicits[(uint_8s[ofs] >> 7) & 0x01]

        # advance past the header
        ofs = 32

        luigi_meta_defs = ['name', 'short_name', 'author', 'vendor', 'release_date', 'license', 'description', 'misc',
                           'game_art_by', 'music_composer', 'sfx_by', 'voice_actor', 'documentation_writer',
                           'concept_creator', 'box_artist', 'more']

        # start looping over the data blocks
        block_crcs = []
        while ofs < len(uint_8s):
            # print(f"start of block ofs={ofs}")
            block_type = uint_8s[ofs]
            # print(f"block type={block_type}")

            #
            # block header structure
            #

            # -------+--------------------+---------------------------------------------------------------------
            #  Bytes | Field              | Details
            # -------+--------------------+---------------------------------------------------------------------
            #   0    | Block Type         | Single byte field indicating the block type.
            #   1 2  | Payload Length     | Length of the payload associated with this block: 0 .. 65535 bytes.
            #   3    | Header Checksum    | DOWCRC checksum over { Block Type, Payload Length }.
            #   4 7  | Payload Checksum   | CRC32/4 checksum for the payload. (Details below.)
            #   8 ?  | Payload (optional) | Optional payload data associated with this block.
            # -------+--------------------+---------------------------------------------------------------------

            try:
                # NOTE: Little Endian calculations here
                block_len = (uint_8s[ofs + 2] << 8) + uint_8s[ofs + 1]
                # block_header_crc = uint_8s[ofs+3]
                block_crc = ((uint_8s[ofs + 7] << 24) + (uint_8s[ofs + 6] << 16) + (uint_8s[ofs + 5] << 8) +
                             uint_8s[ofs + 4])

                # move pointer past the block header
                ofs += 8

                if block_type != 0x00:
                    # deal with block CRCs
                    calc_crc = checksum.crc32(uint_8s, ofs, block_len)
                    block_crcs.append(block_crc)

                    if calc_crc != block_crc:
                        warnings.append(f"Data block CRC doesn't match calculated CRC: In block={block_crc} "
                                        f"Calculated={calc_crc}")

            except Exception as errmsg:
                raise Exception(f"Couldn't parse this block's header: {str(errmsg)}")

            if block_type == 0x00:
                # encrypted data block - also implies the rest of the file is encrypted
                # just calc a crc for the whole rest of the file

                # first 16 bytes are the DRUID, so pull that for reporting
                luigi_meta['druid'] = 0
                for i in range(ofs + 15, ofs - 1, -1):
                    luigi_meta['druid'] <<= 8
                    luigi_meta['druid'] += uint_8s[i]

                luigi_meta['druid_hex'] = f"{luigi_meta['druid']:032X}"
                luigi_meta['encrypted'] = True

                calc_crc = checksum.crc32(uint_8s, ofs, len(uint_8s) - ofs)
                ofs = len(uint_8s)

            elif block_type == 0x01:
                # memory mapping, permissions, and page flipping tables
                raise Exception(f"Hit a block type of {block_type}, I don't have any info on how to parse this.")

            elif block_type == 0x02:
                # unencrypted data block
                raise Exception(f"Hit a block type of {block_type}, I don't have any info on how to parse this.")

            elif block_type == 0x03:
                # metadata block
                lofs = ofs
                inner_block_len = 0

                while lofs < ofs + block_len:
                    tag = uint_8s[lofs]
                    leng = uint_8s[lofs + 1]
                    lofs += 2
                    inner_block_len += 2

                    # tag 4 is the year - numeric
                    if tag != 4:
                        data_str = ""
                        for i in range(lofs, lofs + leng):
                            data_str += chr(uint_8s[i])
                    else:
                        data_str = 1900 + int(uint_8s[lofs:lofs + leng][0])

                    tag_str = luigi_meta_defs[int(tag)]

                    # print(f"{tag_str} -> {data_str}")

                    if tag_str in luigi_meta.keys():
                        luigi_meta[tag_str] += "\n"
                        luigi_meta[tag_str] += data_str
                    else:
                        luigi_meta[tag_str] = data_str

                    lofs += leng
                    inner_block_len += leng

                ofs += block_len

            elif block_type == 0xFF:
                # this signals end of data - ignore anything else in the file
                ofs = len(uint_8s)

            else:
                raise Exception(f"Hit a block type of {block_type}, I don't have any info on how to parse this.")

            # print(f"end of block ofs={ofs}")

        data['luigi_crc32s'] = ','.join(map(lambda x: f"{x:08X}", block_crcs))
        if luigi_meta is not None:
            data['luigi_meta'] = luigi_meta
        return (data, warnings)
