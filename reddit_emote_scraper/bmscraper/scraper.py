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
from .Emote import get_single_image_path, get_single_hover_image_path, extract_single_image, has_hover, extract_single_hover_image, friendly_name, canonical_name, get_explode_directory
from dateutil import parser
from PIL import Image
import pypuzzle
import shutil
from sh import apngasm, cwebp, webpmux, apng2webp
from glob import glob
from lxml import etree
import execjs
import tempfile

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

    def _merge_emotes(self, keeper, goner):
        logger.debug('Merging '+canonical_name(goner)+' into '+canonical_name(keeper))

        try:
            os.remove(get_single_image_path(goner))
        except:
            pass

        try:
            os.remove(get_single_hover_image_path(goner))
        except:
            pass

        try:
            shutil.rmtree(get_explode_directory(goner))
        except:
            pass

        # webp's do not have to be removed here.
        # webp files do not exist during any of the merge steps.

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
        logger.info('Beginning to process stylesheets')

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
        logger.info('Beginning to de-duplicate emotes based on meta-data')

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

        with self.mutex:
            if not path.exists(image_dir):
                os.makedirs(image_dir)

        with open(image_path, 'wb') as f:
            f.write(data)

    def _explode_emote(self, emote, background_image_path):
        '''
        Create a {emote name}_exploded directory
        This directory contains all frames.
        The frames are cut out a spritemap if the spritemap was animated.
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
            extracted_single_image = extract_single_image(emote, background_image)
            if cmp(background_image.size, extracted_single_image.size) != 0:
                extracted_single_image.save(frame_path)

    def _calculate_frame_delay(self, delay_text):
        '''Calucate delay in ms'''
        delay = int(round(float(delay_text[0:delay_text.index('/')]) / float(delay_text[delay_text.index('/') + 1:]) * 1000))
        if delay == 0:
            delay = 1;
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
        extracted_single_image = extract_single_image(emote, background_image)

        if not os.path.exists(os.path.dirname(get_single_image_path(emote))):
            os.makedirs(os.path.dirname(get_single_image_path(emote)))

        if emote['img_animation'] and not os.path.exists(get_explode_directory(emote)):
            self._explode_emote(emote, background_image_path)

        if cmp(background_image.size, extracted_single_image.size) == 0:
            shutil.copyfile(background_image_path, get_single_image_path(emote, background_image.format))
            shutil.copystat(background_image_path, get_single_image_path(emote))
        elif not os.path.exists(get_single_image_path(emote)):
            if emote['img_animation']:
                self._reassemble_emote_png(emote)
            else:
                with open(get_single_image_path(emote), 'wb') as f:
                    extracted_single_image.save(f)

        if has_hover(emote) and emote['img_animation']:
            logger.error('Emote '+friendly_name(emote)+' is animated and contains a hover. This was never anticipated any output this script generates may be incorrect')

        if has_hover(emote) and 'hover-background-image' not in emote and not os.path.exists(get_single_hover_image_path(emote)):
            extracted_single_hover_image = extract_single_hover_image(emote, background_image)
            with open(get_single_hover_image_path(emote), 'wb') as f:
                extracted_single_hover_image.save(f)

    def _handle_hover_background_for_emote(self, emote, hover_background_image_path, hover_background_image):
        extracted_single_hover_image = extract_single_hover_image(emote,hover_background_image)

        if cmp(hover_background_image.size, extracted_single_hover_image.size) == 0:
            shutil.copyfile(hover_background_image_path, get_single_hover_image_path(emote, hover_background_image.format))
            shutil.copystat(hover_background_image_path, get_single_hover_image_path(emote))
        with open(get_single_hover_image_path(emote), 'wb') as f:
            extracted_single_hover_image.save(f)

    def _extract_images_from_spritemaps(self):
        logger.info('Beginning to extract images from spritemaps')

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

            for emote in emote_group:
                emote['img_animation'] = animated
                 # TODO: Consider checking if the hover image is animated.
                self._handle_background_for_emote(emote, background_image_path, background_image)

        key_func = lambda e: e.get('hover-background-image')
        for image_url, emote_group in itertools.groupby(sorted(self.emotes, key=key_func), key_func):

            if not image_url:
                continue

            hover_background_image_path = get_file_path(image_url, rootdir=self.cache_dir)
            hover_background_image = Image.open(open(hover_background_image_path, 'rb'))
            for emote in emote_group:
                self._handle_hover_background_for_emote(emote, hover_background_image_path, hover_background_image)

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

    def _reassemble_emote__webp(self, emote):
        '''Convert a animated emote image to a animate webp image. Does not handle hover emotes.'''
        # Converting to webp is a 3 step process for animated emotes
        # 1. Explode animated .png <- Already done during self._extract_images_from_spritemaps()
        # 2. Convert all frames to .webp
        # 3. Reassemble frames into single webp
        explode_dir = get_explode_directory(emote)
        frame_files = glob(os.path.join(explode_dir, '*.png'))
        animation_file = os.path.join(explode_dir, 'animation.xml')
        with open(animation_file, 'r') as f:
            animation_xml = etree.parse(f).getroot()

        for frame_file in frame_files:
            cwebp('-lossless', '-q', '100', frame_file, '-o', os.path.splitext(frame_file)[0] + '.webp')

        args = []
        args = args + ['-o', os.path.splitext(get_single_image_path(emote))[0] + '.webp']
        for frame_xml in animation_xml:
            frame_file = os.path.join(explode_dir, os.path.splitext(frame_xml.get('src'))[0] + '.webp')
            delay = self._calculate_frame_delay(frame_xml.get('delay'))
            args.append('-frame')
            args.append(frame_file)
            args.append('+' + str(delay) + '+0+0+1-b')
        webpmux(*args)

    def _maby_convert_emote_webp(self, emote):
        '''
        This function may convert a non-animated emote image to a .webp if it yields any benefits (in size).
        See _reassemble_emote__webp() for converting a animated emote image.
        Does not handle hover emotes.
        '''
        webp_file_path = os.path.splitext(get_single_image_path(emote))[0] + '.webp'
        
        cwebp('-lossless', '-q', '100', get_single_image_path(emote),
            '-o', webp_file_path)

        size_non_webp = os.path.getsize(get_single_image_path(emote))
        size_webp = os.path.getsize(webp_file_path)
        
        if size_webp > size_non_webp:
            os.remove(webp_file_path)
            logger.debug(get_single_image_path(emote)+' could not create a smaller webp file')

    def _convert_emotes_to_webp(self):

        fd, temp_webp_path = tempfile.mkstemp(suffix=".webp")
        
        try:
            for emote in self.emotes:
                webp_file_path = os.path.splitext(get_single_image_path(emote))[0] + '.webp'
                webp_hover_file_path = os.path.splitext(get_single_hover_image_path(emote))[0] + '.webp'
                
                if not os.path.exists(webp_file_path):
                    if emote['img_animation']:
                        self._reassemble_emote__webp(emote)
                        apng2webp(get_single_image_path(emote), temp_webp_path)
                        
                        size_apng = os.path.getsize(get_single_image_path(emote))
                        size_apng2webp_webp = os.path.getsize(temp_webp_path)
                        size_reassemble_webp = os.path.getsize(webp_file_path)
                        size_difference_percentage = size_apng2webp_webp/(size_reassemble_webp/100.0)
                        
                        logger.debug(canonical_name(emote) + ' size_reassemble_webp : '+str(size_reassemble_webp))
                        logger.debug(canonical_name(emote) + ' size_apng2webp_webp  : '+str(size_apng2webp_webp)+' apng2webp/reassemble_webp size difference: '+str(size_difference_percentage))
                        
                        if size_apng2webp_webp > size_reassemble_webp:
                            logger.warn('size_apng2webp_webp created bigger size for emote '+canonical_name(emote))
                            logger.debug(canonical_name(emote) + ' size_apng            : '+str(size_apng) + ' apng/reassemble_webp size difference: '+str(size_reassemble_webp/(size_apng/100.0)))
                        else:
                            logger.debug(canonical_name(emote) + ' size_apng            : '+str(size_apng) + ' apng/apng2webp_webp size difference: '+str(size_apng2webp_webp/(size_apng/100.0)))
                            shutil.copy(temp_webp_path, webp_file_path)
                    else:
                        self._maby_convert_emote_webp(emote)
                
                # TODO: Handle edge case for animated hover images.
                if has_hover(emote) and not os.path.exists(webp_hover_file_path):
                    cwebp('-lossless', '-q', '100', get_single_hover_image_path(emote),
                        '-o', webp_hover_file_path)
        finally:
            os.remove(temp_webp_path)

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
        self._extract_images_from_spritemaps()
        self._visually_dedupe_emotes()
        self._convert_emotes_to_webp()
        self._emote_post_preferance()
        self._remove_garbage()

    def export_emotes(self):
        return self.emotes
