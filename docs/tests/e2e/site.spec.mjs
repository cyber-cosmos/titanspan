import assert from "node:assert/strict";
import { mkdir, readdir } from "node:fs/promises";
import path from "node:path";

import { expect, test } from "@playwright/test";

const viewportWidths = [320, 375, 768, 1024, 1280, 1440, 1920, 2560];
const sampleRoutes = [
  "./",
  "./getting-started/installation",
  "./architecture/",
  "./http/streaming",
  "./logging/configuration",
  "./container/index",
  "./container/method-bindings",
  "./specifications/container",
];
const screenshotDirectory = path.join(process.cwd(), "screenshots");

test.beforeEach(async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 400 && new URL(response.url()).origin === "http://127.0.0.1:4321") {
      errors.push(`${response.status()} ${response.url()}`);
    }
  });
  page.setDefaultTimeout(10_000);
  page.__browserErrors = errors;
});

test.afterEach(async ({ page }) => {
  expect(page.__browserErrors).toEqual([]);
});

test("all requested widths render key pages in both themes", async ({ page }) => {
  test.setTimeout(180_000);
  for (const theme of ["light", "dark"]) {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("./", { waitUntil: "domcontentloaded" });
    await setTheme(page, theme);
    if (theme === "light") {
      await expect(
        page.locator(
          '.is-terminal button[title="Copy to clipboard"]',
        ).first(),
      ).toHaveAttribute("data-code", /git clone/);
    }
    for (const width of viewportWidths) {
      await page.setViewportSize({ width, height: 1000 });
      for (const route of sampleRoutes) {
        const response = await page.goto(route, { waitUntil: "domcontentloaded" });
        expect(response?.status()).toBe(200);
        await expect(page.locator("main h1")).toBeVisible();
        await expect.poll(() => page.evaluate(() => document.documentElement.dataset.theme)).toBe(theme);
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth),
          `${width}px ${theme} ${route} should not overflow horizontally`,
        ).toBeLessThanOrEqual(width + 1);
        await expectAssetsUseBasePath(page);
      }
    }
  }
});

