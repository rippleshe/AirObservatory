import { createRouter, createWebHistory } from "vue-router";

const CurrentFieldView = () => import("../views/CurrentFieldView.vue");
const ExploreView = () => import("../views/ExploreView.vue");
const ForecastView = () => import("../views/ForecastView.vue");
const SystemView = () => import("../views/SystemView.vue");

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/live" },
    {
      path: "/live",
      name: "live",
      component: CurrentFieldView,
      meta: { title: "态势" },
    },
    {
      path: "/explore",
      name: "explore",
      component: ExploreView,
      meta: { title: "探索" },
    },
    {
      path: "/forecast",
      name: "forecast",
      component: ForecastView,
      meta: { title: "预测" },
    },
    {
      path: "/system",
      name: "system",
      component: SystemView,
      meta: { title: "系统" },
    },
    { path: "/:pathMatch(.*)*", redirect: "/live" },
  ],
});
