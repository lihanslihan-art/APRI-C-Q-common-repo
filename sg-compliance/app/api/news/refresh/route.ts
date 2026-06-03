import { NextResponse } from "next/server";
import { NEWS_SOURCES } from "@/lib/news/sources";
import { fetchAll } from "@/lib/news/fetcher";
import { mergeItems } from "@/lib/news/storage";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(req: Request) {
  const required = process.env.NEWS_REFRESH_SECRET;
  if (required) {
    const provided = new URL(req.url).searchParams.get("key");
    if (provided !== required) {
      return NextResponse.json({ error: "unauthorized" }, { status: 401 });
    }
  }
  const startedAt = Date.now();
  const { items, errors } = await fetchAll(NEWS_SOURCES);
  const store = await mergeItems(items);
  return NextResponse.json({
    ok: true,
    sources: NEWS_SOURCES.length,
    fetched: items.length,
    stored: store.items.length,
    durationMs: Date.now() - startedAt,
    errors,
    updatedAt: store.updatedAt,
  });
}
