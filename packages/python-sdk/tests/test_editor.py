"""Editor document API contract tests (editor-runtime, v0.2.10+)."""

from __future__ import annotations

import unittest

from neon3_sdk import (
    EDITOR_CHANGE_COMMIT,
    EDITOR_CHANGE_DRAFT,
    EDITOR_LANGUAGE_NUI_FLOW,
    COMPLETION_AUTOMATIC,
    COMPLETION_INVOKED,
    COMPLETION_TRIGGER_CHARACTER,
    MAX_CHANGESET_OPS,
    MAX_INSERT_BYTES,
    ChangeSet,
    EditOp,
    EditorChangeKind,
    EditorClient,
    EditorCompletionResult,
    EditorOpenResult,
    EditorOperationResult,
    EditorPosition,
    EditorSelection,
    EditorSnapshot,
    ShaderPackage,
    ShaderParameter,
    shader_source_digest,
)
from neon3_sdk.constants import event_name, method, service


class EditorWireShapeTests(unittest.TestCase):
    def test_edit_op_wire_shape_matches_runtime_serde(self) -> None:
        insert = EditOp.insert(3, 7, EditorPosition(3, 12), "hello")
        self.assertEqual(
            insert.to_wire(),
            {"kind": "insert", "line": 3, "column": 7, "end": {"line": 3, "column": 12}, "text": "hello"},
        )
        delete = EditOp.delete(EditorPosition(3, 7), EditorPosition(3, 12), "hello")
        self.assertEqual(
            delete.to_wire(),
            {"kind": "delete", "start": {"line": 3, "column": 7}, "end": {"line": 3, "column": 12}, "text": "hello"},
        )
        with self.assertRaises(ValueError):
            EditOp("bogus", "x").to_wire()

    def test_change_set_validation_matches_runtime_limits(self) -> None:
        valid = ChangeSet(4, (EditOp.insert(0, 0, EditorPosition(0, 1), "x"),))
        self.assertEqual(valid.to_wire(), {"base_revision": 4, "ops": [EditOp.insert(0, 0, EditorPosition(0, 1), "x").to_wire()]})
        with self.assertRaises(ValueError):
            ChangeSet(0, ()).validate()
        overflow = ChangeSet(0, tuple(EditOp.insert(i, 0, EditorPosition(0, 1), "x") for i in range(MAX_CHANGESET_OPS + 1)))
        with self.assertRaises(ValueError):
            overflow.validate()
        big = ChangeSet(0, (EditOp.insert(0, 0, EditorPosition(0, 1), "x" * (MAX_INSERT_BYTES + 1)),))
        with self.assertRaises(ValueError):
            big.validate()

    def test_result_decoders_accept_runtime_shapes(self) -> None:
        snapshot_payload = {
            "document_id": "doc-1", "session_id": "sess-1", "language": "nui_flow",
            "epoch": 2, "revision": 9, "committed_revision": 8, "dirty": True,
            "line_count": 12, "byte_length": 340, "source_hash": "abc", "source": "flow",
            "diagnostics": [],
        }
        snapshot = EditorSnapshot.from_wire(snapshot_payload)
        self.assertEqual(snapshot.revision, 9)
        self.assertTrue(snapshot.dirty)

        opened = EditorOpenResult.from_wire({"state": "opened", "snapshot": snapshot_payload})
        self.assertIsNotNone(opened.snapshot)
        already = EditorOpenResult.from_wire({"state": "already_open"})
        self.assertIsNone(already.snapshot)

        operation = EditorOperationResult.from_wire({
            "state": "draft", "snapshot": snapshot_payload, "applied_ops": 2,
            "cursor": {"line": 1, "column": 1},
            "selection": {"anchor": {"line": 0, "column": 0}, "active": {"line": 1, "column": 1}},
        })
        self.assertEqual(operation.applied_ops, 2)
        self.assertEqual(operation.cursor, EditorPosition(1, 1))
        self.assertEqual(operation.selection, EditorSelection(EditorPosition(0, 0), EditorPosition(1, 1)))

        completion = EditorCompletionResult.from_wire({
            "document_id": "doc-1", "document_revision": 9, "position": {"line": 0, "column": 3},
            "items": [{
                "item_id": "k1", "label": "machine", "insert_text": "machine",
                "replace_start": {"line": 0, "column": 0}, "replace_end": {"line": 0, "column": 3},
                "kind": "keyword", "detail": "NUI keyword", "sort_text": "0machine",
                "source": "grammar", "commit_characters": [" ", "\n"],
            }],
        })
        self.assertEqual(completion.items[0].commit_characters, (" ", "\n"))

    def test_wire_constants_and_kinds_are_stable(self) -> None:
        self.assertEqual(service.EDITOR_RUNTIME, "editor-runtime")
        self.assertEqual(method.EDITOR_DOCUMENT_OPEN, "editor.document.open")
        self.assertEqual(method.EDITOR_DOCUMENT_SNAPSHOT_GET, "editor.document.snapshot.get")
        self.assertEqual(method.EDITOR_DOCUMENT_CHANGE_APPLY, "editor.document.change.apply")
        self.assertEqual(method.EDITOR_DOCUMENT_CHANGE_COMMIT, "editor.document.change.commit")
        self.assertEqual(method.EDITOR_COMPLETION_REQUEST, "editor.completion.request")
        self.assertEqual(method.EDITOR_DOCUMENT_CLOSE, "editor.document.close")
        self.assertEqual(method.WGPU_SHADER_REGISTER, "wgpu.shader.register")
        self.assertEqual(method.WGPU_SHADER_STATE, "wgpu.shader.state")
        self.assertEqual(event_name.DOCUMENT_COMMIT, "document_commit")
        self.assertEqual(EDITOR_CHANGE_DRAFT.as_wire(), "draft")
        self.assertEqual(EDITOR_CHANGE_COMMIT.as_wire(), "commit")
        self.assertEqual(COMPLETION_AUTOMATIC.as_wire(), "automatic")
        self.assertEqual(COMPLETION_INVOKED.as_wire(), "invoked")
        self.assertEqual(COMPLETION_TRIGGER_CHARACTER.as_wire(), "trigger_character")
        self.assertEqual(EDITOR_LANGUAGE_NUI_FLOW, "nui_flow")

    def test_editor_client_validates_identity_and_language_locally(self) -> None:
        client = EditorClient.__new__(EditorClient)  # no connection needed for local validation
        client.client = None  # type: ignore[assignment]
        client.target = "editor-runtime"
        with self.assertRaises(ValueError):
            client.open("", "sess", "flow")
        with self.assertRaises(ValueError):
            client.open("doc", " ", "flow")
        with self.assertRaises(ValueError):
            client.open("doc", "sess", "flow", language="typescript")


