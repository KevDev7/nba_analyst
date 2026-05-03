import type { ChartArtifact } from "$lib/artifacts/types";

type VegaLiteSpec = Record<string, unknown>;

const DEFAULT_HEIGHT = 360;
const DENSE_SERIES_HEIGHT = 420;
const DENSE_CATEGORY_HEIGHT = 440;
const HORIZONTAL_BAR_MIN_HEIGHT = 320;
const HORIZONTAL_BAR_MAX_HEIGHT = 760;
const MOBILE_HORIZONTAL_BAR_MAX_HEIGHT = 680;
const MANY_SERIES_THRESHOLD = 8;
const DENSE_SERIES_THRESHOLD = 24;
const DENSE_CATEGORY_THRESHOLD = 12;
const VERY_DENSE_CATEGORY_THRESHOLD = 24;
export const CATEGORICAL_SERIES_PALETTE = [
  "#5A5156",
  "#E4E1E3",
  "#F6222E",
  "#FE00FA",
  "#16FF32",
  "#3283FE",
  "#FEAF16",
  "#B00068",
  "#1CFFCE",
  "#90AD1C",
  "#2ED9FF",
  "#DEA0FD",
  "#AA0DFE",
  "#F8A19F",
  "#325A9B",
  "#C4451C",
  "#1C8356",
  "#85660D",
  "#B10DA1",
  "#FBE426",
  "#1CBE4F",
  "#FA0087",
  "#FC1CBF",
  "#F7E1A0",
  "#C075A6",
  "#782AB6",
  "#AAF400",
  "#BDCDFF",
  "#822E1C",
  "#B5EFB5",
  "#7ED7D1",
  "#1C7F93",
  "#D85FF7",
  "#683B79",
  "#66B0FF",
  "#3B00FB"
];

export function chartLayoutSpec(artifact: ChartArtifact, containerWidth: number): VegaLiteSpec {
  const spec = cloneSpec(artifact.spec);
  const profile = chartLayoutProfile(artifact);

  spec.width = "container";
  spec.height = chartHeight(profile, containerWidth);
  spec.autosize = { type: "fit-x", contains: "padding", resize: true };
  applyCategoricalColorScale(spec);
  applyQuantitativeScalePolicy(spec, profile);
  applyAxisPolicy(spec, profile, containerWidth);

  if (profile.seriesCount > MANY_SERIES_THRESHOLD) {
    applyLegend(spec, {
      orient: "bottom",
      direction: "horizontal",
      columns: legendColumns(containerWidth, profile.seriesCount)
    });
  }

  return spec;
}

type ChartLayoutProfile = {
  chartFamily: string;
  orientation: string;
  seriesCount: number;
  categoryCount: number;
  xType: string;
  yType: string;
};

function cloneSpec(spec: Record<string, unknown>): VegaLiteSpec {
  return JSON.parse(JSON.stringify(spec)) as VegaLiteSpec;
}

function chartLayoutProfile(artifact: ChartArtifact): ChartLayoutProfile {
  return {
    chartFamily: stringMetadata(artifact, "chart_family"),
    orientation: stringMetadata(artifact, "orientation"),
    seriesCount: numberMetadata(artifact, "series_count"),
    categoryCount: numberMetadata(artifact, "category_count"),
    xType: stringMetadata(artifact, "x_type"),
    yType: stringMetadata(artifact, "y_type")
  };
}

function chartHeight(profile: ChartLayoutProfile, containerWidth: number): number {
  if (isHorizontalBar(profile)) {
    const rowHeight = containerWidth < 520 ? 24 : 28;
    const chartChrome = containerWidth < 520 ? 92 : 104;
    const maxHeight = containerWidth < 520 ? MOBILE_HORIZONTAL_BAR_MAX_HEIGHT : HORIZONTAL_BAR_MAX_HEIGHT;
    return clamp(
      profile.categoryCount * rowHeight + chartChrome,
      HORIZONTAL_BAR_MIN_HEIGHT,
      maxHeight
    );
  }
  if (profile.seriesCount >= DENSE_SERIES_THRESHOLD) {
    return DENSE_SERIES_HEIGHT;
  }
  if (isVerticalBar(profile) && profile.categoryCount >= VERY_DENSE_CATEGORY_THRESHOLD) {
    return DENSE_CATEGORY_HEIGHT;
  }
  return DEFAULT_HEIGHT;
}

