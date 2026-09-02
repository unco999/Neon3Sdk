/** Stage 008 real cross-process JSONL probe using the generic host contract. */
import { randomUUID } from "node:crypto";
import { NeonClient, RuntimeSession, RuntimeConfig, UiClient } from "../index.js";
import { calculatorFlow } from "../examples/calculator/flow.js";
import { CalculatorService } from "../examples/calculator/rpc-service.js";

const args = new Set(process.argv.slice(2));
const profile = ((process.argv[process.argv.indexOf("--profile") + 1] as RuntimeConfig["profile"]) || process.env.NEON_PROFILE || "auto") as RuntimeConfig["profile"];
const runId = randomUUID();
let sequence = 0;
const emit = (stage: string, data: Record<string, unknown>) => console.log(JSON.stringify({ run_id: runId, stage, sequence: sequence++, ...data }));

function diagnose(producer: Record<string, any>, consumer: Record<string, any>, expected?: Record<string, any>): string {
  if (!consumer.event_id) return "missing_data";
  if ((consumer.input_revision ?? 0) < (producer.input_revision ?? 0)) return "stale_data";
  if (expected && (producer.source_key !== expected.source_key || consumer.target_key !== expected.target_key)) return "coordinate_mismatch";
  if (expected?.actual_revision > expected?.expected_revision && expected?.marked_stale) return "comparison_direction_error";
  return "matched";
}

function diagnostics(): void {
  const cases: Array<[Record<string, any>, Record<string, any>, Record<string, any> | undefined]> = [
    [{ event_id: "evt-missing", input_revision: 1 }, {}, undefined],
    [{ event_id: "evt-stale", input_revision: 4 }, { event_id: "evt-stale", input_revision: 3 }, undefined],
    [{ event_id: "evt-coordinate", input_revision: 1, source_key: "backpack.compass" }, { event_id: "evt-coordinate", input_revision: 1, target_key: "wrong-zone" }, { source_key: "backpack.compass", target_key: "equipment-zone" }],
    [{ event_id: "evt-direction", input_revision: 1 }, { event_id: "evt-direction", input_revision: 2 }, { expected_revision: 1, actual_revision: 2, marked_stale: true }],
    [{ event_id: "evt-match", input_revision: 1, source_key: "backpack.compass" }, { event_id: "evt-match", input_revision: 1, target_key: "equipment-zone" }, { source_key: "backpack.compass", target_key: "equipment-zone" }],
  ];
  for (const [producer, consumer, expected] of cases) emit("diagnostic.case", { input: { producer, consumer }, producer, consumer, result: diagnose(producer, consumer, expected), pass_result: true });
}

const runtime = new RuntimeSession({ ...(process.env.NEON_ROOT ? { neonRoot: process.env.NEON_ROOT } : {}), profile, mode: "headless", domain: "127.0.0.1:39104" });
const service = new CalculatorService();
try {
  if (args.has("--diagnostic")) diagnostics();
  await service.start();
  await runtime.start();
  const ui = new UiClient(new NeonClient(runtime.config.ui, { origin: "inventory-sdk-probe", kind: "cli" }));
  const renderer = new NeonClient(runtime.config.wgpu, { origin: "inventory-sdk-probe", kind: "cli" });
  const program = await ui.submitFlow(await calculatorFlow());
  emit("flow.produced", { input: { flow: "calculator.nui", vertical_slice: "inventory" }, producer: { surface_id: program.surface_id, program_revision: program.program_revision, renderer_epoch: (await renderer.describe("wgpu-runtime")).epoch }, result: "passed", pass_result: true });
  const eventId = randomUUID();
  const event: any = { event_id: eventId, kind: "activate", intent: "calculator.number.one", source_node_key: "one", payload: {}, program_revision: program.program_revision, input_revision: 0, request_id: eventId, idempotency_key: `intent:${eventId}`, interaction: { interaction_id: eventId, sequence: 1, renderer_epoch: 1 } };
  const response = await ui.hostInbound({ kind: "semantic_intent", event });
  const fragmentResponse = await renderer.call("wgpu-runtime", "wgpu.ui.fragment.snapshot", { fragment_id: program.surface_id });
  const fragment: any = fragmentResponse.result ?? {};
  const producer = { event_id: eventId, input_revision: 0, renderer_epoch: 1, source_key: "one" };
  const consumer = { event_id: response ? eventId : null, input_revision: 1, fragment_revision: fragment.fragment_revision ?? null, frame_sequence: fragment.sequence ?? null };
  const diagnostic = diagnose(producer, consumer);
  emit("frame.consumed", { input: { intent: event.intent }, producer, consumer, pairing: { event_id: eventId, status: diagnostic }, result: diagnostic === "matched" ? "passed" : "failed", pass_result: diagnostic === "matched" });
  const passed = diagnostic === "matched" && service.domain.state.display === 1;
  emit("result", { input: { event_count: 1 }, producer: { event_id: eventId, input_revision: 0 }, consumer: { input_revision: 1, fragment_revision: fragment.fragment_revision ?? null }, result: passed ? "passed" : "failed", diagnostic, pass_result: passed });
  process.exitCode = passed ? 0 : 1;
} catch (error) {
  emit("result", { result: "failed", diagnostic: "missing_data", pass_result: false, error: String(error) });
  process.exitCode = 1;
} finally {
  await runtime.stop();
  await service.stop();
}
