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
    <div className="chat-page flex h-full min-h-0 items-center justify-center px-5">
      <div className="w-full max-w-3xl">
        <Skeleton className="h-24 w-full rounded-3xl" />
      </div>
    </div>
  );
}
