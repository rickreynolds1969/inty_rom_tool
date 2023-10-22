#!/usr/bin/python

import hashlib
import struct


def cowering_crc32_from_file(filename):
    return call_crc_func_for_file(filename, 'cowering_crc32')


def crc32_from_file(filename):
    return call_crc_func_for_file(filename, 'crc32')


def crc16_from_file(filename):
    return call_crc_func_for_file(filename, 'crc16')


def ieee_crc32_from_file(filename):
    return call_crc_func_for_file(filename, 'ieee_crc32')


def dow_crc8_from_file(filename):
    return call_crc_func_for_file(filename, 'dow_crc8')


def call_crc_func_for_file(filename, funcname):
    uint_8s = list()
    with open(filename, 'rb') as fh:
        ch = fh.read(1)
        while ch != b'':
            uint_8s.append(struct.unpack('B', ch)[0])
            ch = fh.read(1)

    function_map = {'cowering_crc32': cowering_crc32,
                    'crc32': crc32,
                    'crc16': crc16,
                    'ieee_crc32': ieee_crc32,
                    'dow_crc8': dow_crc8}

    try:
        func = function_map[funcname]
    except Exception:
        raise Exception(f"No crc func for {funcname}")
    return func(uint_8s, 0, len(uint_8s))


def cowering_crc32(uint_8s, start=0, length=None):
    crc_table = []
    for i in range(256):
        k = i
        for j in range(8):
            if k & 1:
                k ^= 0x1db710640
            k >>= 1
        crc_table.append(k)

    crc = 0xFFFFFFFF

    if length is None:
        length = len(uint_8s)

    for i in range(start, start + length):
        crc = (crc >> 8) ^ crc_table[(crc & 0xFF) ^ uint_8s[i]]
    return crc ^ 0xFFFFFFFF


def crc32(uint_8s, start=0, length=None):
    # Castagnoli, Brauer, Hermann CRC32/4
    #
    # Reference implementation from Joe Z
    #
    # uint32_t ref_crc32_4_update(uint32_t crc, uint8_t byte) {
    #     int i;
    #     crc ^= byte;
    #     for (i = 0; i < 8; i++) {
    #         crc = (crc >> 1) ^ (crc & 1 ? 0x82F63B78ul : 0);
    #     }
    #     return crc;
    # }
    #
    # uint32_t ref_crc32_4_block(const uint8_t *block, int length) {
    #     uint32_t crc = 0;
    #     int i;
    #     for (i = 0; i < length; i++) {
    #         crc = ref_crc32_4_update(crc, block[i]);
    #     }
    #     return crc;
    # }
    #
    # Test vectors:
    # Input                                                 Output
    # 0x00 0x01 0x02 0x03 0x04 0x05 0x06 0x07
    # 0x08 0x09 0x0A 0x0B 0x0C 0x0D 0x0E 0x0F               0x9BB99201
    # 0x4A 0x5A 0x6A 0x7A                                   0x02CB247E
    # 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00               0x00000000
    # 0xFF 0xFF 0xFF 0xFF 0xFF 0xFF 0xFF 0xFF               0xC44FF94D

    crc = 0
    crc_const = 0x82F63B78

    if length is None:
        length = len(uint_8s)

    for i in range(start, start + length):
        crc ^= uint_8s[i]
        crc &= 0xFFFFFFFF
        for j in range(0, 8):
            bitval = 0
            if (crc & 0x01) == 1:
                bitval = crc_const
            crc = (crc >> 1) ^ bitval
            crc &= 0xFFFFFFFF
    return crc


