#!/usr/bin/python

import sys
import os.path
import glob
from optparse import OptionParser
import re

import musicbrainz2.webservice as ws
from mutagen import id3


def main(args):
    directory = parse(args)
    files = glob.glob(os.path.join(directory, "*.mp3"))
    files = [f.decode(sys.getfilesystemencoding()) for f in files]
    
    artist = raw_input('Artist: ').decode(sys.stdin.encoding)
    disc_title = raw_input('Disc: ').decode(sys.stdin.encoding)
    
    query = ws.Query()
    f = ws.ReleaseFilter(artistName=artist, title=disc_title)
    results = query.getReleases(f)
    releases = []
    for result in results:
        if result.release.tracksCount == len(files):
            releases.append(result.release)
    
    if not releases:
        print "No matching discs found."
        return 1
    
    release = choose_release(releases)
    
    inc = ws.ReleaseIncludes(artist=True, releaseEvents=True, tracks=True)
    release = query.getReleaseById(release.id, inc)

    discset = discset_info(release)
    if discset:
        release.title = discset['title']
        discs_total = 0
        while discs_total < discset['number']:
            try:
                answer = raw_input('How many discs does this set contain?: ')
                discs_total = int(answer)
            except ValueError:
                continue

    date = release.getEarliestReleaseDate()
    tracks_total = len(release.tracks)
    
    print
    print "%s - %s - %s - %s tracks" % (
        release.artist.name, release.title, date, tracks_total)
    print "   " + "Musicbrainz track".center(30) + "Filename".center(30)
    for i, (file, track) in enumerate(zip(files, release.tracks)):
        print "%2s. %-30s %-30s" % (i + 1, track.title, os.path.basename(file))
    
    if not yes_or_no("Tag? [Y/n] "):
        return 1
    
    print "Tagging..."
    for index, (file, track) in enumerate(zip(files, release.tracks)):
        try:
            tag = id3.ID3(file)
        except id3.ID3NoHeaderError:
            tag = id3.ID3()

        if release.isSingleArtistRelease():
            artist = release.artist.name
        else:
            artist = track.artist.name
        track_num = "%i/%i" % (index + 1, tracks_total)
        disc_num  = "%i/%i" % (discset['number'], discs_total))

        tag.add(id3.TPE1(3, artist))
        tag.add(id3.TALB(3, release.title))
        tag.add(id3.TIT2(3, track.title))
        tag.add(id3.TDRC(3, date))
        tag.add(id3.TRCK(3, track_num))
        if discset:
            tag.add(TPOS(3, disc_num)
            tag.add(COMM(3, discset['desc'], lang="eng"))

        tag.save(file)
        sys.stdout.write('.')
        sys.stdout.flush()


def parse(args):
    usage = "Usage: %prog [options] DIRECTORY"
    parser = OptionParser(usage=usage, version="%prog 0.1")
    options, args = parser.parse_args(args)
    
    if len(args) != 1 or not os.path.isdir(args[0]):
        parser.error("first argument must be directory")
    
    return args[0]


def choose_release(releases):
    if len(releases) == 1:
        return releases[0]
    
    print "Found %i discs. Choose the correct one." % len(releases)
    for i, r in enumerate(releases):
        print "%i: %s - %s (%i Tracks)" % (
            i + 1, r.artist.name, r.title, r.tracksCount)
    
    number = 0
    while not 1 <= number <= len(releases):
        try:
            number = int(raw_input("Disc: "))
        except ValueError:
            continue
    
    return releases[number-1]


def discset_info(release):
    p = re.compile(r'(?P<title>.*)\((?P<desc>disc (?P<number>\d+)(: .*)?)\)')
    match = p.match(release.title)
    if not match:
        return None
    info = match.groupdict()
    info['number'] = int(info['number'])
    return info


def yes_or_no(question):
    while True:
        answer = raw_input(question)
        if answer in ['yes', 'y', '']:
            return True
        elif answer in ['no', 'n']:
            return False


if __name__ == '__main__':
    try:
        exitcode = main(sys.argv[1:])
    except KeyboardInterrupt:
        exitcode = 1
    sys.exit(exitcode)
