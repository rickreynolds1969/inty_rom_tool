#!/usr/bin/perl

package INTY;
use strict;
use Cowering;
use CC3;
use Digest::MD5;
use FileHandle;

#
# singleton pattern: this constructor will always return the same object
#
my $oneTrueSelf;

sub new {
  return $oneTrueSelf ||= (shift)->instance();
}

sub instance {
  my ($class) = @_;
  my ($data) = {};

  my $dir = "/Users/rick/inty_roms_tool";
  #my $dir = "/media/psf/Home/inty_roms_tool";

  $data->{inty_tool_dir} = $dir;
  $data->{cowering_file} = "$dir/inty_203.dat";
  $data->{inty_data_file} = "$dir/inty_data.dat";
  $data->{roms_repository} = "$dir/roms";
  $data->{boxart_repository} = "$dir/boxart";
  $data->{manuals_repository} = "$dir/cc3_manuals";
  $data->{kbdhackfile_dir} = "$dir/kbdhackfiles";
  $data->{laptop_default_kbdhackfile} = "basicnoecs";
  $data->{laptop_default_ecs_kbdhackfile} = "basic";
  $data->{frinkiac7_default_kbdhackfile} = "basic";
  $data->{temp_dir} = "/tmp";
  $data->{db_delimiter} = "#--- 8< cut here 8< ---";
  $data->{fields_order} = [ 'id', 'name', 'flashback_name', 'good_name',
    'rom_data_md5', 'rom_attr_md5', 'bin_md5', 'bin_crc32', 'cowering_crc32',
    'cc3_desc', 'cc3_filename', 'tags', 'variant_of', 'author', 'year',
    'options', 'kbdhackfile', 'cfg_file', 'comments' ];
  $data->{dirty} = 0;
  $data->{number_of_backups_to_keep} = 9;
  #$data->{bin2rom} = "/Users/rick/Gaming/Emulation/jzintv-1.0-beta-mac/bin/bin2rom";
  #$data->{rom2bin} = "/Users/rick/Gaming/Emulation/jzintv-1.0-beta-mac/bin/rom2bin";
  $data->{bin2rom} = "/Users/rick/jzintv/bin/bin2rom";
  $data->{rom2bin} = "/Users/rick/jzintv/bin/rom2bin";

  ($data->{db},$data->{db_header}) = INTY::read_inty_data_file($data->{inty_data_file});
  $data->{cowering_data} = Cowering::read_cowering_data($data->{cowering_file});

  return(bless($data, $class));
}



