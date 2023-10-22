#!/usr/local/bin/python3

import sys
import os
import struct
import re
import json
import argparse
import subprocess
import string

tool_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(tool_dir)

import Cowering
import Shell
import CC3
import Checksum

CRLF = "%s%s" % (chr(13), chr(10))

if sys.platform == "darwin":
    syswart = "macos"
else:
    syswart = "linux"

bin2rom = "%s/bin2rom_%s" % (tool_dir, syswart)
rom2bin = "%s/rom2bin_%s" % (tool_dir, syswart)
bin2luigi = "%s/bin2luigi_%s" % (tool_dir, syswart)
luigi2bin = "%s/luigi2bin_%s" % (tool_dir, syswart)

allowed_romfile_extensions = ('ROM', 'BIN', 'LUIGI')

class Inty:
    def __init__(self):
        self.inty_tool_dir = tool_dir
        self.cowering_file = '%s/inty_203.dat' % tool_dir
        self.inty_data_file = '%s/py_data.dat' % tool_dir
        self.roms_repository = '%s/roms' % tool_dir
        self.boxart_repository = '%s/boxart' % tool_dir
        self.manuals_repository = '%s/cc3_manuals' % tool_dir
        self.kbdhackfile_dir = '%s/kbdhackfiles' % tool_dir
        self.laptop_default_kbdhackfile = 'basicnoecs'
        self.laptop_default_ecs_kbdhackfile = 'basic'
        self.frinkiac7_default_kbdhackfile = 'basic'
        self.temp_dir = '/tmp'
        self.db_delimiter = '#--- 8< cut here 8< ---'
        self.fields_order = ('id', 'name', 'flashback_name', 'good_name',
                             'rom_data_md5', 'rom_attr_md5', 'bin_md5',
                             'bin_crc32', 'cowering_crc32', 'rom_data_crc16s',
                             'rom_attr_crc16', 'luigi_crc32s', 'cc3_desc',
                             'cc3_filename', 'tags', 'variant_of', 'author',
                             'year', 'options', 'kbdhackfile', 'cfg_file',
                             'comments')
        self.dirty = False
        self.number_of_backups_to_keep = 9

        self.db, self.db_header = self.read_inty_data_file(self.inty_data_file)
        self.cowering_data = Cowering.read_cowering_data(self.cowering_file)
        return

    def __del__(self):
        if self.dirty is True:
            self.write_inty_data_file()
        return

    def calc_crcs_for_file(self, filename):
        if os.path.isfile(filename) is False:
            raise Exception("%s doesn't seem to be a file" % filename)

        uint_8s = []
        rom_file_len = os.path.getsize(filename)

        with open(filename, 'rb') as fh:
            ch = fh.read(1)
            while ch != b'':
                uint_8s.append(struct.unpack('B', ch)[0])
                ch = fh.read(1)

        # determine file type via the 3-byte header
        if uint_8s[0] == 0x4C and uint_8s[1] == 0x54 and uint_8s[2] == 0x4F:
            data, warnings = self.parse_luigi(uint_8s)

        elif uint_8s[1] == (0xFF ^ uint_8s[2]):
            data, warnings = self.parse_rom(uint_8s)

        else:
            data, warnings = self.parse_bin(uint_8s)

        data['file_length'] = rom_file_len
        return (data, warnings)

    def calc_md5_for_file(self, filename):
        #raise Exception("Call to calc_md5_for_file")

        if os.path.isfile(filename) is False:
            raise Exception("%s doesn't seem to be a file" % filename)

        uint_8s = []
        rom_file_len = os.path.getsize(filename)

        with open(filename, 'rb') as fh:
            ch = fh.read(1)
            while ch != b'':
                uint_8s.append(struct.unpack('B', ch)[0])
                ch = fh.read(1)

        # determine file type via the 3-byte header
        if uint_8s[0] == 0x4C and uint_8s[1] == 0x54 and uint_8s[2] == 0x4F:
            data, warnings = self.parse_luigi(uint_8s)

        elif uint_8s[1] == (0xFF ^ uint_8s[2]):
            data, warnings = self.parse_rom(uint_8s)

        else:
            data, warnings = self.parse_bin(uint_8s)

        data['file_length'] = rom_file_len
        return (data, warnings)

    def parse_bin(self, uint_8s):
        # bin is just a data blob
        data = {}
        warnings = []
        data['rom_file_type'] = 'bin'
        data['bin_crc32'] = "%08X" % Checksum.crc32(uint_8s)
        data['bin_md5'] = Checksum.md5_hex_str(uint_8s)
        return (data, warnings)

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
        data['rom_file_type'] = 'luigi'
        luigi_meta = {}

        # check the version in the file header
        ofs = 3
        if uint_8s[ofs] != 1:
            raise Exception("This is a version %d luigi file, not supported by this tool" % uint_8s[ofs])

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

        compats = ('Incompatible', 'Tolerates', 'Enhanced', 'Requires')

        ofs = 4
        luigi_meta['ivoice_compat'] = compats[(uint_8s[ofs] >> 6) & 0x03]
        luigi_meta['ecs_compat'] = compats[(uint_8s[ofs] >> 4) & 0x03]
        luigi_meta['inty2_compat'] = compats[(uint_8s[ofs] >> 2) & 0x03]
        luigi_meta['keyb_compat'] = compats[uint_8s[ofs] & 0x03]

        ofs = 5
        tv_compat_ver = ((uint_8s[ofs] >> 6) & 0x03)
        if tv_compat_ver >= 0x01:
            luigi_meta['tv_compat'] = compats[(uint_8s[ofs] >> 4) & 0x03]

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
        #       | Flash Enable |   FLash memory available
        # ------+--------------+---------------------------------------------------------------------

        jlps = ('Disabled', 'Accel On', 'Accel Off/Flash', 'Accel On/Flash')
        ofs = 6
        luigi_meta['jlp_accel'] = jlps[(uint_8s[ofs] >> 6) & 0x03]

        implicits = ('Features Implicit', 'Features Explicit')
        ofs = 11
        luigi_meta['explicit_implicit'] = implicits[uint_8s[ofs] & 0x01]

        # advance past the header
        ofs = 32

        luigi_meta_defs = ['name', 'short_name', 'author', 'vendor',
                           'release_date', 'license', 'description', 'misc',
                           'game_art_by', 'music_composer', 'sfx_by',
                           'voice_actor', 'documentation_writer',
                           'concept_creator', 'box_artist', 'more']

        # start looping over the data blocks
        block_crcs = []
        while ofs < len(uint_8s):
            # print("start of block ofs=%d" % ofs)
            block_type = uint_8s[ofs]
            # print("block type=%d" % block_type)

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
                block_len = (uint_8s[ofs+2] << 8) + uint_8s[ofs+1]
                # print("block_len=%d" % block_len)
                block_header_crc = uint_8s[ofs+3]
                block_crc = (uint_8s[ofs+7] << 24) + (uint_8s[ofs+6] << 16) + (uint_8s[ofs+5] << 8) + uint_8s[ofs+4]

                # move pointer past the block header
                ofs += 8
                # print("start of payload ofs=%d" % ofs)

                if block_type != 0x00:
                    # deal with block CRCs
                    calc_crc = Checksum.crc32(uint_8s, ofs, block_len)
                    block_crcs.append(block_crc)

                    if calc_crc != block_crc:
                        warnings.append("Data block CRC doesn't matched calculated CRC: %s %s" % (block_crc, calc_crc))

            except Exception as errmsg:
                raise Exception("Couldn't parse this block's header: %s" % errmsg)

            if block_type == 0x00:
                # encrypted data block - also implies the rest of the file is encrypted
                # just calc a crc for the whole rest of the file

                # first 16 bytes are the DRUID, so pull that for reporting
                luigi_meta['druid'] = 0
                for i in range(ofs+15, ofs-1, -1):
                    luigi_meta['druid'] <<= 8
                    luigi_meta['druid'] += uint_8s[i]

                luigi_meta['druid_hex'] = "%032X" % luigi_meta['druid']
                luigi_meta['encrypted'] = True

                calc_crc = Checksum.crc32(uint_8s, ofs, len(uint_8s) - ofs)
                ofs = len(uint_8s)

            elif block_type == 0x01:
                # memory mapping, permissions, and page flipping tables
                raise Exception("Hit a block type of %d, I don't have any info on how to parse this." % block_type)

            elif block_type == 0x02:
                # unencrypted data block
                raise Exception("Hit a block type of %d, I don't have any info on how to parse this." % block_type)

            elif block_type == 0x03:
                # metadata block
                luigi_meta = {}
                lofs = ofs
                inner_block_len = 0

                while lofs < ofs + block_len:
                    tag = uint_8s[lofs]
                    leng = uint_8s[lofs+1]
                    lofs += 2
                    inner_block_len += 2

                    # tag 4 is the year - numeric
                    if tag != 4:
                        data_str = ""
                        for i in range(lofs, lofs+leng):
                            data_str += chr(uint_8s[i])
                    else:
                        data_str = 1900 + int(uint_8s[lofs:lofs+leng][0])

                    tag_str = luigi_meta_defs[int(tag)]

                    # print("%s -> %s" % (tag_str, data_str))

                    if tag_str in luigi_meta.keys():
                        luigi_meta[tag_str] += "\n%s" % data_str
                    else:
                        luigi_meta[tag_str] = data_str

                    lofs += leng
                    inner_block_len += leng

                ofs += block_len

            elif block_type == 0xFF:
                # this signals end of data - ignore anything else in the file
                ofs = len(uint_8s)

            else:
                raise Exception("Hit a block type of %d, I don't have any info on how to parse this." % block_type)

            # print("end of block ofs=%d" % ofs)

        data['luigi_crc32s'] = ','.join(map(lambda x: "%08X" % x, block_crcs))
        if luigi_meta is not None:
            data['luigi_meta'] = luigi_meta
        return (data, warnings)

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
                rom_data[j] = (uint_8s[ofs] << 8) | (uint_8s[ofs+1] & 0xFF)
                ofs += 2

            # check the CRC-16 (for grins?)
            crc_expect = (uint_8s[ofs] << 8) | (uint_8s[ofs+1] & 0xFF)
            crc_actual = Checksum.crc16(uint_8s, start_of_this_block, 2 * (hi - lo) + 2)

            data_crc16s.append(crc_expect)

            if crc_expect != crc_actual:
                warnings.append("Block found whose CRC entry doesn't match the CRC of the actual data: CRC in rom=%x, CRC calculated=%x" % (crc_expect, crc_actual))

            ofs += 2

        data['rom_data_crc16s'] = ','.join(map(lambda x: "%04X" % x, data_crc16s))

        # read the attribute & fine address tables (3 & 4)
        start_of_attribute_table = ofs
        attr = []
        for i in range(0, 48):
            attr.append(uint_8s[ofs])
            ofs += 1

        # check the CRC of the previous tables (5)
        crc_expect = (uint_8s[ofs] << 8) | (uint_8s[ofs+1] & 0xFF)
        crc_actual = Checksum.crc16(uint_8s, start_of_attribute_table, 48)

        data['rom_attr_crc16'] = "%04X" % crc_expect

        if crc_expect != crc_actual:
            warnings.append("Attribute and fine address tables' CRC entry doesn't match the CRC of the actual data: CRC in rom=%x, CRC calculated=%x" % (crc_expect, crc_actual))

        ofs += 2

        data['processed_bytes'] = ofs

        # print("rlrDEBUG rom_data=")
        # for i in range(0, len(rom_data)):
        #     sys.stdout.write("%04d " % rom_data[i])
        #     if i % 20 == 0:
        #         sys.stdout.write("\n")
        # sys.stdout.write("\n")

        data['rom_data_md5'] = Checksum.md5_hex_str(rom_data)
        data['rom_attr_md5'] = Checksum.md5_hex_str(attr)
        return (data, warnings)

    def set_dirty(self):
        self.dirty = True
        return

    def get_db(self):
        return self.db

    def get_laptop_default_kbdhackfile(self):
        return self.laptop_default_kbdhackfile

    def get_roms_repository(self):
        return self.roms_repository

    def get_kbdhackfile_dir(self):
        return self.kbdhackfile_dir

    def get_fields_order(self):
        return self.fields_order

    def get_laptop_default_ecs_kbdhackfile(self):
        return self.laptop_default_ecs_kbdhackfile

    def get_boxart_repository(self):
        return self.boxart_repository

    def get_cowering_data(self):
        return self.cowering_data

    def get_temp_dir(self):
        return self.temp_dir

    def get_number_of_records(self):
        return len(self.db)

    def get_record_from_name(self, name):
        return self.get_record_from_FIELD('name', name)

    def get_record_from_goodname(self, name):
        return self.get_record_from_FIELD('good_name', name)

    def get_record_from_cc3filename(self, name, ext=None):
        fname = name
        if ext is not None:
            fname = "%s.%s" % (name, ext)
        return self.get_record_from_FIELD('cc3_filename', fname)

    def get_record_from_rom_md5s(self, datamd5, attrmd5):
        query = {'rom_data_md5' : datamd5,
                 'rom_attr_md5' : attrmd5}
        return self.get_record_from_FIELDS(query)

    def get_record_from_rom_crcs(self, datacrc, attrcrc):
        query = {'rom_data_crc16s' : datacrc,
                 'rom_attr_crc16' : attrcrc}
        return self.get_record_from_FIELDS(query)

    def get_record_from_bin_md5(self, name):
        return self.get_record_from_FIELD('bin_md5', name)

    def get_record_from_bin_crc32(self, name):
        return self.get_record_from_FIELD('bin_crc32', name)

    def get_record_from_luigi_crc32s(self, crc_list):
        query = {'luigi_crc32s' : crc_list}
        return self.get_record_from_FIELDS(query)

    def get_record_from_cowering_crc32(self, name):
        return self.get_record_from_FIELD('cowering_crc32', name)

    def get_record_from_id(self, name):
        return self.get_record_from_FIELD('id', name)

    def get_all_records_with_cc3desc(self):
        recs = []

        for rec in self.db:
            try:
                if rec['cc3_desc'] is not None:
                    recs.append(rec)
            except:
                pass
        return recs

    def get_all_records_from_tag(self, tag):
        recs = []

        for rec in self.db:
            try:
                tags = rec['tags'].split(',')
                if tag in tags:
                    recs.append(rec)
            except:
                pass
        return recs

    def get_all_tags(self):
        all_tags = set()
        for rom in self.db:
            try:
                tags = rom['tags'].split(',')
                all_tags.update(tags)
            except:
                pass

        all_tags_list = sorted(list(all_tags))
        return list(all_tags_list)

    def dump_game_opts_db_for_emulator(self, outfile):
        outdb = {}
        for rec in self.db:
            nrec = {'voice': False,
                    'ecs': False,
                    'jlp': False,
                    'tutorvision': False}

            for okey in nrec.keys():
                if okey in str(rec['options']).lower():
                    nrec[okey] = True
            if rec['cc3_filename'] is not None:
                outdb[rec['cc3_filename'].upper()] = nrec

        with open(outfile, 'w') as fh:
            fh.write(json.dumps(outdb, indent=4, sort_keys=True))
        return

    def get_all_ids(self, field=None):
        sorted_db = self.db[:]

        if field is not None:
            sorted_db = sorted(self.db, key=lambda x: x[field])

        ids = []
        for rom in sorted_db:
            ids.append(rom['id'])
        return ids

    def get_record_from_FIELD(self, field, value):
        if field == 'cc3_filename':
            value = value.lower()

        for rec in self.db:
            found = False

            if ',' in value:
                # this is a list comparison
                values_list = sorted(value.split(','))

                if ',' not in rec[field]:
                    continue

                rec_values_list = sorted(rec[field].split(','))

                if len(rec_values_list) != len(values_list):
                    continue

                found = True
                for i in range(0, len(values_list)):
                    if values_list[i] != rec_values_list[i]:
                        found = False
                        break

            else:
                # simple scalar value
                if rec[field] == value:
                    found = True

            if found is True:
                return rec
        return None

    def get_record_from_FIELDS(self, query):
        if type(query) is dict:
            fields_list = query.keys()
        else:
            raise Exception("Not implemented: query is type %s" % type(query))

        for rec in self.db:
            found = True

            for field in fields_list:
                if field not in rec.keys():
                    found = False
                    break

                if rec[field] is None or len(rec[field]) == 0:
                    found = False
                    break

                value = query[field]

                case_insensitive_list = (
                    'cc3_filename', 'rom_data_md5', 'rom_attr_md5', 'bin_md5',
                    'bin_crc32', 'cowering_crc32', 'rom_data_crc16s',
                    'rom_attr_crc16', 'luigi_crc32s')

                if field in case_insensitive_list:
                    value = value.lower()

                if ',' in value:
                    # this is a list comparison
                    values_list = sorted(value.split(','))

                    if ',' not in rec[field]:
                        found = False
                        break

                    rec_values_list = sorted(rec[field].split(','))

                    if len(rec_values_list) != len(values_list):
                        found = False
                        break

                    for i in range(0, len(values_list)):
                        if values_list[i] != rec_values_list[i]:
                            found = False
                            break

                else:
                    # simple scalar value
                    if rec[field] != value:
                        found = False
                        break


            if found is True:
                return rec
        return None

    def get_record_from_wash_data(self, wash):
        if wash['rom_file_type'] == 'rom':
            rom_crc = wash['romcrcdata']
            rec = self.get_record_from_rom_crcs(rom_crc['rom_data_crc16s'], rom_crc['rom_attr_crc16'])
            if rec is not None:
                return (rec, 'ROM CRC16')

            bin_crc = wash['bincrcdata']
            rec = self.get_record_from_bin_crc32(bin_crc['bin_crc32'])
            if rec is not None:
                return (rec, 'BIN CRC32')

        elif wash['rom_file_type'] == 'luigi':
            luigi_crc = wash['luigicrcdata']
            rec = self.get_record_from_luigi_crc32s(luigi_crc['luigi_crc32s'])
            if rec is not None:
                return (rec, 'LUIGI CRC32')

        elif wash['rom_file_type'] == 'bin':
            bin_crc = wash['bincrcdata']
            rec = self.get_record_from_bin_crc32(bin_crc['bin_crc32'])
            if rec is not None:
                return (rec, 'BIN CRC32')

            rec = self.get_record_from_cowering_crc32(wash['bin_cowering_crc32'])
            if rec is not None:
                return (rec, 'COWERING CRC32')

        else:
            raise Exception("Bad rom file type: %s" % wash['rom_file_type'])
        return (None, 'NOT FOUND')

    def validate_record(self, rec):
        # this method is designed to be called after a user edit of a record

        statuses = []

        # check 1: ID
        if 'id' not in rec.keys():
            statuses.append('no ID in record')
        elif rec['id'] is None:
            statuses.append('no ID in record')
        else:
            all_ids = self.get_all_ids()
            if rec['id'] in all_ids:
                statuses.append('ID in DB')

        # check 2: ROM filename
        if rec['cc3_filename'] is not None:
            if "." not in rec['cc3_filename']:
                statuses.append("ROM filename doesn't have an extension!")

            romfile = "%s/%s" % (self.roms_repository, rec['cc3_filename'].upper())

            if os.path.isfile(romfile):
                statuses.append('ROM in repository')
            else:
                statuses.append('no ROM in repository')

        # check 3: cc3_desc
        if rec['cc3_desc'] is not None:
            if len(rec['cc3_desc']) > 20:
                statuses.append('cc3_desc too long')
        return statuses

    def read_inty_data_file(self, filename):
        db_header = ''
        d = []
        with open(filename, 'r') as fh:
            # first loop is just slurping up the file header - up to the first blank line
            while True:
                line = fh.readline().rstrip()

                if line == "":
                    break

                db_header = "%s%s\n" % (db_header, line)

            # loop over records in the file
            while True:
                rec = self.parse_ascii_record_from_file(fh)
                if rec is not None:
                    d.append(rec)
                else:
                    break
        return (d, db_header)

    def parse_ascii_record(self, filename):
        with open(filename, 'r') as fh:
            rec = self.parse_ascii_record_from_file(fh)
        return rec

    def parse_ascii_record_from_file(self, fh):
        in_multi_line = False
        multi_line_attr = ''
        rec = {}

        blank_reg = re.compile('^\s*$')

        # all fields get created with None as values
        for field in self.fields_order:
            rec[field] = None

        while True:
            line = fh.readline()

            # this should detect EOF
            if not line:
                break

            line = line.strip()

            # keep blank lines in multi-line attrs, but skip otherwise
            if line == '' and in_multi_line is False:
                continue

            if line.startswith(self.db_delimiter) is True:
                break

            if len(line) > 0 and line[0] == '#':
                continue

            # in multi-line attributes, save the entire line while we look for the sentinel
            if in_multi_line is True:
                if line.endswith('_multi_line_end'):
                    in_multi_line = False
                    continue

                rec[multi_line_attr] = "%s%s\n" % (rec[multi_line_attr], line)
                continue

            if line.endswith('_multi_line_begin'):
                in_multi_line = True
                multi_line_attr = line[:-17]
                rec[multi_line_attr] = ""
                continue

            line_parts = line.split('=')

            # NOTE: empty values in the file are missing elements of the record struct
            if len(line_parts) < 2:
                continue

            attr = line_parts[0]
            value = line_parts[1]

            if blank_reg.search(value) is not None:
                continue

            # NOTE: values in the records are all strings - might need/want to change that for checksums, lists, etc?
            rec[attr] = str(value)

        # if this record doesn't have an ID, assume it's empty / the end of the file
        if rec['id'] is None:
            return None
        return rec

    def write_inty_data_file(self):
        inty_data_file = self.inty_data_file

        # rotate old backups
        for i in range(self.number_of_backups_to_keep, 0, -1):
            j = i - 1
            if os.path.isfile("%s.bak.%s" % (inty_data_file, j)):
                os.rename("%s.bak.%s" % (inty_data_file, j), "%s.bak.%s" % (inty_data_file, i))

        # save current file as backup
        if os.path.isfile(inty_data_file):
            os.rename(inty_data_file, "%s.bak.0" % inty_data_file)

        sorted_db = sorted(self.db, key=lambda x: x['id'])
        self.db = sorted_db

        with open(inty_data_file, "w") as fh:
            fh.write(self.db_header)
            fh.write('\n')

            for rom in self.db:
                self.write_ascii_record_to_file(fh, rom)
        self.dirty = False
        return

    def write_ascii_record(self, rom, filename=None):
        if type(rom) is str:
            rom = self.get_record_from_id(rom)

        output = None

        if rom is not None:
            pid = os.getpid()
            outfile = '%s/temprec.%s' % (self.temp_dir, pid)
            with open(outfile, 'w') as fh:
                fh.write("# To cancel edit of record, delete the line containing the ID\n")
                if filename is not None:
                    fh.write("# FILENAME: %s\n" % filename)
                self.write_ascii_record_to_file(fh, rom)

            output = outfile
        return output

    def write_ascii_record_to_file(self, fh, rec):
        # print("rlrDEBUG rec=|%s|" % str(rec))
        for k in self.fields_order:
            if k == 'cc3_desc':
                fh.write('#c3_desc=12345678901234567890\n')
            if k == 'tags':
                fh.write('# possible tags:%s\n' % ','.join(self.get_all_tags()))

            if k not in rec.keys() or rec[k] is None:
                fh.write('%s=\n' % k)
                continue

            # NOTE: due to the above continue, rec[k] must exist and has a value

            if '\n' in rec[k]:
                fh.write('%s_multi_line_begin\n' % k)
                fh.write(rec[k])
                fh.write('%s_multi_line_end\n' % k)
            else:
                fh.write('%s=%s\n' % (k, rec[k]))

        fh.write('\n%s\n\n' % self.db_delimiter)
        return

    def rom_file_exists_in_repository(self, romname):
        return os.path.isfile('%s/%s' % (self.roms_repository, romname))

    def copy_rom_file_to_repository(self, src, dest, force=False):
        if os.path.isfile("%s/%s" % (self.roms_repository, dest)) is False or force is True:
            Shell.exc('cp %s %s/%s' % (src, self.roms_repository, dest))
        else:
            raise Exception("Cannot copy file, target exists.")
        return

    def copy_rom_file_from_repository(self, romfile, force=False):
        if os.path.isfile(romfile) is False or force is True:
            Shell.exc('cp %s/%s .' % (self.roms_repository, romfile))
        else:
            raise Exception("Cannot copy file, target exists.")
        return

    def add_rom(self, rec):
        for dbrec in self.db:
            if dbrec['id'] == rec['id']:
                raise Exception("Cannot add rom, already in the DB")

        self.db.append(rec)
        self.dirty = True
        return

    def recs_intersection(self, rec_set1, rec_set2):
        rec1_ids = set(map(lambda x: x['id'], rec_set1))
        rec2_ids = set(map(lambda x: x['id'], rec_set2))

        inter_set = rec1_ids.intersection(rec2_ids)

        out_recs = []
        for ID in inter_set:
            rec = self.get_record_from_id(ID)
            out_recs.append(rec)
        return out_recs

    def replace_rom(self, new_rec):
        findid = new_rec['id']

        if 'replace_id' in new_rec.keys():
            findid = new_rec['replace_id']
            del new_rec['replace_id']

        rom_index = -1

        for i in range(0, len(self.db)):
            if self.db[i]['id'] == findid:
                rom_index = i
                break

        if rom_index < 0:
            raise Exception("Didn't find record for replacement.  ID:%s" % findid)

        self.db[rom_index] = new_rec
        self.dirty = True
        return

    def add_or_replace_rom(self, new_rec):
        try:
            self.replace_rom(new_rec)
        except:
            self.add_rom(new_rec)
        return

    def wash_rom(self, filename):
        origcrcdata, origwarnings = self.calc_crcs_for_file(filename)

        # TODO: check warnings

        Shell.exc("rm -f %s/xxx.bin %s/xxx.cfg %s/xxx.rom %s/xxx.luigi > /dev/null" %
                  (self.temp_dir, self.temp_dir, self.temp_dir, self.temp_dir))

        filename.replace("'", "\'")
        basename, ext = os.path.splitext(filename)
        cowering_bin_crc = None
        output = {}
        output['rom_file_type'] = origcrcdata['rom_file_type']

        if origcrcdata['rom_file_type'] == 'bin':
            # convert bin to rom to get those CRCs
            Shell.exc("cp '%s' %s/xxx.bin" % (filename, self.temp_dir))
            if os.path.isfile('%s.cfg' % basename):
                Shell.exc("cp '%s.cfg' %s/xxx.cfg" % (basename, self.temp_dir))
            if os.path.isfile('%s.CFG' % basename):
                Shell.exc("cp '%s.CFG' %s/xxx.cfg" % (basename, self.temp_dir))
            Shell.exc("cd %s ; %s xxx.bin > /dev/null" % (self.temp_dir, bin2rom))

            romcrcdata, warnings = self.calc_crcs_for_file('%s/xxx.rom' % self.temp_dir)

            # TODO: check warnings

            output['bin_cowering_crc32'] = "%08X" % Checksum.cowering_crc32_from_file(filename)
            output['bincrcdata'] = origcrcdata
            output['romcrcdata'] = romcrcdata

        elif origcrcdata['rom_file_type'] == 'rom':
            # convert rom to bin to get CRCs
            Shell.exc("cp '%s' %s/xxx.rom" % (filename, self.temp_dir))
            Shell.exc("cd %s ; %s xxx.rom > /dev/null" % (self.temp_dir, rom2bin))

            bincrcdata, warnings = self.calc_crcs_for_file('%s/xxx.bin' % self.temp_dir)

            # TODO: check warnings

            output['bin_cowering_crc32'] = "%08X" % Checksum.cowering_crc32_from_file('%s/xxx.bin' % self.temp_dir)
            output['bincrcdata'] = bincrcdata
            output['romcrcdata'] = origcrcdata

        elif origcrcdata['rom_file_type'] == 'luigi':
            output['luigicrcdata'] = origcrcdata

            try:
               enc = output['luigicrcdata']['luigi_meta']['encrypted']
            except:
               enc = False

            if enc is False:
                Shell.exc("cp '%s' %s/xxx.luigi" % (filename, self.temp_dir))
                Shell.exc("cd %s ; %s xxx.luigi > /dev/null" % (self.temp_dir, luigi2bin))

                bincrcdata, warnings = self.calc_crcs_for_file('%s/xxx.bin' % self.temp_dir)

                # TODO: check warnings

                output['bin_cowering_crc32'] = "%08X" % Checksum.cowering_crc32_from_file('%s/xxx.bin' % self.temp_dir)
                output['bincrcdata'] = bincrcdata

        else:
            raise Exception("romfile parsing came up with invalid rom file type: %s" % origcrcdata['rom_file_type'])
        return output

    def banner(self, msg):
        mesg = ''.join(s for s in msg if s in string.printable)
        banstr = '=' * (len(mesg) + 2)
        print("\n%s\n %s\n%s\n" % (banstr, mesg, banstr))
        return

    def verify_data(self, level=1, menufile=None):
        #
        #  First set of checks: consistency within the DB itself
        #
        self.banner("Checking for repeated game data and repeated ROMs in the DB")

        for rec1 in self.db:
            for rec2 in self.db:
                if rec1 is rec2:
                    continue

                if rec1['name'] is not None and rec2['name'] is not None and rec1['name'] == rec2['name']:
                    print("%s (game name) is in the DB more than once" % rec1['name'])

                if rec1['good_name'] is not None and rec2['good_name'] and rec1['good_name'] == rec2['good_name']:
                    print("%s (good name) is in the DB more than once" % rec1['good_name'])

                if rec1['id'] == rec2['id']:
                    print("%s (id) is in the DB more than once!!!" % rec1['id'])

                if (rec1['bin_md5'] is not None and rec2['bin_md5'] is not None and
                        rec1['bin_md5'] == rec2['bin_md5']):
                    print("%s (bin_md5) is in the DB more than once" % rec1['bin_md5'])

                if (rec1['bin_crc32'] is not None and rec2['bin_crc32'] is not None and
                        rec1['bin_crc32'] == rec2['bin_crc32']):
                    print("%s (bin_crc32) is in the DB more than once" % rec1['bin_crc32'])

                if (rec1['cowering_crc32'] is not None and rec2['cowering_crc32'] is not None and
                        rec1['cowering_crc32'] == rec2['cowering_crc32']):
                    print("%s (cowering_crc32) is in the DB more than once" % rec1['cowering_crc32'])

                if (rec1['cc3_filename'] is not None and rec2['cc3_filename'] is not None and
                        rec1['cc3_filename'] == rec2['cc3_filename']):
                    print("%s (cc3_filename) is in the DB more than once" % rec1['cc3_filename'])

                data_same = False
                attr_same = False
                if (rec1['rom_data_md5'] is not None and rec2['rom_data_md5'] is not None and
                        rec1['rom_data_md5'] == rec2['rom_data_md5']):
                    data_same = True

                if (rec1['rom_attr_md5'] is not None and rec2['rom_attr_md5'] is not None and
                        rec1['rom_attr_md5'] == rec2['rom_attr_md5']):
                    attr_same = True

                if (data_same and attr_same) is True:
                    print("%s and %s are the same ROM image" % (rec1['name'], rec2['name']))

                if level > 1 and data_same is True:
                    print("%s and %s have the same ROM data MD5" % (rec1['name'], rec2['name']))

            #
            # check the md5's on the physical files against the DB
            #

            # NOTE: cowering in the options indicates this record is only here because it is in the cowering data file and does not represent real rom file(s) I own
            if level > 1 and (rec1['options'] is not None and 'cowering' not in rec1['options']):
                romfilename = "%s/%s" % (self.roms_repository, rec1['cc3_filename'].upper())
                if os.path.isfile(romfilename) is False:
                    print("I can't find the rom file %s is referring to." % rec1['id'])

                else:
                    w = self.wash_rom(romfilename)
                    cc3f = rec1['cc3_filename'].upper()

                    if (w['wash']['binmd5data']['bin_md5'] is not None and rec1['bin_md5'] is not None and
                            w['wash']['binmd5data']['bin_md5'] != rec1['bin_md5']):
                        print("The bin MD5 for %s in the DB doesn't match what is in the romfile in the repository (%s)" % (rec1['id'], cc3f))

                    if (w['wash']['crc32'] is not None and rec1['bin_crc32'] is not None and
                            w['wash']['crc32'] != rec1['bin_crc32']):
                        print("The bin CRC32 for %s in the DB doesn't match what is in the romfile in the repository (%s)" % (rec1['id'], cc3f))

                    if (w['wash']['rommd5data']['rom_data_md5'] is not None and rec1['rom_data_md5'] is not None and
                            w['wash']['rommd5data']['rom_data_md5'] != rec1['rom_data_md5']):
                        print("The rom data MD5 for %s in the DB doesn't match what is in the romfile in the repository (%s)" % (rec1['id'], cc3f))

                    if (w['wash']['rommd5data']['rom_attr_md5'] is not None and rec1['rom_attr_md5'] is not None and
                            w['wash']['rommd5data']['rom_attr_md5'] != rec1['rom_attr_md5']):
                        print("The rom attr MD5 for %s in the DB doesn't match what is in the romfile in the repository (%s)" % (rec1['id'], cc3f))

            #
            # other checks
            #
            if rec1['cc3_desc'] is not None and len(rec1['cc3_desc']) > 20:
                print("%s has a CC3 description that is too long." % rec1['id'])

            if rec1['cc3_filename'] is not None and rec1['cc3_filename'] == rec1['name']:
                print("%s doesn't appear to have a valid name" % rec1['id'])

            if rec1['tags'] is None or len(rec1['tags']) == 0:
                print("%s doesn't have any tags" % rec1['id'])

            if (rec1['cc3_filename'] is None or len(rec1['cc3_filename']) == 0) and 'cowering' not in rec1['options']:
                print("%s doesn't have a cc3_filename" % rec1['id'])

            if (rec1['cc3_filename'] == rec1['name']) and (rec1['cc3_filename'] == rec1['cc3_desc']):
                print("%s doesn't appear to have a fully fleshed out record" % rec1['id'])

            if rec1['bin_crc32'] is not None and self.cowering_data[rec1['bin_crc32']] is not None and rec1['good_name'] is not None and rec1['good_name'] != self.cowering_data[rec1['bin_crc32']]:
                print("%s has a bad good_name" % rec1['id'])

            # check against Cowering's data
            if rec1['good_name'] is not None:
                found_crc = False
                for c in self.cowering_data.keys():
                    if self.cowering_data[c] == rec1['good_name']:
                        if rec1['bin_crc32'] != c and rec1['cowering_crc32'] != c:
                            print("%s has a CRC32 that doesn't match Cowering's for its good_name" % rec1['id'])
                        found_crc = True
                        break
                if found_crc is False:
                    print("Never found a CRC in the Cowering datafile for %s's good_name" % rec1['id'])

            # check variant ID
            if rec1['variant_of'] is not None:
                found_parent = False
                for rec2 in self.db:
                    if rec1 is rec2:
                        continue

                    if rec1['variant_of'] == rec2['id']:
                        found_parent = True
                        break

                if found_parent is False:
                    print("%s has a variant_of that doesn't point to any valid record" % rec1['id'])

        self.banner("Checking that all Cowering CRC32s are in the DB")

        found_crc = False
        for crc in self.cowering_data.keys():
            for rec in self.db:
                if rec['bin_crc32'] == crc or rec['cowering_crc32'] == crc:
                    found_crc = True
                    if rec['good_name'] != self.cowering_data[crc]:
                        print("%s has a good_name that doesn't match Cowering's" % rec['id'])
                    break

        if found_crc is False:
            print("Didn't find a CRC32 in the DB for %s: %s" % (crc, self.cowering_data[crc]))


        if level > 1:
            self.banner("Checking that all ROMs in the roms dir are in the DB")

            files_in_db = []
            for rec in self.db:
                if rec['cc3_filename'] is not None:
                    filename = rec['cc3_filename'].upper()
                    basename, ext = os.path.splitext(filename)
                    ext = ext[1:]
                    if ext in allowed_romfile_extensions:
                        files_in_db.append(filename)

            files_in_repo = []
            for romfile in os.listdir(self.roms_repository):
                basename, ext = os.path.splitext(romfile)
                ext = ext[1:]
                if ext in allowed_romfile_extensions:
                    files_in_repo.append(romfile)

            for romfile in files_in_repo:
                if romfile not in files_in_db:
                    # we didn't find this .rom file in the DB under cc3_filename.rom
                    # check to see if this .rom file is actually in the DB under another name
                    rom_data, warnings = self.calc_md5_for_file("%s/%s" % (self.roms_repository, romfile))
                    rec = self.get_record_from_rom_md5s(rom_data['rom_data_md5'], rom_data['rom_attr_md5'])

                    if rec is not None:
                        print("%s is in the repository, but it is in the DB under %s (%s)" % (romfile, rec['id'], rec['cc3_filename'].upper()))
                    else:
                        print("%s is in the repository, but it is not in the DB" % romfile)

            self.banner("Checking that all ROMs in the DB are in the roms dir")

            for dbfile in files_in_db:
                if dbfile not in files_in_repo:
                    rec = self.get_record_from_cc3filename(dbfile)
                    print("%s is referenced in the DB (%s), but it isn't in the repository" % (dbfile, rec['id']))

        if menufile is not None:
            # check the entries in the MENULIST to be sure that they have filenames and
            # descriptions

            with open(menufile, 'r') as fh:
                for line in fh.readlines:
                    tag = line[:8].lower()

                    # hack for menu - it should get the game tag records
                    if tag == 'menu':
                        tag = 'game'

                    recs = self.get_all_records_from_tag(tag)

                    blank_reg = re.compile('^\s*$')

                    for rec in recs:
                        if rec['cc3_desc'] is None:
                            print("%s is missing a cc3_desc" % rec['id'])
                        elif blank_reg.search(rec['cc3_desc']) is not None:
                            print("%s has a blank cc3_desc" % rec['id'])

                        basename, ext = os.path.splitext(rec['cc3_filename'])
                        if ((not os.path.isfile("%s/%s.TXT" % (self.manuals_repository, basename.upper()))) and
                                ('proto' not in rec['tags']) and
                                ('demo' not in rec['tags'])):
                            print("%s is referenced for the CC3, but missing a manual file (%s.TXT)" % (rec['id'], basename.upper()))

        if level > 2:
            self.banner("Checking manuals")

            for manfile in os.listdir(self.manuals_repository):
                if not manfile.endswith('.TXT'):
                    continue

                found_rec = False
                for ext in allowed_romfile_extensions:
                    basename, junk = os.path.splitext(manfile)
                    rec = self.get_record_from_cc3filename(basename.lower(), ext=ext)
                    if rec is not None:
                        found_rec = True

                if found_rec is False:
                    print("%s is in the manuals repository, but isn't referenced in the DB" % manfile)

                with open("%s/%s" % (self.manuals_repository, manfile), 'r') as fh:
                    for line in fh.readlines():
                        line = line.strip(CRLF)
                        if len(line) > 20:
                            print("%s has line(s) longer than 20 characters" % manfile)
                            break
        return


