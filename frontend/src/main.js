import { createApp } from 'vue'
import { ElDropdown, ElIcon, ElSlider } from 'element-plus'
import 'element-plus/es/components/dropdown/style/css'
import 'element-plus/es/components/icon/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/slider/style/css'
import './demo/demo.css'
import './demo/evidence-panel.css'
import './demo/pages.css'
import './demo/settings.css'
import './demo/responsive.css'
import DemoApp from './demo/DemoApp.vue'

// Only the handful of Element Plus components actually used by the views are
// registered here (evaluation I-20): el-icon, el-slider, and the el-dropdown
// row menu, plus the imperative ElMessage/ElMessageBox styles. Per-component
// style entries pull in their own dependencies (buttons, inputs, popper…).
const app = createApp(DemoApp)
app.use(ElIcon)
app.use(ElDropdown)
app.use(ElSlider)
app.mount('#app')
