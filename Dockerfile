# syntax=docker/dockerfile:1
FROM alpine:3 AS runtime
RUN apk add --no-cache bash iproute2 iptables ip6tables ca-certificates

# Keep the complete sources alongside the distributed runtime packages.
FROM runtime AS alpine-sources
RUN cp /lib/apk/db/installed /tmp/runtime-installed \
 && apk add --no-cache python3 git abuild
COPY scripts/bundle-alpine-sources.py /tmp/bundle-alpine-sources.py
RUN DISTFILES_MIRROR="https://distfiles.alpinelinux.org/distfiles/v$(cut -d. -f1,2 /etc/alpine-release)" \
      python3 /tmp/bundle-alpine-sources.py /tmp/runtime-installed /tmp/alpine-sources \
 && mkdir -p /out \
 && tar -czf /out/alpine-sources.tar.gz -C /tmp alpine-sources

FROM golang:alpine AS build
ARG AWG_GO_COMMIT
ARG AWG_TOOLS_COMMIT
RUN apk add --no-cache git make bash gcc musl-dev linux-headers
COPY scripts/quick-userspace.bash /tmp/quick-userspace.bash
RUN test -n "$AWG_GO_COMMIT" && test -n "$AWG_TOOLS_COMMIT" \
 && mkdir -p /src/go /src/tools /out/licenses/go /out/licenses/tools
RUN git -C /src/go init \
 && git -C /src/go remote add origin https://github.com/amnezia-vpn/amneziawg-go.git \
 && git -C /src/go fetch --depth=1 origin "$AWG_GO_COMMIT" \
 && git -C /src/go checkout --detach FETCH_HEAD \
 && test "$(git -C /src/go rev-parse HEAD)" = "$AWG_GO_COMMIT" \
 && cd /src/go && go mod vendor \
 && CGO_ENABLED=0 go build -mod=vendor -trimpath -ldflags="-s -w" -o /out/amneziawg-go
RUN git -C /src/tools init \
 && git -C /src/tools remote add origin https://github.com/amnezia-vpn/amneziawg-tools.git \
 && git -C /src/tools fetch --depth=1 origin "$AWG_TOOLS_COMMIT" \
 && git -C /src/tools checkout --detach FETCH_HEAD \
 && test "$(git -C /src/tools rev-parse HEAD)" = "$AWG_TOOLS_COMMIT" \
 && cd /src/tools/src && make && make install DESTDIR=/out PREFIX=/usr WITH_WGQUICK=yes
# Use upstream's explicit function-override hook, and fail if it disappears.
RUN test "$(grep -Fxc '# ~~ function override insertion point ~~' /out/usr/bin/awg-quick)" = 1 \
 && sed -i '/^# ~~ function override insertion point ~~$/r /tmp/quick-userspace.bash' /out/usr/bin/awg-quick \
 && grep -Fq '# AWGdocker: force userspace' /out/usr/bin/awg-quick \
 && bash -n /out/usr/bin/awg-quick
RUN set -eu; for component in go tools; do \
      find "/src/$component" -maxdepth 1 -type f \
        \( -iname '*license*' -o -iname 'copying*' \) \
        -exec cp '{}' "/out/licenses/$component/" \; ; \
      test -n "$(ls -A /out/licenses/$component)"; \
    done

RUN mkdir -p /out/sources \
 && tar --exclude='go/.git' -czf /out/sources/amneziawg-go.tar.gz -C /src go \
 && git -C /src/tools archive --format=tar.gz --prefix=amneziawg-tools/ \
      -o /out/sources/amneziawg-tools.tar.gz HEAD

FROM runtime AS final
ARG AWG_GO_TAG
ARG AWG_GO_COMMIT
ARG AWG_TOOLS_TAG
ARG AWG_TOOLS_COMMIT
ARG SOURCE_URL
ARG SOURCE_REVISION
COPY --from=build /out/amneziawg-go /usr/bin/
COPY --from=build /out/usr/bin/awg /out/usr/bin/awg-quick /usr/bin/
COPY --from=build /out/licenses /usr/share/licenses/amneziawg
COPY --from=build /out/sources /usr/src/awg-docker/
COPY --from=alpine-sources /out/alpine-sources.tar.gz /usr/src/awg-docker/
COPY Dockerfile entrypoint.sh THIRD_PARTY.md /usr/src/awg-docker/build/
COPY scripts/quick-userspace.bash scripts/build-local.sh scripts/resolve-upstream.py scripts/bundle-alpine-sources.py /usr/src/awg-docker/build/scripts/
COPY LICENSES/ /usr/share/licenses/awg-docker/
COPY LICENSE /usr/share/licenses/awg-docker/MIT.txt
# Do not rewrite a sysctl already set by Compose in read-only /proc/sys.
# Fail closed if upstream changes the expected statement.
RUN test "$(grep -Fc 'cmd sysctl -q net.ipv4.conf.all.src_valid_mark=1' /usr/bin/awg-quick)" = 1 \
 && sed -i 's#cmd sysctl -q net.ipv4.conf.all.src_valid_mark=1#{ [[ $(sysctl -n net.ipv4.conf.all.src_valid_mark) == 1 ]] || cmd sysctl -q net.ipv4.conf.all.src_valid_mark=1; }#' /usr/bin/awg-quick \
 && grep -Fq 'sysctl -n net.ipv4.conf.all.src_valid_mark' /usr/bin/awg-quick \
 && sed -i "2i# Modified by AWGdocker on $(date -u +%F): force userspace and preserve an already-set src_valid_mark." /usr/bin/awg-quick \
 && bash -n /usr/bin/awg-quick
RUN mkdir -p /usr/src/awg-docker/modified \
 && cp /usr/bin/awg-quick /usr/src/awg-docker/modified/awg-quick \
 && printf 'go_tag=%s\ngo_commit=%s\ntools_tag=%s\ntools_commit=%s\nsource_url=%s\nsource_revision=%s\n' \
      "$AWG_GO_TAG" "$AWG_GO_COMMIT" "$AWG_TOOLS_TAG" "$AWG_TOOLS_COMMIT" \
      "$SOURCE_URL" "$SOURCE_REVISION" > /usr/src/awg-docker/versions.txt
LABEL org.opencontainers.image.source="$SOURCE_URL" \
      org.opencontainers.image.revision="$SOURCE_REVISION" \
      io.amneziawg.go.tag="$AWG_GO_TAG" \
      io.amneziawg.go.commit="$AWG_GO_COMMIT" \
      io.amneziawg.tools.tag="$AWG_TOOLS_TAG" \
      io.amneziawg.tools.commit="$AWG_TOOLS_COMMIT"
COPY --chmod=755 entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
