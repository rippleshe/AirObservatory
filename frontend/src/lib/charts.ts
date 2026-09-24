import {
  BarChart,
  EffectScatterChart,
  HeatmapChart,
  LineChart,
  ScatterChart,
} from "echarts/charts";
import {
  AriaComponent,
  GeoComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import {
  init as echartsInit,
  registerMap,
  use,
  type ECharts,
} from "echarts/core";
import { CanvasRenderer, SVGRenderer } from "echarts/renderers";

use([
  AriaComponent,
  BarChart,
  CanvasRenderer,
  EffectScatterChart,
  HeatmapChart,
  GeoComponent,
  GridComponent,
  LegendComponent,
  LineChart,
  MarkAreaComponent,
  MarkLineComponent,
  ScatterChart,
  SVGRenderer,
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

export { registerMap };
export type { ECharts };
