import { defineConfig } from "vitepress";

const isGitHubPages = process.env.GITHUB_ACTIONS === "true";

export default defineConfig({
  title: "Titanspan",
  description: "Engineer beyond limits.",
  base: isGitHubPages ? "/titanspan/" : "/",
  cleanUrls: true,
  themeConfig: {
    nav: [
      { text: "Guide", link: "/getting-started/installation" },
      { text: "Architecture", link: "/architecture/" },
      {
        text: "Roadmap",
        link: "https://github.com/titanspan/titanspan/blob/main/ROADMAP.md",
      },
      {
        text: "GitHub",
        link: "https://github.com/titanspan/titanspan",
      },
    ],
    sidebar: [
      {
        text: "Getting started",
        items: [
          { text: "Installation", link: "/getting-started/installation" },
          { text: "Hello World", link: "/getting-started/hello-world" },
        ],
      },
      {
        text: "Architecture",
        items: [
          { text: "Overview", link: "/architecture/" },
          { text: "Basics", link: "/basics/" },
        ],
      },
      {
        text: "Planned modules",
        items: [
          { text: "Database", link: "/database/" },
          { text: "Concurrency", link: "/concurrency/" },
          { text: "Data processing", link: "/data-processing/" },
          { text: "AI", link: "/ai/" },
          { text: "Workflows", link: "/workflows/" },
        ],
      },
      {
        text: "Configuration",
        items: [
          { text: "Overview", link: "/config/" },
          { text: "Repository", link: "/config/repository" },
          { text: "Environment", link: "/config/environment" },
          {
            text: "Configuration files",
            link: "/config/configuration-files",
          },
          { text: "Typed settings", link: "/config/typed-settings" },
          { text: "Precedence", link: "/config/precedence" },
          { text: "Package defaults", link: "/config/package-defaults" },
          { text: "Caching and commands", link: "/config/caching" },
          { text: "Overrides", link: "/config/overrides" },
          { text: "Testing", link: "/config/testing" },
          { text: "Security", link: "/config/security" },
          {
            text: "Laravel compatibility",
            link: "/compatibility/laravel-config",
          },
        ],
      },
      {
        text: "Logging",
        items: [
          { text: "Overview", link: "/logging/" },
          { text: "Configuration", link: "/logging/configuration" },
          { text: "Channels", link: "/logging/channels" },
          { text: "Drivers", link: "/logging/drivers" },
          { text: "Context", link: "/logging/context" },
          {
            text: "Structured logging",
            link: "/logging/structured-logging",
          },
          { text: "Async logging", link: "/logging/async-logging" },
          { text: "Security", link: "/logging/security" },
          { text: "Testing", link: "/logging/testing" },
          { text: "Deployment", link: "/logging/deployment" },
          {
            text: "Laravel compatibility",
            link: "/compatibility/laravel-logging",
          },
        ],
      },
      {
        text: "Support",
        items: [
          { text: "Overview", link: "/support/" },
          { text: "Arrays", link: "/support/arrays" },
          { text: "Environment", link: "/support/environment" },
          { text: "Fluent", link: "/support/fluent" },
          {
            text: "Forwarded calls",
            link: "/support/forwards-calls",
          },
          { text: "Helpers", link: "/support/helpers" },
          { text: "Message bags", link: "/support/message-bag" },
          { text: "Optional values", link: "/support/optional" },
          { text: "Strings", link: "/support/strings" },
          { text: "Fluent strings", link: "/support/stringable" },
          { text: "Numbers", link: "/support/numbers" },
          { text: "Binary codecs", link: "/support/binary-codecs" },
          {
            text: "Configuration URLs",
            link: "/support/configuration-urls",
          },
          {
            text: "Namespaced items",
            link: "/support/namespaced-items",
          },
          { text: "URI utilities", link: "/support/uris" },
          { text: "Timing utilities", link: "/support/timing" },
          { text: "Sleep", link: "/support/sleep" },
          { text: "HTML values", link: "/support/html" },
          { text: "Extensions", link: "/support/extensions" },
          {
            text: "Laravel compatibility",
            link: "/compatibility/laravel-support",
          },
        ],
      },
      {
        text: "Contracts",
        items: [
          { text: "Overview", link: "/contracts/" },
          {
            text: "Dependency injection",
            link: "/contracts/dependency-injection",
          },
          {
            text: "Implementing contracts",
            link: "/contracts/implementing-contracts",
          },
          { text: "Testing contracts", link: "/contracts/testing" },
          {
            text: "Laravel compatibility",
            link: "/compatibility/laravel-contracts",
          },
        ],
      },
      {
        text: "Project",
        items: [
          { text: "Testing", link: "/testing/" },
          { text: "Deployment", link: "/deployment/" },
          { text: "Development standards", link: "/development/standards" },
          {
            text: "Continuous integration",
            link: "/development/continuous-integration",
          },
          {
            text: "AI agent compatibility",
            link: "/development/agent-compatibility",
          },
        ],
      },
    ],
    socialLinks: [
      { icon: "github", link: "https://github.com/titanspan/titanspan" },
    ],
    footer: {
      message: "Licensed under the MIT License.",
      copyright: "Copyright © 2026 Titanspan",
    },
  },
});