def crc16(uint_8s, start=0, length=None):
    crc_16_table = (
        0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
        0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
        0x1231, 0x0210, 0x3273, 0x2252, 0x52B5, 0x4294, 0x72F7, 0x62D6,
        0x9339, 0x8318, 0xB37B, 0xA35A, 0xD3BD, 0xC39C, 0xF3FF, 0xE3DE,
        0x2462, 0x3443, 0x0420, 0x1401, 0x64E6, 0x74C7, 0x44A4, 0x5485,
        0xA56A, 0xB54B, 0x8528, 0x9509, 0xE5EE, 0xF5CF, 0xC5AC, 0xD58D,
        0x3653, 0x2672, 0x1611, 0x0630, 0x76D7, 0x66F6, 0x5695, 0x46B4,
        0xB75B, 0xA77A, 0x9719, 0x8738, 0xF7DF, 0xE7FE, 0xD79D, 0xC7BC,
        0x48C4, 0x58E5, 0x6886, 0x78A7, 0x0840, 0x1861, 0x2802, 0x3823,
        0xC9CC, 0xD9ED, 0xE98E, 0xF9AF, 0x8948, 0x9969, 0xA90A, 0xB92B,
        0x5AF5, 0x4AD4, 0x7AB7, 0x6A96, 0x1A71, 0x0A50, 0x3A33, 0x2A12,
        0xDBFD, 0xCBDC, 0xFBBF, 0xEB9E, 0x9B79, 0x8B58, 0xBB3B, 0xAB1A,
        0x6CA6, 0x7C87, 0x4CE4, 0x5CC5, 0x2C22, 0x3C03, 0x0C60, 0x1C41,
        0xEDAE, 0xFD8F, 0xCDEC, 0xDDCD, 0xAD2A, 0xBD0B, 0x8D68, 0x9D49,
        0x7E97, 0x6EB6, 0x5ED5, 0x4EF4, 0x3E13, 0x2E32, 0x1E51, 0x0E70,
        0xFF9F, 0xEFBE, 0xDFDD, 0xCFFC, 0xBF1B, 0xAF3A, 0x9F59, 0x8F78,
        0x9188, 0x81A9, 0xB1CA, 0xA1EB, 0xD10C, 0xC12D, 0xF14E, 0xE16F,
        0x1080, 0x00A1, 0x30C2, 0x20E3, 0x5004, 0x4025, 0x7046, 0x6067,
        0x83B9, 0x9398, 0xA3FB, 0xB3DA, 0xC33D, 0xD31C, 0xE37F, 0xF35E,
        0x02B1, 0x1290, 0x22F3, 0x32D2, 0x4235, 0x5214, 0x6277, 0x7256,
        0xB5EA, 0xA5CB, 0x95A8, 0x8589, 0xF56E, 0xE54F, 0xD52C, 0xC50D,
        0x34E2, 0x24C3, 0x14A0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405,
        0xA7DB, 0xB7FA, 0x8799, 0x97B8, 0xE75F, 0xF77E, 0xC71D, 0xD73C,
        0x26D3, 0x36F2, 0x0691, 0x16B0, 0x6657, 0x7676, 0x4615, 0x5634,
        0xD94C, 0xC96D, 0xF90E, 0xE92F, 0x99C8, 0x89E9, 0xB98A, 0xA9AB,
        0x5844, 0x4865, 0x7806, 0x6827, 0x18C0, 0x08E1, 0x3882, 0x28A3,
        0xCB7D, 0xDB5C, 0xEB3F, 0xFB1E, 0x8BF9, 0x9BD8, 0xABBB, 0xBB9A,
        0x4A75, 0x5A54, 0x6A37, 0x7A16, 0x0AF1, 0x1AD0, 0x2AB3, 0x3A92,
        0xFD2E, 0xED0F, 0xDD6C, 0xCD4D, 0xBDAA, 0xAD8B, 0x9DE8, 0x8DC9,
        0x7C26, 0x6C07, 0x5C64, 0x4C45, 0x3CA2, 0x2C83, 0x1CE0, 0x0CC1,
        0xEF1F, 0xFF3E, 0xCF5D, 0xDF7C, 0xAF9B, 0xBFBA, 0x8FD9, 0x9FF8,
        0x6E17, 0x7E36, 0x4E55, 0x5E74, 0x2E93, 0x3EB2, 0x0ED1, 0x1EF0
    )

    crc = 0xFFFF

    if length is None:
        length = len(uint_8s)

    for i in range(start, start + length):
        crc = 0xFFFF & ((crc << 8) ^ crc_16_table[0xFF & ((crc >> 8) ^ uint_8s[i])])
    return crc


def md5_hex_str(data_string):
    m = hashlib.md5()

    if isinstance(data_string, list):
        for i in data_string:
            if i is not None:
                m.update(str(i).encode('utf-8'))
    else:
        m.update(str(data_string).encode('utf-8'))
    return m.hexdigest()


def ieee_crc32(uint_8s, start=0, length=None):
    # IEEE 802.3 CRC32
    #
    # Reference implementation from Joe Z
    #
    # uint32_t ref_ieee802_crc32_update(uint32_t crc, uint8_t byte) {
    #     int i;
    #     crc ^= byte;
    #     for (i = 0; i < 8; i++) {
    #         crc = (crc >> 1) ^ (crc & 1 ? 0xEDB88320ul : 0);
    #     }
    #     return crc;
    # }
    #
    # uint32_t ref_ieee802_crc32_block(const uint8_t *block, int length) {
    #     uint32_t crc = 0xFFFFFFFFul;
    #     int i;
    #     for (i = 0; i < length; i++) {
    #         crc = ref_ieee802_crc32_update(crc, block[i]);
    #     }
    #     return crc ^ 0xFFFFFFFFul;
    # }
    #
    # Test vectors:
    # Input                                                 Output
    # 0x00 0x01 0x02 0x03 0x04 0x05 0x06 0x07
    # 0x08 0x09 0x0A 0x0B 0x0C 0x0D 0x0E 0x0F               0xCECEE288
    # 0x4A 0x5A 0x6A 0x7A                                   0x9B04D72C
    # 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00               0x6522DF69
    # 0xFF 0xFF 0xFF 0xFF 0xFF 0xFF 0xFF 0xFF               0x2144DF1C

    crc = 0xFFFFFFFF
    crc_const = 0xEDB88320

    if length is None:
        length = len(uint_8s)

    for i in range(start, start + length):
        crc ^= uint_8s[i]
        crc &= 0xFFFFFFFF
        for j in range(0, 8):
            bitval = 0
            if (crc & 0x01) == 1:
                bitval = crc_const
            crc = (crc >> 1) ^ bitval
            crc &= 0xFFFFFFFF

    crc ^= 0xFFFFFFFF
    return crc


