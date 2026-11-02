import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path';
const root=path.resolve(process.env.WEB_ROOT||'dist'),port=Number(process.env.PORT||4173);
const mime={'.html':'text/html','.js':'application/javascript','.css':'text/css','.json':'application/json','.webp':'image/webp','.png':'image/png','.sog':'application/octet-stream','.mp4':'video/mp4','.wasm':'application/wasm'};
http.createServer((req,res)=>{let p;try{p=decodeURIComponent(new URL(req.url,'http://localhost').pathname);}catch{res.writeHead(400).end();return;}
if(p.endsWith('/'))p+='index.html';const f=path.resolve(root,'.'+p);if(!f.startsWith(root+path.sep)){res.writeHead(403).end();return;}
fs.stat(f,(err,st)=>{if(err||!st.isFile()){res.writeHead(404).end('Not found');return;}res.writeHead(200,{'Content-Type':mime[path.extname(f)]||'application/octet-stream','Content-Length':st.size,'Cache-Control':'no-cache'});fs.createReadStream(f).pipe(res);});}).listen(port,'0.0.0.0',()=>console.log('Afterlight local server on '+port));
