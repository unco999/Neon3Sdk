export class NeonError extends Error {}
export class TransportError extends NeonError {}
export class ProtocolError extends NeonError {}

export class RemoteError extends NeonError {
  constructor(
    readonly requestId: string,
    readonly status: string,
    readonly error: Record<string, unknown> | null,
  ) {
    super(`${String(error?.code ?? "remote_error")}: ${String(error?.message ?? "remote error")} (request_id=${requestId})`);
  }
}
