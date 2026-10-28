import { expect, test } from "vitest";
import { z } from "zod";

test("an overlong text is explained in Spanish", () => {
  const result = z.string().max(3).safeParse("abcd");

  expect(result.error?.issues[0]?.message).toBe("Escribe como máximo 3 caracteres.");
});
