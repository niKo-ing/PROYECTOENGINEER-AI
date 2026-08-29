import { Suspense } from "react";

import { AuthSkeleton } from "@/components/auth/auth-skeleton";
import { LoginView } from "@/components/auth/login-view";

export default function LoginPage() {
  return (
    <Suspense fallback={<AuthSkeleton />}>
      <LoginView />
    </Suspense>
  );
}