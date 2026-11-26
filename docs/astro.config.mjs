import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

import { documentationSidebar } from "./navigation.mjs";

export default defineConfig({
  site: "https://titanspan.github.io",
  base: "/titanspan",
  output: "static",
  trailingSlash: "ignore",
  build: {
    format: "directory",
  },
  integrations: [
    starlight({
      title: "Titanspan",
      description:
        "An async-first Python application framework for intelligent systems.",
      logo: {
        src: "../assets/logo.png",
        alt: "Titanspan",
      },
      favicon: "/titanspan-mark.png",
      tableOfContents: {
        minHeadingLevel: 2,
        maxHeadingLevel: 3,
      },
      editLink: {
        baseUrl: "https://github.com/titanspan/titanspan/edit/main/docs/",
      },
      sidebar: documentationSidebar,
      customCss: ["./src/styles/titanspan-brand.css"],
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/titanspan/titanspan",
        },
      ],
      pagefind: true,
      pagination: true,
      disable404Route: true,
    }),
  ],
});
