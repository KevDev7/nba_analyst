import type { ChartArtifact } from "$lib/artifacts/types";

export type ChartRenderModel =
  | {
      status: "renderable";
      artifact: ChartArtifact & { renderer: "vega_lite" };
    }
  | {
      status: "unsupported";
      title: string;
      message: string;
    };

export function chartRenderModel(artifact: ChartArtifact): ChartRenderModel {
  if (artifact.renderer === "vega_lite") {
    return { status: "renderable", artifact: artifact as ChartArtifact & { renderer: "vega_lite" } };
  }
  return {
    status: "unsupported",
    title: artifact.title,
    message: `Chart renderer "${artifact.renderer}" is not supported in this UI yet.`
  };
}
