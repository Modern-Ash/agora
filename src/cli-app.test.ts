import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { runCli } from "./cli-app.js";

const previousHome = process.env.AGORA_HOME;

afterEach(() => {
  if (previousHome === undefined) delete process.env.AGORA_HOME;
  else process.env.AGORA_HOME = previousHome;
});

describe("Agora CLI", () => {
  it("targets projects outside the current environment", () => {
    const project = mkdtempSync(join(tmpdir(), "agora-cli-project-"));
    process.env.AGORA_HOME = mkdtempSync(join(tmpdir(), "agora-cli-home-"));
    const output: string[] = [];
    const errors: string[] = [];
    const environment = {
      log: (value: string) => output.push(value),
      error: (value: string) => errors.push(value),
    };

    expect(runCli(["init", "--path", project, "--integration", "claude"], environment)).toBe(0);
    expect(
      runCli(
        [
          "actor",
          "add",
          "--project",
          project,
          "--id",
          "ada",
          "--name",
          "Ada",
          "--kind",
          "ai-agent",
          "--capability",
          "implementation",
        ],
        environment,
      ),
    ).toBe(0);
    expect(errors).toEqual([]);
    expect(output.join("\n")).toContain('"integration": "claude"');
    expect(output.join("\n")).toContain('"reference": "project:ada"');
  });
});
