import { describe, expect, it } from "vitest";

import type { ChartArtifact } from "$lib/artifacts/types";
import { CATEGORICAL_SERIES_PALETTE, chartLayoutSpec } from "./chartLayout";

const baseArtifact: ChartArtifact = {
  kind: "chart",
  renderer: "vega_lite",
  title: "Monthly average points",
  spec: {
    width: "container",
    height: 360,
    autosize: { type: "fit-x", contains: "padding", resize: true },
    mark: { type: "line", point: true },
    encoding: {
      x: { field: "month", type: "temporal" },
      y: { field: "average_points", type: "quantitative" },
      color: { field: "team", type: "nominal", title: "Team" }
    }
  },
  metadata: {
    series_count: 2,
    chart_family: "line"
  }
};

describe("chartLayoutSpec", () => {
  it("uses the Polychrome 36 categorical palette", () => {
    expect(CATEGORICAL_SERIES_PALETTE).toHaveLength(36);
    expect(CATEGORICAL_SERIES_PALETTE.slice(0, 3)).toEqual(["#5A5156", "#E4E1E3", "#F6222E"]);
  });

  it("keeps sparse series charts compact with the default Vega-Lite legend", () => {
    const spec = chartLayoutSpec(baseArtifact, 900);

    expect(spec.width).toBe("container");
    expect(spec.height).toBe(360);
    expect(spec.autosize).toEqual({ type: "fit-x", contains: "padding", resize: true });
    expect(colorScale(spec)).toEqual({ range: CATEGORICAL_SERIES_PALETTE });
    expect(yScale(spec)).toEqual({ zero: false });
    expect(colorLegend(spec)).toBeUndefined();
  });

  it("moves many-series legends below the chart with responsive columns", () => {
    const spec = chartLayoutSpec(
      {
        ...baseArtifact,
        metadata: { series_count: 30, chart_family: "line" }
      },
      900
    );

    expect(spec.height).toBe(420);
    expect(colorLegend(spec)).toEqual({
      orient: "bottom",
      direction: "horizontal",
      columns: 6
    });
  });

  it("scales horizontal bar chart height from category count", () => {
    const spec = chartLayoutSpec(
      {
        ...baseArtifact,
        spec: {
          ...baseArtifact.spec,
          mark: { type: "bar" },
          encoding: {
            x: { field: "total_points", type: "quantitative" },
            y: { field: "player", type: "nominal" }
          }
        },
        metadata: {
          chart_family: "bar",
          orientation: "horizontal",
          category_count: 18,
          x_type: "number",
          y_type: "text"
        }
      },
      900
    );

    expect(spec.height).toBe(608);
    expect(yAxis(spec)).toMatchObject({
      labelLimit: 220,
      labelOverlap: false,
      labelPadding: 6,
      titlePadding: 10
    });
    expect(xAxis(spec)).toMatchObject({
      labelOverlap: true,
      titlePadding: 8
    });
  });

  it("keeps horizontal bar charts usable in narrow containers", () => {
    const spec = chartLayoutSpec(
      {
        ...baseArtifact,
        spec: {
          ...baseArtifact.spec,
          mark: { type: "bar" },
          encoding: {
            x: { field: "metric_value", type: "quantitative" },
            y: { field: "entity_name", type: "nominal" }
          }
        },
        metadata: {
          chart_family: "bar",
          orientation: "horizontal",
          category_count: 40,
          x_type: "number",
          y_type: "text"
        }
      },
      420
    );

    expect(spec.height).toBe(680);
    expect(yAxis(spec)).toMatchObject({
      labelLimit: 130,
      labelOverlap: false
    });
  });

  it("can infer horizontal bar layout from typed axes when orientation metadata is absent", () => {
    const spec = chartLayoutSpec(
      {
        ...baseArtifact,
        spec: {
          ...baseArtifact.spec,
          mark: { type: "bar" },
          encoding: {
            x: { field: "points", type: "quantitative" },
            y: { field: "player", type: "nominal" }
          }
        },
        metadata: {
          chart_family: "bar",
          category_count: 12,
          x_type: "number",
          y_type: "text"
        }
      },
      900
    );

    expect(spec.height).toBe(440);
    expect(yAxis(spec)).toMatchObject({
      labelLimit: 220,
      labelOverlap: false
    });
  });

  it("rotates dense vertical bar labels without changing the bar baseline policy", () => {
    const spec = chartLayoutSpec(
      {
        ...baseArtifact,
        spec: {
          ...baseArtifact.spec,
          mark: { type: "bar" },
          encoding: {
            x: { field: "team", type: "nominal" },
            y: { field: "average_points", type: "quantitative" }
          }
        },
        metadata: {
          chart_family: "bar",
          orientation: "vertical",
          category_count: 16,
          x_type: "text",
          y_type: "number"
        }
      },
      900
    );

    expect(spec.height).toBe(360);
    expect(yScale(spec)).toBeUndefined();
    expect(xAxis(spec)).toMatchObject({
      labelAngle: -35,
      labelLimit: 120,
      labelOverlap: false
    });
  });

  it("gives very dense vertical bars extra height and steeper mobile labels", () => {
    const spec = chartLayoutSpec(
      {
        ...baseArtifact,
        spec: {
          ...baseArtifact.spec,
          mark: { type: "bar" },
          encoding: {
            x: { field: "player", type: "nominal" },
            y: { field: "points", type: "quantitative" }
          }
        },
        metadata: {
          chart_family: "bar",
          orientation: "vertical",
          category_count: 26
        }
      },
      420
    );

    expect(spec.height).toBe(440);
    expect(xAxis(spec)).toMatchObject({
      labelAngle: -45,
      labelLimit: 76
    });
  });

  it("uses fewer legend columns in narrow containers", () => {
    const spec = chartLayoutSpec(
      {
        ...baseArtifact,
        metadata: { series_count: 30, chart_family: "line" }
      },
      420
    );

    expect(colorLegend(spec)).toMatchObject({
      orient: "bottom",
      columns: 2
    });
  });

  it("does not mutate the original artifact spec", () => {
    const artifact: ChartArtifact = {
      ...baseArtifact,
      metadata: { series_count: 30 }
    };

    chartLayoutSpec(artifact, 900);

    expect(colorLegend(artifact.spec)).toBeUndefined();
    expect(colorScale(artifact.spec)).toBeUndefined();
    expect(yScale(artifact.spec)).toBeUndefined();
  });

  it("preserves existing quantitative y scale properties when fitting line chart domains", () => {
    const spec = chartLayoutSpec(
      {
        ...baseArtifact,
        spec: {
          ...baseArtifact.spec,
          encoding: {
            x: { field: "month", type: "temporal" },
            y: {
              field: "average_points",
              type: "quantitative",
              scale: { nice: false }
            }
          }
        }
      },
      900
    );

    expect(yScale(spec)).toEqual({ nice: false, zero: false });
  });

  it("keeps zero baselines for bar charts", () => {
    const spec = chartLayoutSpec(
      {
        ...baseArtifact,
        spec: {
          ...baseArtifact.spec,
          mark: { type: "bar" },
          encoding: {
            x: { field: "team", type: "nominal" },
            y: { field: "average_points", type: "quantitative" }
          }
        },
        metadata: { series_count: 0, chart_family: "bar" }
      },
      900
    );

    expect(yScale(spec)).toBeUndefined();
  });

  it("fits quantitative point chart domains on both axes", () => {
    const spec = chartLayoutSpec(
      {
        ...baseArtifact,
        spec: {
          ...baseArtifact.spec,
          mark: { type: "point", filled: true },
          encoding: {
            x: { field: "points", type: "quantitative" },
            y: { field: "assists", type: "quantitative" }
          }
        },
        metadata: { chart_family: "point" }
      },
      900
    );

    expect(xScale(spec)).toEqual({ zero: false });
    expect(yScale(spec)).toEqual({ zero: false });
  });

  it("does not fit non-quantitative y scales", () => {
    const spec = chartLayoutSpec(
      {
        ...baseArtifact,
        spec: {
          ...baseArtifact.spec,
          encoding: {
            x: { field: "month", type: "temporal" },
            y: { field: "score_band", type: "ordinal" }
          }
        }
      },
      900
    );

    expect(yScale(spec)).toBeUndefined();
  });

  it("preserves existing nominal scale properties when adding the product palette", () => {
    const spec = chartLayoutSpec(
      {
        ...baseArtifact,
        spec: {
          ...baseArtifact.spec,
          encoding: {
            x: { field: "month", type: "temporal" },
            y: { field: "average_points", type: "quantitative" },
            color: {
              field: "team",
              type: "nominal",
              title: "Team",
              scale: { domain: ["Lakers", "Warriors"] }
            }
          }
        }
      },
      900
    );

    expect(colorScale(spec)).toEqual({
      domain: ["Lakers", "Warriors"],
      range: CATEGORICAL_SERIES_PALETTE
    });
  });

  it("does not apply a categorical palette to quantitative color encodings", () => {
    const spec = chartLayoutSpec(
      {
        ...baseArtifact,
        spec: {
          ...baseArtifact.spec,
          encoding: {
            x: { field: "month", type: "temporal" },
            y: { field: "average_points", type: "quantitative" },
            color: { field: "average_points", type: "quantitative", title: "Average Points" }
          }
        },
        metadata: { series_count: 0 }
      },
      900
    );

    expect(colorScale(spec)).toBeUndefined();
  });
});

