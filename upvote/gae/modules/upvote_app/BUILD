package(default_visibility = ["//upvote"])

load("//upvote:builddefs.bzl", "py_appengine_library", "upvote_appengine_binary")

# AppEngine Libraries
# ==============================================================================

py_appengine_library(
    name = "upvote_app_library",
    data = [
        "//upvote/gae:app.yaml",
        "//upvote/gae/modules/upvote_app/frontend:app_css",
        "//upvote/gae/modules/upvote_app/frontend:app_min",
        "//upvote/gae/templates/web:templates",
    ],
    deps = [
        "//upvote/gae/cron:main",
        "//upvote/gae/modules/upvote_app/api/web:main",
    ],
)

# Binaries
# ==============================================================================

upvote_appengine_binary(
    name = "upvote_app_binary",
    srcs = ["//upvote/gae/modules/upvote_app/api/web:main.py"],
    configs = [
        "//upvote/gae:app.yaml",
        "//upvote/gae:appengine_config.py",
    ],
    deps = [
        ":upvote_app_library",
    ],
)
