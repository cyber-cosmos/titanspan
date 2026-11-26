<template>
  <figure
    class="ts-architecture-map"
    aria-labelledby="ts-architecture-title"
  >
    <header class="ts-map-header">
      <div>
        <p class="ts-map-kicker">APPLICATION COMPOSITION</p>
        <h2 id="ts-architecture-title">One application context</h2>
      </div>
      <span class="ts-map-index">SYSTEM / 01</span>
    </header>
    <div class="ts-map-diagram">
      <div class="ts-map-root">
        <span class="ts-map-code">APP</span>
        <strong>Application</strong>
        <span>Lifecycle and composition</span>
      </div>
      <div class="ts-map-branches" role="list">
        <div class="ts-map-branch" role="listitem">
          <span class="ts-branch-code">01</span>
          <div>
            <strong>Native container</strong>
            <span>Shared service registry</span>
          </div>
        </div>
        <div class="ts-map-branch" role="listitem">
          <span class="ts-branch-code">02</span>
          <div>
            <strong>Service providers</strong>
            <span>Component registration</span>
          </div>
        </div>
        <div class="ts-map-branch" role="listitem">
          <span class="ts-branch-code">03</span>
          <div>
            <strong>FastAPI / ASGI</strong>
            <span>HTTP hosting boundary</span>
          </div>
        </div>
      </div>
    </div>
    <figcaption>
      Framework services share one application context; FastAPI provides the
      current HTTP hosting boundary.
    </figcaption>
  </figure>
</template>
