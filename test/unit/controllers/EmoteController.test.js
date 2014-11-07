var request = require('supertest');

describe('EmoteController', function() {

    it('/emote/submit should by default give a 403 when not logged in', function (done) {
        request(sails.hooks.http.server)
        .get('/emote/submit')
        .expect(403)
    });

});

