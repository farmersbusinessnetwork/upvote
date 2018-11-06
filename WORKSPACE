git_repository(
    name = "io_bazel_rules_appengine",
    remote = "https://github.com/bazelbuild/rules_appengine.git",
    # Check https://github.com/bazelbuild/rules_appengine/releases for the latest version.
    #tag = "0.0.8",
    # We need this fix: https://github.com/bazelbuild/rules_appengine/commit/8122a7086c101d57f940ffe7075e635d7f787b70#diff-6c4ba9456a113bcff5caecf8bffd5833R26
    commit = "ee5eec25f22782e03c5abda88f2c946e88d776f3",
)

load(
    "@io_bazel_rules_appengine//appengine:sdk.bzl",
    "appengine_repositories",
)

appengine_repositories()


load(
    "@io_bazel_rules_appengine//appengine:py_appengine.bzl",
    "py_appengine_repositories",
)

# Available from: https://storage.googleapis.com/appengine-sdks/featured/google_appengine_{version}.zip
py_appengine_repositories(
    version = '1.9.78',
    sha256 = 'fc37637530705260102d6acb03f5086290093394a07c51706c37da5254ce215b',
)

# needed for mock, webtest
new_http_archive(
    name = "six_archive",
    build_file = "//third_party:six.BUILD",
    sha256 = "105f8d68616f8248e24bf0e9372ef04d3cc10104f1980f54d57b2ce73a5ad56a",
    strip_prefix = "six-1.10.0",
    urls = [
        "http://mirror.bazel.build/pypi.python.org/packages/source/s/six/six-1.10.0.tar.gz",
        "https://pypi.python.org/packages/source/s/six/six-1.10.0.tar.gz",
    ],
)

bind(
    name = "six",
    actual = "@six_archive//:six",
)

new_http_archive(
    name = "mock_archive",
    build_file = "//third_party:mock.BUILD",
    sha256 = "b839dd2d9c117c701430c149956918a423a9863b48b09c90e30a6013e7d2f44f",
    strip_prefix = "mock-1.0.1",
    urls = [
        "http://mirror.bazel.build/pypi.python.org/packages/a2/52/7edcd94f0afb721a2d559a5b9aae8af4f8f2c79bc63fdbe8a8a6c9b23bbe/mock-1.0.1.tar.gz",
        "https://pypi.python.org/packages/a2/52/7edcd94f0afb721a2d559a5b9aae8af4f8f2c79bc63fdbe8a8a6c9b23bbe/mock-1.0.1.tar.gz",
    ],
)

bind(
    name = "mock",
    actual = "@mock_archive//:mock",
)

bind(
    name = "webob",
    actual = "@com_google_appengine_python//:webob-latest",
)

# needed for webtest
new_http_archive(
    name = "waitress_archive",
    build_file = "//third_party:waitress.BUILD",
    sha256 = "c74fa1b92cb183d5a3684210b1bf0a0845fe8eb378fa816f17199111bbf7865f",
    strip_prefix = "waitress-1.0.2",
    urls = [
        "http://mirror.bazel.build/pypi.python.org/packages/cd/f4/400d00863afa1e03618e31fd7e2092479a71b8c9718b00eb1eeb603746c6/waitress-1.0.2.tar.gz",
        "https://pypi.python.org/packages/cd/f4/400d00863afa1e03618e31fd7e2092479a71b8c9718b00eb1eeb603746c6/waitress-1.0.2.tar.gz",
    ],
)

bind(
    name = "waitress",
    actual = "@waitress_archive//:waitress",
)

# needed for webtest
new_http_archive(
    name = "beautifulsoup4_archive",
    build_file = "//third_party:beautifulsoup4.BUILD",
    sha256 = "b21ca09366fa596043578fd4188b052b46634d22059e68dd0077d9ee77e08a3e",
    strip_prefix = "beautifulsoup4-4.5.3",
    urls = [
        "http://mirror.bazel.build/pypi.python.org/packages/9b/a5/c6fa2d08e6c671103f9508816588e0fb9cec40444e8e72993f3d4c325936/beautifulsoup4-4.5.3.tar.gz",
        "https://pypi.python.org/packages/9b/a5/c6fa2d08e6c671103f9508816588e0fb9cec40444e8e72993f3d4c325936/beautifulsoup4-4.5.3.tar.gz",
    ],
)

bind(
    name = "beautifulsoup4",
    actual = "@beautifulsoup4_archive//:beautifulsoup4",
)

