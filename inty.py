#!/usr/bin/env python3

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


import sys
import os
import re
import json
import argparse
import subprocess
# import yaml

tool_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(tool_dir)

import cowering
import shell
import cc3
import checksum
from file_parser import FileParser
from db_parser import DbParser

CRLF = f"{chr(13)}{chr(10)}"

syswart = "linux"
if sys.platform == "darwin":
    syswart = "macos"

bin2rom = f"{tool_dir}/bin2rom_{syswart}"
rom2bin = f"{tool_dir}/rom2bin_{syswart}"
bin2luigi = f"{tool_dir}/bin2luigi_{syswart}"
luigi2bin = f"{tool_dir}/luigi2bin_{syswart}"

allowed_romfile_extensions = ('ROM', 'BIN', 'LUIGI')


################################################################################
#
#  Stuff for sanely dealing with argparse and subparsers
#
#  NOTE: I got this recipe from a webposting:
#   https://mike.depalatis.net/blog/simplifying-argparse.html
#


hmsg = "My CLI tool for managing my Intellivision ROMs collection"
cli = argparse.ArgumentParser(description=hmsg)
subparsers = cli.add_subparsers(dest="subcommand")


def argument(*name_or_flags, **kwargs):
    # Convenience function to properly format arguments to pass to the subcommand decorator.
    return (list(name_or_flags), kwargs)


def subcommand(args=[], parent=subparsers):
    #
    # Decorator to define a new subcommand in a sanity-preserving way.
    # The function will be stored in the 'func' variable when the parser
    # parses arguments so that it can be called directly like so:
    #     args = cli.parse_args()
    #     args.func(args)
    #
    # Usage example::
    #     @subcommand([argument("-d", help="Enable debug mode", action="store_true")])
    #     def my_subcommand(args):
    #         # code here can use args.d to refer to the optional debug mode
    #         # argument stored by the decorator
    #         if args.d is True:
    #             # do something debuggish
    #         else:
    #             # do something without debug
    #
    # Then on the command line::
    #     $ python cli.py my_subcommand -d
    #
    def decorator(func):
        parser = parent.add_parser(func.__name__, help=func.__doc__, description=func.__doc__)
        for arg in args:
            parser.add_argument(*arg[0], **arg[1])
        parser.set_defaults(func=func)
    return decorator

################################################################################


