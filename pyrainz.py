#!/usr/bin/python

import sys
from optparse import OptionParser


def main(args):
    parser = OptionParser()
    options, args = parser.parse_args(args)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
