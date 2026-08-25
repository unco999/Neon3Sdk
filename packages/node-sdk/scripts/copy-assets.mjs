import { mkdir, copyFile } from "node:fs/promises";

await mkdir("dist/examples/calculator", { recursive: true });
await copyFile("src/examples/calculator/calculator.nui", "dist/examples/calculator/calculator.nui");