class IntellivisionRomsDB:
    def __init__(self):
        self.inty_tool_dir = tool_dir
        self.cowering_file = f'{tool_dir}/inty_203.dat'
        self.inty_data_file = f'{tool_dir}/inty_data.dat'
        self.roms_repository = f'{tool_dir}/roms'
        self.boxart_repository = f'{tool_dir}/boxart'
        self.manuals_repository = f'{tool_dir}/cc3_manuals'
        self.kbdhackfile_dir = f'{tool_dir}/kbdhackfiles'
        self.laptop_default_kbdhackfile = 'basicnoecs'
        self.laptop_default_ecs_kbdhackfile = 'basic'
        self.frinkiac7_default_kbdhackfile = 'basic'
        self.temp_dir = '/tmp'
        self.dirty = False
        self.number_of_backups_to_keep = 9

        dbparser = DbParser()
        self.db, self.db_header = dbparser.read_inty_data_file(self.inty_data_file)
        self.cowering_data = cowering.read_cowering_data(self.cowering_file)
        return

    def __del__(self):
        if self.dirty is True:
            dbparser = DbParser()
            dbparser.write_inty_data_file()
        return

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
            fname = f"{name}.{ext}"
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
            except Exception:
                pass
        return recs

    def get_all_records_from_tag(self, tag):
        recs = []

        for rec in self.db:
            try:
                tags = rec['tags'].split(',')
                if tag in tags:
                    recs.append(rec)
            except Exception:
                pass
        return recs

    def get_all_tags(self):
        all_tags = set()
        for rom in self.db:
            try:
                tags = rom['tags'].split(',')
                all_tags.update(tags)
            except Exception:
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
        if isinstance(query, dict):
            fields_list = query.keys()
        else:
            raise Exception(f"Not implemented: query is type {type(query)}")

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

                case_insensitive_list = ('cc3_filename', 'rom_data_md5', 'rom_attr_md5', 'bin_md5', 'bin_crc32',
                                         'cowering_crc32', 'rom_data_crc16s', 'rom_attr_crc16', 'luigi_crc32s')

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
            raise Exception(f"Bad rom file type: {wash['rom_file_type']}")
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

            romfile = f"{self.roms_repository}/{rec['cc3_filename'].upper()}"

            if os.path.isfile(romfile):
                statuses.append('ROM in repository')
            else:
                statuses.append('no ROM in repository')

        # check 3: cc3_desc
        if rec['cc3_desc'] is not None:
            if len(rec['cc3_desc']) > 20:
                statuses.append('cc3_desc too long')
        return statuses

    def rom_file_exists_in_repository(self, romname):
        return os.path.isfile(f'{self.roms_repository}/{romname}')

    def copy_rom_file_to_repository(self, src, dest, force=False):
        if os.path.isfile(f"{self.roms_repository}/{dest}") is False or force is True:
            shell.exc(f'cp {src} {self.roms_repository}/{dest}')
        else:
            raise Exception("Cannot copy file, target exists.")
        return

    def copy_rom_file_from_repository(self, romfile, force=False):
        if os.path.isfile(romfile) is False or force is True:
            shell.exc(f'cp {self.roms_repository}/{romfile} .')
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
            raise Exception(f"Didn't find record for replacement.  ID:{findid}")

        self.db[rom_index] = new_rec
        self.dirty = True
        return

    def add_or_replace_rom(self, new_rec):
        try:
            self.replace_rom(new_rec)
        except Exception:
            self.add_rom(new_rec)
        return

    def wash_rom(self, filename):
        parser = FileParser()
        origcrcdata, origwarnings = parser.calc_crcs_for_file(filename)

        # TODO: check warnings

        shell.exc(f"rm -f {self.temp_dir}/xxx.bin {self.temp_dir}/xxx.cfg {self.temp_dir}/xxx.rom "
                  f"{self.temp_dir}/xxx.luigi > /dev/null")

        filename.replace("'", "\'")
        basename, ext = os.path.splitext(filename)
        output = {}
        output['rom_file_type'] = origcrcdata['rom_file_type']

        if origcrcdata['rom_file_type'] == 'bin':
            # convert bin to rom to get those CRCs
            shell.exc(f"cp '{filename}' {self.temp_dir}/xxx.bin")
            if os.path.isfile(f'{basename}.cfg'):
                shell.exc(f"cp '{basename}.cfg' {self.temp_dir}/xxx.cfg")
            if os.path.isfile(f'{basename}.CFG'):
                shell.exc(f"cp '{basename}.CFG' {self.temp_dir}/xxx.cfg")
            shell.exc(f"cd {self.temp_dir} ; {bin2rom} xxx.bin > /dev/null")

            romcrcdata, warnings = parser.calc_crcs_for_file(f'{self.temp_dir}/xxx.rom')

            # TODO: check warnings

            output['bin_cowering_crc32'] = f"{checksum.cowering_crc32_from_file(filename):08X}"
            output['bincrcdata'] = origcrcdata
            output['romcrcdata'] = romcrcdata

        elif origcrcdata['rom_file_type'] == 'rom':
            # convert rom to bin to get CRCs
            shell.exc(f"cp '{filename}' {self.temp_dir}/xxx.rom")
            shell.exc(f"cd {self.temp_dir} ; {rom2bin} xxx.rom > /dev/null")

            bincrcdata, warnings = parser.calc_crcs_for_file(f'{self.temp_dir}/xxx.bin')

            # TODO: check warnings

            binfile = f'{self.temp_dir}/xxx.bin'
            output['bin_cowering_crc32'] = f"{checksum.cowering_crc32_from_file(binfile):08X}"
            output['bincrcdata'] = bincrcdata
            output['romcrcdata'] = origcrcdata

        elif origcrcdata['rom_file_type'] == 'luigi':
            output['luigicrcdata'] = origcrcdata

            try:
                enc = output['luigicrcdata']['luigi_meta']['encrypted']
            except Exception:
                enc = False

            if enc is False:
                shell.exc(f"cp '{filename}' {self.temp_dir}/xxx.luigi")
                shell.exc(f"cd {self.temp_dir} ; {luigi2bin} xxx.luigi > /dev/null")

                bincrcdata, warnings = parser.calc_crcs_for_file(f'{self.temp_dir}/xxx.bin')

                # TODO: check warnings

                binfile = f'{self.temp_dir}/xxx.bin'
                output['bin_cowering_crc32'] = f"{checksum.cowering_crc32_from_file(binfile):08X}"
                output['bincrcdata'] = bincrcdata

        else:
            raise Exception(f"romfile parsing came up with invalid rom file type: {origcrcdata['rom_file_type']}")
        return output

    def banner(self, msg):
        maxlen = 0
        for line in msg.splitlines():
            if len(line) > maxlen:
                maxlen = len(line)
        bannerlen = maxlen + 2
        bannerstr = '=' * bannerlen
        print(f"\n{bannerstr}\n {msg}\n{bannerstr}\n")
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
                    print(f"{rec1['name']} (game name) is in the DB more than once")

                if rec1['good_name'] is not None and rec2['good_name'] and rec1['good_name'] == rec2['good_name']:
                    print(f"{rec1['good_name']} (good name) is in the DB more than once")

                if rec1['id'] == rec2['id']:
                    print(f"{rec1['id']} (id) is in the DB more than once!!!")

                if (rec1['bin_md5'] is not None and rec2['bin_md5'] is not None and
                        rec1['bin_md5'] == rec2['bin_md5']):
                    print(f"{rec1['bin_md5']} (bin_md5) is in the DB more than once")

                if (rec1['bin_crc32'] is not None and rec2['bin_crc32'] is not None and
                        rec1['bin_crc32'] == rec2['bin_crc32']):
                    print(f"{rec1['bin_crc32']} (bin_crc32) is in the DB more than once")

                if (rec1['cowering_crc32'] is not None and rec2['cowering_crc32'] is not None and
                        rec1['cowering_crc32'] == rec2['cowering_crc32']):
                    print(f"{rec1['cowering_crc32']} (cowering_crc32) is in the DB more than once")

                if (rec1['cc3_filename'] is not None and rec2['cc3_filename'] is not None and
                        rec1['cc3_filename'] == rec2['cc3_filename']):
                    print(f"{rec1['cc3_filename']} (cc3_filename) is in the DB more than once")

                data_same = False
                attr_same = False
                if (rec1['rom_data_md5'] is not None and rec2['rom_data_md5'] is not None and
                        rec1['rom_data_md5'] == rec2['rom_data_md5']):
                    data_same = True

                if (rec1['rom_attr_md5'] is not None and rec2['rom_attr_md5'] is not None and
                        rec1['rom_attr_md5'] == rec2['rom_attr_md5']):
                    attr_same = True

                if (data_same and attr_same) is True:
                    print(f"{rec1['name']} and {rec2['name']} are the same ROM image")

                if level > 1 and data_same is True:
                    print(f"{rec1['name']} and {rec2['name']} have the same ROM data MD5")

            #
            # check the md5's on the physical files against the DB
            #

            # NOTE: cowering in the options indicates this record is only here because it is in the cowering data
            # file and does not represent real rom file(s) I own
            if level > 1 and (rec1['options'] is not None and 'cowering' not in rec1['options']):
                romfilename = "{self.roms_repository}/{rec1['cc3_filename'].upper()}"
                if os.path.isfile(romfilename) is False:
                    print(f"I can't find the rom file {rec1['id']} is referring to.")

                else:
                    w = self.wash_rom(romfilename)
                    cc3f = rec1['cc3_filename'].upper()

                    if (w['wash']['binmd5data']['bin_md5'] is not None and rec1['bin_md5'] is not None and
                            w['wash']['binmd5data']['bin_md5'] != rec1['bin_md5']):
                        print(f"The bin MD5 for {rec1['id']} in the DB doesn't match what is in the romfile in the "
                              f"repository ({cc3f})")

                    if (w['wash']['crc32'] is not None and rec1['bin_crc32'] is not None and
                            w['wash']['crc32'] != rec1['bin_crc32']):
                        print(f"The bin CRC32 for {rec1['id']} in the DB doesn't match what is in the romfile in the "
                              f"repository ({cc3f})")

                    if (w['wash']['rommd5data']['rom_data_md5'] is not None and rec1['rom_data_md5'] is not None and
                            w['wash']['rommd5data']['rom_data_md5'] != rec1['rom_data_md5']):
                        print(f"The rom data MD5 for {rec1['id']} in the DB doesn't match what is in the romfile in "
                              f"the repository ({cc3f})")

                    if (w['wash']['rommd5data']['rom_attr_md5'] is not None and rec1['rom_attr_md5'] is not None and
                            w['wash']['rommd5data']['rom_attr_md5'] != rec1['rom_attr_md5']):
                        print(f"The rom attr MD5 for {rec1['id']} in the DB doesn't match what is in the romfile in "
                              f"the repository ({cc3f})")

            #
            # other checks
            #
            if rec1['cc3_desc'] is not None and len(rec1['cc3_desc']) > 20:
                print(f"{rec1['id']} has a CC3 description that is too long.")

            if rec1['cc3_filename'] is not None and rec1['cc3_filename'] == rec1['name']:
                print(f"{rec1['id']} doesn't appear to have a valid name")

            if rec1['tags'] is None or len(rec1['tags']) == 0:
                print(f"{rec1['id']} doesn't have any tags")

            if (rec1['cc3_filename'] is None or len(rec1['cc3_filename']) == 0) and 'cowering' not in rec1['options']:
                print(f"{rec1['id']} doesn't have a cc3_filename")

            if (rec1['cc3_filename'] == rec1['name']) and (rec1['cc3_filename'] == rec1['cc3_desc']):
                print(f"{rec1['id']} doesn't appear to have a fully fleshed out record")

            if (rec1['bin_crc32'] is not None and self.cowering_data[rec1['bin_crc32']] is not None and
                    rec1['good_name'] is not None and rec1['good_name'] != self.cowering_data[rec1['bin_crc32']]):
                print(f"{rec1['id']} has a bad good_name")

            # check against Cowering's data
            if rec1['good_name'] is not None:
                found_crc = False
                for c in self.cowering_data.keys():
                    if self.cowering_data[c] == rec1['good_name']:
                        if rec1['bin_crc32'] != c and rec1['cowering_crc32'] != c:
                            print(f"{rec1['id']} has a CRC32 that doesn't match Cowering's for its good_name")
                        found_crc = True
                        break
                if found_crc is False:
                    print(f"Never found a CRC in the Cowering datafile for {rec1['id']}'s good_name")

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
                    print(f"{rec1['id']} has a variant_of that doesn't point to any valid record")

        self.banner("Checking that all Cowering CRC32s are in the DB")

        found_crc = False
        for crc in self.cowering_data.keys():
            for rec in self.db:
                if rec['bin_crc32'] == crc or rec['cowering_crc32'] == crc:
                    found_crc = True
                    if rec['good_name'] != self.cowering_data[crc]:
                        print(f"{rec['id']} has a good_name that doesn't match Cowering's")
                    break

        if found_crc is False:
            print(f"Didn't find a CRC32 in the DB for {crc}: {self.cowering_data[crc]}")

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
                    parser = FileParser()
                    rom_data, warnings = parser.calc_md5s_for_file(f"{self.roms_repository}/{romfile}")
                    rec = self.get_record_from_rom_md5s(rom_data['rom_data_md5'], rom_data['rom_attr_md5'])

                    if rec is not None:
                        print(f"{romfile} is in the repository, but it is in the DB under {rec['id']} "
                              f"({rec['cc3_filename'].upper()})")
                    else:
                        print(f"{romfile} is in the repository, but it is not in the DB")

            self.banner("Checking that all ROMs in the DB are in the roms dir")

            for dbfile in files_in_db:
                if dbfile not in files_in_repo:
                    rec = self.get_record_from_cc3filename(dbfile)
                    print("{dbfile} is referenced in the DB ({rec['id']}), but it isn't in the repository")

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
                            print(f"{rec['id']} is missing a cc3_desc")
                        elif blank_reg.search(rec['cc3_desc']) is not None:
                            print(f"{rec['id']} has a blank cc3_desc")

                        basename, ext = os.path.splitext(rec['cc3_filename'])
                        if ((not os.path.isfile(f"{self.manuals_repository}/{basename.upper()}.TXT")) and
                                ('proto' not in rec['tags']) and
                                ('demo' not in rec['tags'])):
                            print(f"{rec['id']} is referenced for the CC3, but missing a manual file "
                                  f"({basename.upper()}.TXT)")

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
                    print(f"{manfile} is in the manuals repository, but isn't referenced in the DB")

                with open(f"{self.manuals_repository}/{manfile}", 'r') as fh:
                    for line in fh.readlines():
                        line = line.strip(CRLF)
                        if len(line) > 20:
                            print(f"{manfile} has line(s) longer than 20 characters")
                            break
        return

    def dump_luigi(self, filename):
        parser = FileParser()
        data, warnings = parser.calc_crcs_for_file(filename)
        if data['rom_file_type'] != 'luigi':
            print(f"{filename} is not a luigi file.")
            return

        print("Luigi data:")
        for kkey in data['luigi_meta'].keys():
            print(f"{kkey}: {data['luigi_meta'][kkey]}")
        return

    def test(self):
        parser = FileParser()
        for rec in self.db:
            try:
                rec['encrypted'] = False
                data, warnings = parser.calc_crcs_for_file(f"{self.roms_repository}/{rec['cc3_filename']}")
                if data['rom_file_type'] == 'luigi':
                    if data['luigi_meta']['encrypted'] is True:
                        print(f"Setting encrypted status for {rec['id']} to True")
                        rec['encrypted'] = True
                        self.dirty = True
            except Exception as errmsg:
                print(f"Exception processing {rec['id']} - {str(errmsg)}")
        return