class ShaderPackageTests(unittest.TestCase):
    def test_shader_source_digest_matches_fnv1a64(self) -> None:
        self.assertEqual(shader_source_digest(b"A"), "af63fc4c860222ec")
        self.assertEqual(shader_source_digest("A"), "af63fc4c860222ec")
        self.assertNotEqual(shader_source_digest("a"), shader_source_digest("b"))

    def test_shader_package_wire_shape(self) -> None:
        package = ShaderPackage(
            package_id="pulse-neon-text",
            version=1,
            entry_point="text_material",
            fallback="standard_text",
            source_text="fn f() {}",
            parameters=(ShaderParameter("speed", "f32", 2.0, (0.0, 10.0)),),
        )
        wire = package.to_wire()
        self.assertEqual(wire["package_id"], "pulse-neon-text")
        self.assertEqual(wire["source_digest"], shader_source_digest("fn f() {}"))
        self.assertEqual(wire["source_bytes"], list(b"fn f() {}"))
        self.assertEqual(wire["parameters"][0]["kind"], "f32")
        self.assertEqual(wire["parameters"][0]["default_value"], 2.0)

    def test_shader_package_rejects_empty_source(self) -> None:
        package = ShaderPackage("x", 1, "text_material", "standard_text", source_text="")
        with self.assertRaises(ValueError):
            package.to_wire()


if __name__ == "__main__":
    unittest.main()
