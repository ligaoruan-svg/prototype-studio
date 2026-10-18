import { createApp } from 'vue'
import App from './App.vue'
import './styles/style.css'
import { t, syncDocument } from './lib/i18n.js'

const app = createApp(App)
// 模板里用 $t('中文原文')：切语言时 locale 变了，用到它的地方会自己重渲染
app.config.globalProperties.$t = t
syncDocument()
app.mount('#app')
