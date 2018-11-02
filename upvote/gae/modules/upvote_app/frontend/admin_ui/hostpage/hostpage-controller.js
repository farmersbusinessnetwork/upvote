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

goog.provide('upvote.admin.hostpage.HostController');

goog.require('upvote.admin.lib.controllers.ModelController');
goog.require('upvote.errornotifier.ErrorService');
goog.require('upvote.hosts.HostService');
goog.require('upvote.hosts.HostUtilsService');
goog.require('upvote.shared.Page');

goog.scope(() => {
const ModelController = upvote.admin.lib.controllers.ModelController;


/** Host model controller. */
upvote.admin.hostpage.HostController = class extends ModelController {
  /**
   * @param {!angular.Resource} hostResource
   * @param {!angular.Resource} hostQueryResource
   * @param {!angular.Resource} userResource
   * @param {!upvote.hosts.HostService} hostService
   * @param {!upvote.hosts.HostUtilsService} hostUtilsService
   * @param {!upvote.errornotifier.ErrorService} errorService
   * @param {!angular.$routeParams} $routeParams
   * @param {!md.$dialog} $mdDialog
   * @param {!angular.Scope} $scope
   * @param {!angular.Scope} $rootScope
   * @param {!angular.$location} $location
   * @param {!upvote.shared.Page} page Details about the active webpage
   * @ngInject
   */
  constructor(
      hostResource, hostQueryResource, userResource, hostService,
      hostUtilsService, errorService, $routeParams, $mdDialog, $scope, $rootScope,
      $location, page) {
    super(hostResource, hostQueryResource, $routeParams, $scope, $location);

    /** @export {!Object<string, !upvote.admin.lib.controllers.Field>} */
    this.fields = HostController.BASE_FIELDS_;
    /** @private {!upvote.errornotifier.ErrorService} errorService */
    this.errorService_ = errorService;
    /** @private {!upvote.hosts.HostService} */
    this.hostService_ = hostService;
    /** @private {!angular.Resource} */
    this.userResource_ = userResource;
    /** @export {!upvote.hosts.HostUtilsService} */
    this.hostUtils = hostUtilsService;
    /** @export {!angular.Scope} */
    this.rootScope = $rootScope;
    /** @export {?upvote.shared.models.User} */
    this.user = null;
    /** @private {!md.$dialog} */
    this.mdDialog_ = $mdDialog;

    // A list of hostnames that have visible host details
    /** @private {!Set<string>} */
    this.visibleHostDetails_ = new Set();

    page.title = 'Hosts';

    // Initialize the controller
    this.init();

    this.userResource_.getSelf()['$promise']
        .then((user) => {
          this.user = user;
        })
        .catch((response) => {
          this.errorService_.createDialogFromError(response);
        });
  }

  /** @override */
  updateToAll() {
    this.fields = HostController.BASE_FIELDS_;
  }

  /** @override */
  updateToSanta() {
    this.fields = Object.assign({}, HostController.BASE_FIELDS_, {
      'primary_user': {'displayName': 'Primary User', 'value': 'primary_user'},
      'serial_num': {'displayName': 'Serial Number', 'value': 'serial_num'},
      'santa_version':
          {'displayName': 'Santa Version', 'value': 'santa_version'}
    });
  }

  /**
   * Navigate to the Event page for the selected Host.
   * @param {!string} hostId
   * @export
   */
  goToHostEvents(hostId) {
    this.location.path('/admin/events').search({'hostId': hostId});
  }

  /**
   * Navigates to a host's "blockables" page.
   * @param {!string} hostId
   * @export
   */
  goToBlockablesPage(hostId) {
    let requestPath = '/hosts/' + hostId + '/blockables';
    this.location_.path(requestPath);
  }

  /**
   * Opens Prompt to change host's whitelist REGEX
   * @param {!Object} host
   * @param {!object} event
   * @export
   */
  changeWhitelistREGEX(host, event) {
    let previousWhitelistREGEX = host['directoryWhitelistRegex'];
    let resource = this.resource;

    // .required(true)  doesn't seem to be supported
    let confirm = this.mdDialog_.prompt()
        .title('Whitelist REGEX')
        .textContent('Enter updated whitelist REGEX')
        .initialValue(previousWhitelistREGEX)
        .targetEvent(event)
        .ok('Update')
        .cancel('Cancel');

    this.mdDialog_.show(confirm).then(function(result) {
      host['directoryWhitelistRegex'] = result;
      resource.update(host)['$promise'].catch(() => {
        host['directoryWhitelistRegex'] = previousWhitelistREGEX;
      });
    }, function() { /* nop */});
  }

  /**
   * Opens Prompt to change host's blacklist REGEX
   * @param {!Object} host
   * @param {!object} event
   * @export
   */
  changeBlacklistREGEX(host, event) {
    let previousBlacklistREGEX = host['directoryBlacklistRegex'];
    let resource = this.resource;

    // .required(true)  doesn't seem to be supported
    let confirm = this.mdDialog_.prompt()
        .title('Blacklist REGEX')
        .textContent('Enter updated blacklist REGEX')
        .initialValue(previousBlacklistREGEX)
        .targetEvent(event)
        .ok('Update')
        .cancel('Cancel');

    this.mdDialog_.show(confirm).then(function(result) {
      host['directoryBlacklistRegex'] = result;
      resource.update(host)['$promise'].catch(() => {
        host['directoryBlacklistRegex'] = previousBlacklistREGEX;
      });
    }, function() { /* nop */});
  }

  /**
   * Requests logs for a santa host
   * @param {!Object} host
   * @export
   */
  requestLogs(host) {
    host['shouldUploadLogs'] = true;
    this.resource.update(host)['$promise'].catch(() => {
      host['shouldUploadLogs'] = false;
    });
  }

  canEnableMonitorMode(host) {
    return (
        this.hostUtils.isSantaHost(host) && this.hostUtils.isInLockdown(host) &&
        this.userCanEditHosts());
  }

  enableMonitorMode(host) {
    let previousMode = host['clientMode'];
    host['clientMode'] = 'MONITOR';
    this.resource['update'](host)['$promise'].catch(() => {
      host['clientMode'] = previousMode;
    });
  }

  canEnableLockdownMode(host) {
    return (
        this.hostUtils.isSantaHost(host) &&
        !this.hostUtils.isInLockdown(host) && this.userCanEditHosts());
  }

  enableLockdownMode(host) {
    let previousMode = host['clientMode'];
    host['clientMode'] = 'LOCKDOWN';
    this.resource['update'](host)['$promise'].catch(() => {
      host['clientMode'] = previousMode;
    });
  }

  canToggleClientModeLock(host) {
    return this.hostUtils.isSantaHost(host) && this.userCanEditHosts();
  }

  toggleClientModeLock(host) {
    let previousState = host['clientModeLock'];
    host['clientModeLock'] = !previousState;
    this.resource['update'](host)['$promise'].catch(() => {
      host['clientModeLock'] = previousState;
    });
  }

  toggleTransitiveWhitelisting(host) {
    let previousState = host['transitiveWhitelistingEnabled'];
    host['transitiveWhitelistingEnabled'] = !previousState;
    this.resource['update'](host)['$promise'].catch(() => {
      host['transitiveWhitelistingEnabled'] = previousState;
    });
  }

  userCanEditHosts() {
    return !!this.user && this.user['permissions'].includes('EDIT_HOSTS');
  }

  /**
   * Returns true if the host details are visible
   * @param {!string} hostId
   * @return {!boolean} the host visibility
   * @export
   */
  detailsVisible(hostId) {
    return this.visibleHostDetails_.has(hostId);
  }

  /**
   * Makes the host details visible for given host ID
   * @param {!string} hostId
   * @export
   */
  showDetails(hostId) {
    this.visibleHostDetails_.add(hostId);
  }

  /**
   * Hides the host details for given host ID
   * @param {!string} hostId
   * @export
   */
  hideDetails(hostId) {
    this.visibleHostDetails_.delete(hostId);
  }
};
let HostController = upvote.admin.hostpage.HostController;

/** @private {!Object<string, !upvote.admin.lib.controllers.Field>} */
HostController.BASE_FIELDS_ = {
  'id': {'displayName': 'ID', 'value': 'id'},
  'hostname': {'displayName': 'Hostname', 'value': 'hostname'},
  'primary_user': {'displayName': 'Primary User', 'value': 'primary_user'}
};

});  // goog.scope
