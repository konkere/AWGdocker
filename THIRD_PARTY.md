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

The inventory generator reads every package in the runtime APK database before
installing build-only tools. It retrieves exact aports recipes from Alpine's
official GitHub mirror, <https://github.com/alpinelinux/aports>. The installed
package commit remains authoritative. Upstream URLs and license expressions
come from APK metadata; source URLs are expanded from that commit's APKBUILD.
Local sources and patches link to files at the same commit. The generator fails
on missing metadata, missing recipes or a recipe/package version mismatch.
It does not download or verify source distfiles, and does not guess missing data.

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
- `alpine/packages.json`: all actually installed Alpine runtime packages, including
  transitive dependencies, with versions, licenses, upstream URLs, exact aports
  commits, recipe URLs and all recipe source/patch URLs.
- `alpine/installed`: the original runtime APK database used for that inventory.
- `alpine/THIRD_PARTY.md` and `build/THIRD_PARTY.md`: this document with the full
  generated package table for this build and architecture.

The AmneziaWG archives remain inside the image. Alpine source archives are not
collected or included. Existing upstream license/copyright notices and the GPL
text are retained. The inventory identifies the AWGdocker source revision, Alpine
release, APK architectures and SHA-256 of the exact runtime database. CI checks
it against the built image and exports the generated document, inventory and
image identity as an artifact for each architecture; artifacts have finite retention.

You can extract sources without starting a tunnel or granting privileges:

```bash
export AWG_IMAGE='ghcr.io/konkere/awgdocker@sha256:REPLACE_WITH_DIGEST'
container=$(timeout 10 docker create "$AWG_IMAGE")
timeout 120 docker cp "$container:/usr/src/awg-docker" ./image-sources
timeout 10 docker rm "$container"
```

Sources and licenses for Go modules remain in the Go archive's `vendor` directory.
The repository copy of this document is a template, not a claim about a moving
Alpine tag. The complete table is generated into each image at build time, so
amd64 and arm64 builds can accurately document different package sets. Extract
`image-sources/build/THIRD_PARTY.md` using the command above to read that table.

## Alpine runtime packages (generated per image)

<!-- BEGIN ALPINE RUNTIME INVENTORY -->
Build an image to populate this section from its actual runtime APK database.
<!-- END ALPINE RUNTIME INVENTORY -->

## Redistribution

Keep these source bundles, copyright notices, license texts and modification
notices with redistributed images. If you publish a different binary, regenerate
the matching source bundles. Do not describe the whole image as MIT-only.
The independently executable programs are packaged together; the wrapper's MIT
license does not override the GPL or any other bundled license.

### Legal caveat for Alpine source links

Links to third-party upstream sources do **not necessarily satisfy GPLv2**.
GPLv2 section 3 requires a permitted corresponding-source distribution method;
a package inventory or a link to somebody else's server is not, by itself, a
guarantee of compliance or a written source offer. Distributors remain responsible
for complete matching sources, including applicable patches and build scripts,
and their availability under the relevant license. Removing Alpine source
archives is a packaging decision, not a legal compliance certification. Before
redistributing, arrange a source-provision method appropriate to the licenses
and distribution circumstances. See [GPLv2 section 3](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html#section3)
and the [GNU GPL FAQ](https://www.gnu.org/licenses/old-licenses/gpl-2.0-faq.html#SourceAndBinaryOnDifferentSites).
