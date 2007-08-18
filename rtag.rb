#!/usr/bin/env ruby -wKU

require 'rubygems'
require 'rbrainz'
require 'id3lib'
require 'iconv'

#Format Miliseconds as %M:%S
def format_milis(miliseconds)
  return Time.at(miliseconds/1000).gmtime.strftime('%M:%S')
end

#Choose a Disc
def choose_disc(discs)
  if discs.count == 1
    #Only 1 Disc -> take it
    return 0
  else
    puts "\nFound #{discs.count} discs. Choose the correct one."
    discs.each_with_index do |disc, index|
      puts "#{index+1}: #{disc.entity.artist} / #{disc.entity.title} / #{disc.entity.tracks.count} Tracks"
    end
    number = 0
    until number.between?(1, discs.count)
      print 'Disc: '
      number = STDIN.gets.to_i
    end
    return number
  end
end


### Start ###

if ARGV.length != 1 or !File.directory?(ARGV[0])
	puts "Usage: #{File.basename(__FILE__)} Directory"
	exit 0
end

# Load files from the given directory
files = Dir[File.join(ARGV[0], "*.mp3")].sort

# Ask for Artist & Disc.
print 'Artist: '
artist = STDIN.gets.chomp
print 'Disc: '
disc_title = STDIN.gets.chomp

# Download all matching discs & choose one of them.
query  = MusicBrainz::Webservice::Query.new
discs = query.get_releases(:artist => artist, :title  => disc_title, :count => files.length)
if discs.count < 1
  puts 'No matching discs found.'
  exit 0
end
number = choose_disc(discs)

# Download & print the choosen disc.
disc = query.get_release_by_id(discs[number-1].entity.id, :tracks => true, :release_events => true, :artist => true)
puts "#{disc.artist} / #{disc.title} / #{disc.earliest_release_date().year} / #{disc.tracks.size} Tracks"
puts "   " + "Musicbrainz track".center(30) + "Filename".center(30)
files.zip(disc.tracks).each_with_index do |(file, track), index|
  puts "%-2s %-30s %-30s" % [index, track.title, File.basename(file)]
end

# Continue?
loop do
  print 'Continue? [Y/n] '
  answer = STDIN.gets.chomp.downcase
  case answer
  when '', 'y', 'yes'
    break
  when 'n'
    exit 0
  end
end

# Handle discsets: "* (disc ?)"
match = /(.*)\(disc (\d+)(: .*)?\)/.match(disc.title)
if match
  album, disc_no, disc_desc = match.captures
  discs_total = 0
  until discs_total > 0
    print 'How many discs does this set contain? '
    discs_total = STDIN.gets.to_i
  end
  discset = disc_no.to_s + '/' + discs_total.to_s
  # Handle named discsets: "* (disc ?: NAME)"
  if disc_desc
    comment = 'disc ' + disc_no.to_s + disc_desc.to_s
  end
else
  album = disc.title
end
year = disc.earliest_release_date().year
tracks_total = '/' + disc.tracks.size.to_s

# Tag
print "Tagging"
disc.tracks.each_with_index do |track, index|
  datei = ID3Lib::Tag.new(files[index])
  title = datei.frame(:TIT2)
  title[:textenc] = 1
  title[:text] = Iconv.conv("utf-16le", "utf-8", track.title)
  datei.artist = track.artist
  datei.album = album
  datei.year = year
  datei.track = (index+1).to_s + tracks_total.to_s
  datei.disc = discset
  datei.comment = comment
  datei.update!(ID3Lib::V2)
  print "."
  STDOUT.flush
end
puts