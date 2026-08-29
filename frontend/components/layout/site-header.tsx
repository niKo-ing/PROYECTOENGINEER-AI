"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { MessageSquareText, Settings, ShoppingBag } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ProfileMenu } from "@/components/layout/profile-menu";

export function SiteHeader() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  function submitSearch(event: React.FormEvent) {
    event.preventDefault();
    const term = query.trim();
    if (!term) return;
    router.push(`/search?q=${encodeURIComponent(term)}`);
  }

  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary font-bold text-primary-foreground" aria-hidden="true">
            S
          </span>
          <span className="hidden font-semibold tracking-tight sm:inline">
            SoloTodo <span className="text-primary">Comparador</span>
          </span>
        </Link>

        <form onSubmit={submitSearch} className="mx-auto flex w-full max-w-xl items-center gap-2" role="search">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar producto, marca o modelo…"
            aria-label="Buscar productos"
            className="h-10"
          />
          <Button type="submit" size="icon" className="shrink-0" aria-label="Buscar">
            <ShoppingBag className="h-4 w-4" />
          </Button>
        </form>

        <nav className="flex shrink-0 items-center gap-1">
          <Button variant="ghost" asChild className="gap-2">
            <Link href="/chat">
              <MessageSquareText className="h-4 w-4" />
              <span className="hidden sm:inline">Chat IA</span>
            </Link>
          </Button>
          <Button variant="ghost" asChild className="gap-2">
            <Link href="/admin">
              <Settings className="h-4 w-4" />
              <span className="hidden sm:inline">Admin</span>
            </Link>
          </Button>
          <ProfileMenu />
        </nav>
      </div>
    </header>
  );
}
