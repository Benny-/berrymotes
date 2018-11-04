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
from datetime import datetime, timedelta
import time
import calendar
from email.utils import parsedate
from dateutil.tz import tzutc
import requests
from workerpool import WorkerPool
import threading
import tinycss
import re
from collections import defaultdict
import itertools
import os
from os import path, utime
from .downloadjob import DownloadJob
from .filenameutils import get_file_path
from .emote import get_single_image_path
from .emote import get_single_hover_image_path
from .emote import extract_single_image
from .emote import has_hover
from .emote import extract_single_hover_image
from .emote import friendly_name
from .emote import canonical_name
from .emote import calculateCrop
from .emote import get_explode_directory
from .emote import setPosition
from .emote import getPosition
from dateutil import parser
from PIL import Image
import pypuzzle
import shutil
from sh import apngasm
from glob import glob
from lxml import etree
import execjs
import tempfile
import pickle
import urlparse
import json

import logging

logger = logging.getLogger(__name__)

re_numbers = re.compile(r"\d+")
re_slash = re.compile(r"/")

class NoCSSFoundException(Exception):
    pass

def _remove_duplicates(seq):
    '''https://stackoverflow.com/questions/480214/how-do-you-remove-duplicates-from-a-list-in-python-whilst-preserving-order'''
    seen = set()
    seen_add = seen.add
    return [ x for x in seq if x not in seen and not seen_add(x)]

