// Router for the smoke fixture (TypeScript grammar must load from the wheel).
export interface Route {
  path: string;
  handler: (req: Request) => Response;
}

export function computeOrderTotal(items: number[]): number {
  return items.reduce((a, b) => a + b, 0);
}

export class Router {
  private routes: Route[] = [];
  add(route: Route): void {
    this.routes.push(route);
  }
  match(path: string): Route | undefined {
    return this.routes.find((r) => r.path === path);
  }
}
