#!/usr/bin/python

import sys
import os.path
import glob
from optparse import OptionParser


def main(args):
    usage = "Usage: %prog [options] DIRECTORY"
    parser = OptionParser(usage=usage, version="%prog 0.1")
    options, args = parser.parse_args(args)
    
    if len(args) != 1 or not os.path.isdir(args[0]):
        parser.error("first argument must be directory")

    directory = args[0]
    files = glob.glob(os.path.join(directory, "*.mp3"))
    
    try:
        artist = raw_input('Artist: ')
        disc_title = raw_input('Disc: ')
    except KeyboardInterrupt:
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
