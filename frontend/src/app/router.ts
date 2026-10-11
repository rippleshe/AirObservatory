import { createRouter, createWebHistory } from "vue-router";

const NationalOverviewView = () => import("../views/NationalOverviewView.vue");
const CityDetailView = () => import("../views/CityDetailView.vue");
const SystemView = () => import("../views/SystemView.vue");
const AnalysisView = () => import("../views/AnalysisView.vue");
const ForecastView = () => import("../views/ForecastView.vue");

/* Four research workspaces; provenance stays an auxiliary tool route. */
export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/overview" },
    {
      path: "/overview",
      name: "overview",
      component: NationalOverviewView,
      meta: { title: "全国时空" },
    },
    {
      path: "/city/:locationId",
      name: "city",
      component: CityDetailView,
      meta: { title: "污染过程" },
    },
    {
      path: "/analysis",
      name: "analysis",
      component: AnalysisView,
      meta: { title: "多变量关联" },
    },
    {
      path: "/forecast",
      name: "forecast",
      component: ForecastView,
      meta: { title: "预测评估" },
    },
    { path: "/model", redirect: "/forecast" },
    {
      path: "/system",
      name: "system",
      component: SystemView,
      meta: { title: "数据与方法" },
    },
    { path: "/:pathMatch(.*)*", redirect: "/overview" },
  ],
});
