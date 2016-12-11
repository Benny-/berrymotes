# Emote server

The emote server is designed to import the results from the reddit_emote_scraper and acts as a complete replacement to using reddit as a emoticon hosting site.

## Running the service

### Dependencies

[NodeJS and npm](https://nodejs.org/download/) are required.

### Running in dev mode

Download all requirements for the emote server (no root privileges required):

```bash
npm install
```

Run the server:

```bash
npm start
```

No need for a external database. A (inefficient) file database is used.

### Running in production

First run all the commands in "Running in dev mode".

The biggest difference between running in development or production is the database. The mysql and postgresql databases are supported. Only mysql is shown here.

First install the sails adapter for mysql:

```bash
npm install sails-mysql
```

Your `config/local.js` must contain something like this:

```javascript
module.exports = {
    
    models: {
        connection: "mysql",
        // Setting migrate to 'safe' makes sure adapter never alters the tables
        //migrate: 'safe',
    },
    
    connections: {
        mysql: {
            module    : 'sails-mysql',
            host      : 'localhost',
            port      : 3306,
            user      : 'username',
            password  : '*******',
            database  : 'emoticons',
        }
    }
    
};
```

In addition to the above steps I recommend reading [Sails Deployment](http://sailsjs.com/documentation/concepts/deployment)

### Running behind apache webserver

The following apache configuration can be used if you desire to run the service behind a reverse apache proxy.

Assuming the emoticon webservice is running on the same server on port 1337.

```apache
# The following apache modules must be enabled:
# proxy
# proxy_http
# proxy_wstunnel

ProxyRequests off
<Proxy *>
    Order deny,allow
    Allow from all
</Proxy>

# The error pages must not be proxified to the back-end.
# This might need to be changed depending where you store your error docs.
ProxyPass        /error_docs !

ProxyPass        /socket.io/1/websocket ws://localhost:1337/socket.io/1/websocket retry=0 timeout=5
ProxyPassReverse /socket.io/1/websocket ws://localhost:1337/socket.io/1/websocket

ProxyPass        / http://localhost:1337/ retry=0 timeout=5
ProxyPassReverse / http://localhost:1337/
```

## Importing emoticons from reddit

Importing emotes from reddit is entirely optional.

Before you can import them into the emote server, you must generate them. To do this run reddit_emote_scraper at least once. See [reddit_emote_scraper](../reddit_emote_scraper) for instructions.

Give yourself admin privileges (set role from '0' to '1' in the `user` table) using your favorite database interface. And browse on the emote server to `/emote/bulk_upload`.


