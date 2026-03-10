FROM debian:bookworm-slim

# ── System packages ───────────────────────────────────────────────────────────
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        ca-certificates curl git zsh sqlite3 jq wget python3 tmux && \
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

# ── Shell setup (zsh + Oh My Zsh + Spaceship) ─────────────────────────────────
RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended && \
    git clone --depth=1 https://github.com/spaceship-prompt/spaceship-prompt.git \
        /root/.oh-my-zsh/custom/themes/spaceship-prompt && \
    ln -s /root/.oh-my-zsh/custom/themes/spaceship-prompt/spaceship.zsh-theme \
        /root/.oh-my-zsh/custom/themes/spaceship.zsh-theme && \
    git clone --depth=1 https://github.com/zsh-users/zsh-syntax-highlighting.git \
        /root/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting && \
    git clone --depth=1 https://github.com/zsh-users/zsh-autosuggestions.git \
        /root/.oh-my-zsh/custom/plugins/zsh-autosuggestions

COPY config/zshrc /root/.zshrc
COPY config/bashrc /root/.bashrc
COPY config/tmux.conf /root/.tmux.conf

# ── User packages (edit config/packages.sh to add your own) ──────────────────
COPY config/packages.sh /tmp/packages.sh
RUN chmod +x /tmp/packages.sh && /tmp/packages.sh && rm /tmp/packages.sh

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV TERM=xterm-256color
ENV ROOST_DIR=/root/.roost

EXPOSE 7681 7683 7690 7691 7692 7693 7694 7695 7696 7697 7698 7699

ENTRYPOINT ["/entrypoint.sh"]
