# Licensing and corresponding source

The root [LICENSE](LICENSE) applies to original AWGdocker build scripts,
entrypoint, examples, tests, workflow and documentation, except for files with an
explicit different notice. It does not relicense the programs inside the image.

| Component | License and scope |
| --- | --- |
| Original AWGdocker files | MIT, except the GPL fragment below |
| `scripts/quick-userspace.bash` | GPL-2.0-only; inserted into upstream `awg-quick` |
| `amneziawg-go` | MIT; vendored dependencies keep their own licenses |
| `amneziawg-tools`, including the modified `awg-quick` | GPLv2; original copyright and SPDX notices are retained |
| Alpine runtime packages and their dependencies | Their individual upstream licenses, recorded in the bundled package inventory |

Official upstream projects:

- <https://github.com/amnezia-vpn/amneziawg-go>
- <https://github.com/amnezia-vpn/amneziawg-tools>
- <https://gitlab.alpinelinux.org/alpine/aports>

The collector fetches those same aports commits from Alpine's official GitHub
mirror, <https://github.com/alpinelinux/aports>, since the GitLab frontend can
reject unattended runner requests. The installed package commit remains authoritative.

The tools GPL text is included at `LICENSES/GPL-2.0-only.txt`. The installed
`awg-quick` remains GPL-covered as a whole, including our inserted override and
sysctl modification. Our changes force the userspace implementation and avoid
writing an already-set `src_valid_mark` in a read-only proc filesystem. The
modified script includes a change notice and date.

## What ships with every image

`/usr/share/licenses/amneziawg/` contains the selected upstream license texts.
`/usr/share/licenses/awg-docker/` contains the wrapper MIT and GPL texts.

`/usr/src/awg-docker/` contains:

- `amneziawg-go.tar.gz`: the selected complete Go source tree, including vendored
  module sources, notices and licenses. The executable is built from that vendor tree.
- `amneziawg-tools.tar.gz`: the complete selected upstream tools source tree.
- `modified/awg-quick`: the full modified Bash source, identical to the installed script.
- `build/`: the Dockerfile and wrapper sources used to build and install it.
- `versions.txt`: the component tags/commits and AWGdocker source revision.
- `alpine-sources.tar.gz`: the runtime package inventory, exact aports recipes and
  patches, and checksum-verified source distfiles for each package origin. Build-only
  packages used to collect these sources are not part of that runtime inventory.

The image build fails if a runtime package lacks an aports commit, its original
recipe cannot be found, or its source cannot be fetched and verified. These archives
are distributed inside the same image as the binaries, rather than relying on a
temporary Actions artifact or an upstream link remaining available. Source bundles
increase build time and image size.

You can extract sources without starting a tunnel or granting privileges:

```bash
export AWG_IMAGE='ghcr.io/konkere/awgdocker@sha256:REPLACE_WITH_DIGEST'
container=$(timeout 10 docker create "$AWG_IMAGE")
timeout 120 docker cp "$container:/usr/src/awg-docker" ./image-sources
timeout 10 docker rm "$container"
```

The exact runtime package versions and aports commits are in
`alpine-sources/packages.json` after unpacking `alpine-sources.tar.gz`. To rebuild
one Alpine package, use its bundled APKBUILD and patches with Alpine's `abuild`,
setting `SRCDEST` to that recipe's bundled `distfiles` directory. Kernel/compiler
toolchains are normal external build prerequisites. Sources and licenses for Go
modules are retained within the Go archive's `vendor` directory.

## Redistribution

Keep these source bundles, copyright notices, license texts and modification
notices with redistributed images. If you publish a different binary, regenerate
the matching source bundles. Do not describe the whole image as MIT-only.
The independently executable programs are packaged together; the wrapper's MIT
license does not override the GPL or any other bundled license.
