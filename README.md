# Emote server

The emote server is designed to import the results from the reddit_emote_scraper and serve the content in a more usable format (json).

Please see the [reddit_emote_scraper](reddit_emote_scraper) sub-directory for scraping emotes from Reddit.

Please see the [server-filler](server-filler) sub-directory for the server hosting the emoticons. It takes the output of reddit_emote_scraper as input.

## Motivation

This project was designed to act as a complete replacement for using Reddit as a emote hosting site. Reddit is not designed as a emote hosting site and never will be.

* No gif images
* No svg images
* No automatic conversion to .webp
* Adding/editing emotes is a hassle and can be error-prone
* No standard for adding tags to emoticons
* No search or listing of all emotes
* It can be considered rude to use someone's CDN for something it was never intended for

But the scope of the Emote server to tackle all these problems was too big. So for now it merely scapes all emotes from reddit and presents them as a .json file.

