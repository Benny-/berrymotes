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
ulimit -n 8192 # Increase the open file descriptor limit
python redditEmoteScraper.py
```

For help:

```bash
python redditEmoteScraper.py --help
```

### Running (debug)

For debugging purposes you might want to restrict yourself to scrapping a subset of subreddits. The recommended way to do this is to create a seperate `debug_session` directory and copy the minified .css files into it.

```bash
python -O ../reddit_emote_scraper/redditEmoteScraper\
            --debug\
            --no-berrytube-tags\
            --no-better-pony-emote-tags\
            --no-css-download\
            --session-cache "debug_session"\
            --output-dir "debug_output";
```

### Running (production)

For production you might want to do some additional things. Like download the better pony emote sourcecode and use their minified-css directory as a fallback. And make a session directory for every run so we can re-create any past run with updated source-code or for historical archive reasons.


Some setup is required for this:

```bash
sudo apt-get install "git-restore-mtime"

# Download the better pony emote repo
git clone https://github.com/Rothera/bpm.git bpm

mkdir "session_archive"
mkdir "reddit_cache"
mkdir "output"
```

A start script for production might look like this (it assumes you are running from a python [virtualenv](https://pypi.python.org/pypi/virtualenv) and are running out of the source tree):

```bash
#!/usr/bin/env bash

set -e

reddit_cache_dir="reddit_cache"
session_dir="session_archive/session_$(date --utc --iso-8601)"
output_dir="output"
bpm_git_root="bpm"

ulimit -n 8192

if [ -d ${session_dir} ]
then
	echo "${session_dir} dir already exists"
else
    echo "Session dir ${session_dir} is being created"
	mkdir "${session_dir}"
fi

update_bpm()
{
    set -e
	local path_to_bpm_git_repo=$1
	
	EXPECTED_ARGS=1
	E_BADARGS=65
	if [ $# -ne $EXPECTED_ARGS ]
	then
	  echo "Usage: `basename $0` path_to_bpm_git_repo"
	  exit $E_BADARGS
	fi

    (
	    cd "${path_to_bpm_git_repo}"
	    git pull
	    git restore-mtime # This is a git extension. Download it using "sudo apt-get install git-restore-mtime"
	)
}

update_bpm "${bpm_git_root}"

source ../pyenv/bin/activate;
python -O ../reddit_emote_scraper/redditEmoteScraper
            --debug \
            --download-css \
            --css-fallback "${bpm_git_root}/minified-css" \
            --reddit-cache "${reddit_cache_dir}" \
            --berrytube-tags \
            --better-pony-emote-tags \
            --session-cache "${session_dir}" \
            --output-dir "${output_dir}" 2>&1 | tee ""${output_dir}"/scraper.log";
```



