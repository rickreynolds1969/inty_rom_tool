#!/usr/bin/perl

BEGIN {
  push @INC, "/Users/rick/inty_roms_tool";
  push @INC, "/media/psf/Home/inty_roms_tool";
}



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


use strict;
use INTY;
use CC3;
use Cowering;
use Data::Dumper;
use Digest::MD5;

my $inty = new INTY;

my $cmd = shift @ARGV;

short_usage() if (! defined $cmd);

SWITCH: {
  # main commands
  $cmd =~ m/^\s*$/    && do { usage(); last SWITCH; };
  $cmd eq "help"      && do { usage(); last SWITCH; };
  $cmd eq "which"     && do { inty_which(@ARGV); last SWITCH; };
  $cmd eq "edit"      && do { inty_edit(@ARGV); last SWITCH; };
  $cmd eq "search"    && do { inty_search(@ARGV); last SWITCH; };
  $cmd eq "add"       && do { inty_add(@ARGV); last SWITCH; };
  $cmd eq "mwlist"    && do { inty_createfrinklist(@ARGV); last SWITCH; };
  $cmd eq "srclist"   && do { inty_srclist(@ARGV); last SWITCH; };
  $cmd eq "cc3menus"  && do { inty_cc3menus(@ARGV); last SWITCH; };
  $cmd eq "tags"      && do { inty_tags(@ARGV); last SWITCH; };
  $cmd eq "gamelist"  && do { inty_gamelist(@ARGV); last SWITCH; };

  # maintenance stuff
  $cmd eq "test"      && do { test(@ARGV); last SWITCH; };
  $cmd eq "md5"       && do { inty_md5(@ARGV); last SWITCH; };
  $cmd eq "crc32"     && do { inty_crc32(@ARGV); last SWITCH; };
  $cmd eq "list"      && do { inty_list(@ARGV); last SWITCH; };
  $cmd eq "wash"      && do { inty_wash(@ARGV); last SWITCH; };
  $cmd eq "writedb"   && do { $inty->{dirty} = 1; last SWITCH; };
  $cmd eq "checkdb"   && do { inty_checkdb(@ARGV); last SWITCH; };
  $cmd eq "cfgfile"   && do { inty_cfgfile(@ARGV); last SWITCH; };
  $cmd eq "dumpcc3"   && do { inty_dumpcc3(@ARGV); last SWITCH; };
  $cmd eq "replacerom" && do { inty_replacerom(@ARGV); last SWITCH; };
  $cmd eq "fetchrom"  && do { inty_fetchrom(@ARGV); last SWITCH; };
  $cmd eq "mkrename"  && do { inty_mkrename(@ARGV); last SWITCH; };

  # stuff for scripting a front end
  $cmd eq "options"   && do { inty_options(@ARGV); last SWITCH; };
  $cmd eq "rom_dir"   && do { print "$inty->{roms_repository}\n"; last SWITCH; };
  $cmd eq "rom_file"  && do { inty_romfile(@ARGV); last SWITCH; };
  $cmd eq "name_from_rom_file"  && do { inty_namefromromfile(@ARGV); last SWITCH; };
  $cmd eq "kbdhackfile" && do { inty_kbdhackfile(@ARGV); last SWITCH; };
  $cmd eq "kbdhackfiledir" && do { inty_kbdhackfiledir(@ARGV); last SWITCH; };

  print "I don't recognize the command $cmd\n";
}


sub inty_srclist {
  my (@filters) = @_;
  my $CRLF = "\x0d\x0a";
  my $byid = "NO";

  for my $cnt (1 .. 2) {
    if ($filters[0] eq "-id") {
      $byid = "YES";
      shift @filters;
    }
    if ($filters[0] eq "-nodos") {
      $CRLF = "\n";
      shift @filters;
    }
  }

  my @ids = $inty->get_all_ids("name");

  for my $id (@ids) {
    my $rom = $inty->get_record_from_id($id);

    my @romtags = split /,/,$rom->{tags};

    my $itmatches = 1;
    foreach my $filter (@filters) {
      if (! grep(($_ eq $filter),@romtags)) {
        $itmatches = 0;
      }
    }

    if ($itmatches) {
      if ($byid eq "YES") {
        print "$rom->{id}$CRLF"
      } else {
        print uc($rom->{cc3_filename}) . "$CRLF"
      }
    }
  }
}

sub inty_gamelist {
  my (@filters) = @_;

  my $images = "YES";
  if ($filters[0] eq "-noimages") {
    $images = "NO";
    shift @filters;
  }

  my @boxart_files;
  if ($images eq "YES") {
    # read in the boxart dir
    opendir my $fhdir, "$inty->{boxart_repository}" or die "Cannot opendir: $!\n";
    @boxart_files = readdir $fhdir;
    @boxart_files = grep !/^\.$/,@boxart_files;
    @boxart_files = grep !/^\.\.$/,@boxart_files;
    closedir $fhdir;
  }


  open my $fhw, "> gamelist.xml" or die "Cannot open gamelist.xml: $!\n";
  print $fhw "<?xml version=\"1.0\"?>\n";
  print $fhw "<gameList>\n";

  my @ids = $inty->get_all_ids("name");

  for my $id (@ids) {
    my $rom = $inty->get_record_from_id($id);

    next if (! exists $rom->{cc3_filename});
    next if ($rom->{cc3_filename} eq "");

    my @romtags = split /,/,$rom->{tags};
    my $itmatches = 1;

    if (@filters) {
      foreach my $filter (@filters) {
        if (! grep(($_ eq $filter),@romtags)) {
          $itmatches = 0;
        }
      }
    }

    next if (! $itmatches);

    my @opts = split /,/,$rom->{options};
    # .ROM is the only extension we'll autopopulate, but leave any extension 
    # that is actually in the cc3_filename there
    my $ext = ".ROM";
    $ext = ""
     if (grep(/\./, $rom->{cc3_filename}));

    print $fhw "  <game>\n";
    print $fhw "    <path>./". uc($rom->{cc3_filename}) . $ext . "</path>\n";
    print $fhw "    <name>$rom->{name}</name>\n";

    my @img;
    if ($images eq "YES") {
      # is there an image?
      if (grep(/^$rom->{cc3_filename}....$/, @boxart_files)) {
        @img = grep(/^$rom->{cc3_filename}....$/, @boxart_files)
      } else {
        # how about the variant?
        if (exists $rom->{variant_of}) {
          if ($rom->{variant_of} ne "") {
            my $variant_rom = $inty->get_record_from_id($rom->{variant_of});

            if (grep(/^$variant_rom->{cc3_filename}....$/, @boxart_files)) {
              @img = grep(/^$variant_rom->{cc3_filename}....$/, @boxart_files)
            }
          }
        }
      }
    }
    
    if (@img) {
      print $fhw "    <image>~/.emulationstation/downloaded_images/intellivision/$img[0]</image>\n";
    }
    print $fhw "    <players />\n";
    print $fhw "  </game>\n";
  }

  print $fhw "</gameList>\n";

  close $fhw;
}


