from __future__ import annotations

import unittest

from scripts import snap_store


def payload(version="1.4.2", edge=(35, 36), stable=(33, 34)):
    entries = []
    for risk, revisions in (("edge", edge), ("stable", stable)):
        for architecture, revision in zip(("amd64", "arm64"), revisions):
            entries.append(
                {
                    "channel": {
                        "track": "latest",
                        "risk": risk,
                        "architecture": architecture,
                    },
                    "version": version,
                    "revision": revision,
                    "download": {"sha3-384": f"sha-{revision}"},
                }
            )
    return {"channel-map": entries}


class SnapStoreTest(unittest.TestCase):
    def test_selects_exact_edge_build_set(self):
        selected = snap_store.select_revisions(
            payload(), "1.4.2", "edge", ["amd64", "arm64"]
        )
        self.assertEqual(selected["amd64"].revision, 35)
        self.assertEqual(selected["arm64"].revision, 36)

    def test_wait_retries_until_both_architectures_exist(self):
        responses = iter(
            [
                {
                    "channel-map": [
                        entry
                        for entry in payload()["channel-map"]
                        if entry["channel"]["risk"] == "edge"
                        and entry["channel"]["architecture"] == "amd64"
                    ]
                },
                payload(),
            ]
        )
        selected = snap_store.wait_for_revisions(
            "1.4.2",
            "edge",
            ["amd64", "arm64"],
            {},
            timeout=10,
            interval=0,
            fetcher=lambda: next(responses),
            sleeper=lambda _: None,
        )
        self.assertEqual(set(selected), {"amd64", "arm64"})

    def test_expected_revisions_prevent_wrong_stable_build_set(self):
        responses = iter([payload(), payload(stable=(35, 36))])
        selected = snap_store.wait_for_revisions(
            "1.4.2",
            "stable",
            ["amd64", "arm64"],
            {"amd64": 35, "arm64": 36},
            timeout=10,
            interval=0,
            fetcher=lambda: next(responses),
            sleeper=lambda _: None,
        )
        self.assertEqual(selected["arm64"].revision, 36)

    def test_parse_expected_revisions(self):
        self.assertEqual(
            snap_store.parse_expected(["amd64=35", "arm64=36"]),
            {"amd64": 35, "arm64": 36},
        )

    def test_wait_retries_transient_store_error(self):
        responses = iter([snap_store.StoreError("temporary"), payload()])

        def fetcher():
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response

        selected = snap_store.wait_for_revisions(
            "1.4.2",
            "edge",
            ["amd64", "arm64"],
            {},
            timeout=10,
            interval=0,
            fetcher=fetcher,
            sleeper=lambda _: None,
        )
        self.assertEqual(set(selected), {"amd64", "arm64"})

    def test_rejects_expected_revision_for_unrequested_architecture(self):
        with self.assertRaisesRegex(snap_store.StoreError, "unrequested"):
            snap_store.wait_for_revisions(
                "1.4.2",
                "edge",
                ["amd64"],
                {"arm64": 36},
                timeout=0,
                interval=0,
                fetcher=payload,
            )


if __name__ == "__main__":
    unittest.main()
