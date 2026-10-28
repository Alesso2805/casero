import { z } from "zod";

/** Zod's own messages are in English; every limit a schema leaves unworded gets one here. */
export function configureValidation(): void {
  z.config({
    customError: (issue) =>
      issue.code === "too_big" && issue.origin === "string"
        ? `Escribe como máximo ${String(issue.maximum)} caracteres.`
        : undefined,
  });
}