@subcommand([argument("filename", help="ROM file.")])
def dump_luigi(args):
    """ Dump data from a .luigi file. """
    inty = IntellivisionRomsDB()
    inty.dump_luigi(args.filename)
    return


@subcommand([argument("--nodos", help="Don't put DOS CR/LF endings on the lines.", action="store_true"),
             argument('--id', help='Print out game IDs (default is to print ROM filenames).', action='store_true'),
             argument("filters", help="Filter by these tags.", action="append")])
def srclist(args):
    """ Dump a list of ROMs filenames that match filters. """
    inty = IntellivisionRomsDB()

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
                sys.stdout.write(f"{rec['id']}{this_crlf}")
                sys.stdout.flush()
            else:
                if rec['cc3_filename'] is not None:
                    sys.stdout.write(f"{rec['cc3_filename'].upper()}{this_crlf}")
                    sys.stdout.flush()
    return


@subcommand([argument("--noimages", help="Don't add image information to the list.", action="store_true"),
             argument("filters", help="Filter by these tags.", action="append")])
def gamelist(args):
    """ Create a gamelist.xml for use on the MAME cab. """
    inty = IntellivisionRomsDB()
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

            fhw.write("  <game>\n")
            fhw.write(f"    <path>./{rec['cc3_filename'].upper()}</path>\n")
            fhw.write(f"    <name>{rec['name']}</name>\n")

            image = None
            if args.noimages is False:
                if rec['cc3_filename'] in boxart.keys():
                    image = f"{rec['cc3_filename']}{boxart[rec['cc3_filename']]}"
                else:
                    # maybe the variant parent?
                    if rec['variant_of'] is not None:
                        variant_rec = inty.get_record_from_id(rec['variant_of'])

                        if variant_rec['cc3_filename'] in boxart.keys():
                            image = f"{variant_rec['cc3_filename']}{boxart[variant_rec['cc3_filename']]}"

            if image is not None:
                fhw.write(f'    <image>~/.emulationstation/downloaded_images/intellivision/{image}</image>\n')
            fhw.write('    <players />\n')
            fhw.write('  </game>\n')

        fhw.write('</gameList>\n')
    return