def dow_crc8(uint_8s, start=0, length=None):
    # DOWCRC
    #
    # Reference implementation from Joe Z
    #
    # uint8_t ref_dowcrc_update(uint8_t crc, uint8_t byte) {
    #     int i;
    #     crc ^= byte;
    #     for (i = 0; i < 8; i++) {
    #         crc = (crc >> 1) ^ (crc & 1 ? 0x98 : 0);
    #     }
    #     return crc;
    # }
    #
    # uint8_t ref_dowcrc_block(const uint8_t *block, int length) {
    #     uint8_t crc = 0;
    #     int i;
    #     for (i = 0; i < length; i++) {
    #         crc = ref_dowcrc_update(crc, block[i]);
    #     }
    #     return crc;
    # }
    #
    # Test vectors:
    # Input                                                 Output
    # 0x00 0x01 0x02 0x03 0x04 0x05 0x06 0x07
    # 0x08 0x09 0x0A 0x0B 0x0C 0x0D 0x0E 0x0F               0x00
    # 0x4A 0x5A 0x6A 0x7A                                   0xB8
    # 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00               0x00
    # 0xFF 0xFF 0xFF 0xFF 0xFF 0xFF 0xFF 0xFF               0x84

    crc = 0
    crc_const = 0x98

    if length is None:
        length = len(uint_8s)

    for i in range(start, start + length):
        crc ^= uint_8s[i]
        crc &= 0xFF
        for j in range(0, 8):
            bitval = 0
            if (crc & 0x01) == 1:
                bitval = crc_const
            crc = (crc >> 1) ^ bitval
            crc &= 0xFF
    return crc


if __name__ == "__main__":

    test_failed = False

    uints = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
             0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F]
    checksum = 0x9BB99201

    crc = crc32(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 1 did not match expected CRC32 checksum")
        test_failed = True

    uints = [0x4A, 0x5A, 0x6A, 0x7A]
    checksum = 0x02CB247E

    crc = crc32(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 2 did not match expected CRC32 checksum")
        test_failed = True

    uints = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    checksum = 0x00000000

    crc = crc32(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 3 did not match expected CRC32 checksum")
        test_failed = True

    uints = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
    checksum = 0xC44FF94D

    crc = crc32(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 4 did not match expected CRC32 checksum")
        test_failed = True

    if test_failed is False:
        print("All CRC32 test data sets passed.")

    test_failed = False

    uints = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
             0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F]
    checksum = 0xCECEE288

    crc = ieee_crc32(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 1 did not match expected IEEE CRC32 checksum")
        test_failed = True

    uints = [0x4A, 0x5A, 0x6A, 0x7A]
    checksum = 0x9B04D72C

    crc = ieee_crc32(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 2 did not match expected IEEE CRC32 checksum")
        test_failed = True

    uints = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    checksum = 0x6522DF69

    crc = ieee_crc32(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 3 did not match expected IEEE CRC32 checksum")
        test_failed = True

    uints = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
    checksum = 0x2144DF1C

    crc = ieee_crc32(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 4 did not match expected IEEE CRC32 checksum")
        test_failed = True

    if test_failed is False:
        print("All IEEE CRC32 test data sets passed.")

    test_failed = False

    uints = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
             0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F]
    checksum = 0x00

    crc = dow_crc8(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 1 did not match expected DOW CRC8 checksum")
        test_failed = True

    uints = [0x4A, 0x5A, 0x6A, 0x7A]
    checksum = 0xB8

    crc = dow_crc8(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 2 did not match expected DOW CRC8 checksum")
        test_failed = True

    uints = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    checksum = 0x00

    crc = dow_crc8(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 3 did not match expected DOW CRC8 checksum")
        test_failed = True

    uints = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
    checksum = 0x84

    crc = dow_crc8(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 4 did not match expected DOW CRC8 checksum")
        test_failed = True

    if test_failed is False:
        print("All DOW CRC8 test data sets passed.")

    test_failed = False

    uints = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
             0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F]
    checksum = 0xCECEE288

    crc = cowering_crc32(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 1 did not match expected Cowering CRC32 checksum")
        test_failed = True

    uints = [0x4A, 0x5A, 0x6A, 0x7A]
    checksum = 0x9B04D72C

    crc = cowering_crc32(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 2 did not match expected Cowering CRC32 checksum")
        test_failed = True

    uints = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    checksum = 0x6522DF69

    crc = cowering_crc32(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 3 did not match expected Cowering CRC32 checksum")
        test_failed = True

    uints = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
    checksum = 0x2144DF1C

    crc = cowering_crc32(uints, 0, len(uints))
    if crc != checksum:
        print("Data set 4 did not match expected Cowering CRC32 checksum")
        test_failed = True

    if test_failed is False:
        print("All Cowering CRC32 test data sets passed.")