sub inty_cc3menus {
  open my $fh, "MENULIST.TXT" or die "Cannot open MENULIST.TXT file: $!\n";
  my @menulist = <$fh>;
  close $fh;

  for my $line (@menulist) {
    $line =~ m/^(.{8})(.*)$/;
    my $cc3file = CC3::trim($1);
    my $cc3menutext = $2;

    print "Writing $cc3file.CC3\n";
    open my $fhw, "> $cc3file.CC3" or die "Cannot open $cc3file.CC3: $!\n";

    if ($cc3file eq "MENU") {
      # the main menu is special - it gets a list of all other menus at the top
      for my $m (@menulist) {
        $m =~ m/^(.{8})(.{20})/;
        printf $fhw "$2$1MENU" if ($1 ne "MENU    ");
      }
    } else {
      # non-main menu lists get a return to main menu option
      printf $fhw "%-20s%-8sMENU", "---  Main Menu   ---", "MENU";
    }

    my $tag = lc($cc3file);

    # hack for menu - it should get the game tag items
    $tag = "ccgame" if ($tag eq "menu");
    my $recs = $inty->get_all_records_from_tag($tag);

    # another hack - brew should include brewcart
    if ($tag eq "brew") {
      my $recs2 = $inty->get_all_records_from_tag("brewcart");
      push @{$recs}, @{$recs2};
    }

    my @sorted = ();

    # if a .LST file is specified, this is giving an order for this category
    if (-f "$cc3file.LST") {
      open my $fhr, "$cc3file.LST" or die "Cannot open $cc3file.LST: $!\n";
      my @orderedlist = <$fhr>;
      close $fhr;

      for my $id (@orderedlist) {
        $id = CC3::trim($id);
        my $rec = $inty->get_record_from_id($id);
        push @sorted, $rec;
      }

    } else {
      @sorted = sort { lc($a->{cc3_desc}) cmp lc($b->{cc3_desc}) } @$recs;
    }

    for my $rec (@sorted) {
      printf $fhw "%-20s%-8s    ",$rec->{cc3_desc},$rec->{cc3_filename};
    }
    close $fhw;
  }
}

sub inty_dumpcc3 {
  my ($filename) = @_;

  my $data = CC3::get_cc3_data($ARGV[0]); 

  for my $d (@$data) {
    printf "|%-20s|%-8s|%4s|\n", $d->{desc}, $d->{file}, $d->{menu};
  }
}

sub inty_tags {
  for my $tag ($inty->get_all_tags()) {
    print "$tag\n";
  }
}

sub inty_cfgfile {
  my ($id, $filename) = @_;

  my $rec = $inty->get_record_from_id($id);

  if (! defined $rec) {
    print "Couldn't find record for ID $id\n";
    return;
  }

  if (! -f $filename) {
    print "$filename doesn't look like a file.\n";
    return;
  }
  
  open my $fh, $filename or die "Cannot open $filename: $!\n";
  $rec->{cfg_file} = "";
  while (<$fh>) {
    # the pattern is an ASCII 13 10 (DOS), or just 10 (Linux/Mac).  In octal, 
    # that's 15(d) 12(a) or just 12(a)
    s/\x0d?\x0a$//;
    $rec->{cfg_file} .= "$_\n";
  }

  close $fh;

  my $retval = $inty->replace_rom($rec);

  print "Record modified for $rec->{id}.\n" if ($retval eq "success");
  print "FAILURE: ID $rec->{id} not found in DB (??)\n" if ($retval ne "success");
}

sub inty_fetchrom {
  my ($game_id) = @_;

  my $suc = "failure";
  my $romfile;

  my $rec = $inty->get_record_from_id($game_id);

  if (defined $rec) {
    $romfile = uc($rec->{cc3_filename}) . ".ROM";
    $suc = $inty->copy_rom_file_from_repository($romfile);
  }

  print "$romfile created.\n" if ($suc eq "success");
  print "FAILURE: $romfile not created: $!\n" if ($suc ne "success");
}

sub inty_wash {
  my ($file) = @_;

  my $data = $inty->wash_rom($file);

  print Dumper($data);

  my ($rec, $why) = $inty->get_record_from_wash_data($data);

  print "FOUND IN DB [$why] AS $rec->{id}\n"
   if (defined $rec);

  my $cowering = $inty->{cowering_data};

  my $crc = $data->{orig}->{crc32};
  print "ORIG FOUND IN COWERING: [$crc] $cowering->{$crc}\n"
   if (grep(($_ eq $crc),(keys %$cowering)));

  $crc = $data->{wash}->{crc32};
  print "WASH FOUND IN COWERING: [$crc] $cowering->{$crc}\n"
   if (grep(($_ eq $crc),(keys %$cowering)));

}


sub inty_edit {
  my ($r) = @_;

  my $retval = "failure";
  my $rec = $r;
  $rec = $inty->get_record_from_id($r) if (! ref $rec);
  $rec = $inty->get_record_from_cc3name($r) if (! ref $rec);

  if (! defined $rec) {
    print "FAILURE: record not found for edit.\n";
    return $retval;
  }

  my $why;
  ($rec, $why) = interactively_edit_record($rec);

  if (! defined $rec) {
    print "FAILURE: $why.\n";
    return $retval;
  } 

  my $retval = $inty->replace_rom($rec);

  print "Record modified for $rec->{id}.\n" if ($retval eq "success");
  print "FAILURE: ID $rec->{id} not found in DB (??)\n" if ($retval ne "success");

  return $retval;
}


