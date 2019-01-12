#!/usr/bin/env python3
#-*- coding:utf-8 -*-

# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
###############################################################################

"""Saves all images in hashed form in the emoticon server image directory

"""

import io
import os
import sys
import json
import shutil
import hashlib
import base64
import logging
import argparse
from pathlib import Path

logger = logging.getLogger(__name__)

# This function returns a path to the primary image of this emote.
def get_single_image_path(root, emote, extension=None):
    if extension:
        emote['single_image_extension'] = extension.lower()

    if 'single_image_extension' in emote:
        extension = emote['single_image_extension']
    else:
        extension = 'png'

    return root / (emote['canonical'] + "." + extension)

# Please note: A emote's hover image is optional.
# There is no guarantee this image exists.
def get_single_hover_image_path(root, emote, extension=None):
    if extension:
        emote['single_hover_image_extension'] = extension.lower()

    if 'single_hover_image_extension' in emote:
        extension = emote['single_hover_image_extension']
    else:
        extension = 'png'

    return root / (emote['canonical'] + "_hover." + extension)

# Stolen from reddit so our filenames look like their filenames.
def _filename_from_content(contents):
    hash_bytes = hashlib.sha256(contents).digest()
    return base64.urlsafe_b64encode(hash_bytes).decode('ascii').rstrip("=")

def cdn_file(path: Path, cdn_directory: Path):
    suffix = path.suffix
    if suffix == '.jpeg':
        suffix = '.jpg'
    assert(suffix == '.jpg' or suffix == '.png' or suffix == '.webp')
    
    with open(path, 'rb') as f:
        contents = f.read()
    cdn_filename = _filename_from_content(contents) + suffix
    cdn_path = cdn_directory / 'sha256' / cdn_filename
    
    if(cdn_path.exists()):
        with open(path, 'rb') as f:
            cdn_file_contents = f.read()
        if(contents != cdn_file_contents):
            raise Exception("Hash collision detected")
    else:
        logger.info("Writing {} to {}.".format(path, cdn_path))
        with open(cdn_path, 'wb') as f:
            f.write(contents)
        shutil.copystat(path, cdn_path)

def recursiveUploadFiles(directory: Path, cdn_directory: Path):
    for path in directory.iterdir():
        if path.is_file():
            cdn_file(path, cdn_directory)
            
        else:
            logger.info("Handling directory {}.".format(path))
            recursiveUploadFiles(path, cdn_directory)

def transformEmotes(reddit_scraper_output: Path, cdn_directory: Path):
    with io.open(reddit_scraper_output / 'emotes_metadata.json', 'r', encoding='utf-8') as f:
        emotes = json.load(f)
    
    for emote in emotes:
        path = get_single_image_path(reddit_scraper_output, emote)
        with open(path, 'rb') as f:
            contents = f.read()
        suffix = path.suffix
        if suffix == '.jpeg':
            suffix = '.jpg'
        emote['base_img_src'] = 'https://mylittleserver.nl/emojis/sha256/' + _filename_from_content(contents) + suffix
        emote.pop('has_hover')
        emote.pop('sr')
        if 'single_image_extension' in emote:
            emote.pop('single_image_extension')
        if 'background-position' in emote:
            emote.pop('background-position')
        emote.pop('background-image')
        if 'hover-background-image' in emote:
            path = get_single_hover_image_path(reddit_scraper_output, emote)
            with open(path, 'rb') as f:
                contents = f.read()
            suffix = path.suffix
            if suffix == '.jpeg':
                suffix = '.jpg'
            emote['base_img_src'] = 'https://mylittleserver.nl/emojis/sha256/' + _filename_from_content(contents) + suffix
            emote.pop('hover-background-image')
            if 'single_hover_image_extension' in emote:
                emote.pop('single_hover_image_extension')
            if 'hover-background-position' in emote:
                emote.pop('hover-background-position')
    
    emotes = sorted(emotes, key=lambda e: e['Last-Modified'], reverse=True)
    
    with io.open(cdn_directory / 'all-reddit-emojis.json', 'w', encoding='utf-8') as f:
        f.write(json.dumps(emotes))
    
def main(arguments):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument(
        '-d', '--debug',
        help="Print lots of extra debugging statements",
        action="store_const",
        dest="loglevel",
        const=logging.DEBUG,
        default=logging.WARNING,
    )

    parser.add_argument(
        'input',
        help="The output directory of reddit_emote_scraper",
    )
    
    parser.add_argument(
        'output',
        help="The output directory where the images will be stored",
    )
    
    args = parser.parse_args(arguments)
    
    logging.basicConfig(level=args.loglevel)
    reddit_scraper_output = Path(args.input)
    cdn_directory = Path(args.output)
    
    (cdn_directory / 'sha256').mkdir(parents=False, exist_ok=True)
    
    path = reddit_scraper_output / 'r'
    logger.info("Handling directory {}.".format(path))
    recursiveUploadFiles(path, cdn_directory)
    transformEmotes(reddit_scraper_output, cdn_directory)
    
    return os.EX_OK

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