sub calc_md5_for_file {
  my ($self,$filename) = @_;

  die "$filename doesn't seem to be a file\n"
   if (! -f "$filename");

  open FH, $filename or die "Cannot open $filename: $!\n";
  binmode FH;

  # Here's a short description of the ROM format's overall structure:
  #   
  # 1.  Header  (3 bytes)
  #     a.  Signature / auto-baud byte (0xA8 for Intellicart, 0x41 for CC3 if 
  #         I recall).
  #     b.  Byte indicating # of ROM segments that follow the header.
  #     c.  Byte containing 1s complement of 1(b)
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
  
  seek(FH,0,2);       # find the end of the file
  my $len = tell(FH); # len should be the length of the file
  seek(FH,0,0);       # go back to the front for read

  my $data;
  read(FH,$data,$len);
  close FH;

  my @warnings;
  my %data;

  $data{file_length} = $len;

  # get the data into unsigned 8-bit ints
  my @uint_8s = unpack("C*",$data);

  my $bin_or_rom = "rom";

  # the 3-byte header (1)
  #  a rom file will have the 1's complement data, if it isn't there, assume 
  #  a bin
  $bin_or_rom = "bin"
   if ($uint_8s[1] != (0xff ^ $uint_8s[2]));

  my $flag = $uint_8s[0];
  if ($flag == 0xa8) {
    $data{icart_or_cc3} = "icart";

  } elsif (($flag == 0x41) || ($flag == 0x61)) {
    $data{icart_or_cc3} = "cc3";

  } else {
    $bin_or_rom = "bin";
  }

  print "rlrDEBUG $data{file_length}\n";
  print "rlrDEBUG $bin_or_rom\n";
  print "rlrDEBUG $data{icart_or_cc3}\n";


  if ($bin_or_rom eq "bin") {
    $data{bin_md5} = Digest::MD5::md5_hex(@uint_8s);
    
  } else {
    $data{num_data_segments} = $uint_8s[1];

    print "rlrDEBUG num_data_segments=$data{num_data_segments}\n";
  
    # read the rom segments (2)
    my $ofs = 3;
    my @rom_data;
    for (1 .. $uint_8s[1]) {
      my $start_of_this_block = $ofs;
      my $lo = $uint_8s[$ofs++] << 8;
      my $hi = ($uint_8s[$ofs++] << 8) + 0x100;
  
      push @warnings, "Bad rom segment defined (hi addr below lo)"
       if ($hi < $lo);
  
      print "rlrDEBUG rom segment from $lo to $hi\n";
      # get this rom segment
      for (my $j=$lo; $j < $hi; $j++) {
        $rom_data[$j] = ($uint_8s[$ofs] << 8) | ($uint_8s[$ofs+1] & 0xFF);
        $ofs += 2;
      }

      print "rlrDEBUG rom_data len=" . scalar(@rom_data) . "\n";
      print "rlrDEBUG location of cfc_expect=|$ofs|\n";

      # check the CRC-16 (for grins?)
      my $crc_expect = ($uint_8s[$ofs] << 8) | ($uint_8s[$ofs+1] & 0xFF);
      my $crc_actual = crc_16_block(\@uint_8s, $start_of_this_block, 2 * ($hi - $lo) + 2);

      print "rlrDEBUG crc_expect=|$crc_expect| crc_actual=|$crc_actual|\n";
      push @warnings, "Block found whose CRC entry doesn't match the CRC of the actual data: CRC in rom=%x, CRC calculated=%x\n", $crc_expect, $crc_actual
       if ($crc_expect != $crc_actual);
  
      # skip the CRC data
      $ofs += 2;
    }
  
    # read the attribute & fine address tables (3 & 4)
    my $start_of_attribute_table = $ofs;
    my @attr;
    for (1 .. 48) {
      push @attr, $uint_8s[$ofs++];
    }
  
    print "rlrDEBUG location of cfc_expect=|$ofs|\n";

    # check the CRC of the previous tables (5)
    my $crc_expect = ($uint_8s[$ofs] << 8) |
                  ($uint_8s[$ofs+1] & 0xFF);
    my $crc_actual = crc_16_block(\@uint_8s, $start_of_attribute_table, 48);

    print "rlrDEBUG crc_expect=|$crc_expect| crc_actual=|$crc_actual|\n";
    push @warnings, "Attribute and fine address tables' CRC entry doesn't match the CRC of the actual data: CRC in rom=%x, CRC calculated=%x\n", $crc_expect, $crc_actual
     if ($crc_expect != $crc_actual);
  
    $ofs += 2;

    # print "rlrDEBUG rom_data=\n";
    # for my $i (0 .. $#rom_data) {
    #   printf "%03d ", $rom_data[$i];
    #   if (($i % 20) == 0) {
    #     print "\n";
    #   }
    # }
    # print "\n";

  
    $data{processed_bytes} = $ofs;
    my $data_str = join('', @rom_data);
    #print "rlrDEBUG data_str=|$data_str|\n";
    $data{rom_data_md5} = Digest::MD5::md5_hex($data_str);
    $data_str = join('', @attr);
    #print "rlrDEBUG data_str=|$data_str|\n";
    $data{rom_attr_md5} = Digest::MD5::md5_hex($data_str);
  }

  return (\%data, \@warnings);
}


sub crc_16_block {
  my ($data_r, $start, $len) = @_;

  my @crc_16_table = (
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
   );

  my $crc = 0xFFFF;
  for (my $i=$start; $i < ($start + $len); $i++) {
    $crc = 0xFFFF & 
     (($crc << 8) ^ $crc_16_table[0xFF & (($crc >> 8) ^ $data_r->[$i])]);
  }

  return $crc;
}

sub get_db {
  my ($self) = @_;
  return $self->{db};
}

sub get_number_of_records {
  my ($self) = @_;
  return scalar(@{$self->{db}});
}


sub get_record_from_name {
  my ($self,$name) = @_;
  return $self->get_record_from_FIELD("name",$name);
}

sub get_record_from_goodname {
  my ($self,$name) = @_;
  return $self->get_record_from_FIELD("good_name",$name);
}

sub get_record_from_cc3name {
  my ($self,$name) = @_;
  return $self->get_record_from_FIELD("cc3_filename",$name);
}

sub get_record_from_rom_md5s {
  my ($self,$datamd5,$attrmd5) = @_;
  $self->get_record_from_FIELDS("rom_data_md5|rom_attr_md5","$datamd5|$attrmd5");
}

sub get_record_from_bin_md5 {
  my ($self,$md5) = @_;
  return $self->get_record_from_FIELD("bin_md5",$md5);
}

sub get_record_from_bin_crc32 {
  my ($self,$md5) = @_;
  return $self->get_record_from_FIELD("bin_crc32",$md5);
}

sub get_record_from_cowering_crc32 {
  my ($self,$md5) = @_;
  return $self->get_record_from_FIELD("cowering_crc32",$md5);
}


sub get_record_from_id {
  my ($self,$id) = @_;
  return $self->get_record_from_FIELD("id",$id);
}

sub get_all_records_from_tag {
  my ($self,$tag) = @_;

  my @recs;

  for my $rom (@{$self->{db}}) {
    if (defined $rom->{tags}) {
      push @recs, $rom
       if (grep(($_ eq $tag),(split /,/,$rom->{tags})));
    }
  }

  return \@recs;
}

sub get_all_tags {
  my ($self) = @_;

  my %seen = ();
  my @all_tags = ();

  for my $rom (@{$self->{db}}) {
    push @all_tags, (split /,/,$rom->{tags})
     if (defined $rom->{tags});
  }

  # NOTE: this is a recipe to uniquify a list
  return grep { ! $seen{$_}++ } @all_tags;
}

