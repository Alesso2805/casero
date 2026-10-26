export function hashToken(hash: string): string | null {
  return new URLSearchParams(hash.replace(/^#/, "")).get("token");
}
