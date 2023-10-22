#!/usr/bin/perl

package CC3;
use strict;


sub get_entries_and_filenames_from_cc3_file {
  my ($filename) = @_;

  die "$filename doesn't seem to be a file\n"
   if (! -f "$filename");

  my $ccd = get_cc3_data($filename);
  my %data;

  for my $d (@$ccd) {
    if ($d->{menu} eq "    ") {
      $data{$d->{file}} = $d->{desc};
    }
  }

  return \%data;
}


sub trim {
  my ($string) = @_;
  $string =~ s/^\s+//;
  $string =~ s/\s+$//;
  return $string;
}


sub get_menufile_data {
  my ($filename) = @_;

  open my $fh, $filename or die "Cannot open $filename file: $!\n";
  my @menulist = <$fh>;
  close $fh;

  my %data;
 
  for my $line (@menulist) {
    $line =~ m/^(.{8})(.*)$/;
    my $cc3file = trim($1);
    my $cc3menutext = trim($2);

    $data{$cc3file} = $cc3menutext;
  }

  return \%data;
}


sub get_cc3_data {
  my ($filename) = @_;

  die "$filename doesn't seem to be a file\n"
   if (! -f "$filename");

  open FH, $filename or die "Cannot open $filename: $!\n";
  binmode FH;

  my ($entry, $file8, $m, @data);

  while (! eof(FH)) {
    # read a 32 byte record
    read(FH,$entry,20);
    read(FH,$file8,8);
    read(FH,$m,4);

    my $r = {};
    $r->{desc} = trim($entry);
    $r->{file} = trim($file8);
    $r->{menu} = $m;

    push @data, $r;
  }

  close FH;

  return \@data;
}


1;