# this routine is to replace the rom file for an already defined rom (e.g. an 
# updated to an in-development game)
sub inty_replacerom {
  my (@args) = @_;

  my $copy = "NO";
  if ($args[0] eq "-c") {
    $copy = "YES";
    shift @args;
  }

  my $id = $args[0];
  my $rec = $inty->get_record_from_id($id);

  if (defined $rec) {
    # wash this file
    my $data = $inty->wash_rom($args[1]);

    # update old data from the record that is about the physical file
    $rec->{bin_md5} = $data->{wash}->{binmd5data}->{bin_md5};
    $rec->{rom_data_md5} = $data->{wash}->{rommd5data}->{rom_data_md5};
    $rec->{rom_attr_md5} = $data->{wash}->{rommd5data}->{rom_attr_md5};

    my $suc = $inty->add_or_replace_rom($rec);

    if ($suc eq "success") {
      print "Record for $id updated";

      if ($copy eq "YES") {
        my $force = 1;
        $suc = $inty->copy_rom_file_to_repository($data->{wash}->{romfile}, uc($rec->{cc3_filename}) . ".ROM", $force);

        if ($suc eq "success") {
          print ", copied to repository as ".uc($rec->{cc3_filename}).".ROM.\n";
        } else {
          print ", BUT COULDN'T COPY TO REPOSITORY!\n";
        }
      } else {
        print ".\n";
      }
    } else {
      print "Couldn't replace record in DB.\n";
    }

  } else {
    print "Couldn't find $rec in the DB.\n";
  }
}


sub inty_add {
  my (@args) = @_;

  my $copy = "NO";
  if ($args[0] eq "-c") {
    $copy = "YES";
    shift @args;
  }

  my $base = $args[0];
  $base =~ s/\..+$//;
  $base =~ s/^.+\///;
  my $game_name = uc(substr($base,0,1)) . lc(substr($base,1));

  # wash this file
  my $data = $inty->wash_rom($args[0]);

  # check to see if this is a known game in the repository
  my ($rec, $why) = $inty->get_record_from_wash_data($data);

  if (defined $rec) {
    print "This " . uc($data->{romorbin}) . " file is already in the DB as $rec->{id}\n";

    return 1;
  }

  $rec = {};

  my $cowdata = $inty->{cowering_data};
  my $occ = $data->{orig}->{crc32};
  my $wcc = $data->{wash}->{crc32};
  if (grep(($_ eq $occ),(keys %$cowdata))) {
    $rec->{good_name} = $cowdata->{$occ};

    if ($occ ne $wcc) {
      $rec->{cowering_crc32} = $occ;
    } else {
      $rec->{bin_crc32} = $occ;
    }

  } elsif (grep(($_ eq $wcc),(keys %$cowdata))) {
    $rec->{good_name} = $cowdata->{$wcc};
    $rec->{bin_crc32} = $wcc;
  }

  $rec->{bin_md5} = $data->{wash}->{binmd5data}->{bin_md5};
  $rec->{rom_data_md5} = $data->{wash}->{rommd5data}->{rom_data_md5};
  $rec->{rom_attr_md5} = $data->{wash}->{rommd5data}->{rom_attr_md5};
  $rec->{cc3_filename} = lc(substr($base,0,8));
  $rec->{cc3_desc} = $game_name;
  $rec->{id} = $rec->{cc3_filename};
  $rec->{name} = $game_name;
  
  while (grep(($_ eq $rec->{id}),$inty->get_all_ids())) {
    $rec->{id} .= "_";
  }

  my $why;
  ($rec, $why) = interactively_edit_record($rec,$args[0]);

  if (! defined $rec) {
    print "FAILURE: $why.\n";
    return;
  }

  if ($inty->rom_file_exists_in_repository(uc($rec->{cc3_filename}) . ".ROM")) {
    print "FAILURE: ".uc($rec->{cc3_filename}).".ROM already exists in repository.\n";
    return;
  }

  my $suc = $inty->add_rom($rec);

  if ($suc eq "success") {
    print "ROM added to DB";

    if ($copy eq "YES") {
      $suc = $inty->copy_rom_file_to_repository($data->{wash}->{romfile}, uc($rec->{cc3_filename}) . ".ROM");

      if ($suc eq "success") {
        print ", copied to repository as ".uc($rec->{cc3_filename}).".ROM.\n";
      } else {
        print ", BUT COULDN'T COPY TO REPOSITORY!\n";
      }
    } else {
      print ".\n";
    }

  } else {
    print "FAILURE: Couldn't add record.\n";
  }
}


sub interactively_edit_record {
  my ($rec,$filename) = @_;

  my $prev_id = $rec->{id};

  my $file = $inty->write_ascii_record($rec,$filename);
  my $prev_rec_md5 = Digest::MD5::md5_hex(Dumper($rec));

  if (defined $file) {
    my $keep_editing = 1;
    while ($keep_editing) {
      $keep_editing = 0;
      system("vim $file");
    
      $rec = $inty->parse_ascii_record($file);

      my $status = $inty->validate_record($rec);

      return (undef,"No change to record")
       if ($prev_rec_md5 eq Digest::MD5::md5_hex(Dumper($rec)));

      # if the id is missing, bail here
      return (undef,"ID missing in record")
       if (grep(/no id in record/i,@$status));

      # if the id is bad, go back for another edit
      if ($rec->{id} ne $prev_id) {
        if (grep(/id in db/i,@$status)) {
          $rec->{id} = $prev_id;
          $file = $inty->write_ascii_record($rec);
          print "FAILURE: you changed the ID, but the new ID is already in the DB.\nReverting the ID.\nHIT A KEY TO CONTINUE.";
          my $junk = <STDIN>;
          $keep_editing = 1;
     
        } else {
          $rec->{replace_id} = $prev_id;
        }
      }

      # if the cc3_desc is too long, go back for another edit
      if (grep(/cc3_desc too long/i,@$status)) {
        $file = $inty->write_ascii_record($rec);
        print "FAILURE: the cc3_desc is too long.\nHIT A KEY TO CONTINUE.";
        my $junk = <STDIN>;
        $keep_editing = 1;
      }
    }
  } else {
    return (undef, "Couldn't write temp file");
  }

  return $rec;
}


