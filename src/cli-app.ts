import {
  actorKinds,
  integrations,
  methods,
  type ActorKind,
  type Integration,
  type Method,
} from "./model.js";
import { AgoraWorkspace } from "./workspace.js";

type Options = Map<string, string[]>;

export const usage = `Agora - governed human and agentic swarms

Usage:
  agora configure --integration <generic|codex|claude> --provider <name> --model <name>
                  [--default-method <scrum|kanban>] [--force]
  agora init [--path <directory>] [--integration <name>] [--provider <name>] [--model <name>]
             [--default-method <scrum|kanban>] [--force]
  agora doctor
  agora actor add --id <id> --name <name> --kind <human|ai-agent|swarm|service|automation>
                  [--capability <name>]... [--scope <user|project>] [--force]
  agora swarm create --id <id> --objective <text> [--method <scrum|kanban>]
                     [--branch <name>] [--no-branch]
  agora swarm assign --swarm <id> --role <id> --actor <id|scope:id>
  agora swarm show --swarm <id>
  agora work create --swarm <id> --id <id> --title <text> --by <actor> [--description <text>]
                    [--criterion <id:description>]... [--required-artifact <kind>]...
  agora work criterion-satisfy --swarm <id> --work <id> --criterion <id> --by <actor>
  agora work transition --swarm <id> --work <id> --to <state> --by <actor>
  agora work show --swarm <id> --work <id>
  agora artifact add --swarm <id> --work <id> --kind <kind> --uri <uri> --by <actor>
  agora evidence add --swarm <id> --work <id> --type <type> --result <success|failure>
                     --by <actor> [--artifact <uri-or-id>]...

Global option: --project <path> targets an initialized project from any environment.
Configuration precedence: Agora defaults < ~/.agora < project .agora < swarm.`;

export function runCli(
  argv: string[],
  environment: {
    cwd?: string;
    log?: (value: string) => void;
    error?: (value: string) => void;
  } = {},
): number {
  const log = environment.log ?? console.log;
  const logError = environment.error ?? console.error;
  try {
    const { positionals, options } = parseArguments(argv);
    if (positionals.length === 0 || options.has("help")) {
      log(usage);
      return 0;
    }
    const workspaceRoot = last(options, "project") ?? environment.cwd;
    const workspace = new AgoraWorkspace(workspaceRoot ? { cwd: workspaceRoot } : {});
    const command = positionals.join(" ");
    switch (command) {
      case "configure":
        output(
          log,
          workspace.configure({
            integration: integration(options, "integration", "generic"),
            provider: last(options, "provider") ?? "configured-by-integration",
            model: last(options, "model") ?? "configured-by-integration",
            defaultMethod: method(options, "default-method", "scrum"),
            force: flag(options, "force"),
          }),
        );
        break;
      case "init":
        output(
          log,
          workspace.initialize({
            ...optionalString(options, "path", "target"),
            ...optionalIntegration(options),
            ...optionalString(options, "provider"),
            ...optionalString(options, "model"),
            ...optionalMethod(options),
            force: flag(options, "force"),
          }),
        );
        break;
      case "doctor": {
        const checks = workspace.doctor();
        output(log, { ok: checks.every((check) => check.ok), checks });
        return checks.every((check) => check.ok || check.name === "git") ? 0 : 1;
      }
      case "actor add": {
        const kind = required(options, "kind");
        if (!actorKinds.includes(kind as ActorKind))
          throw new Error(`Unsupported actor kind: ${kind}`);
        const scope = last(options, "scope") ?? "project";
        if (scope !== "user" && scope !== "project")
          throw new Error(`Unsupported actor scope: ${scope}`);
        output(
          log,
          workspace.addActor({
            id: required(options, "id"),
            name: required(options, "name"),
            kind: kind as ActorKind,
            capabilities: all(options, "capability"),
            scope,
            ...optionalString(options, "description"),
            force: flag(options, "force"),
          }),
        );
        break;
      }
      case "swarm create":
        output(
          log,
          workspace.createSwarm({
            id: required(options, "id"),
            objective: required(options, "objective"),
            ...optionalMethodNamed(options, "method"),
            ...optionalString(options, "branch"),
            createBranch: !flag(options, "no-branch"),
          }),
        );
        break;
      case "swarm assign":
        output(
          log,
          workspace.assignActor({
            swarmId: required(options, "swarm"),
            roleId: required(options, "role"),
            actorId: required(options, "actor"),
          }),
        );
        break;
      case "swarm show":
        output(log, workspace.showSwarm(required(options, "swarm")));
        break;
      case "work create":
        output(
          log,
          workspace.createWork({
            swarmId: required(options, "swarm"),
            id: required(options, "id"),
            title: required(options, "title"),
            ...optionalString(options, "description"),
            acceptanceCriteria: all(options, "criterion").map(parseCriterion),
            requiredArtifacts: all(options, "required-artifact"),
            actorId: required(options, "by"),
          }),
        );
        break;
      case "work criterion-satisfy":
        output(
          log,
          workspace.satisfyCriterion({
            swarmId: required(options, "swarm"),
            workId: required(options, "work"),
            criterionId: required(options, "criterion"),
            actorId: required(options, "by"),
          }),
        );
        break;
      case "work transition":
        output(
          log,
          workspace.transitionWork({
            swarmId: required(options, "swarm"),
            workId: required(options, "work"),
            targetState: required(options, "to"),
            actorId: required(options, "by"),
          }),
        );
        break;
      case "work show":
        output(log, workspace.showWork(required(options, "swarm"), required(options, "work")));
        break;
      case "artifact add":
        output(
          log,
          workspace.addArtifact({
            swarmId: required(options, "swarm"),
            workId: required(options, "work"),
            kind: required(options, "kind"),
            uri: required(options, "uri"),
            actorId: required(options, "by"),
          }),
        );
        break;
      case "evidence add": {
        const result = required(options, "result");
        if (result !== "success" && result !== "failure") {
          throw new Error(`Unsupported evidence result: ${result}`);
        }
        output(
          log,
          workspace.addEvidence({
            swarmId: required(options, "swarm"),
            workId: required(options, "work"),
            type: required(options, "type"),
            result,
            actorId: required(options, "by"),
            artifactRefs: all(options, "artifact"),
          }),
        );
        break;
      }
      default:
        throw new Error(`Unknown command: ${command}\n\n${usage}`);
    }
    return 0;
  } catch (error) {
    logError(error instanceof Error ? error.message : String(error));
    return 1;
  }
}