def inty_srclist(other_args):
    parser = argparse.ArgumentParser(description='srclist')
    parser.add_argument('--id', help='sort by game id (default is to sort by cc3 description',
                        action='store_true')
    parser.add_argument('--nodos', help="don't put DOS CR/LF endings on the lines", action="store_true")
    parser.add_argument('filters', help='filter by these tags', action='append')
    args = parser.parse_args(other_args)

    this_crlf = CRLF

    if args.nodos is True:
        this_crlf = "\n"

    ids = inty.get_all_ids('name')

    for ID in ids:
        rec = inty.get_record_from_id(ID)
        it_matches = True

        if rec['tags'] is not None:
            romtags = rec['tags'].split(',')
            for filt in args.filters:
                if filt not in romtags:
                    it_matches = False
        else:
            # don't print any recs without tags
            it_matches = False

        if it_matches is True:
            if args.id is True:
                sys.stdout.write("%s%s" % (rec['id'], this_crlf))
                sys.stdout.flush()
            else:
                if rec['cc3_filename'] is not None:
                    sys.stdout.write("%s%s" % (rec['cc3_filename'].upper(), this_crlf))
                    sys.stdout.flush()
    return


def inty_gamelist(other_args):
    parser = argparse.ArgumentParser(description='gamelist')
    parser.add_argument('--noimages', help="don't add image information", action="store_true")
    parser.add_argument('filters', help='filter by these tags', action='append')
    args = parser.parse_args(other_args)

    boxart = {}
    if args.noimages is False:
        boxart_files = os.listdir(inty.get_boxart_repository())

        for bfile in boxart_files:
            basename, ext = os.path.splitext(bfile)
            boxart[basename] = ext

    with open('gamelist.xml', 'w') as fhw:
        fhw.write('<?xml version="1.0"?>\n')
        fhw.write('<gameList>\n')

        ids = inty.get_all_ids('name')

        for ID in ids:
            rec = inty.get_record_from_id(ID)

            if rec['cc3_filename'] is None:
                continue
            if rec['tags'] is None:
                continue

            romtags = rec['tags'].split(',')

            it_matches = True

            if len(args.filters) > 0:
                for filt in args.filters:
                    if filt not in romtags:
                        it_matches = False

            if it_matches is False:
                continue

            fhw.write('  <game>\n')
            fhw.write('    <path>./%s</path>\n' % rec['cc3_filename'].upper())
            fhw.write('    <name>%s</name>\n' % rec['name'])

            image = None
            if args.noimages is False:
                if rec['cc3_filename'] in boxart.keys():
                    image = "%s%s" % (rec['cc3_filename'], boxart[rec['cc3_filename']])
                else:
                    # maybe the variant parent?
                    if rec['variant_of'] is not None:
                        variant_rec = inty.get_record_from_id(rec['variant_of'])

                        if variant_rec['cc3_filename'] in boxart.keys():
                            image = "%s%s" % (variant_rec['cc3_filename'], boxart[variant_rec['cc3_filename']])

            if image is not None:
                fhw.write('    <image>~/.emulationstation/downloaded_images/intellivision/%s</image>\n' % image)
            fhw.write('    <players />\n')
            fhw.write('  </game>\n')

        fhw.write('</gameList>\n')
    return