test("mobile navigation, nested sidebar, keyboard use, and search work", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("./architecture/", { waitUntil: "domcontentloaded" });

  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toHaveAttribute("class", /skip-link/);
  await page.keyboard.press("Enter");
  expect(new URL(page.url()).hash).toBe("#_top");

  const menuButton = page.getByRole("button", { name: /Menu/ });
  await menuButton.click();
  const sidebar = page.locator("#starlight__sidebar");
  await expect.poll(() => sidebar.evaluate((element) => element.matches(":popover-open"))).toBe(true);
  const decisionGroup = sidebar
    .locator("summary")
    .filter({ hasText: "Architecture Decision Records" });
  await expect(decisionGroup).toBeVisible();
  await decisionGroup.focus();
  await page.keyboard.press("Enter");
  await expect(sidebar.getByRole("link", { name: /ADR 0005.*Dishka Service Container/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect.poll(() => sidebar.evaluate((element) => element.matches(":popover-open"))).toBe(false);
  await expect(menuButton).toBeFocused();

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.reload({ waitUntil: "domcontentloaded" });
  const desktopSidebar = page.locator("#starlight__sidebar");
  await expect(
    desktopSidebar.getByRole("link", { name: /ADR 0005.*Dishka Service Container/ }),
  ).toBeVisible();
  const longNavigationLabel = desktopSidebar.getByRole("link", {
    name: "Automatic dependency resolution",
    exact: true,
  });
  await expect(longNavigationLabel).toBeVisible();
  expect(
    await longNavigationLabel.evaluate(
      (element) => element.scrollWidth <= element.clientWidth,
    ),
  ).toBe(true);

  const searchButton = page.getByRole("button", { name: "Search" });
  await expect(searchButton).toBeEnabled();
  await searchButton.click();
  const searchBox = page.locator('dialog input[type="text"]');
  await expect(searchBox).toBeVisible();
  await searchBox.fill("execution scopes");
  await expect(page.getByRole("link", { name: /Execution scopes/ }).first()).toBeVisible();

  await page.goto("./container/scopes#execution-scopes", { waitUntil: "domcontentloaded" });
  await expect(page.locator("#execution-scopes")).toHaveCount(1);
  expect(new URL(page.url()).pathname).toBe("/framework/container/scopes");
  await expect(page.getByRole("link", { name: "Edit page" })).toHaveAttribute(
    "href",
    "https://github.com/titanspan/framework/edit/main/docs/src/content/docs/container/scopes.md",
  );
});

test("legacy clean and directory-index URLs resolve under the Pages base", async ({ page }) => {
  for (const route of [
    "./architecture/",
    "./architecture",
    "./architecture.html",
    "./container/scopes",
    "./container/scopes.html",
    "./getting-started/installation",
    "./404.html",
  ]) {
    const response = await page.goto(route, { waitUntil: "domcontentloaded" });
    expect(response?.status(), route).toBe(200);
    await expect(page.locator("main h1")).toBeVisible();
  }
  await expectAssetsUseBasePath(page);
});

test("all rendered documentation links and anchors resolve", async ({ page }) => {
  test.setTimeout(180_000);
  const routes = await collectRenderedRoutes(path.join(process.cwd(), "dist"));
  const internalTargets = new Map();
  const testPort = process.env.TITANSPAN_DOCS_TEST_PORT ?? "4321";
  const base = new URL(`http://127.0.0.1:${testPort}/framework/`);

  for (const route of routes) {
    await page.goto(route, { waitUntil: "domcontentloaded" });
    const links = await page.locator("a[href]").evaluateAll((elements) =>
      elements.map((element) => element.href),
    );
    for (const link of links) {
      const target = new URL(link);
      if (
        target.origin !== base.origin ||
        !target.pathname.startsWith(`${base.pathname}`)
      ) {
        continue;
      }
      target.hash = "";
      const key = target.href;
      if (!internalTargets.has(key)) internalTargets.set(key, new Set());
      const fragment = new URL(link).hash.slice(1);
      if (fragment) internalTargets.get(key).add(decodeURIComponent(fragment));
    }
  }

  for (const [target, fragments] of internalTargets) {
    const response = await page.request.get(target);
    expect(response.status(), target).toBe(200);
    if (fragments.size === 0) continue;
    const html = await response.text();
    for (const fragment of fragments) {
      const escaped = fragment.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&");
      expect(
        html,
        `${target} should contain the anchor #${fragment}`,
      ).toMatch(new RegExp(`\\bid=["']${escaped}["']`));
    }
  }
});

test("captures representative pages in light and dark modes", async ({ page }) => {
  await mkdir(screenshotDirectory, { recursive: true });
  const captures = [
    { route: "./", name: "home", width: 1440 },
    { route: "./container/method-bindings", name: "module", width: 1440 },
    { route: "./logging/configuration", name: "tablet-table", width: 768 },
    { route: "./http/streaming", name: "mobile-module", width: 375 },
  ];

  for (const capture of captures) {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("./", { waitUntil: "domcontentloaded" });
    for (const theme of ["light", "dark"]) {
      await page.setViewportSize({ width: 1440, height: 1000 });
      await setTheme(page, theme);
      await page.setViewportSize({ width: capture.width, height: 1000 });
      await page.goto(capture.route, { waitUntil: "domcontentloaded" });
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({
        path: path.join(
          screenshotDirectory,
          `${capture.name}-${capture.width}-${theme}.png`,
        ),
        fullPage: true,
      });
    }
  }
});

async function setTheme(page, theme) {
  await page.locator("starlight-theme-select select").first().selectOption(theme);
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.theme)).toBe(theme);
}

async function expectAssetsUseBasePath(page) {
  await expect(page.locator('link[rel*="icon"]')).toHaveAttribute(
    "href",
    "/framework/titanspan-mark.png",
  );
  const unbased = await page.evaluate(() => {
    const attrs = [
      ["a", "href"],
      ["img", "src"],
      ["script", "src"],
      ["link[rel=stylesheet]", "href"],
    ];
    return attrs.flatMap(([selector, attribute]) =>
      Array.from(document.querySelectorAll(selector))
        .map((element) => element.getAttribute(attribute))
        .filter(
          (value) =>
            value?.startsWith("/") &&
            value !== "/framework" &&
            !value.startsWith("/framework/"),
        ),
    );
  });
  assert.deepEqual(unbased, []);
}

async function collectRenderedRoutes(directory, relative = "") {
  const entries = await readdir(path.join(directory, relative), {
    withFileTypes: true,
  });
  const routes = [];
  for (const entry of entries) {
    const child = path.join(relative, entry.name);
    if (entry.isDirectory() && !entry.name.startsWith("_")) {
      routes.push(...(await collectRenderedRoutes(directory, child)));
    } else if (entry.isFile() && entry.name === "index.html") {
      const suffix = relative ? `${relative.split(path.sep).join("/")}/` : "";
      routes.push(`/framework/${suffix}`);
    }
  }
  return routes;
}
