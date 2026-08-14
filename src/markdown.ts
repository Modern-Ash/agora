import { readFileSync } from "node:fs";

export type Attributes = Record<string, unknown>;

export interface MarkdownDocument {
  attributes: Attributes;
  body: string;
}

export function parseMarkdown(contents: string): MarkdownDocument {
  const lines = contents.replaceAll("\r\n", "\n").split("\n");
  if (lines[0] !== "---") {
    throw new Error("Markdown document must start with YAML front matter");
  }
  const end = lines.indexOf("---", 1);
  if (end === -1) {
    throw new Error("Markdown document has unterminated front matter");
  }
  const attributes: Attributes = {};
  for (const line of lines.slice(1, end)) {
    if (line.trim() === "" || line.trimStart().startsWith("#")) continue;
    const separator = line.indexOf(":");
    if (separator === -1) throw new Error(`Invalid front matter line: ${line}`);
    const key = line.slice(0, separator).trim();
    attributes[key] = parseValue(line.slice(separator + 1).trim());
  }
  return {
    attributes,
    body: lines
      .slice(end + 1)
      .join("\n")
      .replace(/^\n/, ""),
  };
}

export function readMarkdown(path: string): MarkdownDocument {
  return parseMarkdown(readFileSync(path, "utf8"));
}

export function renderMarkdown(document: MarkdownDocument): string {
  const frontMatter = Object.entries(document.attributes)
    .map(([key, value]) => `${key}: ${renderValue(value)}`)
    .join("\n");
  return `---\n${frontMatter}\n---\n\n${document.body.trim()}\n`;
}

export function stringAttribute(attributes: Attributes, key: string): string {
  const value = attributes[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`Expected non-empty string attribute: ${key}`);
  }
  return value;
}

export function stringsAttribute(attributes: Attributes, key: string): string[] {
  const value = attributes[key];
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`Expected string array attribute: ${key}`);
  }
  return value as string[];
}

export function recordAttribute(attributes: Attributes, key: string): Record<string, string> {
  const value = attributes[key];
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`Expected object attribute: ${key}`);
  }
  if (Object.values(value).some((item) => typeof item !== "string")) {
    throw new Error(`Expected string values in attribute: ${key}`);
  }
  return value as Record<string, string>;
}

function parseValue(value: string): unknown {
  if (value === "") return "";
  if (
    value.startsWith('"') ||
    value.startsWith("[") ||
    value.startsWith("{") ||
    value === "true" ||
    value === "false" ||
    value === "null" ||
    /^-?\d+(\.\d+)?$/.test(value)
  ) {
    try {
      return JSON.parse(value);
    } catch {
      throw new Error(`Front matter value is not valid JSON-compatible YAML: ${value}`);
    }
  }
  return value;
}

function renderValue(value: unknown): string {
  if (typeof value === "string") return JSON.stringify(value);
  return JSON.stringify(value);
}
