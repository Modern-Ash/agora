import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export function agoraHome(): string {
  return resolve(process.env.AGORA_HOME ?? join(homedir(), ".agora"));
}

export function templateRoot(): string {
  return fileURLToPath(new URL("../templates", import.meta.url));
}

export function ensureDirectory(path: string): void {
  mkdirSync(path, { recursive: true });
}

export function atomicWrite(path: string, contents: string): void {
  ensureDirectory(dirname(path));
  const temporary = `${path}.tmp`;
  writeFileSync(temporary, contents, "utf8");
  renameSync(temporary, path);
}

export function writeNew(path: string, contents: string, force = false): void {
  if (existsSync(path) && !force) {
    throw new Error(`Refusing to overwrite existing file: ${path}. Pass --force to replace it.`);
  }
  atomicWrite(path, contents);
}

export function appendEntry(path: string, entry: string): void {
  ensureDirectory(dirname(path));
  appendFileSync(path, `${entry.trimEnd()}\n`, "utf8");
}

export function copyTemplateTree(
  source: string,
  destination: string,
  replacements: Record<string, string>,
  force = false,
): void {
  for (const entry of readdirSync(source, { withFileTypes: true })) {
    const sourcePath = join(source, entry.name);
    const destinationPath = join(destination, entry.name);
    if (entry.isDirectory()) {
      copyTemplateTree(sourcePath, destinationPath, replacements, force);
      continue;
    }
    let contents = readFileSync(sourcePath, "utf8");
    for (const [key, value] of Object.entries(replacements)) {
      contents = contents.replaceAll(`{{${key}}}`, value);
    }
    writeNew(destinationPath, contents, force);
  }
}

export function findProjectRoot(start = process.cwd()): string {
  let current = resolve(start);
  while (true) {
    if (existsSync(join(current, ".agora", "project.md"))) return current;
    const parent = dirname(current);
    if (parent === current) break;
    current = parent;
  }
  throw new Error(`No Agora project found from ${resolve(start)}. Run "agora init" first.`);
}

export function projectName(path: string): string {
  return basename(resolve(path));
}

export function assertSlug(value: string, label: string): void {
  if (!/^[a-z][a-z0-9-]*$/.test(value)) {
    throw new Error(`${label} must match /^[a-z][a-z0-9-]*$/: ${value}`);
  }
}
