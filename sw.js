const C="dma-v1";
self.addEventListener("install",e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(["/","/index.html"])));self.skipWaiting()});
self.addEventListener("fetch",e=>{
 if(e.request.url.includes("signals.json"))return;
 e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)))});