function numberMetadata(artifact: ChartArtifact, key: string): number {
  const value = artifact.metadata?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function stringMetadata(artifact: ChartArtifact, key: string): string {
  const value = artifact.metadata?.[key];
  return typeof value === "string" ? value : "";
}

function legendColumns(containerWidth: number, seriesCount: number): number {
  if (containerWidth >= 860) {
    return Math.min(6, seriesCount);
  }
  if (containerWidth >= 680) {
    return Math.min(5, seriesCount);
  }
  if (containerWidth >= 500) {
    return Math.min(4, seriesCount);
  }
  return Math.min(2, seriesCount);
}

function applyCategoricalColorScale(spec: VegaLiteSpec): void {
  const encoding = objectValue(spec.encoding);
  const color = objectValue(encoding?.color);
  const colorType = color?.type;
  if (color === undefined || (colorType !== "nominal" && colorType !== "ordinal")) {
    return;
  }
  color.scale = {
    ...objectValue(color.scale),
    range: CATEGORICAL_SERIES_PALETTE
  };
}

function applyQuantitativeScalePolicy(spec: VegaLiteSpec, profile: ChartLayoutProfile): void {
  const encoding = objectValue(spec.encoding);
  if (profile.chartFamily === "line") {
    applyZeroBaselinePolicy(encoding?.y);
    return;
  }
  if (profile.chartFamily === "point") {
    applyZeroBaselinePolicy(encoding?.x);
    applyZeroBaselinePolicy(encoding?.y);
  }
}

function applyZeroBaselinePolicy(channelValue: unknown): void {
  const channel = objectValue(channelValue);
  if (channel === undefined || channel.type !== "quantitative") {
    return;
  }
  channel.scale = {
    ...objectValue(channel.scale),
    zero: false
  };
}

function applyAxisPolicy(spec: VegaLiteSpec, profile: ChartLayoutProfile, containerWidth: number): void {
  const encoding = objectValue(spec.encoding);
  if (encoding === undefined) {
    return;
  }
  if (isHorizontalBar(profile)) {
    applyAxis(encoding.y, {
      labelLimit: horizontalBarLabelLimit(containerWidth),
      labelOverlap: false,
      labelPadding: 6,
      titlePadding: 10
    });
    applyAxis(encoding.x, {
      labelOverlap: true,
      titlePadding: 8
    });
    return;
  }
  if (isVerticalBar(profile) && profile.categoryCount >= DENSE_CATEGORY_THRESHOLD) {
    applyAxis(encoding.x, {
      labelAngle: verticalBarLabelAngle(profile, containerWidth),
      labelLimit: verticalBarLabelLimit(containerWidth),
      labelOverlap: false,
      labelPadding: 6,
      titlePadding: 10
    });
  }
}

function applyAxis(channelValue: unknown, axis: Record<string, unknown>): void {
  const channel = objectValue(channelValue);
  if (channel === undefined || channel.axis === null || channel.axis === false) {
    return;
  }
  channel.axis = {
    ...objectValue(channel.axis),
    ...axis
  };
}

function applyLegend(spec: VegaLiteSpec, legend: Record<string, unknown>): void {
  const encoding = objectValue(spec.encoding);
  const color = objectValue(encoding?.color);
  if (color === undefined) {
    return;
  }
  color.legend = {
    ...objectValue(color.legend),
    ...legend
  };
}

function objectValue(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function isHorizontalBar(profile: ChartLayoutProfile): boolean {
  return (
    profile.chartFamily === "bar" &&
    (profile.orientation === "horizontal" ||
      (profile.orientation === "" && isQuantitativeType(profile.xType) && isCategoricalType(profile.yType)))
  );
}

function isVerticalBar(profile: ChartLayoutProfile): boolean {
  return profile.chartFamily === "bar" && profile.orientation !== "horizontal";
}

function horizontalBarLabelLimit(containerWidth: number): number {
  if (containerWidth >= 860) {
    return 220;
  }
  if (containerWidth >= 620) {
    return 180;
  }
  return 130;
}

function verticalBarLabelLimit(containerWidth: number): number {
  if (containerWidth >= 760) {
    return 120;
  }
  if (containerWidth >= 520) {
    return 96;
  }
  return 76;
}

function verticalBarLabelAngle(profile: ChartLayoutProfile, containerWidth: number): number {
  if (profile.categoryCount >= VERY_DENSE_CATEGORY_THRESHOLD || containerWidth < 520) {
    return -45;
  }
  return -35;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function isQuantitativeType(columnType: string): boolean {
  return columnType === "number" || columnType === "integer";
}

function isCategoricalType(columnType: string): boolean {
  return columnType === "text" || columnType === "boolean";
}
