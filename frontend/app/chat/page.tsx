import { Suspense } from "react";

import { SoloTodoApp } from "@/components/solotodo-app";
import { Skeleton } from "@/components/ui/skeleton";

export default function ChatPage() {
  return (
    <Suspense fallback={<ChatSkeleton />}>
      <SoloTodoApp />
    </Suspense>
  );
}

function ChatSkeleton() {
  return (
    <div className="mx-auto max-w-5xl px-5 py-8 sm:px-8 sm:py-12">
      <Skeleton className="h-24 w-full rounded-3xl" />
    </div>
  );
}
