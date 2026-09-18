//! Renderer-neutral diff and patch-review data contract.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashSet;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DiffLineKind { Context, Added, Removed }

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DiffLine {
    pub kind: DiffLineKind,
    pub old_line: Option<u32>,
    pub new_line: Option<u32>,
    pub text: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DiffHunk {
    pub hunk_id: String,
    pub old_start: u32,
    pub old_count: u32,
    pub new_start: u32,
    pub new_count: u32,
    pub collapsed: bool,
    pub lines: Vec<DiffLine>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DiffStatus { Preview, Applying, Applied, Conflict, Rejected }

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DiffLayout { Inline, TwoColumn }

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DiffFrame {
    pub document_id: String,
    pub base_revision: u64,
    pub patch_revision: u64,
    pub epoch: u64,
    pub layout: DiffLayout,
    pub status: DiffStatus,
    pub hunks: Vec<DiffHunk>,
}

impl DiffFrame {
    pub fn validate(&self) -> Result<(), String> {
        if self.document_id.trim().is_empty() { return Err("document_id must be non-empty".into()); }
        if self.patch_revision == 0 { return Err("patch_revision must be greater than zero".into()); }
        let mut ids = HashSet::new();
        for hunk in &self.hunks {
            if hunk.hunk_id.trim().is_empty() || !ids.insert(&hunk.hunk_id) { return Err("hunk IDs must be non-empty and unique".into()); }
            let mut old_count = 0;
            let mut new_count = 0;
            for line in &hunk.lines {
                if line.text.len() > 64 * 1024 { return Err("diff line exceeds 64 KiB".into()); }
                match line.kind { DiffLineKind::Context => { old_count += 1; new_count += 1; }, DiffLineKind::Added => new_count += 1, DiffLineKind::Removed => old_count += 1 }
            }
            if old_count != hunk.old_count || new_count != hunk.new_count { return Err(format!("hunk {} line counts do not match", hunk.hunk_id)); }
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum DiffIntent {
    AcceptHunk { document_id: String, base_revision: u64, patch_revision: u64, epoch: u64, hunk_id: String },
    RejectHunk { document_id: String, base_revision: u64, patch_revision: u64, epoch: u64, hunk_id: String },
    AcceptPatch { document_id: String, base_revision: u64, patch_revision: u64, epoch: u64 },
    RejectPatch { document_id: String, base_revision: u64, patch_revision: u64, epoch: u64 },
}

impl DiffIntent {
    pub fn name(&self) -> &'static str {
        match self { Self::AcceptHunk { .. } => "diff.hunk.accept", Self::RejectHunk { .. } => "diff.hunk.reject", Self::AcceptPatch { .. } => "diff.patch.accept", Self::RejectPatch { .. } => "diff.patch.reject" }
    }

    pub fn payload(&self) -> Value {
        match self {
            Self::AcceptHunk { document_id, base_revision, patch_revision, epoch, hunk_id } | Self::RejectHunk { document_id, base_revision, patch_revision, epoch, hunk_id } => serde_json::json!({"document_id":document_id,"base_revision":base_revision,"patch_revision":patch_revision,"epoch":epoch,"hunk_id":hunk_id}),
            Self::AcceptPatch { document_id, base_revision, patch_revision, epoch } | Self::RejectPatch { document_id, base_revision, patch_revision, epoch } => serde_json::json!({"document_id":document_id,"base_revision":base_revision,"patch_revision":patch_revision,"epoch":epoch}),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn diff_frame_validates_line_counts() {
        let mut frame = DiffFrame { document_id: "doc-1".into(), base_revision: 4, patch_revision: 5, epoch: 2, layout: DiffLayout::Inline, status: DiffStatus::Preview, hunks: vec![DiffHunk { hunk_id: "h1".into(), old_start: 1, old_count: 1, new_start: 1, new_count: 2, collapsed: false, lines: vec![DiffLine { kind: DiffLineKind::Context, old_line: Some(1), new_line: Some(1), text: "old".into() }, DiffLine { kind: DiffLineKind::Added, old_line: None, new_line: Some(2), text: "new".into() }] }] };
        assert!(frame.validate().is_ok());
        frame.hunks[0].new_count = 1;
        assert!(frame.validate().is_err());
    }
}
