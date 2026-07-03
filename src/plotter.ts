import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PYTHON_SCRIPT = path.join(__dirname, "..", "python", "plot_function.py");

export interface PlotCurve {
  x: number[];
  y: number[];
}

export interface Asymptote {
  type: "vertical" | "horizontal" | "oblique";
  x?: number;
  y?: number | null;
  m?: number;
  b?: number;
}

export interface SpecialPoint {
  x: number;
  y: number;
  type: string;
}

export interface PlotData {
  latex: string;
  expression: string;
  domain: [number, number];
  curves: PlotCurve[];
  asymptotes: Asymptote[];
  specialPoints: SpecialPoint[];
}

export async function plotLatexFunction(input: {
  latex: string;
  xmin?: number;
  xmax?: number;
}): Promise<PlotData> {
  const pythonCmd = process.env.PYTHON_PATH || "python";
  const payload = JSON.stringify({
    latex: input.latex,
    xmin: input.xmin ?? -10,
    xmax: input.xmax ?? 10,
  });

  return new Promise((resolve, reject) => {
    const child = spawn(pythonCmd, [PYTHON_SCRIPT], {
      stdio: ["pipe", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("error", (err) => reject(err));
    child.on("close", (code) => {
      try {
        const parsed = JSON.parse(stdout) as {
          ok: boolean;
          data?: PlotData;
          error?: string;
        };
        if (!parsed.ok || !parsed.data) {
          reject(new Error(parsed.error || stderr || `Python exited with ${code}`));
          return;
        }
        resolve(parsed.data);
      } catch {
        reject(new Error(stderr || stdout || `Python exited with ${code}`));
      }
    });

    child.stdin.write(payload);
    child.stdin.end();
  });
}
