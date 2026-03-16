FROM debian:bookworm-slim

# ── System packages ───────────────────────────────────────────────────────────
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        ca-certificates curl git zsh sqlite3 jq wget python3 tmux \
        procps less iputils-ping iproute2 nano htop && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ── ttyd static binary ────────────────────────────────────────────────────────
ARG TTYD_VERSION=1.7.7
RUN DPKG_ARCH=$(dpkg --print-architecture) && \
    case "${DPKG_ARCH}" in \
        amd64)  TTYD_ARCH="x86_64"  ;; \
        arm64)  TTYD_ARCH="aarch64" ;; \
        armhf)  TTYD_ARCH="armhf"   ;; \
        i386)   TTYD_ARCH="i686"    ;; \
        *)      TTYD_ARCH="${DPKG_ARCH}" ;; \
    esac && \
    wget -q "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.${TTYD_ARCH}" \
        -O /usr/local/bin/ttyd && \
    chmod +x /usr/local/bin/ttyd

# ── GitHub CLI ────────────────────────────────────────────────────────────────
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update -qq && \
    apt-get install -y --no-install-recommends gh && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ── User packages (edit config/packages.sh to add your own) ──────────────────
# Keep this layer BEFORE config-file COPYs so that editing tmux.conf/bashrc/
# zshrc does not bust the expensive packages cache.
COPY config/packages.sh /tmp/packages.sh
RUN chmod +x /tmp/packages.sh && /tmp/packages.sh && rm /tmp/packages.sh

# Config files go after packages.sh — OMZ installer overwrites .bashrc/.zshrc,
# so these copies must come last to preserve our versions.
COPY config/bashrc /root/.bashrc
COPY config/tmux.conf /root/.tmux.conf
COPY config/zshrc /root/.zshrc

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV TERM=xterm-256color
ENV GLADE_DIR=/root/.glade

ARG BUILD_DATE=unknown
ENV GLADE_BUILD_DATE=${BUILD_DATE}

EXPOSE 7681 7683 7690 7691 7692 7693 7694 7695 7696 7697 7698 7699

ENTRYPOINT ["/entrypoint.sh"]