@subcommand()
def cc3menus(args):
    """ Create CC3 menu files. """
    inty = IntellivisionRomsDB()
    menulist = []
    with open('MENULIST.TXT', 'r') as fh:
        menulist = fh.readlines()

    for line in menulist:
        cc3file = line[:8].strip()

        print(f"Writing {cc3file}.CC3")

        with open('{cc3file}.CC3', 'w') as fhw:
            if cc3file == 'MENU':
                # main menu is special, it gets a list of all other menus at the top
                for menu in menulist:
                    if menu[0:8] != 'MENU    ':
                        fhw.write(f'{menu[8:28]}{menu[0:8]}MENU')
            else:
                # non-main menu list get a return to the main menu
                #                   1         2
                #          1234567890123456789012345678
                fhw.write("---  Main Menu   ---MENU    MENU")

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
            if os.path.isfile(f"{cc3file}.LST") is True:
                with open(f'{cc3file}.LST', 'r') as fhr:
                    for line in fhr.readline():
                        rec = inty.get_record_from_id(line)
                        sorted_db.append(rec)
            else:
                sorted_db = sorted(recs, key=lambda x: x['cc3_desc'])

            for rec in sorted_db:
                basename, ext = os.path.splitext(rec['cc3_filename'])
                fhw.write(f"{rec['cc3_desc']:-20}{basename:-8}    ")
    return


@subcommand([argument("cc3menu", help="CC3 menu file.")])
def dumpcc3(args):
    """ Dump information contained in a CC3 menu file. """
    for d in cc3.get_cc3_data(args.cc3menu):
        print("|{d['desc']:-20}|{d['file']:-8}|{d['menu']:-4}|")
    return


@subcommand()
def tags(args):
    """ List all the tags present in the DB. """
    inty = IntellivisionRomsDB()
    for tag in inty.get_all_tags():
        print(tag)
    return


@subcommand([argument("id", help="Game ID."),
             argument("cfgfile", help="cfg file to add to the record.")])
def cfgfile(args):
    """ Add a .cfg file to the ROM record. """
    inty = IntellivisionRomsDB()

    rec = inty.get_record_from_id(args.id)

    if rec is None:
        print(f"Couldn't find record for ID {args.id}")
        return

    if not os.path.isfile(args.cfgfile):
        print(f"{args.cfgfile} doesn't look like a file")
        return

    with open(args.cfgfile, 'r') as fh:
        rec['cfg_file'] = ""
        for line in fh.readlines():
            rec['cfg_file'] += line.strip()
            rec['cfg_file'] += "\n"

    try:
        inty.replace_rom(rec)
        print(f"Record modified for {rec['id']}")
    except Exception:
        print(f"FAILURE: ID {rec['id']} not found in the DB during replacement (??)")
    return


@subcommand([argument("id", help="Game ID.")])
def fetchrom(args):
    """ Fetch the ROM file for a given game ID. """
    inty = IntellivisionRomsDB()
    rec = inty.get_record_from_id(args.id)

    if rec is not None:
        romfile = rec['cc3_filename'].upper()

        try:
            inty.copy_rom_file_from_repository(romfile)
            print(f"{romfile} created")
        except Exception as errmsg:
            print(f"FAILURE: {romfile} not created: {str(errmsg)}")
    else:
        print(f"Game ID {args.id} not found")
    return


