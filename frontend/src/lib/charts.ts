import { EffectScatterChart, LineChart, ScatterChart } from "echarts/charts";
import {
  AriaComponent,
  GeoComponent,
  GridComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import { init, registerMap, use, type ECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

use([
  AriaComponent,
  CanvasRenderer,
  EffectScatterChart,
  GeoComponent,
  GridComponent,
  LineChart,
  MarkLineComponent,
  ScatterChart,
  TooltipComponent,
]);

export { init, registerMap };
export type { ECharts };
