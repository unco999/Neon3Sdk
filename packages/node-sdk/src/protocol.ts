export const RPC_PROTOCOL = "neon3.rpc" as const;
export const PROTOCOL_VERSION = { major: 1, minor: 0 } as const;

export interface RpcResponse<T = unknown> {
  request_id: string;
  status: "accepted" | "rejected" | "failed";
  revision: number | null;
  result: T | null;
  snapshot: unknown | null;
  error: Record<string, unknown> | null;
}

export interface ServiceDescription {
  service: string;
  protocol_version: { major: number; minor: number };
  endpoint: string;
  epoch: number;
  capabilities: string[];
}

export interface ServiceHealth {
  service: string;
  status: "healthy" | "degraded" | "unhealthy";
  epoch: number;
}
