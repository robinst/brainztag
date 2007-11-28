#!/usr/bin/python

import sys
import os.path
import glob
from optparse import OptionParser
import re

import musicbrainz2.webservice as mb
from mutagen import id3


def ask(question):
    return raw_input(question).decode(sys.stdin.encoding)

def yes_or_no(question):
    while True:
        answer = ask(question)
        if answer in ['yes', 'y', '']:
            return True
        elif answer in ['no', 'n']:
            return False


class NoReleasesFoundError(Exception):
    pass


class Tagger(object):
    def __init__(self, files):
        self.files = files
    
    def collect_info(self):
        self.artist = ask('Artist: ')
        self.disc_title = ask('Disc: ')
        
        releases = self._find_releases()
        if not releases:
            raise NoReleasesFoundError()
        self.release = self._query_release(releases)
        
        inc = mb.ReleaseIncludes(artist=True, releaseEvents=True, tracks=True)
        self.release = mb.Query().getReleaseById(self.release.id, inc)
        
        self.discset = self._query_discset()
        if self.discset:
            self.release.title = self.discset['title']
        
        self.date = self.release.getEarliestReleaseDate()
        self.tracks_total = len(self.release.tracks)
    
    def _find_releases(self):
        f = mb.ReleaseFilter(artistName=self.artist, title=self.disc_title)
        results = mb.Query().getReleases(f)
        releases = []
        for result in results:
            if result.release.tracksCount == len(self.files):
                releases.append(result.release)
        return releases
    
    def _query_release(self, releases):
        if len(releases) == 1:
            return releases[0]
        
        print "Found %i discs. Choose the correct one." % len(releases)
        for i, r in enumerate(releases):
            print "%i: %s - %s (%i Tracks)" % (
                i + 1, r.artist.name, r.title, r.tracksCount)
        
        number = 0
        while not 1 <= number <= len(releases):
            try:
                number = int(ask("Disc: "))
            except ValueError:
                continue
        
        return releases[number - 1]
    
    def _query_discset(self):
        pattern = r'(?P<title>.*)\((?P<desc>disc (?P<number>\d+)(: .*)?)\)'
        match = re.match(pattern, self.release.title)
        if match is None:
            return None

        discset = match.groupdict()
        discset['number'] = int(discset['number'])
        discset['total'] = 0
        while discset['total'] < discset['number']:
            try:
                question = 'How many discs does this set contain?: '
                discset['total'] = int(ask(question))
            except ValueError:
                continue
        return discset
    
    def print_info(self):
        print
        print "%s - %s - %s - %s tracks" % (
            self.release.artist.name, self.release.title,
            self.date, self.tracks_total)
        print "   " + "Musicbrainz track".center(30) + "Filename".center(30)

        files_and_tracks = zip(self.files, self.release.tracks)
        for i, (file, track) in enumerate(files_and_tracks):
            basename = os.path.basename(file)
            print "%2s. %-30s %-30s" % (i + 1, track.title, basename)
    
    def tag(self):
        sys.stdout.write("Tagging")
        files_and_tracks = zip(self.files, self.release.tracks)
        for i, (file, track) in enumerate(files_and_tracks):
            try:
                tag = id3.ID3(file)
            except id3.ID3NoHeaderError:
                tag = id3.ID3()
            
            if self.release.isSingleArtistRelease():
                artist = self.release.artist.name
            else:
                artist = track.artist.name
            track_num = "%i/%i" % (i + 1, self.tracks_total)
            
            tag.add(id3.TPE1(3, artist))
            tag.add(id3.TALB(3, self.release.title))
            tag.add(id3.TIT2(3, track.title))
            tag.add(id3.TDRC(3, self.date))
            tag.add(id3.TRCK(3, track_num))
            if self.discset:
                disc_num  = "%i/%i" % (self.discset['number'],
                                       self.discset['total'])
                tag.add(TPOS(3, disc_num))
                tag.add(COMM(3, self.discset['desc'], lang="eng"))
            
            tag.save(file)
            sys.stdout.write('.')
            sys.stdout.flush()
        print


def main(args):
    directory = parse(args)
    files = glob.glob(os.path.join(directory, "*.mp3"))
    files = [f.decode(sys.getfilesystemencoding()) for f in files]
    tagger = Tagger(files)
    
    try:
        tagger.collect_info()
    except NoReleasesFoundError:
        print "No matching discs found."
        return 1
    
    tagger.print_info()
    if not yes_or_no("Tag? [Y/n] "):
        return 1
    
    tagger.tag()

def parse(args):
    usage = "Usage: %prog [options] DIRECTORY"
    parser = OptionParser(usage=usage, version="%prog 0.1")
    options, args = parser.parse_args(args)
    
    if len(args) == 1 and os.path.isdir(args[0]):
        return args[0]

    parser.error("first argument must be directory")


if __name__ == '__main__':
    try:
        exitcode = main(sys.argv[1:])
    except KeyboardInterrupt:
        exitcode = 1
    sys.exit(exitcode)