new_http_archive(
    name = "webtest_archive",
    build_file = "//third_party:webtest.BUILD",
    sha256 = "2b6abd2689f28a0b3575bcb5a36757f2344670dd13a8d9272d3a987c2fd1b615",
    strip_prefix = "WebTest-2.0.27",
    urls = [
        "http://mirror.bazel.build/pypi.python.org/packages/80/fa/ca3a759985c72e3a124cbca3e1f8a2e931a07ffd31fd45d8f7bf21cb95cf/WebTest-2.0.27.tar.gz",
        "https://pypi.python.org/packages/80/fa/ca3a759985c72e3a124cbca3e1f8a2e931a07ffd31fd45d8f7bf21cb95cf/WebTest-2.0.27.tar.gz",
    ],
)

bind(
    name = "webtest",
    actual = "@webtest_archive//:webtest",
)

git_repository(
    name = "absl_git",
    commit = "ed0faa035139d118806802c06eba7f02abd3e2a9",
    remote = "https://github.com/abseil/abseil-py.git",
)

new_git_repository(
    name = "rsa_git",
    build_file = "//third_party:rsa.BUILD",
    commit = "d00852509aa3702827941882941dc1c76368cf8c",
    remote = "https://github.com/sybrenstuvel/python-rsa.git",
)

bind(
    name = "rsa",
    actual = "@rsa_git//:rsa",
)

new_git_repository(
    name = "pyasn1_git",
    build_file = "//third_party:pyasn1.BUILD",
    commit = "24d5afade36b05d7ba79460b8a9d4e5d99e19918",
    remote = "https://github.com/etingof/pyasn1.git",
)

bind(
    name = "pyasn1",
    actual = "@pyasn1_git//:pyasn1",
)

new_git_repository(
    name = "oauth2client_git",
    build_file = "//third_party:oauth2client.BUILD",
    commit = "97320af2733f7bdbe47f067327610e348f953ae1",
    remote = "https://github.com/google/oauth2client.git",
)

bind(
    name = "oauth2client",
    actual = "@oauth2client_git//:oauth2client",
)

# needed for googleapiclient
new_http_archive(
    name = "uritemplate_archive",
    build_file = "//third_party:uritemplate.BUILD",
    sha256 = "c02643cebe23fc8adb5e6becffe201185bf06c40bda5c0b4028a93f1527d011d",
    strip_prefix = "uritemplate-3.0.0",
    urls = [
        "http://mirror.bazel.build/pypi.python.org/packages/cd/db/f7b98cdc3f81513fb25d3cbe2501d621882ee81150b745cdd1363278c10a/uritemplate-3.0.0.tar.gz",
        "https://pypi.python.org/packages/cd/db/f7b98cdc3f81513fb25d3cbe2501d621882ee81150b745cdd1363278c10a/uritemplate-3.0.0.tar.gz",
    ],
)

bind(
    name = "uritemplate",
    actual = "@uritemplate_archive//:uritemplate",
)

new_git_repository(
    name = "googleapiclient_git",
    build_file = "//third_party:googleapiclient.BUILD",
    remote = "https://github.com/google/google-api-python-client.git",
    tag = "v1.5.5",
)

bind(
    name = "googleapiclient",
    actual = "@googleapiclient_git//:googleapiclient",
)

# needed for requests
new_git_repository(
    name = "certifi_git",
    build_file = "//third_party:certifi.BUILD",
    remote = "https://github.com/certifi/python-certifi.git",
    tag = "2017.04.17",
)

bind(
    name = "certifi",
    actual = "@certifi_git//:certifi",
)

# needed for requests
new_git_repository(
    name = "idna_git",
    build_file = "//third_party:idna.BUILD",
    remote = "https://github.com/kjd/idna.git",
    tag = "v2.5",
)

bind(
    name = "idna",
    actual = "@idna_git//:idna",
)

# needed for requests
new_git_repository(
    name = "urllib3_git",
    build_file = "//third_party:urllib3.BUILD",
    remote = "https://github.com/shazow/urllib3.git",
    tag = "1.22",
)

bind(
    name = "urllib3",
    actual = "@urllib3_git//:urllib3",
)

# needed for requests
new_git_repository(
    name = "chardet_git",
    build_file = "//third_party:chardet.BUILD",
    remote = "https://github.com/chardet/chardet.git",
    tag = "3.0.2",
)

bind(
    name = "chardet",
    actual = "@chardet_git//:chardet",
)

# needed for gcloud_bigquery
new_git_repository(
    name = "requests_git",
    build_file = "//third_party:requests.BUILD",
    remote = "https://github.com/requests/requests.git",
    tag = "v2.17.3",
)

