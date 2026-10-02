import {
  BarChart,
  CustomChart,
  EffectScatterChart,
  HeatmapChart,
  LineChart,
  ScatterChart,
  ThemeRiverChart,
} from "echarts/charts";
import {
  AriaComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  PolarComponent,
  SingleAxisComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import {
  init as echartsInit,
  use,
  type ECharts,
} from "echarts/core";
import { CanvasRenderer, SVGRenderer } from "echarts/renderers";

use([
  AriaComponent,
  BarChart,
  CanvasRenderer,
  CustomChart,
  EffectScatterChart,
  HeatmapChart,
  GridComponent,
  LegendComponent,
  LineChart,
  MarkAreaComponent,
  MarkLineComponent,
  PolarComponent,
  ScatterChart,
  SingleAxisComponent,
  SVGRenderer,
  ThemeRiverChart,
  TooltipComponent,
  VisualMapComponent,
]);

type Renderer = "canvas" | "svg";
type InitOptions = {
  renderer?: Renderer;
  devicePixelRatio?: number;
  width?: number | string;
  height?: number | string;
};

function crispDevicePixelRatio() {
  if (typeof window === "undefined") return 2;
  return Math.min(Math.max(window.devicePixelRatio || 1, 1.75), 3);
}

/* ECharts paints its own SVG and never resolves var(). Reading the token back
   off the document keeps base.css the single source of truth, so a colour
   change lands in one file instead of being hunted through every chart
   option. Call it at render time, not at module load: the stylesheet must
   already be applied. */
export function token(name: string, fallback = "#000000") {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

/* Resolved chart neutrals — call once per options build. Every chart reads
   the slate system through this factory, so a retired palette hex can never
   leak back into an ECharts option by accident. */
export function chartTheme() {
  return {
    ink: token("--ink", "#0f172a"),
    inkSoft: token("--ink-soft", "#334155"),
    axisInk: token("--muted", "#64748b"),
    faint: token("--faint", "#94a3b8"),
    axisLine: token("--hairline-strong", "#cbd5e1"),
    splitLine: token("--hairline", "#e2e8f0"),
    surface: token("--sheet", "#ffffff"),
    surfaceSubtle: token("--canvas-subtle", "#f1f5f9"),
    tooltipBorder: token("--hairline-strong", "#cbd5e1"),
  };
}

export type ChartTheme = ReturnType<typeof chartTheme>;

/* Every chart is SVG: DESIGN.md asks for vector-crisp geography and for core
   charts that hold up at projector distance and in print. Call sites pass the
   renderer explicitly so the choice is never accidental. */
export function init(
  dom: HTMLElement,
  theme?: string | object | null,
  options: InitOptions = {},
) {
  const renderer = options.renderer ?? "svg";
  return echartsInit(dom, theme, {
    ...options,
    renderer,
    devicePixelRatio:
      renderer === "canvas"
        ? options.devicePixelRatio ?? crispDevicePixelRatio()
        : undefined,
  });
}

export type { ECharts };
