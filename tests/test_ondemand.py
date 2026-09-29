import json
import tempfile
import unittest
from pathlib import Path

from src.ondemand import (
    SCHEMA_VERSION,
    _extract_function,
    _find_obligation,
    _strip_verification_annotations,
    _validate_analysis,
    _validate_reintegration,
    _write_session,
)


def analysis_fixture():
    return {
        "contract": {
            "pre_condition": "input is valid",
            "post_condition": "result preserves unrelated state",
            "failure_condition": "an error reports no success",
        },
        "abstraction": {
            "name": "SelectedState",
            "abstract_state": "the selected mapping",
            "projection": "project the selected address",
            "preserved_state": "all unrelated mappings",
            "hidden_representation": "page tables and allocator handles",
            "observation_boundary": "after the function returns",
        },
        "implementation_assessment": [
            {
                "claim": "the selected mapping is removed",
                "evidence": "the body calls unmap",
                "disposition": "unknown",
            }
        ],
        "obligations": [
            {
                "id": "O1",
                "title": "callee contract",
                "claim": "unmap preserves unrelated mappings",
                "why_blocking": "the caller delegates the mutation",
                "kind": "callee-contract",
                "suggested_callees": [
                    {
                        "symbol": "unmap",
                        "file_hint": "src/vmem.rs",
                        "reason": "it performs the mutation",
                    }
                ],
            }
        ],
        "candidate_variants": [
            {
                "name": "projection",
                "semantic_difference": "only selected state changes",
                "discriminator": "an unrelated mapping remains",
            },
            {
                "name": "orchestration",
                "semantic_difference": "only the call result is specified",
                "discriminator": "a callee may remove unrelated mappings",
            },
        ],
        "uncertainties": ["callee behavior is not shown"],
        "recommended_next_step": "expand unmap for O1",
    }


class OnDemandTests(unittest.TestCase):
    def test_extracts_only_selected_function(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            source = repo / "src/demo.rs"
            source.parent.mkdir()
            source.write_text(
                "impl Demo {\n"
                "    pub fn first(&self) -> bool { true }\n"
                "    pub fn second(&self) -> bool { false }\n"
                "}\n",
                encoding="utf-8",
            )
            extracted = _extract_function(repo, "src/demo.rs", "second")
            self.assertEqual(extracted["extracted_symbol"], "second")
            self.assertIn("false", extracted["source"])
            self.assertNotIn("true", extracted["source"])

    def test_analysis_validation_adds_open_status(self):
        analysis = _validate_analysis(analysis_fixture())
        self.assertEqual(analysis["obligations"][0]["status"], "open")

    def test_strips_verus_attributes_but_preserves_rust_attributes(self):
        source = (
            "#[inline]\n"
            "#[cfg_attr(target_arch = \"x86\", verus_verify(external_body))]\n"
            "#[cfg_attr(target_arch = \"x86\", verus_spec(result =>\n"
            "    ensures result,\n"
            "))]\n"
            "pub fn selected() -> bool { true }\n"
        )
        stripped = _strip_verification_annotations(source)
        self.assertIn("#[inline]", stripped)
        self.assertNotIn("verus_verify", stripped)
        self.assertNotIn("verus_spec", stripped)
        self.assertIn("pub fn selected", stripped)

    def test_find_obligation_is_exact(self):
        node = {"id": "root", "analysis": analysis_fixture()}
        self.assertEqual(_find_obligation(node, "O1")["title"], "callee contract")
        with self.assertRaises(ValueError):
            _find_obligation(node, "O2")

    def test_reintegration_validation(self):
        result = _validate_reintegration(
            {
                "disposition": "conditional",
                "rationale": "the child contract is plausible but unproved",
                "caller_effect": "the parent may consume it conditionally",
                "remaining_gap": "prove the child body",
                "proof_map_updates": ["mark O1 conditional"],
                "parent_contract_revision": None,
            }
        )
        self.assertEqual(result["disposition"], "conditional")

    def test_session_write_is_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            session = {
                "schema_version": SCHEMA_VERSION,
                "updated_at": "",
                "nodes": {},
                "edges": [],
            }
            _write_session(path, session)
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["schema_version"], SCHEMA_VERSION)
            self.assertTrue(loaded["updated_at"])


if __name__ == "__main__":
    unittest.main()
