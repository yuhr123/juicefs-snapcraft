# juicefs-snapcraft

Build and publish the JuiceFS Snap package.

## Release flow

The `Snap Release Automation` GitHub Actions workflow checks the upstream
GitHub Latest Release every six hours. Scheduled runs validate and report the
candidate only. They do not update the recipe or publish to the Snap Store.

To publish a new stable upstream release, start the workflow manually from
`main` with `check_only=false` and leave `version_override` empty. The workflow
then:

1. validates the version, GitHub release, release baseline, and completion tags;
2. updates both `version` and `parts.juicefs.source-tag` in
   `snap/snapcraft.yaml` and pushes one release commit to `main`;
3. waits for the connected Snapcraft/Launchpad build service to publish matching
   `amd64` and `arm64` revisions to `latest/edge`;
4. installs the edge snap and checks `juicefs version`;
5. releases each verified revision explicitly to `latest/stable`;
6. verifies that stable points to the exact tested revisions; and
7. creates an `automation/released/vX.Y.Z` completion tag.

The workflow is resumable while the target remains upstream Latest. Until the
completion tag exists, rerun the manual workflow to continue that release whether
the recipe update, edge build, or one stable revision already completed. If a
newer release becomes Latest, a new manual run targets that newer release. A
scheduled run still only reports the release state.

The Snapcraft build service performs the builds. GitHub Actions coordinates the
release and does not build or upload `.snap` files itself.

## One-time configuration

### Snapcraft build service

Connect this public GitHub repository to the registered `juicefs` snap and
configure successful builds from `main` to release automatically to
`latest/edge`. Enable both architectures declared by `snap/snapcraft.yaml`:

- `amd64`
- `arm64`

Stable must not be an automatic build-service destination; the workflow
releases the tested revisions to stable.

### GitHub Environment

Create a GitHub Environment named `snapcraft-release` with:

- `main` as the only allowed deployment branch;
- an environment secret named `SNAPCRAFT_STORE_CREDENTIALS`.

If the Environment currently has required reviewers, migrate in this order:

1. Merge the workflow change that makes scheduled runs detection-only.
2. Confirm the merged workflow on `main` gates the release job to manual
   dispatch and forces scheduled runs into check-only mode.
3. Remove the Environment's required-reviewer rule. Keep the `main` deployment
   branch restriction and `SNAPCRAFT_STORE_CREDENTIALS` secret.

With that rule removed, a manually dispatched release runs through to the
completion tag without an Environment approval pause.

The workflow needs to push the recipe commit and completion tag. Ensure branch
protection permits GitHub Actions to make those narrowly scoped writes, or use a
repository ruleset bypass granted only to the GitHub Actions app.

### Snap Store credential

Generate a time-limited credential restricted to this snap and the release
operation:

```sh
snapcraft export-login \
  --snaps=juicefs \
  --channels=latest/edge,latest/stable \
  --acls=package_access,package_release \
  --expires=2027-07-01T00:00:00Z \
  snapcraft-login.txt
```

Store the complete file contents in the Environment secret. Verify the selected
ACLs with `snapcraft whoami` and rotate the credential before it expires.

## Operations

Use scheduled runs to see whether a new release is available. To publish it,
open **Actions → Snap Release Automation → Run workflow**, select `main`, set
`check_only=false`, and leave `version_override` empty. `workflow_dispatch`
also supports:

- `check_only=true` to validate detection without changing GitHub or the Store;
- `version_override=X.Y.Z` to inspect a specific version in check-only mode.

Real releases always use the `tag_name` from
`https://api.github.com/repos/juicedata/juicefs/releases/latest`; an override
cannot be used to publish. The response must be a non-draft, non-prerelease
release with a `vX.Y.Z` tag. GitHub's Latest designation determines the
candidate; the workflow does not select the numerically highest release.

If a run fails, fix the external condition and rerun it. Do not manually add the
completion tag. Common resumable states are:

- recipe updated while Launchpad is still building;
- only one edge architecture is available;
- edge passed but release of one stable revision failed; or
- stable is correct but the completion-tag push failed.

The build wait is limited to two hours and stable propagation to ten minutes.

## Local checks

Run unit tests with:

```sh
python3 -m pip install PyYAML==6.0.3
python3 -m unittest discover -s scripts -p '*_test.py' -v
```
