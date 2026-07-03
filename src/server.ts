import { randomUUID } from "node:crypto";
import { createServer } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  RESOURCE_MIME_TYPE,
  registerAppResource,
  registerAppTool,
} from "@modelcontextprotocol/ext-apps/server";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import cors from "cors";
import express from "express";
import { z } from "zod";

import { plotLatexFunction } from "./plotter.js";
import { WIDGET_HTML, WIDGET_URI } from "./widget.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 8080);
const PUBLIC_DOMAIN = process.env.PUBLIC_DOMAIN || `http://localhost:${PORT}`;

function createPlotServer(): McpServer {
  const server = new McpServer(
    {
      name: "latex-function-plotter",
      version: "1.0.0",
    },
    {
      instructions:
        "Usa plot_latex_function quando l'utente fornisce una funzione in LaTeX (es. \\frac{1}{x}, x^2, \\sin(x)) e vuole il grafico con asintoti. Passa latex, xmin e xmax se specificati.",
    }
  );

  registerAppResource(
    server,
    "function-plot-widget",
    WIDGET_URI,
    {
      description: "Widget interattivo per grafici di funzioni LaTeX",
      _meta: {
        ui: {
          prefersBorder: true,
          domain: PUBLIC_DOMAIN,
          csp: {
            connectDomains: [],
            resourceDomains: [
              "https://cdn.plot.ly",
              "https://cdnjs.cloudflare.com",
            ],
          },
        },
        "openai/widgetDescription":
          "Grafico interattivo della funzione con curve, asintoti verticali/orizzontali/obliqui e punti notevoli.",
      },
    },
    async () => ({
      contents: [
        {
          uri: WIDGET_URI,
          mimeType: RESOURCE_MIME_TYPE,
          text: WIDGET_HTML,
        },
      ],
    })
  );

  registerAppTool(
    server,
    "plot_latex_function",
    {
      title: "Grafico funzione LaTeX",
      description:
        "Genera il grafico di una funzione matematica scritta in LaTeX, includendo punti notevoli e asintoti (verticali, orizzontali, obliqui).",
      inputSchema: {
        latex: z
          .string()
          .describe(
            'Espressione LaTeX, es. "\\\\frac{1}{x}", "x^2", "\\\\sin(x)", "\\\\frac{x^2-1}{x-1}"'
          ),
        xmin: z
          .number()
          .optional()
          .describe("Estremo sinistro del dominio (default -10)"),
        xmax: z
          .number()
          .optional()
          .describe("Estremo destro del dominio (default 10)"),
      },
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        openWorldHint: false,
      },
      _meta: {
        ui: { resourceUri: WIDGET_URI },
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Calcolo grafico e asintoti…",
        "openai/toolInvocation/invoked": "Grafico pronto.",
      },
    },
    async ({ latex, xmin, xmax }) => {
      const plot = await plotLatexFunction({ latex, xmin, xmax });
      const asymptoteCount = plot.asymptotes.length;
      const summary = `Grafico di f(x)=${latex} su [${plot.domain[0]}, ${plot.domain[1]}]. Espressione: ${plot.expression}. Asintoti: ${asymptoteCount}. Punti notevoli: ${plot.specialPoints.length}.`;

      return {
        structuredContent: { plot, summary },
        content: [{ type: "text", text: summary }],
        _meta: { plot },
      };
    }
  );

  return server;
}

const app = express();
app.use(
  cors({
    origin: [
      "https://chatgpt.com",
      "https://chat.openai.com",
      "https://cdn.oaistatic.com",
    ],
    credentials: true,
    allowedHeaders: [
      "Content-Type",
      "Authorization",
      "MCP-Protocol-Version",
      "Mcp-Session-Id",
    ],
    methods: ["GET", "POST", "OPTIONS", "DELETE"],
  })
);
app.use(express.json({ limit: "2mb" }));

const transports = new Map<string, StreamableHTTPServerTransport>();

app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    name: "latex-function-plotter-mcp",
    version: "1.0.0",
    mcp: "/mcp",
  });
});

app.get("/", (_req, res) => {
  res.json({
    name: "latex-function-plotter-mcp",
    version: "1.0.0",
    description: "MCP server: grafici di funzioni LaTeX per ChatGPT",
    endpoints: { health: "/health", mcp: "/mcp" },
    chatgpt: "Imposta l'URL del connettore su https://<tuo-dominio>/mcp",
  });
});

app.post("/mcp", async (req, res) => {
  const sessionId = req.headers["mcp-session-id"] as string | undefined;
  let transport = sessionId ? transports.get(sessionId) : undefined;

  if (!transport) {
    transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: () => randomUUID(),
      onsessioninitialized: (id) => {
        transports.set(id, transport!);
      },
    });

    const server = createPlotServer();
    await server.connect(transport);
  }

  await transport.handleRequest(req, res, req.body);
});

app.get("/mcp", async (req, res) => {
  const sessionId = req.headers["mcp-session-id"] as string | undefined;
  const transport = sessionId ? transports.get(sessionId) : undefined;
  if (!transport) {
    res.status(400).json({
      jsonrpc: "2.0",
      error: { code: -32000, message: "Sessione MCP non valida" },
      id: null,
    });
    return;
  }
  await transport.handleRequest(req, res);
});

app.delete("/mcp", async (req, res) => {
  const sessionId = req.headers["mcp-session-id"] as string | undefined;
  const transport = sessionId ? transports.get(sessionId) : undefined;
  if (transport) {
    await transport.close();
    transports.delete(sessionId!);
  }
  res.status(200).end();
});

createServer(app).listen(PORT, () => {
  console.log(`latex-function-plotter-mcp listening on :${PORT}`);
  console.log(`MCP endpoint: ${PUBLIC_DOMAIN}/mcp`);
});
