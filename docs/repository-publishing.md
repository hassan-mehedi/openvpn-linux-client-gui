# Repository Publishing Plan

This project can already build and publish GitHub release artifacts
automatically. The remaining work for native package-manager upgrades is to
publish those builds through package repositories that users can add once and
then upgrade with normal Linux tooling.

## Goal

After this rollout:

- Debian and Ubuntu users install from your signed APT repository and upgrade
  with `apt update && apt upgrade`
- Fedora users install from your COPR project and upgrade with `dnf update`
- GNOME Software, KDE Discover, and other software centers can surface the app
  more naturally because the package now ships AppStream metainfo

## Recommended Rollout

### 1. Keep GitHub Releases as the source build pipeline

The current automation on `main` already gives you:

- source tarballs
- Python wheels
- DEB artifacts
- RPM artifacts

Keep that as the canonical build step. Repository publishing should consume the
packaged artifacts or the same packaging metadata, not rebuild the project with
different logic.

### 2. Fedora first: publish with COPR

Fedora is the easier native update path because COPR already provides the
repository hosting and metadata.

Suggested setup:

1. Create a COPR project named `openvpn3-client-linux`.
2. Point the project at your RPM packaging source.
3. Configure GitHub Actions to trigger a COPR build after a stable GitHub
   release or version tag.
4. Tell Fedora users to enable the repo once:

   ```bash
   sudo dnf copr enable <owner>/openvpn3-client-linux
   sudo dnf install openvpn3-client-linux
   ```

After that, updates arrive through normal `dnf update` flows.

### 3. Debian and Ubuntu: publish a signed APT repository

For Debian-family systems, package-manager updates require a repository in
`sources.list`. The simplest durable shape is:

- signed repository metadata
- hosted over HTTPS
- release packages copied from stable builds only

Practical implementation options:

- GitHub Pages or another static host for the repository contents
- repository generation with `aptly` or `reprepro`
- a dedicated signing key stored as GitHub Actions secrets

Suggested install flow:

```bash
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://<your-domain>/openvpn3-client-linux.asc | sudo tee /etc/apt/keyrings/openvpn3-client-linux.asc >/dev/null
echo "deb [signed-by=/etc/apt/keyrings/openvpn3-client-linux.asc] https://<your-domain>/apt stable main" | sudo tee /etc/apt/sources.list.d/openvpn3-client-linux.list >/dev/null
sudo apt update
sudo apt install openvpn3-client-linux
```

After that, the package upgrades through normal `apt` flows.

## GitHub Actions Shape

Repository publishing should be split from the snapshot workflow:

- `ci.yml`:
  test and package smoke checks
- `release-main.yml`:
  automatic prerelease artifacts for every merge to `main`
- `release-stable.yml`:
  publish signed stable releases on version tags such as `v0.2.0`
- future repository workflow:
  consume stable artifacts and publish them into COPR and APT

This separation matters because package repositories should generally receive
curated stable builds, not every snapshot from `main`.

## Secrets And Variables You Will Need

For COPR:

- COPR API token or config
- COPR owner name
- COPR project name

For APT:

- GPG private key for repository signing
- GPG passphrase if the key uses one
- host credentials or GitHub Pages deployment credentials
- repository base URL

## AppStream Impact

The package now ships:

- `/usr/share/metainfo/com.openvpn3.clientlinux.metainfo.xml`

That enables software centers to render:

- app name and summary
- long description
- homepage and issue tracker links
- release notes from the `<releases>` section

This improves update visibility, but it does not replace repository
distribution. Software centers still need APT or RPM repository metadata to
learn that a newer version exists.

## Suggested Order Of Execution

1. Keep snapshot prereleases on `main` as they are now.
2. Use the stable tag-based release workflow for versions you want users to
   upgrade to.
3. Publish a Fedora COPR project.
4. Publish a signed APT repository.
5. Update `install.sh` so it adds the right repository and installs the package
   from there instead of downloading GitHub release assets directly.
