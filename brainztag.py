#!/usr/bin/python
# -*- coding: utf-8 -*-
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

def ask(question, default=u''):
    """Ask the user a question and return the typed answer.

    Optionally, a default answer can be provided which the user can edit.
    """
    def pre_input_hook():
        readline.insert_text(default.encode(sys.stdin.encoding))
        readline.redisplay()
    readline.set_pre_input_hook(pre_input_hook)

    try:
        return raw_input(question).decode(sys.stdin.encoding)
    finally:
        readline.set_pre_input_hook(None)

def query(question, condition, converter=None):
    while True:
        answer = ask(question)

        if converter:
            try:
                answer = converter(answer)
            except ValueError, e:
                print "Error: Invalid input"
                continue

        if condition(answer):
            return answer

def yes_or_no(question):
    yes = ['yes', 'y', '']
    no = ['no', 'n']

    question += " (Y/n): "
    condition = lambda a: a in yes + no
    answer =  query(question, condition)

    return answer in yes

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
    parts = re.findall(r'(\d+|[^\W\d_]+)', s)
    result = [try_int(part.lower()) for part in parts]
    return result

class NoReleasesFoundError(Exception):
    pass

class Discset(object):
    def __init__(self, d):
        self.title  = d['title']
        self.desc   = d['desc']
        self.number = int(d['number'])

    def num(self):
        return "%i/%i" % (self.number, self.total)

class Track(object):
    def __init__(self, i, t, release):
        self.release = release

        self.title = t.title
        self.id = t.id

        # MusicBrainz Track UUID
        self.uuid = self.id.split('/')[-1]

        self.artist = t.artist
        self.num = "%i/%i" % (i + 1, self.release.tracks_total)

        # Fallback to the artist of the release
        if self.artist is None:
            self.artist = self.release.artist

class Release(object):
    def __init__(self, r):
        self.title = r.title
        self.tracks_total = r.tracksCount
        self.earliestReleaseDate = r.getEarliestReleaseDate()
        self.artist = r.artist
        self.id = r.id

    def load_details(self):
        inc = ReleaseIncludes(artist=True, releaseEvents=True, tracks=True)
        details = Query().getReleaseById(self.id, inc)

        self.tracks = []

        for i, t in enumerate(details.tracks):
            self.tracks.append(Track(i, t, release=self))

        self.artist = details.artist
        self.isSingleArtistRelease = details.isSingleArtistRelease()

        # Handle albums assigned to a single artist but containing tracks of
        # multiple artists.
        is_va = self.artist.id == VARIOUS_ARTISTS_ID
        if is_va or self.isSingleArtistRelease:
            self.album_artist = None
        else:
            self.album_artist = self.release.artist.name

        assert self.tracks_total == len(details.tracks), "unexpected trackk count"

        # handle discsets
        pattern = r'(?P<title>.*)\((?P<desc>disc (?P<number>\d+).*)\)'
        match = re.match(pattern, self.title)

        if match is not None:
            self.discset = Discset(match.groupdict())
            self.title = discset.title
        else:
            self.discset =  None