sub inty_createfrinklist {
  my (@args) = @_;

  my @ids = $inty->get_all_ids("name");

  # DOS line endings
  my $CRLF = "\x0d\x0a";

  for my $id (@ids) {
    my $rom = $inty->get_record_from_id($id);

    print uc($rom->{cc3_filename}) . "$CRLF";
    print "$rom->{name}$CRLF";
    print "$rom->{year}$CRLF";
    print "$rom->{author}$CRLF";
    print "$CRLF";  # parent rom
    print "$CRLF";  # unknown entry
    print "Raster$CRLF";
    print "Horizontal$CRLF";
    print "$CRLF";  # controller type
    print "Status Good$CRLF";  # any value to putting real data here?
    print "Color Good$CRLF";  # any value to putting real data here?
    print "Sound Good$CRLF";  # any value to putting real data here?
    print "$CRLF";  # game type
  }
}


sub inty_crc32 {
  my ($filename) = @_;

  my $crc = Cowering::crc32($filename);

  print "crc=$crc\n";
}


sub inty_md5 {
  my ($filename) = @_;

  my ($rom_data, $warnings) = $inty->calc_md5_for_file($filename);

  if (grep(($_ eq "bin_md5"),(keys %$rom_data))) {
    print "bin_md5=$rom_data->{bin_md5}\n";
  } else {
    print "rom_data_md5=$rom_data->{rom_data_md5}\n";
    print "rom_attr_md5=$rom_data->{rom_attr_md5}\n";
  }
}

sub inty_namefromromfile {
  my ($romfile) = @_;
  my $rec = $inty->get_record_from_cc3name($romfile);
  if (defined $rec) {
    my $rom = $rec->{id};
    print "$rom\n";
  }
}

sub inty_romfile {
  my ($game_id) = @_;
  my $rec = $inty->get_record_from_id($game_id);
  if (defined $rec) {
    my $rom = uc($rec->{cc3_filename});
    print "$rom\n";
  }
}


sub inty_options {
  my ($game_id) = @_;
  my $rec = $inty->get_record_from_id($game_id);
  if (defined $rec) {
    my @opts = split /,/,$rec->{options};
    map { print "$_\n" } @opts;
  }
}


sub inty_kbdhackfile {
  my ($game_id) = @_;
  my $hack = $inty->{laptop_default_kbdhackfile};

  # special hack case for CGC
  if ($game_id eq "cgc") {
    $hack = "laptop-cgc";
  } else {
    my $rec = $inty->get_record_from_id($game_id);
    if (defined $rec) {
      my @opts = split /,/,$rec->{options};
      $hack = $inty->{laptop_default_ecs_kbdhackfile}
       if (grep(($_ eq 'ecs'), @opts));
      $hack = $rec->{kbdhackfile}
       if (grep(($_ eq 'kbdhackfile'),(keys %$rec)));
    }
  }
  print "$hack\n";
}


sub inty_kbdhackfiledir {
  print "$inty->{kbdhackfile_dir}\n";
}



sub inty_list {
  my (@args) = @_;

  my $tag = "";
  if ($args[0] eq "-tag") {
    $tag = $args[1];
    shift @args;
    shift @args;
  }

  if (@args) {
    # overloading the list functionality by dumping a record for a given game
    for my $id (@args) {
      my $rec = $inty->get_record_from_id($id);

      if (! defined $rec) {
        $rec = $inty->get_record_from_cc3name($id);
      }

      if (defined $rec) {
        print "--- $id ---\n";
        for my $k (@{$inty->{fields_order}}) {
          if (grep(($_ eq $k),(keys %$rec))) {
            # multi-line fields can look nicer
            if ($k eq "cfg_file") {
              print " --- CFG FILE ---\n$rec->{$k}\n --- END CFG ---\n";
            #} elsif ($k eq "kbdhackfile") {
            #  print " --- KBDHACKFILE ---\n$rec->{$k}\n --- END KBDHACK ---\n";
            } else {
              # normal, key value pair
              print " $k: $rec->{$k}\n";
            }
          }
        }

      } else {
        print "$id: unknown ROM id\n";
      }
    }

  } else {
    my @ids = $inty->get_all_ids();

    my $n = 0;
    foreach my $id (@ids) {
      my $printit = 1;
      my $rec = $inty->get_record_from_id($id);
      $printit = 0
       if (($tag ne "" ) && ($rec->{tags} !~ m/$tag/));
      if ($printit) {
        printf "%-15s $rec->{name}\n", $rec->{id};
        $n++;
      }
    }

    print "Total: $n ROMs.\n";
  }
}



