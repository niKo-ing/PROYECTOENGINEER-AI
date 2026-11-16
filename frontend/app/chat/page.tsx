import type { Metadata } from "next";
import { Suspense } from "react";

import { AgentScreen } from "@/components/agent/agent-screen";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
  title: "Asistente de ahorro — SoloTodo",
  description: "Un solo asistente: conversa, compara productos, razona sobre el historial de precios y deja alertas y listas de compra guardadas.",
};

export default function ChatPage() {
  return (
    <div className="chat-page flex h-full min-h-0 w-full flex-col overflow-hidden">
      <Suspense fallback={<Skeleton className="mx-auto mt-10 h-24 w-full max-w-3xl rounded-3xl" />}>
        <AgentScreen />
      </Suspense>
    </div>
  );
}
