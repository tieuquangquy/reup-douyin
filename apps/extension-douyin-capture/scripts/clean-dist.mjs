import { rmSync } from "node:fs";
import { join } from "node:path";

const root = process.cwd();
rmSync(join(root, "dist"), { recursive: true, force: true });