bind(
    name = "requests",
    actual = "@requests_git//:requests",
)

# needed for gcloud_core, oauth2client
new_http_archive(
    name = "httplib2_archive",
    build_file = "//third_party:httplib2.BUILD",
    sha256 = "c3aba1c9539711551f4d83e857b316b5134a1c4ddce98a875b7027be7dd6d988",
    strip_prefix = "httplib2-0.9.2/python2",
    urls = [
        "https://mirror.bazel.build/pypi.python.org/packages/ff/a9/5751cdf17a70ea89f6dde23ceb1705bfb638fd8cee00f845308bf8d26397/httplib2-0.9.2.tar.gz",
        "https://pypi.python.org/packages/ff/a9/5751cdf17a70ea89f6dde23ceb1705bfb638fd8cee00f845308bf8d26397/httplib2-0.9.2.tar.gz",
    ],
)

bind(
    name = "httplib2",
    actual = "@httplib2_archive//:httplib2",
)

# needed for gcloud_core
new_http_archive(
    name = "gapi_protos_http",
    build_file = "//third_party:gapi_protos.BUILD",
    sha256 = "c075eddaa2628ab519e01b7d75b76e66c40eaa50fc52758d8225f84708950ef2",
    strip_prefix = "googleapis-common-protos-1.5.3",
    urls = [
        "http://mirror.bazel.build/pypi.python.org/packages/00/03/d25bed04ec8d930bcfa488ba81a2ecbf7eb36ae3ffd7e8f5be0d036a89c9/googleapis-common-protos-1.5.3.tar.gz",
        "https://files.pythonhosted.org/packages/00/03/d25bed04ec8d930bcfa488ba81a2ecbf7eb36ae3ffd7e8f5be0d036a89c9/googleapis-common-protos-1.5.3.tar.gz",
    ],
)

bind(
    name = "gapi_protos",
    actual = "@gapi_protos_http//:gapi_protos",
)

# needed for google-api-core for  gcloud_core
new_http_archive(
    name = "protobuf_archive",
    build_file = "//third_party:protobuf.BUILD",
    sha256 = "1489b376b0f364bcc6f89519718c057eb191d7ad6f1b395ffd93d1aa45587811",
    strip_prefix = "protobuf-3.6.1",
    urls = [
        "http://mirror.bazel.build/pypi.python.org/packages/1b/90/f531329e628ff34aee79b0b9523196eb7b5b6b398f112bb0c03b24ab1973/protobuf-3.6.1.tar.gz",
        "https://files.pythonhosted.org/packages/1b/90/f531329e628ff34aee79b0b9523196eb7b5b6b398f112bb0c03b24ab1973/protobuf-3.6.1.tar.gz",
    ],
)

bind(
    name = "protobuf",
    actual = "@protobuf_archive//:protobuf",
)

# needed for gcloud_core
new_git_repository(
    name = "gcloud_auth_httplib2_git",
    build_file = "//third_party:gcloud_auth_httplib2.BUILD",
    commit = "136da2cd50aa7deb769062cf1d77259d64743a7f",
    remote = "https://github.com/GoogleCloudPlatform/google-auth-library-python-httplib2.git",
)

bind(
    name = "gcloud_auth_httplib2",
    actual = "@gcloud_auth_httplib2_git//:gcloud_auth_httplib2",
)

# needed for gcloud_api_core

new_http_archive(
    name = "futures_archive",
    build_file = "//third_party:futures.BUILD",
    sha256 = "9ec02aa7d674acb8618afb127e27fde7fc68994c0437ad759fa094a574adb265",
    strip_prefix = "futures-3.2.0",
    urls = [
        "https://files.pythonhosted.org/packages/1f/9e/7b2ff7e965fc654592269f2906ade1c7d705f1bf25b7d469fa153f7d19eb/futures-3.2.0.tar.gz",
    ],
)

bind(
    name = "futures",
    actual = "@futures_archive//:futures",
)

new_http_archive(
    name = "pytz_archive",
    build_file = "//third_party:pytz.BUILD",
    sha256 = "ffb9ef1de172603304d9d2819af6f5ece76f2e85ec10692a524dd876e72bf277",
    strip_prefix = "pytz-2018.5",
    urls = [
        "https://files.pythonhosted.org/packages/ca/a9/62f96decb1e309d6300ebe7eee9acfd7bccaeedd693794437005b9067b44/pytz-2018.5.tar.gz",
    ],
)

