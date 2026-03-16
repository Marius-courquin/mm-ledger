import "dotenv/config";
import { TradeRepublicApi, createMessage, type Portfolio } from "trapi";

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

  // Debug: check available accounts first
  api.subscribeOnce(createMessage("accountPairs"), (data) => {
    if (!data) return;
    console.log("Account pairs:", data);
  });

  // Debug: check portfolio status
  api.subscribeOnce(createMessage("portfolioStatus"), (data) => {
    if (!data) return;
    console.log("Portfolio status:", data);
  });

  api.subscribeOnce(createMessage("compactPortfolioByType"), (data) => {
    if (!data) return;

    const portfolio: Portfolio = JSON.parse(data);
    console.log("Portfolio raw:", data);
    const categories = portfolio.categories.filter(
      (c) => c.categoryType !== "cryptos"
    );

    if (!categories.length) {
      console.log("No non-crypto positions found.");
      return;
    }

    const companies = Array.from(
      new Set(
        categories.flatMap((category) =>
          category.positions.map((pos) =>
            pos.derivativeInfo
              ? pos.derivativeInfo.underlying.shortName
              : pos.name
          )
        )
      )
    );

    console.log("Portfolio companies:", companies);
  });

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
