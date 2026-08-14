import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { AgoraWorkspace } from "./workspace.js";

const timestamp = new Date("2026-08-14T12:00:00.000Z");
let previousHome: string | undefined;

beforeEach(() => {
  previousHome = process.env.AGORA_HOME;
  process.env.AGORA_HOME = mkdtempSync(join(tmpdir(), "agora-test-home-"));
});

afterEach(() => {
  if (previousHome === undefined) delete process.env.AGORA_HOME;
  else process.env.AGORA_HOME = previousHome;
});

function repository(): string {
  return mkdtempSync(join(tmpdir(), "agora-test-project-"));
}

function workspace(root: string): AgoraWorkspace {
  return new AgoraWorkspace({ cwd: root, now: () => timestamp });
}

describe("Agora installation", () => {
  it("persists user defaults and materializes a Codex-ready project", () => {
    const root = repository();
    const service = workspace(root);
    service.configure({
      integration: "codex",
      provider: "openai",
      model: "configured-by-codex",
      defaultMethod: "kanban",
    });

    const project = service.initialize({});

    expect(project).toMatchObject({ integration: "codex", defaultMethod: "kanban" });
    expect(existsSync(join(root, ".agora", "methods", "scrum", "METHOD.md"))).toBe(true);
    expect(existsSync(join(root, ".agora", "methods", "kanban", "METHOD.md"))).toBe(true);
    expect(existsSync(join(root, ".agents", "skills", "agora-objective", "SKILL.md"))).toBe(true);
    expect(readFileSync(join(root, ".agora", "project.md"), "utf8")).toContain(
      'integration: "codex"',
    );
  });

  it("reports missing Git as a supported filesystem-only environment", () => {
    const root = mkdtempSync(join(tmpdir(), "agora-test-no-git-"));
    const service = workspace(root);
    service.initialize({ integration: "generic" });

    expect(service.doctor().find((check) => check.name === "git")).toMatchObject({
      ok: false,
      detail: "filesystem-only mode",
    });
  });
});

describe("governed swarms", () => {
  it("supports human, AI, and nested swarm actors through a gated workflow", () => {
    const root = repository();
    const service = workspace(root);
    service.initialize({ integration: "generic", defaultMethod: "scrum" });
    service.addActor({
      id: "owner",
      name: "Product Owner",
      kind: "human",
      capabilities: ["backlog-management", "acceptance"],
      scope: "user",
    });
    service.addActor({
      id: "facilitator",
      name: "Facilitator",
      kind: "ai-agent",
      capabilities: ["facilitation", "governance"],
      scope: "project",
    });
    service.addActor({
      id: "delivery-swarm",
      name: "Delivery Swarm",
      kind: "swarm",
      capabilities: ["implementation"],
      scope: "project",
    });

    expect(() =>
      service.assignActor({ swarmId: "missing", roleId: "developer", actorId: "owner" }),
    ).toThrow();
    service.createSwarm({
      id: "first-slice",
      objective: "Build the Markdown-first slice",
      createBranch: false,
    });
    expect(service.showSwarm("first-slice").branch).toBe("filesystem-only");
    service.assignActor({ swarmId: "first-slice", roleId: "product-owner", actorId: "owner" });
    service.assignActor({
      swarmId: "first-slice",
      roleId: "scrum-master",
      actorId: "facilitator",
    });
    expect(() =>
      service.assignActor({ swarmId: "first-slice", roleId: "developer", actorId: "owner" }),
    ).toThrow("lacks capabilities");
    expect(
      service.assignActor({
        swarmId: "first-slice",
        roleId: "developer",
        actorId: "delivery-swarm",
      }).status,
    ).toBe("ready");

    service.createWork({
      swarmId: "first-slice",
      id: "bootstrap",
      title: "Bootstrap Agora",
      acceptanceCriteria: [{ id: "installable", description: "Agora initializes a project" }],
      requiredArtifacts: ["source-code"],
      actorId: "owner",
    });
    expect(() =>
      service.transitionWork({
        swarmId: "first-slice",
        workId: "bootstrap",
        targetState: "implementing",
        actorId: "delivery-swarm",
      }),
    ).toThrow("expected planned");
    for (const state of ["planned", "implementing", "reviewing", "verifying"]) {
      service.transitionWork({
        swarmId: "first-slice",
        workId: "bootstrap",
        targetState: state,
        actorId: "delivery-swarm",
      });
    }
    expect(() =>
      service.transitionWork({
        swarmId: "first-slice",
        workId: "bootstrap",
        targetState: "completed",
        actorId: "owner",
      }),
    ).toThrow("Final gate failed");
    expect(() =>
      service.satisfyCriterion({
        swarmId: "first-slice",
        workId: "bootstrap",
        criterionId: "installable",
        actorId: "delivery-swarm",
      }),
    ).toThrow("is not allowed to perform criterion.satisfy");

    service.satisfyCriterion({
      swarmId: "first-slice",
      workId: "bootstrap",
      criterionId: "installable",
      actorId: "owner",
    });
    service.addArtifact({
      swarmId: "first-slice",
      workId: "bootstrap",
      kind: "source-code",
      uri: "repo://src/workspace.ts",
      actorId: "delivery-swarm",
    });
    service.addEvidence({
      swarmId: "first-slice",
      workId: "bootstrap",
      type: "test-run",
      result: "success",
      artifactRefs: ["repo://src/workspace.ts"],
      actorId: "facilitator",
    });
    expect(
      service.transitionWork({
        swarmId: "first-slice",
        workId: "bootstrap",
        targetState: "completed",
        actorId: "owner",
      }).state,
    ).toBe("completed");
    expect(service.showSwarm("first-slice").status).toBe("completed");

    const workRoot = join(root, ".agora", "swarms", "first-slice", "work", "bootstrap");
    expect(readFileSync(join(workRoot, "WORK.md"), "utf8")).toContain("- [x] **installable:**");
    expect(readFileSync(join(workRoot, "events.md"), "utf8")).toContain("work.transitioned");
    expect(readFileSync(join(workRoot, "evidence.md"), "utf8")).toContain("| test-run | success |");
  });
});
