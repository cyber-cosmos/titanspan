import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { validateDocumentationNavigation } from "./check-navigation.mjs";

const config = (navLinks, sidebarLinks) => `
export default {
  themeConfig: {
    nav: [${navLinks}],
    sidebar: [${sidebarLinks}],
  },
};
`;

async function withDocs(callback) {
  const root = await mkdtemp(path.join(tmpdir(), "titanspan-docs-"));
  try {
    await callback(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

async function addPages(root, paths) {
  for (const page of paths) {
    const file = path.join(root, page);
    await mkdir(path.dirname(file), { recursive: true });
    await writeFile(file, "# Fixture\n", "utf8");
  }
}

test("accepts complete navigation and excludes home and agent files", async () => {
  await withDocs(async (root) => {
    await addPages(root, [
      "index.md",
      "AGENTS.md",
      "guide.md",
      "architecture/decisions/index.md",
      "architecture/decisions/0001-example.md",
    ]);
    const source = config(
      '{ text: "Guide", link: "/guide" }',
      `
        { text: "Guide", link: "/guide" },
        { text: "Decisions", items: [
          { text: "Index", link: "/architecture/decisions/" },
          { text: "ADR", link: "/architecture/decisions/0001-example" },
        ] },
      `,
    );

    assert.deepEqual(
      validateDocumentationNavigation(root, source),
      [],
    );
  });
});

test("reports published pages missing from the sidebar", async () => {
  await withDocs(async (root) => {
    await addPages(root, ["guide.md", "container/scopes.md"]);
    const source = config(
      '{ text: "Guide", link: "/guide" }',
      '{ text: "Guide", link: "/guide" }',
    );

    const errors = validateDocumentationNavigation(root, source);

    assert.ok(
      errors.some((error) => error.includes("container/scopes.md")),
    );
    assert.ok(
      errors.some((error) => error.includes("missing from the sidebar")),
    );
  });
});

test("reports nonexistent links from both navigation areas", async () => {
  await withDocs(async (root) => {
    await addPages(root, ["guide.md"]);
    const source = config(
      '{ text: "Broken nav", link: "/missing-nav" }',
      `
        { text: "Guide", link: "/guide" },
        { text: "Broken sidebar", link: "/missing-sidebar" },
      `,
    );

    const errors = validateDocumentationNavigation(root, source);

    assert.ok(errors.some((error) => error.includes("missing-nav")));
    assert.ok(errors.some((error) => error.includes("missing-sidebar")));
  });
});

test("reports duplicate sidebar destinations after URL normalization", async () => {
  await withDocs(async (root) => {
    await addPages(root, ["container/index.md"]);
    const source = config(
      '{ text: "Container", link: "/container/" }',
      `
        { text: "Container", link: "/container/" },
        { text: "Same page", link: "/container/index" },
      `,
    );

    const errors = validateDocumentationNavigation(root, source);

    assert.ok(errors.some((error) => error.includes("Duplicate sidebar")));
  });
});

test("reports missing nav or sidebar arrays", async () => {
  const errors = validateDocumentationNavigation(
    tmpdir(),
    "export default { themeConfig: {} };",
  );

  assert.ok(errors.some((error) => error.includes("nav array")));
  assert.ok(errors.some((error) => error.includes("sidebar array")));
});
