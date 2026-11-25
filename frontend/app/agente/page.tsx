import { redirect } from "next/navigation";

// El agente y el chat de IA se unificaron: /agente se conserva solo para no romper enlaces antiguos.
export default async function AgentRedirect({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(await searchParams)) {
    if (typeof value === "string") params.set(key, value);
  }
  const suffix = params.toString();
  redirect(suffix ? `/chat?${suffix}` : "/chat");
}
