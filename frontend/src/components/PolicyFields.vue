<template>
  <div class="grid gap-4 grid-cols-[repeat(auto-fit,minmax(12rem,1fr))] text-sm">
    <label class="block">
      Name
      <input :value="modelValue.name" required maxlength="40" class="mt-1 w-full py-2 px-3 text-sm" @input="set('name', $event.target.value)" />
    </label>
    <label class="block">
      Start time
      <input type="time" required :value="time" class="mt-1 w-full py-2 px-3 text-sm" @input="setTime($event.target.value)" />
    </label>
    <fieldset class="border-0 m-0 p-0 col-span-full">
      <legend class="mb-1.5">Runs</legend>
      <div class="flex flex-wrap items-center gap-x-5 gap-y-2">
        <label class="inline-flex items-center gap-2"><input type="radio" value="daily" :checked="modelValue.frequency === 'daily'" class="accent-brand" @change="set('frequency', 'daily')" /> Every day</label>
        <label class="inline-flex items-center gap-2"><input type="radio" value="weekly" :checked="modelValue.frequency === 'weekly'" class="accent-brand" @change="set('frequency', 'weekly')" /> On these days:</label>
        <label v-for="d in dayNames" :key="d.id" class="inline-flex items-center gap-1.5" :class="modelValue.frequency === 'weekly' ? '' : 'opacity-50'">
          <input type="checkbox" class="accent-brand" :checked="days.has(d.id)" :disabled="modelValue.frequency !== 'weekly'" @change="toggleDay(d.id, $event.target.checked)" />{{ d.label }}
        </label>
      </div>
    </fieldset>
    <fieldset class="border-0 m-0 p-0 col-span-full">
      <legend class="mb-1.5">Keep restore points</legend>
      <div class="flex flex-wrap gap-4">
        <label v-for="k in keeps" :key="k.id" class="inline-flex items-center gap-2">
          <input type="number" :min="0" :max="k.max" :value="modelValue[k.id]" class="w-20 py-1.5 px-2 text-sm text-center" @input="set(k.id, Number($event.target.value))" />
          {{ k.label }}
        </label>
      </div>
    </fieldset>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ modelValue: { type: Object, required: true } })
const emit = defineEmits(['update:modelValue'])

const dayNames = [
  { id: 0, label: 'Mon' }, { id: 1, label: 'Tue' }, { id: 2, label: 'Wed' }, { id: 3, label: 'Thu' },
  { id: 4, label: 'Fri' }, { id: 5, label: 'Sat' }, { id: 6, label: 'Sun' },
]
const keeps = [
  { id: 'keep_daily', label: 'daily', max: 90 },
  { id: 'keep_weekly', label: 'weekly', max: 52 },
  { id: 'keep_monthly', label: 'monthly', max: 120 },
]

const time = computed(() => `${String(props.modelValue.hour).padStart(2, '0')}:${String(props.modelValue.minute).padStart(2, '0')}`)
const days = computed(() => new Set(String(props.modelValue.days || '').split(',').filter((d) => d !== '').map(Number)))

function set(key, value) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

function setTime(v) {
  const [h, m] = (v || '00:00').split(':').map(Number)
  emit('update:modelValue', { ...props.modelValue, hour: h || 0, minute: m || 0 })
}

function toggleDay(id, on) {
  const s = new Set(days.value)
  if (on) s.add(id); else s.delete(id)
  set('days', [...s].sort().join(','))
}
</script>
