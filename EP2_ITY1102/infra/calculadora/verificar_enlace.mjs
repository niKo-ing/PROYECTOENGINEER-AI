// Abre el enlace público en un navegador limpio (sin estado) y captura el resumen del presupuesto.
import { chromium } from 'playwright-core';
import { readFileSync } from 'node:fs';
const exe = `${process.env.HOME}/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome`;
const url = readFileSync('calc-enlace.txt', 'utf8').trim();
const b = await chromium.launch({ executablePath: exe, headless: true });
const p = await b.newPage({ viewport: { width: 1500, height: 1250 }, locale: 'en-US' });
await p.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
await p.waitForTimeout(5000);
const t = await p.locator('body').innerText();
const m = t.match(/Monthly cost\s*\n?\s*([\d,.]+ USD)/);
console.log('Total mensual:', m?.[1], '| 12 meses:', t.match(/Total 12 months cost\s*\n?\s*([\d,.]+ USD)/)?.[1]);
for (const l of t.split('\n').filter(l => /^\s*[\d,.]+ USD$/.test(l)).slice(0, 20)) process.stdout.write(l.trim() + ' · ');
console.log();
await p.getByRole('button', { name: 'Accept', exact: true }).first().click({ timeout: 3000 }).catch(() => {}); await p.waitForTimeout(800);
await p.screenshot({ path: '/home/nikocode/Documentos/Proyecto Arquitectura en IA/EP2_ITY1102/evidencia/aws-pricing-calculator.png' });
await b.close();
