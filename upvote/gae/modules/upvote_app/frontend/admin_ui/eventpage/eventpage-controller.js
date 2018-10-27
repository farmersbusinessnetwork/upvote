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

goog.provide('upvote.admin.eventpage.EventController');

goog.require('goog.dom.safe');
goog.require('upvote.admin.lib.controllers.ModelController');
goog.require('upvote.shared.Page');

goog.scope(() => {
const ModelController = upvote.admin.lib.controllers.ModelController;


upvote.admin.eventpage.Settings = class {
  constructor() {
    /** @export {string} */
    this.santaDirectoryWhitelistRegex = "";
    /** @export {string} */
    this.santaDirectoryBlacklistRegex = "";
  }
};


/** Event model controller. */
upvote.admin.eventpage.EventController = class extends ModelController {
  /**
   * @param {!angular.Resource} eventResource
   * @param {!angular.Resource} eventQueryResource
   * @param {!upvote.admin.settings.SettingsService} settingsService
   * @param {!angular.$routeParams} $routeParams
   * @param {!angular.Scope} $scope
   * @param {!angular.$location} $location
   * @param {!upvote.shared.Page} page Details about the active webpage
   * @ngInject
   */
  constructor(
      eventResource, eventQueryResource, settingsService, $routeParams, $scope, $location,
      page) {
    super(eventResource, eventQueryResource, $routeParams, $scope, $location);

    /** @private {!upvote.admin.settings.SettingsService} */
    this.settingsService_ = settingsService;

    /** @export {string} */
    this.hostId = this.location.search()['hostId'];
    /** @export {string} */
    this.pageTitle = this.hostId ? 'Events for Host ' + this.hostId : 'Events';

    // Add the hostId param to the request before loadData is called by init.
    this.requestData['hostId'] = this.hostId;
    this.requestData['withContext'] = true;

    /** @export {!upvote.admin.eventpage.Settings} */
    this.settings = new upvote.admin.eventpage.Settings();

    page.title = this.pageTitle;

    // Get the settings we need (FBN TODO: use settings controller directly?)
    for (let settingName of Object.keys(this.settings)) {
      this.settingsService_.get(settingName).then((result) => {
        this.settings[settingName] = result['data'];
      });
    }

    // Initialize the controller.
    this.init();
  }

  /**
   * Navigate to the Blockable page associated with the selected Event.
   * @export
   */
  goToBlockable() {
    // FBN
    //this.location.path('/admin/blockables/' + this.card.blockableId).search({});
    goog.dom.safe.openInWindow('/admin/blockables/' + this.card.blockableId);
  }

  /**
   * Navigate to the Host page associated with the selected Event.
   * @export
   */
  goToHost() {
    this.location.path('/admin/hosts/' + this.card.hostId).search({});
  }
};
});  // goog.scope
