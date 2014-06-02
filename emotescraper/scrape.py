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
import time
import requests
from bmscraper.ratelimiter import TokenBucket

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
from bmscraper import BMScraper

from data import subreddits, image_blacklist, nsfw_subreddits, emote_info
import pickle
import json

scraper = BMScraper()
scraper.user = 'ponymoteharvester'
scraper.password = 'berry_punch'
scraper.subreddits = subreddits
scraper.image_blacklist = image_blacklist
scraper.nsfw_subreddits = nsfw_subreddits
scraper.emote_info = emote_info
scraper.rate_limit_lock = TokenBucket(15, 30)
scraper.tags_data = requests.get("http://btc.berrytube.tv/berrymotes/data.js").json()

start = time.time()
scraper.scrape()
logger.info("Finished scrape in {}.".format(time.time() - start))
emotes = scraper.export_emotes()

FILENAME = "emotes_metadata"
with open(FILENAME + '.min.js', 'w') as f:
    f.write("var emotes_metadata = ")
    json.dump(emotes, fp=f, separators=(',', ':'))
    f.write(";")

with open(FILENAME + '.js', 'w') as f:
    f.write("var emotes_metadata = ")
    json.dump(emotes, fp=f, separators=(',', ':'), indent=2)
    f.write(";")

with open(FILENAME + '.min.json', 'w') as f:
    json.dump(emotes, fp=f, separators=(',', ':'))

with open(FILENAME + '.json', 'w') as f:
    json.dump(emotes, fp=f, separators=(',', ':'), indent=2)

with open(FILENAME + '.pickle_v0', "w") as f:
    pickle.dump(emotes, file=f, protocol=0)

with open(FILENAME + '.pickle_v1', "wb") as f:
    pickle.dump(emotes, file=f, protocol=1)

with open(FILENAME + '.pickle_v2', "wb") as f:
    pickle.dump(emotes, file=f, protocol=2)
