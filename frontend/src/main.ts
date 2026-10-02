import { createApp } from "vue";
import { createPinia } from "pinia";
import { VueQueryPlugin, QueryClient } from "@tanstack/vue-query";
import App from "./App.vue";
import { vReveal } from "./app/directives/reveal";
import router from "./app/router";
import "@fontsource-variable/inter-tight";
import "./styles/base.css";

const app = createApp(App);
app.directive("reveal", vReveal);
app.use(createPinia());
app.use(router);
app.use(VueQueryPlugin, {
  queryClient: new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  }),
});
app.mount("#app");
