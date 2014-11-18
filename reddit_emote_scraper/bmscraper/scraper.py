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
from .emote import get_single_image_path, get_single_hover_image_path, extract_single_image, has_hover, extract_single_hover_image, friendly_name, canonical_name, get_explode_directory
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

import logging

logger = logging.getLogger(__name__)

re_numbers = re.compile(r"\d+")
re_slash = re.compile(r"/")

def _remove_duplicates(seq):
    '''https://stackoverflow.com/questions/480214/how-do-you-remove-duplicates-from-a-list-in-python-whilst-preserving-order'''
    seen = set()
    seen_add = seen.add
    return [ x for x in seq if x not in seen and not seen_add(x)]

class BMScraper():
    def __init__(self):
        self.subreddits = []
        self.user = None
        self.password = None
        self.emotes = []
        self.image_blacklist = []
        self.nsfw_subreddits = []
        self.emote_info = []
        self.tags_data = {}
        self.cache_dir = 'cache'
        self.workers = 20
        self.rate_limit_lock = None

        self.mutex = threading.RLock()

        self._requests = requests.Session()
        self._requests.headers = {'user-agent', 'User-Agent: Ponymote harvester v2.0 by /u/marminatoror'}

    def _remove_images_emote(self, emote):
        try:
            os.remove(get_single_image_path(emote))
        except:
            pass

        try:
            os.remove(get_single_hover_image_path(emote))
        except:
            pass

        try:
            shutil.rmtree(get_explode_directory(emote))
        except:
            pass

    def _merge_emotes(self, keeper, goner):
        logger.debug('Merging '+canonical_name(goner)+' into '+canonical_name(keeper))
        
        self._remove_images_emote(goner)
        
        keeper['names'] = keeper['names'] + goner['names']
        keeper['names'] = _remove_duplicates(keeper['names'])
        keeper['tags'] = keeper.get('tags', []) + goner.get('tags', [])
        goner['names'] = []

    def _login(self):
        logger.info('Logging in')

        if self.user and self.password:
            body = {'user': self.user, 'passwd': self.password, "rem": False}
            self.rate_limit_lock and self.rate_limit_lock.acquire()
            self._requests.post('http://www.reddit.com/api/login', body)

    def _fetch_css(self):
        logger.info('Beginning to fetch css files')

        if not os.path.exists('css'):
            os.makedirs('css')

        logger.debug("Fetching css using {} threads".format(self.workers))
        workpool = WorkerPool(size=self.workers)

        for subreddit in self.subreddits:
            try:
                css_subreddit_path = path.join('css', subreddit) + '.css'
                with open( css_subreddit_path, 'r' ) as f:
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

    def _callback_fetch_stylesheet(self, response, subreddit=None):
        if not response:
            logger.error("Failed to fetch css for {}".format(subreddit))
            return

        if response.status_code != 200:
            logger.error("Failed to fetch css for {} (Status {})".format(subreddit, response.status_code))
            return

        text = response.text.encode('utf-8')
        modified_date_tuple = parsedate(response.headers['Last-Modified'])
        modified_date_timestamp = calendar.timegm(modified_date_tuple)
        
        css_cache_file_path = get_file_path(response.url, rootdir=self.cache_dir )
        with self.mutex:
            if not os.path.exists(os.path.dirname(css_cache_file_path)):
                os.makedirs(os.path.dirname(css_cache_file_path))
        css_subreddit_path = path.join('css', subreddit) + '.css'

        with open( css_cache_file_path, 'w' ) as f:
            f.write( text )

        utime(css_cache_file_path, (time.time(), modified_date_timestamp))

        os.symlink(os.path.relpath(css_cache_file_path, 'css/'), css_subreddit_path );

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
                                                   'background', ]:
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

    def _process_stylesheet(self, content, subreddit=None):

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

                tag_data = None
                if name in self.tags_data:
                    tag_data = self.tags_data[name]

                if tag_data:
                    if 'tags' not in emote:
                        emote['tags'] = []
                    logger.debug('Tagging: {} with {}'.format(name, tag_data))
                    emote['tags'].extend(k for k, v in tag_data['tags'].iteritems() if v['score'] >= 1)
                    if tag_data.get('specialTags'):
                        emote['tags'].extend(tag_data['specialTags'])

                    if 'added_date' in tag_data:
                        added_date = parser.parse(tag_data['added_date'])
                        now = datetime.now(tzutc())
                        if now - added_date < timedelta(days=7):
                            emote['tags'].append('new')

            if subreddit in self.nsfw_subreddits:
                emote['nsfw'] = True
            emote['sr'] = subreddit

            # Sometimes people make css errors, fix those.
            if ('background-image' not in emote
                and 'background' in emote
                and emote['background'].startswith('http')):
                emote['background-image'] = emote['background']
                del emote['background']

            # need at least an image for a ponymote. Some trash was getting in.
            # 1500 pixels should be enough for anyone!
            if ('background-image' in emote
                and emote['background-image'] not in self.image_blacklist
                and 'height' in emote and emote['height'] < 1500
                and 'width' in emote and emote['width'] < 1500):
                emotes.append(emote)
            else:
                logger.warn('Discarding emotes {}'.format(emote['names'][0]))
        return emotes

    def _process_stylesheets(self):
        logger.info('Beginning to process stylesheets')

        for subreddit in self.subreddits:
            content = None
            css_subreddit_path = path.join('css', subreddit) + '.css'

            try:
                with open( css_subreddit_path, 'r' ) as f:
                    content = f.read().decode('utf-8')
                    emotes = self._process_stylesheet(content, subreddit)
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
            except Exception as ex:
                logger.warn('Not parsing stylesheet for ' + subreddit + ": " + str(ex))

    def _emote_image_source_equal(self, a, b):
        """
        This function compares if both emotes use the same image sources.
        
        This method is not perfect. It ignores CSS attributes.
        A emote using the same image source (While still being visually different using CSS)
        will still be incorrectly merged.
        
        The _extract_single_image() function in emote.py normalizes some of the values.
        Care should be taken so both inputs are normalized (or ensure both are NOT normalized).
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

    def _dedupe_emotes(self):
        logger.info('Beginning to de-duplicate emotes based on meta-data')

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

    def _read_old_emotes(self):
        """
        This function will remove a emote's image from disk if the emote's image has changed.
        It will try to check if a emote has not changed and change the Last-Modified in the appropriate way.
        It will create self.old_emotes or set it to None.
        """
        # XXX: Filename is defined in two locations now. Here and one level higher in scrape.py.
        FILENAME = path.join('output', 'emotes_metadata')

        old_emotes = None
        try:
            with open(FILENAME + '.pickle_v2',"rb") as f:\
                old_emotes = pickle.Unpickler(f).load()
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

    def _add_bpm_tags(self):
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
        # Compare to the lookup_core_emote() function in https://ponymotes.net/bpm/betterponymotes.user.js
        def expand_BPM_tags(bpm_raw_data):
            expanded_emotes = {}
            tag_id2name = bpm_raw_data['tag_id2name']
            emote_map = bpm_raw_data['emote_map']
            for name, emote_data in emote_map.iteritems():
                parts = emote_data.split(',')
                
                emote = {}
                expanded_emotes[name.split("/").pop()] = emote
                
                flag_data = parts[0];
                tag_data = parts[1];
                
                flags = int(flag_data[0:1], 16) # Hexadecimal
                source_id = int(flag_data[1:3], 16); # Hexadecimal
                size = int(flag_data[3:7], 16); # Hexadecimal
                # var is_nsfw = (flags & _FLAG_NSFW);
                is_redirect = False
                # var is_redirect = (flags & _FLAG_REDIRECT);

                base = None

                tags_ints = [];
                start = 0;
                while True:
                    tag_str = tag_data[start: start+2]
                    if tag_str == "":
                        break
                    tags_ints.append(int(tag_str, 16)) # Hexadecimal
                    start += 2

                if(is_redirect):
                    base = parts[2]
                else:
                    base = name
                
                emote['tags'] = [ tag_id2name[tag_int] for tag_int in tags_ints]
                
            return expanded_emotes
        
        # This is not part of any external api. So it might disappear suddenly.
        bpm_resources_text = self._requests.get("https://ponymotes.net/bpm/bpm-resources.js").text
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

    def _download_images(self):
        logger.debug("Downloading images using {} threads".format(self.workers))
        workpool = WorkerPool(size=self.workers)

        def create_download_jobs(key_func):
            for image_url, group in itertools.groupby(sorted(self.emotes, key=key_func), key_func):
                if not image_url:
                    continue

                file_path = get_file_path(image_url, rootdir=self.cache_dir)
                if not path.isfile(file_path):
                    workpool.put(DownloadJob(self._requests,
                                             image_url,
                                             retry=5,
                                             rate_limit_lock=self.rate_limit_lock,
                                             callback=self._callback_download_image,
                                             **{'image_path': file_path}))

        with self.mutex:
            create_download_jobs( lambda e: e['background-image'])
            create_download_jobs( lambda e: e.get('hover-background-image'))

        workpool.shutdown()
        workpool.join()

    def _callback_download_image(self, response, image_path=None):
        if not image_path:
            return

        data = response.content
        if not data:
            return

        image_dir = path.dirname(image_path)

        modified_date_tuple = parsedate(response.headers['Last-Modified'])
        modified_date_timestamp = calendar.timegm(modified_date_tuple)

        with self.mutex:
            if not path.exists(image_dir):
                os.makedirs(image_dir)

        with open(image_path, 'wb') as f:
            f.write(data)

        utime(image_path, (time.time(), modified_date_timestamp))

    def _explode_emote(self, emote, background_image_path):
        '''
        Create a {emote name}_exploded directory
        This directory contains all frames.
        The frames are cut out a spritemap if needed.
        
        Returns True if animation was not cut out a spritemap. (background image size == individual frames sizes)
        Returns False if animation was part of a spritemap and cutting was required. (background image size != individual frames sizes)
        
        Does not handle hover images.
        '''
        explode_dir = get_explode_directory(emote)
        if not os.path.exists(explode_dir):
            os.makedirs(explode_dir)
        shutil.copyfile(background_image_path, os.path.join(explode_dir, "background.png"))
        apngasm('--force', '-D', os.path.join(explode_dir, "background.png"), "-o", explode_dir, '-j', '-x')
        os.remove(os.path.join(explode_dir, "background.png"))

        frames_paths = glob(os.path.join(explode_dir, '*.png'))
        for frame_path in frames_paths:
            background_image = Image.open(frame_path)
            # Most animations contain changing transparency parts.
            # Therefore we must not autocrop individual frames.
            # Otherwise we will end up with differently sized frames.
            extracted_single_image = extract_single_image(emote, background_image, autocrop=False)
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

    def _reassemble_emote_png(self, emote):
        '''
        Reconstructs a emote from a exploded form to animated .png
        Does not handle hover images.
        '''
        explode_dir = get_explode_directory(emote)
        animation_file = os.path.join(explode_dir, 'animation.xml')
        with open(animation_file, 'r') as f:
            animation_xml = etree.parse(f).getroot()

        args = []
        args = args + ['--force', '-o', get_single_image_path(emote)]
        for frame_xml in animation_xml:
            frame_file = os.path.join(explode_dir,frame_xml.get('src'))
            delay = self._calculate_frame_delay(frame_xml.get('delay'))
            args.append(frame_file)
            args.append(delay)

        apngasm( *args )

    def _handle_background_for_emote(self, emote, background_image_path, background_image):
        
        if not os.path.exists(os.path.dirname(get_single_image_path(emote))):
            os.makedirs(os.path.dirname(get_single_image_path(emote)))

        if emote['img_animation']:
            same_as_spritemap = self._explode_emote(emote, background_image_path)
            if not same_as_spritemap and not os.path.exists(get_single_image_path(emote)):
                self._reassemble_emote_png(emote)
        else:
            # Extracted images should not be auto-cropped if they contain a hover.
            # The hover image may otherwise no longer align with the image below.
            extracted_single_image = extract_single_image(emote, background_image, not has_hover(emote))
            same_as_spritemap = cmp(background_image.size, extracted_single_image.size) == 0
            if not same_as_spritemap and not os.path.exists(get_single_image_path(emote)):
                with open(get_single_image_path(emote), 'wb') as f:
                    extracted_single_image.save(f)

        if same_as_spritemap:
            shutil.copyfile(background_image_path, get_single_image_path(emote, background_image.format))
            shutil.copystat(background_image_path, get_single_image_path(emote))

        if has_hover(emote) and emote['img_animation']:
            logger.error('Emote '+friendly_name(emote)+' is animated and contains a hover. This was never anticipated any output this script generates may be incorrect')

        if has_hover(emote) and 'hover-background-image' not in emote and not os.path.exists(get_single_hover_image_path(emote)):
            extracted_single_hover_image = extract_single_hover_image(emote, background_image)
            with open(get_single_hover_image_path(emote), 'wb') as f:
                extracted_single_hover_image.save(f)

    def _handle_hover_background_for_emote(self, emote, hover_background_image_path, hover_background_image):
        extracted_single_hover_image = extract_single_hover_image(emote, hover_background_image)

        if cmp(hover_background_image.size, extracted_single_hover_image.size) == 0:
            shutil.copyfile(hover_background_image_path, get_single_hover_image_path(emote, hover_background_image.format))
            shutil.copystat(hover_background_image_path, get_single_hover_image_path(emote))
        with open(get_single_hover_image_path(emote), 'wb') as f:
            extracted_single_hover_image.save(f)

    def _extract_images_from_spritemaps(self, emotes):
        logger.info('Beginning to extract images from spritemaps')

        def is_apng(image_data):
            return 'acTL' in image_data[0:image_data.find('IDAT')]

        key_func = lambda e: e['background-image']
        for image_url, emote_group in itertools.groupby(sorted(emotes, key=key_func), key_func):

            if not image_url:
                continue

            background_image_path = get_file_path(image_url, rootdir=self.cache_dir)
            background_image_path = path.realpath(background_image_path)
            modified_time = path.getmtime(background_image_path)
            with open(background_image_path, 'rb') as f:
                background_image_data = f.read()
            animated = False
            if is_apng(background_image_data):
                animated = True;
            background_image = Image.open(open(background_image_path, 'rb'))

            for emote in emote_group:
                emote['img_animation'] = animated
                 # TODO: Consider checking if the hover image is animated.
                self._handle_background_for_emote(emote, background_image_path, background_image)
                if (emote['Last-Modified'] < modified_time):
                    emote['Last-Modified'] = modified_time

        key_func = lambda e: e.get('hover-background-image')
        for image_url, emote_group in itertools.groupby(sorted(emotes, key=key_func), key_func):

            if not image_url:
                continue

            hover_background_image_path = get_file_path(image_url, rootdir=self.cache_dir)
            background_image_path = path.realpath(hover_background_image_path)
            modified_time = path.getmtime(hover_background_image_path)
            hover_background_image = Image.open(open(hover_background_image_path, 'rb'))
            for emote in emote_group:
                self._handle_hover_background_for_emote(emote, hover_background_image_path, hover_background_image)
                if (emote['Last-Modified'] < modified_time):
                    emote['Last-Modified'] = modified_time

    def _visually_dedupe_emotes(self):
        logger.info('Beginning to visually dedupe emotes')
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
                if emote['img_animation']:
                    continue

                image_path = get_single_image_path(emote)
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

    def _emote_post_preferance(self):
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

    def _remove_garbage(self):
        for emote in self.emotes:
            if 'tags' in emote:
                emote['tags'] = _remove_duplicates(emote['tags'])
                if '' in emote['tags']:
                    emote['tags'].remove('')

    def scrape(self):
        self._login()
        self._fetch_css()
        self._process_stylesheets()
        self._dedupe_emotes()
        self._add_bpm_tags()
        self._download_images()
        self._extract_images_from_spritemaps(self.emotes)
        self._read_old_emotes() # This will read the old emotes. Read function help for details.
        self._visually_dedupe_emotes()
        self._emote_post_preferance()
        self._remove_garbage()

    def export_emotes(self):
        return self.emotes
