// Graba la demo de TodoBarato AI en AWS (video con subtítulos): app por HTTPS, chat, agente, balanceo entre zonas y failover.
// Uso (desde un directorio con playwright-core instalado):
//   URL=https://d1d1jx3qpvm3xv.cloudfront.net TB_EMAIL=... TB_CLAVE=... node grabar_demo.mjs
// Necesita la AWS CLI con credenciales del lab (para terminar una réplica en el failover).
import { chromium } from 'playwright-core';
import { execSync } from 'node:child_process';
import { readdirSync, renameSync, mkdirSync } from 'node:fs';

const URL = process.env.URL;
const AWS = `${process.env.HOME}/.local/bin/aws`;
const exe = `${process.env.HOME}/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome`;
mkdirSync('video', { recursive: true });
const b = await chromium.launch({ executablePath: exe, headless: true });
const ctx = await b.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: 'video', size: { width: 1280, height: 720 } } });
const p = await ctx.newPage();
const espera = (ms) => p.waitForTimeout(ms);

// Subtítulo fijo abajo; se vuelve a poner después de cada navegación.
async function subtitulo(texto, sub = '') {
  await p.evaluate(([t, s]) => {
    let d = document.getElementById('__sub');
    if (!d) {
      d = document.createElement('div'); d.id = '__sub';
      d.style.cssText = 'position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:2147483647;max-width:1100px;' +
        'background:rgba(15,23,42,.92);color:#fff;font:600 19px/1.35 system-ui,sans-serif;padding:12px 22px;border-radius:12px;' +
        'box-shadow:0 8px 30px rgba(0,0,0,.35);text-align:center';
      document.body.appendChild(d);
    }
    d.innerHTML = t + (s ? `<div style="font-weight:400;font-size:15px;opacity:.85;margin-top:3px">${s}</div>` : '');
  }, [texto, sub]);
}
async function ir(ruta, texto, sub) {
  // El panel consulta /health sin parar: nunca llega a «networkidle».
  await p.goto(URL + ruta, { waitUntil: ruta === '/__panel' ? 'load' : 'networkidle', timeout: 60000 });
  await subtitulo(texto, sub);
}

// ---------- Panel de /health servido en el mismo dominio (intercepta la ruta en el navegador)
const PANEL = `<!doctype html><html lang="es"><meta charset="utf-8"><title>Panel de réplicas</title>
<body style="margin:0;font-family:system-ui,sans-serif;background:#0b1220;color:#e5e7eb">
<div style="padding:28px 40px">
  <div style="font-size:15px;opacity:.7">TodoBarato AI · AWS us-east-1 · consulta a /health cada 0,5 s a través de CloudFront → ALB</div>
  <h1 style="margin:6px 0 18px;font-size:30px">Réplicas que responden</h1>
  <div style="display:flex;gap:18px;margin-bottom:18px">
    <div style="flex:1;background:#111a2e;border-radius:14px;padding:16px"><div style="opacity:.7">Solicitudes OK</div><div id="ok" style="font-size:44px;font-weight:700;color:#4ade80">0</div></div>
    <div style="flex:1;background:#111a2e;border-radius:14px;padding:16px"><div style="opacity:.7">Fallidas</div><div id="ko" style="font-size:44px;font-weight:700;color:#f87171">0</div></div>
    <div style="flex:1;background:#111a2e;border-radius:14px;padding:16px"><div style="opacity:.7">Disponibilidad</div><div id="disp" style="font-size:44px;font-weight:700">—</div></div>
    <div style="flex:1;background:#111a2e;border-radius:14px;padding:16px"><div style="opacity:.7">Ventana con errores</div><div id="vent" style="font-size:44px;font-weight:700;color:#fbbf24">0 s</div></div>
  </div>
  <div id="tarjetas" style="display:flex;gap:18px;margin-bottom:18px"></div>
  <div id="log" style="font:14px/1.5 ui-monospace,monospace;background:#060b16;border-radius:12px;padding:12px 16px;height:170px;overflow:hidden"></div>
</div>
<script>
let ok=0, ko=0, primerError=0, ultimoError=0; const vistas={}; const colores={'us-east-1a':'#60a5fa','us-east-1b':'#c084fc'};
function pintar(){ document.getElementById('ok').textContent=ok; document.getElementById('ko').textContent=ko;
  document.getElementById('disp').textContent=(ok+ko)?(100*ok/(ok+ko)).toFixed(1)+' %':'—';
  document.getElementById('vent').textContent=primerError?Math.round((ultimoError-primerError)/1000)+' s':'0 s';
  document.getElementById('tarjetas').innerHTML=Object.entries(vistas).map(([id,v])=>{const vivo=Date.now()-v.ult<2500;
    return '<div style="flex:1;border-radius:14px;padding:16px;background:'+(vivo?'#13233f':'#2a1515')+';border:2px solid '+(vivo?(colores[v.zona]||'#94a3b8'):'#f87171')+'">'+
    '<div style="font-size:14px;opacity:.7">'+v.zona+'</div><div style="font-size:20px;font-weight:700">'+id+'</div>'+
    '<div style="margin-top:4px">'+v.n+' respuestas · '+(vivo?'<span style="color:#4ade80">respondiendo</span>':'<span style="color:#f87171">sin respuesta</span>')+'</div></div>';}).join(''); }
function log(t,c){ const l=document.getElementById('log'); const d=document.createElement('div'); d.style.color=c; d.textContent=new Date().toLocaleTimeString('es-CL')+'  '+t; l.prepend(d); while(l.children.length>9) l.lastChild.remove(); }
async function sondear(){ try{ const r=await fetch('/health?t='+Date.now(),{cache:'no-store'});
    if(!r.ok) throw new Error('HTTP '+r.status); const j=await r.json(); ok++;
    const v=vistas[j.instancia]||(vistas[j.instancia]={n:0,zona:j.zona}); v.n++; v.ult=Date.now(); log('200  '+j.instancia+'  '+j.zona, colores[j.zona]);
  }catch(e){ ko++; ultimoError=Date.now(); if(!primerError) primerError=ultimoError; log('FALLA  '+e.message,'#f87171'); } pintar(); }
setInterval(sondear,500); setInterval(pintar,500);
</script></body></html>`;
await p.route(`${URL}/__panel`, (r) => r.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: PANEL }));

