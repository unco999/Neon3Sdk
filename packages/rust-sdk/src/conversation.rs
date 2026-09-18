//! Bounded streaming conversation contract for Agents message lists.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashSet;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MessageRole { User, Assistant, Tool, System }

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MessageState { Streaming, Completed, Failed, Cancelled }

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MessageSegment {
    pub kind: String,
    pub text: String,
    #[serde(default)]
    pub metadata: Value,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConversationMessage {
    pub message_id: String,
    pub sequence: u64,
    pub role: MessageRole,
    pub state: MessageState,
    pub segments: Vec<MessageSegment>,
    #[serde(default)]
    pub metadata: Value,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ConversationDiagnosticKind { SequenceGap, Overflow, EpochChanged }

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConversationDiagnostic {
    pub kind: ConversationDiagnosticKind,
    pub expected_sequence: Option<u64>,
    pub received_sequence: Option<u64>,
    pub message: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct ConversationWindow { pub offset: u32, pub limit: u32 }

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConversationFrame {
    pub conversation_id: String,
    pub session_id: String,
    pub revision: u64,
    pub epoch: u64,
    pub first_sequence: u64,
    pub last_sequence: u64,
    pub window: ConversationWindow,
    pub tail_follow: bool,
    pub messages: Vec<ConversationMessage>,
    #[serde(default)]
    pub diagnostics: Vec<ConversationDiagnostic>,
}

impl ConversationFrame {
    pub fn validate(&self) -> Result<(), String> {
        if self.conversation_id.trim().is_empty() || self.session_id.trim().is_empty() { return Err("conversation_id and session_id are required".into()); }
        if self.window.limit == 0 || self.messages.len() > self.window.limit as usize { return Err("conversation frame exceeds window limit".into()); }
        let mut ids = HashSet::new();
        for message in &self.messages {
            if message.message_id.trim().is_empty() || !ids.insert(&message.message_id) { return Err("message IDs must be unique and non-empty".into()); }
            if message.sequence < self.first_sequence || message.sequence > self.last_sequence { return Err("message sequence is outside frame range".into()); }
            for segment in &message.segments { if segment.text.len() > 256 * 1024 { return Err("message segment exceeds 256 KiB".into()); } }
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct ConversationChunk { pub epoch: u64, pub sequence: u64, pub message_id: String, pub text: String, pub final_chunk: bool }

#[derive(Debug, Clone, PartialEq)]
pub enum ChunkResult { Applied, Duplicate, Gap(ConversationDiagnostic) }

#[derive(Debug, Clone)]
pub struct ConversationStream { pub epoch: u64, pub next_sequence: u64 }

impl ConversationStream {
    pub fn new(epoch: u64, next_sequence: u64) -> Self { Self { epoch, next_sequence } }

    pub fn apply(&mut self, chunk: &ConversationChunk) -> ChunkResult {
        if chunk.epoch != self.epoch { return ChunkResult::Gap(ConversationDiagnostic { kind: ConversationDiagnosticKind::EpochChanged, expected_sequence: Some(self.next_sequence), received_sequence: Some(chunk.sequence), message: "conversation epoch changed".into() }); }
        if chunk.sequence < self.next_sequence { return ChunkResult::Duplicate; }
        if chunk.sequence > self.next_sequence { return ChunkResult::Gap(ConversationDiagnostic { kind: ConversationDiagnosticKind::SequenceGap, expected_sequence: Some(self.next_sequence), received_sequence: Some(chunk.sequence), message: "conversation chunk sequence gap".into() }); }
        self.next_sequence += 1;
        ChunkResult::Applied
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum ConversationIntent { CancelGeneration { conversation_id: String, session_id: String, epoch: u64 }, RetryMessage { conversation_id: String, session_id: String, message_id: String, epoch: u64 }, CopyMessage { conversation_id: String, session_id: String, message_id: String, epoch: u64 }, OpenArtifact { conversation_id: String, session_id: String, message_id: String, artifact_id: String, epoch: u64 } }

impl ConversationIntent {
    pub fn name(&self) -> &'static str { match self { Self::CancelGeneration { .. } => "conversation.cancel", Self::RetryMessage { .. } => "conversation.retry", Self::CopyMessage { .. } => "conversation.copy", Self::OpenArtifact { .. } => "conversation.open_artifact" } }
    pub fn payload(&self) -> Value { match self { Self::CancelGeneration { conversation_id, session_id, epoch } => serde_json::json!({"conversation_id":conversation_id,"session_id":session_id,"epoch":epoch}), Self::RetryMessage { conversation_id, session_id, message_id, epoch } | Self::CopyMessage { conversation_id, session_id, message_id, epoch } => serde_json::json!({"conversation_id":conversation_id,"session_id":session_id,"message_id":message_id,"epoch":epoch}), Self::OpenArtifact { conversation_id, session_id, message_id, artifact_id, epoch } => serde_json::json!({"conversation_id":conversation_id,"session_id":session_id,"message_id":message_id,"artifact_id":artifact_id,"epoch":epoch}) } }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn stream_reports_gap_duplicate_and_epoch_change() {
        let mut stream = ConversationStream::new(4, 10);
        assert_eq!(stream.apply(&ConversationChunk { epoch:4, sequence:11, message_id:"m".into(), text:"x".into(), final_chunk:false }), ChunkResult::Gap(ConversationDiagnostic { kind:ConversationDiagnosticKind::SequenceGap, expected_sequence:Some(10), received_sequence:Some(11), message:"conversation chunk sequence gap".into() }));
        assert_eq!(stream.apply(&ConversationChunk { epoch:4, sequence:10, message_id:"m".into(), text:"x".into(), final_chunk:false }), ChunkResult::Applied);
        assert_eq!(stream.apply(&ConversationChunk { epoch:4, sequence:10, message_id:"m".into(), text:"x".into(), final_chunk:false }), ChunkResult::Duplicate);
        assert!(matches!(stream.apply(&ConversationChunk { epoch:5, sequence:11, message_id:"m".into(), text:"x".into(), final_chunk:true }), ChunkResult::Gap(_)));
    }
}
