<script setup lang="ts">
import { computed } from "vue";
import { useData, withBase } from "vitepress";

const { page } = useData();

const sectionLabel = computed(() => {
  const directory = page.value.relativePath.split("/")[0] ?? "";
  const labels: Readonly<Record<string, string>> = {
    "getting-started": "Getting started",
    architecture: "Architecture",
    basics: "Core concepts",
    config: "Configuration",
    container: "Service container",
    contracts: "Contracts",
    development: "Engineering",
    deployment: "Deployment",
    http: "HTTP",
    logging: "Logging",
    specifications: "Framework specifications",
    support: "Support",
    testing: "Testing",
  };

  if (labels[directory] !== undefined) {
    return labels[directory];
  }

  return directory
    .replaceAll("-", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
});
</script>

<template>
  <nav class="ts-breadcrumbs" aria-label="Breadcrumb">
    <ol>
      <li>
        <a :href="withBase('/')">Docs</a>
      </li>
      <li aria-hidden="true">/</li>
      <li>{{ sectionLabel }}</li>
      <li aria-hidden="true">/</li>
      <li>
        <span aria-current="page">{{ page.title }}</span>
      </li>
    </ol>
  </nav>
</template>
