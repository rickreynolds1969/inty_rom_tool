#!/usr/bin/env python3

import sys
import os
import re

tool_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(tool_dir)

from file_parser import FileParser


class DbParser(FileParser):
    def __init__(self):
        self.db_delimiter = '#--- 8< cut here 8< ---'
        self.fields_order = ('id', 'name', 'flashback_name', 'good_name', 'rom_data_md5', 'rom_attr_md5', 'bin_md5',
                             'bin_crc32', 'cowering_crc32', 'rom_data_crc16s', 'rom_attr_crc16', 'luigi_crc32s',
                             'encrypted', 'cc3_desc', 'cc3_filename', 'tags', 'paid', 'variant_of', 'author', 'year',
                             'options', 'kbdhackfile', 'cfg_file', 'comments')
        return

    def read_inty_data_file(self, filename):
        db_header = ''
        d = []
        with open(filename, 'r') as fh:
            # first loop is just slurping up the file header - up to the first blank line
            while True:
                line = fh.readline().rstrip()

                if line == "":
                    break

                db_header = f"{db_header}{line}"
                db_header += "\n"

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

                rec[multi_line_attr] = f"{rec[multi_line_attr]}{line}"
                rec[multi_line_attr] += "\n"
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
            if os.path.isfile(f"{inty_data_file}.bak.{j}"):
                os.rename(f"{inty_data_file}.bak.{j}", f"{inty_data_file}.bak.{i}")

        # save current file as backup
        if os.path.isfile(inty_data_file):
            os.rename(inty_data_file, f"{inty_data_file}.bak.0")

        sorted_db = sorted(self.db, key=lambda x: x['id'])
        self.db = sorted_db

        with open(inty_data_file, "w") as fh:
            fh.write(self.db_header)
            fh.write('\n')

            for rom in self.db:
                self.write_ascii_record_to_file(fh, rom)

        # with open('inty_data_file.yaml', 'w') as fh:
        #     yaml.dump(self.db, fh)

        self.dirty = False
        return

    def write_ascii_record(self, rom, filename=None):
        if isinstance(rom, str):
            rom = self.get_record_from_id(rom)
        output = None
        if rom is not None:
            pid = os.getpid()
            outfile = f'{self.temp_dir}/temprec.{pid}'
            with open(outfile, 'w') as fh:
                fh.write("# To cancel edit of record, delete the line containing the ID\n")
                if filename is not None:
                    fh.write(f"# FILENAME: {filename}")
                    fh.write("\n")
                self.write_ascii_record_to_file(fh, rom)
            output = outfile
        return output

    def write_ascii_record_to_file(self, fh, rec):
        # print(f"rlrDEBUG write_ascii_record_to_file: rec=|{str(rec)}|")
        for k in self.fields_order:
            if k == 'cc3_desc':
                fh.write('#c3_desc=12345678901234567890\n')
            if k == 'tags':
                fh.write('# possible tags:{",".join(self.get_all_tags())}\n')

            if k not in rec.keys() or rec[k] is None:
                fh.write(f'{k}=\n')
                continue

            # NOTE: due to the above continue, rec[k] must exist and has a value

            if '\n' in str(rec[k]):
                fh.write(f'{k}_multi_line_begin\n')
                fh.write(rec[k])
                fh.write(f'{k}_multi_line_end\n')
            else:
                fh.write(f'{k}{rec[k]}\n')

        fh.write('\n{self.db_delimiter}\n\n')
        return