function colorScale(spec: Record<string, unknown>): unknown {
  const encoding = spec.encoding as Record<string, unknown> | undefined;
  const color = encoding?.color as Record<string, unknown> | undefined;
  return color?.scale;
}

function colorLegend(spec: Record<string, unknown>): unknown {
  const encoding = spec.encoding as Record<string, unknown> | undefined;
  const color = encoding?.color as Record<string, unknown> | undefined;
  return color?.legend;
}

function yScale(spec: Record<string, unknown>): unknown {
  const encoding = spec.encoding as Record<string, unknown> | undefined;
  const y = encoding?.y as Record<string, unknown> | undefined;
  return y?.scale;
}

function xScale(spec: Record<string, unknown>): unknown {
  const encoding = spec.encoding as Record<string, unknown> | undefined;
  const x = encoding?.x as Record<string, unknown> | undefined;
  return x?.scale;
}

function xAxis(spec: Record<string, unknown>): unknown {
  const encoding = spec.encoding as Record<string, unknown> | undefined;
  const x = encoding?.x as Record<string, unknown> | undefined;
  return x?.axis;
}

function yAxis(spec: Record<string, unknown>): unknown {
  const encoding = spec.encoding as Record<string, unknown> | undefined;
  const y = encoding?.y as Record<string, unknown> | undefined;
  return y?.axis;
}
