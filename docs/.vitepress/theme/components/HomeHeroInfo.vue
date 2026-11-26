<script setup lang="ts">
import { withBase } from "vitepress";
</script>

<template>
  <div class="ts-home-hero-copy">
    <p class="ts-overline">
      <span class="ts-overline-rule" aria-hidden="true"></span>
      PYTHON APPLICATION FRAMEWORK
    </p>
    <h1>
      <span class="ts-home-wordmark">Titanspan</span>
      <span class="ts-home-title">Engineer beyond limits.</span>
    </h1>
    <p class="ts-home-description">
      An async-first Python framework with a shared service registry,
      explicit application lifecycles, and proven libraries at its core.
    </p>
    <div class="ts-home-actions">
      <a
        class="ts-button ts-button-primary"
        :href="withBase('/getting-started/installation')"
      >
        Get started
      </a>
      <a
        class="ts-button ts-button-secondary"
        :href="withBase('/architecture/')"
      >
        Explore the architecture
        <span aria-hidden="true">→</span>
      </a>
    </div>
    <p class="ts-release-note">
      <span>0.1.0.dev0</span>
      <span aria-hidden="true">·</span>
      <span>Pre-alpha</span>
      <span aria-hidden="true">·</span>
      <span>Not yet published to PyPI</span>
    </p>
  </div>
</template>
