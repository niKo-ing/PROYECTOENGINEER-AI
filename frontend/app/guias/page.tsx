"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, LoaderCircle, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fetchGuides, searchGuides } from "@/lib/api/pc";

export default function GuidesPage() {
  const guides = useQuery({ queryKey: ["pc-guides"], queryFn: fetchGuides, staleTime: Infinity });
  const [question, setQuestion] = useState("");
  const [submitted, setSubmitted] = useState("");
  const results = useQuery({ queryKey: ["pc-guides-search", submitted], queryFn: () => searchGuides(submitted), enabled: submitted.length >= 3 });

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Guías de compatibilidad</h1>
      <p className="mt-1 max-w-2xl text-muted-foreground">
        Lo que hay que saber para que las piezas calcen. Son la misma base de conocimiento que consulta la IA cuando te explica un armado.
      </p>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          setSubmitted(question.trim());
        }}
        className="mt-6 flex max-w-xl gap-2"
        role="search"
      >
        <Input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ej.: ¿sirve memoria DDR4 en una placa AM5?" aria-label="Pregunta" />
        <Button type="submit" className="gap-2" disabled={question.trim().length < 3}>
          <Search className="size-4" aria-hidden="true" />
          Buscar
        </Button>
      </form>

      {submitted ? (
        <section className="mt-6" aria-live="polite">
          <h2 className="mb-3 text-sm font-medium text-muted-foreground">Fragmentos más relevantes para «{submitted}»</h2>
          {results.isLoading ? (
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" aria-label="Buscando" />
          ) : (
            <ul className="space-y-3">
              {(results.data?.items ?? []).map((hit, index) => (
                <li key={index} className="rounded-lg border p-4">
                  <Link href={hit.url} className="text-sm font-medium text-primary underline-offset-4 hover:underline">
                    {hit.title}
                  </Link>
                  <p className="mt-1 line-clamp-4 whitespace-pre-line text-sm text-muted-foreground">{hit.content.replace(/[#*]/g, "")}</p>
                </li>
              ))}
              {results.data && results.data.items.length === 0 ? <li className="text-sm text-muted-foreground">No encontramos nada sobre eso.</li> : null}
            </ul>
          )}
        </section>
      ) : null}

      <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {(guides.data?.items ?? []).map((guide) => (
          <li key={guide.slug}>
            <Link href={`/guias/${guide.slug}`} className="flex h-full flex-col gap-2 rounded-xl border bg-card p-4 transition-colors hover:border-primary/50 hover:bg-muted/30">
              <BookOpen className="size-5 text-primary" aria-hidden="true" />
              <h2 className="font-semibold leading-snug">{guide.title}</h2>
              <p className="text-sm text-muted-foreground">{guide.summary}</p>
            </Link>
          </li>
        ))}
        {guides.isLoading
          ? Array.from({ length: 6 }).map((_, index) => <li key={index} className="h-40 animate-pulse rounded-xl bg-muted/60" />)
          : null}
      </ul>
    </div>
  );
}
