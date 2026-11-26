import { defineConfig } from "@playwright/test";

const testPort = process.env.TITANSPAN_DOCS_TEST_PORT ?? "4321";
const baseURL = `http://127.0.0.1:${testPort}/titanspan/`;

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 120_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  reporter: "list",
  outputDir: "./test-results",
  use: {
    baseURL,
    viewport: { width: 1440, height: 1000 },
    colorScheme: "light",
    reducedMotion: "reduce",
    trace: "retain-on-failure",
  },
  webServer: {
    command: `npm run docs:preview -- --host 127.0.0.1 --port ${testPort} --ignore-lock`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
