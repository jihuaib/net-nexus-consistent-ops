import { createApp } from 'vue';
import { LUCIDE_CONTEXT } from '@lucide/vue';
import App from './App.vue';
import './style.css';

createApp(App)
  .provide(LUCIDE_CONTEXT, {
    size: 18,
    color: 'currentColor',
    strokeWidth: 2,
    absoluteStrokeWidth: false,
    class: '',
  })
  .mount('#app');
