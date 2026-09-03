import type { Metadata } from "next";
import { headers } from "next/headers";
import { PySorobanLab } from "./pysoroban-lab";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("host") ?? "localhost:3000";
  const protocol = host.startsWith("localhost") ? "http" : "https";
  const image = `${protocol}://${host}/og.png`;
  const title = "PySoroban — Python contracts for Stellar";
  const description =
    "Write typed Python, compile directly to Soroban Wasm, and verify live contracts on Stellar testnet.";

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: "website",
      images: [{ url: image, width: 1731, height: 909, alt: title }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [image],
    },
  };
}

export default function Home() {
  return <PySorobanLab />;
}
