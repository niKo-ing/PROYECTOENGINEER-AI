import type { Metadata } from "next";
import { Suspense } from "react";

import { AgentScreen } from "@/components/agent/agent-screen";

export const metadata: Metadata = {
  title: "Agente de ahorro — SoloTodo",
  description: "Un agente que busca, razona sobre el historial de precios y deja alertas y listas de compra guardadas.",
};

export default function AgentPage() {
  return (
    <div className="chat-page flex h-full min-h-0 w-full flex-col overflow-hidden">
      <Suspense fallback={<p className="py-20 text-center text-sm text-muted-foreground">Cargando…</p>}>
        <AgentScreen />
      </Suspense>
    </div>
  );
}
