import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SITE_ORIGIN = "https://docs.titanspan.invalid";
const PAGE_LINK = /\blink\s*:\s*(["'])(.*?)\1/g;

/**
 * Validate VitePress navigation against the published Markdown pages.
 *
 * The checker reads only the literal ``nav`` and ``sidebar`` arrays from the
 * site configuration. External links are left to their destination owners.
 *
 * @param {string} docsRoot Directory containing the VitePress pages.
 * @param {string} configText Source text of the VitePress configuration.
 * @returns {string[]} Human-readable validation failures.
 */
export function validateDocumentationNavigation(docsRoot, configText) {
  const root = path.resolve(docsRoot);
  const errors = [];
  const navigation = new Map();

  for (const name of ["nav", "sidebar"]) {
    const contents = findArray(configText, name);
    if (contents === null) {
      errors.push(`VitePress config is missing the ${name} array.`);
      continue;
    }
    navigation.set(name, extractLinks(contents));
  }

  const sidebarPages = new Set();
  const sidebarRoutes = new Set();
  for (const name of ["nav", "sidebar"]) {
    const links = navigation.get(name) ?? [];
    for (const link of links) {
      const resolved = resolvePage(root, link.value);
      if (resolved === null) {
        if (isInternalLink(link.value)) {
          errors.push(
            `${name} link "${link.value}" does not resolve to a page.`,
          );
        }
        continue;
      }

      if (name !== "sidebar") {
        continue;
      }

      const pageKey = path.relative(root, resolved).split(path.sep).join("/");
      const routeKey = pageKey;
      if (sidebarRoutes.has(routeKey)) {
        errors.push(
          `Duplicate sidebar link "${link.value}" targets ${pageKey}.`,
        );
      }
      sidebarRoutes.add(routeKey);
      sidebarPages.add(pageKey);
    }
  }

  for (const page of collectMarkdownPages(root)) {
    const pageKey = path.relative(root, page).split(path.sep).join("/");
    if (pageKey === "index.md" || pageKey === "AGENTS.md") {
      continue;
    }
    if (!sidebarPages.has(pageKey)) {
      errors.push(`Published page "${pageKey}" is missing from the sidebar.`);
    }
  }

  return errors;
}

/**
 * Find a named bracketed array while ignoring brackets inside comments or
 * quoted strings.
 *
 * @param {string} source VitePress configuration source.
 * @param {string} property Array property to locate.
 * @returns {string | null} Array contents, or null when the field is absent.
 */
function findArray(source, property) {
  const marker = new RegExp(`\\b${property}\\s*:\\s*\\[`).exec(source);
  if (marker === null) {
    return null;
  }

  const opening = marker.index + marker[0].lastIndexOf("[");
  let depth = 0;
  let quote = null;
  let escaped = false;
  let lineComment = false;
  let blockComment = false;

  for (let index = opening; index < source.length; index += 1) {
    const character = source[index];
    const next = source[index + 1];

    if (lineComment) {
      if (character === "\n") {
        lineComment = false;
      }
      continue;
    }
    if (blockComment) {
      if (character === "*" && next === "/") {
        blockComment = false;
        index += 1;
      }
      continue;
    }
    if (quote !== null) {
      if (escaped) {
        escaped = false;
      } else if (character === "\\") {
        escaped = true;
      } else if (character === quote) {
        quote = null;
      }
      continue;
    }
    if (character === "/" && next === "/") {
      lineComment = true;
      index += 1;
      continue;
    }
    if (character === "/" && next === "*") {
      blockComment = true;
      index += 1;
      continue;
    }
    if (character === "\"" || character === "'") {
      quote = character;
      continue;
    }
    if (character === "[") {
      depth += 1;
    } else if (character === "]") {
      depth -= 1;
      if (depth === 0) {
        return source.slice(opening + 1, index);
      }
    }
  }

  return null;
}

/**
 * Extract explicit string-valued navigation links from one config array.
 *
 * @param {string} source Array contents.
 * @returns {{ value: string }[]} Ordered navigation links.
 */
function extractLinks(source) {
  return [...source.matchAll(PAGE_LINK)].map((match) => ({
    value: match[2],
  }));
}

/**
 * Determine whether a link targets the local documentation site.
 *
 * @param {string} link Navigation link.
 * @returns {boolean} Whether the link is local.
 */
function isInternalLink(link) {
  const url = new URL(link, SITE_ORIGIN);
  return url.origin === SITE_ORIGIN;
}

/**
 * Resolve one local VitePress route to an existing Markdown page.
 *
 * @param {string} docsRoot Directory containing the VitePress pages.
 * @param {string} link Navigation link.
 * @returns {string | null} Absolute page path, or null for an invalid target.
 */
function resolvePage(docsRoot, link) {
  const url = new URL(link, SITE_ORIGIN);
  if (url.origin !== SITE_ORIGIN) {
    return null;
  }

  let route = decodeURIComponent(url.pathname);
  if (route === "/") {
    route = "/index.md";
  } else if (route.endsWith(".html")) {
    route = `${route.slice(0, -5)}.md`;
  }

  const relative = route.replace(/^\/+/, "");
  const candidates = route.endsWith(".md")
    ? [path.resolve(docsRoot, relative)]
    : route.endsWith("/")
      ? [path.resolve(docsRoot, relative, "index.md")]
      : [
          path.resolve(docsRoot, `${relative}.md`),
          path.resolve(docsRoot, relative, "index.md"),
        ];

  for (const candidate of candidates) {
    if (isWithin(docsRoot, candidate) && isMarkdownFile(candidate)) {
      return candidate;
    }
  }
  return null;
}

/**
 * Check whether a candidate is a Markdown file.
 *
 * @param {string} candidate Candidate page path.
 * @returns {boolean} Whether the file exists and has a Markdown suffix.
 */
function isMarkdownFile(candidate) {
  return path.extname(candidate).toLowerCase() === ".md" && existsSync(candidate);
}

/**
 * Prevent navigation routes from resolving outside the documentation root.
 *
 * @param {string} root Documentation directory.
 * @param {string} candidate Candidate file path.
 * @returns {boolean} Whether candidate is contained by root.
 */
function isWithin(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative !== ".." && !relative.startsWith(`..${path.sep}`);
}

/**
 * Collect publishable Markdown pages while excluding tooling directories and
 * internal instruction files.
 *
 * @param {string} root Documentation directory.
 * @returns {string[]} Absolute paths to Markdown pages.
 */
function collectMarkdownPages(root) {
  const pages = [];
  const ignoredDirectories = new Set([
    ".vitepress",
    "node_modules",
    "dist",
    ".cache",
  ]);

  function visit(directory) {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      if (entry.isDirectory() && ignoredDirectories.has(entry.name)) {
        continue;
      }
      const absolute = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        visit(absolute);
      } else if (
        entry.isFile() &&
        entry.name !== "AGENTS.md" &&
        path.extname(entry.name).toLowerCase() === ".md"
      ) {
        pages.push(absolute);
      }
    }
  }

  visit(root);
  return pages;
}

function main() {
  const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
  const docsRoot = path.resolve(scriptDirectory, "..");
  const configPath = path.join(docsRoot, ".vitepress", "config.mts");
  const configText = readFileSync(configPath, "utf8");
  const errors = validateDocumentationNavigation(docsRoot, configText);

  if (errors.length > 0) {
    for (const error of errors) {
      console.error(error);
    }
    process.exitCode = 1;
    return;
  }

  console.log("Documentation navigation check passed.");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
