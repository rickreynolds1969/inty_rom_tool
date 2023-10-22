#!/usr/bin/perl

package Cowering;
use strict;
use Digest::CRC;

sub read_cowering_data {
  my ($coweringfile) = @_;

  # read in the cowering data
  open my $fh, $coweringfile or die "Cannot open $coweringfile: $!\n";
  my $in_game = 0;
  my $good_name = "";
  my $crc = 0;
  my %coweringdata;
  for my $line (<$fh>) {
    if ($line =~ m/^game/) {
      $in_game = 1;
      next;
    }

    if ($in_game) {
      if ($line =~ m/^\)$/) {
        $in_game = 0;
        next;
      }

      if ($line =~ m/.*description "(.*)"/) {
        $good_name = $1;
      }

      if ($line =~ m/.*rom \( name.*size.*crc ([0-9a-f]+) \)/i) {
        $crc = lc($1);

        while (length($crc) < 8) {
          $crc = "0$crc";
        }
        
        if ($good_name eq "") {
          print "WARN: good_name is blank, crc=|$crc|";
          next;
        }

        $coweringdata{$crc} = $good_name;

        $good_name = "";
        $crc = 0;
      }
    }
  }
  close $fh;

  return \%coweringdata;
}

sub crc32 {
  my ($file) = @_;

  my $crc = Digest::CRC->new(type=>"crc32");

  open FH, $file;

  $crc->addfile(*FH);

  my $ret = sprintf "%x", $crc->digest();
  while (length($ret) < 8) {
    $ret = "0$ret";
  }

  return $ret;
}

1;

