import fs from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
if(!existsSync('public/data/259c0051/navigation.json')){
 const install=spawnSync('python3',['-m','pip','install','--disable-pip-version-check','numpy==2.2.6','pillow==11.3.0'],{stdio:'inherit'});if(install.status!==0)throw Error('Navigation dependency installation failed');
 const prep=spawnSync('python3',['tools/prepare.py'],{stdio:'inherit'});if(prep.status!==0)throw Error('Navigation build failed');
}
await fs.rm('dist',{recursive:true,force:true});
await fs.mkdir('dist/vendor',{recursive:true});
for(const file of ['index.html','app.js','style.css','README.md']) await fs.copyFile(file,'dist/'+file);
await fs.cp('public','dist',{recursive:true});
// The companion capture is retained by acquisition, not duplicated in delivery.
await fs.rm('dist/data/0c75de4a',{recursive:true,force:true});
await fs.cp('node_modules/three/build','dist/vendor/three',{recursive:true});
await fs.cp('node_modules/three/examples/jsm','dist/vendor/addons',{recursive:true});
await fs.copyFile('node_modules/@sparkjsdev/spark/dist/spark.module.min.js','dist/vendor/spark.js');
await fs.copyFile('node_modules/three/LICENSE','dist/vendor/THREE-LICENSE.txt');
try {await fs.copyFile('node_modules/@sparkjsdev/spark/LICENSE','dist/vendor/SPARK-LICENSE.txt');}catch{await fs.writeFile('dist/vendor/SPARK-LICENSE.txt','Spark is MIT licensed. Copyright Spark contributors. https://github.com/sparkjsdev/spark/blob/main/LICENSE');}
await fs.mkdir('dist/source/tools',{recursive:true});
for(const file of ['package.json','package-lock.json','index.html','app.js','style.css','README.md'])if(existsSync(file))await fs.copyFile(file,'dist/source/'+file);
await fs.cp('tools','dist/source/tools',{recursive:true});
await fs.writeFile('dist/.nojekyll','');
console.log('Static build completed. Serve dist/ as /forest/. No third-party runtime requests.');
