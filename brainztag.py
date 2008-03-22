#!/usr/bin/python

import sys
import os
import fnmatch
from optparse import OptionParser
import re

from musicbrainz2.webservice import Query, ReleaseIncludes, ReleaseFilter
from musicbrainz2.model import VARIOUS_ARTISTS_ID
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

def make_fs_safe(s):
    s = s.replace("/", "-")
    return s


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
        # TODO: Use 'key' argument
        releases.sort(lambda a, b: cmp(a.title, b.title))
        self.release = self._query_release(releases)
        
        inc = ReleaseIncludes(artist=True, releaseEvents=True, tracks=True)
        self.release = Query().getReleaseById(self.release.id, inc)
        
        self.discset = self._query_discset()
        if self.discset:
            self.release.title = self.discset['title']
        
        self.date = self.release.getEarliestReleaseDate()
        self.tracks_total = len(self.release.tracks)
        # Handle albums assigned to a single artist but containing tracks of multiple artists.
        if not self.release.isSingleArtistRelease() and not self.release.artist.id == VARIOUS_ARTISTS_ID:
            self.album_artist = self.release.artist.name
        else:
            self.album_artist = None
    
    def _find_releases(self):
        f = ReleaseFilter(artistName=self.artist, title=self.disc_title)
        results = Query().getReleases(f)
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
        pattern = r'(?P<title>.*)\((?P<desc>disc (?P<number>\d+).*)\)'
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

        if not ':' in discset['desc']:
            del discset['desc']
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
            
            try:
                artist = track.artist.name
            except AttributeError:
                # Fallback to the artist of the relase
                artist = self.release.artist.name
            track_num = "%i/%i" % (i + 1, self.tracks_total)

            tag.add(id3.TPE1(3, artist))
            tag.add(id3.TALB(3, self.release.title))
            tag.add(id3.TIT2(3, track.title))
            tag.add(id3.TDRC(3, self.date))
            tag.add(id3.TRCK(3, track_num))
            if self.album_artist is not None:
                tag.add(id3.TPE2(3, self.album_artist))
            if self.discset:
                disc_num  = "%i/%i" % (self.discset['number'],
                                       self.discset['total'])
                tag.add(id3.TPOS(3, disc_num))
                if 'desc' in self.discset:
                    tag.delall('COMM')
                    tag.add(id3.COMM(3, text=self.discset['desc'],
                                     desc='', lang='eng'))
            
            tag.save(file)
            sys.stdout.write('.')
            sys.stdout.flush()
        print

    def rename(self):
        sys.stdout.write("Renaming")
        files_and_tracks = zip(self.files, self.release.tracks)
        for i, (file, track) in enumerate(files_and_tracks):
            track_num = i + 1

            filename = "%02i. %s.mp3" % (track_num, track.title)
            filename = make_fs_safe(filename)
            new_file = os.path.join(os.path.dirname(file), filename)

            if os.path.exists(new_file):
                print
                print '"' + new_file + '" already exists, not overwriting.'
                continue

            os.rename(file, new_file)

            sys.stdout.write('.')
            sys.stdout.flush()
        print


def main(args):
    dir = parse(args).decode(sys.getfilesystemencoding())
    files = fnmatch.filter(os.listdir(dir), '*.mp3')
    files.sort()
    files = [os.path.join(dir, file) for file in files]
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

    if not yes_or_no("Rename? [Y/n] "):
        return 1
    tagger.rename()

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
