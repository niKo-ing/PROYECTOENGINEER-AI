"use client";

import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function HomeSearchBar() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  function submitSearch(event: React.FormEvent) {
    event.preventDefault();
    const term = query.trim();
    if (!term) return;
    router.push(`/search?q=${encodeURIComponent(term)}`);
  }

  return (
    <form onSubmit={submitSearch} className="mx-auto w-full max-w-2xl" role="search">
      <div className="flex items-center gap-2 rounded-2xl border bg-background p-2 shadow-lg shadow-primary/5">
        <span className="pl-3 text-muted-foreground" aria-hidden="true">
          <Search className="h-5 w-5" />
        </span>
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Notebook, celular, TV…"
          aria-label="Buscar productos"
          className="h-11 border-0 bg-transparent text-base shadow-none focus-visible:ring-0"
        />
        <Button type="submit" size="lg" className="shrink-0 px-6">
          Buscar
        </Button>
      </div>
    </form>
  );
}
