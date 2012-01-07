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

```sh
$ cd "Sophie Hunger - Monday's Ghost"

$ ls
10-rise_and_fall.mp3  14-spiegelbild.mp3      4-walzer_für_niemand.mp3   8-the_tourist.mp3
11-drainpipes.mp3     1-shape.mp3             5-birth-day.mp3            9-teenage_spirit.mp3
12-mondays_ghost.mp3  2-the_boat_is_full.mp3  6-sophie_hunger_blues.mp3
13-house_of_gods.mp3  3-a_protest_song.mp3    7-round_and_round.mp3

$ brainztag.py --strip --genre "Folk-Pop" .   
Artist: Sophie Hunger
Disc: Monday's Ghost
Found 2 discs with 14 tracks. Choose the correct one.
1: Sophie Hunger - Monday's Ghost (2009-02-27)
2: Sophie Hunger - Monday's Ghost (2008-10-10)
Disc: 2

Sophie Hunger - Monday's Ghost - 2008-10-10 - 14 tracks
             Musicbrainz track          |               Filename             
 1. Shape                          3:32 | 1-shape.mp3                    3:32
 2. The Boat Is Full               3:02 | 2-the_boat_is_full.mp3         3:02
 3. A Protest Song                 3:24 | 3-a_protest_song.mp3           3:24
 4. Walzer für Niemand             2:25 | 4-walzer_für_niemand.mp3       2:25
 5. Birth-Day                      3:20 | 5-birth-day.mp3                3:19
 6. Sophie Hunger Blues            5:14 | 6-sophie_hunger_blues.mp3      5:13
 7. Round and Round                3:28 | 7-round_and_round.mp3          3:28
 8. The Tourist                    3:49 | 8-the_tourist.mp3              3:49
 9. Teenage Spirit                 3:48 | 9-teenage_spirit.mp3           3:48
10. Rise and Fall                  5:31 | 10-rise_and_fall.mp3           5:31
11. Drainpipes                     3:39 | 11-drainpipes.mp3              3:38
12. Monday's Ghost                 4:50 | 12-mondays_ghost.mp3           4:50
13. House of Gods                  3:47 | 13-house_of_gods.mp3           3:47
14. Spiegelbild (feat. Stephan Eicher) 3:50 | 14-spiegelbild.mp3             3:50
Continue? ([t]ag, [r]ename, [B]oth, [c]ancel): b
............................

$ ls
01. Shape.mp3               06. Sophie Hunger Blues.mp3  11. Drainpipes.mp3
02. The Boat Is Full.mp3    07. Round and Round.mp3      12. Monday's Ghost.mp3
03. A Protest Song.mp3      08. The Tourist.mp3          13. House of Gods.mp3
04. Walzer für Niemand.mp3  09. Teenage Spirit.mp3       14. Spiegelbild (feat. Stephan Eicher).mp3
05. Birth-Day.mp3           10. Rise and Fall.mp3
```

[MusicBrainz]: http://musicbrainz.org/