sub get_all_ids {
  my ($self,$field) = @_;
  my @ids;

  my @sorted = @{$self->{db}};

  if (defined $field) {
    @sorted = sort { $a->{$field} cmp $b->{$field} } @{$self->{db}};
  }

  for my $rom (@sorted) {
    push @ids, $rom->{id};
  }
  
  return @ids;
}

sub get_record_from_FIELD {
  my ($self,$field,$value) = @_;

  # special cases
  $value = lc($value) if ($field eq "cc3_filename");

  for my $rom (@{$self->{db}}) {
    if (defined $rom->{$field}) {
      return $rom if ($rom->{$field} eq $value);
    }
  }
  return undef;
}

sub get_record_from_FIELDS {
  my ($self,$fields,$values) = @_;

  my @fields = split /\|/, $fields;
  my @values = split /\|/, $values;

  for my $rom (@{$self->{db}}) {
    my $found = 1;

    for my $i (0 .. $#fields) {
      my $field = $fields[$i];
      my $value = $values[$i];

      if (! defined $rom->{$field}) {
        $found = 0;
        last;
      }

      # special cases
      $value = lc($value) if ($field eq "cc3_filename");

      if ($rom->{$field} ne $value) {
        $found = 0;
        last;
      }
    }

    return $rom if ($found);
  }

  return undef;
}

sub get_record_from_wash_data {
  my ($self, $wash) = @_;

  # algorithm:

  # if ROM
  # 1. check original file via rom md5s
  # 2. check washed file via rom md5s
  # 3. check washed file via bin md5
  # 4. check washed file via bin crc32

  # if BIN
  # 1. check original file via bin md5
  # 2. check original file via bin crc32
  # 3. check original file via cowering crc32
  # 4. check washed file via bin md5
  # 5. check washed file via bin crc32

  my ($md5data, $rec);
  $md5data = $wash->{orig}->{md5data};

  if ($wash->{romorbin} eq "rom") {
    $rec = $self->get_record_from_rom_md5s($md5data->{rom_data_md5}, $md5data->{rom_attr_md5});
    return ($rec, "ORIG ROM MD5") if (defined $rec);

    $md5data = $wash->{wash}->{rommd5data};

    $rec = $self->get_record_from_rom_md5s($md5data->{rom_data_md5}, $md5data->{rom_attr_md5});
    return ($rec, "WASH ROM MD5") if (defined $rec);

    $md5data = $wash->{wash}->{binmd5data};

    $rec = $self->get_record_from_bin_md5($md5data->{bin_md5});
    return ($rec, "WASH BIN MD5") if (defined $rec);

    $rec = $self->get_record_from_bin_crc32($wash->{wash}->{crc32});
    return ($rec, "WASH BIN CRC32") if (defined $rec);


  } else {
    $rec = $self->get_record_from_bin_md5($md5data->{bin_md5});
    return ($rec, "ORIG BIN MD5") if (defined $rec);

    $rec = $self->get_record_from_bin_crc32($wash->{orig}->{crc32});
    return ($rec, "ORIG BIN CRC32") if (defined $rec);

    $rec = $self->get_record_from_cowering_crc32($wash->{orig}->{crc32});
    return ($rec, "ORIG COWERING CRC32") if (defined $rec);

    $md5data = $wash->{wash}->{md5data};

    $rec = $self->get_record_from_rom_md5s($md5data->{rom_data_md5}, $md5data->{rom_attr_md5});
    return ($rec, "WASH ROM MD5") if (defined $rec);

    $rec = $self->get_record_from_bin_md5($md5data->{bin_md5});
    return ($rec, "WASH BIN MD5") if (defined $rec);

    $rec = $self->get_record_from_bin_crc32($wash->{wash}->{crc32});
    return ($rec, "WASH BIN CRC32") if (defined $rec);
  }

  return undef;
}


sub validate_record {
  my ($self, $rec) = @_;

  # this method is designed to be called after a user edit of a record

  my @statuses;

  # check 1: ID
  if (grep(($_ eq 'id'),(keys %$rec))) {
    push @statuses, "ID in DB"
     if (grep(($_ eq $rec->{id}),$self->get_all_ids()));
  } else {
    push @statuses, "no ID in record";
  }

  # check 2: ROM filename
  if (grep(($_ eq 'cc3_filename'),(keys %$rec))) {
    my $romfile1 = "$self->{roms_repository}/" . uc($rec->{cc3_filename}) . ".ROM";
    my $romfile2 = "$self->{roms_repository}/" . uc($rec->{cc3_filename});
    if ((-f $romfile1) || ( -f $romfile2)) {
      push @statuses, "ROM in repository"
    } else {
      push @statuses, "no ROM in repository"
    }
  }

  # check 3: cc3_desc
  if (grep(($_ eq 'cc3_desc'),(keys %$rec))) {
    push @statuses, "cc3_desc too long"
     if (length($rec->{cc3_desc}) > 20);
  }

  return \@statuses;
}



sub get_temp_dir {
  my ($self) = @_;
  return $self->{temp_dir};
}


