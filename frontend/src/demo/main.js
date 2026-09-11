import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './demo.css'
import DemoApp from './DemoApp.vue'

createApp(DemoApp).use(ElementPlus).mount('#demo-app')
