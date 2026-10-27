<template>
  <div class="sakura-wallpaper" aria-hidden="true">
    <img src="/media/studio-lake-wallpaper-volc-v2.png" alt="" decoding="async" fetchpriority="high" />
  </div>
</template>

<style scoped>
.sakura-wallpaper{position:fixed;inset:0;z-index:0;overflow:hidden;pointer-events:none;background:#081426}
.sakura-wallpaper::after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,rgba(13,29,51,.44),rgba(16,34,58,.24) 48%,rgba(18,38,63,.1)),linear-gradient(180deg,rgba(15,32,55,.04),transparent 38%,rgba(15,32,55,.18))}
.sakura-wallpaper img{position:absolute;inset:0;display:block;width:100%;height:100%}
.sakura-wallpaper img{object-fit:cover;object-position:center;filter:brightness(1.16) saturate(.96)}
@media(max-width:760px){.sakura-wallpaper img{object-position:42% center}.sakura-wallpaper:after{background:linear-gradient(180deg,rgba(13,29,51,.26),rgba(15,32,55,.4))}}
</style>
