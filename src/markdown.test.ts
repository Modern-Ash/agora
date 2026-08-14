import { describe, expect, it } from "vitest";
import { parseMarkdown, renderMarkdown } from "./markdown.js";

describe("Markdown protocol documents", () => {
  it("round-trips JSON-compatible YAML front matter and human-readable content", () => {
    const rendered = renderMarkdown({
      attributes: {
        schema: "agora/example/v1",
        states: ["ready", "running"],
        assignments: { developer: "project:ada" },
      },
      body: "# Example\n\nDurable collaboration context.",
    });

    expect(parseMarkdown(rendered)).toEqual({
      attributes: {
        schema: "agora/example/v1",
        states: ["ready", "running"],
        assignments: { developer: "project:ada" },
      },
      body: "# Example\n\nDurable collaboration context.\n",
    });
  });

  it("rejects documents without protocol metadata", () => {
    expect(() => parseMarkdown("# Plain markdown")).toThrow("must start with YAML front matter");
  });
});
