import { defineStore } from 'pinia'
import { shallowRef } from 'vue'
export const useImageDraft = defineStore('image-draft', () => {
  const image = shallowRef<File|null>(null)
  function take() { const value=image.value; image.value=null; return value }
  return { image, take }
})
