# Model Context Protocol Overview

**Source:** https://docs.anthropic.com/en/docs/mcp
**Fetched:** 2026-04-08T19:55:37Z

---

What is the Model Context Protocol (MCP)? - Model Context Protocol                              (function(a,b){try{let c=document.getElementById("banner")?.innerText;if(c){for(let d=0;d          ((a,b,c,d,e,f,g,h)=>{let i=document.documentElement,j=["light","dark"];function k(b){var c;(Array.isArray(a)?a:[a]).forEach(a=>{let c="class"===a,d=c&&f?e.map(a=>f[a]||a):e;c?(i.classList.remove(...d),i.classList.add(f&&f[b]?f[b]:b)):i.setAttribute(a,b)}),c=b,h&&j.includes(c)&&(i.style.colorScheme=c)}if(d)k(d);else try{let a=localStorage.getItem(b)||c,d=g&&"system"===a?window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light":a;k(d)}catch(a){}})("class","isDarkMode","system",null,["dark","light","true","false","system"],{"true":"dark","false":"light","dark":"dark","light":"light"},true,true)  :root{--banner-height:0px!important}  (self.__next_s=self.__next_s||[]).push([0,{"children":"(function j(a,b,c,d,e){try{let f,g,h=[];try{h=window.location.pathname.split(\"/\").filter(a=>\"\"!==a&&\"global\"!==a).slice(0,2)}catch{h=[]}let i=h.find(a=>c.includes(a)),j=[];for(let c of(i?j.push(i):j.push(b),j.push(\"global\"),j)){if(!c)continue;let b=a[c];if(b?.content){f=b.content,g=c;break}}if(!f)return void document.documentElement.setAttribute(d,\"hidden\");let k=!0,l=0;for(;l  :root {
--primary: 9 9 11;
--primary-light: 250 250 250;
--primary-dark: 9 9 11;
--tooltip-foreground: 255 255 255;
--background-light: 255 255 255;
--background-dark: 14 14 16;
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
}   (self.__next_s=self.__next_s||[]).push([0,{"suppressHydrationWarning":true,"children":"(function(a,b,c,d){var e;let f,g=\"mint\"===d||\"linden\"===d?\"sidebar\":\"sidebar-content\",h=(e=d,f=\"navbar-transition\",\"maple\"===e&&(f+=\"-maple\"),f),[i,j]=(()=>{switch(d){case\"almond\":return[\"[--scroll-mt:2.5rem]\",\"[--scroll-mt:2.5rem]\"];case\"luma\":return[\"lg:[--scroll-mt:6rem]\",\"lg:[--scroll-mt:6rem]\"];case\"sequoia\":return[\"lg:[--scroll-mt:8.5rem]\",\"lg:[--scroll-mt:11rem]\"];default:return[\"lg:[--scroll-mt:9.5rem]\",\"lg:[--scroll-mt:12rem]\"]}})();function k(){document.documentElement.classList.add(i)}function l(a){document.getElementById(g)?.style.setProperty(\"top\",`${a}rem`)}function m(a){document.getElementById(g)?.style.setProperty(\"height\",`calc(100vh - ${a}rem)`)}function n(a,b){!a&&b||a&&!b?(k(),document.documentElement.classList.remove(j)):a&&b&&(document.documentElement.classList.add(j),document.documentElement.classList.remove(i))}let o=document.documentElement.getAttribute(\"data-banner-state\"),p=null!=o?\"visible\"===o:b;switch(d){case\"mint\":l(c),n(a,p);break;case\"palm\":case\"aspen\":case\"sequoia\":l(c),m(c),n(a,p);break;case\"luma\":k();break;case\"linden\":l(c),p&&k();break;case\"almond\":k(),l(c),m(c)}let q=function(){let a=document.createElement(\"style\");return a.appendChild(document.createTextNode(\"*,*::before,*::after{-webkit-transition:none!important;-moz-transition:none!important;-o-transition:none!important;-ms-transition:none!important;transition:none!important}\")),document.head.appendChild(a),function(){window.getComputedStyle(document.body),setTimeout(()=>{document.head.removeChild(a)},1)}}();(\"requestAnimationFrame\"in globalThis?requestAnimationFrame:setTimeout)(()=>{let a;a=!1,a=window.scrollY>50,document.getElementById(h)?.setAttribute(\"data-is-opaque\",`${!!a}`),q()})})(\n  true,\n  false,\n  (function m(a,b,c){let d=document.documentElement.getAttribute(\"data-banner-state\"),e=2.5*!!(null!=d?\"visible\"===d:b),f=3*!!a,g=4,h=e+g+f;switch(c){case\"mint\":case\"palm\":break;case\"aspen\":f=2.5*!!a,g=3.5,h=e+f+g;break;case\"luma\":g=3,h=e+g;break;case\"linden\":g=4,h=e+g;break;case\"almond\":g=3.5,h=e+g;break;case\"sequoia\":f=3*!!a,g=3,h=e+g+f}return h})(true, false, \"mint\"),\n  \"mint\",\n)","id":"_mintlify-scroll-top-script"}])  Skip to main content  (function j(a,b,c,d){try{if(window.matchMedia("(max-width: 1024px)").matches||!d){document.documentElement.style.setProperty(c,"0px"),document.documentElement.setAttribute("data-assistant-state","closed"),d||localStorage.setItem(a,"false");return}let e=localStorage.getItem(a);if(null===e){document.documentElement.style.setProperty(c,"0px"),document.documentElement.setAttribute("data-assistant-state","closed");return}let f=JSON.parse(e),g=localStorage.getItem(b),h=null!==g?JSON.parse(g):368;document.documentElement.style.setProperty(c,f?h+"px":"0px"),document.documentElement.setAttribute("data-assistant-state",f?"open":"closed")}catch(a){document.documentElement.style.setProperty(c,"0px"),document.documentElement.setAttribute("data-assistant-state","closed")}})(
"chat-assistant-sheet-open",
"chat-assistant-sheet-width",
"--assistant-sheet-width",
false
)  html{--assistant-sheet-width:0px!important}              Model Context Protocol  home page                 Search...   ⌘ K        Blog    GitHub                                            Search...              Navigation         Get started       What is the Model Context Protocol (MCP)?       Documentation    Extensions    Specification    Registry    SEPs    Community                    Get started        What is MCP?          About MCP        Architecture          Servers          Clients          Versioning          Develop with MCP        Connect to local MCP servers          Connect to remote MCP Servers          Build with Agent Skills          Build an MCP server          Build an MCP client          SDKs        Security            Developer tools        MCP Inspector          Debugging          Examples        Example Clients          Example Servers             document.documentElement.setAttribute('data-page-mode', "none");  (self.__next_s=self.__next_s||[]).push([0,{"suppressHydrationWarning":true,"children":"(function n(a,b){if(!document.getElementById(\"footer\")?.classList.contains(\"advanced-footer\")||\"maple\"===b||\"willow\"===b||\"almond\"===b||\"luma\"===b||\"sequoia\"===b)return;let c=document.documentElement.getAttribute(\"data-page-mode\"),d=document.getElementById(\"navbar\"),e=document.getElementById(\"navigation-items\"),f=document.getElementById(\"sidebar\"),g=document.getElementById(\"footer\"),h=document.getElementById(\"table-of-contents-content\"),i=16*a;if(!g||\"center\"===c)return;let j=g.getBoundingClientRect().top,k=window.innerHeight-j,l=(e?.clientHeight??0)+i+32*(\"mint\"===b||\"linden\"===b);if(f&&e)if(k>0){let a=Math.max(0,l-j);f.style.bottom=`${k}px`,f.style.top=`${i-a}px`}else f.style.bottom=\"\",f.style.top=`${a}rem`,f.style.height=\"auto\";h&&d&&(k>0?h.style.top=\"custom\"===c?`${d.clientHeight-k}px`:`${40+d.clientHeight-k}px`:h.style.top=\"\")})(\n  (function m(a,b,c){let d=document.documentElement.getAttribute(\"data-banner-state\"),e=2.5*!!(null!=d?\"visible\"===d:b),f=3*!!a,g=4,h=e+g+f;switch(c){case\"mint\":case\"palm\":break;case\"aspen\":f=2.5*!!a,g=3.5,h=e+f+g;break;case\"luma\":g=3,h=e+g;break;case\"linden\":g=4,h=e+g;break;case\"almond\":g=3.5,h=e+g;break;case\"sequoia\":f=3*!!a,g=3,h=e+g+f}return h})(true, false, \"mint\"),\n  \"mint\",\n)","id":"_mintlify-footer-and-sidebar-scroll-script"}])    #content-area {
--font-mono: var(--font-jetbrains-mono), ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; /* via Mintlify theme */
h5 {
font-weight: 500;
}
h6 {
font-weight: 400;
}
/* Fix code block line highlight color */
code .line-highlight {
--primary-light: 100 175 250;
}
}
/*** Add automatic section numbers to headings and table of contents items ***/
#enable-section-numbers {
display: none;
}
body:has(#enable-section-numbers) {
#content-area,
#table-of-contents {
counter-reset: h2-counter h3-counter h4-counter h5-counter h6-counter;
}
#content-area h2[id],
#table-of-contents li[data-depth="0"] {
counter-increment: h2-counter;
counter-set: h3-counter h4-counter h5-counter h6-counter;
}
#content-area h3[id],
#table-of-contents li[data-depth="1"] {
counter-increment: h3-counter;
counter-set: h4-counter h5-counter h6-counter;
}
#content-area h4[id],
#table-of-contents li[data-depth="2"] {
counter-increment: h4-counter;
counter-set: h5-counter h6-counter;
}
#content-area h5[id],
#content-area h5,
#table-of-contents li[data-depth="3"] {
counter-increment: h5-counter;
counter-set: h6-counter;
}
#content-area h6[id],
#content-area h6,
#table-of-contents li[data-depth="4"] {
counter-increment: h6-counter;
}
#table-of-contents li a::before {
flex-shrink: 0;
}
#content-area h2[id]::before,
#table-of-contents li[data-depth="0"] a::before {
content: counter(h2-counter) ". ";
}
#content-area h3[id]::before,
#table-of-contents li[data-depth="1"] a::before {
content: counter(h2-counter) "." counter(h3-counter) " ";
}
#content-area h4[id]::before,
#table-of-contents li[data-depth="2"] a::before {
content: counter(h2-counter) "." counter(h3-counter) "." counter(h4-counter)
" ";
}
#content-area h5[id]::before,
#content-area h5::before,
#table-of-contents li[data-depth="3"] a::before {
content: counter(h2-counter) "." counter(h3-counter) "." counter(h4-counter)
"." counter(h5-counter) " ";
}
#content-area h6[id]::before,
#content-area h6::before,
#table-of-contents li[data-depth="4"] a::before {
content: counter(h2-counter) "." counter(h3-counter) "." counter(h4-counter)
"." counter(h5-counter) "." counter(h6-counter) " ";
}
}
/*** Page: schema reference ***/
#schema-reference {
display: none;
}
/* Vertical margins */
body:has(#schema-reference) {
* {
scroll-margin-top: 8rem;
}
--mt-sm: 0.25rem;
--mt-md: 0.5rem;
--mt-lg: 1rem;
--mt-xl: 1.5rem;
/* Headings */
h2, h3 {
margin: 0;
}
.type + h2, .type h3 {
margin-top: calc(5 * var(--mt-lg));
}
h2 + .type h3 {
margin-top: var(--mt-xl);
}
/* Type definition code */
.tsd-signature {
margin: var(--mt-lg) 0 0 0;
}
/* Prose */
.tsd-comment {
margin: var(--mt-lg) 0 0 0;
p, ul, ol, li {
margin: 0;
}
* + :is(p, ul, ol, pre) {
margin-top: var(--mt-lg);
}
* + li {
margin-top: var(--mt-sm);
}
}
/* Example block (`@example` tag) */
.tsd-tag-example {
margin: var(--mt-lg) 0 0 0;
summary + * {
margin: var(--mt-sm) 0 0 0;
scroll-margin-top: calc(8rem + 1.5rem + var(--mt-sm));
}
}
/* "See" links (`@see` tag) */
.tsd-tag-see {
& > :is(p, ul) {
margin-top: 0;
}
}
/* Type member */
.tsd-member {
margin: var(--mt-lg) 0 0 0;
/* Description */
.tsd-comment {
margin-top: var(--mt-sm);
}
/* Sub-members */
.tsd-type-declaration {
/* List */
[data-typedoc-h="4"] + .tsd-parameters {
margin: var(--mt-md) 0 0 0;
}
}
/* Example (`@example` tag) inside type member */
.tsd-tag-example {
margin: var(--mt-sm) 0 0 0;
}
}
}
body:has(#schema-reference) {
/* Prose */
.tsd-comment {
a.tsd-kind-type-alias,
a.tsd-kind-interface,
a.tsd-kind-property {
font-family: var(--font-mono);
font-size: 0.875em;
}
}
/* Code blocks */
.tsd-signature,
.tsd-tag-example pre:has(code) {
/* Based on code blocks rendered by Mintlify. */
border: 1px solid;
border-color: light-dark(rgb(var(--gray-950)/.1), rgba(255 255 255/0.1));
border-radius: 1rem;
padding: 1rem 0.875rem;
background-color: inherit;
color: inherit;
font-family: var(--font-mono);
font-size: 0.875rem;
line-height: 1.5rem;
}
/* Type definition code */
.tsd-signature {
a {
font-weight: normal;
border-bottom: none;
text-decoration: underline;
&:hover {
text-decoration-thickness: 2px;
}
}
a[href="#"] {
pointer-events: none;
color: inherit;
text-decoration: none;
}
.tsd-signature-keyword {
color: light-dark(rgb(207, 34, 46), #9CDCFE);
}
:is(.tsd-kind-interface, .tsd-kind-type-alias):not(.tsd-signature-type) {
color: light-dark(rgb(149, 56, 0), #4EC9B0);
}
.tsd-signature-type:not(.tsd-kind-interface, .tsd-kind-type-alias) {
color: light-dark(rgb(5, 80, 174), #DCDCAA);
}
}
/* Example block (`@example` tag) */
.tsd-tag-example {
/* Label */
summary {
font-weight: 600;
font-style: italic;
}
/* Code */
pre code.json {
.hl-1 {
color: light-dark(rgb(17, 99, 41), #9CDCFE);
}
.hl-2, .hl-3 {
color: light-dark(rgb(10, 48, 105), #CE9178);
}
.hl-5 {
color: light-dark(rgb(5, 80, 174), #569CD6);
}
}
/* Copy button */
pre button {
display: none;
}
}
/* "See" links (`@see` tag) */
.tsd-tag-see {
/* Add trailing ":" to heading */
[data-typedoc-h="4"]::after {
content: ": ";
}
/* Hide (defunct) anchor link */
.tsd-anchor-icon {
display: none;
}
/* Case: single link -- display inline with heading */
&:has(> p) {
[data-typedoc-h="4"], p {
display: inline;
}
}
}
/* Type member */
.tsd-member {
/* Hide members that don't have doc comments */
&:not(:has(.tsd-comment)) {
display: none;
}
/* When the type itself has a doc comment, add a subtle top border to the first visible member */
.tsd-comment ~ &:has(.tsd-comment):not(.tsd-member:has(.tsd-comment) ~ *) {
border-top: 2px solid light-dark(rgb(var(--gray-950)/.05), rgba(255 255 255/0.1));
padding-top: var(--mt-md);
}
/* Member name */
[data-typedoc-h="3"] {
font-family: var(--font-mono);
font-weight: 700;
}
& > .tsd-comment,
& > .tsd-type-declaration {
margin-left: 1.25rem;
}
/* Sub-members */
.tsd-type-declaration {
/* Templated heading ("Type Declaration") */
[data-typedoc-h="4"] {
display: none;
}
/* Name and type */
[data-typedoc-h="5"] {
font-family: var(--font-mono);
font-size: 0.875rem;
font-weight: 500;
width: fit-content;
padding: 0.125em 0.5em;
background-color: light-dark(rgb(var(--gray-100)/.5), rgb(255 255 255/.05));
.tsd-tag {
display: none;
}
}
}
/* Example (`@example` tag) inside type member */
.tsd-tag-example {
padding-left: 0.5rem;
}
.tsd-sources {
display: none;
}
}
/* Anchor links for members and examples */
.tsd-anchor-icon {
border: 0;
padding: 0 0.5rem;
color: rgb(var(--gray-500)/.5);
&:hover {
color: rgb(var(--gray-500))
}
&::before {
content: "#";
color: inherit;
}
svg {
display: none;
}
}
/* Types with only index properties (e.g., `type Foo = { [key: string]: unknown }`) */
.type > .tsd-type-declaration {
/* Hide property if no doc comments */
&:not(:has(.tsd-comment)) {
display: none;
}
/* Templated heading ("Type Declaration") */
[data-typedoc-h="4"] {
display: none;
}
/* Index property */
[data-typedoc-h="5"] {
font-family: var(--font-mono);
font-weight: 700;
}
}
}
/*** LF Projects copyright footer ***/
#lf-copyright {
margin-top: 2rem;
padding-top: 1.5rem;
border-top: 1px solid light-dark(rgb(var(--gray-950)/.1), rgba(255 255 255/0.1));
text-align: center;
font-size: 0.875rem;
color: rgb(var(--gray-500));
line-height: 1.5;
a {
color: inherit;
text-decoration: underline;
&:hover {
color: rgb(var(--gray-700));
}
}
}
On this page      What can MCP enable?    Why does MCP matter?    Broad ecosystem support    Start Building    Learn more           Get started   What is the Model Context Protocol (MCP)?           Copy page                      Copy page             MCP (Model Context Protocol) is an open-source standard for connecting AI applications to external systems.
Using MCP, AI applications like Claude or ChatGPT can connect to data sources (e.g. local files, databases), tools (e.g. search engines, calculators) and workflows (e.g. specialized prompts)—enabling them to access key information and perform tasks.
Think of MCP like a USB-C port for AI applications. Just as USB-C provides a standardized way to connect electronic devices, MCP provides a standardized way to connect AI applications to external systems.
​         What can MCP enable?
Agents can access your Google Calendar and Notion, acting as a more personalized AI assistant.
Claude Code can generate an entire web app using a Figma design.
Enterprise chatbots can connect to multiple databases across an organization, empowering users to analyze data using chat.
AI models can create 3D designs on Blender and print them out using a 3D printer.
​         Why does MCP matter?
Depending on where you sit in the ecosystem, MCP can have a range of benefits.
Developers : MCP reduces development time and complexity when building, or integrating with, an AI application or agent.
AI applications or agents : MCP provides access to an ecosystem of data sources, tools and apps which will enhance capabilities and improve the end-user experience.
End-users : MCP results in more capable AI applications or agents which can access your data and take actions on your behalf when necessary.
​         Broad ecosystem support
MCP is an open protocol supported across a wide range of clients and servers. AI assistants like  Claude  and  ChatGPT , development tools like  Visual Studio Code ,  Cursor ,  MCPJam , and  many others  all support MCP — making it easy to build once and integrate everywhere.
​         Start Building
Build servers   Create MCP servers to expose your data and tools                     Build clients   Develop applications that connect to MCP servers                     Build MCP Apps   Build interactive apps that run inside AI clients
​         Learn more
Understand concepts   Learn the core concepts and architecture of MCP          Was this page helpful?         Yes        No           Architecture               ⌘ I                  github                  (self.__next_f=self.__next_f||[]).push([0])  self.__next_f.push([1,"1:\"$Sreact.fragment\"\n2:I[85341,[],\"\"]\n"])  self.__next_f.push([1,"3:I[2510,[\"73473\",\"static/chunks/891cff7f-dcf0b8e94fd9e2cd.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"51288\",\"static/chunks/51288-0fb44d6be82e9af5.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"14079\",\"static/chunks/14079-70bacdc9c734d291.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"53105\",\"static/chunks/53105-c5098dd7faa69cf4.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"95115\",\"static/chunks/95115-7f3830b22524c9f1.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"90880\",\"static/chunks/90880-8c4cda81ffff4a1f.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"81974\",\"static/chunks/81974-469a0fabac51ec40.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"98816\",\"static/chunks/98816-4875194b6205382d.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"80239\",\"static/chunks/80239-ce217fc534a5bb94.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"19664\",\"static/chunks/19664-8ce43df6b74bea12.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"8685\",\"static/chunks/8685-3edaeb533c1369b7.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"55016\",\"static/chunks/55016-5a57640d3254bfaf.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"75862\",\"static/chunks/75862-ad04ffab7fa65a12.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"71251\",\"static/chunks/71251-e2aa75d985fc5a83.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"18039\",\"static/chunks/app/error-cad9a32b7caec24e.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\"],\"default\",1]\n"])  self.__next_f.push([1,"4:I[90025,[],\"\"]\n"])  self.__next_f.push([1,"5:I[51749,[\"73473\",\"static/chunks/891cff7f-dcf0b8e94fd9e2cd.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"53016\",\"static/chunks/cfdfcc00-442051842d4b5e4f.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"41725\",\"static/chunks/d30757c7-4ce3b53815c6f230.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"51288\",\"static/chunks/51288-0fb44d6be82e9af5.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"14079\",\"static/chunks/14079-70bacdc9c734d291.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"53105\",\"static/chunks/53105-c5098dd7faa69cf4.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"95115\",\"static/chunks/95115-7f3830b22524c9f1.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"90880\",\"static/chunks/90880-8c4cda81ffff4a1f.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"81974\",\"static/chunks/81974-469a0fabac51ec40.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"98816\",\"static/chunks/98816-4875194b6205382d.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"80239\",\"static/chunks/80239-ce217fc534a5bb94.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"19664\",\"static/chunks/19664-8ce43df6b74bea12.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3pQ\",\"50867\",\"static/chunks/50867-80e9047ba5d299cd.js?dpl=dpl_71KqJutK11CWJe3qPwM83SFxN3p
