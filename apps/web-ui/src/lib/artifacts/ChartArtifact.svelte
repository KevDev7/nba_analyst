<script lang="ts">
  import { chartRenderModel } from "$lib/charts/chartModel";
  import type { ChartArtifact } from "./types";

  let { artifact }: { artifact: ChartArtifact } = $props();
  let renderError = $state("");
  const chartModel = $derived(chartRenderModel(artifact));

  function vegaLiteChart(node: HTMLDivElement, currentArtifact: ChartArtifact) {
    let disposed = false;
    let view: { finalize: () => void } | null = null;

    async function renderChart(nextArtifact: ChartArtifact) {
      renderError = "";
      view?.finalize();
      view = null;
      node.replaceChildren();
      if (nextArtifact.renderer !== "vega_lite") {
        return;
      }
      try {
        const { default: embed } = await import("vega-embed");
        if (disposed) {
          return;
        }
        const result = await embed(node, JSON.parse(JSON.stringify(nextArtifact.spec)), {
          actions: false,
          renderer: "canvas"
        });
        view = result.view;
      } catch (caught) {
        renderError = caught instanceof Error ? caught.message : String(caught);
      }
    }

    void renderChart(currentArtifact);

    return {
      update(nextArtifact: ChartArtifact) {
        void renderChart(nextArtifact);
      },
      destroy() {
        disposed = true;
        view?.finalize();
        node.replaceChildren();
      }
    };
  }
</script>

<article class="chart-artifact">
  <div class="chart-toolbar">
    <div>
      <p class="label">Chart artifact</p>
      <h3>{artifact.title}</h3>
    </div>
    <p class="chart-renderer">{artifact.renderer}</p>
  </div>

  {#if chartModel.status === "unsupported"}
    <p class="chart-message">{chartModel.message}</p>
  {:else if renderError}
    <p class="chart-message error-message">Chart could not render: {renderError}</p>
  {:else}
    <div use:vegaLiteChart={artifact} class="chart-frame" aria-label={artifact.title}></div>
  {/if}
</article>
