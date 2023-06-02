FROM debian:buster

RUN apt-get update && \
    apt-get install -y --no-install-recommends --no-install-suggests wget git apt-transport-https ca-certificates gnupg curl vim gcc g++ python2 ssh && \
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add - && \
    apt-get update && apt-get install -y google-cloud-cli && \
    wget https://github.com/bazelbuild/bazel/releases/download/0.21.0/bazel-0.21.0-linux-x86_64 && \
    mv bazel-0.21.0-linux-x86_64 /usr/local/bin/bazel && \
    chmod u+x /usr/local/bin/bazel && \
    ln -s /usr/bin/python2 /usr/bin/python

WORKDIR /root

# you need to run:
# 1) gcloud init, and select santaupvote project,
# 2) git clone git@github.com:farmersbusinessnetwork/upvote.git
# 3) run fbn/deploy.sh
