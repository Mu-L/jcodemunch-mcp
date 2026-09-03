import { computeOrderTotal, Router } from "./router";

export function ordersHandler(req: Request): Response {
  const total = computeOrderTotal([1, 2, 3]);
  return new Response(String(total));
}

export const router = new Router();
router.add({ path: "/orders", handler: ordersHandler });
