const $=id=>document.getElementById(id);
const fmt=n=>Number.isFinite(n)?n.toLocaleString('en-US',{maximumFractionDigits:6}):'—';
let deferredInstall=null;
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();deferredInstall=e;$('install').hidden=false});
$('install').addEventListener('click',async()=>{if(!deferredInstall)return;deferredInstall.prompt();await deferredInstall.userChoice;deferredInstall=null;$('install').hidden=true});
function mid(c,end,period){const w=c.slice(end-period+1,end+1);return (Math.max(...w.map(x=>x.h))+Math.min(...w.map(x=>x.l)))/2}
function rsi(c,p=14){let g=0,l=0;for(let i=c.length-p;i<c.length;i++){let d=c[i].c-c[i-1].c;if(d>=0)g+=d;else l-=d}if(l===0)return 100;return 100-100/(1+(g/p)/(l/p))}
function atr(c,p=14){let a=[];for(let i=Math.max(1,c.length-p);i<c.length;i++)a.push(Math.max(c[i].h-c[i].l,Math.abs(c[i].h-c[i-1].c),Math.abs(c[i].l-c[i-1].c)));return a.reduce((x,y)=>x+y,0)/a.length}
async function loadCandles(symbol,res){const to=Math.floor(Date.now()/1000);const url=`https://apiv2.nobitex.ir/market/udf/history?symbol=${encodeURIComponent(symbol)}&resolution=${res}&to=${to}&countback=200`;const r=await fetch(url);if(!r.ok)throw Error('خطای دریافت داده: HTTP '+r.status);const j=await r.json();if(j.s!=='ok')throw Error(j.errmsg||'API داده معتبر برنگرداند');let c=j.t.map((t,i)=>({t:Number(t),o:+j.o[i],h:+j.h[i],l:+j.l[i],c:+j.c[i],v:+j.v[i]})).filter(x=>[x.t,x.o,x.h,x.l,x.c,x.v].every(Number.isFinite));if(c.length<60)throw Error('کندل کافی دریافت نشد: '+c.length);return c}
function analyze(c,capital,riskPct){
 // Exclude the current, potentially unclosed candle to avoid premature signals.
 c=c.slice(0,-1);if(c.length<60)throw Error('پس از کنار گذاشتن کندل جاری، داده کافی نیست');
 const i=c.length-1,price=c[i].c,ten=mid(c,i,9),kij=mid(c,i,26),spanA=(ten+kij)/2,spanB=mid(c,i,52),top=Math.max(spanA,spanB),bottom=Math.min(spanA,spanB);
 const rv=rsi(c),volAvg=c.slice(-21,-1).reduce((s,x)=>s+x.v,0)/20,volRatio=volAvg?c[i].v/volAvg:0;
 const buy=price>top&&ten>kij&&rv>=52&&rv<=70&&volRatio>1.15;
 const sell=price<bottom&&ten<kij&&rv>=30&&rv<=48&&volRatio>1.15;
 const reasons=[`قیمت نسبت به ابر محاسباتی: ${price>top?'بالای ابر':price<bottom?'زیر ابر':'داخل ابر'}`,`تنکان ${ten>kij?'بالاتر از':'پایین‌تر یا برابر با'} کیجون است`,`RSI(14): ${rv.toFixed(1)}`,`حجم آخرین کندل بسته‌شده ${volRatio.toFixed(2)} برابر میانگین ۲۰ کندل است`];
 const out={price,rsi:rv,volRatio,time:c[i].t,reasons,signal:buy?'خرید احتمالی — نیازمند تأیید':sell?'فروش احتمالی — نیازمند تأیید':'انتظار / بدون سیگنال'};
 if(!buy&&!sell)return out;
 const isLong=buy,a=atr(c),recent=c.slice(-12),struct=isLong?Math.min(...recent.map(x=>x.l)):Math.max(...recent.map(x=>x.h));
 const stop=isLong?Math.min(struct,price-1.5*a):Math.max(struct,price+1.5*a),dist=Math.abs(price-stop);
 if(!Number.isFinite(dist)||dist<=0)return {...out,signal:'انتظار / حد ضرر نامعتبر'};
 const riskFraction=dist/price,riskBudget=capital*Math.max(.1,Math.min(2,riskPct))/100;
 out.entry=price;out.stop=stop;out.t1=price+(isLong?1:-1)*1.5*dist;out.t2=price+(isLong?1:-1)*2*dist;
 out.position=Math.min(capital*2,riskBudget/riskFraction);out.riskPct=riskFraction*100;
 return out
}
$('analyze').addEventListener('click',async()=>{
 $('analyze').disabled=true;$('status').className='status';$('status').textContent='در حال دریافت کندل‌های بازار…';$('err').textContent='';
 try{
 const sym=$('symbol').value,res=$('tf').value,capital=Math.max(0,+$('capital').value||0),risk=Math.max(.1,Math.min(2,+$('risk').value||1));
 const raw=await loadCandles(sym,res),p=analyze(raw,capital,risk);
 $('price').textContent=fmt(p.price);$('rsi').textContent=p.rsi.toFixed(1);$('vol').textContent=p.volRatio.toFixed(2)+'×';$('time').textContent=new Date(p.time*1000).toLocaleString('fa-IR');
 $('status').textContent=p.signal;$('status').className='status '+(p.signal.startsWith('خرید')?'buy':p.signal.startsWith('فروش')?'sell':'');
 for(const [id,k] of [['entry','entry'],['stop','stop'],['t1','t1'],['t2','t2']])$(id).textContent=fmt(p[k]);
 $('position').textContent=p.position?`ارزش اسمی تخمینی موقعیت با سقف ۲×: ${fmt(p.position)} تومان · فاصله ریسک قیمت: ${p.riskPct.toFixed(2)}٪. تبدیل دقیق تومان/تتر و هزینه‌های معامله لحاظ نشده است.`:'اندازه موقعیت محاسبه نشد؛ ورود تأیید نشده است.';
 $('reasons').innerHTML=p.reasons.map(x=>'<li>'+x.replace(/[&<>"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]))+'</li>').join('');
 }catch(e){$('status').textContent='تحلیل ناموفق — بدون سیگنال';$('err').textContent=(e.message||'خطای ناشناخته')+'؛ اتصال اینترنت و دسترسی API را بررسی کن.';for(const id of ['price','rsi','vol','time','entry','stop','t1','t2'])$(id).textContent='—';$('position').textContent='تا زمان دریافت داده معتبر، وارد معامله نشو.';$('reasons').innerHTML=''}
 finally{$('analyze').disabled=false}
});
if('serviceWorker' in navigator)window.addEventListener('load',()=>navigator.serviceWorker.register('./sw.js').catch(()=>{}));
