<template>
  <div class="field" :class="{ 'field--wide': wide }">
    <label :for="inputId" class="field__label">{{ label }}</label>
    <span class="password-entry">
      <input
        :id="inputId"
        v-model="model"
        :type="visible ? 'text' : 'password'"
        :autocomplete="autocomplete"
        :placeholder="placeholder"
        :disabled="disabled"
        :required="required"
        @keydown="updateCaps"
        @keyup="updateCaps"
        @blur="capsLock = false"
      />
      <button
        class="password-entry__toggle"
        type="button"
        :aria-label="visible ? '隐藏密码' : '显示密码'"
        :aria-pressed="visible ? 'true' : 'false'"
        :disabled="disabled"
        @click="visible = !visible"
      >
        {{ visible ? "隐藏" : "显示" }}
      </button>
    </span>
    <small v-if="capsLock" class="password-entry__caps" role="status"
      >大写锁定已开启</small
    >
  </div>
</template>

<script setup lang="ts">
import { ref, useId } from "vue";

withDefaults(
  defineProps<{
    label?: string;
    autocomplete?: string;
    placeholder?: string;
    wide?: boolean;
    disabled?: boolean;
    required?: boolean;
  }>(),
  {
    label: "密码",
    autocomplete: "current-password",
    placeholder: "",
    wide: true,
    disabled: false,
    required: false,
  },
);

const model = defineModel<string>({ required: true });
const inputId = useId();
const visible = ref(false);
const capsLock = ref(false);

function updateCaps(event: KeyboardEvent): void {
  capsLock.value = event.getModifierState("CapsLock");
}
</script>
