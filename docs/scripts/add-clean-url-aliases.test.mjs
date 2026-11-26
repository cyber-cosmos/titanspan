import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { addCleanUrlAliases } from "./add-clean-url-aliases.mjs";

test("adds clean path aliases for nested directory pages", async () => {
  const dist = await mkdtemp(path.join(tmpdir(), "titanspan-site-"));
  try {
    await mkdir(path.join(dist, "architecture"), { recursive: true });
    await mkdir(path.join(dist, "container", "scopes"), {
      recursive: true,
    });
    await writeFile(path.join(dist, "index.html"), "home", "utf8");
    await writeFile(
      path.join(dist, "architecture", "index.html"),
      "architecture",
      "utf8",
    );
    await writeFile(
      path.join(dist, "container", "scopes", "index.html"),
      "scopes",
      "utf8",
    );

    await addCleanUrlAliases(dist);

    assert.equal(
      await readFile(path.join(dist, "architecture.html"), "utf8"),
      "architecture",
    );
    assert.equal(
      await readFile(path.join(dist, "container", "scopes.html"), "utf8"),
      "scopes",
    );
    assert.equal(await readFile(path.join(dist, "index.html"), "utf8"), "home");
  } finally {
    await rm(dist, { recursive: true, force: true });
  }
});

test("does not overwrite a conflicting clean URL file", async () => {
  const dist = await mkdtemp(path.join(tmpdir(), "titanspan-site-"));
  try {
    await mkdir(path.join(dist, "architecture"), { recursive: true });
    await writeFile(
      path.join(dist, "architecture", "index.html"),
      "page",
      "utf8",
    );
    await writeFile(path.join(dist, "architecture.html"), "other", "utf8");

    await assert.rejects(addCleanUrlAliases(dist), /collides with/);
  } finally {
    await rm(dist, { recursive: true, force: true });
  }
});