bind(
    name = "pytz",
    actual = "@pytz_archive//:pytz",
)

# needed for gcloud_core
new_http_archive(
    name = "gcloud_api_core_archive",
    build_file = "//third_party:gcloud_api_core.BUILD",
    sha256 = "a9ae625afd0ea5a4618604675d1fc140998c9c2b17f1d91817a7a7f5b33f7484",
    strip_prefix = "google-api-core-1.4.1",
    urls = [
        "https://files.pythonhosted.org/packages/19/f3/fb05744f23986202714f7198472ce1f18dc8df12113cfdde777ca1172ba3/google-api-core-1.4.1.tar.gz",
    ],
)

bind(
    name = "gcloud_api_core",
    actual = "@gcloud_api_core_archive//:gcloud_api_core",
)

# needed for gcloud_bigquery
new_http_archive(
    name = "gcloud_core_archive",
    build_file = "//third_party:gcloud_core.BUILD",
    sha256 = "89e8140a288acec20c5e56159461d3afa4073570c9758c05d4e6cb7f2f8cc440",
    strip_prefix = "google-cloud-core-0.28.1",
    urls = [
        "https://mirror.bazel.build/files.pythonhosted.org/packages/22/f0/a062f4d877420e765f451af99045326e44f9b026088d621ca40011f14c66/google-cloud-core-0.28.1.tar.gz",
        "https://files.pythonhosted.org/packages/22/f0/a062f4d877420e765f451af99045326e44f9b026088d621ca40011f14c66/google-cloud-core-0.28.1.tar.gz",
    ],
)

bind(
    name = "gcloud_core",
    actual = "@gcloud_core_archive//:gcloud_core",
)

# needed for gcloud_bigquery
new_git_repository(
    name = "gcloud_resumable_media_git",
    build_file = "//third_party:gcloud_resumable_media.BUILD",
    remote = "https://github.com/GoogleCloudPlatform/google-resumable-media-python.git",
    tag = "0.2.1",
)

bind(
    name = "gcloud_resumable_media",
    actual = "@gcloud_resumable_media_git//:gcloud_resumable_media",
)

# NOTE: workaround for pkg_resources import issue with gcloud_bigquery.
new_http_archive(
    name = "setuptools_archive",
    build_file = "//third_party:setuptools.BUILD",
    sha256 = "47881d54ede4da9c15273bac65f9340f8929d4f0213193fa7894be384f2dcfa6",
    strip_prefix = "setuptools-40.2.0",
    urls = [
        "http://mirror.bazel.build/pypi.python.org/packages/source/s/six/setuptools-40.2.0.zip",
        "https://pypi.python.org/packages/source/s/setuptools/setuptools-40.2.0.zip",
    ],
)

bind(
    name = "setuptools",
    actual = "@setuptools_archive//:setuptools",
)

# needed for gcloud_auth
new_git_repository(
    name = "pyasn1_modules_git",
    build_file = "//third_party:pyasn1_modules.BUILD",
    remote = "https://github.com/etingof/pyasn1-modules.git",
    tag = "v0.0.10",
)

bind(
    name = "pyasn1_modules",
    actual = "@pyasn1_modules_git//:pyasn1_modules",
)

# needed for gcloud_auth
new_git_repository(
    name = "cachetools_git",
    build_file = "//third_party:cachetools.BUILD",
    remote = "https://github.com/tkem/cachetools.git",
    tag = "v2.0.0",
)

bind(
    name = "cachetools",
    actual = "@cachetools_git//:cachetools",
)

# needed for gcloud_bigquery
new_git_repository(
    name = "gcloud_auth_git",
    build_file = "//third_party:gcloud_auth.BUILD",
    remote = "https://github.com/GoogleCloudPlatform/google-auth-library-python.git",
    tag = "v1.0.0",
)

bind(
    name = "gcloud_auth",
    actual = "@gcloud_auth_git//:gcloud_auth",
)

# google-cloud-bigquery
new_http_archive(
    name = "gcloud_bigquery_archive",
    build_file = "//third_party:gcloud_bigquery.BUILD",
    sha256 = "aed2b1d4db1e21d891522d6d6bb14476e6ba58c681cbb68eeb42c168a4e3fda9",
    strip_prefix = "google-cloud-bigquery-1.1.0",
    urls = [
        "https://mirror.bazel.build/files.pythonhosted.org/packages/24/f8/54a929bc544d4744ef02cee1c9b97c9498d835445608bf2d099268ed8f1c/google-cloud-bigquery-1.1.0.tar.gz",
        "https://files.pythonhosted.org/packages/24/f8/54a929bc544d4744ef02cee1c9b97c9498d835445608bf2d099268ed8f1c/google-cloud-bigquery-1.1.0.tar.gz",
    ],
)

