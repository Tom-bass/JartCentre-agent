# Build librespot on the native runner by cross-compiling for arm64.
# Avoids Rust compilation under QEMU, which would take 60+ minutes.
ARG BUILDPLATFORM
FROM --platform=$BUILDPLATFORM rust:bookworm AS librespot-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        crossbuild-essential-arm64 \
        pkg-config \
        git \
    && dpkg --add-architecture arm64 \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libasound2-dev:arm64 \
        libssl-dev:arm64 \
        libavahi-compat-libdnssd-dev:arm64 \
    && rm -rf /var/lib/apt/lists/*

RUN rustup target add aarch64-unknown-linux-gnu

ENV CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=aarch64-linux-gnu-gcc \
    PKG_CONFIG_ALLOW_CROSS=1 \
    PKG_CONFIG_LIBDIR=/usr/lib/aarch64-linux-gnu/pkgconfig

# Clone from git HEAD — avoids crates.io dependency conflicts and gets latest Spotify API fixes.
RUN git clone --depth 1 \
        https://github.com/librespot-org/librespot.git /tmp/librespot \
    && cargo install --path /tmp/librespot \
        --locked \
        --target aarch64-unknown-linux-gnu \
        --root /output \
    && rm -rf /tmp/librespot


# Final arm64 runtime image
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        dumb-init \
        supervisor \
        alsa-utils \
        libasound2 \
        libavahi-compat-libdnssd1 \
        snapclient \
        python3 \
        python3-pip \
        wget \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=librespot-builder /output/bin/librespot /usr/local/bin/librespot

COPY webui/requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt

COPY webui/ /app/
COPY run-librespot.sh run-snapclient.sh init-services.sh read-config /usr/local/bin/
COPY supervisord.conf /etc/supervisor/conf.d/audio.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /usr/local/bin/run-librespot.sh \
              /usr/local/bin/run-snapclient.sh \
              /usr/local/bin/init-services.sh \
              /usr/local/bin/read-config \
              /entrypoint.sh

# Baked in at build time so the UI can show the running git SHA and detect updates.
ARG GIT_SHA=unknown
ENV IMAGE_SHA=$GIT_SHA

ENTRYPOINT ["/usr/bin/dumb-init", "--", "/entrypoint.sh"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget -qO- http://localhost:8080/api/health > /dev/null || exit 1

LABEL org.opencontainers.image.title="JartCentre Agent" \
      org.opencontainers.image.description="Snapclient + Librespot + monitoring agent for Raspberry Pi fleet" \
      org.opencontainers.image.licenses="MIT"
