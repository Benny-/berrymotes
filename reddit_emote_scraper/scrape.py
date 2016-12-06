#!/usr/bin/env python

# --------------------------------------------------------------------
#
# Copyright (C) 2013 Marminator <cody_y@shaw.ca>
# Copyright (C) 2013 pao <patrick.oleary@gmail.com>
# Copyright (C) 2013 Daniel Triendl <daniel@pew.cc>
#
# This program is free software. It comes without any warranty, to
# the extent permitted by applicable law. You can redistribute it
# and/or modify it under the terms of the Do What The Fuck You Want
# To Public License, Version 2, as published by Sam Hocevar. See
# COPYING for more details.
#
# --------------------------------------------------------------------

import logging
import argparse
import time
from bmscraper.ratelimiter import TokenBucket
from bmscraper import BMScraper
from data import subreddits, image_blacklist, nsfw_subreddits, broken_emotes, emote_info
from os import path
import json

logger = logging.getLogger(__name__)

scraper = BMScraper()
scraper.user = 'ponymoteharvester'
scraper.password = 'berry_punch'
scraper.subreddits = subreddits
scraper.image_blacklist = image_blacklist
scraper.nsfw_subreddits = nsfw_subreddits
scraper.broken_emotes = broken_emotes
scraper.emote_info = emote_info
scraper.rate_limit_lock = TokenBucket(15, 30)

parser = argparse.ArgumentParser(description='Scrape emoticons from reddit.com\'s subreddits')

parser.add_argument(
    '-v', '--verbose',
    help="Print a few extra statements",
    action="store_const",
    dest="loglevel",
    const=logging.INFO,
)

parser.add_argument(
    '-d', '--debug',
    help="Print lots of extra debugging statements",
    action="store_const",
    dest="loglevel",
    const=logging.DEBUG,
    default=logging.WARNING,
)

parser.add_argument(
    '-dc', '--download-css',
    help="Download css files from reddit",
    action="store_const",
    dest="cssdownload",
    const=True,
    default=True,
)

parser.add_argument(
    '-ndc', '--no-css-download',
    help="Skip the css download phase",
    action="store_const",
    dest="cssdownload",
    const=False,
)

parser.add_argument(
    '-rc', '--reddit-cache',
    help="Use this directory to cache http requests",
    dest="reddit_cache",
    default="cache",
)

parser.add_argument(
    '-bt', '--berrytube-tags',
    help="Download and add berrytube tags from http://berrymotes.com/assets/data.js",
    action="store_const",
    dest="berrytube_tags",
    const=True,
    default=True,
)

parser.add_argument(
    '-nbt', '--no-berrytube-tags',
    help="Do not download berrytube tags",
    action="store_const",
    dest="berrytube_tags",
    const=False,
)

parser.add_argument(
    '-bpm', '--better-pony-emote-tags',
    help="Download and add better pony emote tags from https://ponymotes.net/bpm/bpm-resources.js",
    action="store_const",
    dest="bpm_tags",
    const=True,
    default=True,
)

parser.add_argument(
    '-nbpm', '--no-better-pony-emote-tags',
    help="Do not download bpm tags",
    action="store_const",
    dest="bpm_tags",
    const=False,
)

parser.add_argument(
    '-sc', '--session-cache',
    help="This directory will be used as a session cache. Used files like css and tag files will be stored here. css files will be linked to the proper css file in the reddit cache dir. Files will not be downloaded if they already exist in the session cache.",
    dest="session_cache",
    default="session_cache",
)

parser.add_argument(
    '-o', '--output-dir',
    help="This directory will be used for output. **TODO: Implement this argument**",
    dest="output_dir",
    default="output",
)

args = parser.parse_args()
logging.basicConfig(level=args.loglevel)

scraper.reddit_cache = args.reddit_cache
scraper.session_cache = args.session_cache
scraper.output_dir = args.output_dir

start = time.time()
scraper.download_bt_tags(args.berrytube_tags)
scraper.download_bpm_tags(args.bpm_tags)
scraper.login()
if(args.cssdownload):
    scraper.fetch_css()
scraper.process_stylesheets()
scraper.dedupe_emotes()
if(args.berrytube_tags):
    scraper.add_bt_tags()
if(args.bpm_tags):
    scraper.add_bpm_tags()
scraper.download_images()
scraper.extract_images_from_spritemaps()
# This following command will read the old emotes. It sets the modified date.
scraper.read_old_emotes()
scraper.remove_broken_emotes()
scraper.visually_dedupe_emotes()
scraper.emote_post_preferance()
scraper.remove_garbage()
logger.info("Finished scrape in {}.".format(time.time() - start))
emotes = scraper.export_emotes()

FILENAME = path.join('output', 'emotes_metadata')

with open(FILENAME + '.min.js', 'w') as f:
    f.write("var emotes_metadata = ")
    json.dump(emotes, fp=f, separators=(',', ':'), sort_keys=True)
    f.write(";")

with open(FILENAME + '.js', 'w') as f:
    f.write("var emotes_metadata = ")
    json.dump(emotes, fp=f, separators=(',', ':'), sort_keys=True, indent=2)
    f.write(";")

with open(FILENAME + '.min.json', 'w') as f:
    json.dump(emotes, fp=f, separators=(',', ':'), sort_keys=True)

with open(FILENAME + '.json', 'w') as f:
    json.dump(emotes, fp=f, separators=(',', ':'), sort_keys=True, indent=2)

