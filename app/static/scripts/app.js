(() => {
  const doc = document;
  const root = doc.documentElement;
  const systemReducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const reduced = () => root.dataset.motion === "reduce" || (root.dataset.motion === "system" && systemReducedMotion.matches);
  if ((navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4) || (navigator.deviceMemory && navigator.deviceMemory <= 4)) root.dataset.performance = "low";
  try {
    const storedMotion = localStorage.getItem("cloudgate-motion");
    if (storedMotion === "reduce") root.dataset.motion = "reduce";
  } catch (_) {
    // Local preference storage is optional.
  }

  doc.addEventListener("pointerdown", (event) => {
    const target = event.target.closest(".button,.card--interactive,.icon-button");
    if (target) target.classList.add("is-pressed");
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach((name) => doc.addEventListener(name, () => {
    doc.querySelectorAll(".is-pressed").forEach((item) => item.classList.remove("is-pressed"));
  }));

  doc.querySelectorAll("[data-password-toggle]").forEach((button) => button.addEventListener("click", () => {
    const input = button.parentElement.querySelector("input");
    const nextVisible = input.type !== "text";
    input.type = nextVisible ? "text" : "password";
    button.classList.toggle("is-visible", nextVisible);
    button.setAttribute("aria-pressed", String(nextVisible));
    button.setAttribute("aria-label", nextVisible ? "隐藏密码" : "显示密码");
    input.focus();
  }));

  const mismatchDialog = doc.querySelector("[data-password-mismatch-dialog]");
  const passwordMatchForm = doc.querySelector("form[data-password-match]");
  const openMismatchDialog = () => {
    if (!mismatchDialog) return;
    if (typeof mismatchDialog.showModal === "function") mismatchDialog.showModal();
    else mismatchDialog.setAttribute("open", "");
  };
  const closeMismatchDialog = () => {
    if (!mismatchDialog) return;
    if (typeof mismatchDialog.close === "function") mismatchDialog.close();
    else mismatchDialog.removeAttribute("open");
    passwordMatchForm?.querySelector("[name='password_confirm']")?.focus();
  };
  passwordMatchForm?.addEventListener("submit", (event) => {
    const password = passwordMatchForm.querySelector("[name='password']");
    const confirmation = passwordMatchForm.querySelector("[name='password_confirm']");
    if (!password?.value || !confirmation?.value || password.value === confirmation.value) return;
    event.preventDefault();
    passwordMatchForm.classList.remove("is-submitting");
    openMismatchDialog();
  });
  mismatchDialog?.querySelectorAll("[data-password-mismatch-close]").forEach((button) => {
    button.addEventListener("click", closeMismatchDialog);
  });
  if (mismatchDialog?.hasAttribute("data-open-on-load")) openMismatchDialog();

  doc.querySelectorAll("[data-submit-state]").forEach((form) => form.addEventListener("submit", () => {
    if (form.checkValidity()) form.classList.add("is-submitting");
  }));

  doc.querySelectorAll("[data-policy-gated]").forEach((form) => {
    const consent = form.querySelector("[data-policy-consent]");
    const submit = form.querySelector("[data-policy-submit]");
    const sync = () => {
      if (!submit) return;
      submit.disabled = !consent?.checked;
      submit.setAttribute("aria-disabled", String(submit.disabled));
    };
    consent?.addEventListener("change", sync);
    sync();
  });

  doc.querySelectorAll("[data-fallback-image]").forEach((image) => {
    const media = image.closest("[data-fallback-media]");
    const unavailable = () => {
      image.hidden = true;
      media?.classList.add("is-fallback");
    };
    image.addEventListener("error", unavailable, { once: true });
    image.addEventListener("load", () => media?.classList.add("has-image"), { once: true });
    if (image.complete) {
      if (image.naturalWidth > 0) media?.classList.add("has-image");
      else unavailable();
    }
  });

  doc.querySelectorAll("[data-auto-continue]").forEach((panel) => {
    const target = panel.dataset.continueUrl;
    if (!target) return;
    const requestedDelay = Number.parseInt(panel.dataset.continueDelay || "1000", 10);
    const delay = reduced() ? 80 : Math.max(300, requestedDelay);
    window.setTimeout(() => location.replace(target), delay);
  });

  doc.querySelectorAll(".avatar-upload input[type='file']").forEach((input) => input.addEventListener("change", () => {
    const file = input.files?.[0];
    const preview = input.closest("form")?.querySelector(".avatar-editor__preview");
    if (!file || !preview || !file.type.startsWith("image/")) return;
    const imageUrl = URL.createObjectURL(file);
    preview.innerHTML = "";
    const image = doc.createElement("img");
    image.src = imageUrl;
    image.alt = "新头像预览";
    image.addEventListener("load", () => URL.revokeObjectURL(imageUrl), { once: true });
    preview.append(image);
  }));

  const returning = doc.querySelector("[data-return-countdown]");
  if (returning) {
    const target = returning.dataset.returnUrl;
    const number = returning.querySelector("[data-return-number]");
    const progress = returning.querySelector("[data-return-progress]");
    const total = Math.max(1, Number.parseInt(returning.dataset.returnSeconds || "3", 10));
    let remaining = reduced() ? 1 : total;
    if (number) number.textContent = String(remaining);
    if (progress) {
      progress.style.transitionDuration = `${remaining}s`;
      requestAnimationFrame(() => progress.classList.add("is-running"));
    }
    const timer = window.setInterval(() => {
      remaining -= 1;
      if (number) number.textContent = String(Math.max(0, remaining));
      if (remaining <= 0) {
        window.clearInterval(timer);
        location.replace(target);
      }
    }, 1000);
  }

  const toastReduced = () => root.dataset.motion === "reduce";
  doc.querySelectorAll("[data-toast]").forEach((toast, index) => {
    if (!toastReduced()) toast.style.animationDelay = `${index * 90}ms`;
    const close = () => {
      if (toast.classList.contains("is-leaving")) return;
      toast.style.maxHeight = `${toast.offsetHeight}px`;
      void toast.getBoundingClientRect();
      toast.classList.add("is-leaving");
      toast.style.maxHeight = "0px";
      setTimeout(() => toast.remove(), toastReduced() ? 1 : 480);
    };
    toast.querySelector("[data-dismiss-toast]")?.addEventListener("click", close);
    setTimeout(close, toastReduced() ? 6500 : 6500 + index * 160);
  });

  doc.querySelectorAll("[data-identity-menu]").forEach((menu) => {
    const trigger = menu.querySelector("[data-identity-menu-trigger]");
    const panel = menu.querySelector("[data-identity-menu-panel]");
    const setOpen = (open) => {
      menu.classList.toggle("is-open", open);
      trigger?.setAttribute("aria-expanded", String(open));
    };
    trigger?.addEventListener("click", (event) => {
      event.stopPropagation();
      setOpen(!menu.classList.contains("is-open"));
    });
    menu.addEventListener("mouseenter", () => setOpen(true));
    doc.addEventListener("pointermove", (event) => {
      if (!menu.classList.contains("is-open") || menu.matches(":focus-within")) return;
      const triggerRect = trigger?.getBoundingClientRect();
      const panelRect = panel?.getBoundingClientRect();
      if (!triggerRect || !panelRect) return;
      const insideTrigger = event.clientX >= triggerRect.left
        && event.clientX <= triggerRect.right
        && event.clientY >= triggerRect.top
        && event.clientY <= triggerRect.bottom;
      const insidePanel = event.clientX >= panelRect.left
        && event.clientX <= panelRect.right
        && event.clientY >= panelRect.top
        && event.clientY <= panelRect.bottom;
      const insideDownwardBridge = event.clientX >= triggerRect.left - 5
        && event.clientX <= triggerRect.right + 5
        && event.clientY > triggerRect.bottom
        && event.clientY < panelRect.top;
      if (!insideTrigger && !insidePanel && !insideDownwardBridge) setOpen(false);
    });
    menu.addEventListener("focusout", () => window.setTimeout(() => {
      if (!menu.matches(":focus-within")) setOpen(false);
    }, 0));
    doc.addEventListener("click", (event) => {
      if (!menu.contains(event.target)) setOpen(false);
    });
  });

  const dialog = doc.querySelector("[data-app-system-dialog]");
  const dialogTitle = dialog?.querySelector("[data-confirm-title]");
  const dialogCopy = dialog?.querySelector("[data-confirm-copy]");
  const dialogField = dialog?.querySelector("[data-system-dialog-field]");
  const dialogInputLabel = dialog?.querySelector("[data-app-dialog-input-label]");
  const dialogInput = dialog?.querySelector("[data-system-dialog-input]");
  const dialogAccept = dialog?.querySelector("[data-confirm-accept]");
  const dialogFooterCancel = dialog?.querySelector("[data-dialog-footer-cancel]");
  let pendingForm = null;
  let pendingPrompt = null;
  const prepareSystemDialog = (mode, title, copy) => {
    if (!dialog) return;
    dialog.dataset.dialogMode = mode;
    if (dialogTitle) dialogTitle.textContent = title;
    if (dialogCopy) dialogCopy.textContent = copy;
    if (dialogField) dialogField.hidden = mode !== "prompt";
    if (dialogFooterCancel) dialogFooterCancel.hidden = mode === "alert";
    if (dialogAccept) dialogAccept.textContent = mode === "alert" ? "知道了" : "确认";
    if (dialogInput) dialogInput.value = "";
  };
  const openSystemPrompt = (title, copy, inputLabel, initial, callback) => {
    if (!dialog) { callback(window.prompt(title, initial)); return; }
    pendingForm = null;
    pendingPrompt = callback;
    prepareSystemDialog("prompt", title, copy);
    if (dialogInputLabel) dialogInputLabel.textContent = inputLabel;
    if (dialogInput) dialogInput.value = initial || "";
    dialog.showModal();
    requestAnimationFrame(() => dialogInput?.focus());
  };
  dialog?.addEventListener("cancel", () => {
    pendingForm = null;
    pendingPrompt = null;
  });
  doc.querySelectorAll("form[data-confirm]").forEach((form) => form.addEventListener("submit", (event) => {
    if (form.dataset.confirmed === "true") return;
    event.preventDefault();
    pendingForm = form;
    prepareSystemDialog("confirm", "确认操作", form.dataset.confirm);
    dialog.showModal();
  }));
  dialog?.querySelectorAll("[data-confirm-cancel]").forEach((button) => button.addEventListener("click", () => {
    pendingForm = null;
    pendingPrompt = null;
    dialog.close();
  }));
  dialog?.querySelector("[data-confirm-accept]")?.addEventListener("click", () => {
    if (pendingForm) {
      pendingForm.dataset.confirmed = "true";
      const form = pendingForm;
      pendingForm = null;
      dialog.close();
      form.requestSubmit();
      return;
    }
    if (pendingPrompt) {
      const callback = pendingPrompt;
      pendingPrompt = null;
      dialog.close();
      callback((dialogInput?.value || "").trim());
      return;
    }
    return dialog.close();
  });

  const sidebar = doc.querySelector("[data-admin-sidebar]");
  const backdrop = doc.querySelector("[data-admin-backdrop]");
  const setMenu = (open) => {
    sidebar?.classList.toggle("is-open", open);
    backdrop?.classList.toggle("is-open", open);
    doc.body.style.overflow = open ? "hidden" : "";
  };
  doc.querySelector("[data-admin-menu]")?.addEventListener("click", () => setMenu(true));
  backdrop?.addEventListener("click", () => setMenu(false));

  const adminGroups = [...doc.querySelectorAll("[data-admin-menu-group]")];
  const animateAdminGroup = (group, open) => {
    const panel = group.querySelector(".admin-nav-group__items");
    const toggle = group.querySelector("[data-admin-menu-toggle]");
    if (!panel || !toggle) return;
    const start = panel.getBoundingClientRect().height;
    group.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    panel.style.height = "auto";
    const end = open ? panel.scrollHeight : 0;
    panel.style.height = `${start}px`;
    panel.offsetHeight;
    panel.classList.add("is-height-animating");
    panel.style.height = `${end}px`;
    const finish = () => {
      panel.classList.remove("is-height-animating");
      panel.style.height = open ? "auto" : "0px";
    };
    panel.addEventListener("transitionend", finish, { once: true });
    window.setTimeout(finish, reduced() ? 1 : 360);
  };
  adminGroups.forEach((group) => {
    const panel = group.querySelector(".admin-nav-group__items");
    if (panel) panel.style.height = group.classList.contains("is-open") ? "auto" : "0px";
    group.querySelector("[data-admin-menu-toggle]")?.addEventListener("click", () => {
      const next = !group.classList.contains("is-open");
      adminGroups.forEach((item) => {
        if (item !== group && item.classList.contains("is-open") && item.querySelector(".admin-nav-group__items")) animateAdminGroup(item, false);
      });
      animateAdminGroup(group, next);
    });
  });

  const mobileDrawer = doc.querySelector("#mobile-drawer");
  const mobileBackdrop = doc.querySelector("[data-mobile-backdrop]");
  let drawerTimer = 0;
  let drawerTrigger = null;
  const drawerFocusables = () => [...(mobileDrawer?.querySelectorAll("a[href],button:not([disabled]),input:not([disabled]),[tabindex]:not([tabindex='-1'])") || [])].filter((item) => item.offsetParent !== null);
  const setPortalInert = (value) => {
    doc.querySelectorAll(".site-header,.portal-page,.site-footer,.mobile-capsule-bar").forEach((item) => { item.inert = value; });
  };
  const setDrawer = (open, trigger = null) => {
    window.clearTimeout(drawerTimer);
    if (open) drawerTrigger = trigger || doc.activeElement;
    if (!open && mobileDrawer?.contains(doc.activeElement)) drawerTrigger?.focus();
    mobileDrawer?.classList.toggle("is-open", open);
    mobileDrawer?.setAttribute("aria-hidden", String(!open));
    mobileBackdrop?.classList.toggle("is-visible", open);
    doc.querySelectorAll("[data-mobile-drawer]").forEach((item) => item.setAttribute("aria-expanded", String(open)));
    doc.body.classList.toggle("drawer-open", open);
    setPortalInert(open);
    if (mobileBackdrop) {
      if (open) {
        mobileBackdrop.hidden = false;
        requestAnimationFrame(() => drawerFocusables()[0]?.focus());
      } else {
        drawerTimer = window.setTimeout(() => {
          mobileBackdrop.hidden = true;
          drawerTrigger?.focus();
        }, reduced() ? 1 : 380);
      }
    }
  };
  doc.querySelectorAll("[data-mobile-drawer]").forEach((button) => button.addEventListener("click", () => setDrawer(true, button)));
  doc.querySelectorAll("[data-close-mobile-drawer]").forEach((button) => button.addEventListener("click", () => setDrawer(false)));
  mobileBackdrop?.addEventListener("click", () => setDrawer(false));
  mobileDrawer?.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => setDrawer(false)));
  doc.addEventListener("keydown", (event) => {
    if (!mobileDrawer?.classList.contains("is-open")) return;
    if (event.key === "Escape") setDrawer(false);
    if (event.key !== "Tab") return;
    const items = drawerFocusables();
    if (!items.length) return;
    const first = items[0];
    const last = items.at(-1);
    if (event.shiftKey && doc.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && doc.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth > 860 && mobileDrawer?.classList.contains("is-open")) setDrawer(false);
  });

  const capsuleNavigation = doc.querySelector("[data-capsule-nav]");
  const capsuleLinks = capsuleNavigation?.querySelector(".site-nav__links");
  if (capsuleLinks) {
    const indicator = doc.createElement("span");
    indicator.className = "nav-indicator";
    indicator.setAttribute("aria-hidden", "true");
    capsuleLinks.prepend(indicator);
    const moveIndicator = (target) => {
      if (!target || getComputedStyle(capsuleLinks).display === "none") {
        indicator.hidden = true;
        return;
      }
      indicator.hidden = false;
      const targetRect = target.getBoundingClientRect();
      indicator.style.width = `${targetRect.width}px`;
      indicator.style.height = `${targetRect.height}px`;
      indicator.style.transform = `translate3d(${target.offsetLeft}px,${target.offsetTop}px,0)`;
    };
    const current = capsuleLinks.querySelector("a.is-current") || capsuleLinks.querySelector("a");
    requestAnimationFrame(() => moveIndicator(current));
    capsuleLinks.querySelectorAll("a").forEach((link) => {
      link.addEventListener("pointerenter", () => moveIndicator(link));
      link.addEventListener("focus", () => moveIndicator(link));
    });
    capsuleLinks.addEventListener("pointerleave", () => moveIndicator(current));
    window.addEventListener("resize", () => moveIndicator(current));
  }
  doc.querySelectorAll("[data-capsule-nav],[data-bottom-capsule]").forEach((capsuleNavigation) => {
    const capsuleViewport = window.matchMedia("(min-width: 621px)");
    let previousY = Math.max(0, window.scrollY);
    let ticking = false;
    let arrivalTimer = 0;
    const canScroll = () => doc.documentElement.scrollHeight > window.innerHeight + 24;
    const setCapsuleVisible = (visible) => {
      capsuleNavigation.classList.toggle("is-nav-visible", visible);
      capsuleNavigation.classList.toggle("is-nav-hidden", !visible);
    };
    const updateCapsule = () => {
      const currentY = Math.max(0, window.scrollY);
      const delta = currentY - previousY;
      if (!capsuleViewport.matches || !canScroll()) setCapsuleVisible(true);
      else if (delta > 0) setCapsuleVisible(false);
      else if (delta < 0) setCapsuleVisible(true);
      previousY = currentY;
      ticking = false;
    };
    const requestCapsuleUpdate = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(updateCapsule);
    };
    const resetCapsule = () => {
      previousY = Math.max(0, window.scrollY);
      setCapsuleVisible(true);
      requestCapsuleUpdate();
    };
    const playCapsuleArrival = () => {
      window.clearTimeout(arrivalTimer);
      capsuleNavigation.classList.remove("is-nav-arriving");
      if (capsuleViewport.matches && !reduced()) requestAnimationFrame(() => capsuleNavigation.classList.add("is-nav-arriving"));
      arrivalTimer = window.setTimeout(() => capsuleNavigation.classList.remove("is-nav-arriving"), 680);
    };
    setCapsuleVisible(true);
    playCapsuleArrival();
    window.addEventListener("scroll", requestCapsuleUpdate, { passive: true });
    window.addEventListener("resize", resetCapsule, { passive: true });
    capsuleViewport.addEventListener?.("change", resetCapsule);
    window.addEventListener("pageshow", playCapsuleArrival);
  });

  doc.querySelectorAll(".card").forEach((card, index) => {
    const delay = Math.min(index * 48, 480);
    card.classList.add("motion-card");
    card.style.setProperty("--card-delay", `${delay}ms`);
    requestAnimationFrame(() => card.classList.add("is-card-visible"));
    window.setTimeout(() => card.style.setProperty("--card-delay", "0ms"), reduced() ? 1 : 620 + delay);
  });

  const cropDialog = doc.querySelector("[data-image-crop-dialog]");
  const cropCanvas = cropDialog?.querySelector("[data-crop-canvas]");
  const cropContext = cropCanvas?.getContext("2d");
  const cropZoom = cropDialog?.querySelector("[data-crop-zoom]");
  let cropState = null;
  let cropInput = null;
  let cropDragging = false;
  let cropLastPoint = null;
  const drawAvatarCrop = () => {
    if (!cropState?.image || !cropCanvas || !cropContext) return;
    const size = Math.round(Math.min(520, Math.max(260, cropDialog.clientWidth - 48)));
    cropCanvas.width = size;
    cropCanvas.height = size;
    cropContext.clearRect(0, 0, size, size);
    cropContext.save();
    cropContext.beginPath();
    cropContext.arc(size / 2, size / 2, size / 2, 0, Math.PI * 2);
    cropContext.clip();
    cropContext.translate(size / 2 + cropState.x, size / 2 + cropState.y);
    cropContext.rotate(cropState.rotation * Math.PI / 180);
    const turned = Math.abs(cropState.rotation % 180) === 90;
    const width = turned ? cropState.image.height : cropState.image.width;
    const height = turned ? cropState.image.width : cropState.image.height;
    const scale = Math.max(size / width, size / height) * cropState.zoom;
    cropContext.drawImage(cropState.image, -cropState.image.width * scale / 2, -cropState.image.height * scale / 2, cropState.image.width * scale, cropState.image.height * scale);
    cropContext.restore();
  };
  const closeCrop = (clear = false) => {
    if (cropDialog?.open) cropDialog.close();
    if (clear && cropInput) cropInput.value = "";
    cropState = null;
    cropInput = null;
  };
  doc.addEventListener("change", (event) => {
    const input = event.target.closest("input[type='file'][data-avatar-crop]");
    if (!input || event.cropReady || !input.files?.[0]) return;
    event.stopImmediatePropagation();
    const file = input.files[0];
    if (!file.type.startsWith("image/")) return;
    const image = new Image();
    const source = URL.createObjectURL(file);
    image.onload = () => {
      URL.revokeObjectURL(source);
      cropInput = input;
      cropState = { image, file, zoom: 1, rotation: 0, x: 0, y: 0 };
      cropZoom.value = "1";
      cropDialog.querySelector("[data-crop-zoom-value]").textContent = "100%";
      cropDialog.showModal();
      requestAnimationFrame(drawAvatarCrop);
    };
    image.onerror = () => URL.revokeObjectURL(source);
    image.src = source;
  }, true);
  cropZoom?.addEventListener("input", () => {
    if (!cropState) return;
    cropState.zoom = Number(cropZoom.value);
    cropDialog.querySelector("[data-crop-zoom-value]").textContent = `${Math.round(cropState.zoom * 100)}%`;
    drawAvatarCrop();
  });
  cropDialog?.querySelectorAll("[data-crop-rotate]").forEach((button) => button.addEventListener("click", () => {
    cropState.rotation = (cropState.rotation + Number(button.dataset.cropRotate) + 360) % 360;
    cropState.x = 0;
    cropState.y = 0;
    drawAvatarCrop();
  }));
  cropCanvas?.addEventListener("pointerdown", (event) => {
    cropDragging = true;
    cropLastPoint = [event.clientX, event.clientY];
    cropCanvas.setPointerCapture(event.pointerId);
  });
  cropCanvas?.addEventListener("pointermove", (event) => {
    if (!cropDragging || !cropState) return;
    cropState.x += event.clientX - cropLastPoint[0];
    cropState.y += event.clientY - cropLastPoint[1];
    cropLastPoint = [event.clientX, event.clientY];
    drawAvatarCrop();
  });
  cropCanvas?.addEventListener("pointerup", () => { cropDragging = false; });
  cropDialog?.querySelectorAll("[data-crop-cancel]").forEach((button) => button.addEventListener("click", () => closeCrop(true)));
  cropDialog?.querySelector("[data-crop-apply]")?.addEventListener("click", () => {
    if (!cropState || !cropInput || !cropCanvas) return;
    const output = doc.createElement("canvas");
    output.width = 512;
    output.height = 512;
    const outputContext = output.getContext("2d");
    const scaleToOutput = output.width / cropCanvas.width;
    const turned = Math.abs(cropState.rotation % 180) === 90;
    const width = turned ? cropState.image.height : cropState.image.width;
    const height = turned ? cropState.image.width : cropState.image.height;
    const imageScale = Math.max(cropCanvas.width / width, cropCanvas.height / height) * cropState.zoom * scaleToOutput;
    outputContext.clearRect(0, 0, output.width, output.height);
    outputContext.save();
    outputContext.beginPath();
    outputContext.arc(256, 256, 256, 0, Math.PI * 2);
    outputContext.clip();
    outputContext.translate(256 + cropState.x * scaleToOutput, 256 + cropState.y * scaleToOutput);
    outputContext.rotate(cropState.rotation * Math.PI / 180);
    outputContext.drawImage(cropState.image, -cropState.image.width * imageScale / 2, -cropState.image.height * imageScale / 2, cropState.image.width * imageScale, cropState.image.height * imageScale);
    outputContext.restore();
    output.toBlob((blob) => {
      if (!blob) return;
      const transfer = new DataTransfer();
      transfer.items.add(new File([blob], "cloudgate-avatar.png", { type: "image/png", lastModified: Date.now() }));
      const input = cropInput;
      input.files = transfer.files;
      closeCrop(false);
      const ready = new Event("change", { bubbles: true });
      ready.cropReady = true;
      input.dispatchEvent(ready);
    }, "image/png");
  });

  const footerEditor = doc.querySelector("[data-footer-editor]");
  if (footerEditor) {
    const list = footerEditor.querySelector("[data-footer-column-list]");
    const columnTemplate = doc.querySelector("[data-footer-column-template]");
    const linkTemplate = doc.querySelector("[data-footer-link-template]");
    const addLink = (column) => column.querySelector("[data-footer-link-list]").append(linkTemplate.content.cloneNode(true));
    footerEditor.addEventListener("click", (event) => {
      if (event.target.closest("[data-add-footer-column]")) list.append(columnTemplate.content.cloneNode(true));
      if (event.target.closest("[data-remove-footer-column]")) event.target.closest("[data-footer-column]")?.remove();
      if (event.target.closest("[data-add-footer-link]")) addLink(event.target.closest("[data-footer-column]"));
      if (event.target.closest("[data-remove-footer-link]")) event.target.closest("[data-footer-link]")?.remove();
    });
    footerEditor.addEventListener("submit", () => {
      const columns = [...list.querySelectorAll("[data-footer-column]")].map((column) => ({
        title: column.querySelector("[data-footer-column-title]").value,
        links: [...column.querySelectorAll("[data-footer-link]")].map((link) => ({
          label: link.querySelector("[data-footer-link-label]").value,
          url: link.querySelector("[data-footer-link-url]").value,
        })),
      }));
      footerEditor.querySelector("[data-footer-columns-value]").value = JSON.stringify(columns);
    });
  }

  const durationRange = doc.querySelector("[data-transition-duration-range]");
  const durationInput = doc.querySelector("[data-transition-duration-input]");
  const durationOutput = doc.querySelector("[data-transition-duration-output]");
  durationRange?.addEventListener("input", () => {
    durationInput.value = durationRange.value;
    durationOutput.textContent = `${durationRange.value} ms`;
  });
  doc.querySelectorAll("[data-color-proxy]").forEach((proxy) => {
    const input = proxy.parentElement.querySelector("input[type='text']");
    proxy.addEventListener("input", () => {
      input.value = proxy.value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  });
  const appearanceColorVariables = {
    transition_color_start: "--route-start",
    transition_color_middle: "--route-middle",
    transition_color_end: "--route-end",
    dialog_color_start: "--dialog-color-start",
    dialog_color_end: "--dialog-color-end",
    dialog_accent: "--dialog-accent",
  };
  doc.querySelectorAll(".appearance-color-field input[type='color']").forEach((input) => {
    const syncAppearanceColor = () => {
      const variable = appearanceColorVariables[input.name];
      if (variable) root.style.setProperty(variable, input.value);
      const output = input.closest(".appearance-color-field")?.querySelector("[data-color-value]");
      if (output) output.textContent = input.value.toUpperCase();
    };
    input.addEventListener("input", syncAppearanceColor);
  });
  const transitionForm = doc.querySelector("[data-transition-settings]");
  const refreshTransitionPreview = () => {
    const preview = transitionForm?.querySelector(".transition-live-preview");
    if (!preview) return;
    const colors = [...transitionForm.querySelectorAll(".color-input-pair input[type='text']")].map((input) => input.value);
    if (colors.length === 3 && colors.every((value) => /^#[0-9a-f]{6}$/i.test(value))) {
      preview.style.background = `linear-gradient(100deg,${colors.join(",")})`;
    }
  };
  transitionForm?.addEventListener("input", refreshTransitionPreview);
  durationInput?.addEventListener("input", () => {
    const value = Math.max(300, Math.min(2400, Number.parseInt(durationInput.value, 10) || 720));
    durationRange.value = String(value);
    durationOutput.textContent = `${value} ms`;
  });
  const fontForm = doc.querySelector("[data-font-settings]");
  fontForm?.addEventListener("change", (event) => {
    if (event.target.matches("input[type='radio']")) root.dataset.fontStyle = event.target.value;
  });
  doc.querySelectorAll("[data-dialog-range]").forEach((range) => {
    const key = range.dataset.dialogRange;
    const input = doc.querySelector(`[data-dialog-value='${key}']`);
    const output = doc.querySelector(`[data-dialog-output='${key}']`);
    range.addEventListener("input", () => {
      input.value = range.value;
      output.textContent = `${range.value} px`;
    });
  });
  const dialogAppearanceForm = doc.querySelector("[data-dialog-appearance-settings]");
  const refreshDialogPreview = () => {
    if (!dialogAppearanceForm) return;
    const colorInputs = [...dialogAppearanceForm.querySelectorAll(".appearance-color-field input[type='color']")];
    const [start, end, accent] = colorInputs.map((input) => input.value);
    if ([start, end, accent].every((value) => /^#[0-9a-f]{6}$/i.test(value))) {
      root.style.setProperty("--dialog-color-start", start);
      root.style.setProperty("--dialog-color-end", end);
      root.style.setProperty("--dialog-accent", accent);
    }
    const radius = dialogAppearanceForm.querySelector("[data-dialog-value='radius']")?.value;
    const width = dialogAppearanceForm.querySelector("[data-dialog-value='width']")?.value;
    const blur = dialogAppearanceForm.querySelector("[data-dialog-value='blur']")?.value;
    if (radius) root.style.setProperty("--dialog-radius", `${radius}px`);
    if (width) root.style.setProperty("--dialog-width", `${width}px`);
    if (blur) root.style.setProperty("--dialog-backdrop-blur", `${blur}px`);
    const style = dialogAppearanceForm.querySelector("input[name='dialog_style']:checked")?.value;
    const shadow = dialogAppearanceForm.querySelector("input[name='dialog_shadow']:checked")?.value;
    if (style) root.dataset.dialogStyle = style;
    if (shadow) root.dataset.dialogShadow = shadow;
  };
  dialogAppearanceForm?.addEventListener("input", refreshDialogPreview);
  dialogAppearanceForm?.addEventListener("change", refreshDialogPreview);
  doc.querySelectorAll("[data-dialog-preview]").forEach((button) => button.addEventListener("click", () => {
    pendingForm = null;
    refreshDialogPreview();
    const mode = button.dataset.dialogPreview;
    if (mode === "prompt") prepareSystemDialog("prompt", "输入内容", "");
    else if (mode === "alert") prepareSystemDialog("alert", "提示", "操作已完成。");
    else prepareSystemDialog("confirm", "确认操作", "是否继续？");
    dialog.showModal();
    if (mode === "prompt") requestAnimationFrame(() => dialogInput?.focus());
  }));

  const motionButton = doc.querySelector("[data-motion-toggle]");
  if (motionButton) {
    motionButton.textContent = reduced() ? "动效：精简" : "动效：跟随系统";
    motionButton.setAttribute("aria-pressed", String(root.dataset.motion === "reduce"));
  }
  motionButton?.addEventListener("click", () => {
    const next = root.dataset.motion === "reduce" ? "system" : "reduce";
    root.dataset.motion = next;
    motionButton.textContent = next === "reduce" ? "动效：精简" : "动效：跟随系统";
    motionButton.setAttribute("aria-pressed", String(next === "reduce"));
    try { localStorage.setItem("cloudgate-motion", next); } catch (_) {}
  });

  const emailResendState = doc.querySelector("[data-email-resend-seconds]");
  const emailResendButton = doc.querySelector("[data-email-resend-button]");
  const emailResendLabel = doc.querySelector("[data-email-resend-label]");
  if (emailResendState && emailResendButton && emailResendLabel) {
    let remaining = Math.max(0, Number.parseInt(emailResendState.dataset.emailResendSeconds, 10) || 0);
    const updateEmailResend = () => {
      if (remaining <= 0) {
        emailResendButton.disabled = false;
        emailResendLabel.textContent = "重新发送验证码";
        return false;
      }
      emailResendButton.disabled = true;
      emailResendLabel.textContent = `重新发送（${remaining} 秒）`;
      remaining -= 1;
      return true;
    };
    updateEmailResend();
    const emailResendTimer = window.setInterval(() => {
      if (!updateEmailResend()) window.clearInterval(emailResendTimer);
    }, 1000);
  }

  doc.querySelectorAll("[data-mail-template-form]").forEach((form) => {
    const source = form.querySelector(".mail-template-source");
    const editor = form.querySelector("[data-mail-template-editor]");
    const preview = form.querySelector("[data-mail-template-preview]");
    const toggle = form.querySelector("[data-mail-preview-toggle]");
    if (!source || !editor || !preview || !toggle || source.querySelector(".field-error")) return;
    const input = form.querySelector(`#${editor.dataset.target || "body_html"}`) || source.querySelector("textarea");
    if (!input) return;
    const commandButtons = [...form.querySelectorAll("[data-mail-command]")];
    const escapeMailHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[character]);
    const sanitizeMailPreview = (html) => {
      const allowed = new Set(["a", "blockquote", "br", "code", "div", "em", "h1", "h2", "h3", "li", "ol", "p", "pre", "span", "strong", "u", "s", "ul"]);
      const blocked = new Set(["script", "style", "iframe", "object", "embed", "link", "meta", "form", "input", "button", "svg", "math"]);
      const cleanNode = (node) => {
        if (node.nodeType === Node.TEXT_NODE) return doc.createTextNode(node.nodeValue || "");
        if (node.nodeType !== Node.ELEMENT_NODE) return doc.createTextNode("");
        const tag = node.tagName.toLowerCase();
        if (blocked.has(tag)) return doc.createTextNode("");
        if (!allowed.has(tag)) {
          const fragment = doc.createDocumentFragment();
          node.childNodes.forEach((child) => fragment.append(cleanNode(child)));
          return fragment;
        }
        const element = doc.createElement(tag);
        [...node.attributes].forEach((attribute) => {
          const name = attribute.name.toLowerCase();
          if (tag === "a" && name === "href" && /^(?:https?:|mailto:)/i.test(attribute.value)) element.setAttribute("href", attribute.value);
          if (name === "style" && !/(?:url\s*\(|expression|javascript|<|>)/i.test(attribute.value)) {
            attribute.value.split(";").forEach((declaration) => {
              const separator = declaration.indexOf(":");
              if (separator < 1) return;
              const property = declaration.slice(0, separator).trim().toLowerCase();
              const value = declaration.slice(separator + 1).trim();
              if (property && value) element.style.setProperty(property, value);
            });
          }
        });
        node.childNodes.forEach((child) => element.append(cleanNode(child)));
        return element;
      };
      const parsed = new DOMParser().parseFromString(html, "text/html");
      const output = doc.createElement("div");
      parsed.body.childNodes.forEach((child) => output.append(cleanNode(child)));
      return output.innerHTML;
    };
    const syncInput = () => { input.value = editor.innerHTML.trim(); };
    const renderPreview = () => {
      syncInput();
      const samples = {};
      doc.querySelectorAll("[data-insert-variable]").forEach((button) => {
        samples[button.dataset.insertVariable] = button.dataset.sample || button.dataset.insertVariable;
      });
      const rendered = input.value.replace(/{{\s*([A-Za-z0-9_]+)\s*}}/g, (_match, name) => escapeMailHtml(samples[name] ?? ""));
      preview.innerHTML = sanitizeMailPreview(rendered);
    };
    const setPreview = (enabled) => {
      form.classList.toggle("is-preview", enabled);
      toggle.setAttribute("aria-pressed", String(enabled));
      toggle.querySelector("span").textContent = enabled ? "继续编辑" : "预览";
      preview.setAttribute("aria-hidden", String(!enabled));
      commandButtons.forEach((button) => { button.disabled = enabled; });
      if (enabled) renderPreview();
      else editor.focus();
    };
    form.classList.add("is-enhanced");
    editor.innerHTML = input.value;
    editor.addEventListener("input", syncInput);
    form.addEventListener("submit", syncInput);
    toggle.addEventListener("click", () => setPreview(!form.classList.contains("is-preview")));
    commandButtons.forEach((button) => button.addEventListener("click", () => {
      const command = button.dataset.mailCommand;
      if (command === "createLink") {
        const selection = doc.getSelection();
        const savedRange = selection && selection.rangeCount ? selection.getRangeAt(0).cloneRange() : null;
        openSystemPrompt("插入链接", "请输入链接地址（https:// 或 mailto:）", "链接地址", "https://", (url) => {
          if (!url) return;
          editor.focus();
          if (savedRange) { selection.removeAllRanges(); selection.addRange(savedRange); }
          doc.execCommand("createLink", false, url);
          syncInput();
        });
        return;
      }
      editor.focus();
      if (command) doc.execCommand(command, false, null);
      syncInput();
    }));
    doc.querySelectorAll("[data-insert-variable]").forEach((button) => button.addEventListener("click", () => {
      if (form.classList.contains("is-preview")) setPreview(false);
      const token = `{{ ${button.dataset.insertVariable} }}`;
      editor.focus();
      if (!doc.execCommand("insertText", false, token)) editor.textContent += token;
      syncInput();
    }));
  });

  const isEligibleLink = (link) => {
    if (!link || link.target === "_blank" || link.hasAttribute("download")) return false;
    if (link.origin !== location.origin || link.pathname === location.pathname && link.search === location.search) return false;
    return true;
  };
  doc.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest("a[href]");
    if (!isEligibleLink(link) || reduced()) return;
    event.preventDefault();
    try { sessionStorage.setItem("cloudgate-route-transition", JSON.stringify({ startedAt: Date.now() })); } catch (_) {}
    root.classList.add("is-page-leaving");
    const style = root.dataset.pageTransition;
    const duration = Math.max(300, Math.min(2400, Number.parseInt(root.dataset.transitionDuration, 10) || 720));
    setTimeout(() => { location.href = link.href; }, style === "none" ? 0 : Math.round(duration * .58));
  });
  window.addEventListener("pageshow", () => root.classList.remove("is-page-leaving"));
  if (root.classList.contains("is-page-entering")) setTimeout(() => root.classList.remove("is-page-entering"), 1200);
})();
