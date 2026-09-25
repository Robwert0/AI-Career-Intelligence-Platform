export type Theme = 'dark' | 'light'

export const THEME_STORAGE_KEY = 'theme'

export function resolveTheme(stored: string | null, prefersLight: boolean): Theme {
  if (stored === 'dark' || stored === 'light') return stored
  return prefersLight ? 'light' : 'dark'
}

// Runs in <head> before first paint, so it can't import resolveTheme; the test keeps the two in step.
export const themeInitScript = `(function(){var s=null;try{s=localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)})}catch(e){}var t=s==="dark"||s==="light"?s:matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";document.documentElement.dataset.theme=t})()`
