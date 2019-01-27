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

goog.provide('upvote.hostlistpage.HostListController');

goog.require('upvote.errornotifier.ErrorService');
goog.require('upvote.exemptions.ExemptionService');
goog.require('upvote.hosts.ExemptionState');
goog.require('upvote.hosts.HostService');
goog.require('upvote.hosts.HostUtilsService');
goog.require('upvote.shared.Page');
goog.require('upvote.shared.models.AnyHost');

goog.scope(() => {

/** Controller for host page. */
upvote.hostlistpage.HostListController = class {
  /**
   * @param {!upvote.exemptions.ExemptionService} exemptionService
   * @param {!upvote.hosts.HostService} hostService
   * @param {!upvote.hosts.HostUtilsService} hostUtilsService
   * @param {!upvote.errornotifier.ErrorService} errorService
   * @param {!angular.$location} $location
   * @param {!upvote.shared.Page} page Details about the active page
   * @ngInject
   */
  constructor(
      exemptionService, hostService, hostUtilsService, errorService, $location,
      page) {
    /** @const @private {!upvote.exemptions.ExemptionService} */
    this.exemptionService_ = exemptionService;
    /** @private {!upvote.hosts.HostService} */
    this.hostService_ = hostService;
    /** @private {!upvote.errornotifier.ErrorService} errorService */
    this.errorService_ = errorService;
    /** @private {!angular.$location} $location */
    this.location_ = $location;

    /** @export {!upvote.hosts.HostUtilsService} */
    this.hostUtils = hostUtilsService;
    /** @export {?Array<?upvote.shared.models.AnyHost>} */
    this.hosts = null;

    page.title = 'Hosts';

    /** @export {boolean} */
    this.showHidden = false;

    this.init_();
  }

  /** @private */
  init_() {
    this.hostService_.getAssociatedHosts()
        .then((response) => {
          this.hosts = response['data'];
        })
        .catch((response) => {
          this.errorService_.createDialogFromError(response);
        });
  }

  /**
   * Return whether a host's mode is locked.
   * @param {!upvote.shared.models.AnyHost} host
   * @return {boolean}
   * @export
   */
  isModeLocked(host) {
    return !!host['clientModeLock'];
  }

  /**
   * Return whether a host hasn't synced recently.
   * @param {!upvote.shared.models.AnyHost} host
   * @return {boolean}
   * @export
   */
  isStale(host) {
    let lastSync = new Date(host['ruleSyncDt']);
    if (!lastSync) {
      return true;
    }
    let secondsSinceSync = new Date().getTime() - lastSync.getTime();
    return secondsSinceSync >= HostListController.STALE_THRESHOLD;
  }

  /**
   * Return whether to display exemption status for a host.
   * @param {!upvote.shared.models.AnyHost} host
   * @return {boolean}
   * @export
   */
  isExemptionStatusVisible(host) {
    return (
        host.exemption != null &&
        host.exemption.state != upvote.hosts.ExemptionState.CANCELLED);
  }

  /**
   * Return whether the exemption is in a bad state.
   * @param {!upvote.shared.models.AnyHost} host
   * @return {boolean}
   * @export
   */
  isExemptionInBadState(host) {
    return (
        host.exemption != null &&
        (host.exemption.state == upvote.hosts.ExemptionState.DENIED ||
         host.exemption.state == upvote.hosts.ExemptionState.REVOKED));
  }

  /**
   * Return whether the exemption is in a state where it can be renewed.
   * @param {!upvote.shared.models.AnyHost} host
   * @return {boolean}
   * @export
   */
  isExemptionRenewable(host) {
    return (
        host.exemption != null &&
        host.exemption.state == upvote.hosts.ExemptionState.APPROVED);
  }

  /**
   * Navigates to a host's "request exception" page.
   * @param {string} hostId
   * @export
   */
  goToRequestPage(hostId) {
    let requestPath = '/hosts/' + hostId + '/request-exception';
    this.location_.path(requestPath);
  }

  /**
   * Navigates to a host's "blockables" page.
   * @param {string} hostId
   * @export
   */
  goToBlockablesPage(hostId) {
    let requestPath = '/hosts/' + hostId + '/blockables';
    this.location_.path(requestPath);
  }

  /**
   * Requests to cancel the host's Exemption.
   * @param {string} hostId
   * @export
   */
  cancelExemption(hostId) {
    this.exemptionService_.cancelExemption(hostId)
        .then((response) => this.init_())
        .catch((response) => {
          this.errorService_.createDialogFromError(response);
        });
  }

  /**
   * Toggles the hidden state of the host
   * @param {!upvote.shared.models.AnyHost} host
   * @export
   */
  toggleVisibility(host) {
    this.hostService_.setHidden(host.id, !host.hidden)
        .then((response) => {
          host.hidden = !host.hidden;
        })
        .catch((response) => {
          this.errorService_.createDialogFromError(response);
        });
  }
};
let HostListController = upvote.hostlistpage.HostListController;

/**
 * The number of milliseconds since a host's last sync after which it is
 * considered stale. The current limit is 30 days.
 * @export {number}
 */
HostListController.STALE_THRESHOLD = (1000 * 60 * 60 * 24) * 30;
});  // goog.scope
