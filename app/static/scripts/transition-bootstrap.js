(() => {
  const root = document.documentElement;
  root.classList.add("has-js");
  const colorVars = [
    ["--route-start", "routeColorStart"],
    ["--route-middle", "routeColorMiddle"],
    ["--route-end", "routeColorEnd"],
    ["--dialog-color-start", "dialogColorStart"],
    ["--dialog-color-end", "dialogColorEnd"],
    ["--dialog-accent", "dialogAccent"],
  ];
  for (const [property, datasetKey] of colorVars) {
    const value = root.dataset[datasetKey];
    if (value) root.style.setProperty(property, value);
  }
  const sizeVars = [
    ["--dialog-radius", "dialogRadius"],
    ["--dialog-width", "dialogWidth"],
    ["--dialog-backdrop-blur", "dialogBackdropBlur"],
  ];
  for (const [property, datasetKey] of sizeVars) {
    const value = root.dataset[datasetKey];
    if (value) root.style.setProperty(property, `${value}px`);
  }
  const duration = Math.max(300, Math.min(2400, Number.parseInt(root.dataset.transitionDuration, 10) || 720));
  root.style.setProperty("--route-duration", `${duration}ms`);
  root.style.setProperty("--route-cover", `${Math.round(duration * .58)}ms`);
  root.style.setProperty("--route-reveal", `${Math.round(duration * .86)}ms`);
  try {
    const raw = sessionStorage.getItem("cloudgate-route-transition");
    if (!raw) return;
    sessionStorage.removeItem("cloudgate-route-transition");
    const state = JSON.parse(raw);
    if (state && Date.now() - Number(state.startedAt || 0) < 15000) root.classList.add("is-page-entering");
  } catch (_) {
    // Motion remains optional when storage is unavailable.
  }
})();
