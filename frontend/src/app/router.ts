import { createRouter, createWebHistory } from "vue-router";

const OverviewPage = () => import("../pages/overview/OverviewPage.vue");
const CityPage = () => import("../pages/city/CityPage.vue");
const SystemPage = () => import("../pages/system/SystemPage.vue");
const AnalysisPage = () => import("../pages/analysis/AnalysisPage.vue");
const ForecastPage = () => import("../pages/forecast/ForecastPage.vue");

/* Four research workspaces; provenance stays an auxiliary tool route. */
export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/overview" },
    {
      path: "/overview",
      name: "overview",
      component: OverviewPage,
      meta: { title: "全国时空" },
    },
    {
      path: "/city/:locationId",
      name: "city",
      component: CityPage,
      meta: { title: "污染过程" },
    },
    {
      path: "/analysis",
      name: "analysis",
      component: AnalysisPage,
      meta: { title: "多变量关联" },
    },
    {
      path: "/forecast",
      name: "forecast",
      component: ForecastPage,
      meta: { title: "预测评估" },
    },
    { path: "/model", redirect: "/forecast" },
    {
      path: "/system",
      name: "system",
      component: SystemPage,
      meta: { title: "数据与方法" },
    },
    { path: "/:pathMatch(.*)*", redirect: "/overview" },
  ],
});
