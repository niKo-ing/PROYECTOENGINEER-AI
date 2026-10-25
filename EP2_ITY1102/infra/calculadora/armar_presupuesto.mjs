// Arma el presupuesto de TodoBarato AI en calculator.aws (us-east-1) y obtiene el enlace público para compartir.
import { chromium } from 'playwright-core';
import { writeFileSync } from 'node:fs';
const exe = `${process.env.HOME}/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome`;
const b = await chromium.launch({ executablePath: exe, headless: true });
const ctx = await b.newContext({ viewport: { width: 1400, height: 1100 }, locale: 'en-US', permissions: ['clipboard-read', 'clipboard-write'] });
const p = await ctx.newPage();
const espera = (ms) => p.waitForTimeout(ms);
const log = (...a) => console.log('·', ...a);
const total = async () => (await p.locator('text=/Total Monthly cost:/').first().locator('xpath=..').innerText().catch(() => '?')).replace(/\s+/g, ' ');
let primero = true;

async function agregarServicio(nombre) {
  if (primero) {
    await p.goto('https://calculator.aws/#/addService', { waitUntil: 'networkidle', timeout: 60000 });
    primero = false;
  } else {
    await p.getByRole('button', { name: 'Add service', exact: true }).first().click();
  }
  await espera(1500);
  const reg = p.getByRole('button', { name: /US East \(Ohio\)/ });
  if (await reg.count()) { await reg.first().click(); await espera(500); await p.getByText('US East (N. Virginia)', { exact: true }).first().click(); await espera(500); }
  await p.getByRole('searchbox').first().fill(nombre);
  await espera(1500);
  await p.getByRole('button', { name: `Configure ${nombre}`, exact: true }).first().click();
  await espera(5000);
}
async function campo(etiqueta, valor) {
  const c = p.getByLabel(etiqueta).first();
  await c.scrollIntoViewIfNeeded();
  await c.fill(String(valor));
  await c.press('Tab');
  await espera(400);
}
async function elegir(botonActual, opcion) {  // desplegables de Cloudscape: botón con el valor actual → opción
  const btn = typeof botonActual === 'string' ? p.getByRole('button', { name: botonActual, exact: true }).first() : botonActual;
  await btn.scrollIntoViewIfNeeded(); await btn.click(); await espera(500);
  await p.getByRole('option', { name: opcion, exact: true }).first().click(); await espera(600);
}
async function expandir(texto) {
  const t = p.getByRole('button', { name: new RegExp(`^${texto}`) }).first();
  if ((await t.getAttribute('aria-expanded')) === 'false') { await t.scrollIntoViewIfNeeded(); await t.click(); await espera(1200); }
}
async function guardar(desc) {
  await p.getByLabel('Description - optional').first().fill(desc);
  log(desc, '→', await total());
  await p.getByRole('button', { name: 'Save and view summary', exact: true }).click();
  await espera(3000);
}

async function ec2(desc, cantidad, tipo, ebsGB) {
  await agregarServicio('Amazon EC2');
  await campo('Number of instances Enter amount', cantidad);
  await p.getByPlaceholder('Search by instance name or filter by keyword').fill(tipo);
  await espera(2000);
  await p.locator(`tr:has(td div:text-is("${tipo}"))`).first().locator('input[type=radio]').first().check({ force: true });
  await espera(600);
  await p.locator('#on-demand').check({ force: true });
  await espera(600);
  await expandir('Amazon Elastic Block Store \\(EBS\\)');
  await campo(/^Storage amount/, ebsGB);
  await guardar(desc);
}

async function rds() {
  await agregarServicio('Amazon RDS for PostgreSQL');
  const inst = p.locator('input[value^="db."]').first();
  await inst.click(); await inst.fill('db.t4g.micro'); await espera(1200);
  await p.getByRole('option', { name: /db\.t4g\.micro/ }).first().click(); await espera(800);
  // Multi-AZ viene por defecto; almacenamiento gp3 20 GB
  const tipoDisco = p.getByRole('button', { name: /General Purpose SSD \(gp2\)/ }).first();
  if (await tipoDisco.count()) await elegir(tipoDisco, 'General Purpose SSD (gp3)').catch(e => log('gp3:', e.message.split('\n')[0]));
  await campo('Storage amount Value', 20);
  // La calculadora activa por defecto RDS Proxy, Database Insights y Extended Support: el diseño no los usa.
  for (let i = 0; i < 3; i++) {
    const si = p.locator('button', { hasText: /^\s*Yes\s*$/ });
    log('   botones Yes:', await si.count());
    if (!(await si.count())) break;
    await si.first().scrollIntoViewIfNeeded(); await si.first().click(); await espera(500);
    const opciones = await p.getByRole('option').allInnerTexts();
    await p.getByRole('option').filter({ hasText: /^\s*No\s*$/ }).first().click().catch(e => log('   opciones:', opciones.join('|')));
    await espera(700);
  }
  await guardar('RDS PostgreSQL 17 db.t4g.micro Multi-AZ, 20 GB gp3 (sin Proxy ni Insights)');
}

