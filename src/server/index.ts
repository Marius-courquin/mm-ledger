import { TradeRepublicApi, createMessage } from "trapi";
import { IBApi, EventName, Contract } from "@stoqey/ib";
import { chromium } from "playwright-core";
import { join } from "path";
import { writeFileSync } from "fs";
import { homedir } from "os";
import { spawn, type Subprocess } from "bun";

// --- Helpers ---
const safeParse = (data: string) => {
  try {
    return JSON.parse(data);
  } catch {
    // Some TR endpoints return truncated JSON (missing leading '[')
    try {
      return JSON.parse("[" + data);
    } catch {
      return data;
    }
  }
};

// --- TR API connection ---
let api: TradeRepublicApi | null = null;
let connected = false;
let waitingForPin = false;
let pinResolver: ((pin: string) => void) | null = null;
let trPhoneNumber = "";
let trPin = "";

function sub<T extends Parameters<typeof createMessage>[0]>(
  type: T,
  opts?: any
): Promise<any> {
  if (!api) throw new Error("TR API not connected");
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("Subscription timeout")), 10000);
    api!.subscribeOnce(createMessage(type, opts), (data) => {
      clearTimeout(timeout);
      resolve(data ? safeParse(data) : null);
    });
  });
}

const PRODUCT_LABELS: Record<string, string> = {
  DEFAULT: "CTO",
  TAX_WRAPPER: "PEA",
};

// Browser-based login to bypass AWS WAF
const BRAVE_PATH = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser";
let trBrowserPage: any = null;
let trBrowserContext: any = null;
let trBrowser: any = null;

async function loginViaBrowser(phoneNumber: string, pin: string): Promise<{ processId?: string } | null> {
  console.log("TR: attempting browser-based login (WAF bypass)...");
  let browser;
  try {
    // Close previous browser if any
    if (trBrowser) { try { await trBrowser.close(); } catch {} }

    browser = await chromium.launch({
      headless: false,
      executablePath: BRAVE_PATH,
      args: ["--window-size=400,300", "--window-position=9999,9999"],
    });
    trBrowser = browser;
    const ctx = await browser.newContext();
    trBrowserContext = ctx;
    const page = await ctx.newPage();
    trBrowserPage = page;

    // Navigate to TR app — this loads the AWS WAF JS and sets the waf-token cookie
    console.log("TR browser: loading app.traderepublic.com...");
    await page.goto("https://app.traderepublic.com/login");
    // Wait for WAF challenge to complete and page to fully load
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(5000);

    // Check if WAF token cookie exists
    const cookies = await ctx.cookies("https://api.traderepublic.com");
    const wafCookie = cookies.find(c => c.name === "aws-waf-token");
    console.log("TR browser: WAF token present:", !!wafCookie);

    // Intercept the login request to add proper headers (the app.tr site does this)
    const result = await page.evaluate(async ({ phone, pin }: { phone: string; pin: string }) => {
      // Get the aws-waf-token from cookies
      const wafMatch = document.cookie.match(/aws-waf-token=([^;]+)/);
      const wafToken = wafMatch?.[1] || "";

      const r = await fetch("https://api.traderepublic.com/api/v1/auth/web/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-aws-waf-token": wafToken,
        },
        body: JSON.stringify({ phoneNumber: phone, pin }),
        credentials: "include",
      });
      return { status: r.status, body: await r.text() };
    }, { phone: phoneNumber, pin });

    console.log("TR browser login status:", result.status);

    if (result.status === 200) {
      const data = JSON.parse(result.body);
      console.log("TR browser login success, processId:", data.processId);
      return data;
    }

    console.log("TR browser login response:", result.body.slice(0, 200));
    return null;
  } catch (e) {
    console.error("TR browser login failed:", e);
    // Close browser on error
    if (browser) { await browser.close().catch(() => {}); trBrowser = null; }
    return null;
  }
  // Note: browser stays open for 2FA verification
}

