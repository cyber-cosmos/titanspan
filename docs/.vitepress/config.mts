import { defineConfig } from "vitepress";

const isGitHubPages = process.env.GITHUB_ACTIONS === "true";
const base = isGitHubPages ? "/titanspan/" : "/";

export default defineConfig({
  title: "Titanspan",
  description: "Engineer beyond limits.",
  base,
  cleanUrls: true,
  appearance: true,
  head: [
    [
      "link",
      {
        rel: "icon",
        type: "image/png",
        href: `${base}titanspan-mark.png`,
      },
    ],
  ],
  themeConfig: {
    logo: {
      light: "/titanspan-mark.png",
      dark: "/titanspan-mark.png",
      alt: "Titanspan",
    },
    search: {
      provider: "local",
    },
    editLink: {
      pattern: "https://github.com/titanspan/titanspan/edit/main/docs/:path",
      text: "Edit this page",
    },
    nav: [
      { text: "Guide", link: "/getting-started/installation" },
      { text: "Architecture", link: "/architecture/" },
      {
        text: "Components",
        items: [
          { text: "Configuration", link: "/config/" },
          { text: "Collections", link: "/collections/" },
          { text: "Service Container", link: "/container/" },
          { text: "Contracts", link: "/contracts/" },
          { text: "HTTP", link: "/http/" },
          { text: "Logging", link: "/logging/" },
          { text: "Routing", link: "/routing/" },
          { text: "Support", link: "/support/" },
        ],
      },
      {
        text: "Development",
        items: [
          {
            text: "Architecture decisions",
            link: "/architecture/decisions/",
          },
          {
            text: "Development guides",
            link: "/development/agent-workflow",
          },
          {
            text: "Technical writing",
            link: "/development/writing-standards",
          },
          { text: "Glossary", link: "/development/glossary" },
          {
            text: "Continuous integration",
            link: "/development/continuous-integration",
          },
        ],
      },
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
        collapsed: true,
        items: [
          { text: "Installation", link: "/getting-started/installation" },
          { text: "Hello World", link: "/getting-started/hello-world" },
        ],
      },
      {
        text: "Architecture",
        collapsed: true,
        items: [
          { text: "Overview", link: "/architecture/" },
          { text: "Basics", link: "/basics/" },
          {
            text: "Contract integration audit",
            link: "/architecture/contract-integration",
          },
          {
            text: "Architecture Decision Records",
            collapsed: true,
            items: [
              { text: "Index", link: "/architecture/decisions/" },
              {
                text: "0001 — Modular monolith",
                link: "/architecture/decisions/0001-modular-monolith",
              },
              {
                text: "0002 — Async-first architecture",
                link: "/architecture/decisions/0002-async-first-architecture",
              },
              {
                text: "0003 — uv package management",
                link: "/architecture/decisions/0003-uv-package-management",
              },
              {
                text: "0004 — FastAPI web foundation",
                link: "/architecture/decisions/0004-fastapi-web-foundation",
              },
              {
                text: "0005 — Service container backend",
                link: "/architecture/decisions/0005-dishka-service-container",
              },
              {
                text: "0006 — SQLAlchemy persistence",
                link: "/architecture/decisions/0006-sqlalchemy-persistence",
              },
              {
                text: "0007 — LangGraph orchestration",
                link: "/architecture/decisions/0007-langgraph-orchestration",
              },
              {
                text: "0008 — Structured concurrency",
                link: "/architecture/decisions/0008-structured-concurrency",
              },
              {
                text: "0009 — Contract-driven adapters",
                link: "/architecture/decisions/0009-contract-driven-adapters",
              },
              {
                text: "0010 — Optional dependencies",
                link: "/architecture/decisions/0010-optional-dependencies",
              },
              {
                text: "0011 — Testing and quality standards",
                link: "/architecture/decisions/0011-testing-and-quality-standards",
              },
              {
                text: "0012 — Native logging",
                link: "/architecture/decisions/0012-native-logging",
              },
              {
                text: "0013 — Native configuration",
                link: "/architecture/decisions/0013-native-configuration",
              },
              {
                text: "0014 — Native service container API",
                link: "/architecture/decisions/0014-native-container-api",
              },
              {
                text: "0015 — Synchronous-first resolution",
                link: "/architecture/decisions/0015-sync-first-container-resolution",
              },
              {
                text: "0016 — Native Python API naming",
                link: "/architecture/decisions/0016-native-python-api-naming",
              },
              {
                text: "0017 — Domain-oriented contracts",
                link: "/architecture/decisions/0017-domain-oriented-contracts",
              },
              {
                text: "0018 — Application service composition",
                link: "/architecture/decisions/0018-application-service-composition",
              },
              {
                text: "0019 — Contextual container services",
                link: "/architecture/decisions/0019-contextual-container-services",
              },
              {
                text: "0020 — Native HTTP component",
                link: "/architecture/decisions/0020-native-http-component",
              },
              {
                text: "0021 — Native routing and URI generation",
                link: "/architecture/decisions/0021-native-routing-uri-generation",
              },
            ],
          },
        ],
      },
      {
        text: "Planned modules",
        collapsed: true,
        items: [
          { text: "Database", link: "/database/" },
          { text: "Concurrency", link: "/concurrency/" },
          { text: "Data processing", link: "/data-processing/" },
          { text: "AI", link: "/ai/" },
          { text: "Workflows", link: "/workflows/" },
        ],
      },
      {
        text: "Service Container",
        collapsed: true,
        items: [
          { text: "Overview", link: "/container/" },
          {
            text: "Automatic resolution",
            link: "/container/automatic-resolution",
          },
          { text: "Class declarations", link: "/container/decorators" },
          { text: "Factories", link: "/container/factories" },
          { text: "Injection", link: "/container/injection" },
          {
            text: "Contextual bindings",
            link: "/container/contextual-bindings",
          },
          {
            text: "Extensions and callbacks",
            link: "/container/lifecycle-hooks",
          },
          { text: "Temporary overrides", link: "/container/overrides" },
          {
            text: "Method bindings",
            link: "/container/method-bindings",
          },
          {
            text: "Resource management",
            link: "/container/resource-management",
          },
          { text: "Scopes", link: "/container/scopes" },
          {
            text: "Native specification",
            link: "/specifications/container",
          },
        ],
      },
      {
        text: "Collections",
        items: [
          { text: "Overview", link: "/collections/" },
          { text: "Eager collections", link: "/collections/eager" },
          {
            text: "Grouping and aggregation",
            link: "/collections/operations",
          },
          { text: "Lazy collections", link: "/collections/lazy" },
          {
            text: "Behavioral specification",
            link: "/specifications/collections",
          },
        ],
      },
      {
        text: "Routing",
        items: [
          { text: "Overview", link: "/routing/" },
          {
            text: "URL generation and redirects",
            link: "/routing/url-generation",
          },
          {
            text: "Behavioral specification",
            link: "/specifications/routing",
          },
        ],
      },
      {
        text: "HTTP",
        items: [
          { text: "Overview", link: "/http/" },
          { text: "Incoming requests", link: "/http/requests" },
          { text: "Responses", link: "/http/responses" },
          { text: "Outgoing client", link: "/http/client" },
          { text: "Streaming and SSE", link: "/http/streaming" },
          { text: "Middleware", link: "/http/middleware" },
          {
            text: "Configuration and lifecycle",
            link: "/http/configuration",
          },
          { text: "Security", link: "/http/security" },
          { text: "Testing", link: "/http/testing" },
          {
            text: "Behavioral specification",
            link: "/specifications/http",
          },
        ],
      },
      {
        text: "Configuration",
        collapsed: true,
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
            text: "Native specification",
            link: "/specifications/config",
          },
        ],
      },
      {
        text: "Logging",
        collapsed: true,
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
            text: "Native specification",
            link: "/specifications/logging",
          },
        ],
      },
      {
        text: "Support",
        collapsed: true,
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
            text: "Native specification",
            link: "/specifications/support",
          },
        ],
      },
      {
        text: "Contracts",
        collapsed: true,
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
            text: "Native specification",
            link: "/specifications/contracts",
          },
        ],
      },
      {
        text: "Project",
        collapsed: true,
        items: [
          { text: "Testing", link: "/testing/" },
          { text: "Deployment", link: "/deployment/" },
          {
            text: "Agent workflow",
            link: "/development/agent-workflow",
          },
          { text: "Development standards", link: "/development/standards" },
          {
            text: "Technical writing",
            link: "/development/writing-standards",
          },
          { text: "Glossary", link: "/development/glossary" },
          {
            text: "Continuous integration",
            link: "/development/continuous-integration",
          },
          {
            text: "AI agent compatibility",
            link: "/development/agent-compatibility",
          },
          {
            text: "Public backend boundaries",
            link: "/specifications/backend-boundaries",
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
