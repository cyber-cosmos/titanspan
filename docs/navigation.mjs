/**
 * Define the single Starlight sidebar used by the site and its coverage check.
 * Existing directories autogenerate entries so newly added pages inherit the
 * same navigation and theme without page-specific layout work.
 */
export const documentationSidebar = [
  {
    label: "Getting started",
    items: [
      "getting-started/installation",
      "getting-started/hello-world",
    ],
  },
  {
    label: "Application development",
    items: [
      {
        label: "Application foundation",
        items: [{ autogenerate: { directory: "foundation" } }],
      },
      {
        label: "Core concepts",
        items: [{ autogenerate: { directory: "basics" } }],
      },
      {
        label: "Deployment",
        items: [{ autogenerate: { directory: "deployment" } }],
      },
      {
        label: "Testing",
        items: [{ autogenerate: { directory: "testing" } }],
      },
    ],
  },
  {
    label: "Framework components",
    items: [
      {
        label: "Service container",
        items: [{ autogenerate: { directory: "container" } }],
      },
      {
        label: "Configuration",
        items: [{ autogenerate: { directory: "config" } }],
      },
      {
        label: "Facades",
        items: [{ autogenerate: { directory: "facades" } }],
      },
      {
        label: "Contracts",
        items: [{ autogenerate: { directory: "contracts" } }],
      },
      {
        label: "HTTP",
        items: [{ autogenerate: { directory: "http" } }],
      },
      {
        label: "Routing",
        items: [{ autogenerate: { directory: "routing" } }],
      },
      {
        label: "Events",
        items: [{ autogenerate: { directory: "events" } }],
      },
      {
        label: "Filesystem",
        items: [{ autogenerate: { directory: "filesystem" } }],
      },
      {
        label: "Logging",
        items: [{ autogenerate: { directory: "logging" } }],
      },
      {
        label: "Pipeline",
        items: [{ autogenerate: { directory: "pipeline" } }],
      },
      {
        label: "Validation",
        items: [{ autogenerate: { directory: "validation" } }],
      },
      {
        label: "Collections",
        items: [{ autogenerate: { directory: "collections" } }],
      },
      {
        label: "Support",
        items: [{ autogenerate: { directory: "support" } }],
      },
    ],
  },
  {
    label: "Planned modules",
    collapsed: true,
    items: [
      {
        label: "AI",
        items: [{ autogenerate: { directory: "ai" } }],
      },
      {
        label: "Concurrency",
        items: [{ autogenerate: { directory: "concurrency" } }],
      },
      {
        label: "Data processing",
        items: [{ autogenerate: { directory: "data-processing" } }],
      },
      {
        label: "Database",
        items: [{ autogenerate: { directory: "database" } }],
      },
      {
        label: "Workflows",
        items: [{ autogenerate: { directory: "workflows" } }],
      },
    ],
  },
  {
    label: "Architecture and internals",
    items: [
      {
        label: "Architecture",
        items: [
          "architecture",
          "architecture/contract-integration",
          "architecture/framework-review",
          {
            label: "Architecture Decision Records",
            collapsed: true,
            items: [
              { autogenerate: { directory: "architecture/decisions" } },
            ],
          },
        ],
      },
      {
        label: "Engineering specifications",
        items: [{ autogenerate: { directory: "specifications" } }],
      },
    ],
  },
  {
    label: "Contributors",
    items: [{ autogenerate: { directory: "development" } }],
  },
];