function parseArguments(argv: string[]): { positionals: string[]; options: Options } {
  const positionals: string[] = [];
  const options: Options = new Map();
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token) continue;
    if (!token.startsWith("--")) {
      positionals.push(token);
      continue;
    }
    const key = token.slice(2);
    const next = argv[index + 1];
    const value = next && !next.startsWith("--") ? next : "true";
    if (value !== "true") index += 1;
    options.set(key, [...(options.get(key) ?? []), value]);
  }
  return { positionals, options };
}

function required(options: Options, key: string): string {
  const value = last(options, key);
  if (!value) throw new Error(`Missing required option: --${key}`);
  return value;
}

function last(options: Options, key: string): string | undefined {
  return options.get(key)?.at(-1);
}

function all(options: Options, key: string): string[] {
  return options.get(key) ?? [];
}

function flag(options: Options, key: string): boolean {
  return options.get(key)?.at(-1) === "true";
}

function integration(options: Options, key: string, fallback: Integration): Integration {
  const value = last(options, key) ?? fallback;
  if (!integrations.includes(value as Integration))
    throw new Error(`Unsupported integration: ${value}`);
  return value as Integration;
}

function method(options: Options, key: string, fallback: Method): Method {
  const value = last(options, key) ?? fallback;
  if (!methods.includes(value as Method)) throw new Error(`Unsupported method: ${value}`);
  return value as Method;
}

function optionalIntegration(options: Options): { integration?: Integration } {
  const value = last(options, "integration");
  return value ? { integration: integration(options, "integration", "generic") } : {};
}

function optionalMethod(options: Options): { defaultMethod?: Method } {
  const value = last(options, "default-method");
  return value ? { defaultMethod: method(options, "default-method", "scrum") } : {};
}

function optionalMethodNamed(options: Options, key: string): { method?: Method } {
  const value = last(options, key);
  return value ? { method: method(options, key, "scrum") } : {};
}

function optionalString(options: Options, key: string, outputKey = key): Record<string, string> {
  const value = last(options, key);
  return value ? { [outputKey]: value } : {};
}

function parseCriterion(value: string): { id: string; description: string } {
  const separator = value.indexOf(":");
  if (separator < 1 || separator === value.length - 1) {
    throw new Error(`Invalid criterion "${value}"; expected id:description`);
  }
  return { id: value.slice(0, separator), description: value.slice(separator + 1) };
}

function output(log: (value: string) => void, value: unknown): void {
  log(JSON.stringify(value, null, 2));
}
