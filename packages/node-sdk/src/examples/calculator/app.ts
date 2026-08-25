import { NeonClient, RenderClient, RuntimeSession, UiClient } from "../../index.js";
import { calculatorFlow } from "./flow.js";
import { CalculatorService } from "./rpc-service.js";

const once = process.argv.includes("--once");
const root = process.env.NEON_ROOT ?? "D:/Neon3";
const service = new CalculatorService();
const runtime = new RuntimeSession({ neonRoot: root, mode: "windowed", domain: "127.0.0.1:39104" });
await service.start();
try {
  await runtime.start();
  const ui = new UiClient(new NeonClient("127.0.0.1:39102", { origin: "neon3-node-calculator" }));
  const renderer = new RenderClient(new NeonClient("127.0.0.1:39103", { origin: "neon3-node-calculator" }));
  const program = await ui.submitFlow(await calculatorFlow());
  console.log(JSON.stringify({ stage: "ready", status: "passed", surface: program.surface_id, initial_state: service.domain.state }));
  if (once) {
    let inputRevision = 0;
    for (const [intent, source] of [["calculator.number.one", "one"], ["calculator.operator.add", "add"], ["calculator.number.one", "one"], ["calculator.equals", "equals"], ["calculator.operator.add", "add"], ["calculator.number.one", "one"], ["calculator.equals", "equals"]] as const) {
      const eventId = crypto.randomUUID();
      await ui.hostInbound({
        kind: "semantic_intent",
        event: {
          event_id: eventId,
          kind: "activate",
          intent,
          source_node_key: source,
          payload: {},
          program_revision: program.program_revision,
          input_revision: inputRevision,
          request_id: eventId,
          idempotency_key: `calculator-event:${eventId}`,
          interaction: { interaction_id: eventId, sequence: 1, renderer_epoch: 1 },
        },
      });
      inputRevision += 1;
    }
    const fragment = await renderer.client.call("wgpu-runtime", "wgpu.ui.fragment.snapshot", { fragment_id: program.surface_id });
    console.log(JSON.stringify({ stage: "result", status: service.domain.state.display === 3 ? "passed" : "failed", scenario: "1 + 1 = + 1 =", state: service.domain.state, input_revision: inputRevision, fragment_revision: fragment.result && (fragment.result as any).fragment_revision }));
  } else {
    await new Promise<void>((resolve) => process.once("SIGINT", resolve));
  }
} finally { await runtime.stop(); await service.stop(); }
