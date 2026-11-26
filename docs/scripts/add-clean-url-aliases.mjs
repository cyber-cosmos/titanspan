import { copyFile, mkdir, readdir, readFile, stat } from "node:fs/promises";
import { constants } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_DIST = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../dist",
);

/**
 * Add `.html` aliases for directory pages in a static site build.
 *
 * GitHub Pages serves extensionless clean URLs from sibling `.html` files,
 * while Starlight's directory output serves the same route with a slash.
 * Emitting both forms keeps existing Titanspan URLs available.
 *
 * @param {string} distRoot Built documentation directory.
 * @returns {Promise<void>} Completion of the alias generation.
 */
export async function addCleanUrlAliases(distRoot = DEFAULT_DIST) {
  const root = path.resolve(distRoot);
  const indexFiles = await collectIndexFiles(root);

  for (const indexFile of indexFiles) {
    if (indexFile === path.join(root, "index.html")) {
      continue;
    }
    const pageDirectory = path.dirname(indexFile);
    const alias = path.join(
      path.dirname(pageDirectory),
      `${path.basename(pageDirectory)}.html`,
    );
    await ensureAlias(indexFile, alias);
  }
}

/**
 * Collect every generated directory index below a site root.
 *
 * @param {string} root Built documentation directory.
 * @returns {Promise<string[]>} Absolute index file paths.
 */
async function collectIndexFiles(root) {
  const found = [];
  const pending = [root];

  while (pending.length > 0) {
    const current = pending.pop();
    if (current === undefined) {
      continue;
    }
    for (const entry of await readdir(current, { withFileTypes: true })) {
      const absolute = path.join(current, entry.name);
      if (entry.isDirectory()) {
        pending.push(absolute);
      } else if (entry.isFile() && entry.name === "index.html") {
        found.push(absolute);
      }
    }
  }

  return found;
}

/**
 * Create an alias without replacing conflicting generated output.
 *
 * @param {string} source Starlight directory index page.
 * @param {string} alias Clean URL `.html` file.
 * @returns {Promise<void>} Completion of alias creation or validation.
 */
async function ensureAlias(source, alias) {
  try {
    await copyFile(source, alias, constants.COPYFILE_EXCL);
  } catch (error) {
    if (!isExistingFileError(error)) {
      throw error;
    }
    const [sourceContents, aliasContents] = await Promise.all([
      readFile(source),
      readFile(alias),
    ]);
    if (!sourceContents.equals(aliasContents)) {
      throw new Error(`Clean URL alias collides with existing file: ${alias}`);
    }
  }
  await mkdir(path.dirname(alias), { recursive: true });
  const aliasStats = await stat(alias);
  if (!aliasStats.isFile()) {
    throw new Error(`Clean URL alias is not a file: ${alias}`);
  }
}

/**
 * Identify an existing destination error from exclusive file creation.
 *
 * @param {unknown} error Error raised by copyFile.
 * @returns {boolean} Whether the destination already exists.
 */
function isExistingFileError(error) {
  return (
    error instanceof Error &&
    "code" in error &&
    error.code === "EEXIST"
  );
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  await addCleanUrlAliases(process.argv[2] ?? DEFAULT_DIST);
}
