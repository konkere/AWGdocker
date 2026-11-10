# AWGdocker

[Русская версия](README.ru.md)

One userspace AmneziaWG image for both peers. The configuration determines the role.
A multi-platform manifest serves linux/amd64 and linux/arm64.

This repository contains generic examples only. Example tunnel addresses
10.203.0.1/32 and 10.203.0.2/32 are arbitrary; replace them if they overlap
your networks. No router, LAN gateway, NAT, or internet-exit configuration is included.

## Build policy

- GitHub Actions checks numeric stable Git tags of both official upstream repositories
  daily at 04:23 UTC.
- Releases are not the sole source: amneziawg-go publishes tags without GitHub Releases.
- A changed tag or the commit behind it triggers a build. A source change on main
  and a manual workflow run also build. Scheduled runs skip unchanged inputs on
  every day of the week; there are no mandatory periodic rebuilds.
- Tags are resolved once to exact commit IDs before the architecture jobs start.
  Both jobs build those same commits, not a moving branch.
- Each architecture runs an AWG-to-AWG handshake, bidirectional ping,
  default-route/read-only-sysctl test and graceful-stop check.
- Only successful builds of both architectures promote the shared latest manifest.
  Architecture candidate tags may remain if a later job fails.
- Publishing is restricted to main. A manual run from another branch builds and
  tests without pushing candidate tags or changing latest.
- Build tags (build-RUN_ID-ATTEMPT) identify one publication; use the manifest digest
  for deployment. latest is a convenience alias, not a compatibility guarantee.
- Nothing logs into deployment hosts or installs updates automatically.
- A daily schedule in a public repo can be disabled by GitHub after 60 days
  without repository activity. Monitor workflow runs and re-enable it if needed.
- An upstream release in another repository does not directly trigger this workflow.
  External repository_dispatch or a GitHub App is optional; scheduled polling needs neither.

