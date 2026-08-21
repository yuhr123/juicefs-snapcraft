# juicefs-snapcraft

Build and publish the JuiceFS Snap package.

## Automated release flow

The `Snap Release Automation` GitHub Actions workflow checks the authoritative
JuiceFS version endpoint every six hours. For a new stable upstream release it:

1. validates the version, GitHub release, release baseline, and completion tags;
2. updates both `version` and `parts.juicefs.source-tag` in
   `snap/snapcraft.yaml` and pushes one release commit to `main`;
3. waits for the connected Snapcraft/Launchpad build service to publish matching
   `amd64` and `arm64` revisions to `latest/edge`;
4. installs the edge snap and checks `juicefs version`;
5. promotes the complete edge build set to `latest/stable`;
6. verifies that stable points to the exact tested revisions; and
7. creates an `automation/released/vX.Y.Z` completion tag.

The workflow is resumable. Until the completion tag exists, a later scheduled
or manual run continues the same release whether the recipe update, edge build,
or stable promotion already completed.

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
promotes the tested edge build set.

### GitHub Environment

Create a GitHub Environment named `snapcraft-release` with:

- `main` as the only allowed deployment branch;
- a required reviewer while releases still need human approval; and
- an environment secret named `SNAPCRAFT_STORE_CREDENTIALS`.

The release job starts only after the Environment approval. After a successful
supervised release, remove the required-reviewer rule to make scheduled releases
unattended. Keep the branch restriction and secret.

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
ACLs with `snapcraft whoami` and rotate the credential before it expires. If the
Store requires an additional ACL for `snapcraft promote`, add only that ACL
rather than issuing an unrestricted credential.

## Operations

The scheduled workflow is the normal entry point. `workflow_dispatch` also
supports:

- `check_only=true` to validate detection without changing GitHub or the Store;
- `version_override=X.Y.Z` to inspect a specific version in check-only mode.

Real releases always use
`https://d.juicefs.com/juicefs/releases/latest-version.txt`; an override cannot
be used to publish.

If a run fails, fix the external condition and rerun it. Do not manually add the
completion tag. Common resumable states are:

- recipe updated while Launchpad is still building;
- only one edge architecture is available;
- edge passed but stable promotion failed; or
- stable is correct but the completion-tag push failed.

The build wait is limited to two hours and stable propagation to ten minutes.

## Local checks

Run unit tests with:

```sh
python3 -m unittest discover -s scripts -p '*_test.py' -v
```
