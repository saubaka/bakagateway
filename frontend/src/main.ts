import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { router } from "./router";
import { initializeMotionPreferences, motionDirective } from "./motion";
import { pressFeedbackDirective } from "./pressFeedback";
import { initializeNotifications } from "./notifications";
import "./styles/vendor/app.css";
import "./styles/vendor/small-window-theme.css";
import "./styles/mail-overrides.css";
import "./styles/mail-pages.css";
import "./styles/admin.css";
import "./styles/motion.css";
import "./styles/login.css";
import "./styles/notifications.css";
import "./styles/theme-controls.css";
import "./styles/dialogs.css";
import "./styles/local-theme.css";
import "./styles/dashed-accent.css";
import "./styles/gateway.css";
import "./styles/account.css";

initializeMotionPreferences();
initializeNotifications();
createApp(App)
  .use(createPinia())
  .use(router)
  .directive("motion", motionDirective)
  .directive("press-feedback", pressFeedbackDirective)
  .mount("#app");

import "./styles/management.css";

import "./styles/quality.css";