@subcommand([argument("filename", help="Game filename.")])
def wash(args):
    """ "Wash" a ROM by converting to .bin and back to .rom. """
    inty = IntellivisionRomsDB()
    data = inty.wash_rom(args.filename)
    print(data)
    return


@subcommand([argument("id", help="Game ID.")])
def edit(args):
    """ Edit a ROM record in the DB. """
    inty = IntellivisionRomsDB()
    # this might be an iD
    rec = inty.get_record_from_id(args.id)

    if rec is None:
        # try via cc3filename
        rec = inty.get_record_from_cc3filename(args.id)

    if rec is None:
        print("FAILURE: record not found for edit")
        return

    rec, status = interactively_edit_record(inty, rec)
    # print(f"rlrDEBUG rec=|{str(rec)}| status=|{status}|")

    try:
        inty.replace_rom(rec)
        print(f"Record modified for {rec['id']}")
    except Exception:
        print(f"FAILURE: ID {rec['id']} not found in DB during replacement (??)")
    return


# this routine is to replace the rom file for an already defined rom (e.g. an
# update to an in-development game)

@subcommand([argument("--copy", help="Copy the ROM file into the repository.", action='store_true'),
             argument("id", help="Game ID."),
             argument("romfile", help="ROM filename being added.")])
def replacerom(args):
    """ Update a ROM definition in the DB. """
    inty = IntellivisionRomsDB()
    ID = args.id
    rec = inty.get_record_from_id(ID)

    if rec is None:
        print(f"Couldn't find {ID} in the DB.")
        return

    # wash this file
    data = inty.wash_rom(args.romfile)

    # update old data from the record that is about the physical file
    rec['bin_md5'] = data['wash']['binmd5data']['bin_md5']
    rec['rom_data_md5'] = data['wash']['rommd5data']['rom_data_md5']
    rec['rom_attr_md5'] = data['wash']['rommd5data']['rom_attr_md5']

    try:
        inty.add_or_replace_rom(rec)
        msg = f"Record for {ID} updated"

        if args.copy is True:
            force = True
            try:
                inty.copy_rom_file_to_repository(data['wash']['romfile'], rec['cc3_filename'].upper(), force)
                msg += f", copied to repository as {rec['cc3_filename'].upper()}"
            except Exception as errmsg:
                msg += f", BUT COULDN'T COPY TO REPOSITORY! {errmsg}"
        print(msg)
    except Exception as errmsg:
        print(f"Couldn't replace record in DB: {errmsg}")
    return


@subcommand([argument("--copy", help="Also copy the ROM file into the repository.", action='store_true'),
             argument("romfile", help="ROM filename being added.")])
def add(args):
    """ Add a DB record for the given ROM file. """
    inty = IntellivisionRomsDB()
    base = args.romfile

    dot_idx = base.rfind('.')
    if dot_idx > 0:
        ext = base[dot_idx + 1:]
        base = base[0:dot_idx]

    slash_idx = base.rfind('/')
    if slash_idx > 0:
        base = base[0:slash_idx]

    game_name = base.title()

    # wash this file
    data = inty.wash_rom(args.romfile)

    # print(f"rlrDEBUG data=|{data}|")

    rec, why = inty.get_record_from_wash_data(data)

    if rec is not None:
        print(f"This {data['rom_file_type'].upper()} file is already in the DB as {rec['id']}")
        return 1

    rec = {}

    # fill in any applicable cowerings data
    cowdata = inty.get_cowering_data()
    try:
        cowering_crc32 = data['bin_cowering_crc32']

        if cowering_crc32 in cowdata.keys():
            rec['good_name'] = cowdata[cowering_crc32]
            rec['bin_cowering_crc32'] = cowering_crc32
    except Exception:
        pass

    try:
        rec['cc3_filename'] = f"{base[0:8].lower()}.{ext.lower()}"
    except Exception:
        pass

    if data['rom_file_type'] == 'rom':
        try:
            rec['rom_data_crc16s'] = data['romcrcdata']['rom_data_crc16s']
        except Exception:
            pass
        try:
            rec['rom_attr_crc16'] = data['romcrcdata']['rom_attr_crc16']
        except Exception:
            pass

        try:
            rec['bin_crc32'] = data['bincrcdata']['bin_crc32']
        except Exception:
            pass

    elif data['rom_file_type'] == 'bin':
        try:
            rec['bin_crc32'] = data['bincrcdata']['bin_crc32']
        except Exception:
            pass

        try:
            rec['rom_data_crc16s'] = data['romcrcdata']['rom_data_crc16s']
        except Exception:
            pass
        try:
            rec['rom_attr_crc16'] = data['romcrcdata']['rom_attr_crc16']
        except Exception:
            pass

    elif data['rom_file_type'] == 'luigi':
        try:
            rec['luigi_crc32s'] = data['luigicrcdata']['luigi_crc32s']
        except Exception:
            pass

        meta = data['luigicrcdata']['luigi_meta']

        try:
            game_name = meta['name']
        except Exception:
            pass
        try:
            rec['author'] = meta['author']
        except Exception:
            pass
        try:
            rec['year'] = meta['year']
        except Exception:
            pass
    else:
        raise Exception(f"Unknown rom file type: {data['rom_file_type']}")

    game_id = game_name.replace(' ', '')
    game_id = game_id.replace('_', '')
    rec['cc3_desc'] = game_name[0:20]
    rec['id'] = game_id.lower()
    rec['name'] = game_name

    # uniquify the record ID if necessary
    while rec['id'] in inty.get_all_ids():
        rec['id'] += "_"

    rec, why = interactively_edit_record(inty, rec, args.romfile)

    if rec is None:
        print(f"FAILURE: {why}")
        return

    if inty.rom_file_exists_in_repository(rec['cc3_filename'].upper()):
        print(f"FAILURE: {rec['cc3_filename'].upper()} already exists in repository.")
        return

    try:
        inty.add_rom(rec)
        msg = "ROM added to DB"
        if args.copy is True:
            try:
                srcfile = data['wash']['romfile']
            except Exception:
                srcfile = args.romfile
            try:
                inty.copy_rom_file_to_repository(srcfile, rec['cc3_filename'].upper())
                msg += f", copied to repository as {rec['cc3_filename'].upper()}"
            except Exception as errmsg:
                msg += f", BUT COULDN'T COPY TO REPOSITORY! {errmsg}"
        print(msg)
    except Exception as errmsg:
        print(f"FAILURE: Couldn't add record: {errmsg}")
    return


