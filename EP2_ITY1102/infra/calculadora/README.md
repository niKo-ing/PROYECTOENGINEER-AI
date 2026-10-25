# Presupuesto en AWS Pricing Calculator

Enlace público (solo lectura, sin cuenta): https://calculator.aws/#/estimate?id=1a58bb3366135e297defcea9acb01e129929f388

**USD 120,44 al mes · USD 1.445,28 en 12 meses** (us-east-1, precios del 25-10-2026).

| Servicio | Configuración | USD/mes |
|---|---|---|
| Amazon EC2 | 2 × t3.small On-Demand + EBS 20 GB c/u (API + web) | 33,57 |
| Amazon EC2 | 1 × t3.small On-Demand + EBS 20 GB (worker) | 16,78 |
| Amazon RDS for PostgreSQL | db.t4g.micro Multi-AZ, 20 GB gp3, sin RDS Proxy ni Database Insights | 27,96 |
| Elastic Load Balancing | 1 ALB, ~1 req/s, 2 conexiones nuevas/s, 3 reglas, 20 GB/mes | 16,90 |
| Amazon VPC | 5 IPv4 públicas en uso | 18,25 |
| Amazon CloudWatch | 21 métricas, 1 dashboard, 5 alarmas | 6,80 |
| Amazon S3 | 5 GB Standard, 10.000 PUT, 50.000 GET | 0,18 |

Ojo: la calculadora activa por defecto **RDS Proxy (+21,90)** y **Database Insights (+18,25)** en RDS; el script los pone en «No».

## Regenerar (si cambian los supuestos)

Usa Chromium con Playwright (`playwright-core` y el Chromium de `~/.cache/ms-playwright`):

```bash
mkdir -p /tmp/pw && cd /tmp/pw && pnpm add playwright-core@1.58.2
cp ".../EP2_ITY1102/infra/calculadora/"*.mjs . && node armar_presupuesto.mjs   # escribe calc-enlace.txt
node verificar_enlace.mjs                                                       # total y captura
```
