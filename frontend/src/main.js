import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './demo/demo.css'
import './demo/evidence-panel.css'
import './demo/pages.css'
import './demo/settings.css'
import './demo/responsive.css'
import DemoApp from './demo/DemoApp.vue'

createApp(DemoApp).use(ElementPlus).mount('#app')
