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
from downloadjob import DownloadJob
from filenameutils import FileNameUtils
from multiprocessing import cpu_count
from dateutil import parser
import re
import pypuzzle

import logging

logger = logging.getLogger(__name__)

re_numbers = re.compile(r"\d+")
re_slash = re.compile(r"/")

def _remove_duplicates(seq):
    '''https://stackoverflow.com/questions/480214/how-do-you-remove-duplicates-from-a-list-in-python-whilst-preserving-order'''
    seen = set()
    seen_add = seen.add
    return [ x for x in seq if x not in seen and not seen_add(x)]

class BMScraper(FileNameUtils):
    def __init__(self, processor_factory):
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
        self.processor_factory = processor_factory
        self.rate_limit_lock = None

        self.mutex = threading.RLock()

        self._requests = requests.Session()
        self._requests.headers = {'user-agent', 'User-Agent: Ponymote harvester v2.0 by /u/marminatoror'}
    
    # This function returns a path to a single image.
    # This image does not contain any animations.
    # Please note: A emote can have a hover image.
    # This function does not take the hover image into account.
    def get_single_image(self, emote):
        return os.path.join( *(['single_emotes']+((max(emote['names'], key=len)+".png").split('/'))))
    
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
    
    def merge_emotes(self, keeper, goner):
        filename = self.get_single_image(goner)
        
        try:
            os.remove(filename)
        except:
            pass
        
        keeper['names'] = keeper['names'] + goner['names']
        keeper['names'] = _remove_duplicates(keeper['names'])
        goner['names'] = []
    
    def _dedupe_emotes(self):
    
        for subreddit in self.subreddits:
            subreddit_emotes = [x for x in self.emotes if x['sr'] == subreddit]
            other_subreddits_emotes = [x for x in self.emotes if x['sr'] != subreddit]
            for subreddit_emote in subreddit_emotes:
                for emote in other_subreddits_emotes:
                    
                    # Remove duplicate names. The subreddit scraping order will determine which emote keeps there name.
                    for name in subreddit_emote['names']:
                        if name in emote['names']:
                            #logger.debug("Deduping: {}".format(name))
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
                        
                        self.merge_emotes(subreddit_emote, emote)
                        self.emotes.remove(emote)

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
                if 'apng_url' in emote:
                    continue
                
                # filename points to a emote's image. It is never a sprite map.
                filename = self.get_single_image(emote)
                vector = puzzle.get_cvec_from_file( filename )
                
                for other_emote, other_vector in processed_emotes:
                    
                    if other_emote in duplicates:
                        continue
                    
                    distance = puzzle.get_distance_from_cvec(vector, other_vector)
                    if( distance < 0.05 ):
                        self.merge_emotes(other_emote, emote)
                        duplicates.append(emote)
                processed_emotes.append( (emote, vector) )
            
        self.emotes = filter(lambda emote: emote not in duplicates, self.emotes)
        
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

    def _download_images(self):
        logger.debug("Downloading images using {} threads".format(self.workers))
        workpool = WorkerPool(size=self.workers)

        # cache emotes
        key_func = lambda e: e['background-image']
        with self.mutex:
            for image_url, group in itertools.groupby(sorted(self.emotes, key=key_func), key_func):
                if not image_url:
                    continue

                file_path = self.get_file_path(image_url, rootdir=self.cache_dir)
                if not path.isfile(file_path):
                    workpool.put(DownloadJob(self._requests,
                                             image_url,
                                             retry=5,
                                             rate_limit_lock=self.rate_limit_lock,
                                             callback=self._callback_download_image,
                                             **{'image_path': file_path}))

        workpool.shutdown()
        workpool.join()

    def _process_emotes(self):
        logger.debug("Processing emotes using {} threads".format(self.workers))
        workpool = WorkerPool(self.workers)

        key_func = lambda e: e['background-image']
        with self.mutex:
            for image_url, group in itertools.groupby(sorted(self.emotes, key=key_func), key_func):
                if not image_url:
                    continue

                workpool.put(self.processor_factory.new_processor(scraper=self, image_url=image_url, group=list(group)))

        workpool.shutdown()
        workpool.join()

    def scrape(self):
        # Login
        if self.user and self.password:
            body = {'user': self.user, 'passwd': self.password, "rem": False}
            self.rate_limit_lock and self.rate_limit_lock.acquire()
            response = self._requests.post('http://www.reddit.com/api/login', body)
            #cookie = response.headers['set-cookie']
            #self._headers['cookie'] = cookie[:cookie.index(';')]
        
        self._fetch_css()
        
        self._process_stylesheets()
        
        self._dedupe_emotes()
        
        self._download_images()
        
        self._process_emotes()
        
        self._visually_dedupe_emotes()
        
        self._emote_post_preferance()
        
        logger.info('All Done')

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
    
    def _callback_fetch_stylesheet(self, response, subreddit=None):
        if not response:
            logger.error("Failed to fetch css for {}".format(subreddit))
            return

        if response.status_code != 200:
            logger.error("Failed to fetch css for {} (Status {})".format(subreddit, response.status_code))
            return
        
        filename = response.url.split('/').pop()
        text = response.text.encode('utf-8')
        
        css_cache_file_path = self.get_file_path(response.url, rootdir=self.cache_dir )
        with self.mutex:
            if not os.path.exists(os.path.dirname(css_cache_file_path)):
                os.makedirs(os.path.dirname(css_cache_file_path))
        css_subreddit_path = path.join('css', subreddit) + '.css'
        
        with open( css_cache_file_path, 'w' ) as f:
            f.write( text )
        
        os.symlink(os.path.relpath(css_cache_file_path, 'css/'), css_subreddit_path );

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