def inty_cc3menus(other_args=None):
    menulist = []
    with open('MENULIST.TXT', 'r') as fh:
        menulist = fh.readlines()

    for line in menulist:
        cc3file = line[:8].strip()

        print("Writing %s.CC3" % cc3file)

        with open('%s.CC3' % cc3file, 'w') as fhw:
            if cc3file == 'MENU':
                # main menu is special, it gets a list of all other menus at the top
                for menu in menulist:
                    if menu[0:8] != 'MENU    ':
                        fhw.write('%s%sMENU' % (menu[8:28], menu[0:8]))
            else:
                # non-main menu list get a return to the main menu
                                       # 12345678901234567890    12345678
                fhw.write("%s%sMENU" % ("---  Main Menu   ---", "MENU    "))

            tag = cc3file.lower()

            # hack for menu - it is really 'game' tags
            if tag == 'menu':
                recs1 = inty.get_all_records_from_tag('game')
            else:
                recs1 = inty.get_all_records_from_tag(tag)

            # another hack - brew should include brewcart
            if tag == 'brew':
                recs1.extend(inty.get_all_records_from_tag('brewcart'))

            # perform the intersection with records that have cc3_desc fields
            recs2 = inty.get_all_records_with_cc3desc()
            recs = inty.recs_intersection(recs1, recs2)
            sorted_db = []

            # if a .LST file is specified, this is giving an order for the category
            if os.path.isfile("%s.LST" % cc3file) is True:
                with open('%s.LST' % cc3file, 'r') as fhr:
                    for line in fhr.readline():
                        rec = inty.get_record_from_id(line)
                        sorted_db.append(rec)
            else:
                sorted_db = sorted(recs, key=lambda x: x['cc3_desc'])

            for rec in sorted_db:
                basename, ext = os.path.splitext(rec['cc3_filename'])
                fhw.write('%-20s%-8s    ' % (rec['cc3_desc'], basename))
    return


