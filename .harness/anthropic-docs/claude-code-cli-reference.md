# Claude Code CLI Reference

**Source:** https://docs.anthropic.com/en/docs/claude-code/cli-reference
**Fetched:** 2026-04-11T19:55:13Z

---

CLI reference - Claude Code Docs                                      (function(a,b){try{let c=document.getElementById("banner")?.innerText;if(c){for(let d=0;d          ((a,b,c,d,e,f,g,h)=>{let i=document.documentElement,j=["light","dark"];function k(b){var c;(Array.isArray(a)?a:[a]).forEach(a=>{let c="class"===a,d=c&&f?e.map(a=>f[a]||a):e;c?(i.classList.remove(...d),i.classList.add(f&&f[b]?f[b]:b)):i.setAttribute(a,b)}),c=b,h&&j.includes(c)&&(i.style.colorScheme=c)}if(d)k(d);else try{let a=localStorage.getItem(b)||c,d=g&&"system"===a?window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light":a;k(d)}catch(a){}})("class","isDarkMode","system",null,["dark","light","true","false","system"],{"true":"dark","false":"light","dark":"dark","light":"light"},true,true)  :root{--banner-height:0px!important}  (self.__next_s=self.__next_s||[]).push([0,{"children":"(function j(a,b,c,d,e){try{let f,g,h=[];try{h=window.location.pathname.split(\"/\").filter(a=>\"\"!==a&&\"global\"!==a).slice(0,2)}catch{h=[]}let i=h.find(a=>c.includes(a)),j=[];for(let c of(i?j.push(i):j.push(b),j.push(\"global\"),j)){if(!c)continue;let b=a[c];if(b?.content){f=b.content,g=c;break}}if(!f)return void document.documentElement.setAttribute(d,\"hidden\");let k=!0,l=0;for(;l    :root {
--font-family-headings-custom: "Anthropic Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
--font-family-body-custom: "Anthropic Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
}
:root {
--primary: 14 14 14;
--primary-light: 212 162 127;
--primary-dark: 14 14 14;
--tooltip-foreground: 255 255 255;
--background-light: 253 253 247;
--background-dark: 9 9 11;
--gray-50: 243 243 243;
--gray-100: 238 238 238;
--gray-200: 222 222 222;
--gray-300: 206 206 206;
--gray-400: 158 158 158;
--gray-500: 112 112 112;
--gray-600: 80 80 80;
--gray-700: 62 62 62;
--gray-800: 37 37 37;
--gray-900: 23 23 23;
--gray-950: 10 10 10;
}
(function() {
function loadKatex() {
const link = document.querySelector('link[href="https://d4tuoctqmanu0.cloudfront.net/katex.min.css"]');
if (link) link.rel = 'stylesheet';
}
if (document.readyState === 'loading') {
document.addEventListener('DOMContentLoaded', loadKatex);
} else {
loadKatex();
}
})();
(self.__next_s=self.__next_s||[]).push([0,{"suppressHydrationWarning":true,"children":"(function(a,b,c,d){var e;let f,g=\"mint\"===d||\"linden\"===d?\"sidebar\":\"sidebar-content\",h=(e=d,f=\"navbar-transition\",\"maple\"===e&&(f+=\"-maple\"),f),[i,j]=(()=>{switch(d){case\"almond\":return[\"[--scroll-mt:2.5rem]\",\"[--scroll-mt:2.5rem]\"];case\"luma\":return[\"lg:[--scroll-mt:6rem]\",\"lg:[--scroll-mt:6rem]\"];case\"sequoia\":return[\"lg:[--scroll-mt:8.5rem]\",\"lg:[--scroll-mt:11rem]\"];default:return[\"lg:[--scroll-mt:9.5rem]\",\"lg:[--scroll-mt:12rem]\"]}})();function k(){document.documentElement.classList.add(i)}function l(a){document.getElementById(g)?.style.setProperty(\"top\",`${a}rem`)}function m(a){document.getElementById(g)?.style.setProperty(\"height\",`calc(100vh - ${a}rem)`)}function n(a,b){!a&&b||a&&!b?(k(),document.documentElement.classList.remove(j)):a&&b&&(document.documentElement.classList.add(j),document.documentElement.classList.remove(i))}let o=document.documentElement.getAttribute(\"data-banner-state\"),p=null!=o?\"visible\"===o:b;switch(d){case\"mint\":l(c),n(a,p);break;case\"palm\":case\"aspen\":case\"sequoia\":l(c),m(c),n(a,p);break;case\"luma\":k();break;case\"linden\":l(c),p&&k();break;case\"almond\":k(),l(c),m(c)}let q=function(){let a=document.createElement(\"style\");return a.appendChild(document.createTextNode(\"*,*::before,*::after{-webkit-transition:none!important;-moz-transition:none!important;-o-transition:none!important;-ms-transition:none!important;transition:none!important}\")),document.head.appendChild(a),function(){window.getComputedStyle(document.body),setTimeout(()=>{document.head.removeChild(a)},1)}}();(\"requestAnimationFrame\"in globalThis?requestAnimationFrame:setTimeout)(()=>{let a;a=!1,a=window.scrollY>50,document.getElementById(h)?.setAttribute(\"data-is-opaque\",`${!!a}`),q()})})(\n  true,\n  false,\n  (function m(a,b,c){let d=document.documentElement.getAttribute(\"data-banner-state\"),e=2.5*!!(null!=d?\"visible\"===d:b),f=3*!!a,g=4,h=e+g+f;switch(c){case\"mint\":case\"palm\":break;case\"aspen\":f=2.5*!!a,g=3.5,h=e+f+g;break;case\"luma\":g=3,h=e+g;break;case\"linden\":g=4,h=e+g;break;case\"almond\":g=3.5,h=e+g;break;case\"sequoia\":f=3*!!a,g=3,h=e+g+f}return h})(true, false, \"mint\"),\n  \"mint\",\n)","id":"_mintlify-scroll-top-script"}])  Skip to main content  (function j(a,b,c,d){try{if(window.matchMedia("(max-width: 1024px)").matches||!d){document.documentElement.style.setProperty(c,"0px"),document.documentElement.setAttribute("data-assistant-state","closed"),d||localStorage.setItem(a,"false");return}let e=localStorage.getItem(a);if(null===e){document.documentElement.style.setProperty(c,"0px"),document.documentElement.setAttribute("data-assistant-state","closed");return}let f=JSON.parse(e),g=localStorage.getItem(b),h=null!==g?JSON.parse(g):368;document.documentElement.style.setProperty(c,f?h+"px":"0px"),document.documentElement.setAttribute("data-assistant-state",f?"open":"closed")}catch(a){document.documentElement.style.setProperty(c,"0px"),document.documentElement.setAttribute("data-assistant-state","closed")}})(
"chat-assistant-sheet-open",
"chat-assistant-sheet-width",
"--assistant-sheet-width",
true
)              Claude Code Docs  home page            English                  Search...   ⌘ K            Ask AI        Claude Developer Platform    Claude Code on the Web        Claude Code on the Web                                                  Search...                        Navigation         Reference       CLI reference       Getting started    Build with Claude Code    Deployment    Administration    Configuration    Reference    Agent SDK    What&#x27;s New    Resources                    Reference        CLI reference          Commands          Environment variables          Tools reference          Interactive mode          Checkpointing          Hooks reference          Plugins reference          Channels reference             document.documentElement.setAttribute('data-page-mode', "none");  (self.__next_s=self.__next_s||[]).push([0,{"suppressHydrationWarning":true,"children":"(function n(a,b){if(!document.getElementById(\"footer\")?.classList.contains(\"advanced-footer\")||\"maple\"===b||\"willow\"===b||\"almond\"===b||\"luma\"===b||\"sequoia\"===b)return;let c=document.documentElement.getAttribute(\"data-page-mode\"),d=document.getElementById(\"navbar\"),e=document.getElementById(\"navigation-items\"),f=document.getElementById(\"sidebar\"),g=document.getElementById(\"footer\"),h=document.getElementById(\"table-of-contents-content\"),i=16*a;if(!g||\"center\"===c)return;let j=g.getBoundingClientRect().top,k=window.innerHeight-j,l=(e?.clientHeight??0)+i+32*(\"mint\"===b||\"linden\"===b);if(f&&e)if(k>0){let a=Math.max(0,l-j);f.style.bottom=`${k}px`,f.style.top=`${i-a}px`}else f.style.bottom=\"\",f.style.top=`${a}rem`,f.style.height=\"auto\";h&&d&&(k>0?h.style.top=\"custom\"===c?`${d.clientHeight-k}px`:`${40+d.clientHeight-k}px`:h.style.top=\"\")})(\n  (function m(a,b,c){let d=document.documentElement.getAttribute(\"data-banner-state\"),e=2.5*!!(null!=d?\"visible\"===d:b),f=3*!!a,g=4,h=e+g+f;switch(c){case\"mint\":case\"palm\":break;case\"aspen\":f=2.5*!!a,g=3.5,h=e+f+g;break;case\"luma\":g=3,h=e+g;break;case\"linden\":g=4,h=e+g;break;case\"almond\":g=3.5,h=e+g;break;case\"sequoia\":f=3*!!a,g=3,h=e+g+f}return h})(true, false, \"mint\"),\n  \"mint\",\n)","id":"_mintlify-footer-and-sidebar-scroll-script"}])
/* These styles mirror our design system (converted to plain CSS with Claude's help) from https://ui.product.ant.dev/button */
/* Base button styles */
.btn {
position: relative;
display: inline-flex;
gap: 0.5rem;
align-items: center;
justify-content: center;
flex-shrink: 0;
min-width: 5rem;
height: 2.25rem;
padding: 0.5rem 1rem;
white-space: nowrap;
font-family: Styrene;
font-weight: 600;
border-radius: 0.5rem;
&:active {
transform: scale(0.985);
}
/* Size variants */
&.size-xs {
height: 1.75rem;
min-width: 3.5rem;
padding: 0 0.5rem;
border-radius: 0.25rem;
font-size: 0.75rem;
gap: 0.25rem;
}
&.size-sm {
height: 2rem;
min-width: 4rem;
padding: 0 0.75rem;
border-radius: 0.375rem;
font-size: 0.75rem;
}
&.size-lg {
height: 2.75rem;
min-width: 6rem;
padding: 0 1.25rem;
border-radius: 0.6rem;
}
&:disabled {
pointer-events: none;
opacity: 0.5;
box-shadow: none;
}
&:focus-visible {
outline: none;
--tw-ring-offset-shadow: var(--tw-ring-inset) 0 0 0 var(--tw-ring-offset-width) var(--tw-ring-offset-color);
--tw-ring-shadow: var(--tw-ring-inset) 0 0 0 calc(1px + var(--tw-ring-offset-width)) var(--tw-ring-color);
box-shadow: var(--tw-ring-offset-shadow), var(--tw-ring-shadow);
}
/* Primary variant */
&.primary {
font-weight: 600;
color: hsl(var(--oncolor-100));
background-color: hsl(var(--accent-main-100));
background-image: linear-gradient(
to right,
hsl(var(--accent-main-100)) 0%,
hsl(var(--accent-main-200) / 0.5) 50%,
hsl(var(--accent-main-200)) 100%
);
background-size: 200% 100%;
background-position: 0% 0%;
border: 0.5px solid hsl(var(--border-300) / 0.25);
box-shadow:
inset 0 0.5px 0px rgba(255, 255, 0, 0.15),
0 1px 1px rgba(0, 0, 0, 0.05);
text-shadow: 0 1px 2px rgb(0 0 0 / 10%);
transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1);
&:hover {
background-position: 100% 0%;
background-image: linear-gradient(
to right,
hsl(var(--accent-main-200)) 0%,
hsl(var(--accent-main-200)) 100%
);
}
&:active {
background-color: hsl(var(--accent-main-000));
box-shadow: inset 0 1px 6px rgba(0, 0, 0, 0.2);
transform: scale(0.985);
}
}
/* Flat variant */
&.flat {
font-weight: 500;
color: hsl(var(--oncolor-100));
background-color: hsl(var(--accent-main-100));
transition: background-color 150ms;
&:hover {
background-color: hsl(var(--accent-main-200));
}
}
/* Secondary variant */
&.secondary {
font-weight: 600;
color: hsl(var(--text-100) / 0.9);
background-image: radial-gradient(
ellipse at center,
hsl(var(--bg-500) / 0.1) 50%,
hsl(var(--bg-500) / 0.3) 100%
);
border: 0.5px solid hsl(var(--border-400));
transition: color 150ms, background-color 150ms;
&:hover {
color: hsl(var(--text-000));
background-color: hsl(var(--bg-500) / 0.6);
}
&:active {
background-color: hsl(var(--bg-500) / 0.5);
}
}
/* Outline variant */
&.outline {
font-weight: 600;
color: hsl(var(--text-200));
background-color: transparent;
border: 1.5px solid currentColor;
transition: color 150ms, background-color 150ms;
&:hover {
color: hsl(var(--text-100));
background-color: hsl(var(--bg-400));
border-color: hsl(var(--bg-400));
}
}
/* Ghost variant */
&.ghost {
color: hsl(var(--text-200));
border-color: transparent;
transition: color 150ms, background-color 150ms;
&:hover {
color: hsl(var(--text-100));
background-color: hsl(var(--bg-500) / 0.4);
}
&:active {
background-color: hsl(var(--bg-400));
}
}
/* Underline variant */
&.underline {
opacity: 0.8;
text-decoration-line: none;
text-underline-offset: 3px;
transition: all 150ms;
&:hover {
opacity: 1;
text-decoration-line: underline;
}
&:active {
transform: scale(0.985);
}
}
/* Danger variant */
&.danger {
font-weight: 600;
color: hsl(var(--oncolor-100));
background-color: hsl(var(--danger-100));
transition: background-color 150ms;
&:hover {
background-color: hsl(var(--danger-200));
}
}
}
/* Anthropic Sans - Static fonts from assets.claude.ai */
@font-face {
font-family: "Anthropic Sans";
src: url("https://assets.claude.ai/Fonts/AnthropicSans-Text-Regular-Static.otf") format("opentype");
font-weight: 400;
font-style: normal;
font-display: swap;
}
@font-face {
font-family: "Anthropic Sans";
src: url("https://assets.claude.ai/Fonts/AnthropicSans-Text-RegularItalic-Static.otf") format("opentype");
font-weight: 400;
font-style: italic;
font-display: swap;
}
@font-face {
font-family: "Anthropic Sans";
src: url("https://assets.claude.ai/Fonts/AnthropicSans-Text-Medium-Static.otf") format("opentype");
font-weight: 500;
font-style: normal;
font-display: swap;
}
@font-face {
font-family: "Anthropic Sans";
src: url("https://assets.claude.ai/Fonts/AnthropicSans-Text-MediumItalic-Static.otf") format("opentype");
font-weight: 500;
font-style: italic;
font-display: swap;
}
@font-face {
font-family: "Anthropic Sans";
src: url("https://assets.claude.ai/Fonts/AnthropicSans-Text-Semibold-Static.otf") format("opentype");
font-weight: 600;
font-style: normal;
font-display: swap;
}
@font-face {
font-family: "Anthropic Sans";
src: url("https://assets.claude.ai/Fonts/AnthropicSans-Text-SemiboldItalic-Static.otf") format("opentype");
font-weight: 600;
font-style: italic;
font-display: swap;
}
@font-face {
font-family: "Anthropic Sans";
src: url("https://assets.claude.ai/Fonts/AnthropicSans-Text-Bold-Static.otf") format("opentype");
font-weight: 700;
font-style: normal;
font-display: swap;
}
@font-face {
font-family: "Anthropic Sans";
src: url("https://assets.claude.ai/Fonts/AnthropicSans-Text-BoldItalic-Static.otf") format("opentype");
font-weight: 700;
font-style: italic;
font-display: swap;
}
/* Anthropic Serif Display - for headlines */
@font-face {
font-family: "Anthropic Serif Display";
src: url("https://assets.claude.ai/Fonts/AnthropicSerif-Display-Regular-Static.otf") format("opentype");
font-weight: 400;
font-style: normal;
font-display: swap;
}
@font-face {
font-family: "Anthropic Serif Display";
src: url("https://assets.claude.ai/Fonts/AnthropicSerif-Display-RegularItalic-Static.otf") format("opentype");
font-weight: 400;
font-style: italic;
font-display: swap;
}
@font-face {
font-family: "Anthropic Serif Display";
src: url("https://assets.claude.ai/Fonts/AnthropicSerif-Display-Medium-Static.otf") format("opentype");
font-weight: 500;
font-style: normal;
font-display: swap;
}
@font-face {
font-family: "Anthropic Serif Display";
src: url("https://assets.claude.ai/Fonts/AnthropicSerif-Display-Semibold-Static.otf") format("opentype");
font-weight: 600;
font-style: normal;
font-display: swap;
}
@font-face {
font-family: "Anthropic Serif Display";
src: url("https://assets.claude.ai/Fonts/AnthropicSerif-Display-Bold-Static.otf") format("opentype");
font-weight: 700;
font-style: normal;
font-display: swap;
}
/* Anthropic Serif - Static fonts from assets.claude.ai */
@font-face {
font-family: "Anthropic Serif";
src: url("https://assets.claude.ai/Fonts/AnthropicSerif-Text-Regular-Static.otf") format("opentype");
font-weight: 400;
font-style: normal;
font-display: swap;
}
@font-face {
font-family: "Anthropic Serif";
src: url("https://assets.claude.ai/Fonts/AnthropicSerif-Text-RegularItalic-Static.otf") format("opentype");
font-weight: 400;
font-style: italic;
font-display: swap;
}
@font-face {
font-family: "Anthropic Serif";
src: url("https://assets.claude.ai/Fonts/AnthropicSerif-Text-Medium-Static.otf") format("opentype");
font-weight: 500;
font-style: normal;
font-display: swap;
}
@font-face {
font-family: "Anthropic Serif";
src: url("https://assets.claude.ai/Fonts/AnthropicSerif-Text-MediumItalic-Static.otf") format("opentype");
font-weight: 500;
font-style: italic;
font-display: swap;
}
@font-face {
font-family: "Anthropic Serif";
src: url("https://assets.claude.ai/Fonts/AnthropicSerif-Text-Semibold-Static.otf") format("opentype");
font-weight: 600;
font-style: normal;
font-display: swap;
}
@font-face {
font-family: "Anthropic Serif";
src: url("https://assets.claude.ai/Fonts/AnthropicSerif-Text-SemiboldItalic-Static.otf") format("opentype");
font-weight: 600;
font-style: italic;
font-display: swap;
}
@font-face {
font-family: "Anthropic Serif";
src: url("https://assets.claude.ai/Fonts/AnthropicSerif-Text-Bold-Static.otf") format("opentype");
font-weight: 700;
font-style: normal;
font-display: swap;
}
@font-face {
font-family: "Anthropic Serif";
src: url("https://assets.claude.ai/Fonts/AnthropicSerif-Text-BoldItalic-Static.otf") format("opentype");
font-weight: 700;
font-style: italic;
font-display: swap;
}
/* Color variables copied from https://github.com/anthropics/apps/blob/main/packages/ui/themes/generated/theme-colors.css */
:root {
--always-white: 0 0% 100%;
--always-black: 0 0% 0%;
--constant-book-cloth: 15 55% 80%;
--constant-clay: 15 60% 85%;
--constant-kraft: 25 40% 83%;
--constant-manilla: 40 20% 92%;
--constant-slate-000: 0 0% 100%;
--constant-slate-050: 48 33.3% 97.1%;
--constant-slate-100: 53 28.6% 94.5%;
--constant-slate-150: 48 25% 92.2%;
--constant-slate-200: 50 20.7% 88.6%;
--constant-slate-250: 51 16.5% 84.5%;
--constant-slate-300: 50 11.5% 79.6%;
--constant-slate-350: 50 9% 73.7%;
--constant-slate-400: 49 6.5% 66.9%;
--constant-slate-450: 48 4.8% 59.2%;
--constant-slate-500: 53 3.2% 51.4%;
--constant-slate-550: 51 3.1% 43.7%;
--constant-slate-600: 48 2.7% 35.9%;
--constant-slate-650: 48 3.4% 29.2%;
--constant-slate-700: 60 2.5% 23.3%;
--constant-slate-750: 60 2.1% 18.4%;
--constant-slate-800: 60 2.7% 14.5%;
--constant-slate-850: 30 3.3% 11.8%;
--constant-slate-900: 30 4% 9.8%;
--constant-slate-950: 60 2.6% 7.6%;
--constant-slate-1000: 60 3.4% 5.7%;
}
:root:not(.dark) {
--accent-brand: 15 63.1% 59.6%;
--accent-main-000: 15 55.6% 52.4%;
--accent-main-100: 15 55.6% 52.4%;
--accent-main-200: 15 63.1% 59.6%;
--accent-main-900: 0 0% 0%;
--accent-pro-000: 251 34.2% 33.3%;
--accent-pro-100: 251 40% 45.1%;
--accent-pro-200: 251 61% 72.2%;
--accent-pro-900: 253 33.3% 91.8%;
--accent-secondary-000: 210 73.7% 40.2%;
--accent-secondary-100: 210 70.9% 51.6%;
--accent-secondary-200: 210 70.9% 51.6%;
--accent-secondary-900: 211 72% 90%;
--bg-000: 0 0% 100%;
--bg-100: 48 33.3% 97.1%;
--bg-200: 53 28.6% 94.5%;
--bg-300: 48 25% 92.2%;
--bg-400: 50 20.7% 88.6%;
--bg-500: 50 20.7% 88.6%;
--border-100: 30 3.3% 11.8%;
--border-200: 30 3.3% 11.8%;
--border-300: 30 3.3% 11.8%;
--border-400: 30 3.3% 11.8%;
--danger-000: 0 61.4% 22.4%;
--danger-100: 0 58.6% 34.1%;
--danger-200: 0 58.6% 34.1%;
--danger-900: 0 50% 95%;
--oncolor-100: 0 0% 100%;
--oncolor-200: 60 6.7% 97.1%;
--oncolor-300: 60 6.7% 97.1%;
--text-000: 60 2.6% 7.6%;
--text-100: 60 2.6% 7.6%;
--text-200: 60 2.5% 23.3%;
--text-300: 60 2.5% 23.3%;
--text-400: 51 3.1% 43.7%;
--text-500: 51 3.1% 43.7%;
}
:root.dark {
--accent-brand: 15 63.1% 59.6%;
--accent-main-000: 15 55.6% 52.4%;
--accent-main-100: 15 63.1% 59.6%;
--accent-main-200: 15 63.1% 59.6%;
--accent-main-900: 0 0% 0%;
--accent-pro-000: 251 84.6% 74.5%;
--accent-pro-100: 251 40.2% 54.1%;
--accent-pro-200: 251 40% 45.1%;
--accent-pro-900: 250 25.3% 19.4%;
--accent-secondary-000: 210 71.1% 62%;
--accent-secondary-100: 210 70.9% 51.6%;
--accent-secondary-200: 210 70.9% 51.6%;
--accent-secondary-900: 210 55.9% 24.6%;
--bg-000: 60 2.1% 18.4%;
--bg-100: 60 2.7% 14.5%;
--bg-200: 30 3.3% 11.8%;
--bg-300: 60 2.6% 7.6%;
--bg-400: 60 3.4% 5.7%;
--bg-500: 60 3.4% 5.7%;
--border-100: 51 16.5% 84.5%;
--border-200: 51 16.5% 84.5%;
--border-300: 51 16.5% 84.5%;
--border-400: 51 16.5% 84.5%;
--danger-000: 0 73.1% 66.5%;
--danger-100: 0 58.6% 34.1%;
--danger-200: 0 58.6% 34.1%;
--danger-900: 0 23% 15.6%;
--oncolor-100: 0 0% 100%;
--oncolor-200: 60 6.7% 97.1%;
--oncolor-300: 60 6.7% 97.1%;
--text-000: 48 33.3% 97.1%;
--text-100: 48 33.3% 97.1%;
--text-200: 50 9% 73.7%;
--text-300: 50 9% 73.7%;
--text-400: 48 4.8% 59.2%;
--text-500: 48 4.8% 59.2%;
}
#home-header {
font-family: "Anthropic Sans", system-ui, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
font-weight: 400 !important;
font-size: 50px;
line-height: 1.2;
margin-bottom: 1rem;
color: --text-000;
display: flex;
align-items: baseline;
justify-content: center;
flex-wrap: nowrap;
}
#localization-select-trigger > :has(img[src*="flags"]) {
display: none;
}
div[id^="localization-select-item"] > :has(img[src*="flags"]) {
display: none;
}
/* Keep home header centered on all screen sizes */
@media (min-width: 768px) {
#home-header {
justify-content: center;
}
}
.build-with {
font-family: "Anthropic Sans", system-ui, "Segoe 
