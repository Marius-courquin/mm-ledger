import "dotenv/config";
import { TradeRepublicApi, createMessage } from "trapi";

const phoneNumber = process.env["TR_PHONE_NUMBER"];
const pin = process.env["TR_PIN"];

if (!phoneNumber || !pin) {
  console.error("Missing TR_PHONE_NUMBER or TR_PIN in .env");
  process.exit(1);
}

const api = new TradeRepublicApi(phoneNumber, pin);

async function main() {
  const loggedIn = await api.login();
  if (!loggedIn) {
    console.error("Login failed");
    process.exit(1);
  }

  console.log("Logged in successfully!\n");

  // Helper: safely parse data (some endpoints return plain text, not JSON)
  const safeParse = (data: string) => {
    try {
      return JSON.parse(data);
    } catch {
      return data;
    }
  };

  // Helper: promisify subscribeOnce
  const sub = <T extends Parameters<typeof createMessage>[0]>(
    type: T,
    opts?: any
  ): Promise<any> =>
    new Promise((resolve) => {
      api.subscribeOnce(createMessage(type, opts), (data) => {
        resolve(data ? safeParse(data) : null);
      });
    });

  // ---- Discover accounts dynamically ----
  const { accounts } = (await sub("accountPairs")) as {
    accounts: {
      securitiesAccountNumber: string;
      cashAccountNumber: string;
      productType: string;
      currency: string;
    }[];
  };

  const productTypeLabel: Record<string, string> = {
    DEFAULT: "CTO",
    TAX_WRAPPER: "PEA",
  };

  // Cash balances
  const cashData = await sub("cash");
  const cashEntries: any[] = Array.isArray(cashData) ? cashData : [cashData];

  // Show all cash accounts (including current account / compte courant)
  console.log("===== All cash balances =====");
  for (const entry of cashEntries) {
    const matchedAcc = accounts.find(
      (a) => a.cashAccountNumber === entry.accountNumber
    );
    const label = matchedAcc
      ? productTypeLabel[matchedAcc.productType] ?? matchedAcc.productType
      : "Compte courant";
    console.log(`  ${label} (${entry.accountNumber}): ${entry.amount} ${entry.currencyId}`);
  }

  // Available cash / payout
  const availableCash = await sub("availableCash");
  const availablePayout = await sub("availableCashForPayout");
  console.log(`\n===== Available cash =====`);
  console.log(`  Available:    ${JSON.stringify(availableCash)}`);
  console.log(`  For payout:   ${JSON.stringify(availablePayout)}`);

  for (const acc of accounts) {
    const label = productTypeLabel[acc.productType] ?? acc.productType;
    const cashEntry = cashEntries.find(
      (e: any) => e.accountNumber === acc.cashAccountNumber
    );

    console.log(`\n===== ${label} (${acc.securitiesAccountNumber}) =====`);
    console.log(`  Cash: ${cashEntry ? `${cashEntry.amount} ${cashEntry.currencyId}` : "N/A"}`);

    // Portfolio for this account
    const portfolio = await sub("compactPortfolioByType", {
      secAccNo: acc.securitiesAccountNumber,
    });

    if (!portfolio?.categories?.length) {
      console.log("  Positions: (none)");
      continue;
    }

    for (const cat of portfolio.categories) {
      console.log(`  --- ${cat.categoryType} ---`);
      for (const pos of cat.positions) {
        const name = pos.derivativeInfo
          ? pos.derivativeInfo.underlying.shortName
          : pos.name;
        console.log(`    ${name} | qty: ${pos.netSize} | avg buy-in: ${pos.averageBuyIn}€`);
      }
    }
  }

  // api.subscribe(
  //   createMessage("ticker", { id: "US88160R1014.LSX" }),
  //   (data) => {
  //     if (!data) return;
  //     console.log("TSLA ticker:", JSON.parse(data));
  //   }
  // );
  //
  // api.subscribeOnce(
  //   createMessage("neonSearch", {
  //     data: {
  //       q: "amd",
  //       page: 1,
  //       pageSize: 3,
  //       filter: [
  //         { key: "type", value: "stock" },
  //         { key: "jurisdiction", value: "DE" },
  //       ],
  //     },
  //   }),
  //   (data) => {
  //     if (!data) return;
  //     console.log("Search results:", JSON.parse(data));
  //   }
  // );
}

main().catch(console.error);