sub inty_which {
  my (@filenames) = @_;

  my $rep = $inty->{roms_repository};
  my $tmp = $inty->{temp_dir};
  my $copy = "NO";
  my $log = "NO";
  my $cow = "NO";
  my $idonly = "NO";
  my $logpart = "";

  my (@unknown, @nofiles, @missing);
  my $cowdata;

  while ($filenames[0] =~ m/^-/) {
    $copy = "YES" if ($filenames[0] eq "-c");
    $log = "YES" if ($filenames[0] eq "-l");
    $idonly = "YES" if ($filenames[0] eq "-i");
    if ($filenames[0] eq "-cow") {
      $cow = "YES";
      $cowdata = $inty->{cowering_data};
    }

    shift @filenames;
  }

  my $out;
  my $possess = 0;

  for my $filename (@filenames) {
    $logpart = "";
    $out = "$filename ";

    my $data = $inty->wash_rom($filename);

    $out .= "[" . uc($data->{binorrom}) . "] " if ($idonly ne "YES");

    my ($rec, $where);
    if ($cow eq "YES") {
      my $cc = $data->{orig}->{crc32};
      if (grep(($_ eq $cc),(keys %$cowdata))) {
        $out .= "$cc: $cowdata->{$cc}" if ($idonly ne "YES");
      } else {
        $out .= "$cc: UNKNOWN";
        $logpart = "unknown";
      }
      
    } else {
      ($rec, $where) = $inty->get_record_from_wash_data($data);
    }

    if (defined $rec) {
      my $systemrom = ($rec->{tags} =~ m/systemrom/i);
      $out .= "[$where] " if ((defined $where) && ($idonly ne "YES"));
      $out .= "$rec->{id}";
      $out .= ": $rec->{name}" if ($idonly ne "YES");

      # shall we copy this rom to the repository?
      if ($rec->{cc3_filename} ne "") {
        my $fname = uc($rec->{cc3_filename});

        if ((! -f "$rep/$fname") &&
            (! -f "$rep/$fname.ROM")) {
          if ((! $systemrom) && ($copy eq "YES")) {
            $out .= ", copying ROM to repository as $fname.ROM";
            $inty->copy_rom_file_to_repository($data->{wash}->{romfile},
              "$fname.ROM");
          }

          $logpart = "missing";
        } else {
          $possess++;
        }
      } else {
        $out .= ", CANNOT CHECK REPOSITORY - NO CC3_FILENAME DEFINED.";
        $logpart = "nofile";
      }
      $out .= "\n";

    } elsif ($cow eq "YES") {
      $out .= "\n";

    } else {
      $out .= "UNKNOWN\n";
      $logpart = "unknown";
    }

    print $out;

    push @unknown, $out if ($logpart eq "unknown");
    push @nofiles, $out if ($logpart eq "nofile");
    push @missing, $out if ($logpart eq "missing");
  }

  print scalar(@unknown) . " Unknown ROMs\n" . scalar(@missing) . " ROMs not in the repository\n$possess ROMs already in the repository\n"
   if (@filenames > 1);


  if ($log eq "YES") {
    open FHW, "> inty_logfile.txt" or die "Cannot open logfile: $!\n";
    if (@unknown) {
      print FHW "--- " . scalar(@unknown) . " UNKNOWNS ---\n";
      map { print FHW } @unknown;
    }
 
    if (@nofiles) {
      print FHW "--- " . scalar(@nofiles) . " MISSING CC3_FILENAMES ---\n";
      map { print FHW } @nofiles;
    }

    if (@missing) {
      print FHW "--- " . scalar(@missing) . " MISSING ROM FILES ---\n";
      map { print FHW } @missing;
    }
    close FHW;
  }
}


sub inty_search {
  my (@args) = @_;

  # -case switch
  my $case = "NO";
  if ($args[0] eq "-case") {
    $case = "YES";
    shift @args;
  }

  # if the search word has any upper case, do case sensitive search
  my $patt = $args[0];
  my $ic = "NO";

  $ic = "YES" if (lc($patt) eq $patt);
  $ic = "NO" if ($case eq "YES");

  $patt = "(?i)$patt" if ($ic eq "YES");
  
  my $db = $inty->get_db();
  
  foreach my $rom (@$db) {
    print "$rom->{id}: ID\n" if ($rom->{id} =~ m/$patt/);
    print "$rom->{id}: NAME $rom->{name}\n" if ($rom->{name} =~ m/$patt/);
    print "$rom->{id}: GOOD_NAME $rom->{good_name}\n" if ($rom->{good_name} =~ m/$patt/);
    print "$rom->{id}: CC3_DESC $rom->{cc3_desc}\n" if ($rom->{cc3_desc} =~ m/$patt/);
    print "$rom->{id}: CC3_FILENAME $rom->{cc3_filename}\n" if ($rom->{cc3_filename} =~ m/$patt/);
    print "$rom->{id}: COMMENTS $rom->{comments}\n" if ($rom->{comments} =~ m/$patt/);
  }
}


sub inty_checkdb {
  my (@args) = @_;

  my $level = 1;

  while ($args[0] =~ m/^-/) {
    if ($args[0] eq "-l") {
      $level = $args[1];
      shift @args;
    }

    shift @args;
  }

  $inty->verify_data($level,$args[0]);
}

sub inty_mkrename {
  my (@filters) = @_;

  open my $fhw, "> rename_roms.sh" or die "Cannot open rename_roms.sh: $!\n";

  my @ids = $inty->get_all_ids("name");
  my $game_name;

  for my $id (@ids) {
    my $rom = $inty->get_record_from_id($id);

    next if (! exists $rom->{cc3_filename});
    next if ($rom->{cc3_filename} eq "");

    my @romtags = split /,/,$rom->{tags};
    my $itmatches = 1;

    if (@filters) {
      foreach my $filter (@filters) {
        if (! grep(($_ eq $filter),@romtags)) {
          $itmatches = 0;
        }
      }
    }

    next if (! $itmatches);

    if (exists $rom->{flashback_name}) {
      $game_name = $rom->{flashback_name};
    } else {
      $game_name = $rom->{name};

      $game_name =~ s/'//g;
      $game_name =~ s/"//g;
      $game_name =~ s/!//g;
      $game_name =~ s/\///g;
      $game_name =~ s/&/and/g;
    }

    print $fhw "rm '/home/pi/RetroPie/roms/intellivision/$game_name.rom' > /dev/null 2>&1\n";
    print $fhw "ln -s /home/pi/all_inty_roms/" . uc($rom->{cc3_filename}) . ".ROM '/home/pi/RetroPie/roms/intellivision/$game_name.rom'\n";
  }

  close $fhw;
}