bind(
    name = "gcloud_bigquery",
    actual = "@gcloud_bigquery_archive//:gcloud_bigquery",
)

# google-cloud-monitoring
# unfortunately the latest monitoring relies on grpcio, which is really complicated to support via bazel: https://github.com/grpc/grpc/commit/e1210f78f82b2c9e4ae9f59463322209d45d5354
new_http_archive(
    name = "gcloud_monitoring_archive",
    build_file = "//third_party:gcloud_monitoring.BUILD",
    sha256 = "534d66d97611c9c6e08823532f5144f6786d3a6103a6d5ed6411ac465faa5341",
    strip_prefix = "google-cloud-monitoring-0.28.1",
    urls = [
        "https://mirror.bazel.build/files.pythonhosted.org/packages/bb/9b/cb40fe7bfbb57ba4f031c93d5353e58c0f2cc0060e00c4871a90360ae2d4/google-cloud-monitoring-0.28.1.tar.gz",
        "https://files.pythonhosted.org/packages/bb/9b/cb40fe7bfbb57ba4f031c93d5353e58c0f2cc0060e00c4871a90360ae2d4/google-cloud-monitoring-0.28.1.tar.gz",
    ],
)

bind(
    name = "gcloud_monitoring",
    actual = "@gcloud_monitoring_archive//:gcloud_monitoring",
)


new_http_archive(
    name = "requests_toolbelt_archive",
    build_file = "//third_party:requests_toolbelt.BUILD",
    sha256 = "f6a531936c6fa4c6cfce1b9c10d5c4f498d16528d2a54a22ca00011205a187b5",
    strip_prefix = "requests-toolbelt-0.8.0",
    urls = [
        "https://pypi.python.org/packages/86/f9/e80fa23edca6c554f1994040064760c12b51daff54b55f9e379e899cd3d4/requests-toolbelt-0.8.0.tar.gz",
    ],
)

bind(
    name = "requests_toolbelt",
    actual = "@requests_toolbelt_archive//:requests_toolbelt",
)

http_archive(
    name = "io_bazel_rules_closure",
    sha256 = "f91ec43ce3898c6b965e2bdff91a53755a13004adbeaf606804f719f1e888340",
    strip_prefix = "rules_closure-3555e5ba61fdcc17157dd833eaf7d19b313b1bca",
    urls = [
        "https://github.com/bazelbuild/rules_closure/archive/3555e5ba61fdcc17157dd833eaf7d19b313b1bca.tar.gz",  # 2018-07-23
    ],
)

load("@io_bazel_rules_closure//closure:defs.bzl", "closure_repositories")

closure_repositories()

http_archive(
    name = "org_pubref_rules_node",
    sha256 = "d161dd6551c1061ee954fd6ec014a671d932728776f55a6dcb6ac8ddd5cb5354",
    strip_prefix = "rules_node-993a258096aaf3d4b295c18856e3405011cad99c",
    urls = [
        "http://mirror.bazel.build/github.com/pubref/rules_node/archive/993a258096aaf3d4b295c18856e3405011cad99c.tar.gz",
        "https://github.com/pubref/rules_node/archive/993a258096aaf3d4b295c18856e3405011cad99c.tar.gz",
    ],
)

load("@org_pubref_rules_node//node:rules.bzl", "node_repositories", "yarn_modules")

node_repositories()

yarn_modules(
    name = "npm_html2js",
    deps = {
        "ng-html2js": "3.0.0",
    },
)

new_git_repository(
    name = "material_steppers",
    build_file = "//third_party:md_steppers.BUILD",
    commit = "042f812382aa16eada6078594582150fa5dc7235",
    remote = "https://github.com/eberlitz/material-steppers.git",
)

# FBN
new_http_archive(
    name = "datadog_archive",
    build_file = "//third_party:datadog.BUILD",
    sha256 = "86cef95acd73543d18c417f1b0313c0a7274ed8f5ae9cceb46314f4e588085b1",
    strip_prefix = "datadog-0.22.0",
    urls = [
        "https://files.pythonhosted.org/packages/29/45/4f21ad21de22c7abe64f340e6fe1ebc412bb1e8bb580dd963fd70ac86441/datadog-0.22.0.tar.gz",
    ],
)

bind(
    name = "datadog",
    actual = "@datadog_archive//:datadog",
)