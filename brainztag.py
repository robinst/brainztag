#!/usr/bin/python

# brainztag: CLI tool to tag and rename music albums using MusicBrainz data
#
# Copyright (C) 2007-2008  Robin Stocker
# Copyright (C) 2007-2008  Philippe Eberli
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import sys
import os
import fnmatch
import re
import readline
from optparse import OptionParser

from musicbrainz2.webservice import Query, ReleaseIncludes, ReleaseFilter
from musicbrainz2.model import VARIOUS_ARTISTS_ID

from mutagen import id3
from mutagen import apev2


def ask(question, default=''):
    """Ask the user a question and return the typed answer.

    Optionally, a default answer can be provided which the user can edit.
    """
    def pre_input_hook():
        readline.insert_text(default)
        readline.redisplay()
    readline.set_pre_input_hook(pre_input_hook)

    try:
        return raw_input(question).decode(sys.stdin.encoding)
    finally:
        readline.set_pre_input_hook(None)

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

def distinctive_parts(s):
    """Extract the distinctive parts of a str: the numbers and words.

    The numbers are converted to int and the words are lowercased. All parts
    are returned in a list.

    The result can be used to do a natural sort:

    >>> l = ['a1', 'b1', 'a10b10', 'a2', 'a10b2']
    >>> l.sort(key=distinctive_parts)
    >>> l
    ['a1', 'a2', 'a10b2', 'a10b10', 'b1']
    """
    def try_int(part):
        try: return int(part)
        except: return part
    parts = re.findall(r'(\d+|[^\W\d]+)', s)
    result = [try_int(part.lower()) for part in parts]
    return result

class NoReleasesFoundError(Exception):
    pass


class Tagger(object):
    def __init__(self, files, options):
        self.files = files
        self.options = options
    
    def collect_info(self):
        artist, disc = self._guess_artist_and_disc()
        self.artist = ask('Artist: ', artist)
        self.disc_title = ask('Disc: ', disc)
        
        releases = self._find_releases()
        if not releases:
            raise NoReleasesFoundError()
        releases.sort(key=lambda r: r.title)
        self.release = self._query_release(releases)
        
        inc = ReleaseIncludes(artist=True, releaseEvents=True, tracks=True)
        self.release = Query().getReleaseById(self.release.id, inc)
        
        self.discset = self._query_discset()
        if self.discset:
            self.release.title = self.discset['title']
        
        self.date = self.release.getEarliestReleaseDate()
        self.tracks_total = len(self.release.tracks)

        self._order_files()

        # Handle albums assigned to a single artist but containing tracks of
        # multiple artists.
        is_va = self.release.artist.id == VARIOUS_ARTISTS_ID
        if is_va or self.release.isSingleArtistRelease():
            self.album_artist = None
        else:
            self.album_artist = self.release.artist.name
    
    def _guess_artist_and_disc(self):
        path = os.path.dirname(os.path.abspath(self.files[0]))
        dir = os.path.basename(path)
        parts = re.split('\s*-\s*', dir)
        if len(parts) >= 2:
            return parts[0], parts[1]
        elif len(parts) == 1:
            return "", parts[0]
        else:
            return "", ""

    def _find_releases(self):
        f = ReleaseFilter(artistName=self.artist, title=self.disc_title)
        results = Query().getReleases(f)

        releases = []
        for result in results:
            if result.release.tracksCount == len(self.files):
                releases.append(result.release)

        releases.sort(key=lambda r: r.getEarliestReleaseDate())

        return releases
    
    def _query_release(self, releases):
        if len(releases) == 1:
            return releases[0]
        
        print "Found %i discs. Choose the correct one." % len(releases)
        for i, r in enumerate(releases):
            print "%i: %s - %s (%s)" % (
                i + 1, r.artist.name, r.title, r.getEarliestReleaseDate())
        
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

    def _order_files(self):
        """Make self.files have the same order as the tracks."""

        ordered_files = []
        remaining_files = list(self.files)

        for i, track in enumerate(self.release.tracks):
            track_num = i + 1

            def similarity(file):
                # Strip directories and extension
                file = os.path.splitext(os.path.basename(file))[0]
                file_parts  = distinctive_parts(file)
                track_parts = distinctive_parts(track.title) + [track_num]
                score = 0
                for part in track_parts:
                    if part in file_parts:
                        score += 1
                        file_parts.remove(part)
                return score

            most_similar = max(remaining_files, key=similarity)
            remaining_files.remove(most_similar)
            ordered_files.append(most_similar)

        self.files = ordered_files
    
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

            if self.options.strip:
                id3.delete(file)
                apev2.delete(file)

            try:
                tag = id3.ID3(file)
            except id3.ID3NoHeaderError:
                tag = id3.ID3()
            
            try:
                artist = track.artist.name
            except AttributeError:
                # Fallback to the artist of the release
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

            if self.options.genre:
                tag.add(id3.TCON(3, self.options.genre))
            
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

            if new_file == file:
                continue

            if os.path.exists(new_file):
                print
                print '"' + new_file + '" already exists, not overwriting.'
                continue

            os.rename(file, new_file)

            sys.stdout.write('.')
            sys.stdout.flush()
        print


def main(args):
    options, dir = parse(args)
    dir = dir.decode(sys.getfilesystemencoding())
    files = fnmatch.filter(os.listdir(dir), '*.mp3')

    if len(files) == 0:
        print "No mp3 files found in '" + dir + "'"
        return 1

    files = [os.path.join(dir, file) for file in files]
    tagger = Tagger(files, options)
    
    try:
        tagger.collect_info()
    except NoReleasesFoundError:
        print "No matching discs found."
        return 1
    
    tagger.print_info()

    if yes_or_no("Tag? [Y/n] "):
        tagger.tag()

    if yes_or_no("Rename? [Y/n] "):
        tagger.rename()

def parse(args):
    usage = "Usage: %prog [options] DIRECTORY"
    parser = OptionParser(usage=usage, version="%prog 0.1")
    parser.add_option('-s', '--strip', action='store_true',
                      help="strip existing ID3 and APEv2 tags from files")
    parser.add_option('-g', '--genre', dest='genre',
                      help="set the genre frame")
    options, args = parser.parse_args(args)
    
    if len(args) == 1 and os.path.isdir(args[0]):
        return options, args[0]

    parser.error("first argument must be directory")


if __name__ == '__main__':
    try:
        exitcode = main(sys.argv[1:])
    except KeyboardInterrupt:
        exitcode = 1
    sys.exit(exitcode)
