const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async()=>{
 const base='http://127.0.0.1:18080', token='viewer-local-test-token';
 const call=async(method,path,body)=>{const r=await fetch(base+path,{method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});assert(r.ok, String(r.status));return r.status===204?null:r.json()};
 const store=await call('POST','/stores',{name:'Product workspace'});
 const prefix='/stores/'+store.id;
 const model=await call('POST',prefix+'/authorization-models',{schema_version:'1.1',type_definitions:[
  {type:'user'},
  {type:'folder',relations:{viewer:{this:{}}},metadata:{relations:{viewer:{directly_related_user_types:[{type:'user'}]}}}},
  {type:'document',relations:{parent:{this:{}},owner:{this:{}},viewer:{union:{child:[{computedUserset:{relation:'owner'}},{tupleToUserset:{tupleset:{relation:'parent'},computedUserset:{relation:'viewer'}}},{this:{}}]}}},metadata:{relations:{parent:{directly_related_user_types:[{type:'folder'}]},owner:{directly_related_user_types:[{type:'user'}]},viewer:{directly_related_user_types:[{type:'user'}]}}}}
 ]});
 await call('POST',prefix+'/write',{authorization_model_id:model.authorization_model_id,writes:{tuple_keys:Array.from({length:51},(_,i)=>({user:'user:alice',relation:'viewer',object:'document:report-'+String(i).padStart(2,'0')}))}});
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1050}}); const errors=[], mutations=[]; page.on('pageerror',e=>errors.push(e.message)); page.on('request',r=>{if(r.method()!=='GET' && !(r.method()==='POST' && new URL(r.url()).pathname.endsWith('/read'))) mutations.push(r.method()+' '+new URL(r.url()).pathname)});
 await page.goto(base); await page.locator('#api-key').fill('invalid-test-token'); await page.getByRole('button',{name:'Connect',exact:true}).click(); await page.getByText('Access was rejected.',{exact:false}).waitFor();
 await page.locator('#api-key').fill(token); await page.getByRole('button',{name:'Connect',exact:true}).click(); await page.waitForFunction(()=>document.querySelectorAll('#tuples tr').length===50);
 assert.equal(await page.locator('#stores img').count(),0);
 await page.locator('#next').click(); await page.waitForFunction(()=>document.querySelector('#page-summary').textContent.includes('Page 2')); assert.equal(await page.locator('#tuples tr').count(),1);
 await page.locator('#previous').click(); await page.waitForFunction(()=>document.querySelectorAll('#tuples tr').length===50);
 await page.locator('#filter-object').fill('document:report-00'); await page.getByRole('button',{name:'Query tuples'}).click(); await page.waitForFunction(()=>document.querySelectorAll('#tuples tr').length===1);
 assert((await page.locator('#tuples').innerText()).includes('document:report-00'));
 await page.locator('#example-format').selectOption('curl'); assert(!(await page.locator('#request').innerText()).includes(token));
 await page.locator('#example-format').selectOption('grpc'); assert((await page.locator('#request').innerText()).includes('OpenFGAService/Read'));
 await page.locator('#models-tab').click(); await page.waitForFunction(()=>document.querySelector('#model-summary').textContent.includes('3 types'));
 await page.getByRole('button',{name:'Inspect document',exact:true}).click();
 assert((await page.locator('.model-relations').innerText()).includes('(owner or viewer from parent or [user])'));
 await page.getByRole('button',{name:'Inspect user',exact:true}).click();
 assert((await page.locator('.model-relations').innerText()).includes('This type has no relations'));
 await page.locator('#model-type').selectOption('document');
 await page.getByText('Model JSON',{exact:true}).click();
 assert((await page.locator('#model-json').innerText()).includes(model.authorization_model_id));
 await page.getByText('Model JSON',{exact:true}).click();
 await page.screenshot({path:'/private/tmp/kengen-model-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:'/private/tmp/kengen-model-mobile.png',fullPage:true});
 await page.setViewportSize({width:1440,height:1050});
 await page.locator('#tuples-tab').click(); await page.getByRole('button',{name:'Clear',exact:true}).click(); await page.waitForFunction(()=>document.querySelectorAll('#tuples tr').length===50);
 await page.locator('#example-format').selectOption('http'); await page.screenshot({path:'/private/tmp/kengen-viewer-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844}); await page.screenshot({path:'/private/tmp/kengen-viewer-mobile.png',fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.locator('#disconnect').click(); assert.equal(await page.locator('#api-key').inputValue(),''); assert.equal(await page.locator('#response').innerText(),'');
 assert.deepEqual(errors,[]); assert.deepEqual(mutations,[]);
 await browser.close(); await call('DELETE',prefix); console.log('PASS: login rejection, tuple filtering/pagination, models, safe rendering, credential-free examples, disconnect, responsive layout.');
})().catch(e=>{console.error(e);process.exit(1)});
