export const actorKinds = ["human", "ai-agent", "swarm", "service", "automation"] as const;
export type ActorKind = (typeof actorKinds)[number];

export const integrations = ["generic", "codex", "claude"] as const;
export type Integration = (typeof integrations)[number];

export const methods = ["scrum", "kanban"] as const;
export type Method = (typeof methods)[number];

export interface UserConfiguration {
  integration: Integration;
  provider: string;
  model: string;
  defaultMethod: Method;
}

export interface ProjectConfiguration extends UserConfiguration {
  project: string;
  createdAt: string;
}

export interface ActorRecord {
  id: string;
  name: string;
  kind: ActorKind;
  capabilities: string[];
  path: string;
  reference: string;
}

export interface SwarmRecord {
  id: string;
  method: string;
  status: string;
  branch: string;
  requiredRoles: string[];
  assignments: Record<string, string>;
  objective: string;
  path: string;
}

export interface WorkRecord {
  id: string;
  swarmId: string;
  title: string;
  description: string;
  state: string;
  acceptanceCriteria: Record<string, string>;
  satisfiedCriteria: string[];
  requiredArtifacts: string[];
  artifactKinds: string[];
  evidenceResults: string[];
  path: string;
}
