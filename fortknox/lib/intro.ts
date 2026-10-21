// The games-feed introduction (components/games/intro.tsx) stays closed for
// readers who closed it: this runs in <head> before first paint and marks
// <html> so the strip is hidden by CSS, with no flash.
export const INTRO_KEY = "hs-intro";
export const introScript = `try{if(localStorage.getItem("${INTRO_KEY}")==="0")document.documentElement.classList.add("no-intro")}catch(e){}`;