def inty_dumpcc3(other_args):
    parser = argparse.ArgumentParser(description='dumpcc3')
    parser.add_argument('cc3menu', help='CC3 menu file')
    args = parser.parse_args(other_args)

    filename = args.cc3menu
    for d in CC3.get_cc3_data(filename):
        print("|%-20s|%-8s|%4s|" % (d['desc'], d['file'], d['menu']))
    return


def inty_tags(other_args=None):
    for tag in inty.get_all_tags():
        print("%s" % tag)
    return


def inty_cfgfile(other_args=None):
    parser = argparse.ArgumentParser(description='dumpcc3')
    parser.add_argument('id', help='game id')
    parser.add_argument('cfgfile', help='cfg file to add to the record')
    args = parser.parse_args(other_args)

    ID = args.id
    filename = args.cfgfile

    rec = inty.get_record_from_id(ID)

    if rec is None:
        print("Couldn't find record for ID %s" % ID)
        return

    if not os.path.isfile(filename):
        print("%s doesn't look like a file" % filename)
        return

    with open(filename, 'r') as fh:
        rec['cfg_file'] = ""
        for line in fh.readlines():
            rec['cfg_file'] += "%s\n" % line.strip()

    try:
        inty.replace_rom(rec)
        print("Record modified for %s" % rec['id'])
    except:
        print("FAILURE: ID %s not found in the DB during replacement (??)" % rec['id'])
    return


