import { Skeleton } from "@/components/ui/skeleton";

export function AuthSkeleton() {
  return (
    <main className="mx-auto w-full max-w-md px-4 py-10 sm:py-14">
      <Skeleton className="h-72 w-full rounded-3xl" />
    </main>
  );
}