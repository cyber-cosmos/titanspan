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
        text: "Project",
        items: [
          { text: "Testing", link: "/testing/" },
          { text: "Deployment", link: "/deployment/" },
          { text: "Development standards", link: "/development/standards" },
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