sub short_usage {
print <<EOSUSAGE;
inty.pl command [options]

  which [-c] [-l] [-i] [-cow] <files>
  list [-tag <tag>] [<game ID>]
  add [-c] <file>
  edit <game ID>
  search [-case] <pattern>
  mwlist
  srclist <filter>
  tags
  cc3menus
  fetchrom <game ID>

  writedb
  checkdb [-l <#>] [<menulist file>]
  cfgfile <game ID> <file>
  md5 <file>
  options <game ID>
  dumpcc3 <CC3 menu file>
  mkrename <filter>
  rom_dir
  rom_file <game ID>
  kbdhackfile <game ID>

EOSUSAGE
exit 0;
}


sub usage {
print <<EOUSAGE;
inty.pl command [options]

where command is one of

--- User commands ---

which [-c] [-l] [-i] [-cow] <files>
      Report the identity of the given ROM or BIN files.
      If -c is given, the ROM version of the file will be copied to the 
       repository if it is not present.
      If -l is given, a logfile will be written that details missing ROMs.
      If -i is given, only the ID of the file will be displayed.
      If -cow is given, the DB data will be ignored and the file will only be 
       matched based on the CRC data in the Cowering data file.

list [-tag <tag>] [<game ID>]
      Dump the games in the repository.
      If a tag is given, the games list will be only those containing that tag.
      If a game ID is given, it dumps the DB record for that game.

add [-c] <file>
      Add a DB record for the given ROM file.
      If -c is given, the ROM version of the file will be copied to the 
      repository.

edit <game ID>
      Edit the DB record for the given game ID.

search [-case] <pattern>
      Search the DB for records matching the given pattern.
      If -case is given, the search is case sensitive (defaults to case 
       insensitive).

mwlist
      Dump the games in the DB in a list file for use on the Frinkiac7 (has 
       DOS style line endings applied).

srclist <filter>
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

EOUSAGE
exit 0;
}


##########  OLD CODE  ########################

sub test {
  my (@filenames) = @_;

  open my $fh, "$filenames[0]" or die "Cannot open $filenames[0] file: $!\n";
  my @idlist = <$fh>;
  close $fh;

  for my $id (@idlist) {
    chomp($id);
    my $rom = $inty->get_record_from_id($id);

    print "$rom->{name}\n";
  }
}


sub test2 {
  my (@files) = @_;

  my $coweringdata = $inty->{cowering_data};

  for my $file (@files) {
    my $crc = Cowering::crc32($file);

    if (grep(($_ eq $crc),(keys %$coweringdata))) {
      my $w = $inty->wash_rom($file);
      my ($rec, $why) = $inty->get_record_from_wash_data($w);

      if (! defined $rec) {
        print "*** Can't find a record for $file in DB***\n";
        next;
      } else {
        # we have a record, check for sanity
        print "*** $rec->{id} [$why] ***\n";

        # 1. good name
        if ($rec->{good_name} ne $coweringdata->{$crc}) {
          print "GOOD NAME DOESN'T MATCH.\n";
        } else {
          print "Good name matches.\n";
        }

        # 2. rom md5
        if (($rec->{rom_data_md5} ne $w->{wash}->{md5data}->{rom_data_md5}) ||
            ($rec->{rom_attr_md5} ne $w->{wash}->{md5data}->{rom_attr_md5})) {
          print "ROM MD5 DATA DOESN'T MATCH.\n"
        } else {
          print "ROM md5 data matches.\n";
        }

        # 3. bin md5
        if ($rec->{bin_md5} ne $w->{wash}->{md5data}->{bin_md5}) {
          print "BIN MD5 DATA DOESN'T MATCH.\n"
        } else {
          print "BIN md5 data matches.\n"
        }

        # 4. bin crc
        if ($rec->{bin_crc32} ne $w->{orig}->{crc32}) {
          print "BIN CRC32 DATA DOESN'T MATCH.\n"
        } else {
          print "BIN crc32 data matches.\n"
        }
      }

    } else {
      print "Can't find CRC in Cowering for $file\n";
    }
  }
}


#sub test3 {
  #my $dir = "/Users/rick/Gaming/Emulation/Intellivision/roms";
  #my $rom2bin = "/Users/rick/Gaming/Emulation/jzinty-1.0-beta-mac/bin/rom2bin";
  #my $bin2rom = "/Users/rick/Gaming/Emulation/jzinty-1.0-beta-mac/bin/bin2rom";
  #my $coweringfile = "/Users/rick/inty_roms_tool/inty_203.dat";
  #my $oldromsdir = "/Users/rick/inty_roms_tool/roms";
#
  #my $coweringdata = Cowering::read_cowering_data($coweringfile);
  #
 ## loop over bins
 #opendir DIRH, $dir or die "Cannot open $dir: $!\n";
 #my @binfiles = readdir DIRH;
 #my @binfiles1 = grep(/\.int$/i,@binfiles);
 #my @binfiles2 = grep(/\.bin$/i,@binfiles);
 #closedir DIRH;
#
 #for my $binfile (@binfiles1, @binfiles2) {
   #my $firstcrc = Cowering::crc32("$dir/$binfile");
   #my $basename = $binfile;
   #$basename =~ s/\..+//;
#
   #print "washing $binfile\n";
   #my $washdata = $inty->wash_rom("$dir/$binfile");
#
   #my $rec = $inty->get_record_from_rom_md5s($romdata->{rom_data_md5}, $romdata->{rom_attr_md5});
   #my $rec = undef;
#
   #if (! defined $rec) {
     #print "I don't have a DB record for $binfile\n";
     #next;
   #}
#
   ## is this crc in the cowering data?
   #if (grep(($_ eq $firstcrc),(keys %$coweringdata))) {
     #$rec->{good_name} = $coweringdata->{$firstcrc};
     #$rec->{bin_crc32} = $firstcrc;
     #$rec->{bin_md5} = $bindata->{bin_md5};
#
     #$inty->replace_rom($rec);
#
   #} elsif (grep(($_ eq $bincrc),(keys %$coweringdata))) {
     #$rec->{good_name} = $coweringdata->{$bincrc};
     #$rec->{bin_crc32} = $bincrc;
     #$rec->{bin_md5} = $bindata->{bin_md5};
#
     #$inty->replace_rom($rec);
#
   #} else {
     #print "I didn't find a cowering CRC match for $binfile\n";
    #}
  #}
#}

sub testNN {
  my (@files) = @_;

  for my $cc3file (@files) {
    my $data = CC3::get_entries_and_filenames_from_cc3_file($cc3file);

    $cc3file =~ s/\..*$//;
    $cc3file =~ s/S$//;
    $cc3file = "ECS" if ($cc3file eq "EC");

    for my $cc3_filename (keys %$data) {
      my $rec = $inty->get_record_from_cc3name($cc3_filename);
      if (defined $rec) {
        my @tags = split /,/,$rec->{tags};
        $rec->{tags} = join(",",(@tags,lc($cc3file)));
        $inty->replace_rom($rec);
      }
    }   
  }
}

sub test4 {
  my (@files) = @_;

  my $dir = "/Users/rick/Gaming/CC3DavidHarley/GAMES";
  my $rom2bin = "/Users/rick/Gaming/Emulation/jzinty-1.0-beta-mac/bin/rom2bin";
  my $bin2rom = "/Users/rick/Gaming/Emulation/jzinty-1.0-beta-mac/bin/bin2rom";
  my $coweringfile = "/Users/rick/inty_roms_tool/inty_203.dat";
  my $oldromsdir = "/Users/rick/inty_roms_tool/roms_second_time";

  my $coweringdata = $inty->{cowering_data};

  my ($olddb1, $oldheader1) = INTY::read_inty_data_file("/Users/rick/inty_roms_tool/inty_datanew.dat");
  my ($olddb2, $oldheader2) = INTY::read_inty_data_file("/Users/rick/inty_roms_tool/inty_data.dat");

  # loop over files
  my $newid = 0;

  for my $file (@files) {
    # run this rom through the rom2bin/bin2rom wash
    print "Washing $file\n";
    my $washdata = $inty->wash_rom("$file");

    # output a warning if these aren't the same
#   print "WARN: Wash of $binfile didn't return the same md5s\n"
#    if ($washdata->{orig}->{md5data}->{bin_md5} ne 
#           $washdata->{wash}->{md5data}->{bin_md5});

    my $rec = $inty->get_record_from_wash_data($washdata);
    if ((defined $rec) && ($rec->{good_name} ne "")) {
      print "$file already in DB\n";
      next;
    } elsif (defined $rec) {
      print "*** WARN: This rom would get a new record (no good_name) ***********************************\n";
    }

    $rec = {};
    $rec->{rom_attr_md5} = $washdata->{wash}->{md5data}->{rom_attr_md5};
    $rec->{rom_data_md5} = $washdata->{wash}->{md5data}->{rom_data_md5};
    my $basename = $file;
    $basename =~ s/\..+$//;
    $basename = lc($basename);

    if ($washdata->{binorrom} eq "bin") {
      my $ocrc = $washdata->{orig}->{crc32};
      my $wcrc = $washdata->{wash}->{crc32};
      if (grep(($_ eq $ocrc),(keys %$coweringdata))) {
        $rec->{good_name} = $coweringdata->{$ocrc};
        $rec->{bin_crc32} = $ocrc;
        $rec->{bin_md5} = $washdata->{wash}->{md5data}->{bin_md5};
      } elsif (grep(($_ eq $wcrc),(keys %$coweringdata))) {
        $rec->{good_name} = $coweringdata->{$wcrc};
        $rec->{bin_crc32} = $wcrc;
        $rec->{bin_md5} = $washdata->{wash}->{md5data}->{bin_md5};
      } else {
#       print "$file not found in cowering data\n";
#       print " ocrc=|$ocrc|\n";
#       print " wcrc=|$wcrc|\n";
#       print Dumper($coweringdata);
        next;
      }
    }

    # now check for this rom in the older data file
    my $found = 0;
    for my $r (@$olddb1) {
      if (($rec->{rom_data_md5} eq $r->{rom_data_md5}) &&
          ($rec->{rom_attr_md5} eq $r->{rom_attr_md5})) {
        $found = 1;

        $rec->{id} = $r->{id};

        $rec->{name} = $r->{name}
         if (grep(($_ eq 'name'),(keys %$r)));

        $rec->{year} = $r->{year}
         if (grep(($_ eq 'year'),(keys %$r)));

        $rec->{author} = $r->{author}
         if (grep(($_ eq 'author'),(keys %$r)));

        $rec->{options} = $r->{options}
         if (grep(($_ eq 'options'),(keys %$r)));

        $rec->{cc3_filename} = $r->{cc3_filename}
         if (grep(($_ eq 'cc3_filename'),(keys %$r)));

        last;
      }
    }

    # if we don't find the rom in the older data file via the washed md5s, 
    # check with the originals
    if (! $found) {
      for my $r (@$olddb1) {
        if ($washdata->{orig}->{md5data}->{bin_md5} eq 
              $r->{bin_md5}) {
          $found = 1;

          $rec->{id} = $r->{id};

          $rec->{name} = $r->{name}
           if (grep(($_ eq 'name'),(keys %$r)));

          $rec->{year} = $r->{year}
           if (grep(($_ eq 'year'),(keys %$r)));

          $rec->{author} = $r->{author}
           if (grep(($_ eq 'author'),(keys %$r)));

          $rec->{options} = $r->{options}
           if (grep(($_ eq 'options'),(keys %$r)));

          $rec->{cc3_filename} = $r->{cc3_filename}
           if (grep(($_ eq 'cc3_filename'),(keys %$r)));

          last;
        }
      }
    }

    # if we didn't find records in the first older DB, check another
    if (! $found) {
      for my $r (@$olddb2) {
        if (($rec->{rom_data_md5} eq $r->{rom_data_md5}) &&
            ($rec->{rom_attr_md5} eq $r->{rom_attr_md5})) {
          $found = 1;

          $rec->{id} = $r->{id};

          $rec->{name} = $r->{name}
           if (grep(($_ eq 'name'),(keys %$r)));

          $rec->{year} = $r->{year}
           if (grep(($_ eq 'year'),(keys %$r)));

          $rec->{author} = $r->{author}
           if (grep(($_ eq 'author'),(keys %$r)));

          $rec->{options} = $r->{options}
           if (grep(($_ eq 'options'),(keys %$r)));

          $rec->{cc3_filename} = $r->{cc3_filename}
           if (grep(($_ eq 'cc3_filename'),(keys %$r)));

          last;
        }
      }
    }

    # if we don't find the rom in the older data file via the washed md5s, 
    # check with the originals
    if (! $found) {
      for my $r (@$olddb2) {
        if ($washdata->{orig}->{md5data}->{bin_md5} eq 
              $r->{bin_md5}) {
          $found = 1;

          $rec->{id} = $r->{id};

          $rec->{name} = $r->{name}
           if (grep(($_ eq 'name'),(keys %$r)));

          $rec->{year} = $r->{year}
           if (grep(($_ eq 'year'),(keys %$r)));

          $rec->{author} = $r->{author}
           if (grep(($_ eq 'author'),(keys %$r)));

          $rec->{options} = $r->{options}
           if (grep(($_ eq 'options'),(keys %$r)));

          $rec->{cc3_filename} = $r->{cc3_filename}
           if (grep(($_ eq 'cc3_filename'),(keys %$r)));

          last;
        }
      }
    }


    if (! $found) {
      $newid++;
      print "I did not find a record in the old data files for $file.\nSetting id to id_$newid\n";
      $rec->{id} = "id_$newid";
    }

    # make sure there are no duplicate IDs
    my @ids = $inty->get_all_ids();
    if (grep(($_ eq $rec->{id}),@ids)) {
      my $id = $rec->{id};
      while (grep(($_ eq $id),@ids)) {
        $id .= "_";
      }
      $rec->{id} = $id;
    }

    # add this record
    print "*** Adding this record to DB:\n" . Dumper($rec) . "\n";
    my $suc = $inty->add_or_replace_rom($rec);
    print "  SUCCESS.\n" if ($suc eq "success");
    print "  FAILURE.\n" if ($suc ne "success");
  }



# print Dumper($coweringdata);


# opendir DIRH, $oldromsdir or die "Cannot open dir $oldromsdir $!";
# my @files = readdir DIRH;
# closedir DIRH;
# @files = grep(/\.BIN$/,@files);

# print "Scanning $oldromsdir for CRC matches...\n";

# for my $binfile (@files) {
#   my $crc = Cowering::crc32("$oldromsdir/$binfile");
#   if (grep(($_ eq $crc),(keys %$coweringdata))) {

#     # check to see if this rom is already in the DB with this CRC
#     my $rec = $inty->get_record_from_bin_crc32($crc);

#     if (! defined $rec) {
#       print "Found $binfile in cowering, but not in DB.";

#       my $basename;
#       ($basename = $binfile) =~ s/\.BIN$//;
#       my $romfile = "$basename.ROM";
#       if (-f "$oldromsdir/$romfile") {
#         my $targetrom = lc($romfile);
#         my $targetbin = $targetrom;
#         $targetbin =~ s/\.rom/.bin/;
#         system("cp $oldromsdir/$romfile /tmp/$targetrom");
#         system("$rom2bin /tmp/$targetrom > /dev/null");
#         
#         my $newcrc = Cowering::crc32("/tmp/$targetbin");
#         if ($newcrc eq $crc) {
#           my ($binmd5s, $warnings) = $inty->calc_md5_for_file("/tmp/$targetbin");
#           my ($rommd5s, $warnings) = $inty->calc_md5_for_file("/tmp/$targetrom");

#           my $rom = {};
#           $rom->{bin_crc32} = $crc;
#           $rom->{bin_md5} = $binmd5s->{bin_md5};
#           $rom->{rom_data_md5} = $rommd5s->{rom_data_md5};
#           $rom->{rom_attr_md5} = $rommd5s->{rom_attr_md5};
#           $rom->{cc3_filename} = $romfile;
#           $rom->{name} = $coweringdata->{$crc};
#           $rom->{good_name} = $coweringdata->{$crc};
#           my $id = lc($basename);

#           my @ids = $inty->get_all_ids();
#           while (grep(($_ eq $id),@ids)) {
#             $id .= "_";
#           }
#           $rom->{id} = $id;

#           print "FOUND $binfile, IT'S $coweringdata->{$crc}, and a new ROM\n";
#           print Dumper($rom);
#           
#         } else {
#           print "ERR: CRC for bin of $romfile doesn't match $binfile ($crc != $newcrc)\n";
#           next;
#         }
#
#       } else {
#         print "ERR: didn't find romfile named $romfile\n";
#         next;
#       }

# copy .romfile named the same to /tmp
# run rom2bin on it and get crc
# if different than this one, ERR
# if same - compute md5s for rom and bin
# add record, using goodname as the name, romfilename as id (if not existing)


#     } else {
#       print "found $binfile in DB\n";
#     }


#   } else {
#     print "didn't find bin file $binfile in cowering dat file\n";
#   }
# }


# my ($old_db, $old_header) = INTY::read_inty_data_file("inty_data.dat"); 

# print Dumper($old_db);

# for my $id ($inty->get_all_ids()) {
#   my $rom = $inty->get_record_from_id($id);

#   print "looking at $rom->{id}\n";

#   my $dirty = 0;

#   for my $r (@$old_db) {
#     if ($rom->{rom_data_md5} eq $r->{rom_data_md5}) {
#       if ($rom->{id} eq $r->{id}) {
#         print "$rom->{id} is THE SAME on both DBs\n";
#       } else {
#         print "updating $rom->{id} to be $r->{id}\n";
#         $rom->{id} = $r->{id};
#         $dirty = 1;
#       }

#       last;
#     }
#   }

#   if ($dirty) {
#     print "  Updating rom record\n";
#     $inty->replace_rom($rom);
#   }
# }



# for my $id ($inty->get_all_ids()) {
#   my $file = uc($id);
#   system("cp $dir/$file.ROM ./candidate.rom");
#   system("$rom2bin candidate.rom > /dev/null");
#   my $crc = Cowering::crc32("candidate.bin");


#   my ($md5, $warnings) = $inty->calc_md5_for_file("candidate.bin");

#   print "WARN: " . Dumper($warnings) . "\n"
#    if ($#$warnings >= 0);

#   # find this crc in the cowering data
#   if (grep(($_ eq $crc),(keys %$coweringdata))) {
#     my $rom = $inty->get_record_from_id($id);
#     $rom->{good_name} = $coweringdata->{$crc};
#     $rom->{bin_crc32} = $crc;
#     $rom->{bin_md5} = $md5->{bin_md5};
#     my $ok = $inty->replace_rom($rom);
#     print "$id - $ok\n";
#   } else {
#     print "didn't find a cowering record for crc=$crc, file=$file\n";
#   }
# }
}


sub test5 {
  my ($dir) = @_;

  opendir DIRH, $dir or die "Cannot open dir: $!\n";
  my @files = readdir DIRH;
  @files = grep !/^\.$/,@files;
  @files = grep !/^\.\.$/,@files;
  closedir DIRH;

  for my $file (@files) {
    $file =~ m/\.(.*)$/;
    my $ext = $1;
    my $base = $file;
    $base =~ s/\..*$//;

    my $rec = $inty->get_record_from_goodname($base);
    $file =~ s/'/'\\''/g;

    if (defined $rec) {
      print "mv '$file' $rec->{cc3_filename}.$ext\n";
    }
  }
}
