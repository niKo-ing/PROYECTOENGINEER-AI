"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut, UserRound } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { useSession } from "@/lib/supabase/use-session";

export function ProfileMenu() {
  const router = useRouter();
  const { session, isLoading } = useSession();
  const [pendingSignOut, setPendingSignOut] = useState(false);

  const displayName =
    typeof session?.user.user_metadata?.name === "string" && session.user.user_metadata.name.trim()
      ? session.user.user_metadata.name.trim()
      : session?.user.email?.split("@")[0];

  async function signOut() {
    setPendingSignOut(true);
    try {
      await createSupabaseBrowserClient().auth.signOut();
      router.push("/login");
      router.refresh();
    } catch {
      // La sesión se refresca en el próximo intento.
    } finally {
      setPendingSignOut(false);
    }
  }

  if (isLoading) {
    return (
      <Button variant="ghost" size="icon" className="size-9" disabled aria-label="Cargando perfil">
        <UserRound className="size-4" aria-hidden="true" />
      </Button>
    );
  }

  if (!session) {
    return (
      <Button variant="ghost" asChild className="gap-2">
        <Link href="/login">
          <UserRound className="size-4" aria-hidden="true" />
          <span className="hidden sm:inline">Perfil</span>
        </Link>
      </Button>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="gap-2" aria-label="Menú de perfil">
          <UserRound className="size-4" aria-hidden="true" />
          <span className="hidden max-w-28 truncate sm:inline">{displayName}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="truncate">
          <span className="block truncate font-medium">{displayName}</span>
          <span className="block truncate text-xs font-normal text-muted-foreground">
            {session.user.email}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          disabled={pendingSignOut}
          onSelect={() => void signOut()}
          className="text-destructive focus:text-destructive"
        >
          <LogOut className="size-4" aria-hidden="true" />
          Cerrar sesión
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}