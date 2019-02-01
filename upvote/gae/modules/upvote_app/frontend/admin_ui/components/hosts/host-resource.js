// Copyright 2017 Google Inc. All Rights Reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS-IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

goog.provide('upvote.admin.hosts.HostQueryResource');
goog.provide('upvote.admin.hosts.HostResource');

goog.require('upvote.admin.app.constants');
goog.require('upvote.admin.lib.resources.buildQueryResource');
goog.require('upvote.admin.lib.resources.buildResource');

goog.scope(() => {
const buildResource = upvote.admin.lib.resources.buildResource;
const buildQueryResource = upvote.admin.lib.resources.buildQueryResource;


/** @const {string} */
const API_PREFIX = upvote.admin.app.constants.WEB_PREFIX + 'hosts/';


/** @export {function(!angular.$resource):!angular.Resource} */
upvote.admin.hosts.HostResource = buildResource(API_PREFIX + ':id', {
  'update': {
    'method': 'POST',
    'params': {
      'id': '@id',
      'clientMode': '@clientMode',
      'clientModeLock': '@clientModeLock',
      'shouldUploadLogs': '@shouldUploadLogs'
    }
  }
});


/** @export {function(!angular.$resource):!angular.Resource} */
upvote.admin.hosts.HostQueryResource =
    buildQueryResource(API_PREFIX + 'query/santa/:platform');
});  // goog.scope
