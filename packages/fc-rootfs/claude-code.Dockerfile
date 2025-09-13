FROM nikolaik/python-nodejs:python3.10-nodejs20

RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources && \
  sed -i 's/http:/https:/g' /etc/apt/sources.list.d/debian.sources

RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y --no-install-recommends \
  build-essential curl git util-linux jq iputils-ping wget

ARG RELEASE_TAG=
ARG RELEASE_ORG="gitpod-io"
ARG OPENVSCODE_SERVER_ROOT="/home/user/.openvscode-server"

# Downloading the latest VSC Server release and extracting the release archive
# Rename `openvscode-server` cli tool to `code` for convenience
RUN if [ -z "${RELEASE_TAG}" ]; then \
        echo "The RELEASE_TAG build arg must be set." >&2 && \
        exit 1; \
    fi && \
    arch=$(uname -m) && \
    if [ "${arch}" = "x86_64" ]; then \
        arch="x64"; \
    elif [ "${arch}" = "aarch64" ]; then \
        arch="arm64"; \
    elif [ "${arch}" = "armv7l" ]; then \
        arch="armhf"; \
    fi && \
    wget https://githubfast.com/${RELEASE_ORG}/openvscode-server/releases/download/${RELEASE_TAG}/${RELEASE_TAG}-linux-${arch}.tar.gz && \
    tar -xzf ${RELEASE_TAG}-linux-${arch}.tar.gz && \
    mkdir -p $(dirname ${OPENVSCODE_SERVER_ROOT}) && \
    mv -f ${RELEASE_TAG}-linux-${arch} ${OPENVSCODE_SERVER_ROOT} && \
    cp ${OPENVSCODE_SERVER_ROOT}/bin/remote-cli/openvscode-server ${OPENVSCODE_SERVER_ROOT}/bin/remote-cli/code && \
    rm -f ${RELEASE_TAG}-linux-${arch}.tar.gz

# install claude code
RUN npm install -g @anthropic-ai/claude-code
COPY claude-setup.sh /home/user/claude-setup.sh