def inty_fetchrom(other_args):
    parser = argparse.ArgumentParser(description='fetchrom')
    parser.add_argument('id', help='game id')
    args = parser.parse_args(other_args)

    game_id = args.id
    rec = inty.get_record_from_id(game_id)

    if rec is not None:
        romfile = rec['cc3_filename'].upper()

        try:
            inty.copy_rom_file_from_repository(romfile)
            print("%s created" % romfile)
        except Exception as errmsg:
            print("FAILURE: %s not created: %s" % (romfile, errmsg))
    else:
        print("Game ID %s not found" % game_id)
    return


def inty_wash(other_args):
    parser = argparse.ArgumentParser(description='wash')
    parser.add_argument('filename', help='rom file to wash')
    args = parser.parse_args(other_args)

    data = inty.wash_rom(args.filename)

    print(data)
    return


def inty_edit(other_args):
    parser = argparse.ArgumentParser(description='edit')
    parser.add_argument('id', help='Either game id or rom filename')
    args = parser.parse_args(other_args)

    # this might be an iD
    rec = inty.get_record_from_id(args.id)

    if rec is None:
        # try via cc3filename
        rec = inty.get_record_from_cc3filename(args.id)

    if rec is None:
        print("FAILURE: record not found for edit")
        return

    rec, status = interactively_edit_record(rec)
    # print("rlrDEBUG rec=|%s| status=|%s|" % (str(rec), status))

    try:
        inty.replace_rom(rec)
        print("Record modified for %s" % rec['id'])
    except:
        print("FAILURE: ID %s not found in DB during replacement (??)" % rec['id'])
    return