try {
  // 1. Portada
  await ir('/', 'TodoBarato AI desplegado en AWS', 'HTTPS con CloudFront → ALB → réplicas en 2 zonas · catálogo leído desde RDS PostgreSQL');
  await espera(4500);
  await p.mouse.wheel(0, 500); await espera(2500);

  // 2. Login
  await ir('/login', 'Inicio de sesión (JWT validado con JWKS en cada solicitud)');
  await p.locator('input[type=email]').pressSequentially(process.env.TB_EMAIL, { delay: 25 });
  await p.locator('input[type=password]').fill(process.env.TB_CLAVE);
  await espera(800);
  await p.locator('input[type=password]').press('Enter');
  await p.waitForURL((u) => !u.toString().includes('/login'), { timeout: 30000 });

  // 3. Chat
  await ir('/chat', 'Asistente de IA: RAG + herramientas sobre el catálogo', 'Máximo 3 herramientas y 1.600 tokens de contexto por consulta · Gemini por API');
  await espera(1500);
  const cajaChat = p.locator('textarea, input[type=text]').last();
  await cajaChat.pressSequentially('Busco una placa madre ASUS barata, ¿cuál me recomiendas?', { delay: 18 });
  await cajaChat.press('Enter');
  await p.waitForResponse((r) => r.url().includes('/api/v1/ai/chat'), { timeout: 90000 });
  await subtitulo('Respuesta con productos y precios reales del catálogo', 'La API no guarda estado: cualquier réplica puede atender la siguiente consulta');
  await espera(7000);

  // 4. Agente
  await ir('/agente', 'Agente de ahorro (LangGraph): planifica, usa herramientas y escribe alertas', 'Panel derecho: «Cómo pensó» → plan, herramientas y memoria del usuario');
  await espera(1500);
  const cajaAg = p.locator('textarea, input[type=text]').last();
  await cajaAg.pressSequentially('Busca el celular Samsung más barato y avísame si baja de precio', { delay: 18 });
  await cajaAg.press('Enter');
  await p.waitForResponse((r) => r.url().includes('/api/v1/agent/run'), { timeout: 120000 });
  await espera(2500);
  await subtitulo('El agente buscó, comparó ofertas y dejó una alerta guardada', 'Checkpoints en Postgres: la conversación sigue aunque cambie la réplica');
  await espera(8000);

  // 5. Balanceo entre zonas
  await ir('/__panel', 'Balanceo de carga entre dos zonas de disponibilidad', 'El ALB reparte con «least outstanding requests» entre us-east-1a y us-east-1b');
  await espera(25000);

  // 6. Failover: se termina una réplica sin aviso
  const victima = execSync(`${AWS} autoscaling describe-auto-scaling-groups --auto-scaling-group-names tb-ep2-api --query "AutoScalingGroups[0].Instances[?LifecycleState=='InService']|[0].InstanceId" --output text`).toString().trim();
  const zona = execSync(`${AWS} ec2 describe-instances --instance-ids ${victima} --query "Reservations[0].Instances[0].Placement.AvailabilityZone" --output text`).toString().trim();
  await subtitulo(`Simulamos una caída: terminamos la réplica ${victima} (${zona}) sin aviso`, 'aws ec2 terminate-instances');
  execSync(`${AWS} ec2 terminate-instances --instance-ids ${victima}`);
  await espera(9000);
  await subtitulo('El health check (cada 5 s, 2 fallos) la retira del balanceador', 'Solo fallan las solicitudes de esos segundos («ventana con errores»); después, 0 errores');
  await espera(16000);
  await subtitulo('El servicio sigue respondiendo desde la otra zona', 'El Auto Scaling Group lanza un reemplazo solo (medido: 219 s) y CloudWatch avisa por correo');
  await espera(14000);
  await subtitulo('TodoBarato AI · EP2 ITY1102 · Equipo 1', 'Arquitectura escalable, segura y verificada en AWS');
  await espera(4000);
} catch (e) {
  console.log('ERROR', e.message.split('\n')[0]);
  await p.screenshot({ path: 'demo-error.png' });
}
await ctx.close(); await b.close();
const v = readdirSync('video').filter((f) => f.endsWith('.webm')).sort().pop();
renameSync(`video/${v}`, 'video/demo.webm');
console.log('video/demo.webm');
