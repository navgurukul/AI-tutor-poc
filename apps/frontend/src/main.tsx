import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { VOICE_MODEL_URL, VOICE_CONFIG_URL } from './config/voice'
import { ensureFreshVoiceModelCache } from './utils/ensureFreshVoiceModelCache'

ensureFreshVoiceModelCache([VOICE_MODEL_URL, VOICE_CONFIG_URL]).finally(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
