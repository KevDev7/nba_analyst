<script lang="ts">
  import { chartLayoutSpec } from "$lib/charts/chartLayout";
  import { chartRenderModel } from "$lib/charts/chartModel";
  import type { ChartArtifact } from "./types";

  let { artifact }: { artifact: ChartArtifact } = $props();
  let renderError = $state("");
  const chartModel = $derived(chartRenderModel(artifact));

  function vegaLiteChart(node: HTMLDivElement, currentArtifact: ChartArtifact) {
    let disposed = false;
    let lastLayoutWidth = 0;
    let pendingArtifact = currentArtifact;
    let renderId = 0;
    let resizeObserver: ResizeObserver | null = null;
    let view: { finalize: () => void } | null = null;

    async function renderChart(nextArtifact: ChartArtifact) {
      pendingArtifact = nextArtifact;
      const currentRenderId = ++renderId;
      const layoutWidth = Math.max(Math.round(node.clientWidth), 320);
      lastLayoutWidth = layoutWidth;
      renderError = "";
      view?.finalize();
      view = null;
      node.replaceChildren();
      if (nextArtifact.renderer !== "vega_lite") {
        return;
      }
      try {
        const { default: embed } = await import("vega-embed");
        if (disposed || currentRenderId !== renderId) {
          return;
        }
        const result = await embed(node, chartLayoutSpec(nextArtifact, layoutWidth), {
          actions: false,
          renderer: "canvas"
        });
        view = result.view;
      } catch (caught) {
        renderError = caught instanceof Error ? caught.message : String(caught);
      }
    }

    function rerenderIfLayoutChanged() {
      const layoutWidth = Math.max(Math.round(node.clientWidth), 320);
      if (Math.abs(layoutWidth - lastLayoutWidth) < 48) {
        return;
      }
      void renderChart(pendingArtifact);
    }

    void renderChart(currentArtifact);
    resizeObserver = new ResizeObserver(() => {
      if (!disposed) {
        rerenderIfLayoutChanged();
      }
    });
    resizeObserver.observe(node);

    return {
      update(nextArtifact: ChartArtifact) {
        void renderChart(nextArtifact);
      },
      destroy() {
        disposed = true;
        resizeObserver?.disconnect();
        view?.finalize();
        node.replaceChildren();
      }
    };
  }
</script>

<article class="chart-artifact">
  {#if chartModel.status === "unsupported"}
    <p class="chart-message">{chartModel.message}</p>
  {:else if renderError}
    <p class="chart-message error-message">Chart could not render: {renderError}</p>
  {:else}
    <div use:vegaLiteChart={artifact} class="chart-frame" aria-label={artifact.title}></div>
  {/if}
</article>
