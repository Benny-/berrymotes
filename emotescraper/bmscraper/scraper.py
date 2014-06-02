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
from dateutil.tz import tzutc
import requests
from workerpool import WorkerPool
import threading
import tinycss
import re
from collections import defaultdict
import itertools
import os
from os import path
from .downloadjob import DownloadJob
from .filenameutils import get_file_path
from .Emote import get_single_image_path, get_single_hover_image_path, extract_single_image, has_hover, extract_single_hover_image, friendly_name
from multiprocessing import cpu_count
from dateutil import parser
from PIL import Image
import pypuzzle
import shutil

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
        self.workers = cpu_count()
        self.rate_limit_lock = None

        self.mutex = threading.RLock()

        self._requests = requests.Session()
        self._requests.headers = {'user-agent', 'User-Agent: Ponymote harvester v2.0 by /u/marminatoror'}

    def _merge_emotes(self, keeper, goner):

        try:
            os.remove(goner.get_single_image_path())
        except:
            pass

        try:
            os.remove(goner.get_single_hover_image_path())
        except:
            pass

        keeper['names'] = keeper['names'] + goner['names']
        keeper['names'] = _remove_duplicates(keeper['names'])
        keeper['tags'] = keeper.get('tags', []) + goner.get('tags', [])
        goner['names'] = []

    def _login(self):
        if self.user and self.password:
            body = {'user': self.user, 'passwd': self.password, "rem": False}
            self.rate_limit_lock and self.rate_limit_lock.acquire()
            self._requests.post('http://www.reddit.com/api/login', body)

    def _fetch_css(self):

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

        css_cache_file_path = get_file_path(response.url, rootdir=self.cache_dir )
        with self.mutex:
            if not os.path.exists(os.path.dirname(css_cache_file_path)):
                os.makedirs(os.path.dirname(css_cache_file_path))
        css_subreddit_path = path.join('css', subreddit) + '.css'

        with open( css_cache_file_path, 'w' ) as f:
            f.write( text )

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
                self.emotes.append(emote)
            else:
                logger.warn('Discarding emotes {}'.format(emote['names'][0]))

    def _process_stylesheets(self):

        for subreddit in self.subreddits:
            content = None
            css_subreddit_path = path.join('css', subreddit) + '.css'

            try:
                with open( css_subreddit_path, 'r' ) as f:
                    content = f.read().decode('utf-8')
                    self._process_stylesheet(content, subreddit)
            except Exception as ex:
                logger.warn('Not parsing stylesheet for ' + subreddit + ": " + str(ex))

    def _dedupe_emotes(self):

        for subreddit in self.subreddits:
            subreddit_emotes = [x for x in self.emotes if x['sr'] == subreddit]
            other_subreddits_emotes = [x for x in self.emotes if x['sr'] != subreddit]
            for subreddit_emote in subreddit_emotes:
                for emote in other_subreddits_emotes:

                    # Remove duplicate names. The subreddit scraping order will determine which emote keeps there name.
                    for name in subreddit_emote['names']:
                        if name in emote['names']:
                            emote['names'].remove(name)

        for subreddit in self.subreddits:
            subreddit_emotes = [x for x in self.emotes if x['sr'] == subreddit]
            other_subreddits_emotes = [x for x in self.emotes if x['sr'] != subreddit]
            for subreddit_emote in subreddit_emotes:
                for emote in other_subreddits_emotes:

                    # merge (move all names to one emote) both emotes if they use the same image source
                    # This method is not perfect. It ignores CSS attributes.
                    # A emote using the same image source (While still being visually different using CSS)
                    # will still be incorrectly merged.
                    #
                    # This method does not do visual image comparison. Visually equal images will not be merged.
                    if (emote['background-image'] == subreddit_emote['background-image'] and
                        emote.get('background-position') == subreddit_emote.get('background-position') and
                        emote.get('height') == subreddit_emote.get('height') and
                        emote.get('width') == subreddit_emote.get('width') ):

                        self._merge_emotes(subreddit_emote, emote)
                        self.emotes.remove(emote)

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

        with self.mutex:
            if not path.exists(image_dir):
                os.makedirs(image_dir)

        with open(image_path, 'wb') as f:
            f.write(data)

    def _handle_background_for_emote(self, emote, background_image_path, background_image, background_image_width, background_image_height):
        extracted_single_image = extract_single_image(emote, background_image)
        extracted_single_image_width, extracted_single_image_height = extracted_single_image.size

        if not os.path.exists(os.path.dirname(get_single_image_path(emote))):
            os.makedirs(os.path.dirname(get_single_image_path(emote)))

        if background_image_width == extracted_single_image_width and background_image_height == extracted_single_image_height:
            shutil.copyfile(background_image_path, get_single_image_path(emote, background_image.format))
            shutil.copystat(background_image_path, get_single_image_path(emote))
        elif not os.path.exists(get_single_image_path(emote)):
            with open(get_single_image_path(emote), 'wb') as f:
                extracted_single_image.save(f)
            if emote['img_animation']:
                logger.error('Emote '+friendly_name(emote)+' is animated but is part of a spritemap. Single image output will be incorrect.')

        if has_hover(emote) and emote['img_animation']:
            logger.error('Emote '+friendly_name(emote)+' is animated and contains a hover. This was never anticipated any output this script generates may be incorrect')

        if has_hover(emote) and 'hover-background-image' not in emote:
            if not os.path.exists(os.path.dirname(get_single_hover_image_path(emote))):
                os.makedirs(os.path.dirname(get_single_hover_image_path(emote)))
            extracted_single_hover_image = extract_single_hover_image(emote, background_image)
            with open(get_single_hover_image_path(emote), 'wb') as f:
                extracted_single_hover_image.save(f)

    def _handle_hover_background_for_emote(self, emote, hover_background_image_path, hover_background_image, hover_background_image_width, hover_background_image_height):
        extracted_single_hover_image = extract_single_hover_image(emote,hover_background_image)
        extracted_single_hover_image_width, extracted_single_hover_image_height = extracted_single_hover_image.size

        if not os.path.exists(os.path.dirname(get_single_hover_image_path(emote))):
            os.makedirs(os.path.dirname(get_single_hover_image_path(emote)))

        if hover_background_image_width == extracted_single_hover_image_width and hover_background_image_height == extracted_single_hover_image_height:
            shutil.copyfile(hover_background_image_path, get_single_hover_image_path(emote, hover_background_image.format))
            shutil.copystat(hover_background_image_path, get_single_hover_image_path(emote))
        with open(get_single_hover_image_path(emote), 'wb') as f:
            extracted_single_hover_image.save(f)

    def _extract_images_from_spritemaps(self):

        def is_apng(image_data):
            return 'acTL' in image_data[0:image_data.find('IDAT')]

        key_func = lambda e: e['background-image']
        for image_url, emote_group in itertools.groupby(sorted(self.emotes, key=key_func), key_func):

            if not image_url:
                continue

            background_image_path = get_file_path(image_url, rootdir=self.cache_dir)
            with open(background_image_path, 'rb') as f:
                background_image_data = f.read()
            animated = False
            if is_apng(background_image_data):
                animated = True;
            background_image = Image.open(open(background_image_path, 'rb'))
            background_image_width, background_image_height = background_image.size

            for emote in emote_group:
                emote['img_animation'] = animated
                 # TODO: Consider checking if the hover image is animated.
                self._handle_background_for_emote(emote, background_image_path, background_image, background_image_width, background_image_height)

        key_func = lambda e: e.get('hover-background-image')
        for image_url, emote_group in itertools.groupby(sorted(self.emotes, key=key_func), key_func):

            if not image_url:
                continue

            hover_background_image_path = get_file_path(image_url, rootdir=self.cache_dir)
            hover_background_image = Image.open(open(hover_background_image_path, 'rb'))
            hover_background_image_width, hover_background_image_height = hover_background_image.size

            for emote in emote_group:
                self._handle_hover_background_for_emote(emote, hover_background_image_path, hover_background_image, hover_background_image_width, hover_background_image_height)

    def _visually_dedupe_emotes(self):
        processed_emotes = []
        duplicates = []
        puzzle = pypuzzle.Puzzle()

        for subreddit in self.subreddits:
            subreddit_emotes = [x for x in self.emotes if x['sr'] == subreddit]

            logger.info('Beginning to visually dedupe emotes in subreddit '+subreddit)
            for emote in subreddit_emotes:

                if emote in duplicates:
                    continue

                # Ignore apng urls as they sometime start with a black frame.
                # We only check the first frame and thus they are visually the same as any other black picture.
                if emote['img_animation']:
                    continue

                image_path = get_single_image_path(emote)
                vector = puzzle.get_cvec_from_file(image_path)

                for other_emote, other_compressed_vector in processed_emotes:
                    other_vector = puzzle.uncompress_cvec(other_compressed_vector)

                    if other_emote in duplicates:
                        continue

                    distance = puzzle.get_distance_from_cvec(vector, other_vector)
                    if( distance < 0.05 ):
                        self._merge_emotes(other_emote, emote)
                        duplicates.append(emote)
                processed_emotes.append((emote, puzzle.compress_cvec(vector)))

        self.emotes = filter(lambda emote: emote not in duplicates, self.emotes)

    def _emote_post_preferance(self):
        '''A emote's first name will be used to post. Some names are preferred over other names. We re-order the names here.'''

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
        self._download_images()
        self._extract_images_from_spritemaps()
        self._visually_dedupe_emotes()
        self._emote_post_preferance()
        self._remove_garbage()

    def export_emotes(self):
        return self.emotes
