import { describe, expect, it } from "vitest";

import { chartRenderModel } from "./chartModel";
import type { ChartArtifact } from "$lib/artifacts/types";

const vegaLiteArtifact: ChartArtifact = {
  kind: "chart",
  renderer: "vega_lite",
  title: "Monthly average points",
  spec: {
    mark: "line",
    encoding: {
      x: { field: "month", type: "temporal" },
      y: { field: "average_points", type: "quantitative" }
    }
  }
};

describe("chartRenderModel", () => {
  it("marks Vega-Lite chart artifacts as renderable", () => {
    const model = chartRenderModel(vegaLiteArtifact);

    expect(model.status).toBe("renderable");
    if (model.status === "renderable") {
      expect(model.artifact.renderer).toBe("vega_lite");
      expect(model.artifact.spec.mark).toBe("line");
    }
  });

  it("returns a stable unsupported-renderer message", () => {
    const model = chartRenderModel({
      ...vegaLiteArtifact,
      renderer: "plotly"
    });

    expect(model).toEqual({
      status: "unsupported",
      title: "Monthly average points",
      message: 'Chart renderer "plotly" is not supported in this UI yet.'
    });
  });
});
