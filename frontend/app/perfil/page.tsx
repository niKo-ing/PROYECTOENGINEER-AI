"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, Download, LoaderCircle, Monitor, ShieldCheck, Trash2, UserRound, Wrench } from "lucide-react";

import { LoginNeeded } from "@/components/pc/pc-ui";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { auth } from "@/lib/auth/client";
import { useSession } from "@/lib/auth/use-session";
import { deleteMyData, exportMyData, listMyPcs } from "@/lib/api/pc";

export default function ProfilePage() {
  const { session, isLoading } = useSession();
  const router = useRouter();
  const token = session?.access_token ?? "";
  const pcs = useQuery({ queryKey: ["my-pcs", token], queryFn: () => listMyPcs(token), enabled: Boolean(token) });
  const [exporting, setExporting] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [message, setMessage] = useState("");

  if (isLoading) return <div className="px-4 py-16 text-center text-muted-foreground">Cargando…</div>;
  if (!session) {
    return (
      <div className="px-4 py-16">
        <LoginNeeded what="ver tu perfil" />
      </div>
    );
  }

  const name = typeof session.user.user_metadata?.name === "string" && session.user.user_metadata.name.trim() ? session.user.user_metadata.name : session.user.email?.split("@")[0];
  const items = pcs.data?.items ?? [];

  async function download() {
    setExporting(true);
    setMessage("");
    try {
      const data = await exportMyData(token);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `mis-datos-todobarato-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo descargar.");
    } finally {
      setExporting(false);
    }
  }

  async function removeEverything() {
    setDeleting(true);
    try {
      await deleteMyData(token);
      await auth.signOut();
      router.push("/?cuenta=borrada");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo borrar.");
      setDeleting(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <div className="mb-8 flex items-center gap-4">
        <span className="flex size-14 items-center justify-center rounded-full bg-primary/10 text-primary">
          <UserRound className="size-7" aria-hidden="true" />
        </span>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{name}</h1>
          <p className="text-sm text-muted-foreground">{session.user.email}</p>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Monitor className="size-4 text-primary" aria-hidden="true" />
              Mis computadores
            </CardTitle>
            <CardDescription>
              {pcs.isLoading
                ? "Cargando…"
                : `${items.filter((pc) => pc.kind === "propio").length} propio(s) y ${items.filter((pc) => pc.kind === "proyecto").length} proyecto(s)`}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button asChild>
              <Link href="/mis-pc">Ver todos</Link>
            </Button>
            <Button asChild variant="outline" className="gap-2">
              <Link href="/armar">
                <Wrench className="size-4" aria-hidden="true" />
                Armar
              </Link>
            </Button>
            <Button asChild variant="outline" className="gap-2">
              <Link href="/armar/asistente">
                <Bot className="size-4" aria-hidden="true" />
                Asistente
              </Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldCheck className="size-4 text-primary" aria-hidden="true" />
              Tus datos
            </CardTitle>
            <CardDescription>Puedes descargarlos o borrarlos cuando quieras (Ley 19.628 y Ley 21.719).</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button variant="outline" className="gap-2" onClick={() => void download()} disabled={exporting}>
              {exporting ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : <Download className="size-4" aria-hidden="true" />}
              Descargar mis datos
            </Button>
            <Button variant="outline" className="gap-2 text-destructive hover:text-destructive" onClick={() => setDeleteOpen(true)}>
              <Trash2 className="size-4" aria-hidden="true" />
              Borrar mi cuenta y datos
            </Button>
            {message ? (
              <p className="basis-full text-sm text-destructive" role="alert">
                {message}
              </p>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <section className="mt-8 rounded-xl border bg-muted/30 p-5 text-sm leading-relaxed">
        <h2 className="mb-2 flex items-center gap-2 font-semibold">
          <Bot className="size-4 text-primary" aria-hidden="true" />
          Cómo usamos la inteligencia artificial
        </h2>
        <ul className="list-disc space-y-1.5 pl-5 text-muted-foreground">
          <li>El asistente usa Gemini (Google) para entender lo que pides y explicar los armados. Lo que escribes se envía a ese servicio para generar la respuesta.</li>
          <li>La compatibilidad no la decide la IA: la revisa un motor de reglas (socket, memoria, medidas, watts). Si la IA cita un precio que no está en los datos, su explicación se descarta.</li>
          <li>Para medir la calidad guardamos un registro técnico de cada consulta (tiempos, herramientas usadas) con un identificador seudónimo y una vista previa con correos, RUT y teléfonos enmascarados.</li>
          <li>Los precios del armador son referenciales; confirma en la tienda antes de comprar.</li>
        </ul>
      </section>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>¿Borrar tu cuenta y todos tus datos?</DialogTitle>
            <DialogDescription>
              Se eliminan tu cuenta, tus computadores, listas, alertas, lo que recuerda el asistente, tu historial de conversación y los registros técnicos asociados. No se puede deshacer.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="confirmar">Escribe BORRAR para confirmar</Label>
            <Input id="confirmar" value={confirmText} onChange={(event) => setConfirmText(event.target.value)} autoComplete="off" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              Cancelar
            </Button>
            <Button variant="destructive" disabled={confirmText !== "BORRAR" || deleting} onClick={() => void removeEverything()}>
              {deleting ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : null}
              Borrar todo
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