class Tagger(object):
    def __init__(self, files, options):
        self.files = files
        self.options = options


    def _guess_artist_and_disc(self):
        rel = self.files[0]
        abs = os.path.normpath(os.path.join(os.getcwdu(), rel))
        dir = os.path.basename(os.path.dirname(abs))

        parts = re.split('\s+-\s+', dir)
        if len(parts) >= 2:
            return parts[0], parts[1]
        elif len(parts) == 1:
            return "", parts[0]
        else:
            return "", ""

    def find_releases(self, artist, disc_title, track_count):
        query_limit = 100
        f = ReleaseFilter(artistName=self.artist, title=self.disc_title,
                    limit=query_limit)
        results = Query().getReleases(f)

        if len(results) == query_limit:
            print """\

Woah! the specified artist/disc names were pretty vague
we weren't able to check all possible candiates.

Please try to be more specific if the correct album
isn't in the following list.
"""
        # was wäre wenn wir hier die daten in unsere eigene
        # struktur wrappern würden und dabei gleichzeitig
        # alles normalisieren. dann würde das handling,
        # ausserhlab einhelticheer, keine komische Attribute Exceptions abfangen.

        # btw, list comprehensions?
        releases = []
        for result in results:
            # wrap result into our own structure
            release = Release(result.release)
            # only keep releases with correct amount of tracks
            if track_count < 0 or release.tracks_total == track_count:
                releases.append(release)

        # TODO: the following line was here, but was overriden by the
        # following line back in _collect_info()

        # releases.sort(key=lambda r: r.earliestReleaseDate)

        releases.sort(key=lambda r: r.title)


        return releases

    def _query_release(self, releases):
        if len(releases) == 1:
            return releases[0]

        print "Found %i discs with %i tracks. Choose the correct one." % \
            (len(releases), len(self.files))
        for i, r in enumerate(releases):
            print "%i: %s - %s (%s)" % (
                i + 1, r.artist.name, r.title, r.earliestReleaseDate)

        condition = lambda number: 1 <= number <= len(releases)
        number = query("Disc: ", condition, converter=int)
        return releases[number - 1]

    def _query_discset(self):

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
            self.release.earliestReleaseDate,
            self.release.tracks_total)
        print "   " + "Musicbrainz track".center(30) + "Filename".center(30)

        files_and_tracks = zip(self.files, self.release.tracks)
        for i, (file, track) in enumerate(files_and_tracks):
            basename = os.path.basename(file)
            print "%2s. %-30s %-30s" % (i + 1, track.title, basename)

    def tag(self):
        sys.stdout.write("Tagging")

        files_and_tracks = zip(self.files, self.release.tracks)
        for file, track in files_and_tracks:

            if self.options.strip:
                id3.delete(file)
                apev2.delete(file)

            try:
                tag = id3.ID3(file)
            except id3.ID3NoHeaderError:
                tag = id3.ID3()

            tag.add(id3.TPE1(3, track.artist.name))
            tag.add(id3.TALB(3, track.release.title))
            tag.add(id3.TIT2(3, track.title))
            tag.add(id3.TDRC(3, track.release.earliestReleaseDate))
            tag.add(id3.TRCK(3, track.num))

            if track.release.album_artist is not None:
                tag.add(id3.TPE2(3, track.release.album_artist))

            discset = track.release.discset
            if discset:
                disc_num  = discset.num()

                tag.add(id3.TPOS(3, disc_num))
                if discset.desc:
                    tag.delall('COMM')
                    tag.add(id3.COMM(3, text=discset.desc,
                                     desc='', lang='eng'))

            if self.options.genre:
                tag.add(id3.TCON(3, self.options.genre))

            tag.add(id3.UFID(owner='http://musicbrainz.org', data=track.uuid))

            tag.save(file)
            sys.stdout.write('.')
            sys.stdout.flush()
        print

    def rename(self):
        sys.stdout.write("Renaming")
        files_and_tracks = zip(self.files, self.release.tracks)
        for i, (file, track) in enumerate(files_and_tracks):
            track_num = i + 1

            #format = self.options.format
            #filename = "%02i. %s.mp3" % (track_num, track.title)#filename = format_filename(format, track)

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

class BrainztagCLI(object):
    def __init__(self, args):
        self.args = args


    def parse(args):
        usage = "Usage: %prog [options] <DIRECTORY | FILES...>"
        parser = OptionParser(usage=usage, version="%prog 0.1")
        parser.add_option('-s', '--strip', action='store_true',
                          help="strip existing ID3 and APEv2 tags from files")
        parser.add_option('-g', '--genre', dest='genre',
                          help="set the genre frame")
        options, args = parser.parse_args(args)

        if len(args) == 1 and os.path.isdir(args[0]):
            return options, args[0]
        elif len(args) >= 1:
            if all(not os.path.isdir(arg) for arg in args):
                return options, args

        parser.error("please specify either one directory or a one or more files")

    # TODO: should we move this function to Brainztag?
    def _get_files_in_folder(self, dir):
        dir = dir.decode(sys.getfilesystemencoding())

        files = fnmatch.filter(os.listdir(dir), '*.[mM][pP]3')
        files = [os.path.join(dir, file) for file in files]

    def _parse_file_list(arg):
        if type(arg) is str:
            # user specified a single folder

            files = get_files_in_folder(arg)

            if len(files) == 0:
                _error("No mp3 files found in '%s'" % dir)

            return files
        else:
            # user specified list of files
            # TODO: do we need to do a encoding cleanup here
            return args

    def ask_for_discset_total(self):
        question = 'How many discs does this set contain?: '
        condition = lambda i: i >= discset.number
        total = query(question, condition, converter=int)


    def _error(msg, exitcode=1):
        print msg
        sys.exit(exitcode)

    def run(self):
        options, arg = parse(args)

        files = _parse_file_list(arg)

        tagger = Tagger(files, options)

        artist, disc_title = tagger.guess_artist_and_disc()
        artist = ask('Artist: ', artist)
        disc_title = ask('Disc: ', disc_title)

        track_count = len(self.files)

        releases = tagger.find_releases(artist, disc_title, track_count)

        if not releases:
            _error("No matching discs found.")

        release = tagers.query_release(releases)
        release.load_details()

        if self.release.discset is not None:
            self.release.discset.total = ask_for_discset_total()

        self._order_files()

        tagger.print_info()

        if yes_or_no("Tag?"):
            tagger.tag()

        if yes_or_no("Rename?"):
            tagger.rename()


        # initialize tagger
        # ask user for search conditions
        # fetch releases list
        # present user with releases list
        # ask user for correct release
        # fetch release
        # if release discset
        #   ask user for discset number
        # match/compare release with files list
        # ask user for match confirmation
        # ask user if files should be tagged
        # ask user if files should be renamed
        # tag & rename
        # quit



def main(args):
    b = BrainztagCLI(args)

    b.run()


if __name__ == '__main__':
    try:
        exitcode = main(sys.argv[1:])
    except KeyboardInterrupt:
        exitcode = 1