# this routine is to replace the rom file for an already defined rom (e.g. an
# update to an in-development game)

def inty_replacerom(other_args):
    parser = argparse.ArgumentParser(description='replacerom')
    parser.add_argument('--copy', help='Copy flag - if present, copy the rom file into the repository')
    parser.add_argument('id', help='game id')
    parser.add_argument('romfile', help='rom filename')
    args = parser.parse_args(other_args)

    ID = args.id
    rec = inty.get_record_from_id(ID)

    if rec is None:
        print("Couldn't find %s in the DB." % ID)
        return

    # wash this file
    data = inty.wash_rom(args.romfile)

    # update old data from the record that is about the physical file
    rec['bin_md5'] = data['wash']['binmd5data']['bin_md5']
    rec['rom_data_md5'] = data['wash']['rommd5data']['rom_data_md5']
    rec['rom_attr_md5'] = data['wash']['rommd5data']['rom_attr_md5']

    try:
        inty.add_or_replace_rom(rec)
        msg = "Record for %s updated" % ID

        if args.copy is True:
            force = True
            try:
                inty.copy_rom_file_to_repository(data['wash']['romfile'], rec['cc3_filename'].upper(), force)
                msg += ", copied to repository as %s" % rec['cc3_filename'].upper()
            except Exception as errmsg:
                msg += ", BUT COULDN'T COPY TO REPOSITORY! %s" % errmsg
        print(msg)
    except Exception as errmsg:
        print("Couldn't replace record in DB: %s" % errmsg)
    return


def inty_add(other_args):
    parser = argparse.ArgumentParser(description='add')
    parser.add_argument('--copy', help='Copy flag: if present, copy the romfile into the repository',
                        action='store_true')
    parser.add_argument('romfile', help='romfile being added')
    args = parser.parse_args(other_args)

    base = args.romfile

    dot_idx = base.rfind('.')
    if dot_idx > 0:
        ext = base[dot_idx+1:]
        base = base[0:dot_idx]

    slash_idx = base.rfind('/')
    if slash_idx > 0:
        base = base[0:slash_idx]

    game_name = "%s%s" % (base[0].upper(), base[1:].lower())

    # wash this file
    data = inty.wash_rom(args.romfile)

    # print("rlrDEBUG data=|%s|" % data)

    rec, why = inty.get_record_from_wash_data(data)

    if rec is not None:
        print("This %s file is already in the DB as %s" % (data['rom_file_type'].upper(), rec['id']))
        return 1

    rec = {}

    # fill in any applicable cowerings data
    cowdata = inty.get_cowering_data()
    try:
        cowering_crc32 = data['bin_cowering_crc32']

        if cowering_crc32 in cowdata.keys():
            rec['good_name'] = cowdata[cowering_crc32]
            rec['bin_cowering_crc32'] = cowering_crc32
    except:
        pass

    try:
        rec['cc3_filename'] = "%s.%s" % (base[0:8].lower(), ext.lower())
    except:
        pass

    if data['rom_file_type'] == 'rom':
        try:
            rec['rom_data_crc16s'] = data['romcrcdata']['rom_data_crc16s']
        except:
            pass
        try:
            rec['rom_attr_crc16'] = data['romcrcdata']['rom_attr_crc16']
        except:
            pass

        try:
            rec['bin_crc32'] = data['bincrcdata']['bin_crc32']
        except:
            pass

    elif data['rom_file_type'] == 'bin':
        try:
            rec['bin_crc32'] = data['bincrcdata']['bin_crc32']
        except:
            pass

        try:
            rec['rom_data_crc16s'] = data['romcrcdata']['rom_data_crc16s']
        except:
            pass
        try:
            rec['rom_attr_crc16'] = data['romcrcdata']['rom_attr_crc16']
        except:
            pass

    elif data['rom_file_type'] == 'luigi':
        try:
            rec['luigi_crc32s'] = data['luigicrcdata']['luigi_crc32s']
        except:
            pass

        meta = data['luigicrcdata']['luigi_meta']

        try:
            game_name = meta['name']
        except:
            pass
        try:
            rec['author'] = meta['author']
        except:
            pass
        try:
            rec['year'] = meta['year']
        except:
            pass
    else:
        raise Exception("Unknown rom file type: %s" % data['rom_file_type'])

    game_id = game_name.replace(' ','')
    game_id = game_id.replace('_','')
    rec['cc3_desc'] = game_name[0:20]
    rec['id'] = game_id.lower()
    rec['name'] = game_name

    # uniquify the record ID if necessary
    while rec['id'] in inty.get_all_ids():
        rec['id'] += "_"

    rec, why = interactively_edit_record(rec, args.romfile)

    if rec is None:
        print("FAILURE: %s" % why)
        return

    if inty.rom_file_exists_in_repository(rec['cc3_filename'].upper()):
        print("FAILURE: %s already exists in repository." % rec['cc3_filename'].upper())
        return

    try:
        inty.add_rom(rec)
        msg = "ROM added to DB"
        if args.copy is True:
            try:
                srcfile = data['wash']['romfile']
            except:
                srcfile = args.romfile
            try:
                inty.copy_rom_file_to_repository(srcfile, rec['cc3_filename'].upper())
                msg += ", copied to repository as %s" % rec['cc3_filename'].upper()
            except Exception as errmsg:
                msg += ", BUT COULDN'T COPY TO REPOSITORY! %s" % errmsg
        print(msg)
    except Exception as errmsg:
        print("FAILURE: Couldn't add record: %s" % errmsg)
    return


def interactively_edit_record(rec, filename=None):
    prev_id = rec['id']

    newfilename = inty.write_ascii_record(rec, filename)
    prev_rec_md5 = Checksum.md5_hex_str(str(rec))

    if newfilename is not None:
        keep_editing = True

        while keep_editing is True:
            keep_editing = False
            cmd = ['vim', newfilename]
            subprocess.call(cmd)

            rec = inty.parse_ascii_record(newfilename)
            if rec is None:
                return (None, "No ID in record")

            status = inty.validate_record(rec)

            if prev_rec_md5 == Checksum.md5_hex_str(str(rec)):
                return (None, "No change to record")

            # if the iD is missing, bail here
            if 'no ID in record' in status:
                return (None, "ID missing in record")

            # if the ID is bad, go back for another edit
            if rec['id'] != prev_id:
                if 'ID in DB' in status:
                    rec['id'] = prev_id
                    newfilename = inty.write_ascii_record(rec)
                    print("FAILURE: you changed the ID, but the new ID is already in the DB.\nReverting the ID.")
                    raw_input("HIT RETURN TO CONTINUE.")
                    keep_editing = True
                else:
                    rec['replace_id'] = prev_id

            if 'cc3_desc too long' in status:
                newfilename = inty.write_ascii_record(rec)
                print("FAILURE: the cc3_desc is too long")
                raw_input("HIT RETURN TO CONTINUE.")
                keep_editing = True

    else:
        return (None, "Couldn't write temp file")
    return (rec, "success")


def inty_createfrinklist(other_args=None):
    ids = inty.get_all_ids("name")

    for ID in ids:
        rom = inty.get_record_from_id(ID)

        cc3f = ""
        name = ""
        year = ""
        auth = ""

        if rom['cc3_filename'] is not None:
            cc3f = rom['cc3_filename'].upper()
        if rom['name'] is not None:
            name = rom['name']
        if rom['year'] is not None:
            year = rom['year']
        if rom['author'] is not None:
            auth = rom['author']

        sys.stdout.write("%s%s" % (cc3f, CRLF))
        sys.stdout.write("%s%s" % (name, CRLF))
        sys.stdout.write("%s%s" % (year, CRLF))
        sys.stdout.write("%s%s" % (auth, CRLF))
        sys.stdout.write("%s" % CRLF)  # parent rom
        sys.stdout.write("%s" % CRLF)  # unknown entry
        sys.stdout.write("Raster%s" % CRLF)
        sys.stdout.write("Horizontal%s" % CRLF)
        sys.stdout.write("%s" % CRLF)  # controller type
        sys.stdout.write("Status Good%s" % CRLF) # any value to putting real data here?
        sys.stdout.write("Color Good%s" % CRLF) # any value to putting real data here?
        sys.stdout.write("Sound Good%s" % CRLF) # any value to putting real data here?
        sys.stdout.write("%s" % CRLF)  # game type
    return


def inty_md5(other_args):
    parser = argparse.ArgumentParser(description='md5')
    parser.add_argument('romfile', help='rom filename')
    args = parser.parse_args(other_args)

    filename = args.romfile
    rom_data, warnings = inty.calc_md5_for_file(filename)

    if len(warnings) > 0:
        print("WARNINGS:")
        for warn in warnings:
            print(warn)

    if rom_data['rom_file_type'] == 'bin':
        print("bin_md5=%s" % rom_data['bin_md5'])
    elif rom_data['rom_file_type'] == 'rom':
        print("rom_data_md5=%s" % rom_data['rom_data_md5'])
        print("rom_attr_md5=%s" % rom_data['rom_attr_md5'])
    elif rom_data['rom_file_type'] == 'luigi':
        print("luigi crcs=%s" % str(rom_data))
    return


