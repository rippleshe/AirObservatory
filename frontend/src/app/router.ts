import { createRouter, createWebHistory } from "vue-router";

const NationalOverviewView = () => import("../views/NationalOverviewView.vue");
const CityDetailView = () => import("../views/CityDetailView.vue");
const SystemView = () => import("../views/SystemView.vue");

/* One narrative: national picture → city explanation → data provenance.
   Forecast, structure and trust live inside the city page, so there is no
   parallel navigation for them. */
export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/overview" },
    {
      path: "/overview",
      name: "overview",
      component: NationalOverviewView,
      meta: { title: "全国总览" },
    },
    {
      path: "/city/:locationId",
      name: "city",
      component: CityDetailView,
      meta: { title: "城市详情" },
    },
    {
      path: "/system",
      name: "system",
      component: SystemView,
      meta: { title: "数据与方法" },
    },
    { path: "/:pathMatch(.*)*", redirect: "/overview" },
  ],
});
