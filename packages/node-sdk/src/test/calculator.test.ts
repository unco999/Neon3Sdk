import assert from "node:assert/strict";
import test from "node:test";
import { CalculatorDomain } from "../examples/calculator/domain.js";

test("Node calculator handles chained operations after equals", () => {
  const domain = new CalculatorDomain();
  const program = { program_id: "calculator", revision: 1 };
  const intents = ["calculator.number.one", "calculator.operator.add", "calculator.number.one", "calculator.equals", "calculator.operator.add", "calculator.number.one", "calculator.equals"];
  intents.forEach((intent, index) => domain.apply({ event_id: String(index), intent }, program, index));
  assert.equal(domain.state.display, 3);
  assert.equal(domain.state.revision, 7);
});