class RedditEmoteScraper():
    def __init__(self):
        self.subreddits = []
        self.user = None
        self.password = None
        self.emotes = []
        self.image_blacklist = []
        self.nsfw_subreddits = []
        self.broken_emotes = []
        self.emote_info = []
        self.css_fallbacks = []
        self.reddit_cache = 'cache'
        self.session_cache = 'session_cache'
        self.output_dir = 'output'
        self.workers = 20
        self.rate_limit_lock = None

        self.mutex = threading.RLock()

        self._requests = requests.Session()
        self._requests.headers = {'user-agent', 'User-Agent: emoticon harvester v2.1'}

    def _remove_images_emote(self, emote):
        try:
            os.remove(get_single_image_path(self.output_dir, emote))
        except:
            pass

        try:
            os.remove(get_single_hover_image_path(self.output_dir, emote))
        except:
            pass

        try:
            shutil.rmtree(get_explode_directory(self.output_dir, emote, hover=False))
        except:
            pass

        try:
            shutil.rmtree(get_explode_directory(self.output_dir, emote, hover=True))
        except:
            pass

    def _merge_emotes(self, keeper, goner):
        logger.debug('Merging '+canonical_name(goner)+' into '+canonical_name(keeper))

        self._remove_images_emote(goner)

        keeper['names'] = keeper['names'] + goner['names']
        keeper['names'] = _remove_duplicates(keeper['names'])
        keeper['tags'] = keeper.get('tags', []) + goner.get('tags', [])
        goner['names'] = []

    def download_bt_v2_tags(self):
        logger.info('Beginning download_bt_tags()')
        download_location = os.path.join(self.session_cache, "bt-tags.v2.json")
        if not os.path.exists(download_location):
            with open(download_location, "w") as f:
                f.write(self._requests.get("https://cdn.berrytube.tv/sha1/zu5qdzSDZFLN6QV-VHMwKOwstqI/berrymotes/data/berrymotes_json_data.v2.json").text)

    def download_bpm_tags(self):
        logger.info('Beginning download_bpm_tags()')
        download_location = os.path.join(self.session_cache, "bpm-resources.js")
        if not os.path.exists(download_location):
            with open(download_location, "w") as f:
                f.write(self._requests.get("https://ponymotes.net/bpm/bpm-resources.js").text)

    def fetch_css(self):
        logger.info('Beginning fetch_css()')

        logger.debug("Fetching css using {} threads".format(self.workers))
        workpool = WorkerPool(size=self.workers)

        for subreddit in self.subreddits:
            try:
                css_subreddit_path = path.join(self.session_cache, subreddit.lower()) + '.css'
                with open(css_subreddit_path, 'r') as f:
                    pass
            except:
                workpool.put(DownloadJob(self._requests,
                                         'https://pay.reddit.com/r/{}/stylesheet'.format(subreddit),
                                         retry=5,
                                         rate_limit_lock=self.rate_limit_lock,
                                         callback=self._callback_fetch_stylesheet,
                                         **{'subreddit': subreddit}))

        workpool.shutdown()
        workpool.join()

    def _callback_fetch_stylesheet(self, response, subreddit):
        if not response:
            logger.error("Failed to fetch css for {}".format(subreddit))
            return

        if response.status_code != 200:
            logger.error("Failed to fetch css for {} (Status {})".format(subreddit, response.status_code))
            return

        text = response.text.encode('utf-8')
        modified_date_tuple = parsedate(response.headers['Last-Modified'])
        modified_date_timestamp = calendar.timegm(modified_date_tuple)

        css_cache_file_path = get_file_path(response.url, rootdir=self.reddit_cache )
        with self.mutex:
            if not os.path.exists(os.path.dirname(css_cache_file_path)):
                os.makedirs(os.path.dirname(css_cache_file_path))
        css_subreddit_path = path.join(self.session_cache, subreddit.lower()) + '.css'

        with open( css_cache_file_path, 'w' ) as f:
            f.write( text )

        utime(css_cache_file_path, (time.time(), modified_date_timestamp))

        os.symlink(os.path.relpath(css_cache_file_path, self.session_cache + '/'), css_subreddit_path );

    def _parse_css(self, data):
        cssparser = tinycss.make_parser('page3')
        css = cssparser.parse_stylesheet(data)

        if not css:
            return None

        re_emote = re.compile('a\[href[|^$]?=["\']/([\w:]+)["\']\](:hover)?(\sem|\sstrong)?')
        emotes_staging = defaultdict(dict)

        for rule in css.rules:
            if re_emote.match(rule.selector.as_css()):
                for match in re_emote.finditer(rule.selector.as_css()):
                    rules = {}

                    for declaration in rule.declarations:
                        if match.group(3):
                            name = match.group(3).strip() + '-' + declaration.name
                            rules[name] = declaration.value.as_css()
                            emotes_staging[match.group(1)].update(rules)
                        elif declaration.name in ['text-align',
                                                  'line-height',
                                                  'color'] or declaration.name.startswith('font') or declaration.name.startswith('text'):
                            name = 'text-' + declaration.name
                            rules[name] = declaration.value.as_css()
                            emotes_staging[match.group(1)].update(rules)
                        elif declaration.name in ['width',
                                                   'height',
                                                   'background-image',
                                                   'background-position',
                                                   'background',
                                                   'background-size',
                                                  ]:
                            name = declaration.name
                            if name == 'background-position':
                                val = ['{}{}'.format(v.value, v.unit if v.unit else '') for v in declaration.value if
                                       v.value != ' ']
                            else:
                                val = declaration.value[0].value
                            if match.group(2):
                                name = 'hover-' + name
                            rules[name] = val
                            emotes_staging[match.group(1)].update(rules)
        return emotes_staging

    def _process_stylesheet(self, content, subreddit):
        emotes = []
        emotes_staging = self._parse_css(content)
        if not emotes_staging:
            return

        key_func = lambda e: e[1]
        for emote, group in itertools.groupby(sorted(emotes_staging.iteritems(), key=key_func), key_func):
            emote['names'] = [a[0].encode('ascii', 'ignore') for a in group]

            full_names = []
            for name in emote['names']:
                full_names.append('r/'+subreddit+'/'+name)
            emote['names'] = emote['names'] + full_names
            emote['canonical'] = max(emote['names'], key=len)

            for name in emote['names']:
                meta_data = next((x for x in self.emote_info if x['name'] == name), None)


                if meta_data:
                    for key, val in meta_data.iteritems():
                        if key != 'name':
                            emote[key] = val

            if subreddit in self.nsfw_subreddits:
                emote['nsfw'] = True
            emote['sr'] = subreddit

            # Sometimes people make css errors, fix those.
            if 'background-image' not in emote and 'background' in emote:
                if re.match(r'^(https?:)?//', emote['background']):
                    emote['background-image'] = emote['background']
                    del emote['background']

            validEmote = True

            # Sometimes people make css errors, fix those.
            if 'background-image' not in emote and 'background' in emote:
                if re.match(r'^(https?:)?//', emote['background']):
                    emote['background-image'] = emote['background']
                    del emote['background']

            if("background-size" in emote):
                logger.warn("background-size found in emote {}. Removing width/height/background-size. See #8. Output possible incorrect.".format(canonical_name(emote)))
                del emote['width']
                del emote['height']
                del emote['background-size']

            if 'background-image' not in emote:
                logger.warn('Discarding emotes (does not contain a background-image): {}'.format(emote['names'][0]))
                validEmote = False

            if 'background-position' in emote:
                for backgroundPosValue in emote['background-position']:
                    if ',' in backgroundPosValue:
                        logger.warn('Discarding emotes (Contains illegal "," in background-position css attribute): {}'.format(emote['names'][0]))
                        validEmote = False

            if 'hover-background-position' in emote:
                for backgroundPosValue in emote['hover-background-position']:
                    if ',' in backgroundPosValue:
                        logger.warn('Discarding emotes (Contains illegal "," in hover-background-position css attribute): {}'.format(emote['names'][0]))
                        validEmote = False

            if 'background-image' in emote:
                if emote['background-image'] in self.image_blacklist:
                    logger.warn('Discarding emotes (background-image is on blacklist): {}'.format(emote['names'][0]))
                    validEmote = False

            if validEmote:
                emotes.append(emote)

        return emotes

    def _open_fallback_stylesheet(self, fallbacks, subreddit):
        if(len(fallbacks) == 0):
            raise NoCSSFoundException("Tried all fallback directories")
        else:
            css_subreddit_path = path.join(fallbacks.pop(0), subreddit.lower()) + '.css'
            try:
                return (open(css_subreddit_path), css_subreddit_path)
            except IOError as ex:
                self._open_fallback_stylesheet(fallbacks, subreddit)


    def process_stylesheets(self):
        logger.info('Beginning process_stylesheets()')

        for subreddit in self.subreddits:
            content = None
            css_subreddit_path = path.join(self.session_cache, subreddit.lower()) + '.css'

            try:
                with open( css_subreddit_path, 'r' ) as f:
                    content = f.read().decode('utf-8')
            except IOError as ex:
                logger.warn('Could not open stylesheet in session directory for ' + subreddit + ": " + str(ex))
                if(len(self.css_fallbacks) != 0):
                    try:
                        (f, css_subreddit_path) = self._open_fallback_stylesheet(list(self.css_fallbacks), subreddit)
                        with f as f:
                            content = f.read().decode('utf-8')
                    except NoCSSFoundException as ex:
                        logger.warn('Could not open stylesheet in fallback directories for ' + subreddit + ": " + str(ex))
                        content = None;

            if content is not None:
                emotes = self._process_stylesheet(content, subreddit)
                if emotes is not None:
                    modified_time = path.getmtime(css_subreddit_path)
                    for emote in emotes:
                        # The emote['last-modified'] is set to the last modify date.
                        # The last-modified http headers are used for this.
                        #
                        # Here we check if CSS file modified date. Image files
                        # are handled at a later stage. (so this value could be over-
                        # written at a later stage)
                        #
                        # A additional operation related to modified date happens
                        # in _read_old_emote(). We set the modify date to the oldest
                        # possible date, as CSS header modify date is not reliable.
                        emote['Last-Modified'] = modified_time
                        self.emotes.append(emote)
                else:
                    logger.warn('Could not process stylesheet for ' + subreddit + ", it does not contain any emoticons")

    def _emote_image_source_equal(self, a, b):
        """
        This function compares if both emotes use the same image sources.

        This method is not perfect. It ignores CSS attributes.
        A emote using the same image source (While still being visually different using CSS)
        will still be incorrectly merged.

        The _extract_single_image() function in emote.py normalizes some of the values.
        Care should be taken so both inputs are normalized.
        """
        if (a.get('background-image')           ==  b.get('background-image')           and
            a.get('background-position')        ==  b.get('background-position')        and
            a.get('width')                      ==  b.get('width')                      and
            a.get('height')                     ==  b.get('height')                     and
            a.get('hover-background-position')  ==  b.get('hover-background-position')  and
            a.get('hover-width')                ==  b.get('hover-width')                and
            a.get('hover-height')               ==  b.get('hover-height')
            ):
            return True
        return False

    def dedupe_emotes(self):
        """
        De-duplicate emotes. Based on meta-data, no visual image comparison.
        """
        logger.info('Beginning dedupe_emotes()')

        for subreddit in self.subreddits:
            subreddit_emotes = [x for x in self.emotes if x['sr'] == subreddit]
            other_subreddits_emotes = [x for x in self.emotes if x['sr'] != subreddit]
            for subreddit_emote in subreddit_emotes:
                for emote in other_subreddits_emotes:

                    # Remove duplicate names. The subreddit scraping order will determine which emote keeps their name.
                    for name in subreddit_emote['names']:
                        if name in emote['names']:
                            emote['names'].remove(name)

        for subreddit in self.subreddits:
            subreddit_emotes = [x for x in self.emotes if x['sr'] == subreddit]
            other_subreddits_emotes = [x for x in self.emotes if x['sr'] != subreddit]
            for subreddit_emote in subreddit_emotes:
                for emote in other_subreddits_emotes:

                    # This method does not do visual image comparison.
                    # Visually merging equal emotes happens at a later stage when
                    # the images have been downloaded.
                    if self._emote_image_source_equal(subreddit_emote, emote):
                        self._merge_emotes(subreddit_emote, emote)
                        self.emotes.remove(emote)

    def add_bt_tags(self):
        logger.info('Beginning add_bt_tags()')
        bt_tags = None
        try:
            with open(os.path.join(self.session_cache, "bt-tags.json")) as f:
                bt_tags = json.load(f)
        except:
            logger.warn("Could not open bt-tags.json")
            return

        for emote in self.emotes:
            for name in emote['names']:

                tag_data = None
                if name in bt_tags:
                    tag_data = bt_tags[name]

                    if tag_data:
                        if 'tags' not in emote:
                            emote['tags'] = []
                        logger.debug('Tagging: {} with {}'.format(name, tag_data))
                        emote['tags'].extend(k for k, v in tag_data['tags'].iteritems() if v['score'] >= 1)
                        if tag_data.get('specialTags'):
                            emote['tags'].extend(tag_data['specialTags'])

    def add_bt_v2_tags(self):
        logger.info('Beginning add_bt_tags()')
        bt_emotes = None
        try:
            with open(os.path.join(self.session_cache, "bt-tags.v2.json")) as f:
                bt_emotes = json.load(f)
        except:
            logger.warn("Could not open bt-tags.v2.json")
            return
            
        bt_name_tag_map = {}
        
        for bt_emote in bt_emotes:
            if 'tags' in bt_emote:
                for name in bt_emote['names']:
                    bt_name_tag_map[name] = bt_emote['tags']
        
        for emote in self.emotes:
            for name in emote['names']:
            
                if 'name' in bt_name_tag_map:
                    bt_tags = bt_name_tag_map[name]

                    if 'tags' not in emote:
                        emote['tags'] = []
                    logger.debug('Tagging: {} with {}'.format(name, bt_tags))
                    emote['tags'].extend(bt_tags)

    def add_bpm_tags(self):
        logger.info('Beginning add_bpm_tags()')
        bpm_resources_text = None
        try:
            with open(os.path.join(self.session_cache, "bpm-resources.js")) as f:
                bpm_resources_text = f.read()
        except:
            logger.warn("Could not open bpm-resources.js")
            return

        # Some people prefer to store web data in code instead of json.
        # This function extracts data from javascript code.
        def get_globals_from_js(javascript, js_var_names):

            ctx = execjs.compile(javascript)
            extracted_vars = {}
            for js_var_name in js_var_names:
                extracted_vars[js_var_name] = ctx.eval(js_var_name)
            return extracted_vars

        # bpm stores information using hexidecimals to save some bits
        # We convert those numbers back to string tags here
        # Compare to the lookup_core_emote() function in
        # https://github.com/Rothera/bpm/blob/a931dbcfaba06387bb52042e4e6bf8c06934b874/addon/bpm-store.js#L96
        def expand_BPM_tags(bpm_raw_data):
            expanded_emotes = {}
            tag_id2name = bpm_raw_data['tag_id2name']
            emote_map = bpm_raw_data['emote_map']
            for name, emote_data in emote_map.iteritems():
                parts = emote_data.split(',')

                emote = {}
                expanded_emotes[name.split("/").pop()] = emote

                flag_data = parts[0]
                tag_data = parts[1]

                flags = int(flag_data[0:1], 16)  # Hexadecimal
                source_id = int(flag_data[1:3], 16)  # Hexadecimal
                size = int(flag_data[3:7], 16)  # Hexadecimal
                # var is_nsfw = (flags & _FLAG_NSFW);
                # var is_redirect = (flags & _FLAG_REDIRECT);

                tags_ints = []
                start = 0
                while True:
                    tag_str = tag_data[start: start + 2]
                    if tag_str == "":
                        break
                    tags_ints.append(int(tag_str, 16))  # Hexadecimal
                    start += 2

                emote['tags'] = [tag_id2name[tag_int][1:] for tag_int in tags_ints]

            return expanded_emotes

        bpm_raw_data = get_globals_from_js(bpm_resources_text, [
                                    'sr_id2name',
                                    'sr_name2id',
                                    'tag_id2name',
                                    'tag_name2id',
                                    'emote_map',
                                ])
        bpm_emotes = expand_BPM_tags(bpm_raw_data)

        for emote in self.emotes:
            for name in emote['names']:
                if name in bpm_emotes:
                    emote['tags'] = emote.get('tags', []) + bpm_emotes[name]['tags']

    def download_images(self):
        logger.info('Beginning download_images()')
        logger.debug("Downloading images using {} threads".format(self.workers))
        workpool = WorkerPool(size=self.workers)

        def create_download_jobs(key_func):
            for image_url, group in itertools.groupby(sorted(self.emotes, key=key_func), key_func):
                if not image_url:
                    continue

                file_path = get_file_path(image_url, rootdir=self.reddit_cache)
                if not path.isfile(file_path):
                    workpool.put(DownloadJob(self._requests,
                                             urlparse.urljoin('https://s3.amazonaws.com/',image_url),
                                             retry=5,
                                             rate_limit_lock=self.rate_limit_lock,
                                             callback=self._callback_download_image,
                                             **{'image_path': file_path}))

        with self.mutex:
            create_download_jobs( lambda e: e['background-image'])
            create_download_jobs( lambda e: e.get('hover-background-image'))

        workpool.shutdown()
        workpool.join()

    def _callback_download_image(self, response, image_path):

        if response.status_code != 200:
            logger.error("Failed to fetch image at {} (Status {})".format(response.url, response.status_code))
            return

        data = response.content

        image_dir = path.dirname(image_path)

        modified_date_tuple = parsedate(response.headers['Last-Modified'])
        modified_date_timestamp = calendar.timegm(modified_date_tuple)

        with self.mutex:
            if not path.exists(image_dir):
                os.makedirs(image_dir)

        with open(image_path, 'wb') as f:
            f.write(data)

        utime(image_path, (time.time(), modified_date_timestamp))

    def _explode_emote(self, emote, background_image_path, hover):
        '''
        Create a {emote name}_exploded directory
        This directory contains all frames.
        The frames are cut out a spritemap if needed.

        Returns True if animation was not cut out a spritemap. (background image size == individual frames sizes)
        Returns False if animation was part of a spritemap and cutting was required. (background image size != individual frames sizes)

        Does not handle hover images.
        '''
        explode_dir = get_explode_directory(self.output_dir, emote, hover)
        if not os.path.exists(explode_dir):
            os.makedirs(explode_dir)
        shutil.copyfile(background_image_path, os.path.join(explode_dir, "background.png"))
        apngasm('--force', '-D', os.path.join(explode_dir, "background.png"), "-o", explode_dir, '-j', '-x')
        os.remove(os.path.join(explode_dir, "background.png"))

        frames_paths = glob(os.path.join(explode_dir, '*.png'))
        for frame_path in frames_paths:
            background_image = Image.open(frame_path)
            if hover:
                extracted_single_image = extract_single_hover_image(emote, background_image)
            else:
                extracted_single_image = extract_single_image(emote, background_image)
            background_image.close()

            if cmp(background_image.size, extracted_single_image.size) != 0:
                extracted_single_image.save(frame_path)
            else:
                return True
        return False

    def _calculate_frame_delay(self, delay_text):
        '''Calucate delay in ms from apng's delay representation'''
        delay = int(round(float(delay_text[0:delay_text.index('/')]) / float(delay_text[delay_text.index('/') + 1:]) * 1000))
        if delay == 0:
            delay = 10;
        return delay

    def _reassemble_emote_png(self, emote, hover):
        '''
        Reconstructs a emote from a exploded form to animated .png
        '''
        explode_dir = get_explode_directory(self.output_dir, emote, hover)
        animation_file = os.path.join(explode_dir, 'animation.xml')
        with open(animation_file, 'r') as f:
            animation_xml = etree.parse(f).getroot()

        if(hover):
            image_path = get_single_image_path(self.output_dir, emote, True)
        else:
            image_path = get_single_image_path(self.output_dir, emote, False)

        args = []
        args = args + ['--force', '-o', image_path]
        for frame_xml in animation_xml:
            frame_file = os.path.join(explode_dir, frame_xml.get('src'))
            delay = self._calculate_frame_delay(frame_xml.get('delay'))
            args.append(frame_file)
            args.append(delay)

        apngasm( *args )

    def _handle_background_for_emote(self, emote, background_image_path, background_image):
        extracted_single_image = extract_single_image(emote, background_image)

        if not os.path.exists(os.path.dirname(get_single_image_path(self.output_dir, emote))):
            os.makedirs(os.path.dirname(get_single_image_path(self.output_dir, emote)))

        if emote['base_img_animation']:
            same_as_spritemap = self._explode_emote(emote, background_image_path, hover=False)
            if not same_as_spritemap:
                self._reassemble_emote_png(emote, hover=False)
        else:
            same_as_spritemap = cmp(background_image.size, extracted_single_image.size) == 0
            if not same_as_spritemap:
                with open(get_single_image_path(self.output_dir, emote), 'wb') as f:
                    extracted_single_image.save(f)

        if same_as_spritemap:
            shutil.copyfile(background_image_path, get_single_image_path(self.output_dir, emote, background_image.format))
            shutil.copystat(background_image_path, get_single_image_path(self.output_dir, emote))

        if has_hover(emote) and 'hover-background-image' not in emote:
            if emote['base_img_animation']:
                emote['hover_img_animation'] = True
                same_as_spritemap = self._explode_emote(emote, background_image_path, hover=True)
                self._reassemble_emote_png(emote, hover=True)
            else:
                emote['hover_img_animation'] = False
                same_as_spritemap = cmp(background_image.size, extracted_single_image.size) == 0
                assert same_as_spritemap is False # A hover can never be the same as the spritemap, as the base image shares the spritemap
                with open(get_single_hover_image_path(self.output_dir, emote), 'wb') as f:
                    extracted_single_image.save(f)

    def _handle_hover_background_for_emote(self, emote, hover_background_image_path, hover_background_image):
        extracted_single_hover_image = extract_single_hover_image(emote, hover_background_image)

        if emote['hover_img_animation']:
            same_as_spritemap = self._explode_emote(emote, hover_background_image_path, hover=True)
            if not same_as_spritemap:
                self._reassemble_emote_png(emote, hover=True)
        else:
            same_as_spritemap = cmp(hover_background_image.size, extracted_single_hover_image.size) == 0
            if not same_as_spritemap:
                with open(get_single_hover_image_path(self.output_dir, emote), 'wb') as f:
                    extracted_single_hover_image.save(f)

        if same_as_spritemap:
            shutil.copyfile(hover_background_image_path, get_single_hover_image_path(self.output_dir, emote, hover_background_image.format))
            shutil.copystat(hover_background_image_path, get_single_hover_image_path(self.output_dir, emote))

    def _extract_images_from_spritemaps(self, emotes):

        def is_apng(image_data):
            return 'acTL' in image_data[0:image_data.find('IDAT')]

        key_func = lambda e: e['background-image']
        for image_url, emote_group in itertools.groupby(sorted(emotes, key=key_func), key_func):

            if not image_url:
                continue

            background_image_path = get_file_path(image_url, rootdir=self.reddit_cache)
            background_image_path = path.realpath(background_image_path)
            modified_time = path.getmtime(background_image_path)
            with open(background_image_path, 'rb') as f:
                background_image_data = f.read()
            animated = False
            if is_apng(background_image_data):
                animated = True;

            background_image = Image.open(open(background_image_path, 'rb'))
            for emote in emote_group:
                emote['base_img_animation'] = animated
                self._handle_background_for_emote(emote, background_image_path, background_image)
                if (emote['Last-Modified'] < modified_time):
                    emote['Last-Modified'] = modified_time
            background_image.close()

        key_func = lambda e: e.get('hover-background-image')
        for image_url, emote_group in itertools.groupby(sorted(emotes, key=key_func), key_func):

            if not image_url:
                continue

            hover_background_image_path = get_file_path(image_url, rootdir=self.reddit_cache)
            background_image_path = path.realpath(hover_background_image_path)
            modified_time = path.getmtime(hover_background_image_path)
            with open(background_image_path, 'rb') as f:
                hover_background_image_data = f.read()
            animated = False
            if is_apng(hover_background_image_data):
                animated = True;

            hover_background_image = Image.open(open(hover_background_image_path, 'rb'))
            for emote in emote_group:
                if(animated):
                    emote['hover_img_animation'] = True
                elif not hasattr(emote, 'hover_img_animation'):
                    emote['hover_img_animation'] = False
                self._handle_hover_background_for_emote(emote, hover_background_image_path, hover_background_image)
                if (emote['Last-Modified'] < modified_time):
                    emote['Last-Modified'] = modified_time
            hover_background_image.close()

    def extract_images_from_spritemaps(self):
        logger.info('Beginning extract_images_from_spritemaps()')
        self._extract_images_from_spritemaps(self.emotes)

    def cropEmotes(self):
        logger.info('Beginning cropEmotes()')
        for emote in self.emotes:
            base_path = get_single_image_path(self.output_dir, emote)
            if not has_hover(emote):
                if(emote['base_img_animation']):
                    explode_dir = get_explode_directory(self.output_dir, emote, hover=False)
                    frames_paths = glob(os.path.join(explode_dir, '*.png'))
                    images = []
                    for frame_path in frames_paths:
                        images.append(Image.open(frame_path))
                    crop = calculateCrop(*images)
                    if crop is not None:
                        (x, y) = getPosition(emote, 'background-position')
                        width = emote['width']
                        height = emote['height']
                        if( (x,y,width,height) != crop):
                            for i, p in zip(images, frames_paths):
                                c = i.crop(crop)
                                c.save(p)
                                c.close()
                                (width, height) = c.size
                            setPosition(emote, 'background-position', x, y)
                            emote['width'] = width
                            emote['height'] = height
                            self._reassemble_emote_png(emote, hover=False)
                    else:
                        logger.warn('Emote: '+canonical_name(emote)+' is empty')
                    for i in images:
                        i.close()
                else:
                    i = Image.open(base_path)
                    crop = calculateCrop(i)
                    if crop is not None:
                        (x, y) = getPosition(emote, 'background-position')
                        (width, height) = i.size
                        if( (x,y,width,height) != crop):
                            c = i.crop(crop)
                            c.save(base_path)
                            c.close()
                            (width, height) = c.size
                            setPosition(emote, 'background-position', x, y)
                            emote['width'] = width
                            emote['height'] = height
                    else:
                        logger.warn('Emote: '+canonical_name(emote)+' is empty')
                    i.close()
            else:
                if(emote['base_img_animation']):
                    if(emote['hover_img_animation']):
                        pass
                    else:
                        pass
                else:
                    if(emote['hover_img_animation']):
                        pass
                    else:
                        pass

    def read_old_emotes(self):
        """
        This function will remove a emote's image from disk if the emote's image has changed.
        It will try to check if a emote has not changed and change the Last-Modified in the appropriate way.
        It will create self.old_emotes or set it to None.
        """
        logger.info('Beginning read_old_emotes()')
        # XXX: Filename is defined in two locations now. Here and one level higher in scrape.py.
        FILENAME = path.join(self.output_dir, 'emotes_metadata')

        old_emotes = None
        try:
            with open(FILENAME + '.json') as f:
                old_emotes = json.load(f)
        except:
            logger.warn("Could not read old emote file, this is expected if you run this for the first time.")

        self.old_emotes = old_emotes
        if old_emotes is None:
            return

        old_emote_map = {}
        for old_emote in old_emotes:
            old_emote_map[canonical_name(old_emote)] = old_emote

        changed_emotes = []
        for new_emote in self.emotes:
            if canonical_name(new_emote) in old_emote_map:
                old_emote = old_emote_map[canonical_name(new_emote)]
                equal = self._emote_image_source_equal(old_emote, new_emote)
                if not equal:
                    logger.info("Emote: " + canonical_name(old_emote) + "'s spritemap has been updated. Emote marked as updated since comparing code is missing. TODO: Visually compare the old and new emote to be sure they are changed.")
                    # Someone might have added a image to a spritemap,
                    # this will cause the background-image to change
                    # making the old and new emote unequal, even if they look exactly the same.
                    # There is only one solution for this:
                    # TODO: Visually compare the old and new emote to be sure they are changed.
                    self._remove_images_emote(new_emote)
                    changed_emotes.append(new_emote)
                else:
                    # We set the new emote's modified date from the old one.
                    # The new_emote modified date comes from the css or image files.
                    # But the old and new emote are the same, so we will keep the oldest
                    # modified date.
                    #
                    # The additional new_emote['Last-Modified'] > old_emote['Last-Modified'] check
                    # is here if this script is run on old css data (If old_emotes are
                    # actually generated from newer css data) (we always keep the oldest
                    # valid modify date).
                    if new_emote['Last-Modified'] > old_emote['Last-Modified']:
                        new_emote['Last-Modified'] = old_emote['Last-Modified']
                    # Technically its not correct, the emote's css might have changed. Meh.

        # The changed emotes will need to be re-extracted.
        self._extract_images_from_spritemaps(changed_emotes)

    def remove_broken_emotes(self):
        logger.info('Beginning remove_broken_emotes()')
        erase = []
        beginning_of_time = datetime(1970,1,1)
        for broken_emote in self.broken_emotes:
            marked_on_utc_seconds = (broken_emote['marked_on'] - beginning_of_time).total_seconds()
            for emote in self.emotes:
                if(canonical_name(emote) == broken_emote['canonical_name']):
                    erase.append(emote)

                    # Consider calling self._remove_images_emote(emote) here to remove the images associated with the emote

                    if(emote['Last-Modified'] > marked_on_utc_seconds):
                        logger.warn('Emote: ' + canonical_name(emote) + ' is marked for removal, but has a modify date after the mark date. Please review this emote for re-approval into the emote pool.')
        self.emotes = [emote for emote in self.emotes if emote not in erase]

    def visually_dedupe_emotes(self):
        logger.info('Beginning visually_dedupe_emotes()')
        processed_emotes = []
        duplicates = []
        puzzle = pypuzzle.Puzzle()
        # Some images like 'minigunkill' got a generic vector (a vector consisting of only zero's)
        # These images where merged with other images who also got a generic vector.
        # Setting noise cutoff fixed this.
        puzzle.set_noise_cutoff(0)

        for subreddit in self.subreddits:
            subreddit_emotes = [x for x in self.emotes if x['sr'] == subreddit]

            logger.info('Visually dedupeing emotes in subreddit '+subreddit)
            for emote in subreddit_emotes:

                if emote in duplicates:
                    continue

                # Ignore animations as they sometime start with a blank (transparant) frame.
                # We only check the first frame and thus they are visually the same as any other blank picture.
                if emote['base_img_animation'] or (has_hover(emote) and emote['hover_img_animation']):
                    continue

                image_path = get_single_image_path(self.output_dir, emote)
                logger.debug('puzzle.get_cvec_from_file('+image_path+')')
                vector = puzzle.get_cvec_from_file(image_path)

                for other_emote, other_compressed_vector in processed_emotes:
                    other_vector = puzzle.uncompress_cvec(other_compressed_vector)

                    if other_emote in duplicates:
                        continue

                    distance = puzzle.get_distance_from_cvec(vector, other_vector)
                    if( distance > 0 ):
                        pass # Images are not equal.
                    else:
                        # Images are equal! Lets merge them.
                        self._merge_emotes(other_emote, emote)
                        duplicates.append(emote)
                processed_emotes.append((emote, puzzle.compress_cvec(vector)))

        self.emotes = [emote for emote in self.emotes if emote not in duplicates]

    def emote_post_preferance(self):
        logger.info('Beginning emote_post_preferance()')
        '''A emote's first name will be used for posting. Some names are preferred over other names. We re-order the names here.'''

        # We push all the numbered names back. They are generally not very descriptive.
        for emote in self.emotes:
            numbered_names = []
            descriptive_names = []
            for name in emote['names']:
                if len(re_numbers.findall(name)) > 0:
                    numbered_names.append(name)
                else:
                    descriptive_names.append(name)
            emote['names'] = descriptive_names + numbered_names

        # We push all the names containing slashes back.
        for emote in self.emotes:
            long_names = []
            descriptive_names = []
            for name in emote['names']:
                if len(re_slash.findall(name)) > 0:
                    long_names.append(name)
                else:
                    descriptive_names.append(name)
            emote['names'] = descriptive_names + long_names

    def remove_garbage(self):
        logger.info('Beginning remove_garbage()')
        for emote in self.emotes:
            if 'tags' in emote:
                emote['tags'] = _remove_duplicates(emote['tags'])
                if '' in emote['tags']:
                    emote['tags'].remove('')

    def export_emotes(self):
        return self.emotes
