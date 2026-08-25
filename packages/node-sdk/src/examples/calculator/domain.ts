export type Operation = "add" | "subtract" | "multiply" | "divide";

export interface CalculatorState {
  display: number;
  accumulator: number;
  pending: number;
  operation: Operation;
  awaitingOperand: boolean;
  revision: number;
}

export interface UiPublication {
  scalar_frame: {
    program_revision: Record<string, unknown>;
    expected_input_revision: number;
    request_id: string;
    idempotency_key: string;
    changes: Array<{ key: string; value: Record<string, unknown> }>;
  };
  grid_inputs: unknown[];
  presentation_update: null;
}

const DIGITS: Record<string, number> = { zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9 };

export class CalculatorDomain {
  state: CalculatorState = { display: 0, accumulator: 0, pending: 0, operation: "add", awaitingOperand: true, revision: 0 };
  private readonly handled = new Map<string, UiPublication>();

  apply(event: { event_id: string; intent: string }, programRevision: Record<string, unknown>, inputRevision: number): UiPublication {
    const replay = this.handled.get(event.event_id);
    if (replay) return replay;
    this.reduce(event.intent);
    this.state.revision += 1;
    const publication = this.publication(programRevision, inputRevision, event.event_id);
    this.handled.set(event.event_id, publication);
    return publication;
  }

  private reduce(intent: string): void {
    if (intent.startsWith("calculator.number.")) {
      const digit = DIGITS[intent.split(".").at(-1)!];
      if (digit === undefined) throw new Error("unknown calculator digit");
      this.state.display = this.state.awaitingOperand ? digit : this.state.display * 10 + digit;
      this.state.awaitingOperand = false;
      return;
    }
    if (intent === "calculator.clear") { this.state = { display: 0, accumulator: 0, pending: 0, operation: "add", awaitingOperand: true, revision: this.state.revision }; return; }
    if (intent.startsWith("calculator.operator.")) {
      if (!this.state.awaitingOperand) {
        this.state.accumulator = this.state.pending ? calculate(this.state.accumulator, this.state.display, this.state.operation) : this.state.display;
        this.state.pending = this.state.accumulator;
      }
      this.state.operation = intent.split(".").at(-1) as Operation;
      this.state.awaitingOperand = true;
      return;
    }
    if (intent === "calculator.equals") {
      if (!this.state.awaitingOperand && this.state.pending) {
        this.state.display = calculate(this.state.accumulator, this.state.display, this.state.operation);
        this.state.accumulator = this.state.display;
        this.state.pending = this.state.display;
      }
      this.state.awaitingOperand = true;
      return;
    }
    throw new Error(`unsupported calculator intent: ${intent}`);
  }

  private publication(programRevision: Record<string, unknown>, inputRevision: number, requestId: string): UiPublication {
    return { scalar_frame: { program_revision: programRevision, expected_input_revision: inputRevision, request_id: requestId, idempotency_key: `calculator-input:${this.state.revision}`, changes: [
      { key: "display", value: { kind: "f32", value: this.state.display } },
      { key: "accumulator", value: { kind: "f32", value: this.state.accumulator } },
      { key: "pending", value: { kind: "f32", value: this.state.pending } },
      { key: "operation", value: { kind: "enum", value: this.state.operation } },
    ] }, grid_inputs: [], presentation_update: null };
  }
}

function calculate(left: number, right: number, operation: Operation): number {
  if (operation === "add") return left + right;
  if (operation === "subtract") return left - right;
  if (operation === "multiply") return left * right;
  if (right === 0) throw new Error("division by zero");
  return left / right;
}
