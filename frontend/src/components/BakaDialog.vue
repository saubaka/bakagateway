<template>
  <dialog
    ref="element"
    class="modal app-system-dialog baka-confirm-dialog"
    :class="{ 'is-danger': dialogState.tone === 'danger' }"
    :data-dialog-mode="dialogState.mode"
    aria-labelledby="baka-dialog-title"
    @cancel.prevent="cancel"
    @click="onBackdrop"
  >
    <div class="app-system-dialog__content">
      <header class="modal__header">
        <div>
          <span class="eyebrow">{{ dialogState.tone === "danger" ? "请谨慎确认" : "BAKA" }}</span>
          <h2 id="baka-dialog-title">{{ dialogState.title }}</h2>
        </div>
        <button class="icon-button icon-button--small" type="button" aria-label="关闭" @click="cancel">×</button>
      </header>
      <p>{{ dialogState.message }}</p>
      <form class="form-stack" @submit.prevent="submit">
        <label v-if="showField" class="field app-system-dialog__field">
          <span class="field__label">{{ fieldLabel }}</span>
          <input
            ref="input"
            v-model="dialogState.value"
            :type="dialogState.inputType"
            :placeholder="dialogState.placeholder"
            :autocomplete="dialogState.inputType === 'password' ? 'new-password' : 'off'"
          />
        </label>
        <p v-if="dialogState.requiredText" class="dialog-required-hint">
          请输入 <strong>{{ dialogState.requiredText }}</strong> 以继续。
        </p>
        <p v-if="problem" class="dialog-problem" role="status">{{ problem }}</p>
        <div class="button-row dialog-actions">
          <button class="button button--soft" type="button" @click="cancel">
            {{ dialogState.cancelLabel }}
          </button>
          <button
            class="button"
            :class="dialogState.tone === 'danger' ? 'button--danger' : 'button--primary'"
            type="submit"
            :disabled="!canSubmit"
          >
            {{ dialogState.confirmLabel }}
          </button>
        </div>
      </form>
    </div>
  </dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { closeDialog, dialogState, openDialog, settleDialog } from "../dialog";

const element = ref<HTMLDialogElement | null>(null);
const input = ref<HTMLInputElement | null>(null);
const showField = computed(() => dialogState.mode === "prompt" || Boolean(dialogState.requiredText));
const fieldLabel = computed(() =>
  dialogState.fieldLabel || (dialogState.requiredText ? "确认文字" : "请输入"),
);
const isSecret = computed(() => dialogState.inputType === "password");
const submitted = (): string => (isSecret.value ? dialogState.value : dialogState.value.trim());
const problem = computed(() => (dialogState.mode === "prompt" && dialogState.value && dialogState.validate ? dialogState.validate(submitted()) : ""));
const canSubmit = computed(() => {
  if (dialogState.requiredText) return dialogState.value.trim() === dialogState.requiredText;
  if (dialogState.mode === "prompt") return submitted().length > 0 && !problem.value;
  return true;
});

watch(
  () => dialogState.open,
  async (isOpen) => {
    if (isOpen) {
      await nextTick();
      openDialog(element.value);
      await nextTick();
      if (showField.value) input.value?.focus();
      return;
    }
    closeDialog(element.value);
  },
);

function cancel(): void {
  settleDialog(dialogState.mode === "prompt" ? null : false);
}

function submit(): void {
  if (!canSubmit.value) return;
  settleDialog(dialogState.mode === "prompt" ? submitted() : true);
}

function onBackdrop(event: MouseEvent): void {
  if (event.target === element.value) cancel();
}
</script>
