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

from musicbrainz2.webservice import Query, ReleaseIncludes, ReleaseFilter, ResourceNotFoundError
from musicbrainz2.model import VARIOUS_ARTISTS_ID

from mutagen.mp3 import MP3
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

def format_seconds(seconds):
    return "%u:%02u" % (seconds/60, seconds%60)

class NoReleasesFoundError(Exception):
    pass

class Discset(object):
    def __init__(self, d):
        self.title  = d['title']
        self.desc   = d['desc']
        self.number = int(d['number'])

    def number_str(self):
        return "%i/%i" % (self.number, self.total)

class Track(object):
    def __init__(self, i, t, release):
        self.release = release

        self.title = t.title
        self.id = t.id
        self.duration = t.duration

        # MusicBrainz Track UUID
        self.uuid = self.id.split('/')[-1]

        self.artist = t.artist
        self.number = i + 1

        # Fallback to the artist of the release
        if self.artist is None:
            self.artist = self.release.artist

    def number_str(self):
        return "%i/%i" % (self.number, self.release.tracks_total)

class Release(object):
    def __init__(self, r, query, details_included=False):
        self.query = query
        self.title = r.title
        self.tracks_total = r.tracksCount
        self.earliestReleaseDate = r.getEarliestReleaseDate()
        self.artist = r.artist
        self.id = r.id

        if details_included:
            self.load_details(r)
            # for some weird reasons the musicbrainz api doesn't provide
            # the tracksCount if the query includes tracks (tracks=True)
            self.tracks_total = len(self.tracks)


    def load_details(self, details=None):
        if not details:
            inc = ReleaseIncludes(artist=True, releaseEvents=True, tracks=True)
            details = self.query.getReleaseById(self.id, inc)

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
            self.album_artist = self.artist.name

        assert self.tracks_total is None or \
            self.tracks_total == len(details.tracks), "unexpected track count"

        # handle discsets
        pattern = r'(?P<title>.*)\((?P<desc>disc (?P<number>\d+).*)\)'
        match = re.match(pattern, self.title)

        if match is not None:
            self.discset = Discset(match.groupdict())
            self.title = self.discset.title
        else:
            self.discset =  None

class Tagger(object):

    def __init__(self):
        self.query = Query()

    def guess_artist_and_disc(self, files):
        rel = files[0]
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
        f = ReleaseFilter(artistName=artist, title=disc_title,
                          limit=query_limit)
        results = self.query.getReleases(f)

        if len(results) == query_limit:
            print """\

Woah! the specified artist/disc names were pretty vague
we weren't able to check all possible candiates.

Please try to be more specific if the correct album
isn't in the following list.
"""

        releases = []
        for result in results:
            # wrap result into our own structure
            release = Release(result.release, self.query)
            # only keep releases with correct amount of tracks
            if track_count < 0 or release.tracks_total == track_count:
                releases.append(release)

        releases.sort(key=lambda r: r.title)

        return releases

    def find_release_by_mbid(self, mbid, track_count):
        include = ReleaseIncludes(artist=True, tracks=True)
        try:
            result = self.query.getReleaseById(mbid, include)
        except ResourceNotFoundError:
            error("There is no Release with this Musicbrainz ID")

        release = Release(result, self.query, details_included=True)

        if release.tracks_total == track_count:
            return release
        else:
            error("Unexpected track count for '%s - %s' expected %i but was %i"
                  % (release.artist.name, release.title, track_count, release.tracks_total))


    def order_files(self, files, tracks):
        """Make self.files have the same order as the tracks."""

        ordered_files = []
        remaining_files = list(files)

        for track in tracks:

            def similarity(file):
                # Strip directories and extension
                file = os.path.splitext(os.path.basename(file))[0]
                file_parts  = distinctive_parts(file)
                track_parts = distinctive_parts(track.title) + [track.number]
                score = 0
                for part in track_parts:
                    if part in file_parts:
                        score += 1
                        file_parts.remove(part)
                return score

            most_similar = max(remaining_files, key=similarity)
            remaining_files.remove(most_similar)
            ordered_files.append(most_similar)

        return ordered_files

    def tag(self, files, release,
            genre=None, strip_existing_tags=False, progress=None):

        files_and_tracks = zip(files, release.tracks)
        for file, track in files_and_tracks:

            if strip_existing_tags:
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
            tag.add(id3.TRCK(3, track.number_str()))

            if track.release.album_artist is not None:
                tag.add(id3.TPE2(3, track.release.album_artist))

            discset = track.release.discset
            if discset:
                disc_num = discset.number_str()

                tag.add(id3.TPOS(3, disc_num))
                if discset.desc:
                    tag.delall('COMM')
                    tag.add(id3.COMM(3, text=discset.desc,
                                     desc='', lang='eng'))

            if genre is not None:
                tag.add(id3.TCON(3, genre))

            tag.add(id3.UFID(owner='http://musicbrainz.org', data=track.uuid))

            tag.save(file)
            if progress is not None:
                progress(file, track)

    def rename(self, files, release, progress=None):
        warnings = []
        for file, track in zip(files, release.tracks):

            filename = "%02i. %s.mp3" % (track.number, track.title)
            filename = make_fs_safe(filename)
            new_file = os.path.join(os.path.dirname(file), filename)

            if new_file == file:
                continue

            if os.path.exists(new_file):
                w = '"%s" already exists, not overwriting.' % new_file
                warnings.append(w)
                continue

            os.rename(file, new_file)

            if progress is not None:
                progress(file, track)

        return warnings


