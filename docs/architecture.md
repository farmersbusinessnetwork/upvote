## Architecture

### Technology

Upvote runs on Google App Engine (Python) with an AngularJS frontend. Upvote is
built using Bazel.

### App Structure

On App Engine, Upvote is divided into three modules:

1.  `upvote_app`: The main module which hosts the API, the UI (both user and
    admin), and the voting/policy logic.
    *   Hosts the Upvote API at `/api/web/...` (defined
        [here](../upvote/gae/modules/upvote_app/api/main.py))
    *   Hosts the user app at `/...` (defined
        [here](../upvote/gae/modules/upvote_app/frontend/web_ui/app-routes.js))
    *   Hosts the admin app at `/admin/...` (defined
        [here](../upvote/gae/modules/upvote_app/frontend/admin_ui/app-routes.js))
2.  `santa_api`: The sync server API for Santa.
    *   Hosts the Santa API at `/api/santa/...` (defined
        [here](../upvote/gae/modules/santa_api/main.py))

![Upvote architecture diagram](images/architecture.png)

### Storage

Upvote uses both [Cloud Datastore](https://cloud.google.com/datastore/) and
[BigQuery](https://cloud.google.com/bigquery/) to store its data. Upvote
generally stores active application state (e.g. execution policy, client
settings) in Datastore and offloads historical data to BigQuery.

**NOTE:** BigQuery export is disabled by default. See [setup section](setup.md)
for instructions on how to enable it.

#### Schema

-   `User`: A user accessing Upvote's frontend (identified by their email
    address).
-   `Host`: A machine running an application whitelisting client.
-   `Blockable`: An entity for which execution policy can be created. This
    includes Binaries, Certificates, and Packages.
-   `Event`: An execution event (e.g. block, allow) unique to a
    User-Host-Blockable triple.
    -   These are deduped to the execution's most recent occurrence.
    -   Metadata about the number of occurrences, the time of the least recent,
        and the time of the most recent are retained across dedupes.
-   `Rule`: An execution policy. It can apply to one host or all hosts. It can
    specify a whitelist or a blacklist.
-   `Vote`: An upvote or downvote on a Blockable. It carries variable weight
    depending on the user who cast it.

`Rule`, `Event`, `Host`, and all `Blockable` types have platform-specific
variants (e.g. `Bit9Rule`, `SantaEvent`).

### Application Whitelisting Clients

Upvote supports [Santa](https://github.com/google/santa) on macOS, a
Google-built whitelisting client, and
[Bit9](https://www.carbonblack.com/products/cb-protection/) (now known as Carbon
Black Protection) on Windows. Upvote has a dedicated App Engine module for both
the Santa sync API as well as the Bit9 sync process.

*NOTE:* Deployed modules that aren't serving traffic won't cost anything in App
Engine.
