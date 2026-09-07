"use client";

import { Lightbulb, ExternalLink, FileText } from "lucide-react";

import type { EvidenceEntry, RecommendationDetail } from "@/lib/api/chat";

const CLAIM_LABELS: Record<string, string> = {
  fact: "Dato",
  performance: "Rendimiento",
  compatibility: "Compatibilidad",
  price: "Precio",
  recommendation: "Recomendación",
  inference: "Inferencia",
  unknown: "Sin clasificar",
  conflict: "Conflicto",
};

function ClaimBadge({ claimType }: { claimType: string | null | undefined }) {
  const label = claimType ? CLAIM_LABELS[claimType] ?? claimType : "Evidencia";
  return (
    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
      {label}
    </span>
  );
}

function Confidence({ value }: { value: number }) {
  const percent = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <span className="rounded-full bg-background px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
      {percent}% confianza
    </span>
  );
}

function EvidenceList({ evidence }: { evidence: EvidenceEntry[] }) {
  if (!evidence.length) return null;
  return (
    <div className="mt-2.5 border-t border-border/70 pt-2.5">
      <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <FileText className="size-3" />
        Evidencia recopilada
      </p>
      <ul className="mt-1.5 space-y-2">
        {evidence.map((entry, index) => {
          const key = `${entry.source_name}-${entry.source_url ?? entry.title ?? index}`;
          const label = entry.title || entry.content?.slice(0, 120);
          return (
            <li key={key} className="flex flex-wrap items-center gap-1.5 text-xs leading-5">
              <ClaimBadge claimType={entry.claim_type} />
              <Confidence value={entry.confidence} />
              {entry.source_url ? (
                <a
                  href={entry.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-primary hover:underline"
                >
                  {entry.source_name}
                  <ExternalLink className="size-3" />
                </a>
              ) : (
                <span className="text-muted-foreground">{entry.source_name}</span>
              )}
              {label ? <span className="text-muted-foreground">— {label}</span> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function BadgeList({ label, items }: { label: string; items?: string[] }) {
  if (!items || !items.length) return null;
  return (
    <li className="flex flex-wrap items-baseline gap-x-1.5 gap-y-1 text-xs leading-5">
      <span className="font-semibold text-foreground">{label}:</span>
      {items.map((item) => (
        <span key={item} className="rounded-full bg-background px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
          {item}
        </span>
      ))}
    </li>
  );
}

function CriterionScores({ scores }: { scores: Record<string, number> }) {
  const entries = Object.entries(scores).sort(([, a], [, b]) => b - a);
  if (!entries.length) return null;
  return (
    <li className="space-y-1.5 text-xs leading-5">
      <span className="font-semibold text-foreground">Criterios evaluados:</span>
      {entries.slice(0, 6).map(([criterion, score]) => (
        <div key={criterion} className="flex items-center justify-between gap-3">
          <span className="text-muted-foreground">{criterion}</span>
          <span className="font-medium text-foreground">{Math.round(score * 100)}%</span>
        </div>
      ))}
    </li>
  );
}

function RecommendationBox({ recommendation }: { recommendation: RecommendationDetail }) {
  if (!recommendation.winner_id) return null;
  const reason = recommendation.final_reason || recommendation.winner_reason;
  return (
    <div className="mt-2.5 border-t border-border/70 pt-2.5">
      <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <Lightbulb className="size-3" />
        ¿Por qué esta recomendación?
      </p>
      <ul className="mt-1.5 space-y-1.5">
        {recommendation.user_need ? (
          <li className="text-xs leading-5">
            <span className="font-semibold text-foreground">Necesidad:</span>{" "}
            <span className="text-muted-foreground">{recommendation.user_need}</span>
          </li>
        ) : null}
        <BadgeList label="Requisitos" items={recommendation.hard_constraints} />
        <BadgeList label="Preferencias" items={recommendation.soft_preferences} />
        <CriterionScores scores={recommendation.criteria_scores ?? {}} />
        {reason ? (
          <li className="text-xs leading-5 text-muted-foreground">
            <span className="font-semibold text-foreground">Motivo:</span> {reason}
          </li>
        ) : null}
        {recommendation.basis ? (
          <li className="text-[11px] text-muted-foreground">
            Base: {recommendation.basis === "catalog" ? "catálogo" : recommendation.basis}
          </li>
        ) : null}
      </ul>
    </div>
  );
}

export function EvidencePanel({
  evidence,
  recommendation,
}: {
  evidence?: EvidenceEntry[];
  recommendation?: RecommendationDetail | null;
}) {
  if ((!evidence || !evidence.length) && !recommendation?.winner_id) return null;
  return (
    <>
      <RecommendationBox recommendation={recommendation ?? {}} />
      <EvidenceList evidence={evidence ?? []} />
    </>
  );
}