import { spawnSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { AgoraWorkspace } from "../dist/workspace.js";

const project = mkdtempSync(join(tmpdir(), "agora-example-project-"));
process.env.AGORA_HOME = mkdtempSync(join(tmpdir(), "agora-example-home-"));
git(["init", "-q", project]);

const agora = new AgoraWorkspace({ cwd: project });
console.log(`Project: ${project}`);
console.log("1. Configure the user and initialize a Codex-ready project");
agora.configure({
  integration: "codex",
  provider: "openai",
  model: "configured-by-codex",
  defaultMethod: "scrum",
});
agora.initialize({});

console.log("2. Register a human, an AI agent, and a nested swarm");
agora.addActor({
  id: "owner",
  name: "Human Product Owner",
  kind: "human",
  capabilities: ["backlog-management", "acceptance"],
  scope: "user",
});
agora.addActor({
  id: "facilitator",
  name: "AI Facilitator",
  kind: "ai-agent",
  capabilities: ["facilitation", "governance"],
  scope: "project",
});
agora.addActor({
  id: "delivery-swarm",
  name: "Delivery Swarm",
  kind: "swarm",
  capabilities: ["implementation"],
  scope: "project",
});

console.log("3. Create an Agora branch and form the swarm");
agora.createSwarm({ id: "first-slice", objective: "Deliver governed Markdown-first work" });
agora.assignActor({ swarmId: "first-slice", roleId: "product-owner", actorId: "owner" });
agora.assignActor({ swarmId: "first-slice", roleId: "scrum-master", actorId: "facilitator" });
agora.assignActor({ swarmId: "first-slice", roleId: "developer", actorId: "delivery-swarm" });

console.log("4. Create work and advance through the installed Scrum Method Pack");
agora.createWork({
  swarmId: "first-slice",
  id: "bootstrap",
  title: "Bootstrap Agora",
  acceptanceCriteria: [{ id: "installable", description: "Agora initializes locally" }],
  requiredArtifacts: ["source-code"],
  actorId: "owner",
});
for (const targetState of ["planned", "implementing", "reviewing", "verifying"]) {
  agora.transitionWork({
    swarmId: "first-slice",
    workId: "bootstrap",
    targetState,
    actorId: "delivery-swarm",
  });
}

console.log("5. Confirm that completion is rejected without artifacts and evidence");
try {
  agora.transitionWork({
    swarmId: "first-slice",
    workId: "bootstrap",
    targetState: "completed",
    actorId: "owner",
  });
} catch (error) {
  console.log(`   Rejected: ${error.message}`);
}

console.log("6. Satisfy the gate and complete");
agora.satisfyCriterion({
  swarmId: "first-slice",
  workId: "bootstrap",
  criterionId: "installable",
  actorId: "owner",
});
agora.addArtifact({
  swarmId: "first-slice",
  workId: "bootstrap",
  kind: "source-code",
  uri: "repo://src/workspace.ts",
  actorId: "delivery-swarm",
});
agora.addEvidence({
  swarmId: "first-slice",
  workId: "bootstrap",
  type: "test-run",
  result: "success",
  artifactRefs: ["repo://src/workspace.ts"],
  actorId: "facilitator",
});
agora.transitionWork({
  swarmId: "first-slice",
  workId: "bootstrap",
  targetState: "completed",
  actorId: "owner",
});

console.log(
  JSON.stringify(
    {
      branch: git(["-C", project, "branch", "--show-current"]).trim(),
      swarm: agora.showSwarm("first-slice").status,
      work: agora.showWork("first-slice", "bootstrap").state,
      persistedAt: join(project, ".agora", "swarms", "first-slice"),
    },
    null,
    2,
  ),
);

function git(arguments_) {
  const result = spawnSync("git", arguments_, { encoding: "utf8" });
  if ((result.status ?? 1) !== 0) throw new Error(result.stderr || "Git command failed");
  return result.stdout;
}
