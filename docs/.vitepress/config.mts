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
        link: "https://github.com/Cyber-Cosmos/titanspan/blob/main/ROADMAP.md",
      },
      {
        text: "GitHub",
        link: "https://github.com/Cyber-Cosmos/titanspan",
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
        text: "Project",
        items: [
          { text: "Testing", link: "/testing/" },
          { text: "Deployment", link: "/deployment/" },
        ],
      },
    ],
    socialLinks: [
      { icon: "github", link: "https://github.com/Cyber-Cosmos/titanspan" },
    ],
    footer: {
      message: "Licensed under the MIT License.",
      copyright: "Copyright © 2026 Cyber Cosmos",
    },
  },
});
