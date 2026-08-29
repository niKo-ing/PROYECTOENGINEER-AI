import { Suspense } from "react";

import { AuthSkeleton } from "@/components/auth/auth-skeleton";
import { RegisterView } from "@/components/auth/register-view";

export default function RegisterPage() {
  return (
    <Suspense fallback={<AuthSkeleton />}>
      <RegisterView />
    </Suspense>
  );
}