def parse(args):
    usage = "Usage: %prog [options] <DIRECTORY | FILES...>"
    parser = OptionParser(usage=usage, version="%prog 0.1")
    parser.add_option('-s', '--strip', action='store_true',
                      help="strip existing ID3 and APEv2 tags from files")
    parser.add_option('-g', '--genre', dest='genre',
                      help="set the genre frame")
    parser.add_option('', '--mbid', dest='mbid',
                      help="the MusicBrainz ID of the album (bypasses the questions about the artist and albumname)")
    parser.add_option('-a', '--artist', dest='artist',
                      help="set the artist (bypasses the question about the artistname)")
    parser.add_option('-d', '--disc', dest='disc',
                      help="set the disctitle (bypasses the question about the disctitle)")
    options, args = parser.parse_args(args)

    if len(args) == 1 and os.path.isdir(args[0]):
        return options, args[0]
    elif len(args) >= 1:
        if all(not os.path.isdir(arg) for arg in args):
            return options, args

    parser.error("please specify either one directory or a one or more files")

def get_files_in_folder(dir):
    dir = dir.decode(sys.getfilesystemencoding())

    files = fnmatch.filter(os.listdir(dir), '*.[mM][pP]3')
    return [os.path.join(dir, file) for file in files]

def parse_file_list(arg):
    if type(arg) is str:
        # user specified a single folder

        files = get_files_in_folder(arg)

        if len(files) == 0:
            error("No mp3 files found in '%s'" % arg)

        return files
    else:
        # user specified list of files
        encoding = sys.getfilesystemencoding()
        return [f.decode(encoding) for f in arg]

def ask_for_discset_total(discset):
    question = 'How many discs does this set contain?: '
    condition = lambda i: i >= discset.number
    return query(question, condition, converter=int)

def query_release(releases, track_count):
    if len(releases) == 1:
        return releases[0]

    print "Found %i discs with %i tracks. Choose the correct one." % \
        (len(releases), track_count)
    for i, r in enumerate(releases):
        print "%i: %s - %s (%s)" % (
            i + 1, r.artist.name, r.title, r.earliestReleaseDate)

    condition = lambda number: 1 <= number <= len(releases)
    number = query("Disc: ", condition, converter=int)

    return releases[number - 1]


def print_info(release, files):
    print
    print "%s - %s - %s - %s tracks" % (
        release.artist.name, release.title,
        release.earliestReleaseDate,
        release.tracks_total)
    print "    " + "Musicbrainz track".center(35) + " | " + "Filename".center(35)

    files_and_tracks = zip(files, release.tracks)
    for i, (file, track) in enumerate(files_and_tracks):
        basename = os.path.basename(file)
        mp3 = MP3(file)
        file_duration = format_seconds(mp3.info.length)
        track_duration = format_seconds(track.duration/1000)
        print "%2s. %-30s %4s | %-30s %4s" % (i + 1, track.title, track_duration, basename, file_duration)


def error(msg, exitcode=1):
    print msg
    sys.exit(exitcode)

def run(args):
    options, arg = parse(args)

    files = parse_file_list(arg)

    tagger = Tagger()
    track_count = len(files)

    if options.mbid:
        release = tagger.find_release_by_mbid(options.mbid, track_count)
    else:
        artist, disc_title = tagger.guess_artist_and_disc(files)
        artist = options.artist or ask('Artist: ', artist)
        disc_title = options.disc or ask('Disc: ', disc_title)

        releases = tagger.find_releases(artist, disc_title, track_count)

        if not releases:
            error("No matching discs found.")

        release = query_release(releases, track_count)

        release.load_details()

    if release.discset is not None:
        release.discset.total = ask_for_discset_total(release.discset)

    files = tagger.order_files(files, release.tracks)

    print_info(release, files)

    def progress(file, track):
        sys.stdout.write('.')
        sys.stdout.flush()
    
    question  = "Continue? ([t]ag, [r]ename, [B]oth, [c]ancel): "
    condition = lambda a: a in ['t', 'r', 'b', 'c', '']
    answer =  query(question, condition)

    if answer in ['t', 'b', '']:
        tagger.tag(files, release, genre=options.genre,
                   strip_existing_tags=options.strip, progress=progress)

    if answer in ['r', 'b', '']:
        tagger.rename(files, release, progress=progress)
    
    print


def main(args):
    run(args)


if __name__ == '__main__':
    try:
        exitcode = main(sys.argv[1:])
    except KeyboardInterrupt:
        exitcode = 1
    sys.exit(exitcode)
