from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path

from codex_second_brain import __version__


ROOT = Path(__file__).resolve().parents[1]


class CapabilityContractTests(unittest.TestCase):
    def test_public_claims_match_package_version_and_artifacts(self) -> None:
        contract = json.loads((ROOT / "capability-contract.json").read_text(encoding="utf-8"))
        version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        self.assertEqual(contract["surfaces"]["public-package"]["version"], version)
        self.assertEqual(__version__, version)
        for capability, matrix in contract["capabilities"].items():
            claim = matrix["public-package"]
            if claim["state"] == "not-shipped":
                self.assertNotIn("artifact", claim, capability)
            else:
                self.assertTrue((ROOT / claim["artifact"]).is_file(), capability)

    def test_public_hardening_claims_are_verified_by_the_surface_suite(self) -> None:
        contract = json.loads((ROOT / "capability-contract.json").read_text(encoding="utf-8"))
        states = {
            capability: matrix["public-package"]["state"]
            for capability, matrix in contract["capabilities"].items()
        }
        self.assertTrue(states)
        self.assertEqual(set(states.values()), {"verified-working"})


if __name__ == "__main__":
    unittest.main()
