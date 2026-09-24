import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// Set VITE_API_URL in Vercel environment variables to point to your Render backend URL.
// Example: VITE_API_URL=https://upi-dispute-agent-api.onrender.com
export default defineConfig({
  plugins: [react()],
})
