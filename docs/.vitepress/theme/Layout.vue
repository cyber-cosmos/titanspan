<script setup lang="ts">
import DefaultTheme from "vitepress/theme";

import HomeArchitecture from "./components/HomeArchitecture.vue";
import HomeHeroInfo from "./components/HomeHeroInfo.vue";
import PageBreadcrumbs from "./components/PageBreadcrumbs.vue";

const { Layout } = DefaultTheme;
</script>

<template>
  <Layout>
    <template #nav-bar-title-after>
      <span class="ts-nav-context">DOCUMENTATION</span>
    </template>
    <template #home-hero-info>
      <HomeHeroInfo />
    </template>
    <template #home-hero-image>
      <HomeArchitecture />
    </template>
    <template #doc-top>
      <PageBreadcrumbs />
    </template>
  </Layout>
</template>
