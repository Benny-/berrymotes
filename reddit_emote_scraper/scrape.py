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
import requests
from bmscraper.ratelimiter import TokenBucket
from bmscraper import BMScraper
from data import subreddits, image_blacklist, nsfw_subreddits, emote_info
from os import path
import json

logger = logging.getLogger(__name__)

scraper = BMScraper()
scraper.user = 'ponymoteharvester'
scraper.password = 'berry_punch'
scraper.subreddits = subreddits
scraper.image_blacklist = image_blacklist
scraper.nsfw_subreddits = nsfw_subreddits
scraper.emote_info = emote_info
scraper.rate_limit_lock = TokenBucket(15, 30)
scraper.tags_data = requests.get("http://berrymotes.com/assets/data.js").json()

parser = argparse.ArgumentParser(description='Scrape emoticons from reddit.com')
parser.add_argument(
    '-d', '--debug',
    help="Print lots of debugging statements",
    action="store_const", dest="loglevel", const=logging.DEBUG,
    default=logging.WARNING,
)
parser.add_argument(
    '-v', '--verbose',
    help="Be verbose",
    action="store_const", dest="loglevel", const=logging.INFO,
)
args = parser.parse_args()    
logging.basicConfig(level=args.loglevel)

start = time.time()
scraper.scrape()
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

