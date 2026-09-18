//! Typed Agent tool-call and approval contract.

use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ToolCallState { Queued, Running, Succeeded, Failed, Cancelled, AwaitingApproval }

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RiskLevel { Low, Medium, High, Critical }

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AgentToolCall {
    pub tool_call_id: String,
    pub session_id: String,
    pub job_id: String,
    pub request_id: String,
    pub tool_name: String,
    pub state: ToolCallState,
    pub risk: RiskLevel,
    /// Host-provided bounded summary. Raw/sensitive arguments never belong in
    /// this presentation contract.
    pub arguments_summary: String,
    pub epoch: u64,
    pub revision: u64,
}

impl AgentToolCall {
    pub fn validate(&self) -> Result<(), String> {
        if [&self.tool_call_id, &self.session_id, &self.job_id, &self.request_id, &self.tool_name].iter().any(|v| v.trim().is_empty()) { return Err("tool call identity fields are required".into()); }
        if self.arguments_summary.len() > 8 * 1024 { return Err("tool arguments summary exceeds 8 KiB".into()); }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ApprovalState { Pending, Approved, Denied, Expired, Stale }

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ApprovalPrompt {
    pub request_id: String,
    pub session_id: String,
    pub job_id: String,
    pub tool_call_id: String,
    pub epoch: u64,
    pub revision: u64,
    pub risk: RiskLevel,
    pub state: ApprovalState,
    pub title: String,
    pub summary: String,
}

impl ApprovalPrompt {
    pub fn validate(&self) -> Result<(), String> {
        if [&self.request_id, &self.session_id, &self.job_id, &self.tool_call_id].iter().any(|v| v.trim().is_empty()) { return Err("approval identity fields are required".into()); }
        if self.summary.len() > 8 * 1024 { return Err("approval summary exceeds 8 KiB".into()); }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum ApprovalIntent { Approve { request_id: String, session_id: String, job_id: String, tool_call_id: String, epoch: u64, revision: u64 }, Deny { request_id: String, session_id: String, job_id: String, tool_call_id: String, epoch: u64, revision: u64, reason: Option<String> }, Cancel { request_id: String, session_id: String, job_id: String, tool_call_id: String, epoch: u64, revision: u64 }, Retry { request_id: String, session_id: String, job_id: String, tool_call_id: String, epoch: u64, revision: u64 } }

impl ApprovalIntent {
    pub fn name(&self) -> &'static str { match self { Self::Approve { .. } => "approval.approve", Self::Deny { .. } => "approval.deny", Self::Cancel { .. } => "approval.cancel", Self::Retry { .. } => "approval.retry" } }
    pub fn payload(&self) -> Value {
        match self {
            Self::Approve { request_id, session_id, job_id, tool_call_id, epoch, revision } | Self::Cancel { request_id, session_id, job_id, tool_call_id, epoch, revision } | Self::Retry { request_id, session_id, job_id, tool_call_id, epoch, revision } => serde_json::json!({"request_id":request_id,"session_id":session_id,"job_id":job_id,"tool_call_id":tool_call_id,"epoch":epoch,"revision":revision}),
            Self::Deny { request_id, session_id, job_id, tool_call_id, epoch, revision, reason } => serde_json::json!({"request_id":request_id,"session_id":session_id,"job_id":job_id,"tool_call_id":tool_call_id,"epoch":epoch,"revision":revision,"reason":reason}),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn tool_and_approval_contracts_require_identity_and_bound_summaries() {
        let tool = AgentToolCall { tool_call_id:"t1".into(), session_id:"s1".into(), job_id:"j1".into(), request_id:"r1".into(), tool_name:"shell".into(), state:ToolCallState::AwaitingApproval, risk:RiskLevel::High, arguments_summary:"command: cargo test".into(), epoch:2, revision:4 };
        assert!(tool.validate().is_ok());
        let prompt = ApprovalPrompt { request_id:"r1".into(), session_id:"s1".into(), job_id:"j1".into(), tool_call_id:"t1".into(), epoch:2, revision:4, risk:RiskLevel::High, state:ApprovalState::Pending, title:"Run command".into(), summary:"cargo test".into() };
        assert!(prompt.validate().is_ok());
    }
}
