from setuptools import setup, find_packages

setup(
    name = 'reddit_emote_scraper',
    version = '0.2.1',
    author = 'Benny',
    author_email = 'Benny@GMX.it',
    url='https://mylittleserver.nl/',
    license='',
    keywords = "emoticons reddit".split(),
    description='Downloads emoticons from reddit',
    # long_description='',
    packages = find_packages(),
    scripts = [
        'redditEmoteScraper.py'
    ],
    install_requires = [
        'requests >= 2.4.3',
        'dateutils >= 0.6.6',
        'workerpool >= 0.9.2',
        'tinycss >= 0.3',
        'pillow >= 2.6.1',
        'pypuzzle >= 1.1',
        'sh >= 1.09',
        'lxml >= 3.4.0',
        'PyExecJS >= 1.0.4',
    ],
    classifiers = [
        "Programming Language :: Python :: 2",
        "Environment :: Console",
    ],
)
