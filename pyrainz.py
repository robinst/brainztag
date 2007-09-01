#!/usr/bin/python

import sys
import os.path
import glob
from optparse import OptionParser

import musicbrainz2.webservice as ws
from mutagen.easyid3 import EasyID3 as ID3


def main(args):
    usage = "Usage: %prog [options] DIRECTORY"
    parser = OptionParser(usage=usage, version="%prog 0.1")
    options, args = parser.parse_args(args)
    
    if len(args) != 1 or not os.path.isdir(args[0]):
        parser.error("first argument must be directory")

    directory = args[0]
    files = glob.glob(os.path.join(directory, "*.mp3"))
    
    artist = raw_input('Artist: ')
    disc_title = raw_input('Disc: ')
        
    query = ws.Query()
    f = ws.ReleaseFilter(artistName=artist, title=disc_title)
    results = query.getReleases(f)
    
    if not results:
        print "No matching discs found."
        return 1
    
    release = choose_release(results)
    
    inc = ws.ReleaseIncludes(artist=True, releaseEvents=True, tracks=True)
    release = query.getReleaseById(release.id, inc)
    
    print "%s - %s" % (release.artist.name, release.title)
    print "   " + "Musicbrainz track".center(30) + "Filename".center(30)
    for index, (file, track) in enumerate(zip(files, release.tracks)):
        n = index + 1
        print "%-2s %-30s %-30s" % (n, track.title, os.path.basename(file))
    
    while True:
        answer = raw_input("Continue? [Y/n] ")
        if answer in ['yes', 'y', '']:
            break
        elif answer in ['no', 'n']:
            return 1
    
    date = release.getEarliestReleaseDate()
    tracks_total = len(release.tracks)
    
    print "Tagging..."
    for index, (file, track) in enumerate(zip(files, release.tracks)):
        track_number = index + 1
        tag = ID3(file)
        tag['artist'] = release.artist.name
        tag['album'] = release.title
        tag['title'] = track.title
        tag['date']  = date
        tag['tracknumber'] = "%i/%i" % (track_number, tracks_total)
        tag.save()
        sys.stdout.write('.')
        sys.stdout.flush()


def choose_release(results):
    if len(results) == 1:
        return results[0].release
    
    print "Found %i discs. Choose the correct one." % len(results)
    for index, result in enumerate(results):
        r = result.release
        print "%i: %s - %s (%i Tracks)" % (
            index + 1, r.artist.name, r.title, r.tracksCount)
    
    number = 0
    while not 1 <= number <= len(results):
        try:
            number = int(raw_input("Disc: "))
        except ValueError:
            continue
    
    return results[number-1].release


if __name__ == '__main__':
    try:
        exitcode = main(sys.argv[1:])
    except KeyboardInterrupt:
        exitcode = 1
    sys.exit(exitcode)
