"use client";

import Link from "next/link";
import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import { ArrowLeft, Bot, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import { fetchGuide } from "@/lib/api/pc";

export default function GuidePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const query = useQuery({ queryKey: ["pc-guide", slug], queryFn: () => fetchGuide(slug), staleTime: Infinity });

  if (query.isLoading) return <div className="mx-auto max-w-3xl px-4 py-8"><div className="h-96 animate-pulse rounded-xl bg-muted/60" /></div>;
  if (query.isError || !query.data) {
    return (
      <div className="mx-auto max-w-xl px-4 py-16 text-center">
        <p className="text-muted-foreground">No encontramos esa guía.</p>
        <Button asChild variant="link">
          <Link href="/guias">Ver todas las guías</Link>
        </Button>
      </div>
    );
  }

  const guide = query.data;
  return (
    <div className="mx-auto grid max-w-5xl gap-8 px-4 py-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_240px]">
      <article>
        <Link href="/guias" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" aria-hidden="true" />
          Guías
        </Link>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{guide.title}</h1>
        <p className="mt-2 text-lg text-muted-foreground">{guide.summary}</p>
        <div className="mt-6 space-y-4 text-[15px] leading-relaxed [&_h2]:mt-8 [&_h2]:text-xl [&_h2]:font-semibold [&_li]:ml-5 [&_ol]:list-decimal [&_ol]:space-y-1 [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:space-y-1">
          <ReactMarkdown>{guide.body}</ReactMarkdown>
        </div>
        <div className="mt-10 flex flex-wrap gap-2 rounded-xl border bg-muted/30 p-4">
          <p className="basis-full text-sm font-medium">¿Listo para probar?</p>
          <Button asChild className="gap-2">
            <Link href="/armar">
              <Wrench className="size-4" aria-hidden="true" />
              Ir al armador
            </Link>
          </Button>
          <Button asChild variant="outline" className="gap-2">
            <Link href="/armar/asistente">
              <Bot className="size-4" aria-hidden="true" />
              Preguntarle a la IA
            </Link>
          </Button>
        </div>
      </article>
      <aside className="lg:pt-10">
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Otras guías</h2>
        <ul className="space-y-2 text-sm">
          {guide.others.map((other) => (
            <li key={other.slug}>
              <Link href={`/guias/${other.slug}`} className="text-primary underline-offset-4 hover:underline">
                {other.title}
              </Link>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
