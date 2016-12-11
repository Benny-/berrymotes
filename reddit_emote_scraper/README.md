# Reddit emote scraper

Some subreddit have emotes. This script harvest emotes from multiple subreddits and outputs them in a directory as images and a json file.

## External dependencies

External dependencies for python Pillow:

http://pillow.readthedocs.org/en/latest/installation.html#external-libraries

External dependencies for pypuzzle:
```bash
sudo apt-get install libgd2-xpm-dev libpuzzle-dev
```

External dependencies for python lxml:

http://lxml.de/installation.html#requirements

External dependencies for PyExecJS (install at least one execution environment):

https://github.com/doloopwhile/PyExecJS#supported-runtimes

The following program must exist in your path for apng handling:

https://github.com/apngasm/apngasm (Use a recent version like v3.1.3 or later)

## Python dependencies

```bash
pip install -r requirements.pip
```

## Running

```bash
python redditEmoteScraper.py
```

