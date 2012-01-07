brainztag
=========

Simple CLI program to add ID3 tags to an album of MP3 files using
metadata from [MusicBrainz][].

* Tries to guess artist and album name based on directory name
* Automatically matches files to titles based on filename
* Adds ID3v2.4 tags to files using MusicBrainz data
* Optionally renames the files to correspond with new tag data
* Adds MusicBrainz track ID to tag

Installation
------------

Dependencies:

    pip install python-musicbrainz2 mutagen

Then clone this repository and use the executable.

Usage
-----

    cd "My Artist - My Album"
    brainztag.py --strip --genre "Rock" .
    # Follow instructions

[MusicBrainz]: http://musicbrainz.org/