def inty_crc32(other_args):
    parser = argparse.ArgumentParser(description='crc32')
    parser.add_argument('romfile', help='rom filename')
    args = parser.parse_args(other_args)

    filename = args.romfile
    rom_data, warnings = inty.calc_crcs_for_file(filename)

    if len(warnings) > 0:
        print("WARNINGS:")
        for warn in warnings:
            print(warn)

    if rom_data['rom_file_type'] == 'bin':
        print("bin_crc32=%s" % rom_data['bin_crc32'])
    elif rom_data['rom_file_type'] == 'rom':
        print("rom_data_crc16s=|%s|" % str(rom_data['rom_data_crc16s']))
        print("rom_attr_crc16=|%s|" % str(rom_data['rom_attr_crc16']))
    elif rom_data['rom_file_type'] == 'luigi':
        print("luigi crcs=%s" % str(rom_data))
    return


def inty_name_from_rom_file(other_args):
    parser = argparse.ArgumentParser(description='namefromromfile')
    parser.add_argument('romfile', help='rom filename')
    args = parser.parse_args(other_args)

    romfile = args.romfile
    rec = inty.get_record_from_cc3filename(romfile)
    if rec is not None:
        rom = rec['id']
        print(rom)
    return


def inty_rom_file(other_args):
    parser = argparse.ArgumentParser(description='romfile')
    parser.add_argument('id', help='game id')
    args = parser.parse_args(other_args)

    game_id = args.id
    rec = inty.get_record_from_id(game_id)
    if rec is not None and rec['cc3_filename'] is not None:
        rom = rec['cc3_filename']
        print(rom)
    return


def inty_options(other_args):
    parser = argparse.ArgumentParser(description='options')
    parser.add_argument('id', help='game id')
    args = parser.parse_args(other_args)

    game_id = args.id
    rec = inty.get_record_from_id(game_id)
    if rec is not None and rec['options'] is not None:
        for opt in rec['options'].split(','):
            print(opt)
    return


def inty_kbdhackfile(other_args):
    parser = argparse.ArgumentParser(description='kbdhackfile')
    parser.add_argument('id', help='game id')
    args = parser.parse_args(other_args)

    game_id = args.id
    hack = inty.get_laptop_default_kbdhackfile()

    # special hack case for CGC
    if game_id == 'cgc':
        hack = 'laptop-cgc'
    else:
        rec = inty.get_record_from_id(game_id)
        if rec is not None:
            if rec['options'] is not None:
                if 'ecs' in rec['options'].split(','):
                    hack = inty.get_laptop_default_ecs_kbdhackfile()
            if rec['kbdhackfile'] is not None:
                hack = rec['kbdhackfile']
    print(hack)
    return


def inty_kbdhackfiledir(other_args=None):
    print(inty.get_kbdhackfile_dir())
    return


def inty_list(other_args):
    parser = argparse.ArgumentParser(description='list')
    parser.add_argument('--tag', help='filter list by this tag (ignored if IDs are given)')
    parser.add_argument('id', nargs='?', help='game id', default=None)
    args = parser.parse_args(other_args)

    if args.id is not None:
        # overloading the list functionality to dump a record for a given name
        ID = args.id
        rec = inty.get_record_from_id(ID)

        if rec is None:
            rec = inty.get_record_from_cc3filename(ID)

        if rec is None:
            print("%s: unknown ROM id" % ID)
            return

        print("--- %s ---" % ID)
        for k in inty.get_fields_order():
            if rec[k] is not None:
                # treat multi-line fields rightly
                if k == 'cfg_file':
                    print(" --- CFG FILE ---\n%s\n --- END CFG ---" % rec[k])
                # elif k == 'kbdhackfile':
                #     print(" --- KBDHACKFILE ---\n%s\n --- END KBDHACKFILE ---" % rec[k])
                else:
                    # normal key-value pair
                    print(" %s: %s" % (k, rec[k]))
    else:
        ids = inty.get_all_ids()

        count = 0
        for ID in ids:
            rec = inty.get_record_from_id(ID)

            if args.tag is not None and rec['tags'] is None:
                continue

            if args.tag is not None and args.tag not in rec['tags'].split(','):
                continue

            print("%-15s %s" % (rec['id'], rec['name']))
            count += 1

        print("Total: %s ROMs" % count)
    return


def inty_dumpdbforpi(other_args=None):
    parser = argparse.ArgumentParser(description='dumpdbforpi')
    parser.add_argument('outfile', help='file in which to write the db')
    args = parser.parse_args(other_args)

    inty.dump_game_opts_db_for_emulator(args.outfile)
    return


def inty_which(other_args):
    parser = argparse.ArgumentParser(description='which')
    parser.add_argument('--copy', help='After identifying the roms, copy them to the repository', action='store_true')
    parser.add_argument('--log', help='Write a logfile of the actions', action='store_true')
    parser.add_argument('--idonly', help='Only output the game id', action='store_true')
    parser.add_argument('--cow', help='Match only based on Cowerings data', action='store_true')
    parser.add_argument('filenames', help='romfiles to lookup', action='append')
    args = parser.parse_args(other_args)

    rep = inty.get_roms_repository()

    cowdata = {}
    if args.cow is True:
        cowdata = inty.get_cowering_data()

    unknown = []
    nofiles = []
    missing = []
    possess = 0
    logpart = ""

    for filename in args.filenames:
        out = "%s " % filename

        data = inty.wash_rom(filename)

        if args.idonly is True:
            out += "[%s] " % data['rom_file_type'].upper()

        if args.cow is True:
            cc = data['orig']['crc32']
            if cc in cowdata.keys():
                if args.idonly is True:
                    out += "%s: %s" % (cc, cowdata[cc])
                else:
                    out += "%s: UNKNOWN" % cc
                    logpart = "unknown"
        else:
            rec, where = inty.get_record_from_wash_data(data)

        # print("rlrDEBUG rec=%s where=%s" % (str(rec), str(where)))

        if rec is not None:
            if 'systemrom' in rec['tags'].split(','):
                systemrom = True
            if where is not None and args.idonly is False:
                out += "[%s] " % where
            out += rec['id']
            if args.idonly is False:
                out += ": %s" % rec['name']

            if rec['cc3_filename'] is not None:
                fname = rec['cc3_filename'].upper()

                if (os.path.isfile("%s/%s" % (rep, fname))) is False:
                    if systemrom is False and args.copy is True:
                        out += ", copying ROM to repository as %s" % fname
                        inty.copy_rom_file_to_repository(data['wash']['romfile'], fname)

                    logpart = "missing"
                else:
                    possess += 1
            else:
                out += ", CANNOT CHECK REPOSITORY - NO CC3_FILENAME DEFINED."
                logpart = "nofile"
        elif args.cow is True:
            pass
        else:
            out += "UNKNOWN"
            logpart = "unknown"

        print(out)

        if logpart == "unknown":
            unknown.append(out)
        if logpart == "nofile":
            nofiles.append(out)
        if logpart == "missing":
            missing.append(out)

    if len(args.filenames) > 1:
        print("%s Unknown ROMS\n%s ROMs not in the repository\n%s ROMs already in the repository" % (len(unknown), len(missing), possess))

    if args.log is True:
        with open('inty_logfile.txt', 'w') as fhw:
            if len(unknown) > 0:
                fhw.write('--- %s UNKNOWNS ---\n' % len(unknown))
                for i in unknown:
                    fhw.write('%s\n' % i)

            if len(nofiles) > 0:
                fhw.write('--- %s MISSING CC3_FILENAMES ---\n' % len(nofiles))
                for i in nofiles:
                    fhw.write('%s\n' % i)

            if len(missing) > 0:
                fhw.write('--- %s MISSING ROM FILES ---\n' % len(missing))
                for i in missing:
                    fhw.write('%s\n' % i)
    return


def inty_search(other_args):
    parser = argparse.ArgumentParser(description='search')
    parser.add_argument('--case', help='if present, perform a case sensitive search', action='store_true')
    parser.add_argument('search', help='search string')
    args = parser.parse_args(other_args)

    # if the search word has any upper case letters, do a case sensitive search
    patt = args.search
    ic = False

    if patt.lower() == patt:
        ic = True
    if args.case is True:
        ic = False

    regex_flags = 0
    if ic is True:
        regex_flags = re.IGNORECASE

    db = inty.get_db()

    for rec in db:
        print_it = False
        out = "---\n%s: ID" % rec['id']
        if re.search(patt, rec['id'], regex_flags) is not None:
            print_it = True
        if (rec['name'] is not None) and (re.search(patt, rec['name'], regex_flags) is not None):
            print_it = True
            out += "\n%s: NAME" % rec['name']
        if (rec['good_name'] is not None) and (re.search(patt, rec['good_name'], regex_flags) is not None):
            print_it = True
            out += "\n%s: GOOD_NAME" % rec['good_name']
        if (rec['cc3_desc'] is not None) and (re.search(patt, rec['cc3_desc'], regex_flags) is not None):
            print_it = True
            out += "\n%s: CC3_DESC" % rec['cc3_desc']
        if (rec['cc3_filename'] is not None) and (re.search(patt, rec['cc3_filename'], regex_flags) is not None):
            print_it = True
            out += "\n%s: CC3_FILENAME" % rec['cc3_filename']
        if (rec['year'] is not None) and (re.search(patt, rec['year'], regex_flags) is not None):
            print_it = True
            out += "\n%s: YEAR" % rec['year']
        if (rec['comments'] is not None) and (re.search(patt, rec['comments'], regex_flags) is not None):
            print_it = True
            out += "\n%s: COMMENTS" % rec['comments']

        if print_it is True:
            print(out)
    return


def inty_checkdb(other_args):
    parser = argparse.ArgumentParser(description='search')
    parser.add_argument('--level', help='checking level', action='store_int', default=1)
    parser.add_argument('menufile', nargs='?', help='menufile filename for CC3 checking')
    args = parser.parse_args(other_args)

    inty.verify_data(args.level, args.menufile)
    return