def interactively_edit_record(inty, rec, filename=None):
    prev_id = rec['id']

    dbparser = DbParser()
    newfilename = dbparser.write_ascii_record(rec, filename)
    prev_rec_md5 = checksum.md5_hex_str(str(rec))

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

            if prev_rec_md5 == checksum.md5_hex_str(str(rec)):
                return (None, "No change to record")

            # if the iD is missing, bail here
            if 'no ID in record' in status:
                return (None, "ID missing in record")

            # if the ID is bad, go back for another edit
            if rec['id'] != prev_id:
                if 'ID in DB' in status:
                    rec['id'] = prev_id
                    newfilename = dbparser.write_ascii_record(rec)
                    print("FAILURE: you changed the ID, but the new ID is already in the DB.\nReverting the ID.")
                    input("HIT RETURN TO CONTINUE.")
                    keep_editing = True
                else:
                    rec['replace_id'] = prev_id

            if 'cc3_desc too long' in status:
                newfilename = dbparser.write_ascii_record(rec)
                print("FAILURE: the cc3_desc is too long")
                input("HIT RETURN TO CONTINUE.")
                keep_editing = True

    else:
        return (None, "Couldn't write temp file")
    return (rec, "success")


@subcommand()
def createfrinklist(args):
    """ Write a list for the arcade cabinet. """
    inty = IntellivisionRomsDB()
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

        sys.stdout.write(f"{cc3f}{CRLF}")
        sys.stdout.write(f"{name}{CRLF}")
        sys.stdout.write(f"{year}{CRLF}")
        sys.stdout.write(f"{auth}{CRLF}")
        sys.stdout.write(f"{CRLF}")             # parent rom
        sys.stdout.write(f"{CRLF}")             # unknown entry
        sys.stdout.write(f"Raster{CRLF}")
        sys.stdout.write(f"Horizontal{CRLF}")
        sys.stdout.write(f"{CRLF}")             # controller type
        sys.stdout.write(f"Status Good{CRLF}")  # any value to putting real data here?
        sys.stdout.write(f"Color Good{CRLF}")   # any value to putting real data here?
        sys.stdout.write(f"Sound Good{CRLF}")   # any value to putting real data here?
        sys.stdout.write(f"{CRLF}")             # game type
    return


@subcommand([argument("romfile", help="ROM filename.")])
def md5(args):
    """ Compute and print the MD5s for a given ROM filename. """
    parser = FileParser()
    rom_data, warnings = parser.calc_md5s_for_file(args.romfile)

    if len(warnings) > 0:
        print("WARNINGS:")
        for warn in warnings:
            print(warn)

    if rom_data['rom_file_type'] == 'bin':
        print(f"bin_md5={rom_data['bin_md5']}")
    elif rom_data['rom_file_type'] == 'rom':
        print(f"rom_data_md5={rom_data['rom_data_md5']}")
        print(f"rom_attr_md5={rom_data['rom_attr_md5']}")
    elif rom_data['rom_file_type'] == 'luigi':
        print(f"luigi crcs={str(rom_data)}")
    return


@subcommand([argument("romfile", help="ROM filename.")])
def crc32(args):
    """ Compute and print the CRCs for a given ROM filename. """
    parser = FileParser()
    rom_data, warnings = parser.calc_crcs_for_file(args.romfile)

    if len(warnings) > 0:
        print("WARNINGS:")
        for warn in warnings:
            print(warn)

    if rom_data['rom_file_type'] == 'bin':
        print(f"bin_crc32={rom_data['bin_crc32']}")
    elif rom_data['rom_file_type'] == 'rom':
        print(f"rom_data_crc16s=|{str(rom_data['rom_data_crc16s'])}|")
        print(f"rom_attr_crc16=|{str(rom_data['rom_attr_crc16'])}|")
        print(f"rom_data_crc32s=|{str(rom_data['rom_data_crc32s'])}|")
        print(f"rom_attr_crc32=|{str(rom_data['rom_attr_crc32'])}|")
    elif rom_data['rom_file_type'] == 'luigi':
        print(f"luigi crcs={str(rom_data)}")
    return


@subcommand([argument("romfile", help="ROM filename.")])
def name_from_rom_file(args):
    """ Given a ROM filename, print the DB ID. """
    inty = IntellivisionRomsDB()
    rec = inty.get_record_from_cc3filename(args.romfile)
    if rec is not None:
        print(rec['id'])
    return


@subcommand([argument("id", help="Game ID.")])
def rom_file(args):
    """ Print name of ROM file for given game ID. """
    inty = IntellivisionRomsDB()
    rec = inty.get_record_from_id(args.id)
    if rec is not None and rec['cc3_filename'] is not None:
        print(rec['cc3_filename'])
    return


@subcommand([argument("id", help="Game ID.")])
def options(args):
    """ Get options to use when running game. """
    inty = IntellivisionRomsDB()
    rec = inty.get_record_from_id(args.id)
    if rec is not None and rec['options'] is not None:
        for opt in rec['options'].split(','):
            print(opt)
    return


@subcommand([argument("id", help="Game ID.")])
def kbdhackfile(args):
    """ Get name of kbdhackfile for a given game ID. """
    inty = IntellivisionRomsDB()
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


@subcommand()
def kbdhackfiledir(args):
    """ Print the directory location that contains the kbdhackfiles. """
    inty = IntellivisionRomsDB()
    print(inty.get_kbdhackfile_dir())
    return