async function alb() {
  await agregarServicio('Elastic Load Balancing');
  await campo('Processed bytes (EC2 Instances and IP addresses as targets) Value', 0.03);
  await campo('Average number of new connections per ALB Value', 2);
  await campo('Average connection duration Value', 5);
  await campo('Average number of requests per second per ALB Enter amount', 1);
  await campo('Average number of rule evaluations per request Enter amount', 3);
  await guardar('ALB tb-ep2-alb: 3 reglas por ruta, ~1 req/s promedio, 20 GB/mes');
}

async function vpc() {
  await agregarServicio('Amazon Virtual Private Cloud (VPC)');
  const toggle = async (nombre, on) => {
    const t = p.getByLabel(nombre, { exact: true }).first();
    if ((await t.isChecked()) !== on) { await t.check({ force: true }).catch(() => t.click({ force: true })); if (!on) await t.uncheck({ force: true }).catch(() => {}); await espera(1500); }
  };
  await toggle('Public IPv4 Address', true);
  await toggle('VPN Connection', false);
  log('   casillas:', await p.evaluate(() => [...document.querySelectorAll('input[type=checkbox]')].filter(c => c.checked).length));
  log('   campos IPv4:', await p.evaluate(() => [...document.querySelectorAll('input:not([type=checkbox])')].map(i => i.getAttribute('aria-label') || '').filter(a => /IP/i.test(a)).join(' | ')));
  const ip = p.locator('input:not([type=checkbox])[aria-label*="IPv4" i]').first();
  await ip.scrollIntoViewIfNeeded(); await ip.fill('5'); await ip.press('Tab'); await espera(500);
  await guardar('IPv4 publicas: 3 EC2 + 2 del ALB');
}

async function cloudwatch() {
  await agregarServicio('Amazon CloudWatch');
  await campo(/^Number of Metrics/, 21);
  await expandir('Dashboards and Alarms');
  await campo(/^Number of Dashboards/, 1);
  await campo(/^Number of Standard Resolution Alarm Metrics/, 5);
  await guardar('CloudWatch: 21 metricas detalladas, 1 dashboard, 5 alarmas');
}

async function s3() {
  await agregarServicio('Amazon Simple Storage Service (S3)');
  await expandir('S3 Standard').catch(() => {});
  await campo(/^S3 Standard storage/, 5);
  await campo(/^PUT, COPY, POST, LIST requests to S3 Standard/, 10000);
  await campo(/^GET, SELECT, and all other requests from S3 Standard/, 50000);
  await guardar('S3 tb-ep2-artefactos: imagenes, config cifrada, logs (5 GB)');
}

const pasos = [
  ['EC2 API', () => ec2('EC2 API + web: ASG tb-ep2-api, 2 x t3.small en 2 AZ', 2, 't3.small', 20)],
  ['EC2 worker', () => ec2('EC2 worker de ingesta: ASG tb-ep2-worker, 1 x t3.small', 1, 't3.small', 20)],
  ['RDS', rds], ['ALB', alb], ['VPC', vpc], ['CloudWatch', cloudwatch], ['S3', s3],
];
for (const [nombre, fn] of pasos) {
  try { await fn(); }
  catch (e) {
    log(`ERROR en ${nombre}:`, e.message.split('\n')[0]);
    await p.screenshot({ path: `error-${nombre.replace(/\s/g, '')}.png` });
    // volver al resumen sin guardar este servicio
    await p.getByRole('button', { name: 'Cancel', exact: true }).first().click().catch(() => {});
    await espera(1500);
    await p.getByRole('button', { name: /^(Yes|Leave|Discard)/ }).first().click().catch(() => {});
    await espera(1500);
    if (!p.url().includes('#/estimate')) { await p.goto('https://calculator.aws/#/estimate'); await espera(2500); }
  }
}

// ---------- Resumen + enlace público
await p.goto('https://calculator.aws/#/estimate'); await espera(3000);
await p.getByLabel(/Description - optional|estimate name/i).first().fill('TodoBarato AI - EP2 ITY1102 (us-east-1)').catch(() => {});
await p.screenshot({ path: 'calc-resumen.png', fullPage: true });
const resumen = await p.locator('body').innerText();
writeFileSync('calc-resumen.txt', resumen);
await p.getByRole('button', { name: 'Share', exact: true }).click(); await espera(1500);
await p.getByRole('button', { name: /Agree and continue/ }).click().catch(() => {}); await espera(5000);
const enlace = await p.evaluate(() => [...document.querySelectorAll('input, a, span, div')].map(e => e.value || e.textContent || '').find(t => /^https:\/\/calculator\.aws\/#\/estimate\?id=/.test(t.trim())));
log('ENLACE', enlace || 'no encontrado');
await p.screenshot({ path: 'calc-share.png' });
writeFileSync('calc-enlace.txt', (enlace || '').trim());
await b.close();
