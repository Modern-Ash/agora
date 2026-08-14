import { spawnSync } from "node:child_process";

export function isGitRepository(cwd: string): boolean {
  return runGit(cwd, ["rev-parse", "--is-inside-work-tree"], true).status === 0;
}

export function currentBranch(cwd: string): string {
  const result = runGit(cwd, ["branch", "--show-current"]);
  return result.stdout.trim() || "detached";
}

export function createBranch(cwd: string, branch: string): void {
  const result = runGit(cwd, ["switch", "-c", branch], true);
  if (result.status !== 0) {
    throw new Error(`Unable to create Git branch ${branch}: ${result.stderr.trim()}`);
  }
}

function runGit(
  cwd: string,
  arguments_: string[],
  tolerateFailure = false,
): { status: number; stdout: string; stderr: string } {
  const result = spawnSync("git", arguments_, { cwd, encoding: "utf8" });
  const status = result.status ?? 1;
  if (!tolerateFailure && status !== 0) {
    throw new Error(`Git command failed: ${result.stderr.trim()}`);
  }
  return { status, stdout: result.stdout, stderr: result.stderr };
}
