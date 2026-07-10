# juicefs-snapcraft

Build snap package for JuiceFS

## Release workflow

The Snap Store is connected to this public repository. With automatic builds
enabled, changes merged into the default branch are built by the
Snapcraft/Launchpad build service for `amd64` and `arm64`, and successful builds
are published to `latest/edge`.

To release a new JuiceFS version:

1. Update both `version` and `parts.juicefs.source-tag` in
   `snap/snapcraft.yaml`.
2. Merge the change into the default branch.
3. Confirm that the automatic Snapcraft build started. If automatic builds are
   disabled, request the build from the Snapcraft Builds page.
4. Wait for the Snapcraft builds for both architectures to finish.
5. Install and verify the edge build:

   ```sh
   sudo snap refresh juicefs --channel=latest/edge
   juicefs version
   ```

6. In GitHub Actions, run **Promote Snap to stable** and enter the version
   without the leading `v` (for example, `1.4.0`).
7. Approve the `snapcraft-stable` environment deployment. The workflow checks
   that both edge architectures have the requested version, then promotes the
   complete edge build set to `latest/stable`.

### One-time GitHub setup

Create a GitHub environment named `snapcraft-stable`, configure its required
reviewers, restrict its deployment branches to the protected `main` branch,
and add an environment secret named
`SNAPCRAFT_STORE_CREDENTIALS`.

Generate a time-limited, snap-specific credential with Snapcraft:

```sh
snapcraft export-login \
  --snaps=juicefs \
  --channels=latest/edge,latest/stable \
  --acls=package_access,package_release \
  --expires=2027-07-01T00:00:00Z \
  snapcraft-login.txt
```

Store the complete contents of `snapcraft-login.txt` in the environment secret.
Do not commit the credentials file. Rotate it before its expiry date.

The promotion workflow uses `snapcraft promote`, which promotes the current
multi-architecture build set from edge to stable in one operation. Manual
per-architecture promotion in the Snap Store is no longer necessary.