The workflow publishes to `ghcr.io/konkere/awgdocker`. Check the latest successful
[Actions run](https://github.com/konkere/AWGdocker/actions/workflows/build.yml)
for the common manifest digest before installing a build. Local checks do not
replace a successful run of the published workflow.

## Requirements and checkout

Both hosts need Linux (amd64 or arm64), Docker Engine with Compose v2, and
`/dev/net/tun`. Containers need `NET_ADMIN`, but not `privileged: true`.
The server must be reachable on its chosen UDP port. Key generation additionally
needs Bash and a trusted machine with Docker; local building needs Git and Python 3.

```bash
timeout 120 git clone https://github.com/konkere/AWGdocker.git
cd AWGdocker
```

No SSH credentials or deployment hosts are configured in Actions. New GHCR packages
may initially be private even for public repositories: the owner must make the
package public for anonymous pulls, or provide authorized registry access.

Offline regression checks (Python standard library and Bash only):

    python3 -m unittest discover -s tests -v

## Local build

Requires Docker/BuildKit, Python 3, Git, and internet access:

    bash scripts/build-local.sh

This selects the newest stable tags automatically and writes upstream.json.
To build where the Docker bridge cannot access the network:

    BUILD_NETWORK=host bash scripts/build-local.sh

Use `IMAGE=amneziawg:candidate bash scripts/build-local.sh` for a different local tag.
Builds also fetch and bundle the corresponding sources for distributed software;
allow extra time, disk space and network access to Alpine's source servers.

The Dockerfile accepts AWG_GO_COMMIT and AWG_TOOLS_COMMIT, not permanent version
defaults. upstream.json and OCI labels record the resolved versions.
AWG_GO_TAG/AWG_TOOLS_TAG are only metadata supplied by the resolver.

Base image tags are intentionally refreshed with --pull. Exact byte-for-byte
rebuilding additionally requires base digests and package/dependency snapshots.
Keep the published manifest digest and build record; resolving the same AWG commits
alone does not reproduce all operating-system packages.

## First setup: AWG to AWG only

1. Choose a successful multi-platform build digest. Set AWG_IMAGE to that reference,
   e.g. ghcr.io/OWNER/REPOSITORY@sha256:DIGEST (replace all placeholders; lower-case path).
   For a local build use amneziawg:local.
2. On a trusted machine generate a new peer pair. Replace the documentation-only
   endpoint 203.0.113.10 with your server address:

       export AWG_IMAGE='ghcr.io/OWNER/REPOSITORY@sha256:DIGEST'
       export ENDPOINT='203.0.113.10:443'
       timeout 300 docker pull "$AWG_IMAGE"
       bash scripts/generate-example.sh

3. Copy private-configs/server/awg0.conf to a private server deployment directory,
   and the client file to a private client directory. Use an encrypted transfer.
   Each file must be mode 600. Never post their contents in logs or issues.
   The generator requires a new output directory and refuses to reuse one.
   For a second pair use `bash scripts/generate-example.sh ./another-private-pair`.
4. Copy examples/server.compose.yml as compose.yml beside the server file,
   and examples/client.compose.yml beside the client file.
   Put AWG_IMAGE=the-selected-reference in each .env. UDP/443 must be available
   on the server; /dev/net/tun and Docker Compose must be available on both hosts.
   For example, inside each private deployment directory:

       umask 077
       printf '%s\n' 'AWG_IMAGE=ghcr.io/konkere/awgdocker@sha256:REPLACE_WITH_DIGEST' > .env
       chmod 600 awg0.conf .env
5. Run in each deployment directory, server first:

       unset AWG_IMAGE
       timeout 10 docker compose config -q
       timeout 300 docker compose pull awg
       timeout 90 docker compose up -d --no-build --pull never awg

6. On the client:

       timeout 10 docker exec awg-client ping -c3 -W2 10.203.0.1
       timeout 10 docker exec awg-client awg show awg0 latest-handshakes

   On the server:

       timeout 10 docker exec awg-server ping -c3 -W2 10.203.0.2

The example only connects the two tunnel addresses; it does not send host or LAN
traffic through the tunnel. The server bridge publishes UDP/443.
TCP/443 is independent, but an HTTP/3 listener also needs UDP/443 and would conflict.
The generator listens on port 443 inside the server container. If ENDPOINT uses a
different public port, set the server Compose mapping to "PUBLIC_PORT:443/udp".
The basic setup omits optional I1/RandomTrailers/padding features; CI tests a
basic fixture and a separate advanced fixture on both architectures.
Add tuning only after the basic link works.

For a locally built image, skip registry pull and run with --pull never.
The local image must exist for each host's architecture. Shell-exported AWG_IMAGE
overrides .env and --env-file; unset it before using Compose with those files.

## Manual update and rollback

Read upstream changes and keep both peers on the same selected build.
A successful new-to-new CI test does not prove compatibility with an older peer.

Before changing the running service:

- Save compose.yml, .env and awg0.conf privately (including their permissions).
- Read the running container's .Image ID, tag it as awg-rollback:TIMESTAMP,
  and keep or export that image. Save the old .env separately.
- Prepare .env.next from .env, changing only AWG_IMAGE to the new manifest digest.
- Unset exported AWG_IMAGE, then verify config --images selects the intended reference.
- Run docker compose --env-file .env.next config -q.
- Pull with docker compose --env-file .env.next pull awg on both hosts first.
  A pull alone does not update a running container.
- If the release changes the protocol or config format, arrange a paired switch
  with independent access to both hosts.

Install .env.next as .env, then run, server first and client second:

    timeout 90 docker compose up -d --no-build --pull never awg

Check fresh handshakes and bidirectional ping. Keep the previous images until
the new pair is stable. If it fails, set AWG_IMAGE to the saved local rollback tag
on each host, and repeat up with --pull never. Restore the previous configuration
too if it was changed: stop the running container BEFORE restoring its config, so
its shutdown hooks still see the old settings. Then restore the config and run
up -d --force-recreate --no-build --pull never awg to refresh bind mounts as well.
Do not use docker compose restart to apply an image update.

## Notes

No kernel module is required: a checked upstream function override forces
amneziawg-go even if a kernel module is available on the host.
A controlled patch avoids writing src_valid_mark if Compose already set it to 1.
If upstream changes that statement, the image build fails for review.

The entrypoint takes a private startup copy of the config and uses the same copy
for down. A failed cleanup exits nonzero; CI checks that down hooks run on both peers.
This does not guarantee cleanup after SIGKILL, host failure, daemon crash or a
partially failed PostUp. With host networking, inspect residual interface/routes
and hook rules before retrying; do not repeatedly restart into non-idempotent hooks.

Do not use bare awg show, showconf or dump in public diagnostics: versions with
header protection may print the shared HeaderProtectionKey. Use selected fields
such as latest-handshakes and transfer. Do not enable shell tracing around key generation.

## License and source code

Original wrapper files use [MIT](LICENSE), with the explicit exception of the
GPL-2.0-only function fragment inserted into `awg-quick`. `amneziawg-go` uses MIT;
`amneziawg-tools` and the modified `awg-quick` retain GPLv2. The entire image is
not licensed as MIT. Other bundled packages retain their individual licenses.

Every image includes corresponding source archives, the complete modified
`awg-quick`, build scripts, component commits and license notices. See
[THIRD_PARTY.md](THIRD_PARTY.md) for the scope and extraction commands.