// Verify 2FA via the same browser session
async function verify2FAViaBrowser(processId: string, devicePin: string): Promise<boolean> {
  console.log("TR: verifying 2FA via browser (same session)...");
  try {
    if (!trBrowserPage || !trBrowserContext) {
      console.error("TR: no browser page available for 2FA");
      return false;
    }

    const result = await trBrowserPage.evaluate(async ({ processId, pin }: { processId: string; pin: string }) => {
      const wafMatch = document.cookie.match(/aws-waf-token=([^;]+)/);
      const wafToken = wafMatch?.[1] || "";

      const res = await fetch(`https://api.traderepublic.com/api/v1/auth/web/login/${processId}/${pin}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-aws-waf-token": wafToken,
        },
        credentials: "include",
      });
      return { status: res.status, body: await res.text() };
    }, { processId, pin: devicePin });

    console.log("TR 2FA verify status:", result.status);

    if (result.status === 200) {
      // Extract session cookies from the browser context
      const cookies = await trBrowserContext.cookies("https://api.traderepublic.com");
      const trSession = cookies.find((c: any) => c.name === "tr_session")?.value;
      const trRefresh = cookies.find((c: any) => c.name === "tr_refresh")?.value;

      if (trSession) {
        const cookiePath = join(homedir(), ".tr_api_cookies.json");
        writeFileSync(cookiePath, JSON.stringify({
          trSessionToken: trSession,
          trRefreshToken: trRefresh || "",
          rawCookies: [
            `tr_session=${trSession}; Path=/; Secure; HttpOnly`,
            ...(trRefresh ? [`tr_refresh=${trRefresh}; Path=/; Secure; HttpOnly`] : []),
          ],
        }, null, 2));
        console.log("TR session saved from browser cookies");
      } else {
        console.log("TR: no tr_session cookie found, but 2FA passed — session may be in response");
      }

      // Close browser — we're done
      if (trBrowser) { await trBrowser.close().catch(() => {}); trBrowser = null; }
      return true;
    }

    console.log("TR 2FA response:", result.body?.slice(0, 200));
    if (trBrowser) { await trBrowser.close().catch(() => {}); trBrowser = null; }
    return false;
  } catch (e) {
    console.error("TR 2FA browser verify failed:", e);
    if (trBrowser) { await trBrowser.close().catch(() => {}); trBrowser = null; }
    return false;
  }
}

async function connectTRViaBrowser(): Promise<"connected" | "need_pin" | "failed"> {
  try {
    const loginResult = await loginViaBrowser(trPhoneNumber, trPin);
    if (loginResult?.processId) {
      // Need 2FA — wait for PIN from frontend
      waitingForPin = true;
      console.log("TR browser: 2FA required, waiting for PIN...");

      const devicePin = await new Promise<string>((resolve) => {
        pinResolver = resolve;
      });

      const verified = await verify2FAViaBrowser(loginResult.processId, devicePin);
      waitingForPin = false;
      pinResolver = null;

      if (verified) {
        // Now connect trapi using saved session
        api = new TradeRepublicApi(trPhoneNumber, trPin);
        const loggedIn = await api.login();
        connected = loggedIn;
        return loggedIn ? "connected" : "failed";
      }
    }
    connected = false;
    return "failed";
  } catch (e) {
    console.error("TR browser login failed:", e);
    connected = false;
    return "failed";
  }
}

async function connectTR(): Promise<"connected" | "need_pin" | "failed" | "no_credentials"> {
  if (!trPhoneNumber || !trPin) {
    connected = false;
    return "no_credentials";
  }
  try {
    api = new TradeRepublicApi(trPhoneNumber, trPin);

    // Provide a callback that waits for PIN from the frontend
    const getDevicePin = (): Promise<string> => {
      waitingForPin = true;
      console.log("2FA required — waiting for PIN from frontend...");
      return new Promise((resolve) => {
        pinResolver = resolve;
      });
    };

    const loggedIn = await api.login(getDevicePin);
    waitingForPin = false;
    pinResolver = null;

    if (loggedIn) {
      connected = true;
      return "connected";
    }

    // Login failed — likely WAF 403. Try browser-based login.
    console.log("TR: standard login failed, trying browser-based login (WAF bypass)...");
    return await connectTRViaBrowser();
  } catch (e: any) {
    console.error("TR connection failed:", e?.message || e);
    // Also try browser fallback on exception
    try {
      return await connectTRViaBrowser();
    } catch {}
    waitingForPin = false;
    pinResolver = null;
    connected = false;
    return "failed";
  }
}

// --- BP API connection (via Python bridge) ---
let bpBridge: Subprocess | null = null;
let bpConnected = false;
let bpWaiting2FA: false | "sms" | "app" = false;
let bp2FAMessage = "";
let bpAccounts: any[] = [];
let bpResponseResolver: ((data: any) => void) | null = null;
let bpLogin = "";
let bpPassword = "";
let bpRegion = "";

function sendBP(action: string, params: Record<string, string> = {}) {
  if (!bpBridge?.stdin) throw new Error("BP bridge not running");
  bpBridge.stdin.write(JSON.stringify({ action, params }) + "\n");
  bpBridge.stdin.flush();
}

function waitBPResponse(): Promise<any> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("BP bridge timeout")), 120000);
    bpResponseResolver = (data) => {
      clearTimeout(timeout);
      resolve(data);
    };
  });
}

function startBPBridge() {
  if (bpBridge) {
    try { bpBridge.kill(); } catch {}
  }

  const venvPython = join(import.meta.dir, "../../banque/venv/bin/python");
  const bridgeScript = join(import.meta.dir, "../../banque/bridge.py");

  bpBridge = spawn([venvPython, bridgeScript], {
    stdin: "pipe",
    stdout: "pipe",
    stderr: "pipe",
  });

  // Read stdout as async iterable (Bun ReadableStream)
  (async () => {
    try {
      const decoder = new TextDecoder();
      let buffer = "";
      for await (const chunk of bpBridge!.stdout) {
        buffer += decoder.decode(chunk, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            handleBPMessage(JSON.parse(line));
          } catch {}
        }
      }
    } catch {}
  })();

  // Drain stderr silently
  (async () => {
    try {
      for await (const _ of bpBridge!.stderr) {}
    } catch {}
  })();
}

function handleBPMessage(msg: any) {
  console.log("BP bridge:", msg.type);
  switch (msg.type) {
    case "ready":
      break;
    case "connected":
      bpConnected = true;
      bpWaiting2FA = false;
      bp2FAMessage = "";
      bpAccounts = msg.accounts || [];
      bpResponseResolver?.(msg);
      break;
    case "accounts":
      bpAccounts = msg.accounts || [];
      bpResponseResolver?.(msg);
      break;
    case "2fa_sms":
      bpWaiting2FA = "sms";
      bp2FAMessage = msg.message;
      bpResponseResolver?.(msg);
      break;
    case "2fa_app":
      bpWaiting2FA = "app";
      bp2FAMessage = msg.message;
      bpResponseResolver?.(msg);
      break;
    case "error":
      bpConnected = false;
      bpWaiting2FA = false;
      bp2FAMessage = msg.message || "";
      bpResponseResolver?.(msg);
      break;
  }
}

// --- IBKR API connection (via IB Gateway) ---
let ibApi: IBApi | null = null;
let ibConnected = false;
let ibAccounts: string[] = [];
let ibPositions: any[] = [];
let ibAccountValues: Record<string, Record<string, string>> = {};

async function connectIBKR(host: string, port: number): Promise<boolean> {
  return new Promise((resolve) => {
    let resolved = false;
    const done = (result: boolean) => {
      if (resolved) return;
      resolved = true;
      resolve(result);
    };

    // Timeout after 10s
    setTimeout(() => {
      console.error("IBKR connection timeout");
      done(false);
    }, 10000);

    try {
      if (ibApi) {
        try { ibApi.disconnect(); } catch {}
      }

      console.log(`IBKR: connecting to ${host}:${port}...`);
      ibApi = new IBApi({ host, port, clientId: 1 });

      ibApi.on(EventName.connected, () => {
        console.log("IBKR connected!");
        ibConnected = true;
        ibApi!.reqManagedAccts();
        done(true);
      });

      ibApi.on(EventName.error, (err: Error, code: number) => {
        console.error(`IBKR error [${code}]:`, err.message);
        if (!ibConnected) done(false);
      });

      ibApi.on(EventName.managedAccounts, (accountsList: string) => {
        ibAccounts = accountsList.split(",").filter(Boolean);
        console.log("IBKR accounts:", ibAccounts);
        // Request account summary and positions for all accounts
        for (const acc of ibAccounts) {
          ibApi!.reqAccountUpdates(true, acc);
        }
        ibApi!.reqPositions();
      });

      ibApi.on(EventName.updateAccountValue, (key: string, value: string, currency: string, accountName: string) => {
        if (!ibAccountValues[accountName]) ibAccountValues[accountName] = {};
        ibAccountValues[accountName][`${key}:${currency}`] = value;
      });

      ibApi.on(EventName.position, (account: string, contract: Contract, pos: number, avgCost: number) => {
        if (pos === 0) return; // skip closed positions
        // Update or add position
        const existing = ibPositions.findIndex(
          (p) => p.account === account && p.conId === contract.conId
        );
        const entry = {
          account,
          conId: contract.conId,
          symbol: contract.symbol,
          secType: contract.secType,
          exchange: contract.exchange,
          currency: contract.currency,
          quantity: pos,
          avgCost,
          value: pos * avgCost,
        };
        if (existing >= 0) {
          ibPositions[existing] = entry;
        } else {
          ibPositions.push(entry);
        }
      });

      ibApi.on(EventName.positionEnd, () => {
        console.log(`IBKR positions loaded: ${ibPositions.length}`);
      });

      ibApi.on(EventName.disconnected, () => {
        console.log("IBKR disconnected");
        ibConnected = false;
      });

      ibApi.on(EventName.received, (...args: any[]) => {
        console.log("IBKR received:", args[0]?.toString?.()?.slice(0, 100));
      });

      ibApi.on(EventName.server, (version: number, connectionTime: string) => {
        console.log(`IBKR server: version=${version} time=${connectionTime}`);
      });

      ibApi.connect();
      console.log("IBKR: connect() called");
    } catch (e) {
      console.error("IBKR connect failed:", e);
      done(false);
    }
  });
}

function disconnectIBKR() {
  if (ibApi) {
    try { ibApi.disconnect(); } catch {}
  }
  ibApi = null;
  ibConnected = false;
  ibAccounts = [];
  ibPositions = [];
  ibAccountValues = {};
}

// --- HTTP Server ---
const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(data: any, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders },
  });
}

function error(msg: string, status = 500) {
  return json({ error: msg }, status);
}

Bun.serve({
  port: 3001,
  idleTimeout: 120,
  async fetch(req) {
    const url = new URL(req.url);
    const path = url.pathname;

    // CORS preflight
    if (req.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    // --- Settings ---
    if (path === "/api/settings" && req.method === "GET") {
      return json({
        connectors: [
          {
            id: "trade-republic",
            name: "Trade Republic",
            connected,
            waitingForPin,
            phoneNumber: trPhoneNumber,
            hasPin: !!trPin,
          },
          {
            id: "banque-populaire",
            name: "Banque Populaire",
            connected: bpConnected,
            waiting2FA: bpWaiting2FA,
            message2FA: bp2FAMessage,
            login: bpLogin,
            hasPassword: !!bpPassword,
            region: bpRegion,
            accounts: bpAccounts,
          },
          {
            id: "interactive-brokers",
            name: "Interactive Brokers",
            connected: ibConnected,
            accounts: ibAccounts,
          },
        ],
      });
    }

    if (path === "/api/settings" && req.method === "POST") {
      const body = await req.json();
      const { phoneNumber, pin } = body;
      if (!phoneNumber || !pin) {
        return error("phoneNumber and pin are required", 400);
      }
      // Store in memory only — no disk persistence
      trPhoneNumber = phoneNumber;
      trPin = pin;
      // Start connection (non-blocking if it needs 2FA)
      connectTR().then((status) => {
        console.log("TR connect result:", status);
      });
      // Return immediately — frontend will poll /api/settings to check status
      return json({ success: true, message: "Credentials saved. Connecting..." });
    }

    // --- Import session from browser cookie ---
    if (path === "/api/auth/import-session" && req.method === "POST") {
      const body = await req.json();
      const { sessionToken, refreshToken } = body;
      if (!sessionToken) {
        return error("sessionToken is required", 400);
      }
      // Write session file for trapi
      const cookiePath = join(
        (await import("os")).homedir(),
        ".tr_api_cookies.json"
      );
      const sessionData = {
        trSessionToken: sessionToken,
        trRefreshToken: refreshToken || "",
        rawCookies: [
          `tr_session=${sessionToken}; Path=/; Secure; HttpOnly`,
          ...(refreshToken ? [`tr_refresh=${refreshToken}; Path=/; Secure; HttpOnly`] : []),
        ],
      };
      (await import("fs")).writeFileSync(cookiePath, JSON.stringify(sessionData, null, 2));

      // Now connect using the saved session
      trPhoneNumber = trPhoneNumber || "imported";
      trPin = trPin || "imported";
      connectTR().then((status) => {
        console.log("TR import-session result:", status);
      });
      return json({ success: true, message: "Session imported. Connecting..." });
    }

    // --- 2FA PIN submission ---
    if (path === "/api/auth/pin" && req.method === "POST") {
      if (!waitingForPin || !pinResolver) {
        return error("Not waiting for PIN", 400);
      }
      const body = await req.json();
      const { pin } = body;
      if (!pin) {
        return error("pin is required", 400);
      }
      pinResolver(pin);
      pinResolver = null;
      waitingForPin = false;
      // Wait a bit for login to complete
      await new Promise((r) => setTimeout(r, 3000));
      return json({ connected });
    }

    if (path === "/api/test-connection" && req.method === "POST") {
      connectTR().then((status) => {
        console.log("TR test-connection result:", status);
      });
      return json({ message: "Connecting...", waitingForPin });
    }

    // --- Require TR connection for TR data endpoints (not BP/IBKR routes) ---
    if (!path.startsWith("/api/bp/") && !path.startsWith("/api/ibkr/") && (!connected || !api)) {
      return error("TR API not connected. Configure credentials in Settings.", 503);
    }

    // --- Accounts ---
    if (path === "/api/accounts") {
      const data = await sub("accountPairs");
      const accounts = data.accounts.map((a: any) => ({
        ...a,
        label: PRODUCT_LABELS[a.productType] ?? a.productType,
      }));
      return json({ accounts });
    }

    // --- Cash ---
    if (path === "/api/cash") {
      const [cashData, accountsData] = await Promise.all([
        sub("cash"),
        sub("accountPairs"),
      ]);
      const cashEntries: any[] = Array.isArray(cashData) ? cashData : [cashData];
      const accounts = accountsData.accounts;

      const result = cashEntries.map((entry: any) => {
        const acc = accounts.find(
          (a: any) => a.cashAccountNumber === entry.accountNumber
        );
        return {
          ...entry,
          label: acc ? PRODUCT_LABELS[acc.productType] ?? acc.productType : "Compte courant",
          secAccNo: acc?.securitiesAccountNumber ?? null,
        };
      });
      return json(result);
    }

    // --- Portfolio (all or per account) ---
    const portfolioMatch = path.match(/^\/api\/portfolio(?:\/(.+))?$/);
    if (portfolioMatch) {
      const secAccNo = portfolioMatch[1];

      if (secAccNo) {
        const portfolio = await sub("compactPortfolioByType", { secAccNo });
        return json(portfolio);
      }

      // All accounts — include all categories (cryptos too)
      const accountsData = await sub("accountPairs");
      const results = [];
      for (const acc of accountsData.accounts) {
        const portfolio = await sub("compactPortfolioByType", {
          secAccNo: acc.securitiesAccountNumber,
        });
        results.push({
          label: PRODUCT_LABELS[acc.productType] ?? acc.productType,
          secAccNo: acc.securitiesAccountNumber,
          ...portfolio,
        });
      }
      return json(results);
    }

    // --- Live prices for all positions ---
    if (path === "/api/prices") {
      const accountsData = await sub("accountPairs");
      const allPositions: { isin: string; name: string; netSize: string; categoryType: string; accountLabel: string; averageBuyIn: string }[] = [];

      for (const acc of accountsData.accounts) {
        const portfolio = await sub("compactPortfolioByType", {
          secAccNo: acc.securitiesAccountNumber,
        });
        const label = PRODUCT_LABELS[acc.productType] ?? acc.productType;
        for (const cat of portfolio.categories || []) {
          for (const pos of cat.positions || []) {
            allPositions.push({
              isin: pos.isin,
              name: pos.name,
              netSize: pos.netSize,
              categoryType: cat.categoryType,
              accountLabel: label,
              averageBuyIn: pos.averageBuyIn,
            });
          }
        }
      }

      // Fetch ticker prices in parallel — try multiple exchange suffixes
      const getTickerId = (isin: string, catType: string) => {
        if (catType === "cryptos") return isin; // crypto has no exchange suffix
        return isin + ".LSX";
      };

      const results = await Promise.all(
        allPositions.map(async (pos) => {
          const id = getTickerId(pos.isin, pos.categoryType);
          try {
            const ticker = await sub("ticker", { id });
            return {
              ...pos,
              price: ticker?.last?.price ?? ticker?.bid?.price ?? ticker?.ask?.price ?? null,
              priceData: ticker,
            };
          } catch {
            return { ...pos, price: null, priceData: null };
          }
        })
      );
      return json(results);
    }

    // --- Performance chart (global) ---
    const perfMatch = path.match(/^\/api\/performance\/(.+)$/);
    if (perfMatch) {
      const range = perfMatch[1] as "1d" | "5d" | "1m" | "1y" | "max";
      const data = await sub("userPortfolioChartModifiedDietz", { range });
      return json(data);
    }

    // --- Performance per position (for per-section charts) ---
    if (path === "/api/history") {
      const range = url.searchParams.get("range") || "max";
      const accountsData = await sub("accountPairs");

      // Collect all positions first
      const allPositions: { pos: any; cat: any; label: string }[] = [];
      for (const acc of accountsData.accounts) {
        const portfolio = await sub("compactPortfolioByType", {
          secAccNo: acc.securitiesAccountNumber,
        });
        const label = PRODUCT_LABELS[acc.productType] ?? acc.productType;
        for (const cat of portfolio.categories || []) {
          for (const pos of cat.positions || []) {
            allPositions.push({ pos, cat, label });
          }
        }
      }

      // Fetch all histories in parallel — try with and without exchange suffix
      const getHistoryId = (isin: string, catType: string) => {
        if (catType === "cryptos") return isin;
        return isin + ".LSX";
      };

      const results = await Promise.all(
        allPositions.map(async ({ pos, cat, label }) => {
          const id = getHistoryId(pos.isin, cat.categoryType);
          try {
            const history = await sub("aggregateHistoryLight", { id, range });
            return {
              name: pos.name,
              isin: pos.isin,
              instrumentType: pos.instrumentType,
              categoryType: cat.categoryType,
              accountLabel: label,
              netSize: pos.netSize,
              averageBuyIn: pos.averageBuyIn,
              history: history?.aggregates || history || [],
            };
          } catch {
            return null;
          }
        })
      );
      return json(results.filter(Boolean));
    }

    // --- BP Settings ---
    if (path === "/api/bp/settings" && req.method === "POST") {
      const body = await req.json();
      const { login, password, region } = body;
      if (!login || !password || !region) {
        return error("login, password, and region are required", 400);
      }

      // Store in memory only
      bpLogin = login;
      bpPassword = password;
      bpRegion = region;

      startBPBridge();
      await new Promise(r => setTimeout(r, 500));
      const promise = waitBPResponse();
      sendBP("connect", { login, password, region });
      await promise;

      return json({ success: true, waiting2FA: bpWaiting2FA, message: bp2FAMessage });
    }

    // --- BP 2FA ---
    if (path === "/api/bp/auth" && req.method === "POST") {
      if (!bpBridge) return error("BP bridge not running", 400);

      const body = await req.json();
      const { method, code } = body;

      const promise = waitBPResponse();
      sendBP("validate_2fa", { method: method || "app", code: code || "" });
      await promise;

      return json({ connected: bpConnected, waiting2FA: bpWaiting2FA, accounts: bpAccounts });
    }

    // --- BP Reset ---
    if (path === "/api/bp/reset" && req.method === "POST") {
      if (bpBridge) {
        try { bpBridge.kill(); } catch {}
      }
      bpBridge = null;
      bpConnected = false;
      bpWaiting2FA = false;
      bp2FAMessage = "";
      bpAccounts = [];
      bpResponseResolver = null;
      return json({ success: true });
    }

    // --- BP Accounts ---
    if (path === "/api/bp/accounts" && req.method === "GET") {
      if (!bpConnected) return error("BP not connected", 503);
      return json({ accounts: bpAccounts });
    }

    // --- BP Refresh ---
    if (path === "/api/bp/refresh" && req.method === "POST") {
      if (!bpBridge || !bpConnected) return error("BP not connected", 503);
      const promise = waitBPResponse();
      sendBP("get_accounts");
      await promise;
      return json({ accounts: bpAccounts });
    }

    // --- IBKR Settings ---
    if (path === "/api/ibkr/connect" && req.method === "POST") {
      const body = await req.json();
      const host = body.host || "127.0.0.1";
      const port = body.port || 4002; // 4002=paper, 4001=live
      const ok = await connectIBKR(host, port);
      return json({ connected: ok, accounts: ibAccounts });
    }

    if (path === "/api/ibkr/disconnect" && req.method === "POST") {
      disconnectIBKR();
      return json({ connected: false });
    }

    // --- IBKR Accounts ---
    if (path === "/api/ibkr/accounts" && req.method === "GET") {
      if (!ibConnected) return error("IBKR not connected", 503);
      // Build account summaries
      const accounts = ibAccounts.map((acc) => {
        const values = ibAccountValues[acc] || {};
        return {
          id: acc,
          netLiquidation: parseFloat(values["NetLiquidation:USD"] || values["NetLiquidation:EUR"] || "0"),
          totalCash: parseFloat(values["TotalCashValue:USD"] || values["TotalCashValue:EUR"] || "0"),
          unrealizedPnL: parseFloat(values["UnrealizedPnL:USD"] || values["UnrealizedPnL:EUR"] || "0"),
          realizedPnL: parseFloat(values["RealizedPnL:USD"] || values["RealizedPnL:EUR"] || "0"),
          buyingPower: parseFloat(values["BuyingPower:USD"] || values["BuyingPower:EUR"] || "0"),
          currency: values["NetLiquidation:EUR"] ? "EUR" : "USD",
          raw: values,
        };
      });
      return json({ accounts });
    }

    // --- IBKR Positions ---
    if (path === "/api/ibkr/positions" && req.method === "GET") {
      if (!ibConnected) return error("IBKR not connected", 503);
      return json({ positions: ibPositions });
    }

    // IBKR history not available — requires market data subscription

    return error("Not found", 404);
  },
});

console.log("Server running on http://localhost:3001");
console.log("No credentials stored — configure connectors via the Settings page.");