def inty_test(other_args):
    inty.set_dirty()
    return


def inty_mkrename(filters=None):
    with open('rename_roms.sh', 'w') as fhw:
        ids = inty.get_all_ids('name')

        for ID in ids:
            rec = inty.get_record_from_id(ID)

            if rec['cc3_filename'] is None:
                continue
            if rec['tags'] is None:
                continue

            junk, ext = os.path.splitext(rec['cc3_filename'])
            lcext = ext.lower()

            romtags = rec['tags'].split(',')
            it_matches = True

            if filters is not None:
                for filt in filters:
                    if filt not in romtags:
                        it_matches = False

            if it_matches is False:
                continue

            if rec['flashback_name'] is not None:
                game_name = rec['flashback_name']
            else:
                game_name = rec['name']

                game_name = re.sub('["!/]', '', game_name)
                game_name = re.sub("'", '', game_name)
                game_name = re.sub("&", 'and', game_name)

            # TODO: this won't work with Desert Bus (.BIN game) - need a better multi-extension solution
            fhw.write("rm '/home/pi/RetroPie/roms/intellivision/%s%s' > /dev/null 2>&1\n" % (game_name, lcext))
            fhw.write("ln -s /home/pi/all_inty_roms/%s '/home/pi/RetroPie/roms/intellivision/%s%s'\n" % (rec['cc3_filename'].upper(), game_name, lcext))
    return


def inty_rom_dir(other_args=None):
    print(inty.get_roms_repository())
    return


def inty_short_help(other_args=None):
    shelp = """
inty command [options]

  help for more complete description of commands

  which [--copy] [--log] [--idonly] [--cow] <files>
  list [--tag <tag>] [<game ID>]
  add [--copy] <file>
  edit <game ID>
  search [--case] <pattern>
  mwlist
  srclist <filter>
  tags
  cc3menus
  fetchrom <game ID>

  writedb
  checkdb [--level <#>] [<menulist file>]
  cfgfile <game ID> <file>
  md5 <file>
  options <game ID>
  dumpcc3 <CC3 menu file>
  mkrename <filter>
  rom_dir
  rom_file <game ID>
  kbdhackfile <game ID>
"""
    print(shelp)
    return


def inty_help(other_args=None):
    lhelp = """
inty command [options]

where command is one of

--- User commands ---

which [--copy] [--log] [--idonly] [--cow] <files>
      Report the identity of the given ROM or BIN files.
      If --copy is given, the ROM version of the file will be copied to the
       repository if it is not present.
      If --log is given, a logfile will be written that details missing ROMs.
      If --idonly is given, only the ID of the file will be displayed.
      If --cow is given, the DB data will be ignored and the file will only be
       matched based on the CRC data in the Cowering data file.

list [--tag <tag>] [<game ID>]
      Dump the games in the repository.
      If a tag is given, the games list will be only those containing that tag.
      If a game ID is given, it dumps the DB record for that game.

add [--copy] <file>
      Add a DB record for the given ROM file.
      If --copy is given, the ROM version of the file will be copied to the
      repository.

edit <game ID>
      Edit the DB record for the given game ID.

search [--case] <pattern>
      Search the DB for records matching the given pattern.
      If --case is given, the search is case sensitive (defaults to case
       insensitive).

mwlist
      Dump the games in the DB in a list file for use on the Frinkiac7 (has
       DOS style line endings applied).

srclist [-nodos] [-id] <filter>
      Dump a list of ROMs that are tagged with the given filter.

tags
      Dump a list of valid tags.

cc3menus
      Create a set of menu files for use with the CC3.  A file named
      MENULIST.TXT must exist in the current directory, which contains the
      list of menus to create.

fetchrom <game ID>
      Make a local copy of the rom file for a given game ID.

mkrename <filter>
      Write a bash script that will rename all the roms matching the filter
      to more descriptive filenames.

gamelist <filter>
      Write an .xml gamelist file for emulation station.

--- Maintenance/tool related commands ---

writedb
      Just load and rewrite the DB file (good for forcing a reordering).

checkdb [-l <#>] [<menulist file>]
      Run a set of sanity checks on the DB.
      A level of detail in checking can be specified by -l.  Levels:
       1 - basic checking
       2 - level 1 + reporting of missing cc3_desc, poor game names,
            duplicate md5s
      If a menulist file is specified, the checks to be sure all the tags
       defined in that menulist have at least 2 records (NOT WORKING)

cfgfile <game ID> <file>
      Add the given .CFG file to the record for a given ID.

md5 <file>
      Report md5 sum(s) for the given ROM or BIN file.

options <game ID>
      Report the jzinty emulator options for the given game ID.
       (really just for command line API purposes)

dumpcc3 <CC3 menu file>
      Dump the contents of a CC3 menu file.

rom_dir
      Report the repository directory where the ROM files are stored.
       (really just for command line API purposes)

rom_file <game ID>
      Report the name of the ROM file for the given game ID.
       (really just for command line API purposes)

kbdhackfile <game ID>
      Give the name of the keyboard hackfile to use for this game, or the
       default one if none is specified in the DB.
"""
    print(lhelp)
    return


def inty_add_new_crcs(other_args=None):
    db = inty.get_db()
    repo = inty.get_roms_repository()

    #i = 0
    for rec in db:
        print("%s" % rec['id'])
        if rec['cc3_filename'] is None:
            continue

        if len(other_args) > 0:
            if rec['id'] not in other_args:
                continue

        romfname = rec['cc3_filename'].upper()
        if os.path.isfile("%s/%s" % (repo, romfname)) is False:
            print("Didn't find a file: %s" % romfname)
            continue

        rom_crc_data, warnings = inty.calc_crcs_for_file("%s/%s" % (repo, romfname))
        rom_md5_data, warnings = inty.calc_md5_for_file("%s/%s" % (repo, romfname))

        # print("rlrDEBUG rom_crc_data=|%s|" % str(rom_crc_data))
        # print("rlrDEBUG rom_md5_data=|%s|" % str(rom_md5_data))
        # print("rlrDEBUG rec=|%s|" % str(rec))

        if rom_md5_data['rom_file_type'] == 'luigi':
            rec['luigi_crc32s'] = rom_crc_data['luigi_crc32s']

        elif rom_md5_data['rom_file_type'] == 'rom':
            if rom_md5_data['rom_data_md5'] != rec['rom_data_md5']:
                print("%s has rom data md5 that doesn't match what's in the DB, skipping." % rec['id'])
                continue
            if rom_md5_data['rom_attr_md5'] != rec['rom_attr_md5']:
                print("%s has rom attr md5 that doesn't match what's in the DB, skipping." % rec['id'])
                continue

            # print("rlrDEBUG rom_crc_data=|%s|" % str(rom_crc_data['rom_data_crc16s'])
            # print("rlrDEBUG mapped=|%s|" % str(map(lambda x: "%x" % x, rom_crc_data['rom_data_crc16s'])))
            rec['rom_data_crc16s'] = rom_crc_data['rom_data_crc16s']
            rec['rom_attr_crc16'] = rom_crc_data['rom_attr_crc16']

        elif rom_md5_data['rom_file_type'] == 'bin':
            if rom_md5_data['bin_md5'] != rec['bin_md5']:
                print("%s has a bin md5 that doesn't match what's in the DB, skipping." % rec['id'])
                continue

            rec['bin_crc32'] = rom_crc_data['bin_crc32']
        else:
            print("%s came up with a bad romfile type: %s" % rom_md5_data['rom_file_type'])

        # print("%d rec=|%s|" % (i, str(rec)))
        #i += 1

    inty.set_dirty()
    return


def inty_write_inty_data_file(other_args=None):
    inty.set_dirty()
    return


#
# USE CASES I CARE ABOUT:
#
# identify a rom/bin file [done - which]
#
# add a set of rom/bin file(s) to the repository [more or less done - which, add, edit]
#
# create CC3 structures [done - cc3menus]
#
# create mamewah structures [done - frink, srclist]
#
# list info about the games in the repository [done - search, list]
#
# for command line API:
#   rom_dir     [done]
#   rom_file    [done]
#   options     [done]
#   kbdhackfile [done]
#
# sanity check the repository [done - checkdb]
#

#
# One more time!
#
# 1. given a .bin file:
#  A. calculate crc32, lookup in cowering
#      -> if not there, drop out (or log it)
#  B. lookup record by good-name, save BIN-ID if found
#  C. wash the bin file, lookup record
#    if BIN-ID = lookup-ID, update good_name, CRC32, bin_md5
#    if BIN-ID != lookup-ID, remove good_name, CRC32, bin_md5 from BIN-ID record
#

#
# Other work to be done:
# - integration of manuals for CC3 (necessary?)
# - integration of keyboard hackfiles (started - really just needs more
#    hackfiles to be defined and entered in DB)
# - integration of .bin/.cfg files (cfg files DONE via lives/rocks, not sure
#    I care to keep .bin duplicates of .rom files)
#


if __name__ == "__main__":
    inty = Inty()
    parser = argparse.ArgumentParser(description='Inty tool')
    args, other_args = parser.parse_known_args()

    try:
        cmd = other_args.pop(0)
        func = "inty_%s(other_args)" % cmd
        exec(func)
    except IndexError:
        inty_short_help()
        sys.exit("No command given.")
    except Exception as errmsg:
        if re.search('name .* is not defined', str(errmsg), re.IGNORECASE) is not None:
            sys.exit("Command %s is invalid." % cmd)
        else:
            sys.exit("Problem running command %s: %s" % (cmd, errmsg))
