/**
* User.js
*
* @description :: TODO: You might write a short summary of how this model works and what it represents here.
* @docs        :: http://sailsjs.org/#!documentation/models
*/

module.exports = {

  schema: true,

  attributes: {
        username: {
            type: 'STRING',
            unique: true,
        },
        email: {
            type: 'STRING',
            unique: true,
        },
        passports : {
            collection: 'Passport',
            via: 'user'
        },
  },
};

