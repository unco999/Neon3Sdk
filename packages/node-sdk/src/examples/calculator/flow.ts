import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

export async function calculatorFlow(): Promise<string> {
  return readFile(fileURLToPath(new URL("./calculator.nui", import.meta.url)), "utf8");
}