# static function, should only be called from other class methods (really 
# only on object creation)
sub read_inty_data_file {
  my ($filename) = @_;
  my $fh = FileHandle->new;
  $fh->open("< $filename") or die "Cannot open the dat file: $!\n";
  
  my @d = ();
  my $db_header = "";

  while (1) {
    my $line = $fh->getline();
    chomp($line);
    
    last if ($line =~ m/^\s*$/);

    $db_header .= "$line\n";
  }
  
  while (! $fh->eof()) {
    my $rec = parse_ascii_record_from_file($fh);
    push @d, $rec if (defined $rec);
  }
  
  close $fh;

  return (\@d, $db_header);
}


sub parse_ascii_record {
  my ($self, $file) = @_;

  my $fh = FileHandle->new;
  $fh->open("< $file") or die "Cannot open temp file: $!\n";

  my $rec = parse_ascii_record_from_file($fh);
  
  close $fh;
  
  return $rec;
}


sub parse_ascii_record_from_file {
  my ($fh) = @_;

  my $rec;
  my $in_multi_line = 0;
  my $multi_line_attr;

  while (1) {
    my $line = $fh->getline();
    last if (! defined $line);

    chomp($line);

    # blank lines are saved in multi-line attrs
    next if (($line =~ m/^\s*$/) && (! $in_multi_line));

    # I'd love to have this be in only one place...
    last if ($line =~ m/#--- 8< cut here 8< ---/);

    next if ($line =~ m/^#/);

    # if we're in a multi-line attribute, save entire line looking for the 
    # end of data sentinel
    if ($in_multi_line) {
      if ($line =~ m/_multi_line_end$/) {
        $in_multi_line = 0;
        next;
      }
  
      $rec->{$multi_line_attr} .= "$line\n";
      next;
    }

    # if the line in _multi_line, this is a multi-line
    if ($line =~ m/_multi_line_begin$/) {
      $in_multi_line = 1;
      ($multi_line_attr = $line) =~ s/_multi_line_begin$//;
      next;
    }

    my ($attr,$value) = split /=/,$line;

    next if ($value eq "");
  
    # save the value for this attribute
    $rec->{$attr} = $value;
  }

  return $rec;
}

# this is called from DESTROY, so it really isn't necessary in most other contexts
sub write_inty_data_file {
  my ($self) = @_;

  my $inty_data_file = $self->{inty_data_file};

  # rotate old backups
  for (my $i=$self->{number_of_backups_to_keep}; $i > 0; $i--) {
    my $j = $i - 1;
    rename "$inty_data_file.bak.$j", "$inty_data_file.bak.$i"
     if (-f "$inty_data_file.bak.$j");
  }

  # save this backup
  rename "$inty_data_file", "$inty_data_file.bak.0"
   if (-f "$inty_data_file");

  # sort the data structure by game id (arbitrary, really, there isn't 
  # anything in the data structure that relies on it being in any order)
  my @tmp = sort { $a->{id} cmp $b->{id} } @{$self->{db}};
  $self->{db} = \@tmp;

  my $fhw = FileHandle->new;
  $fhw->open("> $inty_data_file") or die "Cannot open output datafile: $!\n";

  print $fhw "$self->{db_header}\n";

  for my $rom (@{$self->{db}}) {
    $self->write_ascii_record_to_file($fhw,$rom);
  }

  close $fhw;
  $self->{dirty} = 0;
}


sub write_ascii_record {
  my ($self, $rom, $filename) = @_;

  $rom = $self->get_record_from_id($rom) if (! ref $rom);

  my $retval = undef;

  if (defined $rom) {
    open my $fhw, "> $self->{temp_dir}/temprec.$$" or die "Cannot open temp file: $!\n";
    print $fhw "# To cancel edit of record, delete the line containing the ID\n";
    print $fhw "# FILENAME: $filename\n" if (defined $filename);

    $self->write_ascii_record_to_file($fhw,$rom);
  
    close $fhw;

    $retval = "$self->{temp_dir}/temprec.$$";
  }

  return $retval;
}


sub write_ascii_record_to_file {
  my ($self, $fhw, $rec) = @_;

  for my $k (@{$self->{fields_order}}) {
    # skip if this record doesn't have this field
    if (! defined $rec->{$k}) {
      print $fhw "#c3_desc=12345678901234567890\n"
       if ($k eq 'cc3_desc');
      print $fhw "# possible tags:" . join(",",$self->get_all_tags()) . "\n"
       if ($k eq 'tags');
      print $fhw "$k=\n";
      next;
    }

    # write out the field for this record (2 types: regular and multi-line)
    if ($rec->{$k} =~ m/\n/) {
      print $fhw "${k}_multi_line_begin\n";
      # the multi-line input parser puts \n on each line, so we don't need 
      # to put one on the end of the data here
      print $fhw "$rec->{$k}";
      print $fhw "${k}_multi_line_end\n";
    } else {
      print $fhw "#c3_desc=12345678901234567890\n"
       if ($k eq 'cc3_desc');

      print $fhw "# possible tags:" . join(",",$self->get_all_tags()) . "\n"
       if ($k eq 'tags');
      print $fhw "$k=$rec->{$k}\n";
    }
  }

  print $fhw "\n$self->{db_delimiter}\n\n";
}



sub rom_file_exists_in_repository {
  my ($self, $romname) = @_;

  my $retval = 0;
  my $rep = $self->{roms_repository};

  if (-e "$rep/$romname") {
    $retval = 1;
  }

  return $retval;
}



sub copy_rom_file_to_repository {
  my ($self, $src, $dest, $force) = @_;

  my $retval = "success";
  my $rep = $self->{roms_repository};

  if ((! -f "$rep/$dest") || ($force)) {
    system("cp $src $rep/$dest");
  } else {
    $retval = "failure";
  }

  return $retval;
}


sub copy_rom_file_from_repository {
  my ($self, $romfile, $force) = @_;

  my $retval = "success";
  my $rep = $self->{roms_repository};

  if ((! -f "$romfile") || ($force)) {
    system("cp $rep/$romfile .");
  } else {
    $retval = "failure";
  }

  return $retval;
}




# just adds a rom structure to the DB
sub add_rom {
  my ($self, $rom_rec) = @_;

  # only add unique records
  my $found = 0;
  for my $i (0 .. $#{$self->{db}}) {
    if ($self->{db}->[$i]->{id} eq $rom_rec->{id}) {
      $found = 1;
      last;
    }
  }

  my $retval = "failure";
  if (! $found) {
    push @{$self->{db}},$rom_rec;
    $self->{dirty} = 1;
    $retval = "success";
  }
  
  return $retval;
}

# find a rom structure in the DB by its ID and replace it with the given one
sub replace_rom {
  my ($self, $new_rec) = @_;

  my $findid = $new_rec->{id};

  # replacing a rom's info while also replacing its ID is a special case
  if (grep(($_ eq 'replace_id'),(keys %$new_rec))) {
    $findid = $new_rec->{replace_id};
    delete $new_rec->{replace_id};
  }

  my $game_num = -1;
  for my $i (0 .. $#{$self->{db}}) {
    if ($self->{db}->[$i]->{id} eq $findid) {
      $game_num = $i;
      last;
    }
  }

  my $retval = "failure";

  if ($game_num >= 0) {
    $self->{db}->[$game_num] = $new_rec;
    $self->{dirty} = 1;
    $retval = "success";
  }

  return $retval;
}


sub add_or_replace_rom {
  my ($self, $new_rec) = @_;

  my $suc = $self->replace_rom($new_rec);

  if ($suc ne "success") {
    # rom wasn't in the DB, add it
    $suc = $self->add_rom($new_rec);
  }

  return $suc;
}


sub len {
  my ($self) = @_;

  return $#{$self->{db}}
}


sub wash_rom {
  my ($self, $filename) = @_;

  # first, decide if this is a rom or bin
  my ($origmd5data, $origwarnings) = $self->calc_md5_for_file("$filename");

  my $tmp = $self->{temp_dir};

  my $bin2rom = $self->{bin2rom};
  my $rom2bin = $self->{rom2bin};

  my ($binmd5data, $rommd5data, $warnings, $romorbin, $ocrc, $wcrc);

  system("rm -f $tmp/xxx.bin $tmp/xxx.cfg $tmp/xxx.rom > /dev/null");

  $filename =~ s/'/'\\''/g;

  my $basename = $filename;
  $basename =~ s/\..+$//;

  if (grep(($_ eq "bin_md5"),(keys %$origmd5data))) {
    # a bin file wash
    $romorbin = "bin";
    
    system("cp '$filename' $tmp/xxx.bin");
    system("cp '$basename.cfg' $tmp/xxx.cfg")
     if (-f "$basename.cfg");
    system("cp '$basename.CFG' $tmp/xxx.cfg")
     if (-f "$basename.CFG");

    $ocrc = Cowering::crc32("$tmp/xxx.bin");

    system("cd $tmp ; $bin2rom xxx.bin > /dev/null");
    system("rm -f $tmp/xxx.bin $tmp/xxx.cfg 2> /dev/null");
    system("cd $tmp ; $rom2bin xxx.rom > /dev/null");

    $wcrc = Cowering::crc32("$tmp/xxx.bin");

    ($binmd5data, $warnings) = $self->calc_md5_for_file("$tmp/xxx.bin");
    ($rommd5data, $warnings) = $self->calc_md5_for_file("$tmp/xxx.rom");

  } else {
    # a rom file wash
    $romorbin = "rom";
    system("cp '$filename' $tmp/xxx.rom");
    system("cd $tmp ; $rom2bin xxx.rom > /dev/null");
    system("rm -f $tmp/xxx.rom 2> /dev/null");
    system("cd $tmp ; $bin2rom xxx.bin > /dev/null");

    ($rommd5data, $warnings) = $self->calc_md5_for_file("$tmp/xxx.rom");
    ($binmd5data, $warnings) = $self->calc_md5_for_file("$tmp/xxx.bin");
    $wcrc = Cowering::crc32("$tmp/xxx.bin");
  }

  # now bundle up the info
  my $ret = {};
  $ret->{orig} = {};
  $ret->{orig}->{md5data} = $origmd5data;
  $ret->{orig}->{crc32} = $ocrc
   if (defined $ocrc);

  $ret->{wash} = {};
  $ret->{wash}->{binmd5data} = $binmd5data;
  $ret->{wash}->{rommd5data} = $rommd5data;
  $ret->{wash}->{crc32} = $wcrc;
  $ret->{wash}->{binfile} = "$tmp/xxx.bin";
  $ret->{wash}->{romfile} = "$tmp/xxx.rom";
  $ret->{wash}->{cfgfile} = "$tmp/xxx.cfg";
  $ret->{romorbin} = $romorbin;
  $ret->{binorrom} = $romorbin;

  return $ret;
}


# some sanity checks on the DB
#
# still todo:
# - if a record has a crc32 defined, it should also have a good_name, and 
#   that good_name should be the same as the record in the inty_203.dat file.
# - vice versa of above
# - every record in the inty_203.dat file should be represented in the DB.

sub verify_data {
  my ($self,$level,$menufile) = @_;

  my $dir = $self->{roms_repository};
  my $coweringdata = $self->{cowering_data};

  my %gamenamesout;
  my %goodnamesout;
  my %binmd5sout;
  my %bincrc32sout;
  my %cc3fout;
  my %idsout;
  my %coweringcrc32sout;

  #
  #  First set of checks: consistency within the DB itself
  #
  print "=== Checking for repeated game data and repeated ROMs in the DB ===\n";
  for (my $this_rom=0; $this_rom < @{$self->{db}}; $this_rom++) {
    for (my $i=0; $i < @{$self->{db}}; $i++) {
      next if ($this_rom == $i);

      print "$self->{db}->[$this_rom]->{name} (game name) is in the DB more than once\n"
       if (($self->{db}->[$this_rom]->{name} eq $self->{db}->[$i]->{name}) &&
           (! $gamenamesout{$self->{db}->[$i]->{name}}++));

      print "$self->{db}->[$this_rom]->{good_name} (good name) is in the DB more than once\n"
       if (($self->{db}->[$this_rom]->{good_name} eq $self->{db}->[$i]->{good_name}) &&
           ($self->{db}->[$this_rom]->{good_name} !~ m/^\s*$/) &&
           (! $gamenamesout{$self->{db}->[$i]->{good_name}}++));

      print "$self->{db}->[$this_rom]->{id} (id) is in the DB more than once\n"
       if (($self->{db}->[$this_rom]->{id} eq $self->{db}->[$i]->{id}) &&
           (! $idsout{$self->{db}->[$i]->{id}}++));

      print "$self->{db}->[$this_rom]->{bin_md5} (bin_md5) is in the DB more than once\n"
       if (($self->{db}->[$this_rom]->{bin_md5} ne "") &&
           ($self->{db}->[$this_rom]->{bin_md5} eq $self->{db}->[$i]->{bin_md5}) &&
           (! $binmd5sout{$self->{db}->[$i]->{bin_md5}}++));

      print "$self->{db}->[$this_rom]->{bin_crc32} (bin_crc32) is in the DB more than once\n"
       if (($self->{db}->[$this_rom]->{bin_crc32} eq $self->{db}->[$i]->{bin_crc32}) &&
           ($self->{db}->[$this_rom]->{bin_crc32} ne "") &&
           (! $bincrc32sout{$self->{db}->[$i]->{bin_crc32}}++));

      print "$self->{db}->[$this_rom]->{cowering_crc32} (cowering_crc32) is in the DB more than once\n"
       if (($self->{db}->[$this_rom]->{cowering_crc32} eq $self->{db}->[$i]->{cowering_crc32}) &&
           ($self->{db}->[$this_rom]->{cowering_crc32} ne "") &&
           (! $coweringcrc32sout{$self->{db}->[$i]->{cowering_crc32}}++));

      print "$self->{db}->[$this_rom]->{cc3_filename} is the cc3_filename for more than one rom\n"
       if (($self->{db}->[$this_rom]->{cc3_filename} ne "") &&
           ($self->{db}->[$this_rom]->{cc3_filename} eq 
            $self->{db}->[$i]->{cc3_filename}) &&
           (! $cc3fout{$self->{db}->[$i]->{cc3_filename}}++));

      my $data_same = 0;
      if ((defined $self->{db}->[$this_rom]->{rom_data_md5}) &&
          (defined $self->{db}->[$i]->{rom_data_md5})) {
        $data_same = 1
         if ($self->{db}->[$this_rom]->{rom_data_md5} eq $self->{db}->[$i]->{rom_data_md5});
      }

      my $attr_same = 0;
      if ((defined $self->{db}->[$this_rom]->{rom_attr_md5}) &&
          (defined $self->{db}->[$i]->{rom_attr_md5})) {
        $attr_same = 1
         if ($self->{db}->[$this_rom]->{rom_attr_md5} eq $self->{db}->[$i]->{rom_attr_md5});
      }

      if ($data_same && $attr_same) {
        print "$self->{db}->[$this_rom]->{name} and $self->{db}->[$i]->{name} are the same ROM.\n";
      }


      if ($level > 1) {
        if ((defined $self->{db}->[$this_rom]->{rom_data_md5}) &&
            (defined $self->{db}->[$i]->{rom_data_md5})) {
          print "$self->{db}->[$this_rom]->{name} and $self->{db}->[$i]->{name} have the same rom data MD5\n"
           if ($self->{db}->[$this_rom]->{rom_data_md5} eq $self->{db}->[$i]->{rom_data_md5});
        }
      }
    }

    #
    # check the md5's on the physical files against the DB
    #

    my $rec = $self->{db}->[$this_rom];

    if (($level > 1) && ($rec->{options} !~ m/cowering/)) {
      my $romfilename = "$dir/" . uc($rec->{cc3_filename});
      $romfilename .= ".ROM" if ( ! -f "$romfilename");

      my $w = $self->wash_rom($romfilename);
 
      print "The bin MD5 for $rec->{id} in the DB doesn't match what is in the romfile in the repository (".uc($rec->{cc3_filename}).")\n"
       if ($w->{wash}->{binmd5data}->{bin_md5} ne $rec->{bin_md5});

      print "The bin CRC32 for $rec->{id} in the DB doesn't match what is in the romfile in the repository (".uc($rec->{cc3_filename}).")\n"
       if (($w->{wash}->{crc32} ne $rec->{bin_crc32}) &&
           ($rec->{bin_crc32} !~ m/^\s*$/));

      print "The rom data MD5 for $rec->{id} in the DB doesn't match what is in the romfile in the repository (".uc($rec->{cc3_filename}).")\n"
       if (($w->{wash}->{rommd5data}->{rom_data_md5} ne $rec->{rom_data_md5}) &&
           ($rec->{tags} !~ m/systemrom/) &&
           ($rec->{rom_data_md5} !~ m/^\s*$/));

      print "The rom attr MD5 for $rec->{id} in the DB doesn't match what is in the romfile in the repository (".uc($rec->{cc3_filename}).")\n"
       if (($w->{wash}->{rommd5data}->{rom_attr_md5} ne $rec->{rom_attr_md5}) &&
           ($rec->{tags} !~ m/systemrom/) &&
           ($rec->{rom_attr_md5} !~ m/^\s*$/));
    }

    print "$rec->{id} has a CC3 description that is too long\n"
     if (length($rec->{cc3_desc}) > 20);

    print "$rec->{id} doesn't appear to have a valid name\n"
     if ($rec->{cc3_filename} eq $rec->{name});

    print "$rec->{id} doesn't have any tags\n"
     if ($rec->{tags} =~ m/^\s*$/);

    print "$rec->{id} doesn't have a cc3_filename\n"
     if (((! grep(($_ eq 'cc3_filename'),(keys %$rec))) ||
         ($rec->{cc3_filename} eq "")) &&
         ($rec->{options} !~ m/cowering/));

    print "$rec->{id} doesn't appear to have a fully fleshed out record\n"
     if (($rec->{cc3_filename} eq $rec->{name}) &&
         ($rec->{cc3_filename} eq $rec->{cc3_desc}));

    if (defined $rec->{bin_crc32}) {
      print "$rec->{id} has a bad good_name\n"
       if ($rec->{good_name} ne $coweringdata->{$rec->{bin_crc32}});
    }

    if (defined $rec->{good_name}) {
      my $found_crc = 0;
      for my $c (keys %$coweringdata) {
        if ($coweringdata->{$c} eq $rec->{good_name}) {
          print "$rec->{id} has a CRC32 that doesn't match Cowering's for it's good_name\n"
           if (($rec->{bin_crc32} ne $c) && ($rec->{cowering_crc32} ne $c));
          $found_crc = 1;
          last;
        }
      }
      
      print "$rec->{id}: I never found a CRC in the Cowering datafile for this good_name\n"
       if (! $found_crc);
    }

    # check that this rom's variant_of points to a real id
    if ($rec->{variant_of} !~ m/^\s*$/) {
      my $found = 0;
      for (my $i=0; $i < @{$self->{db}}; $i++) {
        if ($rec->{variant_of} eq $self->{db}->[$i]->{id}) {
          $found = 1;
          last;
        }
      }

      print "$rec->{id} has a variant_of that doesn't point to any valid record\n"
       if (! $found);
    }
  }

  # check that all cowering crc32s are in the DB
  if ($level > 2) {
    print "=== Checking that all Cowering CRC32s are in the DB ===\n";
    for my $crc (keys %$coweringdata) {
      my $found = 0;
      for (my $i=0; $i < @{$self->{db}}; $i++) {
        my $rec = $self->{db}->[$i];
        if (($rec->{bin_crc32} eq $crc) || ($rec->{cowering_crc32} eq $crc)) {
          $found = 1;
          print "$rec->{id}: good_name doesn't match cowering's\n"
           if ($self->{db}->[$i]->{good_name} ne $coweringdata->{$crc});
          last;
        }
      }
  
      print "Didn't find a CRC32 in the DB for $crc: $coweringdata->{$crc}\n"
       if (! $found);
    }
  }


  #
  # checks on the roms dir that are driven by the entries in the dir
  #

  if ($level > 1) {
    print "=== Checking that all ROMs in the roms dir are in the DB ===\n";
    opendir DIRH, $dir or die "Cannot open the roms repository: $dir\n";
    my @files = readdir DIRH;
    closedir DIRH;

    # check the roms in the repository to make sure they're all in the DB
    my @romfiles = grep /\.rom$/i,@files;
    my @files_in_db = grep { !/^\.rom/i } grep { !/\.bin/i } map { uc("$_->{cc3_filename}.rom") } @{$self->{db}};

    for my $file (@romfiles) {
      if (! grep(($_ eq $file),@files_in_db)) {
        # we didn't find this .rom file in the DB under cc3_filename.rom
        # check to see if this .rom file is actually in the DB under another name
        my ($rom_data, $warnings) = $self->calc_md5_for_file("$dir/$file");
        my $rec = $self->get_record_from_rom_md5s($rom_data->{rom_data_md5},$rom_data->{rom_attr_md5});
        if (defined $rec) {
          print "$file is in the repository, but is in the DB under $rec->{id} (" . uc($rec->{cc3_filename}) . ")\n";
        } else {
          print "$file is in the repository but is not in the DB\n";
        }
      }
    }

    # check that all roms listed in the DB are in the repository
    print "=== Checking that all ROMs in the DB are in the roms dir ===\n";
    for my $file (@files_in_db) {
      if (! grep(($_ eq $file),@romfiles)) {
        my $cc3f = $file;
        $cc3f =~ s/\..*$//;
        my $rec = $self->get_record_from_cc3name($cc3f);
        print "$file is referenced in the DB ($rec->{id}), but isn't in the repository.\n";
      }
    }
  }

  # check the entries in the MENULIST to be sure that they have filenames and 
  # descriptions
  my $mdir = $self->{manuals_repository};
  my %manualsout;
  my %manualslen;
  if (defined $menufile) {
    open my $fh, $menufile or die "Cannot open MENULIST.TXT file: $!\n";
    my @menulist = <$fh>;
    close $fh;

    for my $line (@menulist) {
      $line =~ m/^(........)(.*)$/;
      my $cc3file = CC3::trim($1);
      my $tag = lc($cc3file);

      # hack for menu - it should get the game tag items
      $tag = "game" if ($tag eq "menu");
      my $recs = $self->get_all_records_from_tag($tag);

      for my $rec (@$recs) {
        if (! grep(($_ eq 'cc3_desc'),(keys %$rec))) {
          print "$rec->{id} is missing a cc3_desc\n"
        } elsif ($rec->{cc3_desc} =~ m/^\s*$/) {
          print "$rec->{id} has a blank cc3_desc\n"
        }

        print "$rec->{id} is referenced for CC3, but missing a manual file (".uc($rec->{cc3_filename}).".TXT)\n"
        if ((! -f "$mdir/" . uc($rec->{cc3_filename}) . ".TXT") &&
            ($rec->{tags} !~ m/proto/i) &&
            ($rec->{tags} !~ m/demo/i) &&
            (! $manualsout{$rec->{cc3_filename}}++));
      }
    }
  }

  if ($level > 2) {
    print "=== Checking manuals ===\n";
    opendir DIRH, $mdir or die "Cannot open the manuals repository: $mdir\n";
    my @files = readdir DIRH;
    closedir DIRH;

    my @txtfiles = grep /\.txt$/i,@files;

    for my $file (@txtfiles) {
      $file =~ s/\.txt$//i;

      # check that all manuals are referenced
      my $rec = $self->get_record_from_cc3name(lc($file));
      print "$file.TXT is in the manuals repository, but isn't referenced in the DB.\n"
       if (! defined $rec);

      # check that the manual files have no lines over 20 chars
      open FH, "$mdir/".uc($file).".TXT" or die "Cannot open manual ".uc($file).".TXT: $!\n";
      for my $line (<FH>) {
        $line =~ s/\x0d?\x0a$//;
        if (length($line) > 20) {
          print "$file.TXT has line(s) longer than 20 chars\n";
          last;
        }
      }
      close FH;
    }
  }
}


sub DESTROY {
  my ($self) = @_;
  $self->write_inty_data_file() if ($self->{dirty});
}

#################### OLDER CODE ####################



sub parse_good_name {
  my ($self, $goodname) = @_;

  my $in_parens = 0;
  my $this_item = "";
  my @paren_items;

  # pull out all the items in parens
  for my $ch (split //,$goodname) {
    if (! $in_parens) {
      $in_parens = 1 if ($ch eq "(");
      next;
    } else {
      if ($ch eq ")") {
        $in_parens = 0;
        push @paren_items, $this_item;
        $this_item = "";
        next;
      }
    }

    $this_item .= $ch;
  }

  my $year = "";
  my $author = "";
  foreach my $paren_item (@paren_items) {
    if ($paren_item =~ m/^[-0-9]+$/) {
      $year = $paren_item;

    } elsif ($author eq "") {
      $author = $paren_item;
    }
  }

  return ($year,$author);
}



1;