@subcommand([argument("id", help="Game IDs.")])
def show(args):
    """ Dump game info for a game ID. """
    inty = IntellivisionRomsDB()
    rec = inty.get_record_from_id(args.id)

    if rec is None:
        rec = inty.get_record_from_cc3filename(args.id)

    if rec is None:
        print(f"{args.id}: unknown ROM ID")
        return

    print(f'== {args.id.upper()} ==')
    dbparser = DbParser()
    for k in dbparser.get_fields_order():
        if rec[k] is not None:
            # treat multi-line fields rightly
            if k == 'cfg_file':
                print(f"--- CFG FILE ---\n{rec[k]}\n--- END CFG ---")
            else:
                # normal key-value pair
                print(f"{k}: {rec[k]}")
    return


@subcommand([argument("--tag", help="Filter list by this tag.")])
def listgames(args):
    """ List games matching tag. """
    inty = IntellivisionRomsDB()
    ids = inty.get_all_ids()
    count = 0
    for ID in ids:
        rec = inty.get_record_from_id(ID)

        if args.tag is not None and rec['tags'] is None:
            continue

        if args.tag is not None and args.tag not in rec['tags'].split(','):
            continue

        print(f"{rec['id']:-15} {rec['name']}")
        count += 1

    print(f"Total: {count} ROMs")
    return


@subcommand([argument("outfile", help="Output filename.")])
def dumpdbforpi(args):
    """ Dump the game options DB for an emulator platform. """
    inty = IntellivisionRomsDB()
    inty.dump_game_opts_db_for_emulator(args.outfile)
    return


@subcommand([argument("--copy", help="After identifying the roms, copy them to the repository.", action="store_true"),
             argument("--log", help="Write a logfile of the actions taken.", action="store_true"),
             argument("--idonly", help="Only output the ROM ids.", action="store_true"),
             argument("--cow", help="Match only based on Cowerings data.", action="store_true"),
             argument("filenames", help="ROM files to identify.", action='append')])
def which(args):
    """ Given ROM files identify them from the data in the DB. """
    inty = IntellivisionRomsDB()
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
        out = f"{filename} "

        data = inty.wash_rom(filename)

        if args.idonly is True:
            out += f"[{data['rom_file_type'].upper()}] "

        if args.cow is True:
            cc = data['orig']['crc32']
            if cc in cowdata.keys():
                if args.idonly is True:
                    out += f"{cc}: {cowdata[cc]}"
                else:
                    out += f"{cc}: UNKNOWN"
                    logpart = "unknown"
        else:
            rec, where = inty.get_record_from_wash_data(data)

        # print(f"rlrDEBUG rec={str(rec)} where={str(where)}")

        if rec is not None:
            if 'systemrom' in rec['tags'].split(','):
                systemrom = True
            if where is not None and args.idonly is False:
                out += f"[{where}] "
            out += rec['id']
            if args.idonly is False:
                out += f": {rec['name']}"

            if rec['cc3_filename'] is not None:
                fname = rec['cc3_filename'].upper()

                if os.path.isfile(f"{rep}/{fname}") is False:
                    if systemrom is False and args.copy is True:
                        out += f", copying ROM to repository as {fname}"
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
        print(f"{len(unknown)} Unknown ROMS\n{len(missing)} ROMs not in the repository\n{len(possess)} ROMs already "
              f"in the repository")

    if args.log is True:
        with open('inty_logfile.txt', 'w') as fhw:
            if len(unknown) > 0:
                fhw.write(f'--- {len(unknown)} UNKNOWNS ---\n')
                for i in unknown:
                    fhw.write(f'{i}\n')

            if len(nofiles) > 0:
                fhw.write(f'--- {len(nofiles)} MISSING CC3_FILENAMES ---\n')
                for i in nofiles:
                    fhw.write(f'{i}\n')

            if len(missing) > 0:
                fhw.write(f'--- {len(missing)} MISSING ROM FILES ---\n')
                for i in missing:
                    fhw.write(f'{i}\n')
    return


@subcommand([argument("--case", help="Case sensitive search.", action="store_true"),
             argument("search", help="Search string.")])
def search(args):
    """ Search the ROMs DB. """
    inty = IntellivisionRomsDB()

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
        out = "---\n"
        out += f"ID: {rec['id']}"
        if re.search(patt, rec['id'], regex_flags) is not None:
            print_it = True
        if (rec['name'] is not None) and (re.search(patt, rec['name'], regex_flags) is not None):
            print_it = True
            out += "\n"
            out += f"NAME: {rec['name']}"
        if (rec['good_name'] is not None) and (re.search(patt, rec['good_name'], regex_flags) is not None):
            print_it = True
            out += "\n"
            out += f"GOOD_NAME: {rec['good_name']}"
        if (rec['cc3_desc'] is not None) and (re.search(patt, rec['cc3_desc'], regex_flags) is not None):
            print_it = True
            out += "\n"
            out += f"CC3_DESC: {rec['cc3_desc']}"
        if (rec['cc3_filename'] is not None) and (re.search(patt, rec['cc3_filename'], regex_flags) is not None):
            print_it = True
            out += "\n"
            out += f"CC3_FILENAME: {rec['cc3_filename']}"
        if (rec['year'] is not None) and (re.search(patt, rec['year'], regex_flags) is not None):
            print_it = True
            out += "\n"
            out += f"YEAR: {rec['year']}"
        if (rec['comments'] is not None) and (re.search(patt, rec['comments'], regex_flags) is not None):
            print_it = True
            out += "\n"
            out += f"COMMENTS: {rec['comments']}"

        if print_it is True:
            print(out)
    return


@subcommand([argument("--level", help="Level of check to perform.", default=1),
             argument("--menufile", help="Menufile filename for CC3 checking.", nargs='?')])
def checkdb(args):
    """ Perform internal consistency checks on the data file. """
    inty = IntellivisionRomsDB()
    inty.verify_data(args.level, args.menufile)
    return


# @subcommand()
# def test(args):
#     """ Test function """
#     inty = IntellivisionRomsDB()
#     inty.test()
#     return


