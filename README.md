# Emote server

The emote server is designed to import the results from the reddit_emote_scraper and acts as a complete replacement to using reddit as a emoticon hosting site.

Please see the [reddit_emote_scraper](reddit_emote_scraper) sub-directory for scraping emotes from Reddit.

Please see the [emote_server](emote_server) sub-directory for the server hosting the emoticons.

## Motivation

Reddit is not designed as a emote hosting site and never will be.

* No gif images
* No svg images
* Adding/editing emotes is a hassle and can be error-prone
* No standard for adding tags to emoticons
* No search or listing of all emotes

Also, it can be considered rude to use someone's CDN for something it was never intended for.

This server has most of the expected operations you may expect from a CRUD application. There are forms for submitting and editing and there is a JSON api for searching.