@subcommand([argument("--filters", help="Filter by these tags.", action="append")])
def mkrename(args):
    """ Write a rename_roms.sh bash script for use on Linux-based emulation systems that can be used to
        rename the ROM files from the 8.3 standard used by the tooling to more descriptive game names. """
    inty = IntellivisionRomsDB()
    with open('rename_roms.sh', 'w') as fhw:
        ids = inty.get_all_ids('name')

        for ID in ids:
            rec = inty.get_record_from_id(ID)

            if rec['cc3_filename'] is None:
                continue
            if rec['tags'] is None:
                continue

            _, ext = os.path.splitext(rec['cc3_filename'])
            lcext = ext.lower()

            romtags = rec['tags'].split(',')
            it_matches = True

            if args.filters is not None:
                for filt in args.filters:
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
            fhw.write(f"rm '/home/pi/RetroPie/roms/intellivision/{game_name}{lcext}' > /dev/null 2>&1\n")
            fhw.write(f"ln -s /home/pi/all_inty_roms/{rec['cc3_filename'].upper()} "
                      f"'/home/pi/RetroPie/roms/intellivision/{game_name}{lcext}'\n")
    return


@subcommand()
def rom_dir(args):
    """ Print the location of the ROMs repository. """
    inty = IntellivisionRomsDB()
    print(inty.get_roms_repository())
    return


@subcommand()
def short_help(args):
    """ Dump an abbreviated help screen for most commonly used commands. """
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


@subcommand([argument("romid", help="ROM ID to get a cfg file for")])
def get_cfg_file(args):
    """ Write a file named ROMNAME.CFG to the local directory if it exists in the record. """
    inty = IntellivisionRomsDB()
    rec = inty.get_record_from_id(args.romid)
    try:
        cfgdata = rec['cfg_file']
        if cfgdata is None:
            raise Exception("BAH")
        fname = rec['cc3_filename']
        if '.' in fname:
            fname = fname.split('.')[0]
        fname = f'{fname.upper()}.CFG'
        idir = inty.get_roms_repository()
        if os.path.isfile(f"{idir}/{fname}") is False:
            with open(fname, 'w') as fhw:
                fhw.write(cfgdata)
        print(f"CFG file {fname} written to {idir}")
    except Exception:
        print("No cfg file found.")
    return


# def inty_help(other_args=None):
#     lhelp = """
# inty command [options]
#
# where command is one of
#
# --- User commands ---
#
# which [--copy] [--log] [--idonly] [--cow] <files>
#       Report the identity of the given ROM or BIN files.
#       If --copy is given, the ROM version of the file will be copied to the
#        repository if it is not present.
#       If --log is given, a logfile will be written that details missing ROMs.
#       If --idonly is given, only the ID of the file will be displayed.
#       If --cow is given, the DB data will be ignored and the file will only be
#        matched based on the CRC data in the Cowering data file.
#
# list [--tag <tag>] [<game ID>]
#       Dump the games in the repository.
#       If a tag is given, the games list will be only those containing that tag.
#       If a game ID is given, it dumps the DB record for that game.
#
# add [--copy] <file>
#       Add a DB record for the given ROM file.
#       If --copy is given, the ROM version of the file will be copied to the
#       repository.
#
# edit <game ID>
#       Edit the DB record for the given game ID.
#
# search [--case] <pattern>
#       Search the DB for records matching the given pattern.
#       If --case is given, the search is case sensitive (defaults to case
#        insensitive).
#
# mwlist
#       Dump the games in the DB in a list file for use on the Frinkiac7 (has
#        DOS style line endings applied).
#
# srclist [-nodos] [-id] <filter>
#       Dump a list of ROMs that are tagged with the given filter.
#
# tags
#       Dump a list of valid tags.
#
# cc3menus
#       Create a set of menu files for use with the CC3.  A file named
#       MENULIST.TXT must exist in the current directory, which contains the
#       list of menus to create.
#
# fetchrom <game ID>
#       Make a local copy of the rom file for a given game ID.
#
# mkrename <filter>
#       Write a bash script that will rename all the roms matching the filter
#       to more descriptive filenames.
#
# gamelist <filter>
#       Write an .xml gamelist file for emulation station.
#
# --- Maintenance/tool related commands ---
#
# writedb
#       Just load and rewrite the DB file (good for forcing a reordering).
#
# checkdb [-l <#>] [<menulist file>]
#       Run a set of sanity checks on the DB.
#       A level of detail in checking can be specified by -l.  Levels:
#        1 - basic checking
#        2 - level 1 + reporting of missing cc3_desc, poor game names,
#             duplicate md5s
#       If a menulist file is specified, the checks to be sure all the tags
#        defined in that menulist have at least 2 records (NOT WORKING)
#
# cfgfile <game ID> <file>
#       Add the given .CFG file to the record for a given ID.
#
# md5 <file>
#       Report md5 sum(s) for the given ROM or BIN file.
#
# options <game ID>
#       Report the jzinty emulator options for the given game ID.
#        (really just for command line API purposes)
#
# dumpcc3 <CC3 menu file>
#       Dump the contents of a CC3 menu file.
#
# rom_dir
#       Report the repository directory where the ROM files are stored.
#        (really just for command line API purposes)
#
# rom_file <game ID>
#       Report the name of the ROM file for the given game ID.
#        (really just for command line API purposes)
#
# kbdhackfile <game ID>
#       Give the name of the keyboard hackfile to use for this game, or the
#        default one if none is specified in the DB.
# """
#     print(lhelp)
#     return


@subcommand()
def write_inty_data_file(args):
    """ Rewrite the data file.  Will normalize all the records and put them in ID order in the file. """
    inty = IntellivisionRomsDB()
    inty.set_dirty()
    return


if __name__ == "__main__":
    try:
        args = cli.parse_args()
        if args.subcommand is None:
            cli.print_help()
        else:
            args.func(args)
    except Exception as errmsg:
        print(f"ERROR: {str(errmsg)}")
